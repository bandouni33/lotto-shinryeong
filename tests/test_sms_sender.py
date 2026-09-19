"""sms_sender 단위 테스트.

2026-09-19 수정(중요): 예전엔 setUp에서 mdb.DB_PATH를 임시경로로 바꿔 격리한다고
했지만, marketing_db._connect()는 DB_PATH를 안 봐서 그 패치가 no-op이었다 —
이 테스트는 운영 DB의 sms_queue에 시험 번호(01012345678/01099998888/01011112222)를
실제로 남겼다. 이제 db_turso.connect 자체를 임시 sqlite로 바꿔치기한다.
"""

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

TESTS_DIR = Path(__file__).resolve().parent
ROOT = TESTS_DIR.parent
for _path in (str(ROOT), str(TESTS_DIR)):
    if _path not in sys.path:
        sys.path.insert(0, _path)

import _db_isolation  # noqa: E402
import marketing_db as mdb  # noqa: E402
import sms_sender as sms  # noqa: E402


class SmsSenderTests(unittest.TestCase):
    def setUp(self):
        self._iso = _db_isolation.isolated_db()
        self._iso.__enter__()
        self.addCleanup(self._iso.__exit__, None, None, None)
        mdb.init_marketing_tables()

    def tearDown(self):
        for key in ("ALIGO_API_KEY", "ALIGO_USER_ID", "ALIGO_SENDER"):
            os.environ.pop(key, None)

    def test_banner_mode_uses_banner_only(self):
        with patch.object(sms, "SMS_ENABLED", False):
            sms_id = sms.dispatch_purchase_sms("01012345678", "일반구매", "테스트 본문")
        self.assertGreater(sms_id, 0)
        conn = mdb._connect()
        row = conn.execute(
            "SELECT send_status FROM sms_queue WHERE id = ?", (sms_id,)
        ).fetchone()
        conn.close()
        self.assertEqual(row[0], "BANNER_ONLY")

    @patch.object(sms, "SMS_ENABLED", True)
    def test_not_configured_uses_test_skip(self):
        with patch("builtins.print") as mock_print:
            sms_id = sms.dispatch_purchase_sms("01012345678", "일반구매", "테스트 본문")
        self.assertGreater(sms_id, 0)
        conn = mdb._connect()
        row = conn.execute(
            "SELECT send_status FROM sms_queue WHERE id = ?", (sms_id,)
        ).fetchone()
        conn.close()
        self.assertEqual(row[0], "TEST_SKIP")
        mock_print.assert_called()
        self.assertIn("테스트 모드", mock_print.call_args[0][0])

    @patch.object(sms, "SMS_ENABLED", True)
    @patch("sms_sender.requests.post")
    def test_configured_success_marks_sent(self, mock_post):
        os.environ["ALIGO_API_KEY"] = "test-key"
        os.environ["ALIGO_USER_ID"] = "test-user"
        os.environ["ALIGO_SENDER"] = "01000000000"
        mock_resp = mock_post.return_value
        mock_resp.raise_for_status.return_value = None
        mock_resp.json.return_value = {
            "result_code": "1",
            "message": "success",
            "msg_id": "123",
        }
        sms_id = sms.dispatch_purchase_sms("01099998888", "정기구독", "본문")
        conn = mdb._connect()
        row = conn.execute(
            "SELECT send_status FROM sms_queue WHERE id = ?", (sms_id,)
        ).fetchone()
        conn.close()
        self.assertEqual(row[0], "SENT")
        mock_post.assert_called_once()

    def test_enqueue_sms_accepts_banner_only(self):
        sms_id = mdb.enqueue_sms("01011112222", "일반구매", "BANNER_ONLY")
        self.assertGreater(sms_id, 0)

    def test_enqueue_sms_accepts_test_skip(self):
        sms_id = mdb.enqueue_sms("01011112222", "일반구매", "TEST_SKIP")
        self.assertGreater(sms_id, 0)


if __name__ == "__main__":
    unittest.main()
