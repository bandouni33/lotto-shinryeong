# -*- coding: utf-8 -*-
"""로또신령 주간 리포트 카드(4장, 1080x1350) — 2026-10-24 사용자 지시로 5장 → 4장.

  1 표지: N회 당첨번호 + 보너스 (볼 색은 ball_style 단일 기준점) + 바로 밑 '1등 당첨자·당첨금 · 동행복권 집계중'
  2 숫자 분석: 홀짝·저고·합계·연번·구간 분포, 최근 10회 많이 나온 번호 / 오래 안 나온 번호
  3 다음 회 재미 요소: 회차로 정해지는 타로 한 장(메이저 22장, 퍼블릭 도메인 RWS) + 한 줄 + 500P 체험
  4 마무리: 설치 안내
  모든 카드 아래: 홈페이지 주소(2026-10-24 사용자 지시: 게시물에 참고사항 문구는 넣지 않는다)
  (예전 3번 '추첨결과·당첨지역'은 추첨 직후엔 비어 있어 뺐다 — 1등 결과는 공식 발표 뒤 result_post 게시물)

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
PENDING_TEXT = "동행복권 집계중"
# 2026-10-24(사용자 지시): 카드 맨 아래 고지 문구 대신 홈페이지 주소 — 맨 아래는 화면에서 잘 안 보여 조금 위로.
FOOT_TEXT = "홈페이지  lottoshinryeong.com"
FOOT_Y = 1232
SPIRIT_IMG = ROOT / "아이콘815.png"
TAROT_DIR = ROOT / "tarot"


_WEIGHT_FALLBACK = {"Black": ("Black", "Bold"), "Medium": ("Medium", "Regular"), "Bold": ("Bold",),
                    "Regular": ("Regular",)}


def font(size: int, weight: str = "Bold") -> ImageFont.FreeTypeFont:
    # 2026-10-17: Actions 러너의 fonts-noto-cjk 에는 Regular·Bold 만 있다(Black·Medium 은 -extra 패키지) —
    # 없으면 가까운 굵기로 대체(Black→Bold, Medium→Regular). 그래도 없으면 시스템 Noto CJK 를 찾는다.
    for w in _WEIGHT_FALLBACK.get(weight, (weight, "Bold")):
        for path in (_BUNDLED / f"NotoSansKR-{w}.otf", _FONT_DIR / f"NotoSansCJK-{w}.ttc"):
            if path.exists():
                return ImageFont.truetype(str(path), size, index=1 if path.suffix == ".ttc" else 0)
    for path in sorted(Path("/usr/share/fonts").rglob("NotoSansCJK-*.ttc")):
        return ImageFont.truetype(str(path), size, index=1)
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


def _footer(im, page, total=4, label="로또신령 주간 리포트"):
    d = ImageDraw.Draw(im)
    _center(d, FOOT_Y, FOOT_TEXT, font(34, "Bold"), GOLD)
    d.text((W - 110, 40), f"{page}/{total}", font=font(28, "Medium"), fill=MUTED)
    d.text((48, 40), label, font=font(28, "Bold"), fill=GOLD)


# ── 숫자 계산(이력에서만) ─────────────────────────────────────────────
def analyze(draws: dict[int, dict], rnd: int) -> dict:
    nums = sorted(draws[rnd]["nums"])
    odd = sum(n % 2 for n in nums)
    low = sum(1 for n in nums if n <= 22)
    runs = sum(1 for a, b in zip(nums, nums[1:]) if b == a + 1)
    # 2026-10-24(사용자 지시): 연속번호는 '쌍' 개수가 아니라 묶음 길이로 — 22·23·24 = 3연, 27·28 = 2연
    run_lens, cur = [], 1
    for x, y in zip(nums, nums[1:]):
        if y == x + 1:
            cur += 1
        else:
            if cur > 1:
                run_lens.append(cur)
            cur = 1
    if cur > 1:
        run_lens.append(cur)
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
            "high": 6 - low, "sum": sum(nums), "runs": runs, "run_lens": sorted(run_lens), "bands": bands,
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
    # 2026-10-24(사용자 지시): '동행복권 집계중'을 당첨번호 바로 밑으로(1등 결과는 공식 발표 뒤 따로 게시)
    _center(d, 1035, f"1등 당첨자·당첨금  ·  {PENDING_TEXT}", font(32, "Medium"), MUTED)
    _center(d, 1110, "이번 주 숫자, 한 장씩 넘겨 보세요 →", font(34, "Medium"), WHITE)
    _footer(im, 1)
    return im


def card2(a, rnd):
    im = _canvas()
    d = ImageDraw.Draw(im)
    _center(d, 120, f"{rnd}회 숫자 분석", font(64, "Black"), GOLD)
    _panel(im, (60, 230, W - 60, 640))
    d = ImageDraw.Draw(im)
    rows = [("홀 : 짝", f"{a['odd']} : {a['even']}"), ("저(1~22) : 고(23~45)", f"{a['low']} : {a['high']}"),
            ("번호 합계", f"{a['sum']}"), ("연속번호", f"{max(a['run_lens'])}연" if a["run_lens"] else "없음")]   # 10-24: 가장 긴 묶음만(혼동 방지)
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


def card4(rnd, tarot, foot=(3, 4, "로또신령 주간 리포트")):
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
    _footer(im, *foot)
    return im


def card5(store_text, foot=(4, 4, "로또신령 주간 리포트")):
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
    _center(d, 1040, "사용설명서 · 당첨번호 · 번호 통계는 홈페이지에서", font(32, "Medium"), WHITE)
    _center(d, 1100, "매주 토요일 밤, 이번 주 숫자 이야기로 다시 만나요", font(30, "Medium"), MUTED)
    _footer(im, *foot)
    return im


def build(draws: dict[int, dict], rnd: int, out_dir: Path, *, date_text: str) -> list[Path]:
    """2026-10-24(사용자 지시): 4장 — ①당첨번호(+동행복권 집계중) ②숫자 분석 ③다음 회차 타로 ④앱 안내.
    예전 ③추첨결과·당첨지역 카드는 추첨 직후엔 비어 있어 뺐다(1등 결과는 공식 발표 뒤 '결과 정리' 게시물)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    a = analyze(draws, rnd)
    imgs = [card1(a, rnd, date_text), card2(a, rnd), card4(rnd, tarot_for_round(rnd)),
            card5("구글 플레이 · 앱스토어")]
    paths = []
    for i, im in enumerate(imgs, 1):
        p = out_dir / f"{rnd}_{i}.png"
        im.save(p, optimize=True)
        paths.append(p)
    return paths


