import streamlit as st
import hmac
import hashlib
from time import gmtime, strftime
import requests
from datetime import datetime
import pandas as pd
import io
import urllib.parse
import json


# ---------------------------------------------------------
# HMAC 서명 생성
# ---------------------------------------------------------
def generate_hmac(method, url, secret_key, access_key):
    path, *query = url.split("?")
    datetime_gmt = strftime('%y%m%d', gmtime()) + 'T' + strftime('%H%M%S', gmtime()) + 'Z'
    message = datetime_gmt + method + path + (query[0] if query else "")
    signature = hmac.new(
        bytes(secret_key, "utf-8"),
        message.encode("utf-8"),
        hashlib.sha256
    ).hexdigest()
    return f"CEA algorithm=HmacSHA256, access-key={access_key}, signed-date={datetime_gmt}, signature={signature}"


# ---------------------------------------------------------
# 쿠팡 연관검색어 추출 (자동완성 API)
# ---------------------------------------------------------
def get_related_keywords(keyword, limit=10):
    encoded = urllib.parse.quote(keyword)
    url = f"https://www.coupang.com/np/search/suggest?callback=&searchTerm={encoded}&_={int(datetime.now().timestamp()*1000)}"

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": "https://www.coupang.com/",
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "Accept-Language": "ko-KR,ko;q=0.9",
    }

    try:
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code == 200:
            text = response.text.strip()
            # JSONP 형식 처리 (콜백 함수로 감싸진 경우)
            if text.startswith("(") and text.endswith(")"):
                text = text[1:-1]
            elif "(" in text and text.endswith(")"):
                text = text[text.index("(")+1:-1]

            data = json.loads(text)

            # 응답 구조에서 키워드 추출
            suggestions = []
            if isinstance(data, dict):
                # 가능한 여러 키 시도
                for key in ["suggests", "suggestions", "data", "result", "keywords"]:
                    if key in data:
                        raw = data[key]
                        if isinstance(raw, list):
                            for item in raw:
                                if isinstance(item, str):
                                    suggestions.append(item)
                                elif isinstance(item, dict):
                                    for k in ["keyword", "text", "value", "name", "query"]:
                                        if k in item:
                                            suggestions.append(item[k])
                                            break
                        break
            elif isinstance(data, list):
                for item in data:
                    if isinstance(item, str):
                        suggestions.append(item)
                    elif isinstance(item, dict):
                        for k in ["keyword", "text", "value", "name", "query"]:
                            if k in item:
                                suggestions.append(item[k])
                                break

            return {"success": True, "keywords": suggestions[:limit], "raw": data}
        else:
            return {"success": False, "error": f"HTTP {response.status_code}", "raw": response.text}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ---------------------------------------------------------
# 쿠팡 파트너스 상품 검색 API
# ---------------------------------------------------------
def search_products(access_key, secret_key, keyword, limit=10):
    DOMAIN = "https://api-gateway.coupang.com"
    encoded_keyword = urllib.parse.quote(keyword)
    URL = f"/v2/providers/affiliate_open_api/apis/openapi/products/search?keyword={encoded_keyword}&limit={limit}"
    authorization = generate_hmac("GET", URL, secret_key, access_key)
    headers = {
        "Authorization": authorization,
        "Content-Type": "application/json;charset=UTF-8"
    }
    try:
        response = requests.get(f"{DOMAIN}{URL}", headers=headers, timeout=10)
        if response.status_code == 200:
            return response.json()
        else:
            return {"error": True, "status": response.status_code, "msg": response.text}
    except Exception as e:
        return {"error": True, "msg": str(e)}


# ---------------------------------------------------------
# 엑셀 변환
# ---------------------------------------------------------
def to_excel(df):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False)
    return output.getvalue()


