"""인트로 구간 나레이션 — 힘 있고 밝은 여성톤."""

import asyncio
from pathlib import Path

import edge_tts

# 연출: 아이콘 등장 후 메인화면이 떠오를 때
SCRIPT = "로또신령. 당신의 번호, 지금 시작됩니다."

VOICE = "ko-KR-SunHiNeural"
OUTPUT = Path(__file__).resolve().parent / "promo_intro_energetic_female.mp3"


async def main() -> None:
    communicate = edge_tts.Communicate(
        SCRIPT,
        VOICE,
        rate="+8%",
        pitch="+6Hz",
    )
    await communicate.save(str(OUTPUT))
    print(f"Saved: {OUTPUT}")


if __name__ == "__main__":
    asyncio.run(main())
