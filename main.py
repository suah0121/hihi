import json
import numpy as np
import pandas as pd
import plotly.express as px
import requests
import streamlit as st

st.set_page_config(page_title="전국 고령화/유소년 인구 지도", layout="wide")

st.title("전국 시군구별 인구 구조 변화 단계구분도")


# GeoJSON 및 인구 데이터 로드 (캐싱)
@st.cache_data
def load_raw_data():
    # 1. GeoJSON 로드
    geojson_url = "https://raw.githubusercontent.com/first2022-cyber/contents//main/sigungu_kr.geojson"
    res = requests.get(geojson_url)
    geojson_data = res.json()

    # 2. 인구 CSV(zip) 로드
    pop_url = "https://raw.githubusercontent.com/first2022-cyber/contents//main/population_ts_yearly_gender.zip"
    df_pop = pd.read_csv(pop_url)

    return geojson_data, df_pop


geojson_data, df_pop = load_raw_data()

# ---------------------------------------------------------
# 사이드바 컨트롤러
# ---------------------------------------------------------
st.sidebar.header("조회 조건 설정")

# 1. 지표 선택
indicator = st.sidebar.radio(
    "조회할 지표 선택",
    options=["고령화율 (65세 이상)", "유소년 비율 (0~14세)"],
    index=0,
)

# 2. 연도 선택 슬라이더
available_years = sorted(df_pop["연도"].unique())
selected_year = st.sidebar.slider(
    "연도 선택",
    min_value=int(min(available_years)),
    max_value=int(max(available_years)),
    value=int(max(available_years)),
    step=1,
)

# 3. 시도 선택 드롭다운
sido_list = ["전국"] + sorted(
    list(
        {
            feat["properties"]["시도"]
            for feat in geojson_data["features"]
            if "시도" in feat["properties"]
        }
    )
)
selected_sido = st.sidebar.selectbox("시도 선택 (확대 보기)", options=sido_list)

# ---------------------------------------------------------
# 데이터 전처리 및 계산
# ---------------------------------------------------------
# 선택된 연도 필터링
df_year = df_pop[df_pop["연도"] == selected_year].copy()

# 시군구 5자리 코드 생성 및 행정구역 개편 코드 보정
raw_code = df_year["코드"].astype(str).str.zfill(8).str[:5]

# 코드 보정 규칙 적용
# 42(강원) -> 51, 45(전북) -> 52, 47720(군위군) -> 27720
corrected_code = raw_code.copy()
corrected_code = corrected_code.replace(
    {"47720": "27720"}
)  # 군위군 대구 편입
corrected_code = np.where(
    corrected_code.str.startswith("42"),
    "51" + corrected_code.str[2:],
    corrected_code,
)
corrected_code = np.where(
    corrected_code.str.startswith("45"),
    "52" + corrected_code.str[2:],
    corrected_code,
)

df_year["sigungu_code"] = corrected_code

# 연령대별 열 추출
total_cols = [c for c in df_year.columns if c.startswith("계_")]

# 65세 이상 열
elderly_cols = []
# 0~14세 유소년 열
youth_cols = []

for col in total_cols:
    age_str = col.replace("계_", "").replace("세 이상", "").replace("세", "")
    if age_str.isdigit():
        age = int(age_str)
        if age >= 65:
            elderly_cols.append(col)
        elif age <= 14:
            youth_cols.append(col)

# 인구 합산
df_year["총인구"] = df_year[total_cols].sum(axis=1)
df_year["고령인구"] = df_year[elderly_cols].sum(axis=1)
df_year["유소년인구"] = df_year[youth_cols].sum(axis=1)

# 시군구 단위 집계
df_sigungu = (
    df_year.groupby("sigungu_code")[["총인구", "고령인구", "유소년인구"]]
    .sum()
    .reset_index()
)

# 비율 계산 (%)
df_sigungu["고령화율"] = np.where(
    df_sigungu["총인구"] > 0,
    (df_sigungu["고령인구"] / df_sigungu["총인구"]) * 100,
    0,
).round(2)

df_sigungu["유소년비율"] = np.where(
    df_sigungu["총인구"] > 0,
    (df_sigungu["유소년인구"] / df_sigungu["총인구"]) * 100,
    0,
).round(2)

# GeoJSON 정보 추출 및 병합
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

# 경계 데이터와 인구 데이터 병합
df_map = pd.merge(df_geo_info, df_sigungu, on="sigungu_code", how="left")
df_map["지역명"] = df_map["시도"] + " " + df_map["시군구"]

# ---------------------------------------------------------
# 지표 및 구간 범주화 설정
# ---------------------------------------------------------
if indicator == "고령화율 (65세 이상)":
    target_col = "고령화율"
    unit = "%"

    # 구간: ~19%, 19~23%, 23~28%, 28~38%, 38%~
    bins = [-1, 19, 23, 28, 38, 100]
    labels = ["19% 미만", "19% ~ 23%", "23% ~ 28%", "28% ~ 38%", "38% 이상"]
    color_discrete_map = {
        "19% 미만": "#fee5d9",
        "19% ~ 23%": "#fcae91",
        "23% ~ 28%": "#fb6a4a",
        "28% ~ 38%": "#de2d26",
        "38% 이상": "#a50f15",
    }
else:
    target_col = "유소년비율"
    unit = "%"

    # 유소년 비율 구간: ~8%, 8~10%, 10~12%, 12~14%, 14%~
    bins = [-1, 8, 10, 12, 14, 100]
    labels = ["8% 미만", "8% ~ 10%", "10% ~ 12%", "12% ~ 14%", "14% 이상"]
    color_discrete_map = {
        "8% 미만": "#eff3ff",
        "8% ~ 10%": "#bdd7e7",
        "10% ~ 12%": "#6baed6",
        "12% ~ 14%": "#3182bd",
        "14% 이상": "#08519c",
    }

