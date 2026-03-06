import streamlit as st
import hmac
import hashlib
from time import gmtime, strftime
import requests
from datetime import datetime
import pandas as pd
import io
import urllib.parse
import random
import time


# ---------------------------------------------------------
# 쿠팡 파트너스 카테고리 ID 목록 (대 > 중 구조)
# 실제 API에서 작동하는 categoryId 값
# ---------------------------------------------------------
CATEGORIES = {
    "패션의류": {
        "여성의류":       1001,
        "남성의류":       1002,
        "스포츠의류":     1003,
        "언더웨어/잠옷":  1004,
        "유아동의류":     1005,
        "패션잡화":       1006,
    },
    "뷰티": {
        "스킨케어":       1010,
        "메이크업":       1011,
        "헤어케어":       1012,
        "바디케어":       1013,
        "향수/방향":      1014,
        "남성그루밍":     1015,
    },
    "식품": {
        "건강식품":       1020,
        "신선식품":       1021,
        "가공식품":       1022,
        "커피/음료/차":   1023,
        "유제품/아이스크림": 1024,
        "베이커리/간식":  1025,
    },
    "주방/생활": {
        "주방용품":       1030,
        "생활용품":       1031,
        "욕실용품":       1032,
        "청소용품":       1033,
        "세탁용품":       1034,
    },
    "가전/디지털": {
        "생활가전":       1040,
        "주방가전":       1041,
        "영상/음향":      1042,
        "PC/주변기기":    1043,
        "스마트폰/태블릿": 1044,
        "카메라":         1045,
        "웨어러블기기":   1046,
    },
    "스포츠/레저": {
        "운동기구":       1050,
        "아웃도어":       1051,
        "구기스포츠":     1052,
        "수영/수상스포츠": 1053,
        "자전거/킥보드":  1054,
        "캠핑/등산":      1055,
    },
    "완구/육아": {
        "완구/장난감":    1060,
        "유아용품":       1061,
        "아동도서":       1062,
        "임산부용품":     1063,
    },
    "반려동물": {
        "강아지용품":     1070,
        "고양이용품":     1071,
        "소동물용품":     1072,
        "반려동물식품":   1073,
    },
    "도서/문구": {
        "국내도서":       1080,
        "음반/DVD":       1081,
        "문구/오피스":    1082,
        "악기":           1083,
    },
    "자동차/공구": {
        "자동차용품":     1090,
        "공구/DIY":       1091,
        "원예/가드닝":    1092,
    },
}

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/119.0.0.0 Safari/537.36",
]


# ---------------------------------------------------------
# HMAC 서명 생성
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
# Best Category API 호출
# ---------------------------------------------------------
def get_best_category(access_key, secret_key, category_id, limit=20):
    DOMAIN = "https://api-gateway.coupang.com"
    ts = int(time.time() * 1000)
    URL = f"/v2/providers/affiliate_open_api/apis/openapi/products/bestcategories/{category_id}?limit={limit}&_t={ts}"

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
        response = session.get(f"{DOMAIN}{URL}", headers=headers, timeout=10)

        if response.status_code == 200:
            data = response.json()
            # 응답 구조: {"rCode":"0", "rMessage":"", "data":[...]}
            if data.get("rCode") == "0":
                products = data.get("data", [])
            else:
                # 다른 응답 구조 시도
                products = data.get("data", {})
                if isinstance(products, dict):
                    products = products.get("productData", [])
            return {"success": True, "products": products, "raw": data}
        else:
            return {"success": False, "status": response.status_code, "msg": response.text}
    except Exception as e:
        return {"success": False, "msg": str(e)}


