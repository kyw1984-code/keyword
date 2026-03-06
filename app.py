import streamlit as st
import hmac
import hashlib
from time import gmtime, strftime
import requests
import time
import random
import pandas as pd
import io


USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
]


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


def try_category_id(access_key, secret_key, category_id):
    """단일 카테고리 ID 테스트 → 성공 여부 + 상품 수 반환"""
    DOMAIN = "https://api-gateway.coupang.com"
    ts = int(time.time() * 1000)
    URL = f"/v2/providers/affiliate_open_api/apis/openapi/products/bestcategories/{category_id}?limit=5&_t={ts}"
    authorization = generate_hmac("GET", URL, secret_key, access_key)
    headers = {
        "Authorization": authorization,
        "Content-Type": "application/json;charset=UTF-8",
        "User-Agent": random.choice(USER_AGENTS),
        "Cache-Control": "no-cache",
    }
    try:
        session = requests.Session()
        session.cookies.clear()
        resp = session.get(f"{DOMAIN}{URL}", headers=headers, timeout=8)
        raw = resp.text

        if resp.status_code == 200:
            data = resp.json()
            rcode = data.get("rCode", "")
            products = data.get("data", [])
            if rcode == "0" and isinstance(products, list) and len(products) > 0:
                # 첫 상품명으로 카테고리 추정
                sample_name = products[0].get("productName", "")[:30]
                return {
                    "status": "✅ 성공",
                    "상품수": len(products),
                    "샘플상품명": sample_name,
                    "rCode": rcode,
                    "http": resp.status_code,
                }
            else:
                return {
                    "status": "⚠️ 응답은 왔으나 데이터 없음",
                    "상품수": 0,
                    "샘플상품명": "",
                    "rCode": rcode,
                    "http": resp.status_code,
                }
        else:
            msg = ""
            try:
                msg = resp.json().get("message", "")[:40]
            except Exception:
                msg = raw[:40]
            return {
                "status": f"❌ HTTP {resp.status_code}",
                "상품수": 0,
                "샘플상품명": msg,
                "rCode": "-",
                "http": resp.status_code,
            }
    except Exception as e:
        return {
            "status": f"❌ 오류",
            "상품수": 0,
            "샘플상품명": str(e)[:40],
            "rCode": "-",
            "http": 0,
        }


def to_excel(df):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False)
    return output.getvalue()