def caption(draws: dict[int, dict], rnd: int, source: str = "instagram") -> str:
    """source = 채널 이름(instagram/facebook/youtube — 채널별 첫머리·링크 방식이 다름)."""
    from weekly_content import number_story

    from weekly_content import sns_copy as sc

    a = analyze(draws, rnd)
    nums = " ".join(str(n) for n in a["nums"])
    t = tarot_for_round(rnd)
    h = number_story.headline(draws, rnd)
    # 2026-10-18 채널별 특색: 인스타 = 회차 부적 컬렉션, 페북 = 신령엔터 주간 사건 일지
    hook = f"🎯 제{rnd}회 1등 번호, 몇 개 맞으셨나요?\n\n"   # 2026-10-24: 첫 줄 훅(정보 나열은 아래로)
    if source == "instagram":
        opener = hook   # 2026-10-24(사용자 지시 '첫 페이지 부적 삭제'): 부적 안내 문구도 뺀다
    elif source == "facebook":
        extra = []
        if h["comeback"]:
            extra.append("컴백 " + ", ".join(f"{x['n']}번({x['gap']}회 만)" for x in h["comeback"]))
        if h["streak"]:
            extra.append("연속 무대 " + ", ".join(f"{x['n']}번({x['weeks']}주)" for x in h["streak"]))
        extra.append("가장 긴 공백기 " + ", ".join(f"{x['n']}번({x['gap']}주)" for x in h["hiatus"][:3]))
        # 2026-10-24: 페북 본문 링크는 1개(회차 페이지)만 — 멤버 페이지 주소는 뺀다.
        opener = hook + (f"📰 신령엔터 45인조 주간 소식 — {h['title']}\n" + "\n".join(f"· {x}" for x in extra) + "\n\n")
    else:
        opener = hook
    return (opener + f"🔮 로또신령 주간 리포트 | 제{rnd}회 당첨번호\n\n"
            f"{nums} + 보너스 {a['bonus']}\n"
            f"홀짝 {a['odd']}:{a['even']} · 저고 {a['low']}:{a['high']} · 합계 {a['sum']}\n"
            f"최근 10회 자주 나온 번호: {', '.join(str(n) for n, _ in a['hot'])}\n\n"
            f"{rnd + 1}회를 기다리며 뽑은 이번 주 타로: {t['name']}\n“{t['line']}”\n\n"
            "👇 맞힌 개수만 댓글로 남겨주세요.\n\n"
            # 2026-10-22: 링크·해시태그·고지는 sns_copy 한 곳(목·금·토 게시 공통, 홈페이지 링크로 통일)
            f"{sc.footer(source, f'/round/{rnd}/', f'{rnd}회 번호 구성·1등 명당')}\n"
            f"{sc.hashtags(rnd, sc.KW_DRAW, sc.KW_PRIZE, sc.KW_STATS, ['타로'], channel=source)}")


