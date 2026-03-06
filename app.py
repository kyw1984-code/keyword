import streamlit as st
import hmac
import hashlib
from time import gmtime, strftime
import requests
import pandas as pd
import urllib.parse
import re

# 1. HMAC 서명 생성 함수
def generate_hmac(method, url, secret_key, access_key):
    path, *query = url.split("?")
    datetime_gmt = strftime('%y%m%d', gmtime()) + 'T' + strftime('%H%M%S', gmtime()) + 'Z'
    message = datetime_gmt + method + path + (query[0] if query else "")
    signature = hmac.new(bytes(secret_key, "utf-8"), message.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"CEA algorithm=HmacSHA256, access-key={access_key}, signed-date={datetime_gmt}, signature={signature}"

# 2. 상품명에서 연관 키워드를 추출 및 정제하는 함수
def get_related_keywords(product_data, original_keyword):
    if not product_data:
        return []
    
    all_words = []
    for item in product_data:
        name = item.get("productName", "")
        # 한글, 영문, 숫자만 남기고 제거 후 공백 단위로 분리
        words = re.sub(r'[^가-힣a-zA-Z0-9\s]', ' ', name).split()
        all_words.extend(words)
    
    # 1글자 단어, 숫자만 있는 단어, 원본 키워드와 겹치는 단어 제외
    stop_words = [original_keyword, "쿠팡", "정품", "무료배송", "로켓배송", "추천"]
    refined_words = [
        w for w in all_words 
        if len(w) > 1 and not w.isdigit() and w not in stop_words and original_keyword not in w
    ]
    
    # 빈도수 계산 후 상위 15개 반환
    return pd.Series(refined_words).value_counts().head(15).reset_index()

# 3. 메인 앱
def main():
    st.set_page_config(page_title="쿠팡 연관어 추출기", layout="wide")
    st.title("🔍 쿠팡 파트너스 기반 연관 검색어 생성기")

    # 키 설정 (따옴표 제거 로직 포함)
    ACCESS_KEY = st.secrets["COUPANG_ACCESS_KEY"].strip().strip('"').strip("'")
    SECRET_KEY = st.secrets["COUPANG_SECRET_KEY"].strip().strip('"').strip("'")

    keyword = st.text_input("메인 키워드를 입력하세요", placeholder="예: 여성 니트티")

    if st.button("연관 검색어 추출"):
        if not keyword:
            st.warning("키워드를 입력해주세요.")
            return

        with st.spinner("상품 정보를 분석하여 연관어를 뽑아내고 있습니다..."):
            DOMAIN = "https://api-gateway.coupang.com"
            # 분석 데이터 확보를 위해 limit을 20~30으로 설정하는 것이 좋습니다.
            URL = f"/v2/providers/affiliate_open_api/apis/openapi/products/search?keyword={urllib.parse.quote(keyword)}&limit=30"
            
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
                        # --- 연관어 추출 로직 실행 ---
                        df_keywords = get_related_keywords(products, keyword)
                        df_keywords.columns = ["연관 키워드", "추출 빈도(점수)"]

                        st.success(f"✅ '{keyword}' 분석 완료! 가장 연관성이 높은 단어들입니다.")
                        
                        # 화면에 키워드 리스트 보여주기
                        col1, col2 = st.columns([1, 1])
                        with col1:
                            st.subheader("🔥 연관어 추천 순위")
                            st.dataframe(df_keywords, use_container_width=True, hide_index=True)
                        
                        with col2:
                            st.subheader("💡 활용 팁")
                            st.write("1. **블로그 제목**: 메인 키워드와 추천 연관어를 조합하세요.")
                            st.write("2. **태그 구성**: 추출 빈도가 높은 순서대로 해시태그를 작성하세요.")
                            st.write("3. **상세페이지**: 고객들이 많이 검색하는 속성 단어들입니다.")
                    else:
                        st.warning("검색 결과 상품이 없어 분석이 불가능합니다.")
                else:
                    st.error(f"API 응답 오류: {res_data.get('message', '알 수 없는 에러')}")
                    st.json(res_data) # 에러 내용 상세 확인용
            
            except Exception as e:
                st.error(f"시스템 오류: {str(e)}")

if __name__ == "__main__":
    main()
