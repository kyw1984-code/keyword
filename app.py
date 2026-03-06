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
# 1. API 인증 & 호출 함수 (Limit 10으로 강력 고정)
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

def search_products(access_key, secret_key, keyword, limit=10):
    DOMAIN = "https://api-gateway.coupang.com"
    encoded_keyword = urllib.parse.quote(keyword)
    
    # [핵심 수정] 
    # 분석 함수에서 20개를 요청하더라도, 여기서는 API 에러 방지를 위해 
    # 무조건 10개 이하로 강제 조정합니다.
    safe_limit = 10 if int(limit) > 10 else int(limit)
    
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
        else:
            # 에러 발생 시 원인을 파악하기 위해 상세 내용 반환
            return {"error": True, "code": response.status_code, "msg": response.text}
    except Exception as e:
        return {"error": True, "msg": str(e)}

# ---------------------------------------------------------
# 2. 키워드 추출 로직
# ---------------------------------------------------------
def clean_text(text):
    text = re.sub(r'\[.*?\]|\(.*?\)|<.*?>', ' ', text)
    text = re.sub(r'[^가-힣a-zA-Z0-9\s]', ' ', text)
    return re.sub(r'\s+', ' ', text).strip()

def extract_hybrid_keywords(base_keyword, product_names):
    STOPWORDS = {"무료배송", "로켓배송", "정품", "특가", "할인", "쿠팡", "브랜드", "세트", "상품", "추천", "박스", "1개", "x", "및"}
    base_clean = base_keyword.replace(" ", "")
    
    candidates = []
    for name in product_names:
        cleaned = clean_text(name)
        tokens = cleaned.split()
        if len(tokens) < 2: continue
        
        for i in range(len(tokens) - 1):
            gram = f"{tokens[i]} {tokens[i+1]}"
            if not any(s in gram for s in STOPWORDS):
                candidates.append(gram)

    counter = Counter(candidates).most_common()
    
    final_keywords = []
    seen = set()
    seen.add(base_clean)

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

    return final_keywords[:10]

# ---------------------------------------------------------
# 3. 시장 분석 로직 (에러 처리 강화)
# ---------------------------------------------------------
def analyze_market(access_key, secret_key, keyword_list):
    report = []
    
    progress_bar = st.progress(0)
    status_text = st.empty()
    total = len(keyword_list)
    
    for i, kw in enumerate(keyword_list):
        status_text.text(f"🔍 분석 중... '{kw}' ({i+1}/{total})")
        progress_bar.progress((i + 1) / total)
        
        # [수정] limit을 10으로 명시적 호출
        res = search_products(access_key, secret_key, kw, limit=10)
        
        if res and "data" in res:
            products = res["data"].get("productData", [])
            if not products: 
                continue
            
            prices = [item.get("productPrice", 0) for item in products]
            rockets = [1 for item in products if item.get("isRocket") == True]
            
            avg_price = sum(prices) / len(prices) if prices else 0
            rocket_ratio = (len(rockets) / len(products)) * 100 if products else 0
            
            report.append({
                "키워드": kw,
                "평균가격": avg_price,
                "로켓배송 비율(%)": rocket_ratio,
                "상품수(표본)": len(products),
                "대표상품": products[0]['productName'] if products else "-"
            })
        else:
            # [디버깅] 만약 에러가 나면 화면에 작게 출력해서 원인을 알림
            if res and "error" in res:
                st.toast(f"⚠️ '{kw}' 검색 실패: {res.get('msg', '알 수 없는 오류')}")
        
        # API 부하 방지 (1초로 늘림)
        sleep(1.0)
        
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

        with st.spinner("1단계: 연관 키워드를 수집하고 있습니다..."):
            # 여기서도 limit 10 고정
            res = search_products(ACCESS_KEY, SECRET_KEY, main_keyword, 10)
            
            if not res or "data" not in res:
                st.error("API 호출 오류가 발생했습니다.")
                st.json(res) # 상세 에러 출력
                st.stop()
                
            product_names = [p['productName'] for p in res["data"].get("productData", [])]
            related_keywords = extract_hybrid_keywords(main_keyword, product_names)
            
            target_keywords = related_keywords[:analyze_count]
            if main_keyword not in target_keywords:
                target_keywords.insert(0, main_keyword)

        if target_keywords:
            st.success(f"총 {len(target_keywords)}개의 키워드를 심층 분석합니다.")
            df_report = analyze_market(ACCESS_KEY, SECRET_KEY, target_keywords)
            
            if not df_report.empty:
                st.subheader("📊 분석 리포트")
                
                # 데이터 포맷팅 및 스타일링
                # (이전 오류 해결된 버전)
                format_dict = {
                    "평균가격": "{:,.0f}원", 
                    "로켓배송 비율(%)": "{:.1f}%"
                }
                
                styled_df = df_report.style.format(format_dict)\
                                           .background_gradient(subset=["로켓배송 비율(%)"], cmap="Greens")
                
                st.dataframe(styled_df, use_container_width=True)
                
                # 인사이트 도출
                best_rocket = df_report.loc[df_report["로켓배송 비율(%)"].idxmax()]
                best_price = df_report.loc[df_report["평균가격"].idxmax()]
                
                col_a, col_b = st.columns(2)
                with col_a:
                    st.info(f"**🔥 전환율 왕 (로켓비율 1등)**\n\n키워드: **{best_rocket['키워드']}**\n\n로켓 비율이 {best_rocket['로켓배송 비율(%)']:.1f}%입니다.")
                with col_b:
                    st.success(f"**💰 고단가 왕 (평균가격 1등)**\n\n키워드: **{best_price['키워드']}**\n\n평균 {best_price['평균가격']:,.0f}원입니다.")
                
                excel_data = to_excel(df_report)
                st.download_button(
                    "📥 분석 결과 엑셀 다운로드",
                    data=excel_data,
                    file_name=f"황금키워드분석_{main_keyword}.xlsx"
                )
            else:
                st.error("분석된 데이터가 없습니다. (API 호출 실패)")
                st.write("가능성: 너무 빠른 호출로 인한 일시적 차단, 또는 한도 초과")
        else:
            st.warning("연관 키워드를 찾지 못했습니다.")

if __name__ == "__main__":
    main()
