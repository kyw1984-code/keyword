import streamlit as st
import hmac
import hashlib
from time import gmtime, strftime
import requests
import pandas as pd
import io
import urllib.parse
import re
from collections import Counter

# =========================================================
# 1. 핵심 엔진: 쿠팡 API 호출 및 분석
# =========================================================
def generate_hmac(method, url, secret_key, access_key):
    path, *query = url.split("?")
    datetime_gmt = strftime('%y%m%d', gmtime()) + 'T' + strftime('%H%M%S', gmtime()) + 'Z'
    message = datetime_gmt + method + path + (query[0] if query else "")
    signature = hmac.new(bytes(secret_key, "utf-8"), message.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"CEA algorithm=HmacSHA256, access-key={access_key}, signed-date={datetime_gmt}, signature={signature}"

def search_products(access_key, secret_key, keyword):
    # 배포용은 안전하게 limit=10 고정 (에러 방지)
    URL = f"/v2/providers/affiliate_open_api/apis/openapi/products/search?keyword={urllib.parse.quote(keyword)}&limit=10"
    headers = {
        "Authorization": generate_hmac("GET", URL, secret_key, access_key),
        "Content-Type": "application/json;charset=UTF-8"
    }
    try:
        res = requests.get("https://api-gateway.coupang.com" + URL, headers=headers, timeout=5)
        return res.json() if res.status_code == 200 else None
    except:
        return None

def extract_keywords(base_keyword, products):
    """상품명에서 황금 키워드를 추출하는 분석 로직"""
    text = " ".join([p['productName'] for p in products])
    # 특수문자 제거
    text = re.sub(r'\[.*?\]|\(.*?\)|<.*?>|[^가-힣a-zA-Z0-9\s]', ' ', text)
    tokens = text.split()
    
    # 의미 없는 단어 제거
    stops = {"무료배송", "로켓배송", "정품", "할인", "쿠팡", "브랜드", "세트", "상품", "추천", "박스", "1개", "x", "및", "개입", "호", "ml", "kg"}
    
    # 2단어(Bigram) 분석
    bigrams = []
    for i in range(len(tokens)-1):
        if tokens[i] not in stops and tokens[i+1] not in stops:
            bigrams.append(f"{tokens[i]} {tokens[i+1]}")
            
    # 빈도수 상위 추출
    counts = Counter(bigrams).most_common(10)
    keywords = [word for word, cnt in counts]
    
    # 결과가 적으면 검색어 포함된 문구 추가
    if len(keywords) < 5:
        base_clean = base_keyword.replace(" ", "")
        for word in tokens:
            if base_clean in word and word not in keywords:
                keywords.append(word)
                
    return keywords[:10]

def to_excel(df):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False)
    return output.getvalue()

# =========================================================
# 2. 메인 웹사이트 UI
# =========================================================
def main():
    st.set_page_config(page_title="쿠팡 마케팅 마스터", page_icon="🛍️", layout="wide")
    
    st.title("🛍️ 쿠팡 파트너스 마케팅 툴")
    st.markdown("""
    **수강생 여러분 환영합니다!** 이 도구는 쿠팡의 데이터를 분석하여 **팔리는 키워드**와 **상품 정보**를 자동으로 찾아줍니다.
    """)
    
    # 사이드바: API 키 입력 (수강생들이 자기 키를 넣어서 쓰게 함)
    with st.sidebar:
        st.header("🔑 API 설정")
        st.info("본인의 쿠팡 파트너스 API 키를 입력하세요.")
        
        # Streamlit Secrets에 저장된 키가 있으면 자동 입력 (관리자용)
        default_access = st.secrets.get("COUPANG_ACCESS_KEY", "")
        default_secret = st.secrets.get("COUPANG_SECRET_KEY", "")
        
        access_key = st.text_input("Access Key", value=default_access, type="password")
        secret_key = st.text_input("Secret Key", value=default_secret, type="password")
        
        if not access_key or not secret_key:
            st.warning("API 키를 입력해야 작동합니다.")
            st.stop()

    # 메인 기능 탭
    tab1, tab2 = st.tabs(["🔍 키워드 발굴", "📝 블로그 포스팅 생성"])
    
    # --- 탭 1: 키워드 발굴 ---
    with tab1:
        st.subheader("황금 키워드 찾기")
        keyword = st.text_input("검색어를 입력하세요 (예: 캠핑)", key="kw_search")
        
        if st.button("분석 시작", key="btn_anal"):
            with st.spinner("상품 데이터를 분석 중입니다..."):
                data = search_products(access_key, secret_key, keyword)
                
                if data and "data" in data and data["data"]["productData"]:
                    products = data["data"]["productData"]
                    keywords = extract_keywords(keyword, products)
                    
                    st.success("✅ 분석 완료!")
                    
                    col1, col2 = st.columns([1, 2])
                    with col1:
                        st.markdown("### 🔥 추천 연관 키워드")
                        st.dataframe(pd.DataFrame(keywords, columns=["추천 키워드"]), use_container_width=True)
                        
                    with col2:
                        st.markdown("### 📊 상위 노출 상품 분석")
                        df = pd.DataFrame([{
                            "상품명": p['productName'],
                            "가격": f"{int(p['productPrice']):,}원",
                            "로켓": "🚀" if p['isRocket'] else ""
                        } for p in products])
                        st.dataframe(df, use_container_width=True)
                else:
                    st.error("검색 결과가 없거나 API 키가 잘못되었습니다.")

    # --- 탭 2: 블로그 포스팅 생성 ---
    with tab2:
        st.subheader("1초 만에 블로그 HTML 만들기")
        target_kw = st.text_input("포스팅할 상품 키워드", placeholder="예: 가성비 노트북", key="kw_blog")
        
        if st.button("HTML 생성하기", key="btn_blog"):
            data = search_products(access_key, secret_key, target_kw)
            
            if data and "data" in data and data["data"]["productData"]:
                products = data["data"]["productData"]
                
                # HTML 생성 로직
                html = f"""
                <div style='border:1px solid #ddd; padding:20px;'>
                    <h3>'{target_kw}' 추천 BEST 5</h3>
                    <p>쿠팡 랭킹순으로 엄선한 제품들입니다.</p>
                    <table style='width:100%; border-collapse:collapse;'>
                """
                
                for i, p in enumerate(products[:5]):
                    html += f"""
                    <tr style='border-bottom:1px solid #eee;'>
                        <td style='padding:10px;'><img src='{p['productImage']}' width='80'></td>
                        <td style='padding:10px;'>
                            <b>{i+1}위. {p['productName']}</b><br>
                            <span style='color:red;'>{int(p['productPrice']):,}원</span>
                            {' <span style="background:#007bff;color:white;font-size:10px;padding:2px;">로켓배송</span>' if p['isRocket'] else ''}
                        </td>
                        <td style='padding:10px;'>
                            <a href='{p['productUrl']}' style='background:#e44d26;color:white;padding:5px 10px;text-decoration:none;border-radius:4px;'>구매하기</a>
                        </td>
                    </tr>
                    """
                html += "</table><br><p style='font-size:11px; color:#888;'>이 포스팅은 쿠팡 파트너스 활동의 일환으로, 이에 따른 일정액의 수수료를 제공받습니다.</p></div>"
                
                st.code(html, language="html")
                st.success("위 코드를 복사해서 블로그 HTML 모드에 붙여넣으세요!")
            else:
                st.error("상품을 찾을 수 없습니다.")

if __name__ == "__main__":
    main()
