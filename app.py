# app.py
import json
import time
from pathlib import Path

import pandas as pd
import requests
import streamlit as st

st.set_page_config(page_title="연관검색어 수집기", layout="wide")
st.title("연관검색어 수집기")
st.caption("승인된 데이터 소스 또는 사전 확보한 파일만 사용하세요.")

st.sidebar.header("입력 방식")
mode = st.sidebar.radio(
    "데이터 소스 선택",
    ["승인된 API", "JSON 파일 업로드", "CSV 파일 업로드"],
)

def normalize_rows(rows):
    normalized = []
    for row in rows:
        keyword = row.get("keyword", "")
        suggestions = row.get("suggestions", [])
        if isinstance(suggestions, str):
            suggestions = [suggestions]
        for rank, s in enumerate(suggestions, start=1):
            normalized.append({
                "keyword": keyword,
                "rank": rank,
                "suggestion": s
            })
    return pd.DataFrame(normalized)

def call_approved_api(base_url: str, api_key: str, keywords: list[str], sleep_sec: float):
    results = []
    session = requests.Session()
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Accept": "application/json",
        "User-Agent": "approved-client/1.0",
    }

    progress = st.progress(0)
    status = st.empty()

    for i, kw in enumerate(keywords, start=1):
        status.write(f"조회 중: {kw} ({i}/{len(keywords)})")
        try:
            resp = session.get(
                base_url,
                params={"q": kw},
                headers=headers,
                timeout=15,
            )

            if resp.status_code == 429:
                st.warning(f"속도 제한 감지: {kw} 에서 중단했습니다.")
                break

            resp.raise_for_status()
            data = resp.json()

            # 예시 응답 형식:
            # {"keyword":"노트북","suggestions":["노트북 파우치","노트북 거치대"]}
            results.append({
                "keyword": data.get("keyword", kw),
                "suggestions": data.get("suggestions", []),
            })

        except requests.RequestException as e:
            st.error(f"{kw} 조회 실패: {e}")
            results.append({
                "keyword": kw,
                "suggestions": [],
            })

        progress.progress(i / len(keywords))
        time.sleep(sleep_sec)

    return results

keywords_text = st.text_area(
    "키워드 입력",
    placeholder="예:\n노트북\n텀블러\n무선이어폰",
    height=180,
)

keywords = [x.strip() for x in keywords_text.splitlines() if x.strip()]

if mode == "승인된 API":
    st.subheader("승인된 API 사용")
    base_url = st.text_input("API URL", placeholder="https://your-approved-endpoint.example.com/suggest")
    api_key = st.text_input("API Key", type="password")
    sleep_sec = st.number_input("호출 간격(초)", min_value=0.5, max_value=10.0, value=1.0, step=0.5)

    if st.button("조회 시작", type="primary"):
        if not base_url or not api_key or not keywords:
            st.error("API URL, API Key, 키워드를 모두 입력하세요.")
        else:
            rows = call_approved_api(base_url, api_key, keywords, sleep_sec)
            df = normalize_rows(rows)
            st.dataframe(df, use_container_width=True)

            csv = df.to_csv(index=False).encode("utf-8-sig")
            st.download_button(
                "CSV 다운로드",
                data=csv,
                file_name="suggestions.csv",
                mime="text/csv",
            )

elif mode == "JSON 파일 업로드":
    st.subheader("JSON 업로드")
    uploaded = st.file_uploader("JSON 파일 선택", type=["json"])
    if uploaded:
        data = json.load(uploaded)
        if isinstance(data, dict):
            data = [data]
        df = normalize_rows(data)
        st.dataframe(df, use_container_width=True)

        csv = df.to_csv(index=False).encode("utf-8-sig")
        st.download_button(
            "CSV 다운로드",
            data=csv,
            file_name="suggestions_from_json.csv",
            mime="text/csv",
        )

elif mode == "CSV 파일 업로드":
    st.subheader("CSV 업로드")
    uploaded = st.file_uploader("CSV 파일 선택", type=["csv"])
    if uploaded:
        df = pd.read_csv(uploaded)
        st.dataframe(df, use_container_width=True)

        csv = df.to_csv(index=False).encode("utf-8-sig")
        st.download_button(
            "CSV 다운로드",
            data=csv,
            file_name="suggestions_from_csv.csv",
            mime="text/csv",
        )
