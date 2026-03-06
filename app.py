import streamlit as st
import hmac
import hashlib
from time import gmtime, strftime
import requests
from datetime import datetime
import pandas as pd
import io
import urllib.parse
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
# 상품명 전처리: 노이즈 제거
# ---------------------------------------------------------
def clean_product_name(name):
    # 특수문자, 숫자+단위, 영문 단독 제거
    name = re.sub(r'\[.*?\]|\(.*?\)|【.*?】|《.*?》', ' ', name)   # 괄호 안 내용 제거
    name = re.sub(r'\d+[\w%]*', ' ', name)                         # 숫자+단위 제거
    name = re.sub(r'[^가-힣a-zA-Z\s]', ' ', name)                  # 특수문자 제거
    name = re.sub(r'\b[a-zA-Z]{1,2}\b', ' ', name)                 # 1~2자리 영문 제거
    name = re.sub(r'\s+', ' ', name).strip()
    return name


# ---------------------------------------------------------
# 연관 키워드 추출 (정교화 버전)
# ---------------------------------------------------------
def extract_keywords(base_keyword, product_names, limit=10):

    # 불용어 (마케팅 용어, 조사, 단위 등)
    STOPWORDS = {
        # 조사/어미
        "이", "가", "을", "를", "의", "에", "에서", "은", "는", "과", "와", "도",
        "로", "으로", "만", "까지", "부터", "이나", "이라", "하고",
        # 마케팅/배송 단어
        "무료", "배송", "할인", "특가", "신상", "베스트", "추천", "인기", "최저가",
        "당일", "빠른", "정품", "국내", "해외", "직구", "공식", "브랜드", "신제품",
        "세일", "쿠폰", "증정", "사은품", "기획", "한정", "단독",
        # 수량/단위
        "개", "팩", "세트", "묶음", "박스", "장", "켤레", "쌍", "벌",
        # 범용 형용사
        "좋은", "예쁜", "귀여운", "심플", "고급", "프리미엄", "캐주얼",
        # 기타
        "cm", "mm", "ml", "kg", "the", "and", "for", "with", "new", "best"
    }

    # 기본 키워드를 단어 단위로 분리
    base_words = set(re.findall(r'[가-힣a-zA-Z]{2,}', base_keyword.strip()))

    # 상품명 전처리 및 토큰화
    all_tokens = []
    bigrams = []  # 2단어 연속 조합

    for name in product_names:
        cleaned = clean_product_name(name)
        tokens = [t for t in cleaned.split() if len(t) >= 2 and t.lower() not in STOPWORDS]

        # 기본 키워드 단어 자체는 단독 토큰에서 제거 (중복 방지)
        filtered = [t for t in tokens if t not in base_words]
        all_tokens.extend(filtered)

        # 2단어 연속 조합 (bigram) 생성
        for i in range(len(filtered) - 1):
            bigram = f"{filtered[i]} {filtered[i+1]}"
            bigrams.append(bigram)

    # 빈도 계산
    token_counter = Counter(all_tokens)
    bigram_counter = Counter(bigrams)

    # 후보 키워드 풀 구성
    # 우선순위: bigram(2단어 조합) > 단일 단어
    candidates = []

    # 1순위: 2회 이상 등장한 bigram
    for bigram, count in bigram_counter.most_common(50):
        if count >= 2:
            candidates.append(bigram)

    # 2순위: 2회 이상 등장한 단일 단어
    for word, count in token_counter.most_common(50):
        if count >= 2:
            candidates.append(word)

    # 3순위: 1회 등장 단일 단어 (후보 부족할 경우 보충)
    for word, count in token_counter.most_common(50):
        if count == 1:
            candidates.append(word)

    # 중복 제거 (순서 유지)
    seen_words = set()
    unique_candidates = []
    for c in candidates:
        key = c.lower()
        # 이미 추가된 단어가 포함된 후보는 제외 (중복 의미 방지)
        words_in_c = set(c.lower().split())
        if not words_in_c & seen_words:
            unique_candidates.append(c)
            seen_words.update(words_in_c)

    # 최종 연관검색어: "기본키워드 + 후보" 조합
    base = base_keyword.strip()
    related = []
    added_suffixes = set()

    for candidate in unique_candidates:
        suffix_key = candidate.lower()
        if suffix_key not in added_suffixes:
            related.append(f"{base} {candidate}")
            added_suffixes.add(suffix_key)
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
        st.caption("실제 쿠팡 상품명 데이터를 분석해 중복 없이 연관검색어를 추출합니다.")

        col1, col2 = st.columns([3, 1])
        with col1:
            keyword_input = st.text_input("검색 키워드 입력", placeholder="예: 여성 니트티", key="kw1")
        with col2:
            limit_kw = st.number_input("추출 수량", min_value=1, max_value=20, value=10)

        if st.button("🔍 연관검색어 추출", type="primary", use_container_width=True):
            if not keyword_input.strip():
                st.warning("키워드를 입력해 주세요.")
            else:
                with st.spinner(f"'{keyword_input}' 상품 데이터 수집 및 분석 중..."):
                    res = search_products(ACCESS_KEY, SECRET_KEY, keyword_input.strip(), 10)

                if isinstance(res, dict) and "data" in res:
                    product_data = res["data"].get("productData", [])
                    if not product_data:
                        st.warning("검색 결과가 없습니다. 다른 키워드를 시도해보세요.")
                    else:
                        product_names = [item.get("productName", "") for item in product_data]
                        keywords = extract_keywords(keyword_input.strip(), product_names, limit_kw)

                        if keywords:
                            st.success(f"✅ '{keyword_input}' 연관검색어 {len(keywords)}개 추출 완료!")

                            df_kw = pd.DataFrame({
                                "순번": range(1, len(keywords) + 1),
                                "연관검색어": keywords
                            })
                            st.dataframe(df_kw, use_container_width=True, hide_index=True)

                            st.divider()
                            st.caption("💡 키워드 클릭 시 인기상품 탭에서 바로 검색됩니다.")
                            cols = st.columns(5)
                            for i, kw in enumerate(keywords):
                                with cols[i % 5]:
                                    if st.button(kw, key=f"kw_btn_{i}"):
                                        st.session_state["search_keyword"] = kw
                                        st.info(f"📦 '인기상품 검색' 탭에서 '{kw}'를 검색해보세요!")

                            with st.expander("📋 분석에 사용된 원본 상품명 보기"):
                                for i, name in enumerate(product_names, 1):
                                    st.write(f"{i}. {name}")

                            excel_data = to_excel(df_kw)
                            st.download_button(
                                label="📥 연관검색어 엑셀 다운로드",
                                data=excel_data,
                                file_name=f"쿠팡_연관검색어_{keyword_input}_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
                                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                            )
                        else:
                            st.warning("연관검색어를 추출하지 못했습니다. 다른 키워드로 시도해보세요.")
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