# ---------------------------------------------------------
# 메인 앱
# ---------------------------------------------------------
def main():
    st.set_page_config(page_title="쿠팡 키워드 분석", layout="wide")
    st.title("🛍️ 쿠팡 연관검색어 & 인기상품 추출기")

    if "COUPANG_ACCESS_KEY" not in st.secrets or "COUPANG_SECRET_KEY" not in st.secrets:
        st.error("🚨 Streamlit Cloud 설정(Secrets)에 키를 등록해 주세요.")
        st.stop()

    ACCESS_KEY = st.secrets["COUPANG_ACCESS_KEY"].strip().strip('"').strip("'")
    SECRET_KEY = st.secrets["COUPANG_SECRET_KEY"].strip().strip('"').strip("'")

    # 탭 구성
    tab1, tab2 = st.tabs(["🔍 연관검색어 추출", "📦 인기상품 추출"])

    # ── 탭1: 연관검색어 ──
    with tab1:
        st.subheader("🔍 쿠팡 연관검색어 추출")
        st.caption("쿠팡 검색창 자동완성 기반으로 연관검색어를 추출합니다.")

        col1, col2 = st.columns([3, 1])
        with col1:
            keyword_input = st.text_input("검색 키워드 입력", placeholder="예: 여성 니트티", key="kw1")
        with col2:
            limit_kw = st.number_input("추출 수량", min_value=1, max_value=20, value=10)

        if st.button("연관검색어 추출", type="primary"):
            if not keyword_input.strip():
                st.warning("키워드를 입력해 주세요.")
            else:
                with st.spinner(f"'{keyword_input}' 연관검색어 추출 중..."):
                    result = get_related_keywords(keyword_input.strip(), limit_kw)

                if result["success"]:
                    keywords = result["keywords"]
                    if keywords:
                        st.success(f"✅ '{keyword_input}' 연관검색어 {len(keywords)}개 추출 완료!")

                        df_kw = pd.DataFrame({
                            "순번": range(1, len(keywords) + 1),
                            "연관검색어": keywords
                        })
                        st.dataframe(df_kw, use_container_width=True, hide_index=True)

                        excel_data = to_excel(df_kw)
                        st.download_button(
                            label="📥 연관검색어 엑셀 다운로드",
                            data=excel_data,
                            file_name=f"쿠팡_연관검색어_{keyword_input}_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                        )
                    else:
                        st.warning("연관검색어를 찾을 수 없습니다.")
                        with st.expander("🔧 디버그 정보 (원본 응답)"):
                            st.json(result.get("raw", {}))
                else:
                    st.error(f"❌ 추출 실패: {result.get('error')}")
                    with st.expander("🔧 디버그 정보"):
                        st.write(result.get("raw", ""))

    # ── 탭2: 인기상품 ──
    with tab2:
        st.subheader("📦 쿠팡 파트너스 상품 검색")
        st.caption("쿠팡 파트너스 API를 통해 키워드별 인기상품을 가져옵니다.")

        col1, col2 = st.columns([3, 1])
        with col1:
            keyword_prod = st.text_input("검색 키워드 입력", placeholder="예: 에어프라이어", key="kw2")
        with col2:
            limit_prod = st.slider("추출 개수", 1, 10, 10)

        st.info("⚠️ 쿠팡 파트너스 Search API는 시간당 최대 10회 호출 가능합니다.")

        if st.button("상품 검색", type="primary"):
            if not keyword_prod.strip():
                st.warning("키워드를 입력해 주세요.")
            else:
                with st.spinner(f"'{keyword_prod}' 상품 검색 중..."):
                    res = search_products(ACCESS_KEY, SECRET_KEY, keyword_prod.strip(), limit_prod)

                if isinstance(res, dict) and "data" in res:
                    product_data = res["data"].get("productData", [])
                    if not product_data:
                        st.warning("검색 결과가 없습니다.")
                    else:
                        df_prod = pd.DataFrame([{
                            "순위": item.get("rank", i + 1),
                            "상품명": item.get("productName"),
                            "가격(원)": item.get("productPrice"),
                            "로켓배송": "🚀" if item.get("isRocket") else "일반",
                            "무료배송": "✅" if item.get("isFreeShipping") else "❌",
                            "상품링크": item.get("productUrl")
                        } for i, item in enumerate(product_data)])

                        st.success(f"✅ '{keyword_prod}' 상품 {len(df_prod)}개 추출 완료!")
                        st.dataframe(df_prod, use_container_width=True, hide_index=True)

                        excel_data = to_excel(df_prod)
                        st.download_button(
                            label="📥 상품 엑셀 다운로드",
                            data=excel_data,
                            file_name=f"쿠팡_상품_{keyword_prod}_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                        )
                else:
                    st.error("❌ API 호출 실패")
                    st.json(res)


main()
