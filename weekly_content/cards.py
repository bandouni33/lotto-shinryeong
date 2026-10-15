# -*- coding: utf-8 -*-
"""로또신령 주간 리포트 카드(5장, 1080x1350) — 2026-10-12 샘플 단계(사용자 승인 컨셉).

  1 표지: N회 당첨번호 + 보너스 (볼 색은 ball_style 단일 기준점)
  2 숫자 분석: 홀짝·저고·합계·연번·구간 분포, 최근 10회 많이 나온 번호 / 오래 안 나온 번호
  3 필터 결과: 앱 자동조합 화면 '회차별 당첨번호 배출' 표와 같은 값(combo_round_stats — 필터 통과
    조합 기준 참고등수, 나쁜 주도 그대로). '실제 이용자 당첨'으로 표현하지 않는다. 값이 없으면 '동행복권 집계중'만(2026-10-15 사용자 지시 — 부제 '필터 통과 조합 기준 참고 집계' 쓰지 않음).
  4 다음 회 재미 요소: 회차로 정해지는 타로 한 장(메이저 22장, 퍼블릭 도메인 RWS) + 한 줄 + 500P 체험
  5 마무리: 설치 안내 + '참고·재미용, 당첨 보장 없음 / 복권은 만 19세 이상'

금지: 예측·보장·확률 상승 표현. 숫자는 전부 당첨 이력에서 계산한 실제 값만 쓴다.
실행(샘플): python -m weekly_content.cards <전체당첨내역 xlsx> <회차> <출력폴더>
"""
from __future__ import annotations

import random
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import ball_style  # noqa: E402

W, H = 1080, 1350
BG_TOP, BG_BOTTOM = (18, 24, 43), (38, 30, 70)
GOLD = (233, 196, 106)
WHITE = (245, 245, 250)
MUTED = (170, 175, 200)
CARD_BG = (255, 255, 255, 18)
_FONT_DIR = Path("/usr/share/fonts/opentype/noto")
_BUNDLED = ROOT / "weekly_content" / "fonts"
BLOG_URL = "https://blog.naver.com/bandouni"
PENDING_TEXT = "동행복권 집계중"
DISCLAIMER = "참고·재미용 정보이며 당첨을 보장하지 않습니다 · 복권은 만 19세 이상"
SPIRIT_IMG = ROOT / "아이콘815.png"
TAROT_DIR = ROOT / "tarot"


def font(size: int, weight: str = "Bold") -> ImageFont.FreeTypeFont:
    for path in (_BUNDLED / f"NotoSansKR-{weight}.otf", _FONT_DIR / f"NotoSansCJK-{weight}.ttc"):
        if path.exists():
            return ImageFont.truetype(str(path), size, index=1 if path.suffix == ".ttc" else 0)
    raise FileNotFoundError("한글 글꼴을 찾지 못했습니다(weekly_content/fonts 에 Noto Sans KR 필요)")


def _hex(c: str) -> tuple[int, int, int]:
    c = c.lstrip("#")
    return tuple(int(c[i:i + 2], 16) for i in (0, 2, 4))


def _canvas() -> Image.Image:
    im = Image.new("RGB", (W, H))
    d = ImageDraw.Draw(im)
    for y in range(H):
        t = y / (H - 1)
        d.line([(0, y), (W, y)], fill=tuple(int(a + (b - a) * t) for a, b in zip(BG_TOP, BG_BOTTOM)))
    return im


def _center(d, y, text, f, fill=WHITE):
    w = d.textlength(text, font=f)
    d.text(((W - w) / 2, y), text, font=f, fill=fill)


