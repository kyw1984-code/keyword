import streamlit as st
import requests
import pandas as pd
from datetime import datetime
import io

# ---------------------------------------------------------
# 1. 쿠팡 자동완성 키워드 추출 함수
# ---------------------------------------------------------
def get_coupang_suggestions(keyword):
    """
    쿠팡 검색창의 자동완성 데이터를 가져옵니다.
    """
    if not keyword:
        return []
    
    # 쿠팡 자동완성 공식 API 엔드포인트
    url = f"https://www.coupang.com/np/search/auto?keyword={keyword}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=5)
        if response.status_code == 200:
            data = response.json()
            # 자동완성 리스트 추출 (suggest 부분)
            suggestions = [item.get('keyword') for item in data.get('suggest', [])]
            return suggestions
        return []
    except:
        return []

# ---------------------------------------------------------
# 2. 엑셀 변환 함수
# ---------------------------------------------------------
def to_excel(df):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False)
    return output.getvalue()

# ---------------------------------------------------------
# 3. 메인 앱 레이아웃
# ---------------------------------------------------------
def main():
    st.set_page_config(page_title="쿠팡 키워드 마스터", layout="wide")
    
    st.title("🔍 쿠팡 자동완성 & 키워드 분석기")
    st.markdown("입력하신 키워드와 관련된 **쿠팡 실제 급상승 검색어**를 실시간으로 추출합니다.")

    # 사이드바 설정
    st.sidebar.header("설정")
    target_keyword = st.sidebar.text_input("분석할 메인 키워드", placeholder="예: 캠핑")
    
    if st.sidebar.button("연관 키워드 추출하기"):
        if target_keyword:
            with st.spinner(f"'{target_keyword}' 연관 키워드 분석 중..."):
                suggestions = get_coupang_suggestions(target_keyword)
                
                if suggestions:
                    st.subheader(f"✅ '{target_keyword}' 관련 자동완성어")
                    
                    # 결과를 데이터프레임으로 변환
                    df_suggest = pd.DataFrame({
                        "순번": range(1, len(suggestions) + 1),
                        "자동완성 키워드": suggestions
                    })

                    # 가로로 깔끔하게 보여주기 위한 컬럼 배치
                    col1, col2 = st.columns([2, 1])
                    
                    with col1:
                        st.dataframe(df_suggest, use_container_width=True)
                    
                    with col2:
                        st.info("💡 **팁:** 이 키워드들은 쿠팡 소비자들이 지금 이 순간 가장 많이 검색하는 단어들입니다. 상품 소싱이나 제목 키워드 구성에 활용하세요!")
                        
                        # 엑셀 다운로드
                        excel_data = to_excel(df_suggest)
                        st.download_button(
                            label="📥 키워드 리스트 다운로드",
                            data=excel_data,
                            file_name=f"쿠팡_자동완성_{target_keyword}_{datetime.now().strftime('%m%d')}.xlsx",
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                        )
                else:
                    st.warning("추출된 자동완성어가 없습니다. 다른 검색어를 입력해 보세요.")
        else:
            st.error("키워드를 먼저 입력해 주세요.")

    # 하단 가이드
    st.divider()
    with st.expander("ℹ️ 활용 방법"):
        st.write("""
        1. 왼쪽 사이드바에 '아이폰' 또는 '영양제' 같은 메인 키워드를 입력합니다.
        2. '연관 키워드 추출하기' 버튼을 누릅니다.
        3. 쿠팡 앱 검색창에 뜨는 **자동완성 리스트**가 순서대로 표시됩니다.
        4. 이 키워드들을 바탕으로 블로그 제목을 짓거나, 상품을 검색하는 데 활용하세요.
        """)

if __name__ == "__main__":
    main()
