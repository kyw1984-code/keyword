import streamlit as st
import requests
import datetime
import hashlib
import hmac
import pandas as pd

ACCESS_KEY = st.secrets["COUPANG_ACCESS_KEY"]
SECRET_KEY = st.secrets["COUPANG_SECRET_KEY"]

BASE_URL = "https://api-gateway.coupang.com"
PATH = "/v2/providers/affiliate_open_api/apis/openapi/v1/products/search"


def make_signature(method, path, query):
    now = datetime.datetime.utcnow().strftime('%y%m%dT%H%M%SZ')
    message = f"{now}{method}{path}{query}"

    signature = hmac.new(
        SECRET_KEY.encode(),
        message.encode(),
        hashlib.sha256
    ).hexdigest()

    authorization = (
        f"CEA algorithm=HmacSHA256, "
        f"access-key={ACCESS_KEY}, "
        f"signed-date={now}, "
        f"signature={signature}"
    )

    return authorization


def search_products(keyword):

    params = {
        "keyword": keyword,
        "limit": 20
    }

    query = f"keyword={keyword}&limit=20"

    headers = {
        "Authorization": make_signature("GET", PATH, query),
        "Content-Type": "application/json"
    }

    url = BASE_URL + PATH

    r = requests.get(url, headers=headers, params=params)

    return r.json()


st.title("쿠팡 키워드 분석기")

keyword = st.text_input("키워드 입력")

if st.button("검색"):

    data = search_products(keyword)

    products = data.get("data", {}).get("productData", [])

    rows = []

    for p in products:
        rows.append({
            "상품명": p.get("productName"),
            "가격": p.get("productPrice"),
            "평점": p.get("productRating")
        })

    df = pd.DataFrame(rows)

    st.dataframe(df)