def main():
    st.set_page_config(page_title="쿠팡 카테고리 ID 탐색기", layout="wide")
    st.title("🔍 쿠팡 카테고리 ID 탐색기")
    st.caption("Best Category API에서 실제로 작동하는 카테고리 ID를 자동으로 찾아줍니다.")

    missing = []
    if "COUPANG_ACCESS_KEY" not in st.secrets: missing.append("COUPANG_ACCESS_KEY")
    if "COUPANG_SECRET_KEY" not in st.secrets: missing.append("COUPANG_SECRET_KEY")
    if missing:
        st.error(f"🚨 Streamlit Secrets에 등록 필요: {', '.join(missing)}")
        st.stop()

    ACCESS_KEY = st.secrets["COUPANG_ACCESS_KEY"].strip().strip('"').strip("'")
    SECRET_KEY = st.secrets["COUPANG_SECRET_KEY"].strip().strip('"').strip("'")

    st.markdown("### ⚙️ 탐색 범위 설정")
    st.warning("⚠️ API는 시간당 10회 제한이 있어 한 번에 너무 많이 스캔하면 오류가 날 수 있어요. 범위를 좁게 설정하세요!")

    col1, col2, col3 = st.columns(3)
    with col1:
        id_start = st.number_input("시작 ID", min_value=1, max_value=99999, value=1001)
    with col2:
        id_end = st.number_input("끝 ID", min_value=1, max_value=99999, value=1030)
    with col3:
        delay = st.slider("요청 간격(초)", min_value=0.5, max_value=3.0, value=1.0, step=0.5)

    total_count = int(id_end - id_start + 1)
    st.info(f"📋 총 {total_count}개 ID 탐색 예정 | 예상 소요시간: 약 {int(total_count * delay)}초")

    # 단일 ID 테스트
    st.divider()
    st.markdown("### 🎯 단일 ID 빠른 테스트")
    col_a, col_b = st.columns([2, 1])
    with col_a:
        single_id = st.number_input("테스트할 카테고리 ID", min_value=1, value=1001, key="single")
    with col_b:
        if st.button("🔍 단일 테스트", use_container_width=True):
            with st.spinner(f"ID {single_id} 테스트 중..."):
                result = try_category_id(ACCESS_KEY, SECRET_KEY, single_id)
            if "✅" in result["status"]:
                st.success(f"**ID {single_id}** → {result['status']} | 상품 {result['상품수']}개")
                st.write(f"샘플 상품명: {result['샘플상품명']}")
            else:
                st.error(f"**ID {single_id}** → {result['status']}")
                st.write(f"메시지: {result['샘플상품명']}")

    st.divider()

    # 범위 스캔
    st.markdown("### 🚀 범위 스캔")
    if st.button("🚀 카테고리 ID 범위 스캔 시작", type="primary", use_container_width=True):
        progress = st.progress(0)
        status_txt = st.empty()
        results = []
        success_ids = []

        ids_to_scan = list(range(int(id_start), int(id_end) + 1))

        for i, cid in enumerate(ids_to_scan):
            status_txt.markdown(f"🔍 스캔 중: **ID {cid}** ({i+1}/{len(ids_to_scan)})")
            result = try_category_id(ACCESS_KEY, SECRET_KEY, cid)
            results.append({
                "카테고리ID": cid,
                "결과": result["status"],
                "상품수": result["상품수"],
                "샘플상품명": result["샘플상품명"],
                "rCode": result["rCode"],
                "HTTP": result["http"],
            })
            if "✅" in result["status"]:
                success_ids.append(cid)
            progress.progress((i + 1) / len(ids_to_scan))
            time.sleep(delay)

        status_txt.empty()
        progress.empty()

        df = pd.DataFrame(results)

        # 성공한 ID만 따로
        success_df = df[df["결과"].str.contains("✅")]

        st.markdown(f"### 📊 스캔 결과: **{len(success_ids)}개** 유효 카테고리 ID 발견!")

        if not success_df.empty:
            st.markdown("#### ✅ 작동하는 카테고리 ID 목록")
            st.dataframe(success_df, use_container_width=True, hide_index=True)

            # 코드 스니펫 자동 생성
            st.markdown("#### 📋 코드에 바로 붙여넣기용 딕셔너리")
            code_str = "VALID_CATEGORY_IDS = {\n"
            for _, row in success_df.iterrows():
                name = row["샘플상품명"][:10] if row["샘플상품명"] else "카테고리"
                code_str += f'    "{name}...": {row["카테고리ID"]},\n'
            code_str += "}"
            st.code(code_str, language="python")
        else:
            st.warning("이 범위에서 작동하는 카테고리 ID가 없습니다. 다른 범위를 시도해보세요.")

        st.markdown("#### 📋 전체 스캔 결과")
        st.dataframe(df, use_container_width=True, hide_index=True)

        st.download_button(
            label="📥 스캔 결과 엑셀 다운로드",
            data=to_excel(df),
            file_name=f"쿠팡_카테고리ID_스캔_{id_start}~{id_end}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )

    # 안내
    with st.expander("💡 쿠팡 웹사이트에서 직접 확인하는 방법"):
        st.markdown("""
        1. [coupang.com](https://www.coupang.com) 접속
        2. 상단 카테고리 메뉴 클릭
        3. URL에서 `categoryId=숫자` 확인
        ```
        https://www.coupang.com/np/categories/products?categoryId=1001
                                                                    ^^^^
                                                               이 숫자가 ID
        ```
        4. 위 **단일 ID 빠른 테스트**로 API 작동 여부 확인
        """)


main()
