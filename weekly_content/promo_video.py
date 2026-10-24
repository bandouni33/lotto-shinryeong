# -*- coding: utf-8 -*-
"""홍보 영상 1편을 페이스북·인스타(릴스)·스레드에 순서대로 게시 — 2026-10-24 사용자 요청("다른 곳에 순차 업로드").

영상은 홈페이지 저장소(bandouni33.github.io)의 media/ 에 올려 공개 주소로 넘긴다(인스타·스레드 영상 게시는
'공개 영상 주소'만 받는다). 채널 스위치·채널 사이 10~30분 무작위 간격·중복 방지 기록은 publish.py 와 같은 것을 쓴다.
SNS 자동화는 '게시'만 한다(2026-10-22 사용자 지시).

실행(Actions '홍보 영상 게시'): python -m weekly_content.promo_video --id 20261024 --url https://lottoshinryeong.com/media/promo_20261024.mp4
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from weekly_content import publish as pb  # noqa: E402
from weekly_content import sns_copy as sc  # noqa: E402

KEY = "promo"   # 게시 기록 키: '채널:promo' (draw_round 자리에 영상 번호)


def captions() -> dict:
    head = ("로또 번호, 아직도 감으로 고르세요?\n\n"
            "1회부터 지금까지 모든 당첨기록으로 번호를 거르는 앱, 로또신령.\n"
            "· 자동조합 — 6,465개 필터를 통과한 조합만\n"
            "· 번개조합 — 고정수·삭제수만 정하면 한 번에\n"
            "· 번호 검증 — 산 번호, QR 한 번이면 반대 조건 조합까지\n"
            "· 고급필터 — 814만 가지 조합을 내 기준으로\n"
            "· 타로 — 지친 날엔 하루 1회 무료\n\n"
            "여러분은 번호를 어떻게 고르세요? 👇 댓글로 알려주세요.")
    out = {c: f"{head}\n\n{sc.footer(c, '/', '' if c == 'instagram' else '자세한 건 홈페이지')}\n"
              f"{sc.hashtags(None, sc.KW_DRAW, sc.KW_PRIZE, sc.KW_STATS, sc.KW_TIME, channel=c)}"
           for c in ("instagram", "facebook")}
    out["threads"] = ("로또 번호, 아직도 감으로 고르세요?\n"
                      "당첨기록으로 거른 자동조합·번개조합·번호검증·타로를 한 앱에서.\n"
                      "여러분은 번호를 어떻게 고르세요? 댓글로!\n\n"
                      f"{sc.footer('threads', '/')}\n#로또")[:500]
    return out


def _wait(http: pb.Http, url: str, token: str, field: str, ok: str, sleep=time.sleep, tries: int = 40) -> None:
    """영상 처리 대기(인스타 status_code / 스레드 status 가 FINISHED 가 될 때까지)."""
    for _ in range(tries):
        st = http.get(url, params={"fields": field, "access_token": token}).get(field)
        if st == ok:
            return
        if st in ("ERROR", "EXPIRED"):
            raise pb.PublishError(f"영상 처리 실패({st})")
        sleep(15)
    raise pb.PublishError("영상 처리 시간 초과")


def post_facebook_video(http: pb.Http, page_id: str, token: str, video_url: str, text: str) -> str:
    return http.post(f"{pb.GRAPH}/{page_id}/videos",
                     data={"file_url": video_url, "description": text, "access_token": token})["id"]


def post_instagram_reel(http: pb.Http, ig_id: str, token: str, video_url: str, caption: str, sleep=time.sleep) -> str:
    cid = http.post(f"{pb.GRAPH}/{ig_id}/media",
                    data={"media_type": "REELS", "video_url": video_url, "caption": caption, "share_to_feed": "true",
                          "access_token": token})["id"]
    _wait(http, f"{pb.GRAPH}/{cid}", token, "status_code", "FINISHED", sleep)
    return http.post(f"{pb.GRAPH}/{ig_id}/media_publish", data={"creation_id": cid, "access_token": token})["id"]


def post_threads_video(http: pb.Http, user_id: str, token: str, video_url: str, text: str, sleep=time.sleep) -> str:
    cid = http.post(f"{pb.THREADS}/{user_id}/threads",
                    data={"media_type": "VIDEO", "video_url": video_url, "text": text, "access_token": token})["id"]
    _wait(http, f"{pb.THREADS}/{cid}", token, "status", "FINISHED", sleep)
    return http.post(f"{pb.THREADS}/{user_id}/threads_publish", data={"creation_id": cid, "access_token": token})["id"]


def run(promo_id: int, video_url: str, *, env=os.environ, http: pb.Http | None = None, log: pb.PostLog | None = None,
        sleep=time.sleep) -> dict:
    chans = [c for c in pb.enabled_channels(env) if c in ("facebook", "instagram", "threads")]
    res = {"id": promo_id, "url": video_url, "posted": {}, "skipped": {}, "failed": {}}
    if not chans:
        res["skipped"] = {"all": "게시 꺼짐(WEEKLY_PUBLISH_CHANNELS)"}
        return res
    http = http or pb.Http()
    log = log or pb.PostLog()
    caps = captions()
    page_id, page_tok = env.get("META_PAGE_ID"), env.get("META_PAGE_TOKEN")
    jobs = []
    if page_id and page_tok:
        jobs.append(("facebook", lambda: post_facebook_video(http, page_id, page_tok, video_url, caps["facebook"])))
        if env.get("IG_USER_ID"):
            jobs.append(("instagram", lambda: post_instagram_reel(http, env["IG_USER_ID"], page_tok, video_url,
                                                                  caps["instagram"], sleep)))
    if env.get("THREADS_USER_ID"):
        jobs.append(("threads", lambda: post_threads_video(http, env["THREADS_USER_ID"], pb.threads_token(http, log, env),
                                                           video_url, caps["threads"], sleep)))
    posted_once = False
    for ch, fn in jobs:
        if ch not in chans:
            continue
        if log.done(promo_id, f"{ch}:{KEY}"):
            res["skipped"][ch] = "이미 게시됨"
            continue
        if posted_once:
            gap = pb.channel_gap()
            print(f"  ({ch} 게시 전 {gap // 60}분 {gap % 60}초 대기)")
            sleep(gap)
        posted_once = True
        try:
            pid = fn()
            log.mark(promo_id, f"{ch}:{KEY}", pid)
            res["posted"][ch] = pid
        except Exception as e:  # 한 채널 실패가 다른 채널을 막지 않게
            res["failed"][ch] = str(e)[:300]
        print(f"  {ch}: {res['posted'].get(ch) or res['failed'].get(ch)}")
    return res


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--id", type=int, required=True)
    ap.add_argument("--url", required=True)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    if not a.url.startswith("https://lottoshinryeong.com/media/"):
        raise SystemExit("[중단] 영상 주소는 홈페이지 media/ 아래만 허용")
    if a.dry_run:
        print(json.dumps(captions(), ensure_ascii=False, indent=1))
        return 0
    res = run(a.id, a.url)
    print(json.dumps(res, ensure_ascii=False, indent=1))
    pb.annotate(res)
    return 1 if res["failed"] else 0


if __name__ == "__main__":
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
    os._exit(code)  # db_turso 비데몬 스레드로 종료가 멈추지 않게(publish.py 와 같은 이유)
