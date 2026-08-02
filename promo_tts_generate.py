"""로또신령 홍보 대본 → 여성 나레이션 MP3 생성 (edge-tts)."""

import asyncio
from pathlib import Path

import edge_tts

SCRIPT = """
매주 토요일,
우리는 같은 숫자 앞에 서 있죠.
하지만 선택은…… 우연이 아닐 수도 있어요.

로또신령은 당첨의 기록을 읽고,
당신의 마음을 번호로 옮겨 줍니다.

빼고 싶은 숫자, 꼭 담고 싶은 숫자,
사랑하는 사람의 생일에서 피어난 행운까지,
번개조합은 당신의 감각을, 조합으로 바꿔요.

통계센터에서는 숨 쉬지 않던 숫자의 흐름을 한눈에 볼 수 있고,
고급필터는 수많은 가능성 속에서
오직 당신의 기준만 남겨 줍니다.
마치 밤하늘에서 자신의 별자리를 고르듯.

자동구매는 엄선된 조합을 회차마다 조용히 전해 드립니다.
기다림 대신, 확신.
문자 대신, 지금 이 화면,
당신의 구매 내역에 번호가 머물러요.

운을 믿기 전에, 데이터를 믿어보세요.
감으로 고르기 전에, 기준을 세워보세요.

로또신령,
당신의 선택에, 신령이 깃듭니다.
""".strip()

VOICE = "ko-KR-SunHiNeural"  # 한국어 여성
OUTPUT = Path(__file__).resolve().parent / "promo_lotto_shinryeong_female.mp3"


async def main() -> None:
    communicate = edge_tts.Communicate(
        SCRIPT,
        VOICE,
        rate="-8%",
        pitch="+2Hz",
    )
    await communicate.save(str(OUTPUT))
    print(f"Saved: {OUTPUT}")


if __name__ == "__main__":
    asyncio.run(main())
