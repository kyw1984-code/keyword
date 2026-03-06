import streamlit as st
import hmac
import hashlib
from time import gmtime, strftime
import requests
from datetime import datetime
import pandas as pd
import io
import urllib.parse
import re
import random
import time
from collections import Counter


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


USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/119.0.0.0 Safari/537.36",
]


# ---------------------------------------------------------
# 쿠팡 API 상품 검색
# ---------------------------------------------------------
def search_products(access_key, secret_key, keyword, limit=10):
    DOMAIN = "https://api-gateway.coupang.com"
    encoded_keyword = urllib.parse.quote(keyword)
    ts = int(time.time() * 1000)
    URL = f"/v2/providers/affiliate_open_api/apis/openapi/products/search?keyword={encoded_keyword}&limit={limit}&_t={ts}"
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
            seen = set()
            unique = []
            for p in products:
                pid = str(p.get("productId", ""))
                if pid not in seen:
                    seen.add(pid)
                    unique.append(p)
            return unique
        return []
    except Exception:
        return []


# ---------------------------------------------------------
# 유사 단어 판별
# ---------------------------------------------------------
def is_similar_word(a, b):
    a, b = a.lower(), b.lower()
    return a == b or a in b or b in a


def has_overlap(cand_words, seen_list):
    for cw in cand_words:
        for sw in seen_list:
            if is_similar_word(cw, sw):
                return True
    return False


# ---------------------------------------------------------
# 상품명 전처리
# ---------------------------------------------------------
def clean_name(name):
    name = re.sub(r'\[.*?\]|\(.*?\)|【.*?】', ' ', name)
    name = re.sub(r'\d+[\w%]*', ' ', name)
    name = re.sub(r'[^가-힣a-zA-Z\s]', ' ', name)
    name = re.sub(r'\b[a-zA-Z]{1,2}\b', ' ', name)
    return re.sub(r'\s+', ' ', name).strip()


# ---------------------------------------------------------
# 연관 키워드 추출
# ---------------------------------------------------------
STOPWORDS = {
    "이","가","을","를","의","에","은","는","과","와","도","로","으로","만",
    "무료","배송","할인","특가","신상","베스트","추천","인기","최저가","당일",
    "정품","국내","공식","브랜드","세일","쿠폰","증정","사은품","기획","한정",
    "개","팩","세트","묶음","박스","장","켤레","쌍","벌",
    "cm","mm","ml","kg","the","and","for","with","new","best","free"
}

def extract_related_keywords(base_keyword, product_names, limit=10):
    base_words = re.findall(r'[가-힣a-zA-Z]{2,}', base_keyword.strip())
    all_tokens, bigrams = [], []

    for name in product_names:
        cleaned = clean_name(name)
        tokens = [t for t in cleaned.split()
                  if len(t) >= 2 and t.lower() not in STOPWORDS
                  and not any(is_similar_word(t, bw) for bw in base_words)]
        all_tokens.extend(tokens)
        for i in range(len(tokens) - 1):
            bigrams.append(f"{tokens[i]} {tokens[i+1]}")

    token_cnt = Counter(all_tokens)
    bigram_cnt = Counter(bigrams)

    candidates = []
    for bg, c in bigram_cnt.most_common(60):
        if c >= 2: candidates.append(bg)
    for w, c in token_cnt.most_common(60):
        if c >= 2: candidates.append(w)
    for w, c in token_cnt.most_common(60):
        if c == 1: candidates.append(w)

    seen_list = list(base_words)
    result = []
    for cand in candidates:
        cw = re.findall(r'[가-힣a-zA-Z]{2,}', cand)
        if not has_overlap(cw, seen_list):
            result.append(f"{base_keyword.strip()} {cand}")
            seen_list.extend(cw)
        if len(result) >= limit:
            break
    return result


# ---------------------------------------------------------
# 키워드 분석 (로켓비율, 평균가격, 경쟁도, 블루오션 점수)
# ---------------------------------------------------------
def analyze_keyword(products):
    if not products:
        return None

    prices = []
    rocket_count = 0
    free_ship_count = 0

    for p in products:
        try:
            price = int(p.get("productPrice", 0))
            if price > 0:
                prices.append(price)
        except (ValueError, TypeError):
            pass
        if p.get("isRocket"):
            rocket_count += 1
        if p.get("isFreeShipping"):
            free_ship_count += 1

    total = len(products)
    avg_price = int(sum(prices) / len(prices)) if prices else 0
    rocket_ratio = round(rocket_count / total * 100, 1) if total else 0
    free_ratio = round(free_ship_count / total * 100, 1) if total else 0

    # 경쟁도: 로켓배송 비율이 낮을수록 경쟁이 적음 (0~100, 낮을수록 블루오션)
    competition = rocket_ratio

    # 블루오션 점수 계산:
    # - 로켓배송 비율 낮을수록 ↑ (경쟁 적음)
    # - 평균 단가 높을수록 ↑ (수익성 좋음)
    # - 가격 10만원 이상이면 보너스
    price_score = min(avg_price / 100000 * 40, 40)   # 최대 40점
    comp_score  = (100 - rocket_ratio) / 100 * 60     # 최대 60점
    blue_score  = round(price_score + comp_score, 1)

    # 등급 분류
    if blue_score >= 70:
        grade = "🟢 블루오션"
        grade_color = "#28a745"
    elif blue_score >= 45:
        grade = "🟡 중간시장"
        grade_color = "#ffc107"
    else:
        grade = "🔴 레드오션"
        grade_color = "#dc3545"

    return {
        "상품수": total,
        "평균가격": avg_price,
        "로켓비율": rocket_ratio,
        "무료배송비율": free_ratio,
        "경쟁도": competition,
        "블루오션점수": blue_score,
        "등급": grade,
        "등급색": grade_color,
    }


