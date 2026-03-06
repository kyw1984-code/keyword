import streamlit as st
import requests
import pandas as pd
from datetime import datetime
import io

# ---------------------------------------------------------
# 1. 쿠팡 자동완성 키워드 추출 함수 (강화 버전)
# ---------------------------------------------------------
def get_coupang_suggestions(keyword):
    if not keyword:
        return []
    
    # 쿠팡의 실제 검색창에서 사용하는 최신 API 주소
    # 'q' 파라미터를 사용하는 최신 엔드포인트로 변경
    url = f"https://www.coupang.com/np/search/auto?keyword={keyword}"
    
    # 쿠팡 서버의 차단을 피하기 위한 상세 헤더 설정
    headers = {
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
        "Referer": "https://www.coupang.com/",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
        "X-Requested-With": "XMLHttpRequest"
    }
    
    try:
        # verify=True (기본값)로 보안 연결 유지
        response = requests.get(url, headers=headers, timeout=5)
        
        if response.status_code == 200:
            data = response.json()
            # 데이터 구조 확인: suggest -> 리스트 형태
            if 'suggest' in data and data['suggest']:
                suggestions = [item.get('keyword') for item in data['suggest']]
                return suggestions
            else:
                # 결과는 성공했으나 추천 검색어가 없는 경우
                return []
        else:
            return [f"에러 발생 (상태 코드: {response.status_code})"]
    except Exception as e:
        return [f"연결 오류: {str(e)}"]

# ---------------------------------------------------------
# 2. 메인 UI
# ---------------------------------------------------------
def main():
    st.set_page_config(page_title="쿠팡 키워드 추출기", layout="centered")
    st.title("🔍 쿠팡 자동완성 키워드 추출")

    target_keyword = st.text_input("분석할 메인 키워드를 입력하세요", placeholder="예: 캠핑, 자전거, 영양제")
    
    if st.button("실시간 연관 키워드 가져오기"):
        if target_keyword:
            with st.spinner("쿠팡에서 키워드를 분석 중입니다..."):
                suggestions = get_coupang_suggestions(target_keyword)
                
                if suggestions and not suggestions[0].startswith("에러"):
                    st.success(f"✅ '{target_keyword}' 관련 추천 검색어를 찾았습니다.")
                    
                    # 데이터프레임 구성
                    df = pd.DataFrame({
                        "연관 검색어": suggestions
                    })
                    
                    st.table(df) # 깔끔하게 표로 출력
                    
                    # 엑셀 다운로드
                    output = io.BytesIO()
                    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                        df.to_excel(writer, index=False)
                    
                    st.download_button(
                        label="📥 엑셀로 저장하기",
                        data=output.getvalue(),
                        file_name=f"쿠팡_연관어_{target_keyword}.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    )
                elif suggestions and suggestions[0].startswith("에러"):
                    st.error(suggestions[0])
                else:
                    st.warning("데이터가 없습니다. 검색어를 조금 더 짧게(예: '캠핑용' -> '캠핑') 입력해 보세요.")
        else:
            st.info("검색어를 입력해 주세요.")

if __name__ == "__main__":
    main()
