import json
import numpy as np
import pandas as pd
import plotly.express as px
import requests
import streamlit as st

st.set_page_config(page_title="전국 고령화 단계구분도", layout="wide")

st.title("2026년 전국 시군구별 고령화 단계구분도")


@st.cache_data
def load_data():
    # 1. GeoJSON 데이터 다운로드 및 로드
    geojson_url = "https://raw.githubusercontent.com/first2022-cyber/contents//main/sigungu_kr.geojson"
    res = requests.get(geojson_url)
    geojson_data = res.json()

    # 2. 인구 CSV(zip) 데이터 로드
    pop_url = "https://raw.githubusercontent.com/first2022-cyber/contents//main/population_ts_yearly_gender.zip"
    df = pd.read_csv(pop_url)

    # 3. 2026년 데이터만 필터링
    df_2026 = df[df["연도"] == 2026].copy()

    # 코드 열을 5자리 문자열 시군구 코드로 변환
    df_2026["sigungu_code"] = (
        df_2026["코드"].astype(str).str.zfill(8).str[:5]
    )

    # 전체 인구 열('계_'로 시작하는 전체 열)
    total_cols = [c for c in df_2026.columns if c.startswith("계_")]

    # 65세 이상 인구 열('계_65세' ~ '계_100세 이상')
    # 나이 숫자를 추출하여 65세 이상인 열만 선택
    elderly_cols = []
    for col in total_cols:
        age_str = col.replace("계_", "").replace("세 이상", "").replace("세", "")
        if age_str.isdigit() and int(age_str) >= 65:
            elderly_cols.append(col)

    # 시군구 단위 그룹화 및 합산
    df_2026["총인구"] = df_2026[total_cols].sum(axis=1)
    df_2026["고령인구"] = df_2026[elderly_cols].sum(axis=1)

    df_sigungu = (
        df_2026.groupby("sigungu_code")[["총인구", "고령인구"]]
        .sum()
        .reset_index()
    )

    # 고령화율(%) 계산
    df_sigungu["고령화율"] = np.where(
        df_sigungu["총인구"] > 0,
        (df_sigungu["고령인구"] / df_sigungu["총인구"]) * 100,
        0,
    )
    df_sigungu["고령화율"] = df_sigungu["고령화율"].round(2)

    # GeoJSON의 '코드', '시군구', '시도' 속성 추출하여 매핑용 데이터프레임 생성
    geo_info = []
    for feat in geojson_data["features"]:
        props = feat["properties"]
        geo_info.append(
            {
                "sigungu_code": str(props["코드"]),
                "시군구": props["시군구"],
                "시도": props["시도"],
            }
        )
    df_geo_info = pd.DataFrame(geo_info)

    # 시군구 이름 정보를 병합하여 툴팁 표출 준비
    df_result = pd.merge(df_sigungu, df_geo_info, on="sigungu_code", how="inner")
    df_result["지역명"] = df_result["시도"] + " " + df_result["시군구"]

    return geojson_data, df_result


with st.spinner("데이터를 읽어오는 중입니다..."):
    geojson_data, df_map = load_data()

# Plotly Choropleth 지도 생성
fig = px.choropleth_mapbox(
    df_map,
    geojson=geojson_data,
    locations="sigungu_code",
    featureidkey="properties.코드",
    color="고령화율",
    color_continuous_scale="Reds",
    hover_name="지역명",
    hover_data={"sigungu_code": False, "고령화율": ":.2f%"},
    mapbox_style="white-bg",
    center={"lat": 36.3, "lon": 127.8},
    zoom=6.2,
    opacity=0.8,
)

fig.update_layout(
    margin={"r": 0, "t": 40, "l": 0, "b": 0},
    coloraxis_colorbar={"title": "고령화율 (%)"},
    height=750,
)

st.plotly_chart(fig, use_container_width=True)
