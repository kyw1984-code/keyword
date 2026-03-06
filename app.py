import streamlit as st
import hmac
import hashlib
from time import gmtime, strftime
import requests
import json
from datetime import datetime
import pandas as pd
import io
import urllib.parse


# ---------------------------------------------------------
# HMAC 서명 생성 (공식 문서 방식)
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
# 키워드 검색 API (공식 확인된 엔드포인트)
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
# 엑셀 변환
# ---------------------------------------------------------
def to_excel(df):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False)
    return output.getvalue()


# ---------------------------------------------------------
# 카테고리별 키워드 매핑
# ---------------------------------------------------------
CATEGORY_KEYWORDS = {
    "여성패션": "여성 옷",
    "남성패션": "남성 옷",
    "뷰티": "화장품",
    "식품": "식품",
    "주방용품": "주방용품",
    "생활용품": "생활용품",
    "가전디지털": "가전제품",
    "스포츠/레저": "스포츠용품",
    "완구/취미": "장난감",
    "반려동물용품": "반려동물",
    "도서/음반/DVD": "베스트셀러 도서",
}


# ---------------------------------------------------------
# 메인 앱
# ---------------------------------------------------------
def main():
    st.set_page_config(page_title="쿠팡 인기상품 추출", layout="wide")
    st.title("🛍️ 쿠팡 파트너스 인기상품 추출")

    if "COUPANG_ACCESS_KEY" not in st.secrets or "COUPANG_SECRET_KEY" not in st.secrets:
        st.error("🚨 Streamlit Cloud 설정(Secrets)에 키를 등록해 주세요.")
        st.stop()

    ACCESS_KEY = st.secrets["COUPANG_ACCESS_KEY"].strip().strip('"').strip("'")
    SECRET_KEY = st.secrets["COUPANG_SECRET_KEY"].strip().strip('"').strip("'")

    st.sidebar.header("추출 옵션")

    search_mode = st.sidebar.radio("검색 방법", ["카테고리 선택", "직접 키워드 입력"])

    if search_mode == "카테고리 선택":
        selected_cat = st.sidebar.selectbox("카테고리 선택", list(CATEGORY_KEYWORDS.keys()))
        keyword = CATEGORY_KEYWORDS[selected_cat]
        label = selected_cat
    else:
        keyword = st.sidebar.text_input("검색 키워드", placeholder="예: 에어프라이어")
        label = keyword

    limit_count = st.sidebar.slider("추출 개수 (최대 10개)", 1, 10, 10)

    st.sidebar.info("⚠️ 쿠팡 API는 시간당 최대 10회 호출 가능합니다.")

    if st.sidebar.button("데이터 가져오기"):
        if not keyword:
            st.warning("키워드를 입력해 주세요.")
            return

        with st.spinner(f"'{keyword}' 상품 검색 중..."):
            res = search_products(ACCESS_KEY, SECRET_KEY, keyword, limit_count)

            if isinstance(res, dict) and "data" in res:
                product_data = res["data"].get("productData", [])

                if not product_data:
                    st.warning("검색 결과가 없습니다. 다른 키워드를 시도해보세요.")
                    return

                df = pd.DataFrame([{
                    "순위": item.get("rank", i + 1),
                    "상품명": item.get("productName"),
                    "가격(원)": item.get("productPrice"),
                    "로켓배송": "🚀" if item.get("isRocket") else "일반",
                    "무료배송": "✅" if item.get("isFreeShipping") else "❌",
                    "상품링크": item.get("productUrl")
                } for i, item in enumerate(product_data)])

                st.success(f"✅ '{label}' 상품 {len(df)}개를 가져왔습니다!")
                st.dataframe(df, use_container_width=True)

                excel_data = to_excel(df)
                st.download_button(
                    label="📥 엑셀 파일 다운로드",
                    data=excel_data,
                    file_name=f"쿠팡_{label}_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
            else:
                st.error("❌ API 호출 실패")
                st.json(res)


main()

