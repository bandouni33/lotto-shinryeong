"""스토어 스크린샷 합성(2026-10-15). 크롬 기기 모드 440x956 DPR3 캡처(1320x2868) → 위 문구 + 화면.
출력: 애플 1320x2868(6.9"), 구글 1080x1920. 화면 아래쪽(Streamlit 사이트 표시 왕관·프로필)은 잘라낸다.
python scratch/store_screens.py <원본.png> <출력이름> "<큰 문구>" "<작은 문구>" [crop_bottom_px]"""
import sys
from pathlib import Path
from PIL import Image, ImageDraw
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from weekly_content.cards import font, GOLD, WHITE, MUTED, BG_TOP, BG_BOTTOM


def bg(w, h):
    im = Image.new("RGB", (w, h))
    d = ImageDraw.Draw(im)
    for y in range(h):
        t = y / h
        d.line([(0, y), (w, y)], fill=tuple(int(a + (b - a) * t) for a, b in zip(BG_TOP, BG_BOTTOM)))
    return im


def compose(raw, w, h, title, sub, crop_bottom, band, title_px, sub_px):
    im = bg(w, h)
    d = ImageDraw.Draw(im)
    ft, fs = font(title_px, "Black"), font(sub_px, "Medium")
    while d.textlength(title, font=ft) > w * 0.9 and title_px > 40:  # 긴 문구는 폭에 맞게 줄인다
        title_px -= 2
        ft = font(title_px, "Black")
    d.text(((w - d.textlength(title, font=ft)) / 2, band * 0.30), title, font=ft, fill=GOLD)
    d.text(((w - d.textlength(sub, font=fs)) / 2, band * 0.30 + title_px * 1.45), sub, font=fs, fill=MUTED)
    shot = raw.crop((0, 0, raw.width, crop_bottom))
    avail_h = h - band
    scale = min((w * 0.86) / shot.width, avail_h / shot.height)
    shot = shot.resize((int(shot.width * scale), int(shot.height * scale)), Image.LANCZOS)
    r = int(48 * w / 1320)
    mask = Image.new("L", shot.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, *shot.size), r, fill=255)
    x = (w - shot.width) // 2
    # 위만 둥글게, 아래는 화면 끝에서 잘린 듯 보이게
    ImageDraw.Draw(mask).rectangle((0, shot.height - r, shot.width, shot.height), fill=255)
    im.paste(shot, (x, h - shot.height), mask)
    return im


if __name__ == "__main__":
    src, name, title, sub = sys.argv[1:5]
    crop = int(sys.argv[5]) if len(sys.argv) > 5 else 2650
    raw = Image.open(src).convert("RGB")
    out = Path(sys.argv[6] if len(sys.argv) > 6 else "store_out")
    out.mkdir(parents=True, exist_ok=True)
    compose(raw, 1320, 2868, title, sub, crop, 560, 92, 54).save(out / f"apple_{name}.png")
    compose(raw, 1080, 1920, title, sub, crop, 360, 66, 38).save(out / f"google_{name}.png")
    print("ok", out)
