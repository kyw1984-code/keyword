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
# 유사 단어 판별: A가 B에 포함되거나 B가 A에 포함되면 동일 취급
# 예) "니트" ↔ "니트티", "여자" ↔ "여성" 같은 포함 관계
# ---------------------------------------------------------
def is_similar_word(word_a, word_b):
    a, b = word_a.lower(), word_b.lower()
    if a == b:
        return True
    # 한쪽이 다른쪽을 포함하는 경우 (예: 니트 ⊂ 니트티)
    if a in b or b in a:
        return True
    return False


def has_overlap_with_existing(candidate_words, seen_word_list):
    """후보 단어들이 기존 추가된 단어들과 유사한지 확인"""
    for cw in candidate_words:
        for sw in seen_word_list:
            if is_similar_word(cw, sw):
                return True
    return False


# ---------------------------------------------------------
# 상품명 전처리
# ---------------------------------------------------------
def clean_product_name(name):
    name = re.sub(r'\[.*?\]|\(.*?\)|【.*?】|《.*?》', ' ', name)
    name = re.sub(r'\d+[\w%]*', ' ', name)
    name = re.sub(r'[^가-힣a-zA-Z\s]', ' ', name)
    name = re.sub(r'\b[a-zA-Z]{1,2}\b', ' ', name)
    name = re.sub(r'\s+', ' ', name).strip()
    return name


# ---------------------------------------------------------
# 연관 키워드 추출 (유사어 중복 제거 강화)
# ---------------------------------------------------------
def extract_keywords(base_keyword, product_names, limit=10):

    STOPWORDS = {
        "이", "가", "을", "를", "의", "에", "에서", "은", "는", "과", "와", "도",
        "로", "으로", "만", "까지", "부터", "이나", "이라", "하고",
        "무료", "배송", "할인", "특가", "신상", "베스트", "추천", "인기", "최저가",
        "당일", "빠른", "정품", "국내", "해외", "직구", "공식", "브랜드", "신제품",
        "세일", "쿠폰", "증정", "사은품", "기획", "한정", "단독",
        "개", "팩", "세트", "묶음", "박스", "장", "켤레", "쌍", "벌",
        "좋은", "예쁜", "귀여운", "심플", "고급", "프리미엄", "캐주얼",
        "cm", "mm", "ml", "kg", "the", "and", "for", "with", "new", "best"
    }

    # 기본 키워드 단어 분리 (유사어 비교에 사용)
    base_words = re.findall(r'[가-힣a-zA-Z]{2,}', base_keyword.strip())

    all_tokens = []
    bigrams = []

    for name in product_names:
        cleaned = clean_product_name(name)
        tokens = [t for t in cleaned.split()
                  if len(t) >= 2 and t.lower() not in STOPWORDS]

        # 기본 키워드와 유사한 단어 제거 (예: 기본이 "니트티"면 "니트"도 제거)
        filtered = []
        for t in tokens:
            if not any(is_similar_word(t, bw) for bw in base_words):
                filtered.append(t)

        all_tokens.extend(filtered)

        for i in range(len(filtered) - 1):
            bigram = f"{filtered[i]} {filtered[i+1]}"
            bigrams.append(bigram)

    token_counter = Counter(all_tokens)
    bigram_counter = Counter(bigrams)

    # 후보 풀 구성 (bigram 우선)
    candidates = []
    for bigram, count in bigram_counter.most_common(80):
        if count >= 2:
            candidates.append(bigram)
    for word, count in token_counter.most_common(80):
        if count >= 2:
            candidates.append(word)
    for word, count in token_counter.most_common(80):
        if count == 1:
            candidates.append(word)

    # 중복/유사어 제거하며 최종 키워드 선정
    seen_word_list = list(base_words)  # 기본 키워드 단어도 seen에 포함
    final_keywords = []

    for candidate in candidates:
        cand_words = re.findall(r'[가-힣a-zA-Z]{2,}', candidate)

        # 후보 단어가 기존 seen 단어와 유사하면 스킵
        if has_overlap_with_existing(cand_words, seen_word_list):
            continue

        base = base_keyword.strip()
        final_keywords.append(f"{base} {candidate}")
        seen_word_list.extend(cand_words)  # 추가된 단어를 seen에 등록

        if len(final_keywords) >= limit:
            break

    return final_keywords


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
        st.caption("실제 쿠팡 상품명을 분석하여 유사 단어 중복 없이 연관검색어를 추출합니다.")

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
                            st.caption("💡 키워드 클릭 시 인기상품 탭에서 바로 검색할 수 있습니다.")
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
                            st.warning("추출된 연관검색어가 없습니다. 다른 키워드로 시도해보세요.")
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
