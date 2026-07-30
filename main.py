import json
import requests
import pandas as pd
import numpy as np
import plotly.express as px
import streamlit as st

# ------------------------------------------------------------
# 전국 시군구 고령화율 단계구분도
# ------------------------------------------------------------
# 초보자도 이해하기 쉽도록 자세히 주석을 달았습니다.
# ------------------------------------------------------------

st.set_page_config(
    page_title="전국 시군구 고령화 지도",
    layout="wide",
)

st.title("🗺️ 전국 시군구 고령화 지도")
st.caption("시군구별 65세 이상 인구 비율(가장 최신 연도)")

# ------------------------------------------------------------
# 데이터 주소
# ------------------------------------------------------------

POP_URL = (
    "https://raw.githubusercontent.com/greatsong/modudata/main/data/"
    "population_yearly.csv.gz"
)

GEO_URL = (
    "https://raw.githubusercontent.com/greatsong/modudata/main/data/"
    "boundaries/sigungu_kr.geojson"
)


# ------------------------------------------------------------
# 인구 데이터 불러오기
# ------------------------------------------------------------
@st.cache_data(show_spinner=False)
def load_population():

    # 코드 열은 반드시 문자열로 읽는다.
    df = pd.read_csv(
        POP_URL,
        compression="gzip",
        dtype={"코드": str},
        low_memory=False,
    )

    return df


# ------------------------------------------------------------
# GeoJSON 불러오기
# ------------------------------------------------------------
@st.cache_data(show_spinner=False)
def load_geojson():

    r = requests.get(GEO_URL)
    r.raise_for_status()

    return r.json()


# ------------------------------------------------------------
# 최신 연도의 시군구 고령화율 계산
# ------------------------------------------------------------
@st.cache_data(show_spinner=False)
def make_sigungu_table(df):

    latest_year = df["연도"].max()

    df = df[df["연도"] == latest_year].copy()

    # 시군구 코드는 행정동 코드 앞 5자리
    df["시군구코드"] = df["코드"].str[:5]

    # --------------------------------------------------------
    # 총인구 계산
    # --------------------------------------------------------
    total_col = None

    # 보통 '계_총인구수'가 있으면 가장 정확하다.
    candidates = [
        "계_총인구수",
        "계",
        "총인구",
    ]

    for c in candidates:
        if c in df.columns:
            total_col = c
            break

    # 총인구 열이 없다면 모든 나이의 계_ 열을 더한다.
    if total_col is None:

        age_cols = []

        for col in df.columns:
            if col.startswith("계_"):
                age_cols.append(col)

        df["총인구"] = df[age_cols].sum(axis=1)

        total_col = "총인구"

    # --------------------------------------------------------
    # 65세 이상 열 찾기
    # --------------------------------------------------------
    old_cols = []

    for age in range(65, 100):
        col = f"계_{age}세"
        if col in df.columns:
            old_cols.append(col)

    if "계_100세 이상" in df.columns:
        old_cols.append("계_100세 이상")

    df["65세이상"] = df[old_cols].sum(axis=1)

    # --------------------------------------------------------
    # 읍면동 -> 시군구 집계
    # --------------------------------------------------------
    agg = (
        df.groupby(
            ["시군구코드", "시도", "시군구"],
            as_index=False,
        )[[total_col, "65세이상"]]
        .sum()
    )

    agg["고령화율"] = agg["65세이상"] / agg[total_col] * 100

    return agg, latest_year


# ------------------------------------------------------------
# 단계 구분
# ------------------------------------------------------------
def classify(rate):

    if rate < 19:
        return "19% 미만"
    elif rate < 23:
        return "19~23%"
    elif rate < 28:
        return "23~28%"
    elif rate < 38:
        return "28~38%"
    else:
        return "38% 이상"


# ------------------------------------------------------------
# 데이터 읽기
# ------------------------------------------------------------
with st.spinner("데이터 불러오는 중..."):

    pop = load_population()
    geo = load_geojson()
    sigungu, latest_year = make_sigungu_table(pop)

sigungu["구간"] = sigungu["고령화율"].apply(classify)

# ------------------------------------------------------------
# Plotly는 featureidkey로 GeoJSON 속성을 연결한다.
# 이름이 아니라 코드로 연결.
# ------------------------------------------------------------

category_order = {
    "구간": [
        "19% 미만",
        "19~23%",
        "23~28%",
        "28~38%",
        "38% 이상",
    ]
}

# 낮은 값은 옅게, 높은 값은 진하게
color_map = {
    "19% 미만": "#f7fbff",
    "19~23%": "#c6dbef",
    "23~28%": "#6baed6",
    "28~38%": "#2171b5",
    "38% 이상": "#08306b",
}

fig = px.choropleth(
    sigungu,
    geojson=geo,
    locations="시군구코드",
    featureidkey="properties.코드",
    color="구간",
    category_orders=category_order,
    color_discrete_map=color_map,
    custom_data=[
        "시군구",
        "시도",
        "고령화율",
    ],
)

# 배경지도 제거
fig.update_geos(
    fitbounds="locations",
    visible=False,
)

fig.update_traces(
    marker_line_color="white",
    marker_line_width=0.6,
    hovertemplate=(
        "<b>%{customdata[0]}</b><br>"
        "시도: %{customdata[1]}<br>"
        "고령화율: %{customdata[2]:.1f}%"
        "<extra></extra>"
    ),
)

fig.update_layout(
    height=800,
    margin=dict(l=0, r=0, t=0, b=0),
    legend_title_text="65세 이상 비율",
)

st.subheader(f"{latest_year}년 시군구 고령화율")

st.plotly_chart(
    fig,
    use_container_width=True,
)

# ------------------------------------------------------------
# 상위 / 하위 10개
# ------------------------------------------------------------

left, right = st.columns(2)

with left:

    st.subheader("고령화율 높은 곳 TOP 10")

    high = (
        sigungu.sort_values("고령화율", ascending=False)
        .head(10)
        .copy()
    )

    high["고령화율(%)"] = high["고령화율"].round(1)

    st.dataframe(
        high[
            [
                "시도",
                "시군구",
                "고령화율(%)",
            ]
        ],
        hide_index=True,
        use_container_width=True,
    )

with right:

    st.subheader("고령화율 낮은 곳 TOP 10")

    low = (
        sigungu.sort_values("고령화율", ascending=True)
        .head(10)
        .copy()
    )

    low["고령화율(%)"] = low["고령화율"].round(1)

    st.dataframe(
        low[
            [
                "시도",
                "시군구",
                "고령화율(%)",
            ]
        ],
        hide_index=True,
        use_container_width=True,
    )

st.caption(
    "고령화율 = (65세 이상 인구 ÷ 총인구) × 100"
)