# ---------------------------------------------------------
# Search API 폴백 (Best Category 실패 시)
# ---------------------------------------------------------
def search_fallback(access_key, secret_key, keyword, limit=10):
    DOMAIN = "https://api-gateway.coupang.com"
    encoded = urllib.parse.quote(keyword)
    ts = int(time.time() * 1000)
    URL = f"/v2/providers/affiliate_open_api/apis/openapi/products/search?keyword={encoded}&limit={limit}&_t={ts}"
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
        response = session.get(f"{DOMAIN}{URL}", headers=headers, timeout=10)
        if response.status_code == 200:
            data = response.json()
            products = data.get("data", {}).get("productData", [])
            # 중복 제거
            seen, unique = set(), []
            for p in products:
                pid = str(p.get("productId", ""))
                if pid not in seen:
                    seen.add(pid)
                    unique.append(p)
            return {"success": True, "products": unique}
        return {"success": False, "msg": f"HTTP {response.status_code}"}
    except Exception as e:
        return {"success": False, "msg": str(e)}


# ---------------------------------------------------------
# 엑셀 변환
# ---------------------------------------------------------
def to_excel(df):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False)
    return output.getvalue()


# ---------------------------------------------------------
# 상품 데이터 → DataFrame
# ---------------------------------------------------------
def products_to_df(products):
    rows = []
    for idx, item in enumerate(products):
        price = item.get("productPrice", item.get("price", 0))
        try:
            price_fmt = f"{int(price):,}"
        except (ValueError, TypeError):
            price_fmt = str(price)

        rows.append({
            "순위": item.get("rank", idx + 1),
            "상품명": item.get("productName", item.get("name", "-")),
            "가격(원)": price_fmt,
            "로켓배송": "🚀 로켓" if item.get("isRocket") else "일반",
            "무료배송": "✅" if item.get("isFreeShipping") else "❌",
            "상품ID": str(item.get("productId", "-")),
            "상품링크": item.get("productUrl", item.get("url", "")),
        })

    df = pd.DataFrame(rows)
    if not df.empty and "순위" in df.columns:
        df = df.sort_values("순위").reset_index(drop=True)
    return df


