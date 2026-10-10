"""자동조합 '조합시작' 신령 이미지 연출용 영역 가림막(mask) 생성 — 2026-10-10.

로또신령2.jpg 를 영역별(나무·건물·땅·폭포 등)로 나눈 부드러운 가림막 PNG(흰색 + 알파)를 만든다.
page_auto._SPIRIT2_QUAKE_LAYERS 가 이 파일 이름을 쓴다. 영역은 원본 그림 기준 백분율 다각형이다.
인물 오려내기(로또신령2_인물.webp)와 배경판(로또신령2_배경.jpg)은 rembg(isnet)·OpenCV inpaint 로 만들었다.

실행: python scripts/make_spirit2_layers.py  → spirit2_layers/*.png
"""
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "spirit2_layers"
SIZE = 256
FEATHER = 9  # 가장자리 흐림(픽셀, SIZE 기준)

# 이름 → [다각형(백분율 x,y 목록), ...]
REGIONS = {
    # 왼쪽 먼 봉우리·산등성이(땅 — 살짝)
    "mtn_left": [[(0, 26), (8, 25), (14, 27), (22, 27), (30, 31), (32, 40), (26, 43), (10, 41), (0, 40)]],
    # 오른쪽 먼 산줄기·계곡(땅 — 살짝)
    "mtn_right": [[(56, 31), (70, 30), (82, 29), (100, 30), (100, 42), (90, 46), (75, 44), (58, 42)]],
    # 왼쪽 누각(건물 — 살짝)
    "building": [[(0, 43), (10, 42), (24, 47), (22, 53), (19, 56), (19, 66), (8, 66), (0, 63)]],
    # 누각 뒤·옆 숲(나무 — 바람)
    "trees_left": [[(0, 35), (12, 36), (28, 40), (32, 50), (30, 64), (22, 70), (18, 60), (22, 52), (20, 46), (10, 42), (0, 42)]],
    # 왼쪽 아래 꽃가지(나무 — 바람 크게)
    "flowers_left": [[(0, 63), (8, 64), (14, 70), (16, 80), (13, 88), (6, 92), (0, 92)]],
    # 오른쪽 가운데 숲(나무 — 바람)
    "trees_right": [[(58, 42), (72, 43), (86, 44), (90, 50), (88, 62), (80, 70), (72, 66), (66, 56), (60, 50)]],
    # 오른쪽 절벽·폭포(땅 — 살짝)
    "cliff_right": [[(88, 42), (96, 40), (100, 41), (100, 70), (94, 72), (90, 84), (86, 80), (88, 66), (86, 54)]],
    # 오른쪽 아래 나무·꽃(나무 — 바람 크게)
    "trees_right_low": [[(82, 68), (92, 70), (100, 70), (100, 92), (90, 92), (84, 86)]],
    # 아래 돌 난간(땅 — 살짝)
    "rail": [[(0, 92), (100, 92), (100, 100), (0, 100)]],
}


def main() -> None:
    OUT.mkdir(exist_ok=True)
    for name, polys in REGIONS.items():
        m = np.zeros((SIZE, SIZE), np.uint8)
        for poly in polys:
            pts = np.array([[x / 100 * SIZE, y / 100 * SIZE] for x, y in poly], np.int32)
            cv2.fillPoly(m, [pts], 255)
        m = cv2.GaussianBlur(m, (0, 0), FEATHER / 2)
        rgba = np.dstack([np.full_like(m, 255)] * 3 + [m])
        cv2.imwrite(str(OUT / f"{name}.png"), rgba, [cv2.IMWRITE_PNG_COMPRESSION, 9])
        print(name, (OUT / f"{name}.png").stat().st_size)


if __name__ == "__main__":
    main()