def _ball(im, cx, cy, r, n):
    stops = [_hex(c) for c in ball_style.ball_stops(n)]
    layer = Image.new("RGBA", (r * 2, r * 2), (0, 0, 0, 0))
    ld = ImageDraw.Draw(layer)
    for i in range(r, 0, -1):                     # 바깥 → 안쪽으로 밝아지는 원형 그라디언트
        t = i / r
        a, b = (stops[2], stops[1]) if t > 0.5 else (stops[1], stops[0])
        k = (t - 0.5) * 2 if t > 0.5 else t * 2
        col = tuple(int(b[j] + (a[j] - b[j]) * k) for j in range(3))
        off = int((1 - t) * r * 0.35)
        ld.ellipse([r - i - off, r - i - off, r + i - off, r + i - off], fill=col + (255,))
    mask = Image.new("L", (r * 2, r * 2), 0)
    ImageDraw.Draw(mask).ellipse([0, 0, r * 2 - 1, r * 2 - 1], fill=255)
    im.paste(layer, (cx - r, cy - r), mask)
    d = ImageDraw.Draw(im)
    f = font(int(r * 0.9), "Black")
    s = str(n)
    tw = d.textlength(s, font=f)
    bbox = f.getbbox(s)
    d.text((cx - tw / 2, cy - (bbox[1] + bbox[3]) / 2), s, font=f, fill=_hex(ball_style.ball_text_color(n)))


def _panel(im, box, radius=28):
    ov = Image.new("RGBA", im.size, (0, 0, 0, 0))
    ImageDraw.Draw(ov).rounded_rectangle(box, radius, fill=CARD_BG, outline=(255, 255, 255, 40), width=2)
    im.paste(Image.alpha_composite(im.convert("RGBA"), ov).convert("RGB"))


def _footer(im, page):
    d = ImageDraw.Draw(im)
    _center(d, H - 70, DISCLAIMER, font(24, "Regular"), MUTED)
    d.text((W - 110, 40), f"{page}/5", font=font(28, "Medium"), fill=MUTED)
    d.text((48, 40), "로또신령 주간 리포트", font=font(28, "Bold"), fill=GOLD)


# ── 숫자 계산(이력에서만) ─────────────────────────────────────────────
def analyze(draws: dict[int, dict], rnd: int) -> dict:
    nums = sorted(draws[rnd]["nums"])
    odd = sum(n % 2 for n in nums)
    low = sum(1 for n in nums if n <= 22)
    runs = sum(1 for a, b in zip(nums, nums[1:]) if b == a + 1)
    bands = [sum(1 for n in nums if lo <= n <= hi) for lo, hi in ((1, 10), (11, 20), (21, 30), (31, 40), (41, 45))]
    recent = [r for r in sorted(draws) if rnd - 9 <= r <= rnd]
    cnt = {n: sum(1 for r in recent if n in draws[r]["nums"]) for n in range(1, 46)}
    hot = sorted(range(1, 46), key=lambda n: (-cnt[n], n))[:5]
    last_seen = {}
    for r in sorted(draws):
        if r > rnd:
            break
        for n in draws[r]["nums"]:
            last_seen[n] = r
    cold = sorted(range(1, 46), key=lambda n: (last_seen.get(n, 0), n))[:5]
    return {"nums": nums, "bonus": draws[rnd]["bonus"], "odd": odd, "even": 6 - odd, "low": low,
            "high": 6 - low, "sum": sum(nums), "runs": runs, "bands": bands,
            "hot": [(n, cnt[n]) for n in hot], "cold": [(n, rnd - last_seen.get(n, 0)) for n in cold]}


def tarot_for_round(rnd: int) -> dict:
    sys.path.insert(0, str(TAROT_DIR))
    from tarot_data import CARDS  # noqa: E402

    # 노출이 있는 그림(연인·별·태양·심판·세계)과 분위기가 무거운 카드(매달린 사람·죽음·악마·탑)는 뺀다 —
    # SNS 자동 검수에 걸리거나 '이번 주 운' 느낌과 안 맞는다.
    skip = {"major_06", "major_12", "major_13", "major_15", "major_16", "major_17", "major_19", "major_20", "major_21"}
    majors = sorted(k for k in CARDS if k.startswith("major_") and k not in skip)
    key = random.Random(f"lotto-shinryeong-weekly-{rnd}").choice(majors)
    c = CARDS[key]
    return {"key": key, "name": c["name_kr"], "name_en": c["name_en"], "line": c["acceptance"],
            "image": TAROT_DIR / c["image"]}


