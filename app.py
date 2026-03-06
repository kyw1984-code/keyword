import streamlit as st
import hmac
import hashlib
from time import gmtime, strftime
import requests
import pandas as pd
import urllib.parse
import re
from collections import Counter

# ---------------------------------------------------------
# 1. 쿠팡 파트너스 API 인증 (HMAC) - 공식
# ---------------------------------------------------------
def generate_hmac(method, url, secret_key, access_key):
    path, *query = url.split("?")
    datetime_gmt = strftime('%y%m%d', gmtime()) + 'T' + strftime('%H%M%S', gmtime()) + 'Z'
    message = datetime_gmt + method + path + (query[0] if query else "")
    signature = hmac.new(bytes(secret_key, "utf-8"), message.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"CEA algorithm=HmacSHA256, access-key={access_key}, signed-date={datetime_gmt}, signature={signature}"

# ---------------------------------------------------------
# 2. 핵심 로직: API 데이터에서 키워드 광산 캐기
# ---------------------------------------------------------
def extract_auto_complete_keywords(products, original_keyword):
    """
    상품명 리스트에서 가장 많이 등장하는 단어를 찾아 '자동완성어'처럼 만듭니다.
    """
    word_list = []
    
    # 제외할 단어들 (의미 없는 단어)
    stop_words = [original_keyword, "여성", "남성", "공용", "쿠팡", "로켓배송", "무료배송", "정품", "국산", "세트", "상품", "추천", "개입", "브랜드", "x", "1개"]
    # 검색어도 제외 목록에 추가 (예: '니트' 검색 시 '니트' 단어 제외)
    stop_words.extend(original_keyword.split())

    for item in products:
        name = item.get("productName", "")
        # 특수문자 제거 ([ ] ( ) - 등)
        clean_name = re.sub(r'[^\w\s]', ' ', name)
        
        # 공백 기준으로 단어 쪼개기
        words = clean_name.split()
        
        for w in words:
            # 2글자 이상이고, 숫자가 아니며, 제외 단어가 아닌 것만 수집
            if len(w) >= 2 and not w.isdigit() and w not in stop_words:
                word_list.append(w)

    # 가장 많이 등장한 단어 순서대로 정렬 (빈도수 분석)
    # 상위 10개 추출
    most_common = Counter(word_list).most_common(10)
    
    # (단어, 횟수) 형태에서 단어만 리스트로 변환
    return [word for word, count in most_common]

# ---------------------------------------------------------
# 3. 메인 앱
# ---------------------------------------------------------
def main():
    st.set_page_config(page_title="쿠팡 공식 연관어 추출", layout="wide")
    st.title("🛡️ 쿠팡 API 공식 연관 키워드 추출기")
    st.info("크롤링 없이, 오직 파트너스 API 데이터만을 분석하여 연관 검색어를 생성합니다.")

    # Secrets 체크
    if "COUPANG_ACCESS_KEY" not in st.secrets:
        st.error("Secrets에 키가 설정되지 않았습니다.")
        st.stop()
        
    ACCESS_KEY = st.secrets["COUPANG_ACCESS_KEY"].strip().strip('"').strip("'")
    SECRET_KEY = st.secrets["COUPANG_SECRET_KEY"].strip().strip('"').strip("'")

    keyword = st.text_input("검색어를 입력하세요 (예: 노트북, 니트티)", placeholder="키워드 입력")

    if st.button("연관 검색어 분석 시작"):
        if not keyword:
            st.warning("키워드를 입력해주세요.")
            return

        with st.spinner(f"API를 통해 '{keyword}' 데이터를 분석 중입니다..."):
            # 1. API 호출 (공식 Gateway 사용)
            DOMAIN = "https://api-gateway.coupang.com"
            # 분석 정확도를 위해 최대치인 50개 데이터를 요청 (limit=50이 가능한지 시도, 안되면 10으로 조정)
            # 보통 Search API는 10~50 유동적이나, 데이터 확보를 위해 20 정도로 설정
            URL = f"/v2/providers/affiliate_open_api/apis/openapi/products/search?keyword={urllib.parse.quote(keyword)}&limit=20"
            
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
                        # 2. 키워드 추출 실행
                        extracted_keywords = extract_auto_complete_keywords(products, keyword)
                        
                        # 3. 결과 보여주기 (사진처럼 텍스트 리스트로)
                        st.success("✅ 추출된 연관 검색어 (자동완성 추천)")
                        
                        # 보기 좋게 태그 형태로 출력
                        st.markdown("### 👇 결과 리스트")
                        
                        # 데이터프레임으로 깔끔하게 정리
                        df_result = pd.DataFrame(extracted_keywords, columns=["추천 키워드"])
                        df_result.index = df_result.index + 1 # 1부터 시작하게
                        
                        col1, col2 = st.columns(2)
                        with col1:
                            st.dataframe(df_result, use_container_width=True)
                        with col2:
                            st.write("텍스트 복사용:")
                            st.code(", ".join(extracted_keywords))
                            st.caption(f"💡 원리: 상위 {len(products)}개 상품의 제목에서 가장 많이 반복된 핵심 단어를 추출했습니다.")
                            
                    else:
                        st.warning("검색된 상품이 없어 키워드를 추출할 수 없습니다.")
                else:
                    st.error(f"API 오류: {res_data.get('rMessage', '알 수 없는 오류')}")
            
            except Exception as e:
                st.error(f"시스템 오류: {str(e)}")

if __name__ == "__main__":
    main()
