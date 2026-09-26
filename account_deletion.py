"""계정 삭제(회원 탈퇴) — **단일 실행점** (2026-09-27 신규).

왜 한 곳인가
  탈퇴는 여러 DB 모듈에 걸친 파기다(wallet_db·marketing_db·birthday_db·feedback_db).
  화면이나 관리자 페이지가 각 DB를 직접 부르면 **한 곳만 빠져도** "탈퇴했는데 생일과
  주문 연락처는 남아있는" 상태가 조용히 생긴다(그리고 그게 개인정보 미파기다). 그래서
  순서와 대상 목록은 이 파일 한 곳이 전담하고, **각 테이블의 SQL은 그 테이블 주인
  모듈에만** 둔다(기준점 원칙 — AGENTS.md §1).

지우는 것 / 남기는 것의 경계
  · 지운다(즉시 파기): 신원(oauth_hash)·기기 연결·생일·기기 스코프 사용자 데이터
    (구매내역·저장 조합·타로 뽑기)·주문 연락처·결제 고객키·개선 의견·미정산 대기행
  · 남긴다(법정 보관): 적립금 ledger·결제 승인 기록·약관/동의 기록·구독 이력
    — 전자상거래법 제6조(계약·대금결제 기록 5년). 이 행들은 위 신원 파기 후
    익명화된 members 행에만 이어져 있어 개인을 특정할 수 없다.

  이 목록은 DELETED_ITEMS / RETAINED_ITEMS에 있고, 화면·약관 문구(legal_notices의
  ACCOUNT_DELETION_BODY)와 서로 어긋나면 tests/test_account_deletion.py가 실패시킨다.

Google Play "계정 삭제" 요구사항 대응
  ① 앱 내 경로: 메인 [내정보] → [회원 탈퇴](wallet_ui._delete_account_dialog)
  ② 웹 URL: app.py?page=delete_account (user_page의 공개 페이지 — 비로그인으로 열린다)
  ③ Play Console Data safety에 ②의 URL을 신고해야 한다(콘솔 작업 — 코드 아님).
"""

from __future__ import annotations

import wallet_db
from user_scope import birthday_scope_for

# 탈퇴 시 **즉시 파기**되는 항목(문구와 대조됨 — 목록을 고치면 legal_notices의
# ACCOUNT_DELETION_BODY도 같이 고쳐야 한다).
DELETED_ITEMS = (
    "로그인 식별자",       # members.oauth_hash (간편인증 provider + 식별자 해시)
    "기기 연결",           # guest_member_links (자동 로그인 연결)
    "생일",                # birthday_db.userBirthdays (m_<member_id> 스코프)
    "번호 조합",           # marketing_db.guest_generated_combos (저장내역)
    "타로",                # marketing_db.guest_tarot_draws
    "연락처",              # wallet_db.auto_orders.phone
    "결제 고객 식별키",     # wallet_db.wallets.toss_customer_key
    "개선 의견",           # feedback_db.improvement_feedback
)

# **법정 보관**으로 남기는 항목(신원 파기 후 익명 상태로 보관).
RETAINED_ITEMS = (
    "적립금 충전·차감·지급 기록",   # wallet_db.wallet_ledger
    "결제 승인 기록",               # wallet_db.pg_charges (confirmed)
    "약관·동의 기록",               # wallet_db.consent_log
)

# 보관 이유(전자상거래법 제6조 — 계약·대금결제 기록 5년). 화면 문구와 대조된다.
RETAINED_REASON = "전자상거래법 제6조(계약·대금결제 기록 5년)"


def delete_account(member_id: int) -> dict:
    """회원 한 명의 계정을 삭제한다 — 반환: 단계별 처리 건수 요약.

    순서가 중요하다:
      1) 이 회원에 묶인 guest_id 목록을 **먼저** 모은다 — 다음 단계에서
         guest_member_links가 지워지면 어느 기기의 데이터를 지워야 하는지 알 수 없다.
      2) 기기 스코프 사용자 데이터(구매내역·저장 조합·타로 뽑기·업데이트 배너 확인)
      3) 생일 슬롯 / 개선 의견 / 로그인 재개 의도
      4) 신원·기기 연결·연락처 파기 + 미정산 대기행 제거(보관 증빙은 유지)

    여러 번 불러도 안전하다(멱등) — 두 번째 호출은 지울 것이 없어 0건을 돌려준다.
    """
    mid = int(member_id)
    summary: dict[str, int] = {"member_id": mid}

    # 1) 기기(guest_id) 목록 수집
    try:
        guest_ids = [str(gid) for gid in wallet_db.get_guest_ids_for_member(mid) if gid]
    except Exception:
        guest_ids = []
    summary["guest_ids"] = len(guest_ids)

    # 2) 기기 스코프 사용자 데이터
    import marketing_db

    summary["guest_data"] = sum(marketing_db.delete_guest_data(gid) for gid in guest_ids)

    # 3) 생일 슬롯 / 개선 의견 / 남아있는 로그인 재개 의도
    import birthday_db
    import feedback_db

    summary["birthdays"] = int(birthday_db.delete_all_birthdays(birthday_scope_for(mid)))
    summary["feedback"] = int(feedback_db.delete_member_feedback(mid))

    import auth_providers

    for gid in guest_ids:
        auth_providers.forget_pending_resume_for(gid)

    # 4) 신원·연결·연락처 파기(+ 보관 증빙은 그대로)
    summary.update(wallet_db.anonymize_member_account(mid))
    return summary
