"""
전국 시군구 고령화 지도 (스트림릿 앱)
------------------------------------
- 인구 데이터: 읍·면·동 단위 연령별 인구 (2015~2026)
- 지도 데이터: 시군구 경계 GeoJSON
- 시군구별 65세 이상 인구 비율(고령화율)을 5단계 색으로 표시
"""

import re
import json

import numpy as np
import pandas as pd
import requests
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go

# ------------------------------------------------------------
# 0. 기본 화면 설정
# ------------------------------------------------------------
st.set_page_config(page_title="전국 고령화 지도", layout="wide")
st.title("전국 시군구 고령화 지도")
st.caption("시군구별 65세 이상 인구 비율(고령화율)을 색으로 표현한 지도입니다.")

POP_URL = "https://raw.githubusercontent.com/greatsong/modudata/main/data/population_yearly.csv.gz"
GEO_URL = "https://raw.githubusercontent.com/greatsong/modudata/main/data/boundaries/sigungu_kr.geojson"


# ------------------------------------------------------------
# 1. 데이터 불러오기 (한 번 불러온 데이터는 캐시에 저장해서 재사용)
# ------------------------------------------------------------
@st.cache_data(show_spinner="인구 데이터를 불러오는 중입니다...")
def load_population():
    """읍·면·동 단위 연령별 인구 데이터를 불러온다.
    '코드' 열은 숫자가 아니라 이름표이므로 반드시 문자열(str)로 읽는다."""
    df = pd.read_csv(POP_URL, compression="gzip", dtype={"코드": str})
    # 혹시 앞자리 0이 사라졌을 경우를 대비해 8자리로 다시 맞춰준다.
    df["코드"] = df["코드"].str.zfill(8)
    return df


@st.cache_data(show_spinner="지도 경계 데이터를 불러오는 중입니다...")
def load_geojson():
    """시군구 경계선이 담긴 GeoJSON 파일을 불러온다."""
    res = requests.get(GEO_URL)
    res.raise_for_status()
    geo = res.json()
    # 지도의 '코드' 속성도 5자리 문자열로 통일한다.
    for feature in geo["features"]:
        code = str(feature["properties"]["코드"])
        feature["properties"]["코드"] = code.zfill(5)
    return geo


with st.spinner("데이터 준비 중..."):
    df = load_population()
    geojson = load_geojson()

# ------------------------------------------------------------
# 2. 가장 최신 연도만 골라서 사용
# ------------------------------------------------------------
latest_year = int(df["연도"].max())
df_latest = df[df["연도"] == latest_year].copy()

# 읍·면·동 코드(8자리)의 앞 5자리가 시군구 코드
df_latest["시군구코드"] = df_latest["코드"].str[:5]

# ------------------------------------------------------------
# 3. 나이별 인구 열 중에서 '계_'로 시작하는 열(남녀 합계)만 골라서
#    전체 인구와 65세 이상 인구를 계산
# ------------------------------------------------------------
age_cols = [c for c in df.columns if c.startswith("계_")]


def extract_age(col_name: str):
    """'계_0세', '계_100세 이상' 같은 열 이름에서 나이 숫자만 뽑아낸다."""
    m = re.search(r"(\d+)", col_name)
    return int(m.group(1)) if m else None


elderly_cols = [c for c in age_cols if extract_age(c) is not None and extract_age(c) >= 65]

df_latest["총인구"] = df_latest[age_cols].sum(axis=1)
df_latest["고령인구"] = df_latest[elderly_cols].sum(axis=1)

# ------------------------------------------------------------
# 4. 읍·면·동 데이터를 시군구 단위로 합산
# ------------------------------------------------------------
grouped = (
    df_latest.groupby("시군구코드")
    .agg(
        시도=("시도", "first"),
        시군구=("시군구", "first"),
        총인구=("총인구", "sum"),
        고령인구=("고령인구", "sum"),
    )
    .reset_index()
)

grouped["고령화율"] = (grouped["고령인구"] / grouped["총인구"] * 100).round(2)

# ------------------------------------------------------------
# 5. 고령화율을 5단계 구간으로 나누기 (경계값: 19, 23, 28, 38)
# ------------------------------------------------------------
bins = [-np.inf, 19, 23, 28, 38, np.inf]
labels = ["19% 미만", "19%~23%", "23%~28%", "28%~38%", "38% 이상"]

grouped["구간"] = pd.cut(grouped["고령화율"], bins=bins, labels=labels)

# 낮은 단계는 옅은 색, 높은 단계는 진한 색으로 지정
colors = ["#eff3ff", "#bdd7e7", "#6baed6", "#3182bd", "#08306b"]
color_map = dict(zip(labels, colors))

# ------------------------------------------------------------
# 5-1. 내가 사는 지역(완주군)을 항상 다른 지역과 비교해서 보여주기
# ------------------------------------------------------------
MY_SIDO = "전라북도"
MY_SIGUNGU = "완주군"

# 시도 이름이 '전북특별자치도' 등으로 바뀌었을 수도 있으니 '전북'이 들어간 행을 폭넓게 찾는다.
my_row = grouped[
    grouped["시군구"].str.contains(MY_SIGUNGU)
    & grouped["시도"].str.contains("전북|전라북도", regex=True)
]

# 전국 평균 고령화율 (인구 가중 평균)
national_avg = grouped["고령인구"].sum() / grouped["총인구"].sum() * 100

# 전국 순위를 매긴다 (고령화율이 높을수록 1위)
grouped_ranked = grouped.sort_values("고령화율", ascending=False).reset_index(drop=True)
grouped_ranked["순위"] = grouped_ranked.index + 1
total_count = len(grouped_ranked)