# ── 카드 5장 ─────────────────────────────────────────────────────────
def card1(a, rnd, date_text):
    im = _canvas()
    sp = Image.open(SPIRIT_IMG).convert("RGB")
    sp = sp.resize((W, int(sp.height * W / sp.width)))
    sp = sp.crop((0, 0, W, 760))
    fade = Image.new("L", (W, 760), 255)
    fd = ImageDraw.Draw(fade)
    for y in range(460, 760):
        fd.line([(0, y), (W, y)], fill=int(255 * (760 - y) / 300))
    im.paste(sp, (0, 0), fade)
    top = Image.new("RGBA", (W, 140), (0, 0, 0, 0))          # 머리글 글자가 하늘 위에서도 보이게
    td = ImageDraw.Draw(top)
    for y in range(140):
        td.line([(0, y), (W, y)], fill=(18, 24, 43, int(200 * (1 - y / 140))))
    im.paste(top, (0, 0), top)
    d = ImageDraw.Draw(im)
    _center(d, 640, f"제 {rnd}회", font(84, "Black"), GOLD)
    _center(d, 745, f"당첨번호  ·  {date_text}", font(36, "Medium"), WHITE)
    r, gap = 56, 14
    total = 6 * 2 * r + 5 * gap + 70 + 2 * r
    x = (W - total) // 2 + r
    for n in a["nums"]:
        _ball(im, x, 900, r, n)
        x += 2 * r + gap
    d.text((x - r + 8, 868), "+", font=font(60, "Black"), fill=WHITE)
    _ball(im, x + 70, 900, r, a["bonus"])
    _center(d, 990, "보너스", font(26, "Medium"), MUTED) if False else None
    d.text((x + 70 - d.textlength("보너스", font=font(26, "Medium")) / 2, 975), "보너스",
           font=font(26, "Medium"), fill=MUTED)
    _center(d, 1080, "이번 주 숫자, 한 장씩 넘겨 보세요 →", font(34, "Medium"), WHITE)
    _footer(im, 1)
    return im


def card2(a, rnd):
    im = _canvas()
    d = ImageDraw.Draw(im)
    _center(d, 120, f"{rnd}회 숫자 분석", font(64, "Black"), GOLD)
    _panel(im, (60, 230, W - 60, 640))
    d = ImageDraw.Draw(im)
    rows = [("홀 : 짝", f"{a['odd']} : {a['even']}"), ("저(1~22) : 고(23~45)", f"{a['low']} : {a['high']}"),
            ("번호 합계", f"{a['sum']}"), ("연속번호", f"{a['runs']}쌍" if a["runs"] else "없음")]
    y = 265
    for k, v in rows:
        d.text((110, y), k, font=font(38, "Medium"), fill=MUTED)
        d.text((W - 110 - d.textlength(v, font=font(44, "Bold")), y - 4), v, font=font(44, "Bold"), fill=WHITE)
        y += 92
    labels = ["1~10", "11~20", "21~30", "31~40", "41~45"]
    reps = [5, 15, 25, 35, 43]
    bx, by, bw = 110, 700, 150
    d.text((110, 660 - 4), "구간 분포", font=font(32, "Medium"), fill=MUTED)
    for i, c in enumerate(a["bands"]):
        x = bx + i * (bw + 20)
        col = _hex(ball_style.ball_color(reps[i]))
        h = 30 + c * 55
        d.rounded_rectangle([x, by + 230 - h, x + bw, by + 230], 14, fill=col)
        d.text((x + bw / 2 - d.textlength(str(c), font=font(40, "Black")) / 2, by + 230 - h - 52), str(c),
               font=font(40, "Black"), fill=WHITE)
        d.text((x + bw / 2 - d.textlength(labels[i], font=font(28, "Medium")) / 2, by + 245), labels[i],
               font=font(28, "Medium"), fill=MUTED)
    y = 1030
    d.text((110, y), "최근 10회 자주 나온 번호", font=font(30, "Medium"), fill=MUTED)
    x = 110
    for n, c in a["hot"]:
        _ball(im, x + 38, y + 95, 38, n)
        d = ImageDraw.Draw(im)
        d.text((x + 38 - d.textlength(f"{c}회", font=font(22, "Medium")) / 2, y + 140), f"{c}회",
               font=font(22, "Medium"), fill=MUTED)
        x += 92
    d.text((W / 2 + 40, y), "가장 오래 안 나온 번호", font=font(30, "Medium"), fill=MUTED)
    x = W / 2 + 40
    for n, g in a["cold"]:
        _ball(im, int(x + 38), y + 95, 38, n)
        d = ImageDraw.Draw(im)
        d.text((x + 38 - d.textlength(f"{g}회 쉼", font=font(22, "Medium")) / 2, y + 140), f"{g}회 쉼",
               font=font(22, "Medium"), fill=MUTED)
        x += 92
    _footer(im, 2)
    return im


