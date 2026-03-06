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
# Claude AI 연관검색어 생성
# ---------------------------------------------------------
def get_related_keywords_ai(keyword, limit=10):
    url = "https://api.anthropic.com/v1/messages"
    headers = {
        "Content-Type": "application/json",
        "anthropic-version": "2023-06-01"
    }

    prompt = f"""당신은 쿠팡 쇼핑몰 검색 전문가입니다.
사용자가 쿠팡에서 "{keyword}"를 검색할 때 함께 검색할 만한 연관검색어 {limit}개를 생성해주세요.

조건:
- 실제 쿠팡 검색창에서 자동완성으로 나올 법한 키워드
- 구체적인 상품명, 브랜드, 스펙, 용도 등을 포함
- 한국어로 작성
- 중복 없이 {limit}개 정확히

반드시 아래 JSON 형식으로만 답하세요. 다른 설명 없이 JSON만 출력하세요:
{{"keywords": ["키워드1", "키워드2", "키워드3"]}}"""

    body = {
        "model": "claude-sonnet-4-20250514",
        "max_tokens": 1000,
        "messages": [{"role": "user", "content": prompt}]
    }

    try:
        response = requests.post(url, headers=headers, json=body, timeout=30)
        if response.status_code == 200:
            data = response.json()
            text = data["content"][0]["text"].strip()
            # JSON 파싱
            text = text.replace("```json", "").replace("```", "").strip()
            parsed = json.loads(text)
            return {"success": True, "keywords": parsed.get("keywords", [])[:limit]}
        else:
            return {"success": False, "error": f"API 오류: {response.status_code} - {response.text}"}
    except json.JSONDecodeError as e:
        return {"success": False, "error": f"JSON 파싱 오류: {str(e)}"}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ---------------------------------------------------------
# 쿠팡 파트너스 상품 검색
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
    st.set_page_config(page_title="쿠팡 키워드 분석기", layout="wide")
    st.title("🛍️ 쿠팡 연관검색어 & 인기상품 추출기")

    if "COUPANG_ACCESS_KEY" not in st.secrets or "COUPANG_SECRET_KEY" not in st.secrets:
        st.error("🚨 Streamlit Cloud 설정(Secrets)에 쿠팡 API 키를 등록해 주세요.")
        st.stop()

    ACCESS_KEY = st.secrets["COUPANG_ACCESS_KEY"].strip().strip('"').strip("'")
    SECRET_KEY = st.secrets["COUPANG_SECRET_KEY"].strip().strip('"').strip("'")

    tab1, tab2 = st.tabs(["🔍 연관검색어 추출", "📦 인기상품 검색"])

    # ── 탭1: 연관검색어 ──
    with tab1:
        st.subheader("🔍 쿠팡 스타일 연관검색어 추출")
        st.caption("Claude AI가 쿠팡 검색 패턴을 분석하여 연관검색어를 생성합니다.")

        col1, col2 = st.columns([3, 1])
        with col1:
            keyword_input = st.text_input(
                "검색 키워드 입력",
                placeholder="예: 여성 니트티",
                key="kw1"
            )
        with col2:
            limit_kw = st.number_input("추출 수량", min_value=1, max_value=20, value=10)

        if st.button("🔍 연관검색어 추출", type="primary", use_container_width=True):
            if not keyword_input.strip():
                st.warning("키워드를 입력해 주세요.")
            else:
                with st.spinner(f"'{keyword_input}' 연관검색어 AI 분석 중..."):
                    result = get_related_keywords_ai(keyword_input.strip(), limit_kw)

                if result["success"]:
                    keywords = result["keywords"]
                    if keywords:
                        st.success(f"✅ '{keyword_input}' 연관검색어 {len(keywords)}개 생성 완료!")

                        df_kw = pd.DataFrame({
                            "순번": range(1, len(keywords) + 1),
                            "연관검색어": keywords
                        })

                        st.dataframe(df_kw, use_container_width=True, hide_index=True)

                        # 연관검색어로 바로 상품 검색 버튼
                        st.divider()
                        st.caption("💡 연관검색어를 클릭하면 해당 키워드로 상품을 검색할 수 있습니다.")
                        cols = st.columns(5)
                        for i, kw in enumerate(keywords):
                            with cols[i % 5]:
                                if st.button(kw, key=f"kw_btn_{i}"):
                                    st.session_state["search_keyword"] = kw
                                    st.info(f"📦 상품검색 탭에서 '{kw}' 키워드로 검색해보세요!")

                        # 엑셀 다운로드
                        excel_data = to_excel(df_kw)
                        st.download_button(
                            label="📥 연관검색어 엑셀 다운로드",
                            data=excel_data,
                            file_name=f"쿠팡_연관검색어_{keyword_input}_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                        )
                    else:
                        st.warning("연관검색어를 생성하지 못했습니다. 다시 시도해주세요.")
                else:
                    st.error(f"❌ 생성 실패: {result.get('error')}")

    # ── 탭2: 인기상품 ──
    with tab2:
        st.subheader("📦 쿠팡 파트너스 상품 검색")
        st.caption("쿠팡 파트너스 API를 통해 키워드별 상품을 검색합니다.")

        default_kw = st.session_state.get("search_keyword", "")

        col1, col2 = st.columns([3, 1])
        with col1:
            keyword_prod = st.text_input(
                "검색 키워드 입력",
                value=default_kw,
                placeholder="예: 여성 니트티 오버핏",
                key="kw2"
            )
        with col2:
            limit_prod = st.slider("추출 개수", 1, 10, 10)

        st.info("⚠️ 쿠팡 파트너스 API는 시간당 최대 10회 호출 가능합니다.")

        if st.button("🛒 상품 검색", type="primary", use_container_width=True):
            if not keyword_prod.strip():
                st.warning("키워드를 입력해 주세요.")
            else:
                with st.spinner(f"'{keyword_prod}' 상품 검색 중..."):
                    res = search_products(ACCESS_KEY, SECRET_KEY, keyword_prod.strip(), limit_prod)

                if isinstance(res, dict) and "data" in res:
                    product_data = res["data"].get("productData", [])
                    if not product_data:
                        st.warning("검색 결과가 없습니다. 다른 키워드를 시도해보세요.")
                    else:
                        df_prod = pd.DataFrame([{
                            "순위": item.get("rank", i + 1),
                            "상품명": item.get("productName"),
                            "가격(원)": f"{int(item.get('productPrice', 0)):,}" if item.get("productPrice") else "-",
                            "로켓배송": "🚀 로켓" if item.get("isRocket") else "일반",
                            "무료배송": "✅" if item.get("isFreeShipping") else "❌",
                            "상품링크": item.get("productUrl")
                        } for i, item in enumerate(product_data)])

                        st.success(f"✅ '{keyword_prod}' 상품 {len(df_prod)}개 검색 완료!")
                        st.dataframe(df_prod, use_container_width=True, hide_index=True)

                        excel_data = to_excel(df_prod)
                        st.download_button(
                            label="📥 상품목록 엑셀 다운로드",
                            data=excel_data,
                            file_name=f"쿠팡_상품_{keyword_prod}_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                        )
                else:
                    st.error("❌ API 호출 실패")
                    st.json(res)


main()