# 데이터 범주화
df_map["구간"] = pd.cut(
    df_map[target_col], bins=bins, labels=labels, right=False
)
df_map["구간_str"] = df_map["구간"].astype(str).fillna("데이터 없음")
color_discrete_map["데이터 없음"] = "#d9d9d9"  # 누락 지역 회색 처리

# ---------------------------------------------------------
# 상단 지표 카드 (Metrics)
# ---------------------------------------------------------
national_total_pop = df_sigungu["총인구"].sum()
if indicator == "고령화율 (65세 이상)":
    national_target_pop = df_sigungu["고령인구"].sum()
else:
    national_target_pop = df_sigungu["유소년인구"].sum()

national_rate = (
    (national_target_pop / national_total_pop * 100)
    if national_total_pop > 0
    else 0
)

# 데이터가 존재하는 지역 중 최고/최저 추출
df_valid = df_map.dropna(subset=[target_col])
max_row = df_valid.loc[df_valid[target_col].idxmax()]
min_row = df_valid.loc[df_valid[target_col].idxmin()]

col1, col2, col3 = st.columns(3)
col1.metric(
    label=f"{selected_year}년 전국 평균 {indicator.split()[0]}",
    value=f"{national_rate:.2f}%",
)
col2.metric(
    label=f"가장 높은 시군구 ({max_row['지역명']})",
    value=f"{max_row[target_col]:.2f}%",
)
col3.metric(
    label=f"가장 낮은 시군구 ({min_row['지역명']})",
    value=f"{min_row[target_col]:.2f}%",
)

st.markdown("---")

# ---------------------------------------------------------
# 지도 좌표 및 필터링 설정
# ---------------------------------------------------------
# 시도 선택에 따른 위치 중심점 및 줌 레벨 조정
sido_center_map = {
    "서울특별시": {"lat": 37.5665, "lon": 126.9780, "zoom": 9.5},
    "부산광역시": {"lat": 35.1796, "lon": 129.0756, "zoom": 9.5},
    "대구광역시": {"lat": 35.8714, "lon": 128.6014, "zoom": 9.0},
    "인천광역시": {"lat": 37.4563, "lon": 126.7052, "zoom": 9.0},
    "광주광역시": {"lat": 35.1595, "lon": 126.8526, "zoom": 10.0},
    "대전광역시": {"lat": 36.3504, "lon": 127.3845, "zoom": 10.0},
    "울산광역시": {"lat": 35.5384, "lon": 129.3114, "zoom": 9.5},
    "세종특별자치시": {"lat": 36.4800, "lon": 127.2890, "zoom": 10.0},
    "경기도": {"lat": 37.4138, "lon": 127.5183, "zoom": 8.0},
    "강원특별자치도": {"lat": 37.8228, "lon": 128.1555, "zoom": 7.8},
    "충청북도": {"lat": 36.6357, "lon": 127.4917, "zoom": 8.0},
    "충청남도": {"lat": 36.5184, "lon": 126.8000, "zoom": 8.0},
    "전북특별자치도": {"lat": 35.7175, "lon": 127.1530, "zoom": 8.0},
    "전라남도": {"lat": 34.8161, "lon": 126.4629, "zoom": 7.8},
    "경상북도": {"lat": 36.5760, "lon": 128.5056, "zoom": 7.8},
    "경상남도": {"lat": 35.4606, "lon": 128.2132, "zoom": 8.0},
    "제주특별자치도": {"lat": 33.4890, "lon": 126.4983, "zoom": 9.0},
}

if selected_sido != "전국" and selected_sido in sido_center_map:
    center = {
        "lat": sido_center_map[selected_sido]["lat"],
        "lon": sido_center_map[selected_sido]["lon"],
    }
    zoom = sido_center_map[selected_sido]["zoom"]
else:
    center = {"lat": 36.3, "lon": 127.8}
    zoom = 6.2

# ---------------------------------------------------------
# Plotly Choropleth 지도 생성
# ---------------------------------------------------------
fig = px.choropleth_mapbox(
    df_map,
    geojson=geojson_data,
    locations="sigungu_code",
    featureidkey="properties.코드",
    color="구간_str",
    color_discrete_map=color_discrete_map,
    category_orders={"구간_str": labels + ["데이터 없음"]},
    hover_name="지역명",
    hover_data={"sigungu_code": False, "구간_str": False, target_col: ":.2f%"},
    mapbox_style="white-bg",
    center=center,
    zoom=zoom,
    opacity=0.85,
    labels={target_col: f"{indicator.split()[0]} (%)", "구간_str": "구간"},
)

fig.update_layout(
    margin={"r": 0, "t": 10, "l": 0, "b": 0},
    legend_title_text=f"{indicator.split()[0]} 구간",
    height=720,
)

st.plotly_chart(fig, use_container_width=True)

# ---------------------------------------------------------
# 데이터 미매칭 안내 문구
# ---------------------------------------------------------
missing_count = df_map[target_col].isna().sum()
if missing_count > 0:
    missing_regions = df_map[df_map[target_col].isna()]["지역명"].tolist()
    st.info(
        f"ℹ️ **안내**: {selected_year}년 데이터 기준으로 행정구역 변경 또는 데이터 미비로 인해 "
        f"경계 파일과 일치하지 않는 **{missing_count}개 지역**은 회색으로 표시됩니다.\n\n"
        f"• 대상 지역: {', '.join(missing_regions)}"
    )
