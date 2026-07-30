# main.py
# 필요한 라이브러리를 불러옵니다.
import streamlit as st
import pandas as pd
import plotly.express as px
import requests

# --- 1. 초기 설정 ---

# Streamlit 페이지의 레이아웃을 넓게 설정하고, 페이지 제목을 지정합니다.
st.set_page_config(layout="wide", page_title="전국 고령화 지도")

# 앱의 중앙에 제목을 표시합니다.
st.title("🗺️ 전국 시군구별 고령화율 지도 (2026년 기준)")
st.markdown("시군구별 65세 이상 인구 비율을 나타내는 단계구분도입니다.")


# --- 2. 데이터 로딩 ---

# 데이터가 저장된 URL 주소입니다.
POP_URL = "https://raw.githubusercontent.com/greatsong/modudata/main/data/population_yearly.csv.gz"
GEOJSON_URL = "https://raw.githubusercontent.com/greatsong/modudata/main/data/boundaries/sigungu_kr.geojson"

# @st.cache_data: 데이터 로딩처럼 오래 걸리는 작업을 캐시에 저장하여 앱 성능을 향상시킵니다.
@st.cache_data
def load_population_data():
    """연도별 인구 데이터를 불러옵니다. '코드' 열은 문자열로 읽어옵니다."""
    df = pd.read_csv(POP_URL, dtype={"코드": str})
    return df

@st.cache_data
def load_geojson_data():
    """시군구 경계 GeoJSON 데이터를 불러옵니다."""
    response = requests.get(GEOJSON_URL)
    geojson = response.json()
    return geojson

# 데이터 로딩 함수를 실행하고, 오류 발생 시 메시지를 띄우고 앱 실행을 멈춥니다.
try:
    population_df = load_population_data()
    sigungu_geojson = load_geojson_data()
except Exception as e:
    st.error(f"데이터를 불러오는 중 오류가 발생했습니다: {e}")
    st.stop()


# --- 3. 데이터 전처리 ---

# st.spinner를 사용해 사용자에게 데이터 처리 중임을 알립니다.
with st.spinner('고령화율 데이터를 계산하는 중입니다...'):
    # 가장 최신 연도의 데이터를 선택합니다.
    latest_year = population_df["연도"].max()
    df = population_df[population_df["연도"] == latest_year].copy()

    # '코드' 열에서 앞 5자리를 잘라 '시군구코드' 열을 만듭니다.
    df["시군구코드"] = df["코드"].str[:5]

    # '계_'로 시작하는 모든 인구 열(총인구)을 찾습니다.
    total_pop_cols = [col for col in df.columns if col.startswith("계_")]

    # '계_'로 시작하는 열 중에서 65세 이상 인구 열을 찾습니다.
    elderly_pop_cols = []
    for col in total_pop_cols:
        try:
            age_str = col.split("_")[1].replace("세", "").replace(" 이상", "")
            if int(age_str) >= 65:
                elderly_pop_cols.append(col)
        except (ValueError, IndexError):
            continue

    # 시군구 코드를 기준으로 그룹화하여 인구를 합산합니다.
    agg_dict = {col: "sum" for col in total_pop_cols}
    sigungu_pop = df.groupby("시군구코드").agg(agg_dict).reset_index()

    # 총인구와 고령인구 합계를 계산합니다.
    sigungu_pop["총인구"] = sigungu_pop[total_pop_cols].sum(axis=1)
    sigungu_pop["고령인구"] = sigungu_pop[elderly_pop_cols].sum(axis=1)

    # 고령화율을 계산합니다.
    sigungu_pop["고령화율"] = sigungu_pop.apply(
        lambda row: (row["고령인구"] / row["총인구"]) * 100 if row["총인구"] > 0 else 0,
        axis=1
    )

    # GeoJSON 데이터에서 시군구 이름, 시도 정보를 추출하여 데이터프레임으로 만듭니다.
    sigungu_info = pd.DataFrame([
        {
            "시군구코드": feature["properties"]["코드"],
            "시군구": feature["properties"]["시군구"],
            "시도": feature["properties"]["시도"],
        }
        for feature in sigungu_geojson["features"]
    ])

    # 인구 데이터와 지역 정보(이름) 데이터를 '시군구코드'를 기준으로 합칩니다.
    merged_df = pd.merge(sigungu_info, sigungu_pop, on="시군구코드")

    # 고령화율에 따라 5개 구간으로 나눕니다.
    bins = [0, 19, 23, 28, 38, float('inf')]
    labels = ["19% 미만", "19% ~ 23%", "23% ~ 28%", "28% ~ 38%", "38% 이상"]
    merged_df["고령화율_구간"] = pd.cut(
        merged_df["고령화율"], bins=bins, labels=labels, right=False
    )
    
    # 고령화율 순위 열을 추가합니다. (높은 순서대로 1, 2, 3...)
    merged_df['고령화율_순위'] = merged_df['고령화율'].rank(method='min', ascending=False).astype(int)


# --- 4. 완주군 데이터 하이라이트 ---

# 하이라이트할 지역을 지정합니다.
TARGET_SIDO = "전라북도"
TARGET_SIGUNGU = "완주군"

# 지정한 지역의 데이터를 찾습니다.
target_data = merged_df[
    (merged_df["시도"] == TARGET_SIDO) & (merged_df["시군구"] == TARGET_SIGUNGU)
]

