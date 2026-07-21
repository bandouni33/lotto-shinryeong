"""프로젝트 루트 .env 로드 (Streamlit 진입 전 1회 호출)."""

from __future__ import annotations

from pathlib import Path


def load_dotenv_file() -> None:
    env_path = Path(__file__).resolve().parent / ".env"
    if not env_path.is_file():
        return
    try:
        from dotenv import load_dotenv

        load_dotenv(env_path, override=False)
    except ImportError:
        pass
