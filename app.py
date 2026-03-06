import streamlit as st
import hmac
import hashlib
from time import gmtime, strftime
import requests
import json
import pandas as pd
import io
import urllib.parse
from datetime import datetime

# ---------------------------------------------------------
# 1. 쿠팡 파트너스 공식 HMAC 서명 생성
# ---------------------------------------------------------
def generate_hmac(method, url, secret_key, access_key):
    path, *query = url.split("?")
    # 쿠팡 규격 타임스탬프
    datetime_gmt = strftime('%y%m%d', gmtime()) + 'T' + strftime('%H%M%S', gmtime()) + 'Z'
    message = datetime_gmt + method + path + (query[0] if query else "")

    signature = hmac.new(
        bytes(secret_key, "utf-8"),
        message.encode("utf-8"),
        hashlib.sha256
    ).hexdigest()

    return f"CEA algorithm=HmacSHA256, access-key={access_key}, signed-date={datetime_gmt}, signature={signature}"

# ---------------------------------------------------------
# 2. 파트너스 검색 API 호출 함수 (403 에러 없음)
# ---------------------------------------------------------
def search_coupang_api(access_key, secret_key, keyword, limit=20):
    DOMAIN = "https://api-gateway.coupang.com"
    encoded_keyword = urllib.parse.quote(keyword)
    # 공식 검색 엔드포인트
    URL = f"/v2/providers/affiliate_open_api/apis/openapi/products/search?keyword={encoded_keyword}&limit={limit}"

    authorization = generate_hmac("GET", URL, secret_key, access_key)

    headers = {
        "Authorization": authorization,
        "Content-Type": "application/json;charset=UTF-8",
        "x-requested-with": "openapi" # 보안 및 트래킹용 필수 헤더
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
# 3. 메인 UI (Streamlit)
# ---------------------------------------------------------
def main():
    st.set_page_config(page_title="쿠팡 파트너스 마스터", layout="wide")
    st.title("🛠️ 쿠팡 파트너스 API 상품 추출기")
    st.info("이 도구는 공식 API 키를 사용하므로 403 차단 에러가 발생하지 않습니다.")

    # Secrets 확인 및 따옴표 제거
    if "COUPANG_ACCESS_KEY" not in st.secrets or "COUPANG_SECRET_KEY" not in st.secrets:
        st.error("🚨 Streamlit Secrets에 키를 먼저 등록해주세요.")
        st.stop()

    ACCESS_KEY = st.secrets["COUPANG_ACCESS_KEY"].strip().strip('"').strip("'")
    SECRET_KEY = st.secrets["COUPANG_SECRET_KEY"].strip().strip('"').strip("'")

    # 검색 입력창
    col1, col2 = st.columns([3, 1])
    with col1:
        keyword = st.text_input("검색어를 입력하세요 (예: 캠핑용품, 무선이어폰)", placeholder="검색어 입력 후 엔터")
    with col2:
        limit_count = st.selectbox("추출 개수", [10, 20, 30, 50], index=1)

    if keyword:
        with st.spinner(f"'{keyword}' 관련 최신 데이터를 가져오는 중..."):
            res = search_coupang_api(ACCESS_KEY, SECRET_KEY, keyword, limit_count)

            if isinstance(res, dict) and "data" in res:
                product_data = res["data"].get("productData", [])

                if not product_data:
                    st.warning("검색 결과가 없습니다.")
                else:
                    # 데이터 프레임 생성
                    df = pd.DataFrame([{
                        "순위": i + 1,
                        "상품명": item.get("productName"),
                        "가격": f"{item.get('productPrice'):,}원",
                        "로켓": "🚀" if item.get("isRocket") else "",
                        "링크": item.get("productUrl")
                    } for i, item in enumerate(product_data)])

                    st.success(f"✅ '{keyword}' 관련 상품 {len(df)}개를 찾았습니다.")
                    
                    # 결과 출력
                    st.dataframe(df, use_container_width=True)

                    # 엑셀 다운로드
                    output = io.BytesIO()
                    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                        df.to_excel(writer, index=False)
                    
                    st.download_button(
                        label="📥 결과 엑셀로 저장하기",
                        data=output.getvalue(),
                        file_name=f"쿠팡_추출_{keyword}.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    )
            else:
                st.error("❌ API 호출 실패")
                st.json(res)

if __name__ == "__main__":
    main()