# st.metric을 사용하여 내 지역 정보를 카드 형태로 표시합니다.
st.markdown("---")
st.subheader(f"📍 내 지역 ({TARGET_SIDO} {TARGET_SIGUNGU}) 고령화율 현황")

if not target_data.empty:
    target_row = target_data.iloc[0]
    total_count = len(merged_df)
    
    col1, col2 = st.columns(2)
    col1.metric("고령화율", f"{target_row['고령화율']:.2f}%")
    col2.metric("전국 순위 (높은 순)", f"{target_row['고령화율_순위']}위 / {total_count}곳")

    # 하이라이트할 지역의 GeoJSON 피처를 찾습니다.
    target_feature = None
    for feature in sigungu_geojson["features"]:
        if (feature["properties"]["시도"] == TARGET_SIDO and
            feature["properties"]["시군구"] == TARGET_SIGUNGU):
            target_feature = feature
            break

    # 하이라이트용 GeoJSON 객체를 생성합니다.
    highlight_geojson = {
        "type": "FeatureCollection",
        "features": [target_feature] if target_feature else []
    }
else:
    st.warning(f"'{TARGET_SIDO} {TARGET_SIGUNGU}' 데이터를 찾을 수 없습니다.")
    highlight_geojson = None

st.markdown("---")

# --- 5. 지도 시각화 ---

# 각 고령화율 구간에 사용할 색상을 지정합니다.
color_map = {
    "19% 미만": "#ccece6", "19% ~ 23%": "#99d8c9", "23% ~ 28%": "#66c2a4",
    "28% ~ 38%": "#2ca25f", "38% 이상": "#006d2c",
}

# Plotly Express를 사용하여 단계구분도를 생성합니다.
fig = px.choropleth_mapbox(
    merged_df, geojson=sigungu_geojson, locations="시군구코드", featureidkey="properties.코드",
    color="고령화율_구간", color_discrete_map=color_map,
    category_orders={"고령화율_구간": labels}, mapbox_style="white-bg",
    zoom=6.2, center={"lat": 35.9, "lon": 127.7}, opacity=0.8,
    hover_name="시군구",
    hover_data={"시도": True, "고령화율": ":.2f", "고령화율_구간": False, "시군구코드": False},
    labels={"고령화율_구간": "고령화율", "시도": "시도", "고령화율": "고령화율 (%)"}
)

# [수정됨] 문자열 줄바꿈으로 인한 SyntaxError를 방지하기 위해 한 줄로 작성하고 
 태그를 사용했습니다.
fig.update_traces(
    customdata=merged_df[['시도', '고령화율']],
    hovertemplate="<b>%{hover_name}</b>
%{customdata[0]}
고령화율: %{customdata[1]:.2f}%<extra></extra>"
)

# 지도 레이아웃을 설정합니다.
fig.update_layout(
    margin={"r":0, "t":0, "l":0, "b":0},
    legend_title_text='고령화율 구간',
    # 지도 위에 여러 레이어를 겹쳐서 표시합니다.
    mapbox_layers=[
        # 1번 레이어: 모든 시군구의 기본 경계선 (검은색, 얇게)
        {
            "sourcetype": "geojson",
            "source": sigungu_geojson,
            "type": "line",
            "color": "black",
            "line": {"width": 0.5}
        }
    ]
)

# 하이라이트 GeoJSON이 존재할 경우, 지도에 굵은 빨간색 경계선을 추가합니다.
if highlight_geojson and highlight_geojson['features']:
    fig.update_layout(
        mapbox_layers=fig.layout.mapbox_layers + (
            # 2번 레이어: 완주군 경계선 (붉은색, 굵게)
            {
                "sourcetype": "geojson",
                "source": highlight_geojson,
                "type": "line",
                "color": "red",
                "line": {"width": 2.5}
            },
        )
    )

# Streamlit 앱에 지도를 표시합니다.
st.plotly_chart(fig, use_container_width=True)


# --- 6. 상위/하위 10개 지역 표 표시 ---

st.markdown("---")
st.subheader("📊 고령화율 상위 및 하위 10개 지역")

# 고령화율을 기준으로 정렬하여 10개씩 선택합니다.
top_10 = merged_df.sort_values(by="고령화율", ascending=False).head(10)
bottom_10 = merged_df.sort_values(by="고령화율", ascending=True).head(10)

# 표에 표시할 열을 선택하고 인덱스를 1부터 시작하도록 설정합니다.
display_cols = ["시도", "시군구", "고령화율"]
top_10_display = top_10[display_cols].reset_index(drop=True)
bottom_10_display = bottom_10[display_cols].reset_index(drop=True)
top_10_display.index += 1
bottom_10_display.index += 1

# st.columns를 사용하여 화면을 두 개의 열로 나눕니다.
col1, col2 = st.columns(2)

with col1:
    st.markdown("#### 📈 고령화율 높은 지역 Top 10")
    st.dataframe(
        top_10_display,
        column_config={"고령화율": st.column_config.NumberColumn("고령화율 (%)", format="%.2f")},
        use_container_width=True
    )

with col2:
    st.markdown("#### 📉 고령화율 낮은 지역 Top 10")
    st.dataframe(
        bottom_10_display,
        column_config={"고령화율": st.column_config.NumberColumn("고령화율 (%)", format="%.2f")},
        use_container_width=True
    )
