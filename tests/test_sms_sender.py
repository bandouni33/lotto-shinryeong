"""sms_sender 단위 테스트."""

import os
import tempfile
import unittest
from unittest.mock import patch

import marketing_db as mdb
import sms_sender as sms


class SmsSenderTests(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self._orig_mdb = mdb.DB_PATH
        mdb.DB_PATH = os.path.join(self._tmpdir.name, "test.db")
        mdb.init_marketing_tables()

    def tearDown(self):
        mdb.DB_PATH = self._orig_mdb
        self._tmpdir.cleanup()
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
