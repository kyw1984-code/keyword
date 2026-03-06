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
# 쿠팡 파트너스 상품 검색 (Limit 10 고정)
# ---------------------------------------------------------
def search_products(access_key, secret_key, keyword, limit=10):
    DOMAIN = "https://api-gateway.coupang.com"
    encoded_keyword = urllib.parse.quote(keyword)
    safe_limit = 10 if int(limit) > 10 else int(limit) # 안전장치
    
    URL = f"/v2/providers/affiliate_open_api/apis/openapi/products/search?keyword={encoded_keyword}&limit={safe_limit}"
    
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
# [핵심 수정] 하이브리드 키워드 추출 (무조건 추출 보장)
# ---------------------------------------------------------
def clean_text(text):
    text = re.sub(r'\[.*?\]|\(.*?\)|<.*?>|【.*?】', ' ', text)
    text = re.sub(r'[^가-힣a-zA-Z0-9\s]', ' ', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text

def extract_hybrid_keywords(base_keyword, product_names, limit=10):
    """
    1. 검색어를 포함하는 연관 문구 (1순위)
    2. 자주 등장하는 2단어 조합 (2순위)
    3. 자주 등장하는 단일 핵심 키워드 (3순위 - 비상용)
    위 3단계를 거쳐 limit 개수를 무조건 채웁니다.
    """
    STOPWORDS = {
        "무료배송", "로켓배송", "국내생산", "정품", "당일발송", "특가", "할인", "쿠팡", 
        "브랜드", "세트", "상품", "추천", "인기", "신상", "최저가", "기획", "모음",
        "개입", "box", "박스", "1개", "x", "및", "의", "용", "대형", "소형", "사이즈",
        "남녀공용", "겸용", "스타일", "컬러"
    }
    
    # 검색어 자체도 중복 방지를 위해 제외 목록에 추가
    base_parts = base_keyword.split()
    for bp in base_parts:
        STOPWORDS.add(bp)

    base_clean = base_keyword.replace(" ", "")
    
    phrases = [] # 2~3단어 묶음
    words = []   # 1단어

    for name in product_names:
        cleaned_name = clean_text(name)
        tokens = cleaned_name.split()
        
        # 단일 단어 수집
        for t in tokens:
            if len(t) > 1 and t not in STOPWORDS:
                words.append(t)

        if len(tokens) < 2: continue

        # N-gram 수집 (2단어 조합)
        for i in range(len(tokens) - 1):
            gram = f"{tokens[i]} {tokens[i+1]}"
            if not any(stop in gram for stop in STOPWORDS):
                phrases.append(gram)

    # 빈도수 계산
    phrase_counts = Counter(phrases).most_common()
    word_counts = Counter(words).most_common()

    final_keywords = []
    seen = set()
    seen.add(base_clean)
    
    # 전략 1: 검색어가 포함된 문구 우선 추출
    for phrase, count in phrase_counts:
        p_nospace = phrase.replace(" ", "")
        if base_clean in p_nospace and p_nospace not in seen:
            final_keywords.append(phrase)
            seen.add(p_nospace)

    # 전략 2: 검색어가 없더라도 자주 나오는 문구 추출 (빈도 2 이상)
    if len(final_keywords) < limit:
        for phrase, count in phrase_counts:
            p_nospace = phrase.replace(" ", "")
            if p_nospace not in seen and count >= 2: # 최소 2번 이상 등장한 문구
                final_keywords.append(phrase)
                seen.add(p_nospace)
                
    # 전략 3: 그래도 부족하면 자주 나오는 단어(명사)로 채우기 (무조건 채워짐)
    if len(final_keywords) < limit:
        for word, count in word_counts:
            if word not in seen and word not in STOPWORDS:
                final_keywords.append(word)
                seen.add(word)
            if len(final_keywords) >= limit:
                break
    
    return final_keywords[:limit]


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
        st.error("🚨 Streamlit Secrets에 키 설정을 확인해주세요.")
        st.stop()

    ACCESS_KEY = st.secrets["COUPANG_ACCESS_KEY"].strip().strip('"').strip("'")
    SECRET_KEY = st.secrets["COUPANG_SECRET_KEY"].strip().strip('"').strip("'")

    tab1, tab2 = st.tabs(["🔍 연관검색어 추출", "📦 인기상품 검색"])

    # ── 탭1: 연관검색어 ──
    with tab1:
        st.subheader("🔍 쿠팡 연관검색어 추출")
        col1, col2 = st.columns([3, 1])
        with col1:
            keyword_input = st.text_input("검색 키워드 입력", placeholder="예: 여성 니트", key="kw1")
        with col2:
            limit_kw = st.number_input("추출 수량", min_value=1, max_value=10, value=10)

        if st.button("🔍 연관검색어 추출", type="primary", use_container_width=True):
            if not keyword_input.strip():
                st.warning("키워드를 입력해 주세요.")
            else:
                with st.spinner(f"'{keyword_input}' 분석 중..."):
                    # Limit 10 고정
                    res = search_products(ACCESS_KEY, SECRET_KEY, keyword_input.strip(), 10)

                if isinstance(res, dict) and "data" in res:
                    product_data = res["data"].get("productData", [])
                    if not product_data:
                        st.warning("검색 결과가 없습니다.")
                    else:
                        product_names = [item.get("productName", "") for item in product_data]
                        
                        # [변경] 하이브리드 추출 함수 사용
                        keywords = extract_hybrid_keywords(keyword_input.strip(), product_names, limit_kw)

                        if keywords:
                            st.success(f"✅ 연관검색어 추출 완료!")
                            df_kw = pd.DataFrame({"순번": range(1, len(keywords)+1), "연관검색어": keywords})
                            st.dataframe(df_kw, use_container_width=True, hide_index=True)
                            
                            st.caption("👇 키워드 클릭 시 바로 검색")
                            cols = st.columns(4)
                            for i, kw in enumerate(keywords):
                                with cols[i % 4]:
                                    if st.button(kw, key=f"btn_{i}"):
                                        st.session_state["search_keyword"] = kw
                                        st.info(f"👉 '인기상품 검색' 탭에서 확인하세요!")
                            
                            excel_data = to_excel(df_kw)
                            st.download_button(
                                "📥 연관검색어 엑셀 다운로드",
                                data=excel_data,
                                file_name=f"연관검색어_{keyword_input}.xlsx"
                            )
                        else:
                            # 10개 상품이 있는데도 키워드가 안 뽑히는 경우는 거의 없음 (단어로라도 채움)
                            st.warning("특이사항: 추출된 단어가 없습니다. 상품명을 확인해보세요.")
                            st.write(product_names)
                else:
                    st.error("❌ API 호출 실패")
                    st.json(res)

    # ── 탭2: 인기상품 ──
    with tab2:
        st.subheader("📦 쿠팡 파트너스 상품 검색")
        default_kw = st.session_state.get("search_keyword", "")

        col1, col2 = st.columns([3, 1])
        with col1:
            keyword_prod = st.text_input("상품 검색", value=default_kw, key="kw2")
        with col2:
            limit_prod = st.slider("개수", 1, 10, 10)

        if st.button("🛒 상품 검색", type="primary", use_container_width=True):
            if not keyword_prod.strip():
                st.warning("키워드를 입력하세요.")
            else:
                with st.spinner("검색 중..."):
                    res = search_products(ACCESS_KEY, SECRET_KEY, keyword_prod.strip(), limit_prod)

                if isinstance(res, dict) and "data" in res:
                    product_data = res["data"].get("productData", [])
                    if not product_data:
                        st.warning("결과 없음")
                    else:
                        df_prod = pd.DataFrame([{
                            "순위": i+1,
                            "상품명": item.get("productName"),
                            "가격": f"{int(item.get('productPrice',0)):,}" if item.get("productPrice") else "-",
                            "로켓": "🚀" if item.get("isRocket") else "",
                            "링크": item.get("productUrl")
                        } for i, item in enumerate(product_data)])
                        st.dataframe(df_prod, use_container_width=True, hide_index=True)
                        
                        excel_data = to_excel(df_prod)
                        st.download_button(
                            "📥 상품목록 엑셀 다운로드",
                            data=excel_data,
                            file_name=f"상품목록_{keyword_prod}.xlsx"
                        )
                else:
                    st.error("❌ API 호출 실패")
                    st.json(res)

if __name__ == "__main__":
    main()
