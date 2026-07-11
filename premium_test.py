import streamlit as st
import streamlit.components.v1 as components
import pandas as pd

# ==========================================
# 0. 페이지 기본 설정
# ==========================================
st.set_page_config(page_title="고급필터 테스트", layout="wide")

st.markdown("<h2 style='color:#FFB300; font-weight:800;'>👑 전문가용 고급필터 (프리미엄)</h2>", unsafe_allow_html=True)
st.markdown("나만의 패턴을 직접 수정하고 저장하여 언제든 불러올 수 있습니다.")
st.markdown("---")

# ==========================================
# 1. 상단: 툴팁(?)이 적용된 기본필터 세팅 영역
# ==========================================
st.markdown("#### 1. 기본필터 직관적 세팅")

# 레이아웃을 3단 분할하여 공간 활용
col1, col2, col3 = st.columns(3)

with col1:
    # help="" 안에 설명을 넣으면 라벨 옆에 '?' 아이콘이 자동 생성됩니다.
    st.selectbox("홀짝 비율", ["선택", "6:0", "5:1", "4:2", "3:3", "2:4", "1:5", "0:6"], 
                 help="홀수와 짝수의 출현 비율입니다. (예: 3:3은 홀수 3개, 짝수 3개)")
    st.selectbox("저고 비율", ["선택", "6:0", "5:1", "4:2", "3:3", "2:4", "1:5", "0:6"], 
                 help="저(1~22)와 고(23~45)의 출현 비율입니다.")

with col2:
    st.slider("당첨번호 총합 구간", min_value=15, max_value=255, value=(70, 205), 
              help="당첨번호 6개를 모두 더한 값의 최소/최대 구간을 마우스로 드래그하여 설정합니다.")

with col3:
    st.multiselect("볼 색상 수 (체크박스 대체)", ["1색", "2색", "3색", "4색", "5색(모두)"], 
                   help="출현할 로또 공의 색상 종류 개수를 지정합니다. (예: 3색은 3가지 색상만 나옴)")

# ==========================================
# 2. 중단: 나만의 필터 (데이터 에디터)
# ==========================================
st.markdown("<br><br>", unsafe_allow_html=True)
st.markdown("#### 2. 나만의 패턴 직접 수정 (엑셀 연동 대기중)")
st.info("💡 엑셀을 업로드하거나, 아래 표의 빈칸을 더블클릭하여 숫자를 직접 수정할 수 있습니다.")

# 전문가들이 다룰 초기 더미 데이터 세팅
df_premium = pd.DataFrame({
    "그룹명": ["소수", "3배수", "쌍둥이수", "이월수"],
    "고정수": ["", "", "", ""],
    "번호입력(앞,뒤 콤마 필수)": [
        ",2,3,5,7,11,13,17,19,23,29,31,37,41,43,", 
        ",3,6,9,12,15,18,21,24,27,30,33,36,39,42,45,", 
        ",11,22,33,44,", 
        "" # 이월수는 회차마다 다르므로 비워둠
    ],
    "최소": [0, 0, 0, 0],
    "최대": [4, 4, 1, 2]
})

# num_rows="dynamic" 옵션으로 행 추가/삭제까지 가능하게 함
edited_df = st.data_editor(df_premium, num_rows="dynamic", use_container_width=True, hide_index=True)

# ==========================================
# 3. 하단: 조합 제어 및 로컬 저장/불러오기 영역
# ==========================================
st.markdown("---")
st.markdown("#### 3. 세팅 보존 및 조합 실행")

col_save, col_load, col_target, col_start = st.columns([1.5, 1.5, 1, 1.5])

with col_save:
    st.button("💾 이 화면 세팅을 내 PC에 파일로 저장")
with col_load:
    st.button("📂 내 PC에서 저장된 세팅 불러오기")
with col_target:
    st.number_input("희망 추출 수량", min_value=1, max_value=10000, value=100, step=10, 
                    help="엔진이 조건에 맞는 조합 중 몇 개를 최종적으로 뽑아낼지 결정합니다.")
with col_start:
    st.button("🚀 나만의 고급 조합 엔진 가동", type="primary")