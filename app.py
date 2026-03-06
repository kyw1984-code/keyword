import streamlit as st
import hmac
import hashlib
from time import gmtime, strftime, sleep
import requests
import pandas as pd
import io
import urllib.parse
import re
from collections import Counter

# ---------------------------------------------------------
# 1. API 인증 & 호출 함수 (기본 엔진)
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

def search_products(access_key, secret_key, keyword, limit=20):
    # 분석을 위해 20개 정도의 데이터를 가져옵니다.
    DOMAIN = "https://api-gateway.coupang.com"
    encoded_keyword = urllib.parse.quote(keyword)
    limit = int(limit)
    # 안전장치: 최대 50개까지 가능하지만 에러 방지를 위해 조절
    safe_limit = 50 if limit > 50 else limit 
    
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
        return None
    except:
        return None

# ---------------------------------------------------------
# 2. 키워드 추출 로직 (하이브리드 방식)
# ---------------------------------------------------------
def clean_text(text):
    text = re.sub(r'\[.*?\]|\(.*?\)|<.*?>', ' ', text)
    text = re.sub(r'[^가-힣a-zA-Z0-9\s]', ' ', text)
    return re.sub(r'\s+', ' ', text).strip()

def extract_hybrid_keywords(base_keyword, product_names):
    """상품명에서 연관 키워드를 추출합니다."""
    STOPWORDS = {"무료배송", "로켓배송", "정품", "특가", "할인", "쿠팡", "브랜드", "세트", "상품", "추천", "박스", "1개", "x", "및"}
    base_clean = base_keyword.replace(" ", "")
    
    candidates = []
    for name in product_names:
        cleaned = clean_text(name)
        tokens = cleaned.split()
        if len(tokens) < 2: continue
        
        # 2단어 조합 (Bigram)
        for i in range(len(tokens) - 1):
            gram = f"{tokens[i]} {tokens[i+1]}"
            if not any(s in gram for s in STOPWORDS):
                candidates.append(gram)

    # 빈도수 정렬
    counter = Counter(candidates).most_common()
    
    final_keywords = []
    seen = set()
    seen.add(base_clean)

    # 검색어가 포함된 문구 우선
    for kw, count in counter:
        if base_clean in kw.replace(" ", "") and kw.replace(" ", "") not in seen:
            final_keywords.append(kw)
            seen.add(kw.replace(" ", ""))
    
    # 부족하면 빈도수 높은 문구 추가
    if len(final_keywords) < 5:
        for kw, count in counter:
            if kw.replace(" ", "") not in seen and count >= 2:
                final_keywords.append(kw)
                seen.add(kw.replace(" ", ""))

    return final_keywords[:10] # 최대 10개 키워드

# ---------------------------------------------------------
# 3. 시장 분석 로직 (핵심 기능)
# ---------------------------------------------------------
def analyze_market(access_key, secret_key, keyword_list):
    report = []
    
    # 진행 상황바 표시
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    total = len(keyword_list)
    
    for i, kw in enumerate(keyword_list):
        status_text.text(f"🔍 분석 중... '{kw}' ({i+1}/{total})")
        progress_bar.progress((i + 1) / total)
        
        # 각 키워드별로 상품 20개 검색
        res = search_products(access_key, secret_key, kw, limit=20)
        
        if res and "data" in res:
            products = res["data"].get("productData", [])
            if not products: continue
            
            # 지표 계산
            prices = [item.get("productPrice", 0) for item in products]
            rockets = [1 for item in products if item.get("isRocket") == True]
            
            avg_price = sum(prices) / len(prices) if prices else 0
            rocket_ratio = (len(rockets) / len(products)) * 100 if products else 0
            
            # 분석 결과 저장
            report.append({
                "키워드": kw,
                "평균가격": round(avg_price),
                "로켓배송 비율(%)": round(rocket_ratio, 1),
                "상품수(표본)": len(products),
                "대표상품": products[0]['productName'] if products else "-"
            })
        
        # API 부하 방지 (매너 딜레이)
        sleep(0.5)
        
    status_text.text("✅ 분석 완료!")
    progress_bar.empty()
    
    return pd.DataFrame(report)

# ---------------------------------------------------------
# 4. 엑셀 변환
# ---------------------------------------------------------
def to_excel(df):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False)
    return output.getvalue()

# ---------------------------------------------------------
# 5. 메인 앱 UI
# ---------------------------------------------------------
def main():
    st.set_page_config(page_title="황금 키워드 발굴기", layout="wide")
    st.title("💰 쿠팡 파트너스 황금 키워드 발굴기")
    st.markdown("""
    이 프로그램은 단순히 키워드를 찾는 것이 아니라, **'돈이 되는 키워드'**인지 분석해줍니다.
    - **평균 가격:** 높을수록 수수료가 셉니다.
    - **로켓 비율:** 높을수록 구매 전환이 잘 일어납니다.
    """)

    # Secrets 확인
    if "COUPANG_ACCESS_KEY" not in st.secrets:
        st.error("Secrets 키 설정이 필요합니다.")
        st.stop()
        
    ACCESS_KEY = st.secrets["COUPANG_ACCESS_KEY"].strip().strip('"').strip("'")
    SECRET_KEY = st.secrets["COUPANG_SECRET_KEY"].strip().strip('"').strip("'")

    col1, col2 = st.columns([3, 1])
    with col1:
        main_keyword = st.text_input("메인 주제 입력 (예: 캠핑, 홈카페)", placeholder="주제 입력")
    with col2:
        analyze_count = st.selectbox("분석할 연관키워드 수", [3, 5, 10], index=1)

    if st.button("🚀 황금 키워드 분석 시작", type="primary", use_container_width=True):
        if not main_keyword:
            st.warning("주제를 입력해주세요.")
            return

        # 1. 연관 키워드 추출 단계
        with st.spinner("1단계: 연관 키워드를 수집하고 있습니다..."):
            res = search_products(ACCESS_KEY, SECRET_KEY, main_keyword, 10)
            if not res or "data" not in res:
                st.error("API 호출 오류")
                st.stop()
                
            product_names = [p['productName'] for p in res["data"].get("productData", [])]
            related_keywords = extract_hybrid_keywords(main_keyword, product_names)
            
            # 분석 개수 제한
            target_keywords = related_keywords[:analyze_count]
            
            # 메인 키워드도 분석 대상에 포함
            if main_keyword not in target_keywords:
                target_keywords.insert(0, main_keyword)

        # 2. 시장 분석 단계
        if target_keywords:
            st.success(f"총 {len(target_keywords)}개의 키워드를 심층 분석합니다.")
            df_report = analyze_market(ACCESS_KEY, SECRET_KEY, target_keywords)
            
            if not df_report.empty:
                # 점수 매기기 (재미 요소): 로켓비율 + (가격/1000)
                # 로켓비율이 높고 가격이 적당히 비싼 것을 추천
                st.subheader("📊 분석 리포트")
                
                # 데이터프레임 스타일링 (가격에 콤마, 로켓비율에 바 차트)
                st.dataframe(
                    df_report.style.format({"평균가격":
