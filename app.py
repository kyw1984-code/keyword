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
    
    # [핵심 수정] 사용자가 숫자를 크게 입력해도 API로는 무조건 10개만 요청하여 에러 방지
    safe_limit = 10 if int(limit) > 10 else int(limit)
    
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
# 텍스트 전처리 및 N-gram 추출 (자동완성어 로직 강화)
# ---------------------------------------------------------
def clean_text(text):
    """특수문자 제거 및 텍스트 정규화"""
    text = re.sub(r'\[.*?\]|\(.*?\)|<.*?>|【.*?】', ' ', text)
    text = re.sub(r'[^가-힣a-zA-Z0-9\s]', ' ', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text

def extract_auto_complete_like_keywords(base_keyword, product_names, limit=10):
    """
    상품명에서 '검색어 + @' 패턴을 우선적으로 찾아 자동완성어와 유사하게 만듭니다.
    """
    STOPWORDS = {
        "무료배송", "로켓배송", "국내생산", "정품", "당일발송", "특가", "할인", "쿠팡", 
        "브랜드", "세트", "상품", "추천", "인기", "신상", "최저가", "기획", "모음",
        "개입", "box", "박스", "1개", "x", "및", "의", "용", "대형", "소형", "사이즈"
    }

    base_clean = base_keyword.replace(" ", "")
    candidates = []

    for name in product_names:
        cleaned_name = clean_text(name)
        tokens = cleaned_name.split()
        
        if len(tokens) < 2: continue

        grams = []
        # 2단어 조합 (Bigram)
        for i in range(len(tokens) - 1):
            grams.append(f"{tokens[i]} {tokens[i+1]}")
        # 3단어 조합 (Trigram)
        for i in range(len(tokens) - 2):
            grams.append(f"{tokens[i]} {tokens[i+1]} {tokens[i+2]}")

        for gram in grams:
            if any(stop in gram for stop in STOPWORDS): continue
            
            # [로직 강화] 검색어가 문구의 '앞부분'에 위치할수록 가중치를 둠 (실제 자동완성 특징)
            gram_nospace = gram.replace(" ", "")
            if base_clean in gram_nospace:
                candidates.append(gram)

    # 빈도수 분석
    counter = Counter(candidates)
    
    # 정렬 기준: 1. 빈도수 높은 순, 2. 검색어로 시작하는 단어 우선, 3. 짧은 길이 우선
    def sort_key(item):
        kw, count = item
        starts_with_keyword = kw.replace(" ", "").startswith(base_clean)
        return (-count, -starts_with_keyword, len(kw))

    sorted_keywords = sorted(counter.most_common(), key=sort_key)

    final_keywords = []
    seen = set()
    # 원본 검색어 자체는 제외
    seen.add(base_keyword.replace(" ", ""))

    for kw, count in sorted_keywords:
        kw_clean = kw.replace(" ", "")
        
        # 중복 제거 (포함 관계가 너무 명확하면 긴 것만 남기거나 하는 식으로 조절 가능하나 여기선 단순 중복 체크)
        if kw_clean not in seen:
            final_keywords.append(kw)
            seen.add(kw_clean)
            
        if len(final_keywords) >= limit:
            break
            
    # 결과가 부족할 경우 단순 포함 단어로 채우기
    if len(final_keywords) < limit:
        simple_tokens = []
        for name in product_names:
            for t in clean_text(name).split():
                if base_clean in t and t not in seen and t not in STOPWORDS:
                    simple_tokens.append(t)
        
        for kw, _ in Counter(simple_tokens).most_common():
            if kw not in seen:
                final_keywords.append(kw)
                seen.add(kw)
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

    # Secrets 확인
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
            # [UI 수정] 최대값을 10으로 제한하여 사용자 실수 방지
            limit_kw = st.number_input("추출 수량", min_value=1, max_value=10, value=10)

        if st.button("🔍 연관검색어 추출", type="primary", use_container_width=True):
            if not keyword_input.strip():
                st.warning("키워드를 입력해 주세요.")
            else:
                with st.spinner(f"'{keyword_input}' 분석 중..."):
                    # [코드 수정] API 호출 시 limit=10으로 고정
                    res = search_products(ACCESS_KEY, SECRET_KEY, keyword_input.strip(), 10)

                if isinstance(res, dict) and "data" in res:
                    product_data = res["data"].get("productData", [])
                    if not product_data:
                        st.warning("검색 결과가 없습니다.")
                    else:
                        product_names = [item.get("productName", "") for item in product_data]
                        keywords = extract_auto_complete_like_keywords(keyword_input.strip(), product_names, limit_kw)

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
                            
                            # 엑셀 다운로드
                            excel_data = to_excel(df_kw)
                            st.download_button(
                                "📥 연관검색어 엑셀 다운로드",
                                data=excel_data,
                                file_name=f"연관검색어_{keyword_input}.xlsx"
                            )
                        else:
                            st.warning("추출된 키워드가 없습니다.")
                else:
                    st.error("❌ API 호출 실패")
                    st.write("▼ 상세 에러 내용")
                    st.json(res)

    # ── 탭2: 인기상품 ──
    with tab2:
        st.subheader("📦 쿠팡 파트너스 상품 검색")
        default_kw = st.session_state.get("search_keyword", "")

        col1, col2 = st.columns([3, 1])
        with col1:
            keyword_prod = st.text_input("상품 검색", value=default_kw, key="kw2")
        with col2:
            # [UI 수정] 슬라이더 최대값도 10으로 제한
            limit_prod = st.slider("개수", 1, 10, 10)

        if st.button("🛒 상품 검색", type="primary", use_container_width=True):
            if not keyword_prod.strip():
                st.warning("키워드를 입력하세요.")
            else:
                with st.spinner("검색 중..."):
                    # [코드 수정] 여기서도 limit을 UI 설정값(최대 10)으로 전달
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
