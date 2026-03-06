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
import re
from collections import Counter


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
# 상품명에서 연관 키워드 추출
# ---------------------------------------------------------
def extract_keywords_from_products(base_keyword, product_names, limit=10):
    # 불용어 (의미없는 단어들)
    stopwords = {
        "이", "가", "을", "를", "의", "에", "에서", "은", "는", "과", "와", "도",
        "로", "으로", "만", "이다", "있다", "없다", "하다", "되다",
        "cm", "mm", "ml", "kg", "g", "l", "m", "개", "팩", "세트", "묶음",
        "무료", "배송", "할인", "특가", "신상", "베스트", "추천", "인기",
        "1", "2", "3", "4", "5", "a", "b", "c", "s", "m", "l", "xl", "xxl",
        "x", "v", "n", "the", "and", "or", "for"
    }

    # 모든 상품명 합치기
    all_text = " ".join(product_names)

    # 한글+영문 단어 추출 (2글자 이상)
    tokens = re.findall(r'[가-힣a-zA-Z][가-힣a-zA-Z0-9]{1,}', all_text)

    # 소문자 변환 및 불용어 제거
    tokens = [t for t in tokens if t.lower() not in stopwords and len(t) >= 2]

    # 빈도 계산
    counter = Counter(tokens)

    # 기본 키워드 단어들 (중복 제거용)
    base_words = set(re.findall(r'[가-힣a-zA-Z]{2,}', base_keyword))

    # 빈도 높은 순으로 정렬, 기본 키워드 단어 단독은 제외
    candidates = []
    for word, count in counter.most_common(100):
        if word not in base_words:
            candidates.append(word)

    # 연관 키워드 조합 생성: "기본키워드 + 추출단어"
    base = base_keyword.strip()
    related = []
    seen = set()
    for word in candidates:
        kw = f"{base} {word}"
        if kw not in seen:
            seen.add(kw)
            related.append(kw)
        if len(related) >= limit:
            break

    # 부족하면 단어 자체도 추가
    if len(related) < limit:
        for word in candidates:
            if word not in seen:
                seen.add(word)
                related.append(word)
            if len(related) >= limit:
                break

    return related[:limit]


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

    # Secrets 검증
    missing = []
    if "COUPANG_ACCESS_KEY" not in st.secrets: missing.append("COUPANG_ACCESS_KEY")
    if "COUPANG_SECRET_KEY" not in st.secrets: missing.append("COUPANG_SECRET_KEY")
    if missing:
        st.error(f"🚨 Streamlit Secrets에 다음 키를 등록해 주세요: {', '.join(missing)}")
        st.stop()

    ACCESS_KEY = st.secrets["COUPANG_ACCESS_KEY"].strip().strip('"').strip("'")
    SECRET_KEY = st.secrets["COUPANG_SECRET_KEY"].strip().strip('"').strip("'")

    tab1, tab2 = st.tabs(["🔍 연관검색어 추출", "📦 인기상품 검색"])

    # ── 탭1: 연관검색어 ──
    with tab1:
        st.subheader("🔍 쿠팡 연관검색어 추출")
        st.caption("쿠팡 파트너스 API 검색 결과의 상품명을 분석하여 연관검색어를 자동 추출합니다.")

        col1, col2 = st.columns([3, 1])
        with col1:
            keyword_input = st.text_input("검색 키워드 입력", placeholder="예: 여성 니트티", key="kw1")
        with col2:
            limit_kw = st.number_input("추출 수량", min_value=1, max_value=20, value=10)

        if st.button("🔍 연관검색어 추출", type="primary", use_container_width=True):
            if not keyword_input.strip():
                st.warning("키워드를 입력해 주세요.")
            else:
                with st.spinner(f"'{keyword_input}' 상품 데이터 수집 및 키워드 분석 중..."):
                    # 상품 10개 검색
                    res = search_products(ACCESS_KEY, SECRET_KEY, keyword_input.strip(), 10)

                if isinstance(res, dict) and "data" in res:
                    product_data = res["data"].get("productData", [])
                    if not product_data:
                        st.warning("검색 결과가 없습니다. 다른 키워드를 시도해보세요.")
                    else:
                        # 상품명 추출
                        product_names = [item.get("productName", "") for item in product_data]

                        # 연관 키워드 추출
                        keywords = extract_keywords_from_products(
                            keyword_input.strip(), product_names, limit_kw
                        )

                        if keywords:
                            st.success(f"✅ '{keyword_input}' 연관검색어 {len(keywords)}개 추출 완료!")

                            df_kw = pd.DataFrame({
                                "순번": range(1, len(keywords) + 1),
                                "연관검색어": keywords
                            })
                            st.dataframe(df_kw, use_container_width=True, hide_index=True)

                            # 키워드 버튼
                            st.divider()
                            st.caption("💡 키워드를 클릭하면 해당 키워드로 상품을 검색합니다.")
                            cols = st.columns(5)
                            for i, kw in enumerate(keywords):
                                with cols[i % 5]:
                                    if st.button(kw, key=f"kw_btn_{i}"):
                                        st.session_state["search_keyword"] = kw
                                        st.info(f"📦 '인기상품 검색' 탭에서 '{kw}' 검색해보세요!")

                            # 분석에 사용된 상품명 보기
                            with st.expander("📋 분석에 사용된 상품명 보기"):
                                for i, name in enumerate(product_names, 1):
                                    st.write(f"{i}. {name}")

                            # 엑셀 다운로드
                            excel_data = to_excel(df_kw)
                            st.download_button(
                                label="📥 연관검색어 엑셀 다운로드",
                                data=excel_data,
                                file_name=f"쿠팡_연관검색어_{keyword_input}_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
                                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                            )
                        else:
                            st.warning("연관검색어를 추출하지 못했습니다. 다른 키워드를 시도해보세요.")
                else:
                    st.error("❌ API 호출 실패")
                    st.json(res)

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
