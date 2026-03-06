import datetime as dt
import hashlib
import hmac
from urllib.parse import urlencode

import requests
import streamlit as st

st.set_page_config(page_title="쿠팡 API 호출기", layout="wide")
st.title("쿠팡 API 호출기")
st.caption("공식적으로 승인된 쿠팡 API 엔드포인트만 사용하세요.")

BASE_URL = "https://api-gateway.coupang.com"

ACCESS_KEY = st.secrets.get("COUPANG_ACCESS_KEY", "")
SECRET_KEY = st.secrets.get("COUPANG_SECRET_KEY", "")
DEFAULT_PATH = st.secrets.get("COUPANG_ENDPOINT_PATH", "")

if not ACCESS_KEY or not SECRET_KEY:
    st.error("Streamlit secrets에 COUPANG_ACCESS_KEY, COUPANG_SECRET_KEY가 필요합니다.")
    st.stop()


def make_authorization(method: str, path: str, query_string: str = "") -> str:
    """
    Coupang OpenAPI HMAC Authorization 생성
    공식 문서 형식:
    CEA algorithm=HmacSHA256, access-key=..., signed-date=..., signature=...
    """
    method = method.upper()
    signed_date = dt.datetime.utcnow().strftime("%y%m%dT%H%M%SZ")
    message = f"{signed_date}{method}{path}{query_string}"

    signature = hmac.new(
        SECRET_KEY.encode("utf-8"),
        message.encode("utf-8"),
        hashlib.sha256
    ).hexdigest()

    authorization = (
        f"CEA algorithm=HmacSHA256, "
        f"access-key={ACCESS_KEY}, "
        f"signed-date={signed_date}, "
        f"signature={signature}"
    )
    return authorization


def coupang_get(path: str, params: dict | None = None, timeout: int = 20):
    params = params or {}
    query_string = urlencode(params, doseq=True)

    headers = {
        "Content-Type": "application/json;charset=UTF-8",
        "Authorization": make_authorization("GET", path, query_string),
    }

    url = f"{BASE_URL}{path}"
    return requests.get(url, headers=headers, params=params, timeout=timeout)


def flatten_response(keyword: str, data):
    """
    응답 구조를 모를 때 화면 표시용으로 최대한 평탄화
    """
    rows = []

    if isinstance(data, list):
        for i, item in enumerate(data, start=1):
            if isinstance(item, dict):
                row = {"keyword": keyword, "rank": i}
                for k, v in item.items():
                    row[k] = str(v)
                rows.append(row)
            else:
                rows.append({"keyword": keyword, "rank": i, "value": str(item)})

    elif isinstance(data, dict):
        # 흔한 배열 후보 탐색
        list_found = None
        for key in ["data", "results", "items", "products", "suggestions", "keywords"]:
            if isinstance(data.get(key), list):
                list_found = data[key]
                break

        if list_found is not None:
            return flatten_response(keyword, list_found)

        rows.append({"keyword": keyword, "value": str(data)})

    else:
        rows.append({"keyword": keyword, "value": str(data)})

    return rows


with st.sidebar:
    st.header("설정")
    endpoint_path = st.text_input(
        "엔드포인트 Path",
        value=DEFAULT_PATH,
        placeholder="/v2/providers/affiliate_open_api/apis/openapi/v1/..."
    )
    show_raw = st.checkbox("원본 응답 보기", value=True)

st.write("키워드를 줄바꿈으로 입력하세요.")
keywords_text = st.text_area(
    "키워드 입력",
    placeholder="예:\n노트북\n텀블러\n무선이어폰",
    height=180
)

# 필요시 직접 추가 파라미터 입력
st.subheader("추가 쿼리 파라미터")
param_text = st.text_area(
    "key=value 형식, 한 줄에 하나씩",
    placeholder="limit=10\nsubId=mytest",
    height=120
)

extra_params = {}
for line in param_text.splitlines():
    line = line.strip()
    if not line or "=" not in line:
        continue
    k, v = line.split("=", 1)
    extra_params[k.strip()] = v.strip()

keywords = [x.strip() for x in keywords_text.splitlines() if x.strip()]

if st.button("실행", type="primary"):
    if not endpoint_path:
        st.error("엔드포인트 Path를 입력하세요.")
        st.stop()

    if not keywords:
        st.error("키워드를 1개 이상 입력하세요.")
        st.stop()

    all_rows = []
    raw_results = []

    progress = st.progress(0)
    status = st.empty()

    for i, keyword in enumerate(keywords, start=1):
        status.write(f"호출 중: {keyword} ({i}/{len(keywords)})")

        params = {"keyword": keyword}
        params.update(extra_params)

        try:
            resp = coupang_get(endpoint_path, params=params)
            content_type = resp.headers.get("Content-Type", "")

            try:
                data = resp.json()
            except Exception:
                data = resp.text

            raw_results.append({
                "keyword": keyword,
                "status_code": resp.status_code,
                "response": data
            })

            if resp.ok:
                all_rows.extend(flatten_response(keyword, data))
            else:
                all_rows.append({
                    "keyword": keyword,
                    "error": f"HTTP {resp.status_code}",
                    "response": str(data)
                })

        except requests.RequestException as e:
            all_rows.append({
                "keyword": keyword,
                "error": str(e)
            })

        progress.progress(i / len(keywords))

    st.subheader("정리 결과")
    if all_rows:
        st.dataframe(all_rows, use_container_width=True)

        import pandas as pd
        df = pd.DataFrame(all_rows)
        csv = df.to_csv(index=False).encode("utf-8-sig")
        st.download_button(
            "CSV 다운로드",
            data=csv,
            file_name="coupang_api_result.csv",
            mime="text/csv",
        )

    if show_raw:
        st.subheader("원본 응답")
        st.json(raw_results)
