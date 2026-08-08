# 로또신령 타로 위로 - 데이터 패키지

## 폴더 구성
```
tarot_package/
├── tarot_data.py      # SUBCATEGORIES(30) + CARDS(78) 전체 콘텐츠 + draw_card() 함수
├── tarot_page.py       # 카드 오픈 페이지 전체 (카테고리→소분류→뽑기→손편지 결과화면)
├── images/             # 카드 이미지 78장 (key.jpg, 1086×1810px)
└── README.md
```

## Cursor 프로젝트에 적용하는 법

### 방법 A: 독립 페이지로 바로 테스트
```
pip install streamlit
streamlit run tarot_page.py
```
카테고리 선택 → 소분류 선택 → 카드 뽑기 → 손편지 스타일 결과까지 전체 플로우가 바로 동작해요.

### 방법 B: 기존 로또신령 앱에 통합
1. `tarot_data.py`, `tarot_page.py`, `images/` 폴더를 기존 Streamlit 프로젝트에 그대로 복사
2. 메인 앱에서 버튼 클릭 시 호출:
   ```python
   import tarot_page

   if st.session_state.get("show_tarot"):
       tarot_page.render()
   ```
3. "오늘의 타로 한 장" 버튼 클릭 시 `st.session_state["show_tarot"] = True` 로 전환하는 로직만 기존 메인 화면에 추가하면 돼요.

### tarot_data.py만 따로 쓰고 싶을 때
```python
from tarot_data import draw_card, get_subcategory_intro, SUBCATEGORIES

key, card = draw_card()          # 78장 중 완전 무작위
intro_text = get_subcategory_intro("번아웃 / 무기력", "아무것도 하기 싫음")
```

## 이미지 출처 및 라이선스
- 덱: Rider-Waite-Smith (Pamela Colman Smith, 1909)
- 원본: 미국 내 퍼블릭 도메인 (저작권 만료, Wikimedia Commons에도 "Public Domain Mark"로 등록됨)
- 이번 파일: 1086×1810px (이전 350×600px 대비 약 3배 해상도), [mixvlad/TarotCards](https://github.com/mixvlad/TarotCards) 저장소의 `full/` 폴더에서 확보
- **라이선스 참고**: 이 저장소 자체는 CC BY-NC 4.0(비상업적 이용)로 표기돼 있지만, 라이선스 본문에 "퍼블릭 도메인 요소에는 이 라이선스가 적용되지 않는다"는 조항이 명시돼 있어요. RWS 카드 이미지 자체는 저장소 문서(SOURCES.md)에서도 별도로 "Public Domain"이라 밝히고 있어서, 카드 이미지 자체를 상업적으로 쓰는 데는 문제없다고 판단했어요.
- **그래도 더 확실히 하고 싶으시면**: Wikimedia Commons 원본(예: `upload.wikimedia.org/wikipedia/commons/f/ff/RWS_Tarot_21_World.jpg`, PD 마크 명시)에서 직접 재다운로드하는 게 가장 깔끔해요. 지금 작업 환경에서는 해당 도메인 접근이 막혀 있어 제가 직접 받아오지 못했어요 — Cursor 등 일반 인터넷 접근이 되는 환경에서 스크립트로 재다운로드하시면 됩니다.

## 카드 뽑기 로직 (중요)
- `draw_card()`는 **카테고리/소분류와 무관하게 78장 전체에서 완전 무작위**로 뽑아요.
- 카테고리별로 어울리는 카드만 추려서 뽑는 방식은 **의도적으로 배제**했어요 (요청사항 반영).

## 데이터 구조 참고
- `SUBCATEGORIES[카테고리명][소분류명]` → 도입부 문자열
- `CARDS[카드키]` → `{name_en, name_kr, arcana, suit, image, intro, state, comfort, hope}`
- 카드 키 규칙: 메이저 `major_00`~`major_21`, 마이너 `완드/컵/소드/펜타클_숫자또는코트` (예: `wands_ace`, `cups_queen`, `pentacles_10`)