def card3(rnd, app_result: dict | None):
    im = _canvas()
    d = ImageDraw.Draw(im)
    _center(d, 120, f"{rnd}회 로또신령 필터 결과", font(60, "Black"), GOLD)
    _center(d, 200, "앱 ‘회차별 당첨번호 배출’ 표와 같은 값이에요", font(32, "Medium"), MUTED)
    if app_result is None:   # 미확정: 등수 칸 없이 한 줄만(2026-10-15 사용자 지시)
        _center(d, 620, PENDING_TEXT, font(44, "Medium"), MUTED)
        _footer(im, 3)
        return im
    _panel(im, (60, 310, W - 60, 960))
    d = ImageDraw.Draw(im)
    tiers = [("1등", "t1"), ("2등", "t2"), ("3등", "t3"), ("4등", "t4"), ("5등", "t5")]
    y = 350
    for label, k in tiers:
        v = f"{int(app_result.get(k, 0)):,}개"
        d.text((130, y), label, font=font(48, "Bold"), fill=WHITE)
        f = font(48, "Black")
        d.text((W - 130 - d.textlength(v, font=f), y), v, font=f, fill=GOLD)
        y += 120
    _center(d, 1010, "결과가 좋든 나쁘든 매주 그대로 공개합니다", font(32, "Medium"), WHITE)
    _footer(im, 3)
    return im


def card4(rnd, tarot):
    im = _canvas()
    d = ImageDraw.Draw(im)
    _center(d, 110, f"{rnd + 1}회를 기다리며", font(60, "Black"), GOLD)
    _center(d, 200, "이번 주 신령의 타로 한 장", font(36, "Medium"), WHITE)
    card = Image.open(tarot["image"]).convert("RGB")
    ch = 600
    card = card.resize((int(card.width * ch / card.height), ch))
    shadow = Image.new("RGBA", (card.width + 40, ch + 40), (0, 0, 0, 0))
    ImageDraw.Draw(shadow).rounded_rectangle([20, 20, card.width + 20, ch + 20], 16, fill=(0, 0, 0, 160))
    shadow = shadow.filter(ImageFilter.GaussianBlur(14))
    x = (W - card.width) // 2
    im.paste(shadow, (x - 20, 270), shadow)
    im.paste(card, (x, 280))
    d = ImageDraw.Draw(im)
    _center(d, 905, f"{tarot['name']}  ·  {tarot['name_en']}", font(40, "Bold"), GOLD)
    line = tarot["line"]
    f = font(34, "Medium")
    words, lines, cur = line.split(" "), [], ""
    for w_ in words:
        if d.textlength((cur + " " + w_).strip(), font=f) > W - 200:
            lines.append(cur)
            cur = w_
        else:
            cur = (cur + " " + w_).strip()
    lines.append(cur)
    y = 975
    for ln in lines[:3]:
        _center(d, y, ln, f, WHITE)
        y += 50
    _center(d, 1150, "첫 가입 500P로 번호 조합을 무료로 체험해 보세요", font(32, "Bold"), GOLD)
    _footer(im, 4)
    return im