THREADS_LIMIT = 500  # 스레드 글자 제한(이모지·URL 포함)


def caption_threads(draws: dict[int, dict], rnd: int) -> str:
    """스레드용 짧은 문구(500자 이내) — 해시태그는 1개만 붙는 플랫폼이라 끝에 하나만."""
    from weekly_content import sns_copy as sc

    a = analyze(draws, rnd)
    nums = " ".join(str(n) for n in a["nums"])
    # 2026-10-24: 목요일 스레드가 5장 컨셉으로 바뀌어 '목요일 문답 결과'는 싣지 않는다(문답을 더 이상 묻지 않음)
    qa = f"홀짝 {a['odd']}:{a['even']} · 저고 {a['low']}:{a['high']} · 합계 {a['sum']}\n\n"

    txt = (f"🔮 제{rnd}회 로또 당첨번호\n{nums} + 보너스 {a['bonus']}\n\n" + qa +
           "내 번호는 몇 개 맞았나요? 댓글로!\n\n"
           f"{sc.footer('threads', f'/round/{rnd}/')}\n{sc.hashtags(rnd, channel='threads')}")
    return txt[:THREADS_LIMIT]


def youtube_meta(draws: dict[int, dict], rnd: int) -> dict:
    """유튜브 쇼츠 제목(100자 이내)·설명."""
    a = analyze(draws, rnd)
    nums = " ".join(str(n) for n in a["nums"])
    return {"title": f"제{rnd}회 로또 당첨번호 {nums} + {a['bonus']} | 로또신령 #Shorts"[:100],
            "description": caption(draws, rnd, "youtube") + "\n#Shorts"}


def captions_all(draws: dict[int, dict], rnd: int) -> dict:
    """채널별 문구 한 벌 — 게시 단계(publish.py)는 이 값만 쓴다(문구를 따로 만들지 않는다)."""
    yt = youtube_meta(draws, rnd)
    return {"instagram": caption(draws, rnd, "instagram"), "facebook": caption(draws, rnd, "facebook"), "threads": caption_threads(draws, rnd),
            "youtube_title": yt["title"], "youtube_description": yt["description"]}


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
