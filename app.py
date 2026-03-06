import streamlit as st
import hmac
import hashlib
from time import gmtime, strftime
import requests
import pandas as pd
import urllib.parse
import re

# ---------------------------------------------------------
# 1. HMAC 서명 생성 (기존 성공 코드 유지)
# ---------------------------------------------------------
def generate_hmac(method, url, secret_key, access_key):
    path, *query = url.split("?")
    datetime_gmt = strftime('%y%m%d', gmtime()) + 'T' + strftime('%H%M%S', gmtime()) + 'Z'
    message = datetime_gmt + method + path + (query[0] if query else "")
    signature = hmac.new(bytes(secret_key, "utf-8"), message.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"CEA algorithm=HmacSHA256, access-key={access_key}, signed-date={datetime_gmt}, signature={signature}"

# ---------------------------------------------------------
# 2. 연관 키워드 분석 로직
# ---------------------------------------------------------
def get_related_keywords(product_data, original_keyword):
    if not product_data:
        return []
    
    all_words = []
    for item in product_data:
        name = item.get("productName", "")
        # 특수문자 제거 후 단어 분리
        words = re.sub(r'[^가-힣a-zA-Z0-9\s]', ' ', name).split()
        all_words.extend(words)
    
    # 불용어(제외할 단어) 설정
    stop_words = [original_keyword, "쿠팡", "무료배송", "로켓배송", "추천", "세트", "정품", "국산", "상품", "개입"]
    
    # 단어 정제: 1글자 제외, 검색어 포함 단어 제외
    refined_words = [
        w for w in all_words 
        if len(w) > 1 and not w.isdigit() and w not in stop_words and original_keyword not in w
    ]
    
    # 상위 10개 키워드 추출
    return pd.Series(refined_words).value_counts().head(10).reset_index()

# ---------------------------------------------------------
# 3. 메인 앱
# ---------------------------------------------------------
def main():
    st.set_page_config(page_title="쿠팡 키워드 분석기", layout="wide")
    st.title("🔍 쿠팡 자동완성(연관어) 추출기")

    # Secrets에서 키 가져오기 (따옴표 제거 로직 포함)
    if "COUPANG_ACCESS_KEY" not in st.secrets:
        st.error("Secrets에 키가 없습니다.")
        st.stop()
        
    ACCESS_KEY = st.secrets["COUPANG_ACCESS_KEY"].strip().strip('"').strip("'")
    SECRET_KEY = st.secrets["COUPANG_SECRET_KEY"].strip().strip('"').strip("'")

    keyword = st.text_input("분석할 키워드를 입력하세요", placeholder="예: 캠핑 의자")

    if st.button("분석 시작"):
        if not keyword:
            st.warning("키워드를 입력해주세요.")
            return

        with st.spinner(f"'{keyword}' 관련 상품을 분석 중입니다..."):
            DOMAIN = "https://api-gateway.coupang.com"
            # ✅ [수정 핵심] limit을 30에서 10으로 변경했습니다. (쿠팡 최대 허용치)
            URL = f"/v2/providers/affiliate_open_api/apis/openapi/products/search?keyword={urllib.parse.quote(keyword)}&limit=10"
            
            auth = generate_hmac("GET", URL, SECRET_KEY, ACCESS_KEY)
            headers = {
                "Authorization": auth,
                "Content-Type": "application/json;charset=UTF-8",
                "x-requested-with": "openapi"
            }

            try:
                response = requests.get(DOMAIN + URL, headers=headers, timeout=10)
                res_data = response.json()

                if response.status_code == 200 and "data" in res_data:
                    products = res_data["data"].get("productData", [])
                    
                    if products:
                        # 1. 연관 키워드 추출
                        df_keywords = get_related_keywords(products, keyword)
                        df_keywords.columns = ["추천 연관어", "빈도"]

                        # 2. 결과 화면 구성
                        col1, col2 = st.columns([1, 2])
                        
                        with col1:
                            st.success(f"✅ 추출 완료!")
                            st.dataframe(df_keywords, use_container_width=True, hide_index=True)
                            
                        with col2:
                            st.info("💡 **분석 원리**")
                            st.write(f"쿠팡에서 실제 판매 중인 상위 10개 상품의 제목을 분석하여, '{keyword}'와 가장 자주 함께 쓰이는 단어를 찾았습니다.")
                            st.write("---")
                            st.write("**분석된 원본 상품 예시:**")
                            for p in products[:3]: # 3개만 예시로 보여줌
                                st.caption(f"- {p['productName']}")

                    else:
                        st.warning("검색된 상품이 없습니다.")
                else:
                    # 에러 메시지 출력
                    st.error(f"오류 발생: {res_data.get('rMessage', '')}")
                    st.json(res_data)
            
            except Exception as e:
                st.error(f"시스템 오류: {str(e)}")

if __name__ == "__main__":
    main()