def card5(store_text):
    im = _canvas()
    sp = Image.open(SPIRIT_IMG).convert("RGB")
    icon = sp.crop((90, 120, 90 + 600, 120 + 600)).resize((300, 300))
    m = Image.new("L", (300, 300), 0)
    ImageDraw.Draw(m).rounded_rectangle([0, 0, 299, 299], 64, fill=255)
    im.paste(icon, ((W - 300) // 2, 230), m)
    d = ImageDraw.Draw(im)
    _center(d, 580, "로또신령", font(80, "Black"), GOLD)
    _center(d, 690, "번호 생성 · 당첨 통계 · 구매복권 QR · 타로", font(36, "Medium"), WHITE)
    _panel(im, (110, 790, W - 110, 990))
    d = ImageDraw.Draw(im)
    _center(d, 825, store_text, font(38, "Bold"), WHITE)
    _center(d, 895, "에서 ‘로또신령’ 검색", font(34, "Medium"), MUTED)
    _center(d, 1040, "자세한 사용법은 네이버 블로그 ‘로또신령’", font(32, "Medium"), WHITE)
    _center(d, 1100, "매주 토요일 밤, 이번 주 숫자 이야기로 다시 만나요", font(30, "Medium"), MUTED)
    _footer(im, 5)
    return im


def build(draws: dict[int, dict], rnd: int, out_dir: Path, *, date_text: str,
          app_result: dict | None = None) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    a = analyze(draws, rnd)
    imgs = [card1(a, rnd, date_text), card2(a, rnd), card3(rnd, app_result),
            card4(rnd, tarot_for_round(rnd)), card5("구글 플레이 · 앱스토어")]
    paths = []
    for i, im in enumerate(imgs, 1):
        p = out_dir / f"{rnd}_{i}.png"
        im.save(p, optimize=True)
        paths.append(p)
    return paths


def caption(draws: dict[int, dict], rnd: int) -> str:
    a = analyze(draws, rnd)
    nums = " ".join(str(n) for n in a["nums"])
    t = tarot_for_round(rnd)
    return (f"🔮 로또신령 주간 리포트 | 제{rnd}회 당첨번호\n\n"
            f"{nums} + 보너스 {a['bonus']}\n"
            f"홀짝 {a['odd']}:{a['even']} · 저고 {a['low']}:{a['high']} · 합계 {a['sum']}\n"
            f"최근 10회 자주 나온 번호: {', '.join(str(n) for n, _ in a['hot'])}\n\n"
            f"{rnd + 1}회를 기다리며 뽑은 이번 주 타로: {t['name']}\n“{t['line']}”\n\n"
            "첫 가입 500P로 번호 조합 무료 체험 → 구글 플레이·앱스토어에서 '로또신령'\n"
            f"자세한 사용법: {BLOG_URL}\n\n"
            "※ 참고·재미용 정보이며 당첨을 보장하지 않습니다. 복권은 만 19세 이상.\n"
            f"#로또 #로또{rnd}회 #로또당첨번호 #로또번호 #로또통계 #타로 #로또신령")


def _draws_from_xlsx(path: str) -> dict[int, dict]:
    import openpyxl

    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    out = {}
    for row in wb["전체당첨내역"].iter_rows(min_row=2, values_only=True):
        if isinstance(row[0], int):
            out[row[0]] = {"nums": [int(x) for x in row[1:7]], "bonus": int(row[7])}
    return out


if __name__ == "__main__":
    src, rnd, out = sys.argv[1], int(sys.argv[2]), Path(sys.argv[3])
    dr = _draws_from_xlsx(src)
    import datetime as _dt

    date_text = (_dt.date(2002, 12, 7) + _dt.timedelta(weeks=rnd - 1)).strftime("%Y.%m.%d")
    for p in build(dr, rnd, out, date_text=date_text):
        print(p)
    (out / f"{rnd}_caption.txt").write_text(caption(dr, rnd), encoding="utf-8")