# ---------------------------------------------------------
# 엑셀 변환
# ---------------------------------------------------------
def to_excel(df):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False)
    return output.getvalue()


# ---------------------------------------------------------
# 메인 앱
# ---------------------------------------------------------
def main():
    st.set_page_config(page_title="황금 키워드 발굴기", layout="wide")

    st.title("🏅 황금 키워드 & 꿀통 상품 발굴기")
    st.caption("메인 키워드 → 연관 키워드 자동 추출 → 블루오션 키워드 분석까지 한 번에!")

    missing = []
    if "COUPANG_ACCESS_KEY" not in st.secrets: missing.append("COUPANG_ACCESS_KEY")
    if "COUPANG_SECRET_KEY" not in st.secrets: missing.append("COUPANG_SECRET_KEY")
    if missing:
        st.error(f"🚨 Streamlit Secrets에 다음 키를 등록해 주세요: {', '.join(missing)}")
        st.stop()

    ACCESS_KEY = st.secrets["COUPANG_ACCESS_KEY"].strip().strip('"').strip("'")
    SECRET_KEY = st.secrets["COUPANG_SECRET_KEY"].strip().strip('"').strip("'")

    # ── 입력 영역 ──
    st.markdown("### 🔍 Step 1. 메인 키워드 입력")
    col1, col2, col3 = st.columns([3, 1, 1])
    with col1:
        main_keyword = st.text_input("메인 키워드", placeholder="예: 캠핑, 여성 니트티, 홈트레이닝", label_visibility="collapsed")
    with col2:
        kw_count = st.number_input("연관 키워드 수", min_value=3, max_value=10, value=5)
    with col3:
        run_btn = st.button("🚀 분석 시작", type="primary", use_container_width=True)

    st.divider()

    if run_btn:
        if not main_keyword.strip():
            st.warning("키워드를 입력해 주세요.")
            return

        # ── STEP 1: 메인 키워드로 상품 검색 & 연관 키워드 추출 ──
        st.markdown("### 📡 Step 2. 연관 키워드 자동 추출 중...")
        with st.spinner(f"'{main_keyword}' 상품 데이터 수집 중..."):
            main_products = search_products(ACCESS_KEY, SECRET_KEY, main_keyword.strip(), 10)

        if not main_products:
            st.error("메인 키워드 검색 결과가 없습니다. 다른 키워드를 시도해보세요.")
            return

        product_names = [p.get("productName", "") for p in main_products]
        related_kws = extract_related_keywords(main_keyword.strip(), product_names, kw_count)

        if not related_kws:
            st.warning("연관 키워드를 추출하지 못했습니다.")
            return

        # 분석 대상: 메인 키워드 + 연관 키워드
        all_keywords = [main_keyword.strip()] + related_kws
        st.success(f"✅ 연관 키워드 {len(related_kws)}개 추출 완료! 총 {len(all_keywords)}개 키워드 분석 시작...")

        # ── STEP 2: 각 키워드별 분석 ──
        st.markdown("### 📊 Step 3. 키워드별 분석 중...")
        progress = st.progress(0)
        status_txt = st.empty()

        results = []
        for idx, kw in enumerate(all_keywords):
            status_txt.text(f"🔍 분석 중: {kw} ({idx+1}/{len(all_keywords)})")
            time.sleep(0.4)  # API 호출 간격

            products = search_products(ACCESS_KEY, SECRET_KEY, kw, 10)
            analysis = analyze_keyword(products)

            if analysis:
                results.append({
                    "키워드": kw,
                    "구분": "🔑 메인" if kw == main_keyword.strip() else "🔗 연관",
                    **analysis,
                    "상품목록": products,
                })
            progress.progress((idx + 1) / len(all_keywords))

        status_txt.empty()
        progress.empty()

        if not results:
            st.error("분석 결과가 없습니다.")
            return

        # ── STEP 3: 결과 표시 ──
        st.divider()
        st.markdown("## 📈 분석 결과")

        # 블루오션 점수 기준 정렬
        results_sorted = sorted(results, key=lambda x: x["블루오션점수"], reverse=True)

        # 🏆 TOP 블루오션 키워드 강조
        st.markdown("### 🏆 블루오션 TOP 키워드")
        top3 = results_sorted[:3]
        cols = st.columns(len(top3))
        for i, r in enumerate(top3):
            with cols[i]:
                st.markdown(f"""
                <div style='background:linear-gradient(135deg,#f8f9fa,#e9ecef);
                            padding:18px;border-radius:12px;
                            border-left:5px solid {r["등급색"]};
                            min-height:200px'>
                    <div style='font-size:13px;color:#666'>{r["구분"]}</div>
                    <div style='font-size:16px;font-weight:700;margin:6px 0;color:#333'>
                        {r["키워드"]}
                    </div>
                    <div style='font-size:28px;font-weight:800;color:{r["등급색"]}'>
                        {r["블루오션점수"]}점
                    </div>
                    <div style='font-size:13px;margin-top:8px'>{r["등급"]}</div>
                    <hr style='border:1px solid #dee2e6;margin:10px 0'>
                    <div style='font-size:12px;color:#555;line-height:1.8'>
                        💰 평균가: <b>{r["평균가격"]:,}원</b><br>
                        🚀 로켓비율: <b>{r["로켓비율"]}%</b><br>
                        📦 상품수: <b>{r["상품수"]}개</b>
                    </div>
                </div>
                """, unsafe_allow_html=True)

        st.divider()

        # 전체 분석 테이블
        st.markdown("### 📋 전체 키워드 분석표")
        st.caption("블루오션 점수 높은 순 정렬 | 로켓배송 비율 낮고 단가 높을수록 블루오션")

        df_display = pd.DataFrame([{
            "등급": r["등급"],
            "키워드": r["키워드"],
            "구분": r["구분"],
            "블루오션점수": r["블루오션점수"],
            "평균가격(원)": f"{r['평균가격']:,}",
            "로켓배송비율(%)": r["로켓비율"],
            "무료배송비율(%)": r["무료배송비율"],
            "분석상품수": r["상품수"],
        } for r in results_sorted])

        st.dataframe(df_display, use_container_width=True, hide_index=True)

        # 블루오션 점수 시각화
        st.markdown("### 📊 블루오션 점수 시각화")
        chart_df = pd.DataFrame({
            "키워드": [r["키워드"] for r in results_sorted],
            "블루오션점수": [r["블루오션점수"] for r in results_sorted],
            "평균가격": [r["평균가격"] for r in results_sorted],
            "로켓비율": [r["로켓비율"] for r in results_sorted],
        }).set_index("키워드")
        st.bar_chart(chart_df["블루오션점수"])

        # 블루오션 키워드만 필터
        blue_only = [r for r in results_sorted if "블루오션" in r["등급"]]
        if blue_only:
            st.markdown("### 🟢 블루오션 키워드 상세")
            st.caption("경쟁은 적고 단가는 높은 '황금 키워드'입니다!")
            for r in blue_only:
                with st.expander(f"🟢 {r['키워드']} — 블루오션점수: {r['블루오션점수']}점 | 평균가: {r['평균가격']:,}원"):
                    products = r.get("상품목록", [])
                    if products:
                        df_prod = pd.DataFrame([{
                            "순위": i + 1,
                            "상품명": p.get("productName", "-"),
                            "가격(원)": f"{int(p.get('productPrice',0)):,}" if str(p.get("productPrice","")).isdigit() else "-",
                            "로켓배송": "🚀" if p.get("isRocket") else "일반",
                            "무료배송": "✅" if p.get("isFreeShipping") else "❌",
                            "링크": p.get("productUrl", ""),
                        } for i, p in enumerate(products)])
                        st.dataframe(df_prod, use_container_width=True, hide_index=True)

        # 엑셀 다운로드
        st.divider()
        df_excel = pd.DataFrame([{
            "등급": r["등급"],
            "구분": r["구분"],
            "키워드": r["키워드"],
            "블루오션점수": r["블루오션점수"],
            "평균가격(원)": r["평균가격"],
            "로켓배송비율(%)": r["로켓비율"],
            "무료배송비율(%)": r["무료배송비율"],
            "분석상품수": r["상품수"],
        } for r in results_sorted])

        st.download_button(
            label="📥 전체 분석 결과 엑셀 다운로드",
            data=to_excel(df_excel),
            file_name=f"황금키워드_분석_{main_keyword}_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )

        # 점수 설명
        with st.expander("ℹ️ 블루오션 점수 계산 방법"):
            st.markdown("""
            | 항목 | 배점 | 설명 |
            |------|------|------|
            | 단가 점수 | 최대 40점 | 평균가격 10만원 = 40점 기준 |
            | 경쟁도 점수 | 최대 60점 | 로켓배송 비율 낮을수록 높은 점수 |
            | **합계** | **100점 만점** | |

            - 🟢 **블루오션 (70점↑)**: 경쟁 적고 단가 높음 → 진입 추천
            - 🟡 **중간시장 (45~69점)**: 적당한 경쟁 → 전략 필요
            - 🔴 **레드오션 (44점↓)**: 경쟁 치열 → 진입 신중
            """)


main()