# ---------------------------------------------------------
# 메인 앱
# ---------------------------------------------------------
def main():
    st.set_page_config(page_title="쿠팡 카테고리 베스트", layout="wide")
    st.title("🏆 쿠팡 카테고리별 베스트셀러")
    st.caption("쿠팡 파트너스 Best Category API 연동 | 중복 제거 | 순위 정렬")

    # Secrets 검증
    missing = []
    if "COUPANG_ACCESS_KEY" not in st.secrets: missing.append("COUPANG_ACCESS_KEY")
    if "COUPANG_SECRET_KEY" not in st.secrets: missing.append("COUPANG_SECRET_KEY")
    if missing:
        st.error(f"🚨 Streamlit Secrets에 다음 키를 등록해 주세요: {', '.join(missing)}")
        st.stop()

    ACCESS_KEY = st.secrets["COUPANG_ACCESS_KEY"].strip().strip('"').strip("'")
    SECRET_KEY = st.secrets["COUPANG_SECRET_KEY"].strip().strip('"').strip("'")

    # ── 사이드바 ──
    st.sidebar.header("📂 카테고리 선택")
    big_cat = st.sidebar.selectbox("🔹 대카테고리", list(CATEGORIES.keys()))
    mid_cats = CATEGORIES[big_cat]
    mid_cat = st.sidebar.selectbox("🔸 중카테고리", list(mid_cats.keys()))
    category_id = mid_cats[mid_cat]
    limit_count = st.sidebar.slider("조회 상품 수", 5, 50, 20)

    st.sidebar.divider()
    st.sidebar.info(f"📌 카테고리 ID: `{category_id}`")
    st.sidebar.caption("⚠️ API 호출은 시간당 최대 10회")

    # 경로 표시
    st.markdown(f"### 📌 `{big_cat}` > `{mid_cat}`")
    st.caption(f"Category ID: {category_id}")
    st.divider()

    if st.sidebar.button("🏆 베스트셀러 조회", type="primary", use_container_width=True):
        with st.spinner(f"'{big_cat} > {mid_cat}' 베스트셀러 조회 중..."):
            result = get_best_category(ACCESS_KEY, SECRET_KEY, category_id, limit_count)

        # Best Category API 성공
        if result.get("success") and result.get("products"):
            products = result["products"]
            st.success(f"✅ **{big_cat} > {mid_cat}** 베스트셀러 {len(products)}개")
            df = products_to_df(products)

        # Best Category API 실패 → Search API 폴백
        else:
            st.warning(f"⚠️ Best Category API 응답 없음 → 키워드 검색으로 대체합니다.")

            # 오류 상세 표시
            with st.expander("🔧 API 응답 상세"):
                if "raw" in result:
                    st.json(result["raw"])
                else:
                    st.write(result)

            # 카테고리명으로 검색 폴백
            with st.spinner(f"'{mid_cat}' 키워드로 검색 중..."):
                fb = search_fallback(ACCESS_KEY, SECRET_KEY, mid_cat, min(limit_count, 10))

            if fb.get("success") and fb.get("products"):
                products = fb["products"]
                st.info(f"🔍 키워드 '{mid_cat}' 검색 결과 {len(products)}개로 대체 표시")
                df = products_to_df(products)
            else:
                st.error("❌ 검색 결과도 없습니다. 다른 카테고리를 선택해보세요.")
                return

        # ── TOP 3 카드 ──
        if len(df) >= 3:
            st.markdown("#### 🥇🥈🥉 TOP 3")
            cols = st.columns(3)
            medals = ["🥇", "🥈", "🥉"]
            for i in range(3):
                row = df.iloc[i]
                with cols[i]:
                    link = row.get("상품링크", "")
                    st.markdown(f"""
                    <div style='background:linear-gradient(135deg,#fff,#f8f9fa);
                                padding:16px;border-radius:12px;
                                border:1px solid #dee2e6;
                                border-top:4px solid {"#FFD700" if i==0 else "#C0C0C0" if i==1 else "#CD7F32"};
                                min-height:150px'>
                        <div style='font-size:26px'>{medals[i]}</div>
                        <div style='font-size:13px;font-weight:600;margin:8px 0;color:#333;line-height:1.4'>
                            {str(row["상품명"])[:50]}{'...' if len(str(row["상품명"]))>50 else ''}
                        </div>
                        <div style='color:#e63946;font-weight:700;font-size:16px'>{row["가격(원)"]}원</div>
                        <div style='font-size:12px;color:#888;margin-top:6px'>{row["로켓배송"]}</div>
                    </div>
                    """, unsafe_allow_html=True)
                    if link:
                        st.markdown(f"[🔗 상품 보기]({link})")
            st.divider()

        # ── 전체 순위표 ──
        st.markdown("#### 📋 전체 순위표")
        display_df = df.drop(columns=["상품ID"], errors="ignore")
        st.dataframe(display_df, use_container_width=True, hide_index=True)

        # ── 통계 ──
        st.divider()
        st.markdown("#### 📊 통계 요약")
        c1, c2, c3, c4 = st.columns(4)
        try:
            prices = [int(str(p).replace(",","")) for p in df["가격(원)"] if str(p).replace(",","").isdigit()]
            rocket_cnt = df["로켓배송"].str.contains("🚀").sum()
            free_cnt = df["무료배송"].str.contains("✅").sum()
            c1.metric("총 상품 수", f"{len(df)}개")
            c2.metric("평균 가격", f"{int(sum(prices)/len(prices)):,}원" if prices else "-")
            c3.metric("🚀 로켓배송", f"{rocket_cnt}개 ({int(rocket_cnt/len(df)*100)}%)")
            c4.metric("✅ 무료배송", f"{free_cnt}개 ({int(free_cnt/len(df)*100)}%)")
        except Exception:
            pass

        # ── 엑셀 다운로드 ──
        st.divider()
        st.download_button(
            label="📥 베스트셀러 엑셀 다운로드",
            data=to_excel(df),
            file_name=f"쿠팡_베스트_{big_cat}_{mid_cat}_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )


main()
