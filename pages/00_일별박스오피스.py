import streamlit as st
import pandas as pd
import requests
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

st.set_page_config(page_title="박스오피스 대시보드", layout="wide")
st.title("🎬 박스오피스 대시보드")

# ------------------------------------------------------------
# 0. 인증키 확인
# ------------------------------------------------------------
KOBIS_KEY = st.secrets.get("KOBIS_KEY")
if not KOBIS_KEY:
    st.error("Secrets에 KOBIS_KEY가 설정되어 있지 않습니다.")
    st.stop()

URL = "https://www.kobis.or.kr/kobisopenapi/webservice/rest/boxoffice/searchDailyBoxOfficeList.json"

# ------------------------------------------------------------
# 1. 날짜 고르기 (오늘 것은 아직 집계 전이라 어제까지만 고를 수 있다)
# ------------------------------------------------------------
today_kst = datetime.now(ZoneInfo("Asia/Seoul")).date()
yesterday_kst = today_kst - timedelta(days=1)

selected_date = st.date_input(
    "조회할 날짜를 골라 주세요",
    value=yesterday_kst,
    max_value=yesterday_kst,
)
target_dt = selected_date.strftime("%Y%m%d")
st.caption(f"조회 기준일: {selected_date.strftime('%Y-%m-%d')}")


# ------------------------------------------------------------
# 2. KOBIS API 호출 (같은 날짜는 캐시에 저장해서 재사용)
# ------------------------------------------------------------
@st.cache_data(ttl=3600, show_spinner="박스오피스 자료를 불러오는 중입니다...")
def fetch_boxoffice(key: str, dt: str):
    try:
        res = requests.get(URL, params={"key": key, "targetDt": dt}, timeout=10)
    except requests.exceptions.RequestException as e:
        return None, f"KOBIS 서버에 연결하지 못했습니다: {e}"

    if res.status_code != 200:
        return None, f"요청이 실패했습니다 (상태코드: {res.status_code})"

    try:
        data = res.json()
    except ValueError:
        return None, "KOBIS 응답을 해석하지 못했습니다."

    # KOBIS는 키가 틀려도 상태코드 200을 준다. 대신 faultInfo 상자가 온다.
    if "faultInfo" in data:
        return None, "인증키가 올바르지 않습니다. 금고(Secrets)의 KOBIS_KEY를 확인해 주세요."

    return data, None


data, error_msg = fetch_boxoffice(KOBIS_KEY, target_dt)
if error_msg:
    st.error(error_msg)
    st.stop()

box_list = data.get("boxOfficeResult", {}).get("dailyBoxOfficeList", [])
if not box_list:
    st.warning("그날은 아직 집계 전입니다.")
    st.stop()

df = pd.DataFrame(box_list)

# 글자로 온 숫자들을 진짜 숫자로 바꾸기 (rankInten은 부호가 있는 순위 변동값)
for col in ["rank", "audiCnt", "audiAcc", "scrnCnt", "showCnt", "rankInten"]:
    df[col] = pd.to_numeric(df[col])

# ------------------------------------------------------------
# 3. 1위 영화 지표 카드 세 장
# ------------------------------------------------------------
top = df.sort_values("rank").iloc[0]
c1, c2, c3 = st.columns(3)
c1.metric("1위", top["movieNm"])
c2.metric("당일 관객수", f"{top['audiCnt']:,}명")
c3.metric("누적 관객", f"{top['audiAcc']:,}명")


# ------------------------------------------------------------
# 4. 표 만들기
#    - rankInten 양수(순위 상승): 빨간 위 화살표
#    - rankInten 음수(순위 하락): 파란 아래 화살표
#    - 누적관객 100만 명 이상: 영화명 옆에 트로피 이모지
# ------------------------------------------------------------
def rank_change_text(inten: int) -> str:
    if inten > 0:
        return f"🔺{inten}"
    elif inten < 0:
        return f"🔻{abs(inten)}"
    else:
        return "-"


def movie_name_with_trophy(row) -> str:
    if row["audiAcc"] >= 1_000_000:
        return f"🏆 {row['movieNm']}"
    return row["movieNm"]


table = df.copy()
table["영화명"] = table.apply(movie_name_with_trophy, axis=1)
table["순위변동"] = table["rankInten"].apply(rank_change_text)

table = table[["rank", "영화명", "순위변동", "openDt", "audiCnt", "audiAcc", "scrnCnt"]]
table.columns = ["순위", "영화명", "전일대비", "개봉일", "관객수", "누적관객", "스크린수"]
table = table.sort_values("순위").reset_index(drop=True)

st.subheader("📋 박스오피스 TOP 10")
st.dataframe(table, use_container_width=True)

st.caption("🔺 순위 상승 · 🔻 순위 하락 · 🏆 누적관객 100만 명 이상")

# ------------------------------------------------------------
# 5. 관객수 상위 5편 그래프
# ------------------------------------------------------------
st.subheader("📈 관객수 상위 5편")
top5 = table.sort_values("관객수", ascending=False).head(5)
st.bar_chart(top5.set_index("영화명")["관객수"])
