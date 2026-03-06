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
# HMAC 서명 생성 (기존 유지)
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
# 쿠팡 파트너스 상품 검색 (기존 유지)
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
# [핵심 변경] 텍스트 전처리 함수
# ---------------------------------------------------------
def clean_text(text):
    """특수문자 제거 및 텍스트 정규화"""
    # 괄호 안의 내용 제거 (예: [무료배송], (1+1) 등)
    text = re.sub(r'\[.*?\]|\(.*?\)|<.*?>|【.*?】', ' ', text)
    # 특수문자 제거 (한글, 영문, 숫자, 공백만 허용)
    text = re.sub(r'[^가-힣a-zA-Z0-9\s]', ' ', text)
    # 다중 공백을 하나로
    text = re.sub(r'\s+', ' ', text).strip()
    return text

# ---------------------------------------------------------
# [핵심 변경] N-gram 기반 연관검색어 추출 로직
# ---------------------------------------------------------
def extract_auto_complete_like_keywords(base_keyword, product_names, limit=10):
    """
    상품명에서 2~3어절(N-gram)을 추출하고 빈도수를 분석하여
    실제 자동완성어와 유사한 형태의 키워드를 반환합니다.
    """
    
    # 의미 없는 불용어 리스트
    STOPWORDS = {
        "무료배송", "로켓배송", "국내생산", "정품", "당일발송", "특가", "할인", "쿠팡", 
        "브랜드", "세트", "상품", "추천", "인기", "신상", "최저가", "기획", "모음",
        "개입", "box", "박스", "1개", "x", "및", "의", "용", "대형", "소형"
    }

    # 검색어 전처리 (공백 제거하여 포함 여부 확인용)
    base_clean = base_keyword.replace(" ", "")
    
    candidates = []

    for name in product_names:
        cleaned_name = clean_text(name)
        tokens = cleaned_name.split()
        
        # 토큰이 너무 적으면 스킵
        if len(tokens) < 2:
            continue

        # N-gram 생성 (2단어, 3단어 조합)
        # 예: "여성 니트 브이넥 조끼" -> "여성 니트", "니트 브이넥", "브이넥 조끼", "여성 니트 브이넥"...
        grams = []
        
        # 1. Bigram (2단어)
        for i in range(len(tokens) - 1):
            gram = f"{tokens[i]} {tokens[i+1]}"
            grams.append(gram)
            
        # 2. Trigram (3단어) - 조금 더 긴 자동완성어
        for i in range(len(tokens) - 2):
            gram = f"{tokens[i]} {tokens[i+1]} {tokens[i+2]}"
            grams.append(gram)

        # 3. 유효성 검사 및 필터링
        for gram in grams:
            # 불용어가 포함되어 있으면 스킵
            if any(stop in gram for stop in STOPWORDS):
                continue
            
            # [중요] 검색어의 '의미'가 포함된 것만 추출
            # 사용자가 '니트'를 검색했으면 '니트'라는 글자가 들어간 구문만 유효함
            if base_clean in gram.replace(" ", ""):
                candidates.append(gram)

    # 빈도수 계산
    counter = Counter(candidates)
    
    # 빈도수가 높은 순서대로 정렬 (동점일 경우 짧은 단어 우선)
    # most_common()은 빈도수 -> 순서 대로 정렬됨
    sorted_keywords = sorted(counter.most_common(), key=lambda x: (-x[1], len(x[0])))

    # 결과 리스트 생성 (중복 제거 로직 포함)
    final_keywords = []
    seen = set()

    # 원본 키워드도 결과에 포함되지 않도록 처리
    seen.add(base_keyword.replace(" ", ""))

    for kw, count in sorted_keywords:
        kw_clean = kw.replace(" ", "")
        
        # 이미 등록된 단어와 너무 유사하면 스킵 (예: "여성 니트"가 있으면 "여성 니트 티" 스킵 방지 등 조절 가능)
        # 여기서는 단순 중복만 체크
        if kw_clean not in seen:
            final_keywords.append(kw)
            seen.add(kw_clean)
            
        if len(final_keywords) >= limit:
            break
            
    # 만약 결과가 너무 적으면(N-gram 매칭 실패 시), 기존 방식대로 단순 포함 단어도 추가
    if len(final_keywords) < limit:
        simple_tokens = []
        for name in product_names:
            for t in clean_text(name).split():
                if base_clean in t and t not in seen and t not in STOPWORDS:
                    simple_tokens.append(t)
        
        simple_counter = Counter(simple_tokens).most_common()
        for kw, _ in simple_counter:
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
        st.caption("상품명 문맥을 분석하여 실제 자동완성어와 유사한 키워드를 추출합니다.")

        col1, col2 = st.columns([3, 1])
        with col1:
            keyword_input = st.text_input("검색 키워드 입력", placeholder="예: 여성 니트", key="kw1")
        with col2:
            limit_kw = st.number_input("추출 수량", min_value=1, max_value=20, value=10)

        if st.button("🔍 연관검색어 추출", type="primary", use_container_width=True):
            if not keyword_input.strip():
                st.warning("키워드를 입력해 주세요.")
            else:
                with st.spinner(f"'{keyword_input}' 상품 데이터 분석 중..."):
                    # 분석 정확도를 위해 limit을 30개 정도로 넉넉하게 호출 (API 허용 범위 내)
                    res = search_products(ACCESS_KEY, SECRET_KEY, keyword_input.strip(), 30)

                if isinstance(res, dict) and "data" in res:
                    product_data = res["data"].get("productData", [])
                    if not product_data:
                        st.warning("검색 결과가 없습니다. 다른 키워드를 시도해보세요.")
                    else:
                        product_names = [item.get("productName", "") for item in product_data]
                        
                        # [변경] 새로운 추출 로직 적용
                        keywords = extract_auto_complete_like_keywords(keyword_input.strip(), product_names, limit_kw)

                        if keywords:
                            st.success(f"✅ '{keyword_input}' 연관검색어 {len(keywords)}개 추출 완료!")

                            df_kw = pd.DataFrame({
                                "순번": range(1, len(keywords) + 1),
                                "연관검색어": keywords
                            })
                            st.dataframe(df_kw, use_container_width=True, hide_index=True)

                            st.divider()
                            st.caption("💡 키워드 클릭 시 인기상품 탭에서 바로 검색할 수 있습니다.")
                            
                            # 버튼 레이아웃
                            cols = st.columns(4)
                            for i, kw in enumerate(keywords):
                                with cols[i % 4]:
                                    if st.button(kw, key=f"kw_btn_{i}"):
                                        st.session_state["search_keyword"] = kw
                                        st.info(f"📦 '인기상품 검색' 탭으로 이동하여 '{kw}'를 확인하세요!")

                            with st.expander("📋 분석에 사용된 원본 상품명 보기"):
                                for i, name in enumerate(product_names[:10], 1): # 10개만 보여줌
                                    st.write(f"{i}. {name}")

                            excel_data = to_excel(df_kw)
                            st.download_button(
                                label="📥 연관검색어 엑셀 다운로드",
                                data=excel_data,
                                file_name=f"쿠팡_연관검색어_{keyword_input}_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
                                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                            )
                        else:
                            st.warning("추출된 연관검색어가 없습니다.")
                else:
                    st.error("❌ API 호출 실패 (잠시 후 다시 시도해주세요)")
                    # st.json(res) # 에러 디버깅용

    # ── 탭2: 인기상품 ──
    with tab2:
        st.subheader("📦 쿠팡 파트너스 상품 검색")
        
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

        if st.button("🛒 상품 검색", type="primary", use_container_width=True):
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
                            "가격(원)": f"{int(item.get('productPrice', 0)):,}" if item.get("productPrice") else "-",
                            "로켓배송": "🚀 로켓" if item.get("isRocket") else "일반",
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

if __name__ == "__main__":
    main()
