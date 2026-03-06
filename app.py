import streamlit as st
import requests
import pandas as pd
from datetime import datetime
import io

def get_coupang_suggestions(keyword):
    if not keyword:
        return []
    
    # 1. 쿠팡 최신 자동완성 API 주소
    url = f"https://www.coupang.com/np/search/auto?keyword={keyword}"
    
    # 2. 브라우저인 것처럼 속이기 위한 고도화된 헤더
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
        "Referer": "https://www.coupang.com/",
        "X-Requested-With": "XMLHttpRequest",
        "Sec-Ch-Ua": '"Chromium";v="122", "Not(A:Brand";v="24", "Google Chrome";v="122"',
        "Sec-Ch-Ua-Mobile": "?0",
        "Sec-Ch-Ua-Platform": '"Windows"',
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-origin"
    }
    
    try:
        # 세션을 사용하여 쿠키를 자동으로 관리
        session = requests.Session()
        # 먼저 메인 페이지에 접속해 기본 쿠키를 확보 (선택 사항이지만 차단 방지에 도움됨)
        session.get("https://www.coupang.com/", headers={"User-Agent": headers["User-Agent"]}, timeout=5)
        
        # 실제 데이터 요청
        response = session.get(url, headers=headers, timeout=5)
        
        if response.status_code == 200:
            data = response.json()
            if 'suggest' in data and data['suggest']:
                return [item.get('keyword') for item in data['suggest']]
            return []
        elif response.status_code == 403:
            return ["error_403"]
        else:
            return [f"에러 발생: {response.status_code}"]
            
    except Exception as e:
        return [f"연결 오류: {str(e)}"]

# ---------------------------------------------------------
# Streamlit UI
# ---------------------------------------------------------
st.set_page_config(page_title="쿠팡 키워드 우회 추출기")
st.title("🔍 쿠팡 자동완성 (403 에러 해결 버전)")

target_keyword = st.text_input("검색어를 입력하세요", placeholder="예: 캠핑")

if st.button("추출하기"):
    if target_keyword:
        with st.spinner("보안 필터 우회 중..."):
            suggestions = get_coupang_suggestions(target_keyword)
            
            if suggestions == ["error_403"]:
                st.error("🚫 쿠팡 서버가 접속을 차단했습니다 (403 에러).")
                st.info("💡 **원인:** 너무 잦은 요청이거나 IP가 제한되었습니다.\n**해결:** 잠시 후 다시 시도하거나, 다른 검색어를 입력해 보세요.")
            elif suggestions and not suggestions[0].startswith("에러"):
                df = pd.DataFrame({"연관 검색어": suggestions})
                st.table(df)
            else:
                st.warning("데이터가 없거나 다른 에러가 발생했습니다.")
    else:
        st.info("키워드를 입력해 주세요.")
