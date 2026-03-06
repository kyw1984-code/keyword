import streamlit as st
import hmac
import hashlib
from time import gmtime, strftime
import requests
import pandas as pd
import urllib.parse
import re  # 단어 정제를 위한 정규표현식

# 1. HMAC 서명 및 API 호출 함수는 기존 성공한 코드와 동일 (생략/유지)
def generate_hmac(method, url, secret_key, access_key):
    path, *query = url.split("?")
    datetime_gmt = strftime('%y%m%d', gmtime()) + 'T' + strftime('%H%M%S', gmtime()) + 'Z'
    message = datetime_gmt + method + path + (query[0] if query else "")
    signature = hmac.new(bytes(secret_key, "utf-8"), message.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"CEA algorithm=HmacSHA256, access-key={access_key}, signed-date={datetime_gmt}, signature={signature}"

# 2. 상품명에서 연관 키워드를 추출하는 함수
def extract_keywords(product_names, original_keyword):
    all_words = []
    for name in product_names:
        # 특수문자 제거 및 공백 기준 분리
        words = re.sub(r'[^\w\s]', '', name).split()
        all_words.extend(words)
    
    # 너무 짧은 단어(1글자)나 원래 검색어는 제외
    stop_words = [original_keyword, "및", "선물", "추천", "세트", "용"]
    refined_words = [w for w in all_words if len(w) > 1 and w not in stop_words]
    
    # 빈도수 측정 후 상위 키워드 반환
    return pd.Series(refined_words).value_counts().head(10).index.tolist()

def main():
    st.set_page_config(page_title="쿠팡 연관 키워드 추출기", layout="wide")
    st.title("🔍 쿠팡 파트너스 기반 연관 검색어 추출")

    ACCESS_KEY = st.secrets["COUPANG_ACCESS_KEY"].strip().strip('"').strip("'")
    SECRET_KEY = st.secrets["COUPANG_SECRET_KEY"].strip().strip('"').strip("'")

    keyword = st.text_input("검색어를 입력하세요", placeholder="예: 여성 니트티")

    if keyword:
        DOMAIN = "https://api-gateway.coupang.com"
        URL = f"/v2/providers/affiliate_open_api/apis/openapi/products/search?keyword={urllib.parse.quote(keyword)}&limit=20"
        
        authorization = generate_hmac("GET", URL, SECRET_KEY, ACCESS_KEY)
        headers = {"Authorization": authorization, "Content-Type": "application/json;charset=UTF-8", "x-requested-with": "openapi"}

        res = requests.get(DOMAIN + URL, headers=headers).json()

        if "data" in res and res["data"].get("productData"):
            products = res["data"]["productData"]
            product_names = [p['productName'] for p in products]

            # --- 핵심: 연관 키워드 추출 ---
            related_keywords = extract_keywords(product_names, keyword)
            
            st.subheader(f"✨ '{keyword}' 관련 추천 연관어")
            # 버튼 형태로 나열하여 클릭 시 바로 재검색되도록 구성 가능
            cols = st.columns(len(related_keywords))
            for i, word in enumerate(related_keywords):
                cols[i].button(word, key=f"btn_{word}")

            st.divider()

            # 원본 상품 데이터 테이블 (이미지에서 보신 부분)
            df = pd.DataFrame([{
                "순위": i+1,
                "연관 키워드가 포함된 상품명": p['productName'],
                "가격": p['productPrice'],
                "링크": p['productUrl']
            } for i, p in enumerate(products)])
            
            st.write("📋 **분석된 상품 원본 데이터**")
            st.dataframe(df, use_container_width=True)
        else:
            st.error("데이터를 가져오지 못했습니다. API 제한 혹은 키 설정을 확인하세요.")

if __name__ == "__main__":
    main()
