# -*- coding: utf-8 -*-
"""앱 "불러오는 중" 화면을 Streamlit 이 화면을 다 그릴 때까지 유지 (2026-10-08).

실기기 영상 실측: 문서 로드 끝(onLoadEnd)에 로딩 화면을 내려서 흰 화면 3.5초 + 빈 어두운 화면
9.5초가 그대로 보였다. streamlit-webview.tsx 의 PAGE_READY_INJECTED_JS 가 Streamlit 첫 실행
완료(+화면 칠해짐)를 pageReady 로 알리고, 그때 로딩 화면을 내린다.

  R1 WebView 에 injectedJavaScript 로 연결돼 있고, onMessage 가 pageReady 를 받아 로딩을 내린다.
  R2 onLoadEnd 는 신호를 기다리는 중이면 로딩을 내리지 않는다(신호 미지원 환경은 예전처럼 내림).
  R3 신호가 끝내 안 와도 PAGE_READY_MAX_WAIT_MS 뒤엔 내린다(멈춘 것처럼 보이지 않게).
  R4 실제로 웹뷰에 들어갈 스크립트(템플릿 문자열을 풀어낸 결과)가 문법상 맞고, 배경 판정 정규식이
     어두운/밝은 배경을 바르게 가른다(node 가 있으면 실행해 확인).
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "LottoShinryeong" / "components" / "streamlit-webview.tsx"


def _src() -> str:
    return SRC.read_text(encoding="utf-8")


_NODE_EVAL = r"""
const fs = require('fs');
const src = fs.readFileSync(process.argv[1], 'utf8');
const m = src.match(/const PAGE_READY_INJECTED_JS = (`[\s\S]*?`);/);
const PAGE_READY_MESSAGE_TYPE = (src.match(/const PAGE_READY_MESSAGE_TYPE = '([^']+)'/) || [])[1];
const js = eval(m[1]);
new Function(js);  // 문법 확인
const re = /rgba?\((\d+),\s*(\d+),\s*(\d+)/;
const line = js.split('\n').find(l => l.includes('rgba?'));
const dark = (c) => { const x = new RegExp(line.match(/\/(rgba[^/]+)\//)[1]).exec(c); return x ? (Number(x[1]) + Number(x[2]) + Number(x[3])) / 3 < 128 : null; };
console.log(JSON.stringify({type: PAGE_READY_MESSAGE_TYPE, darkApp: dark('rgb(18, 24, 43)'), lightDefault: dark('rgb(250, 248, 255)'), hasType: js.includes("type: '" + PAGE_READY_MESSAGE_TYPE + "'")}));
"""


class PageReadyOverlayTests(unittest.TestCase):
    def test_R1_wired(self):
        s = _src()
        self.assertIn("injectedJavaScript={PAGE_READY_INJECTED_JS}", s)
        self.assertIn("payload?.type === PAGE_READY_MESSAGE_TYPE", s)
        branch = s[s.index("payload?.type === PAGE_READY_MESSAGE_TYPE"):][:400]
        self.assertIn("setLoading(false)", branch)
        self.assertIn("awaitingPageReadyRef.current = false", branch)

    def test_R2_load_end_waits(self):
        s = _src()
        end = s[s.index("onLoadEnd={() => {"):][:1200]
        self.assertIn("if (pageReadyUnsupportedRef.current || !awaitingPageReadyRef.current)", end)
        start = s[s.index("onLoadStart={() => {"):][:200]
        self.assertIn("awaitingPageReadyRef.current = true", start)

    def test_R3_max_wait(self):
        s = _src()
        m = re.search(r"const PAGE_READY_MAX_WAIT_MS = (\d+);", s)
        self.assertTrue(m)
        self.assertTrue(8000 <= int(m.group(1)) <= 20000, m.group(1))
        self.assertNotIn("setTimeout(() => setLoading(false), 6000)", s)
        self.assertIn("PAGE_READY_MAX_WAIT_MS);", s)

    def test_R4_injected_script_runs(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("node 없음")
        out = subprocess.run([node, "-e", _NODE_EVAL, str(SRC)], capture_output=True, text=True, timeout=60)
        self.assertEqual(out.returncode, 0, out.stderr)
        r = json.loads(out.stdout.strip().splitlines()[-1])
        self.assertEqual(r["type"], "pageReady")
        self.assertTrue(r["hasType"])
        self.assertIs(r["darkApp"], True)
        self.assertIs(r["lightDefault"], False)


if __name__ == "__main__":
    result = unittest.TextTestRunner(verbosity=2).run(
        unittest.defaultTestLoader.loadTestsFromTestCase(PageReadyOverlayTests))
    sys.exit(0 if result.wasSuccessful() else 1)
