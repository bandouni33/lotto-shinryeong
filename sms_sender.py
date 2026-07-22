"""알리고(Aligo) SMS 발송 — API 키 없으면 테스트 모드(큐 TEST_SKIP + 로그)."""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any

import requests

from env_loader import load_dotenv_file
from marketing_db import enqueue_sms

load_dotenv_file()

logger = logging.getLogger(__name__)

ALIGO_SEND_URL = "https://apis.aligo.in/send/"
ALIGO_SUCCESS_CODE = "1"


def _env(name: str) -> str:
    return (os.getenv(name) or "").strip()


def is_aligo_configured() -> bool:
    """ALIGO_API_KEY, ALIGO_USER_ID, ALIGO_SENDER 모두 설정됐는지."""
    return bool(_env("ALIGO_API_KEY") and _env("ALIGO_USER_ID") and _env("ALIGO_SENDER"))


def normalize_phone(phone: str) -> str:
    """수신번호 — 숫자만 (알리고 receiver 형식)."""
    return re.sub(r"\D", "", str(phone).strip())


def build_purchase_sms_message(
    draw_round: int,
    purchase_type: str,
    allocated: list[dict],
) -> str:
    """배정된 조합으로 SMS 본문 생성."""
    lines = [f"[로또신령] {purchase_type} · {int(draw_round)}회차"]
    for idx, item in enumerate(allocated, start=1):
        combo = item.get("combo") or []
        nums = " ".join(f"{n:02d}" for n in combo)
        lines.append(f"{idx}. {nums}")
    lines.append("당첨을 보장하지 않는 참고용 번호입니다.")
    return "\n".join(lines)


def send_sms_via_aligo(receiver: str, message: str, *, msg_type: str = "LMS") -> dict[str, Any]:
    """
    알리고 문자 발송 API (POST https://apis.aligo.in/send/).

    Returns:
        {"ok": bool, "result_code": str|None, "message": str, "raw": dict|None, "error": str|None}
    """
    api_key = _env("ALIGO_API_KEY")
    user_id = _env("ALIGO_USER_ID")
    sender = _env("ALIGO_SENDER")
    recv = normalize_phone(receiver)
    body = str(message).strip()

    if not (api_key and user_id and sender):
        return {
            "ok": False,
            "result_code": None,
            "message": "missing_credentials",
            "raw": None,
            "error": "ALIGO_API_KEY / ALIGO_USER_ID / ALIGO_SENDER 미설정",
        }
    if not recv:
        return {
            "ok": False,
            "result_code": None,
            "message": "invalid_receiver",
            "raw": None,
            "error": "수신번호가 비어 있습니다.",
        }
    if not body:
        return {
            "ok": False,
            "result_code": None,
            "message": "empty_message",
            "raw": None,
            "error": "메시지 본문이 비어 있습니다.",
        }

    payload = {
        "key": api_key,
        "user_id": user_id,
        "sender": sender,
        "receiver": recv,
        "msg": body,
        "msg_type": msg_type,
    }

    try:
        resp = requests.post(ALIGO_SEND_URL, data=payload, timeout=20)
        resp.raise_for_status()
    except requests.RequestException as exc:
        logger.exception("Aligo SMS HTTP 오류: %s", exc)
        return {
            "ok": False,
            "result_code": None,
            "message": "http_error",
            "raw": None,
            "error": str(exc),
        }

    try:
        raw = resp.json()
    except json.JSONDecodeError:
        logger.error("Aligo SMS JSON 파싱 실패: %s", resp.text[:500])
        return {
            "ok": False,
            "result_code": None,
            "message": "invalid_json",
            "raw": None,
            "error": resp.text[:200],
        }

    result_code = str(raw.get("result_code", ""))
    ok = result_code == ALIGO_SUCCESS_CODE
    if not ok:
        logger.warning("Aligo SMS 실패: %s", raw)
    return {
        "ok": ok,
        "result_code": result_code,
        "message": str(raw.get("message", "")),
        "raw": raw,
        "error": None if ok else str(raw.get("message") or raw),
    }


def dispatch_purchase_sms(phone: str, purchase_type: str, message: str) -> int:
    """
    구매 확정 SMS: 알리고 설정 시 실발송+SENT, 미설정 시 시뮬레이션+TEST_SKIP.
    실패 시 WAIT 큐 등록.
    """
    phone = str(phone).strip()
    purchase_type = str(purchase_type).strip()
    message = str(message).strip()

    if not is_aligo_configured():
        sim_line = f"[테스트 모드] SMS 발송 시뮬레이션: {phone}로 발송 예정"
        print(sim_line, flush=True)
        logger.info("%s | type=%s | msg_preview=%s", sim_line, purchase_type, message[:120])
        return enqueue_sms(phone, purchase_type, "TEST_SKIP")

    result = send_sms_via_aligo(phone, message)
    if result.get("ok"):
        logger.info(
            "Aligo SMS 발송 성공 phone=%s result_code=%s msg_id=%s",
            phone,
            result.get("result_code"),
            (result.get("raw") or {}).get("msg_id"),
        )
        return enqueue_sms(phone, purchase_type, "SENT")

    logger.error("Aligo SMS 발송 실패 phone=%s error=%s", phone, result.get("error"))
    return enqueue_sms(phone, purchase_type, "WAIT")