my_code = None
if not my_row.empty:
    my_info = my_row.iloc[0]
    my_code = my_info["시군구코드"]
    my_ratio = my_info["고령화율"]
    my_sido_name = my_info["시도"]

    my_rank = int(grouped_ranked.loc[grouped_ranked["시군구코드"] == my_code, "순위"].iloc[0])

    # 완주군이 속한 시도 전체 평균 (인구 가중 평균)
    sido_group = grouped[grouped["시도"] == my_sido_name]
    sido_avg = sido_group["고령인구"].sum() / sido_group["총인구"].sum() * 100

st.subheader("완주군 vs 전국 비교")

if my_code is None:
    st.warning("데이터에서 완주군을 찾지 못했습니다. 지역 이름이 바뀌었을 수 있습니다.")
else:
    m1, m2, m3 = st.columns(3)
    m1.metric("완주군 고령화율", f"{my_ratio:.1f}%")
    m2.metric("전국 평균", f"{national_avg:.1f}%", delta=f"{my_ratio - national_avg:+.1f}%p")
    m3.metric("전국 순위 (높은 순)", f"{my_rank}위 / {total_count}개 중")
    st.caption(f"{my_sido_name} 평균 고령화율: {sido_avg:.1f}%")

    # 완주군을 전국 평균, 시도 평균, 전국 최고·최저 지역과 나란히 비교하는 막대그래프
    compare_df = pd.DataFrame(
        {
            "구분": ["완주군", f"{my_sido_name} 평균", "전국 평균", "전국 최고 지역", "전국 최저 지역"],
            "고령화율": [
                my_ratio,
                sido_avg,
                national_avg,
                grouped["고령화율"].max(),
                grouped["고령화율"].min(),
            ],
        }
    )
    fig_compare = px.bar(
        compare_df,
        x="구분",
        y="고령화율",
        text="고령화율",
        color="구분",
        color_discrete_sequence=px.colors.qualitative.Set2,
    )
    fig_compare.update_traces(texttemplate="%{text:.1f}%", textposition="outside")
    fig_compare.update_layout(
        showlegend=False,
        yaxis_title="고령화율(%)",
        xaxis_title="",
        height=350,
        margin=dict(l=0, r=0, t=10, b=0),
    )
    st.plotly_chart(fig_compare, use_container_width=True)

# ------------------------------------------------------------
# 6. 지도 그리기 (단계구분도)
# ------------------------------------------------------------
st.subheader(f"{latest_year}년 시군구별 고령화율")

fig = px.choropleth(
    grouped,
    geojson=geojson,
    locations="시군구코드",
    featureidkey="properties.코드",
    color="구간",
    color_discrete_map=color_map,
    category_orders={"구간": labels},
    hover_name="시군구",
    hover_data={
        "시도": True,
        "고령화율": ":.1f",
        "시군구코드": False,
        "구간": False,
    },
    labels={"구간": "고령화율 구간", "고령화율": "고령화율(%)"},
)

# 배경 지도(타일)는 보이지 않게 하고, 경계선만 나오도록 설정
fig.update_geos(visible=False, fitbounds="locations")
fig.update_traces(marker_line_color="white", marker_line_width=0.6)
fig.update_layout(
    height=700,
    margin=dict(l=0, r=0, t=10, b=0),
    legend_title_text="고령화율 구간",
)

# 완주군만 빨간 테두리로 한 번 더 그려서 항상 눈에 띄게 강조한다.
if my_code is not None:
    fig.add_trace(
        go.Choropleth(
            geojson=geojson,
            locations=[my_code],
            z=[1],
            featureidkey="properties.코드",
            colorscale=[[0, "rgba(0,0,0,0)"], [1, "rgba(0,0,0,0)"]],
            showscale=False,
            marker_line_color="red",
            marker_line_width=4,
            hoverinfo="skip",
        )
    )

st.plotly_chart(fig, use_container_width=True)
if my_code is not None:
    st.caption("지도의 붉은 테두리로 표시된 지역이 완주군입니다.")

# ------------------------------------------------------------
# 7. 고령화율 상위 10곳 / 하위 10곳 표
# ------------------------------------------------------------
st.subheader("고령화율 상위 10곳 / 하위 10곳")

table_cols = ["시도", "시군구", "고령화율"]

top10 = grouped.sort_values("고령화율", ascending=False).head(10)[table_cols].reset_index(drop=True)
bottom10 = grouped.sort_values("고령화율", ascending=True).head(10)[table_cols].reset_index(drop=True)

# 표에서 보기 좋게 순위(1~10)를 붙이고, 고령화율에 % 표시를 붙인다.
top10.index = top10.index + 1
bottom10.index = bottom10.index + 1
top10["고령화율"] = top10["고령화율"].map(lambda x: f"{x:.1f}%")
bottom10["고령화율"] = bottom10["고령화율"].map(lambda x: f"{x:.1f}%")

col1, col2 = st.columns(2)
with col1:
    st.markdown("**고령화율 높은 지역 TOP 10**")
    st.dataframe(top10, use_container_width=True)
with col2:
    st.markdown("**고령화율 낮은 지역 TOP 10**")
    st.dataframe(bottom10, use_container_width=True)

if my_code is not None:
    if my_rank <= 10:
        st.info(f"완주군은 전국 고령화율 상위 10곳 안에 있습니다. (전국 {my_rank}위)")
    elif my_rank > total_count - 10:
        st.info(f"완주군은 전국 고령화율 하위 10곳 안에 있습니다. (전국 {my_rank}위)")
    else:
        st.info(f"완주군은 상위·하위 10곳에는 포함되지 않으며, 전국 {my_rank}위 / {total_count}개 중입니다.")

st.caption("데이터 출처: modudata (읍·면·동 연령별 인구, 시군구 경계 GeoJSON)")
