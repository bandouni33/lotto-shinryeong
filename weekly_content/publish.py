# -*- coding: utf-8 -*-
"""주간 리포트 자동 게시 — 페이스북 페이지·인스타그램·스레드·유튜브 쇼츠(2026-10-17 사용자 지시).

run_weekly.py 가 만든 out 폴더({회차}_1~5.png · _shorts.mp4 · _captions.json)를 그대로 올린다.
문구는 cards.captions_all() 한 곳에서만 만든다(여기서 새로 쓰지 않는다).

켜는 스위치(GitHub 저장소 변수 WEEKLY_PUBLISH_CHANNELS, 예: "facebook,instagram,threads,youtube")
  · 비어 있으면 아무것도 올리지 않고 '게시 계획'만 남긴다(기본값 = 안전).
  · 채널 키가 없으면 그 채널만 건너뛴다.
중복 게시 방지: DB 표 weekly_social_posts(회차, 채널) 에 성공 기록이 있으면 다시 올리지 않는다.
  · 같은 회차를 다시 실행해도 이미 올린 채널은 건너뛴다.

인스타·스레드는 '공개 이미지 주소'가 필요하다 → 카드를 페이스북 페이지에 '비공개 사진'으로 먼저 올리고
그 주소를 쓴다(그래서 인스타·스레드도 META_PAGE_ID·META_PAGE_TOKEN 이 있어야 한다).
스레드 장기 토큰은 60일 만료 → 실행할 때마다 갱신해 DB(social_tokens)에 저장한다(처음엔 THREADS_TOKEN).

실행: python -m weekly_content.publish --dir weekly_out [--dry-run]
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

CHANNELS = ("facebook", "instagram", "threads", "youtube")
GRAPH = "https://graph.facebook.com/v25.0"
THREADS = "https://graph.threads.net/v1.0"
THREADS_BASE = "https://graph.threads.net"  # 토큰 갱신은 버전 없는 주소(공식 문서)
YT_TOKEN_URL = "https://oauth2.googleapis.com/token"
YT_UPLOAD_URL = "https://www.googleapis.com/upload/youtube/v3/videos"
TIMEOUT = 120


class PublishError(RuntimeError):
    pass


# ── 설정 ─────────────────────────────────────────────────────────────

def enabled_channels(env=os.environ) -> list[str]:
    raw = (env.get("WEEKLY_PUBLISH_CHANNELS") or "").lower()
    want = {c.strip() for c in raw.split(",") if c.strip()}
    return [c for c in CHANNELS if c in want]


def find_round(out_dir: Path) -> int:
    rounds = {int(m.group(1)) for p in out_dir.glob("*_captions.json")
              if (m := re.match(r"(\d+)_captions\.json$", p.name))}
    if len(rounds) != 1:
        raise PublishError(f"회차를 정할 수 없습니다(captions.json {sorted(rounds)})")
    return rounds.pop()


# ── 기록(중복 방지·토큰) ────────────────────────────────────────────

class PostLog:
    """weekly_social_posts / social_tokens — db_turso 한 곳으로만 접속."""

    def __init__(self, connect=None):
        if connect is None:
            import db_turso
            connect = db_turso.connect
        self._connect = connect
        conn = self._connect()
        conn.execute("CREATE TABLE IF NOT EXISTS weekly_social_posts ("
                     "draw_round INTEGER NOT NULL, channel TEXT NOT NULL, post_id TEXT, posted_at TEXT,"
                     " PRIMARY KEY (draw_round, channel))")
        conn.execute("CREATE TABLE IF NOT EXISTS social_tokens ("
                     "name TEXT PRIMARY KEY, token TEXT NOT NULL, updated_at TEXT)")
        conn.commit()

    def done(self, rnd: int, channel: str) -> bool:
        row = self._connect().execute(
            "SELECT post_id FROM weekly_social_posts WHERE draw_round=? AND channel=?", (rnd, channel)).fetchone()
        return row is not None

    def mark(self, rnd: int, channel: str, post_id: str) -> None:
        conn = self._connect()
        conn.execute("INSERT OR REPLACE INTO weekly_social_posts VALUES (?,?,?,?)",
                     (rnd, channel, str(post_id), dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")))
        conn.commit()

    def get_token(self, name: str) -> str | None:
        row = self._connect().execute("SELECT token FROM social_tokens WHERE name=?", (name,)).fetchone()
        return row[0] if row else None

    def set_token(self, name: str, token: str) -> None:
        conn = self._connect()
        conn.execute("INSERT OR REPLACE INTO social_tokens VALUES (?,?,?)",
                     (name, token, dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")))
        conn.commit()


# ── HTTP ─────────────────────────────────────────────────────────────

class Http:
    def __init__(self, session=None):
        if session is None:
            import requests
            session = requests.Session()
        self.s = session

    def _json(self, r):
        try:
            data = r.json()
        except Exception:
            data = {"raw": r.text[:300]}
        if r.status_code >= 400 or (isinstance(data, dict) and "error" in data):
            raise PublishError(f"{r.status_code} {json.dumps(data, ensure_ascii=False)[:300]}")
        return data

    def get(self, url, **kw):
        return self._json(self.s.get(url, timeout=TIMEOUT, **kw))

    def post(self, url, **kw):
        return self._json(self.s.post(url, timeout=TIMEOUT, **kw))


# ── 페이스북 페이지 ─────────────────────────────────────────────────

def to_jpegs(pngs: list[Path], tmp: Path) -> list[Path]:
    """인스타는 JPEG 만 받는다 — PNG 카드를 JPEG 로 바꾼다."""
    from PIL import Image

    tmp.mkdir(parents=True, exist_ok=True)
    out = []
    for p in pngs:
        q = tmp / (p.stem + ".jpg")
        Image.open(p).convert("RGB").save(q, "JPEG", quality=92)
        out.append(q)
    return out


def fb_upload_unpublished(http: Http, page_id: str, token: str, jpgs: list[Path]) -> list[tuple[str, str]]:
    """카드를 페이지에 '비공개 사진'으로 올리고 (사진ID, 공개 이미지 주소) 를 돌려준다."""
    out = []
    for j in jpgs:
        with open(j, "rb") as fh:
            r = http.post(f"{GRAPH}/{page_id}/photos",
                          data={"published": "false", "access_token": token},
                          files={"source": (j.name, fh, "image/jpeg")})
        pid = r["id"]
        info = http.get(f"{GRAPH}/{pid}", params={"fields": "images", "access_token": token})
        imgs = sorted(info.get("images") or [], key=lambda x: x.get("width", 0), reverse=True)
        if not imgs:
            raise PublishError(f"사진 주소를 받지 못했습니다({pid})")
        out.append((pid, imgs[0]["source"]))
    return out


def post_facebook(http: Http, page_id: str, token: str, photo_ids: list[str], message: str) -> str:
    data = {"message": message, "access_token": token}
    for i, pid in enumerate(photo_ids):
        data[f"attached_media[{i}]"] = json.dumps({"media_fbid": pid})
    return http.post(f"{GRAPH}/{page_id}/feed", data=data)["id"]


# ── 인스타그램 ───────────────────────────────────────────────────────

def _wait_ig(http: Http, cid: str, token: str, tries: int = 10, sleep=time.sleep) -> None:
    for _ in range(tries):
        st = http.get(f"{GRAPH}/{cid}", params={"fields": "status_code", "access_token": token}).get("status_code")
        if st == "FINISHED":
            return
        if st in ("ERROR", "EXPIRED"):
            raise PublishError(f"인스타 준비 실패({cid}: {st})")
        sleep(6)
    raise PublishError(f"인스타 준비 시간 초과({cid})")


def post_instagram(http: Http, ig_id: str, token: str, urls: list[str], caption: str, sleep=time.sleep) -> str:
    kids = []
    for u in urls:
        cid = http.post(f"{GRAPH}/{ig_id}/media",
                        data={"image_url": u, "is_carousel_item": "true", "access_token": token})["id"]
        _wait_ig(http, cid, token, sleep=sleep)
        kids.append(cid)
    car = http.post(f"{GRAPH}/{ig_id}/media", data={"media_type": "CAROUSEL", "children": ",".join(kids),
                                                     "caption": caption, "access_token": token})["id"]
    _wait_ig(http, car, token, sleep=sleep)
    return http.post(f"{GRAPH}/{ig_id}/media_publish", data={"creation_id": car, "access_token": token})["id"]


# ── 스레드 ───────────────────────────────────────────────────────────

def threads_token(http: Http, log: PostLog, env=os.environ) -> str | None:
    """갱신 가능한 토큰을 찾아 갱신·저장하고 돌려준다 — DB 에 저장된 최신 토큰 먼저, 안 되면 THREADS_TOKEN.
    2026-10-17: 사용자가 Secrets 를 새로 넣었는데 DB 의 옛(끊긴) 토큰이 먼저 쓰이면 안 되므로 둘 다 시도."""
    cands = [t for t in (log.get_token("threads"), env.get("THREADS_TOKEN")) if t]
    for tok in dict.fromkeys(cands):
        try:
            new = http.get(f"{THREADS_BASE}/refresh_access_token",
                           params={"grant_type": "th_refresh_token", "access_token": tok}).get("access_token")
            if new:
                log.set_token("threads", new)
                return new
        except PublishError as e:
            print(f"  (스레드 토큰 갱신 실패 — 다음 후보: {str(e)[:120]})")
    return env.get("THREADS_TOKEN") or (cands[0] if cands else None)


def check_keys(env=os.environ, http: Http | None = None, log: PostLog | None = None) -> dict:
    """게시하지 않고 키만 점검(2026-10-17) — 채널별 OK/실패와 계정 이름만 돌려준다(토큰 값은 절대 출력 안 함)."""
    http = http or Http()
    out = {}

    def run(name, fn):
        try:
            out[name] = "OK " + fn()
        except Exception as e:  # noqa: BLE001
            out[name] = "실패 " + str(e)[:200]

    page, ptok = env.get("META_PAGE_ID"), env.get("META_PAGE_TOKEN")
    run("facebook", lambda: http.get(f"{GRAPH}/{page}", params={"fields": "name", "access_token": ptok})["name"])
    ig = env.get("IG_USER_ID")
    run("instagram", lambda: "@" + http.get(f"{GRAPH}/{ig}", params={"fields": "username",
                                                                    "access_token": ptok})["username"])

    def th():
        tok = threads_token(http, log or PostLog(), env)
        me = http.get(f"{THREADS}/me", params={"fields": "id,username", "access_token": tok})
        if str(me.get("id")) != str(env.get("THREADS_USER_ID")):
            raise PublishError(f"THREADS_USER_ID 불일치(토큰 계정 @{me.get('username')})")
        return "@" + me["username"]

    run("threads", th)

    def yt():
        if not env.get("YT_REFRESH_TOKEN"):
            raise PublishError("YT 키 없음")
        at = http.post(YT_TOKEN_URL, data={"client_id": env.get("YT_CLIENT_ID"),
                                           "client_secret": env.get("YT_CLIENT_SECRET"),
                                           "refresh_token": env.get("YT_REFRESH_TOKEN"),
                                           "grant_type": "refresh_token"})["access_token"]
        items = http.get("https://www.googleapis.com/youtube/v3/channels",
                         params={"part": "snippet", "mine": "true"},
                         headers={"Authorization": f"Bearer {at}"}).get("items") or []
        if not items:
            raise PublishError("이 계정에 유튜브 채널 없음")
        sn = items[0]["snippet"]
        return f"{sn.get('title')} ({sn.get('customUrl', '')})"

    run("youtube", yt)
    out["채널 스위치"] = ",".join(enabled_channels(env)) or "(비어 있음 — 게시 안 함)"
    return out


def post_threads(http: Http, user_id: str, token: str, urls: list[str], text: str, sleep=time.sleep) -> str:
    kids = [http.post(f"{THREADS}/{user_id}/threads",
                      data={"media_type": "IMAGE", "image_url": u, "is_carousel_item": "true",
                            "access_token": token})["id"] for u in urls]
    car = http.post(f"{THREADS}/{user_id}/threads",
                    data={"media_type": "CAROUSEL", "children": ",".join(kids), "text": text,
                          "access_token": token})["id"]
    sleep(30)  # 스레드 권장: 만든 뒤 30초 기다렸다 발행
    return http.post(f"{THREADS}/{user_id}/threads_publish",
                     data={"creation_id": car, "access_token": token})["id"]


# ── 유튜브 쇼츠 ─────────────────────────────────────────────────────

def post_youtube(http: Http, env, mp4: Path, title: str, desc: str) -> str:
    tok = http.post(YT_TOKEN_URL, data={"client_id": env["YT_CLIENT_ID"], "client_secret": env["YT_CLIENT_SECRET"],
                                         "refresh_token": env["YT_REFRESH_TOKEN"],
                                         "grant_type": "refresh_token"})["access_token"]
    meta = {"snippet": {"title": title, "description": desc, "categoryId": "24", "defaultLanguage": "ko"},
            "status": {"privacyStatus": env.get("YT_PRIVACY") or "public", "selfDeclaredMadeForKids": False}}
    r = http.s.post(f"{YT_UPLOAD_URL}?uploadType=resumable&part=snippet,status", json=meta, timeout=TIMEOUT,
                    headers={"Authorization": f"Bearer {tok}", "X-Upload-Content-Type": "video/mp4"})
    if r.status_code >= 400 or not r.headers.get("Location"):
        raise PublishError(f"유튜브 업로드 시작 실패 {r.status_code} {r.text[:200]}")
    with open(mp4, "rb") as fh:
        up = http.s.put(r.headers["Location"], data=fh, timeout=600,
                        headers={"Authorization": f"Bearer {tok}", "Content-Type": "video/mp4"})
    return http._json(up)["id"]


# ── 전체 흐름 ───────────────────────────────────────────────────────

KINDS = ("weekly", "thu", "fri", "result")   # 2026-10-18: 목·금 구매 전(pre_draw.py)·공식 결과 정리(result_post.py) — 카드 2장


def publish(out_dir: Path, *, env=os.environ, http: Http | None = None, log: PostLog | None = None,
            dry_run: bool = False, sleep=time.sleep, kind: str = "weekly") -> dict:
    if kind not in KINDS:
        raise PublishError(f"kind 는 {KINDS} 중 하나")
    rnd = find_round(out_dir)
    caps = json.loads((out_dir / f"{rnd}_captions.json").read_text(encoding="utf-8"))
    pngs = [out_dir / f"{rnd}_{i}.png" for i in range(1, 6 if kind == "weekly" else 3)]
    mp4 = out_dir / f"{rnd}_shorts.mp4"
    talis = [p for p in (out_dir / f"{rnd}_talisman.png",) if kind == "weekly" and p.exists()]
    missing = [p.name for p in pngs if not p.exists()]
    if missing:
        raise PublishError(f"카드가 없습니다: {missing}")
    chans = enabled_channels(env)
    result = {"round": rnd, "channels": chans, "posted": {}, "skipped": {}, "failed": {}}
    if dry_run or not chans:
        result["skipped"] = {c: "게시 꺼짐(WEEKLY_PUBLISH_CHANNELS)" for c in CHANNELS}
        (out_dir / f"{rnd}_publish_plan.json").write_text(json.dumps(result, ensure_ascii=False, indent=1),
                                                          encoding="utf-8")
        return result
    http = http or Http()
    log = log or PostLog()
    key = (lambda c: c) if kind == "weekly" else (lambda c: f"{c}:{kind}")   # 게시 기록 키(토요일 게시와 분리)
    todo = [c for c in chans if not log.done(rnd, key(c))]
    for c in chans:
        if c not in todo:
            result["skipped"][c] = "이미 게시됨"

    page_id, page_tok = env.get("META_PAGE_ID"), env.get("META_PAGE_TOKEN")
    photos: list[tuple[str, str]] = []
    if any(c in todo for c in ("facebook", "instagram", "threads")):
        if not (page_id and page_tok):
            for c in ("facebook", "instagram", "threads"):
                if c in todo:
                    result["skipped"][c] = "META_PAGE_ID/META_PAGE_TOKEN 없음"
                    todo.remove(c)
        else:
            try:
                photos = fb_upload_unpublished(http, page_id, page_tok, to_jpegs(pngs + talis, out_dir / "_jpg"))
            except PublishError as e:
                for c in ("facebook", "instagram", "threads"):
                    if c in todo:
                        result["failed"][c] = f"사진 올리기 실패: {e}"
                        todo.remove(c)

    def run(channel, fn):
        if channel not in todo:
            return
        try:
            pid = fn()
            log.mark(rnd, key(channel), pid)
            result["posted"][channel] = pid
        except Exception as e:  # 한 채널 실패가 다른 채널을 막지 않게
            result["failed"][channel] = str(e)[:300]

    # 2026-10-18: 회차 부적(있으면 마지막에 올림) — 인스타 캐러셀 첫 장으로만 쓰고 페북·스레드는 카드만
    card_photos, talis_photos = photos[:len(pngs)], photos[len(pngs):]
    urls = [u for _, u in card_photos]
    ig_urls = [u for _, u in talis_photos] + urls
    run("facebook", lambda: post_facebook(http, page_id, page_tok, [p for p, _ in card_photos], caps["facebook"]))
    if "instagram" in todo and not env.get("IG_USER_ID"):
        todo.remove("instagram")
        result["skipped"]["instagram"] = "IG_USER_ID 없음"
    run("instagram", lambda: post_instagram(http, env["IG_USER_ID"], page_tok, ig_urls, caps["instagram"], sleep=sleep))
    if "threads" in todo:
        ttok = threads_token(http, log, env) if env.get("THREADS_USER_ID") else None
        if not ttok:
            todo.remove("threads")
            result["skipped"]["threads"] = "THREADS_USER_ID/THREADS_TOKEN 없음"
        else:
            run("threads", lambda: post_threads(http, env["THREADS_USER_ID"], ttok, urls, caps["threads"], sleep=sleep))
    if "youtube" in todo:
        if not all(env.get(k) for k in ("YT_CLIENT_ID", "YT_CLIENT_SECRET", "YT_REFRESH_TOKEN")):
            todo.remove("youtube")
            result["skipped"]["youtube"] = "YT_CLIENT_ID/SECRET/REFRESH_TOKEN 없음"
        elif not mp4.exists():
            todo.remove("youtube")
            result["skipped"]["youtube"] = "쇼츠 파일 없음"
        else:
            run("youtube", lambda: post_youtube(http, env, mp4, caps["youtube_title"], caps["youtube_description"]))
    (out_dir / f"{rnd}_publish_result.json").write_text(json.dumps(result, ensure_ascii=False, indent=1),
                                                        encoding="utf-8")
    return result


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default="weekly_out")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--check", help="게시 없이 키 점검 — 결과를 이 파일에 씀")
    ap.add_argument("--kind", default="weekly", choices=KINDS)
    a = ap.parse_args()
    if a.check:
        res = check_keys()
        txt = "\n".join(f"{k}: {v}" for k, v in res.items())
        Path(a.check).write_text(txt + "\n", encoding="utf-8")
        print(txt)
        return 0
    res = publish(Path(a.dir), dry_run=a.dry_run, kind=a.kind)
    print(json.dumps(res, ensure_ascii=False, indent=1))
    return 1 if res["failed"] else 0


if __name__ == "__main__":
    # 2026-10-17: 예외로 끝나도 os._exit 로 바로 종료 — 아니면 db_turso 비데몬 스레드 때문에 프로세스가
    # 안 끝나 Actions 가 시간 한도까지 '진행 중'으로 멈추고, 같은 concurrency 의 다음 실행까지 막는다.
    import traceback
    try:
        code = main()
    except SystemExit as e:
        code = e.code if isinstance(e.code, int) else (1 if e.code else 0)
        if not isinstance(e.code, int) and e.code:
            print(e.code)
    except BaseException:
        traceback.print_exc()
        code = 1
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(code)  # db_turso 비데몬 스레드로 종료가 멈추지 않게
