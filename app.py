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
# 1. HMAC 서명 생성 (공식 인증)
# ---------------------------------------------------------
def generate_hmac(method, url, secret_key, access_key):
    path, *query = url.split("?")
    datetime_gmt = strftime('%y%m%d', gmtime()) + 'T' + strftime('%H%M%S', gmtime()) + 'Z'
    message = datetime_gmt + method + path + (query[0] if query else "")
    signature = hmac.new(bytes(secret_key, "utf-8"), message.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"CEA algorithm=HmacSHA256, access-key={access_key}, signed-date={datetime_gmt}, signature={signature}"

# ---------------------------------------------------------
# 2. 핵심 로직: 상위 10개 상품에서 키워드 추출
# ---------------------------------------------------------
def extract_keywords_from_products(products, original_keyword):
    """
    상품명 10개에서 핵심 단어를 뽑아 자동완성어 리스트를 만듭니다.
    """
    word_list = []
    
    # 검색어 자체나 의미 없는 단어 제거
    stop_words = [original_keyword, "쿠팡", "로켓배송", "무료배송", "정품", "국산", "세트", "상품", "추천", "개입", "브랜드", "모델", "호환"]
    # 검색어에 포함된 단어들도 제외 (예: '여성 니트' 검색 시 '여성', '니트' 제외)
    stop_words.extend(original_keyword.split())

    for item in products:
        name = item.get("productName", "")
        # 특수문자 제거 후 공백 기준 분리
        # 가-힣(한글), a-zA-Z(영어), 0-9(숫자)만 남김
        clean_name = re.sub(r'[^가-힣a-zA-Z0-9\s]', ' ', name)
        words = clean_name.split()
        
        for w in words:
            # 2글자 이상이고, 숫자가 아니며, 금지어가 아닌 것만
            if len(w) >= 2 and not w.isdigit() and w not in stop_words:
                word_list.append(w)

    # 빈도수가 높은 순서대로 정렬하여 중복 제거
    # 상위 10개 상품이므로 데이터가 적어서, 1번만 등장해도 리스트에 포함
    counts = Counter(word_list)
    
    # 많이 등장한 순서대로 정렬된 키워드 리스트 반환
    return [word for word, count in counts.most_common(10)]

# ---------------------------------------------------------
# 3. 메인 앱
# ---------------------------------------------------------
def main():
    st.set_page_config(page_title="쿠팡 연관어 추출기", layout="centered")
    st.title("🛡️ 쿠팡 API 공식 연관 키워드 추출")
    st.info("공식 API(limit=10)를 사용하여 안전하게 연관 검색어를 생성합니다.")

    # Secrets 체크 및 로드
    if "COUPANG_ACCESS_KEY" not in st.secrets:
        st.error("Secrets 설정이 필요합니다.")
        st.stop()
        
    ACCESS_KEY = st.secrets["COUPANG_ACCESS_KEY"].strip().strip('"').strip("'")
    SECRET_KEY = st.secrets["COUPANG_SECRET_KEY"].strip().strip('"').strip("'")

    keyword = st.text_input("검색어를 입력하세요", placeholder="예: 캠핑 의자")

    if st.button("연관어 추출하기"):
        if not keyword:
            st.warning("키워드를 입력해주세요.")
            return

        with st.spinner(f"'{keyword}' 관련 데이터를 분석 중입니다..."):
            DOMAIN = "https://api-gateway.coupang.com"
            # ✅ [수정 완료] limit=10 으로 고정 (에러 해결 핵심)
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
                        # 키워드 추출 함수 실행
                        extracted = extract_keywords_from_products(products, keyword)
                        
                        st.success("✅ 추출 완료! (자동완성 추천)")
                        
                        if extracted:
                            # 1. 텍스트 리스트 형태로 보여주기 (복사하기 좋게)
                            st.markdown("### 📋 추천 키워드 리스트")
                            st.code(", ".join(extracted))

                            # 2. 깔끔한 테이블로 보여주기
                            df = pd.DataFrame(extracted, columns=["연관 키워드"])
                            df.index = df.index + 1
                            st.dataframe(df, use_container_width=True)
                        else:
                            st.warning("연관 키워드를 추출할 만큼 충분한 데이터가 없습니다.")

                        st.divider()
                        with st.expander("분석에 사용된 원본 상품명 보기 (증빙용)"):
                            for p in products:
                                st.text(f"- {p['productName']}")
                    else:
                        st.warning("검색된 상품이 없습니다.")
                else:
                    # 또 다른 에러가 있다면 메시지 출력
                    st.error(f"API 오류: {res_data.get('rMessage', '알 수 없는 오류')}")
            
            except Exception as e:
                st.error(f"시스템 오류: {str(e)}")

if __name__ == "__main__":
    main()
