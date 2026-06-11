import argparse
import datetime as dt
import os
import unittest
from unittest import mock

import tax_exemption_review as review


class ApiKeyTests(unittest.TestCase):
    def test_load_api_key_uses_embedded_test_key_when_no_runtime_key_is_set(self):
        args = argparse.Namespace(api_key=None, api_key_env="MISSING_TEST_KEY")

        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(
                review.load_api_key(args),
                "fW2eKh3wsBqMtOHQ6jyYn8xpiPZvaVXb",
            )


class AuditPayloadTests(unittest.TestCase):
    def test_rejected_payload_defaults_expired_at_to_now(self):
        fixed_now = dt.datetime(2026, 6, 11, 9, 8, 7)
        args = argparse.Namespace(
            status="rejected",
            expired_at=None,
            refuse_reason="the document provided is not a valid tax exemption certificate.",
        )

        payload = review.build_audit_payload(args, now=lambda: fixed_now)

        self.assertEqual(
            payload,
            {
                "status": "rejected",
                "expired_at": "2026-06-11 09:08:07",
                "refuse_reason": "the document provided is not a valid tax exemption certificate.",
            },
        )

    def test_rejected_payload_rejects_long_refuse_reason(self):
        args = argparse.Namespace(
            status="rejected",
            expired_at=None,
            refuse_reason="x" * 501,
        )

        with self.assertRaises(SystemExit):
            review.build_audit_payload(args, now=lambda: dt.datetime(2026, 6, 11, 9, 8, 7))

    def test_approved_payload_requires_expired_at(self):
        args = argparse.Namespace(status="approved", expired_at=None, refuse_reason=None)

        with self.assertRaises(SystemExit):
            review.build_audit_payload(args)

    def test_approved_payload_omits_refuse_reason(self):
        args = argparse.Namespace(
            status="approved",
            expired_at="2026-12-31 23:59:59",
            refuse_reason="ignored",
        )

        payload = review.build_audit_payload(args)

        self.assertEqual(
            payload,
            {"status": "approved", "expired_at": "2026-12-31 23:59:59"},
        )

    def test_audit_dry_run_does_not_require_api_key_or_send_request(self):
        args = argparse.Namespace(
            api_key=None,
            api_key_env="MISSING_TEST_KEY",
            base_url="https://jd.test.jeeda.net",
            id="123",
            status="rejected",
            expired_at="2026-06-11 09:08:07",
            refuse_reason="the document provided is not a valid tax exemption certificate.",
            dry_run=True,
        )

        with mock.patch("tax_exemption_review.request_json") as request_json:
            with mock.patch("tax_exemption_review.print") as print_mock:
                review.cmd_audit(args)

        request_json.assert_not_called()
        printed = print_mock.call_args.args[0]
        self.assertIn('"url": "https://jd.test.jeeda.net/api/external/tax/exemption/123/audit"', printed)
        self.assertIn('"status": "rejected"', printed)


class UrlFallbackTests(unittest.TestCase):
    def test_test_cdn_url_maps_to_public_s3_url(self):
        url = "https://media.test.jeeda.net/media/exemption/x/x/file.jpg"

        self.assertEqual(
            review.fallback_download_urls(url),
            [
                "https://media.test.jeeda.net/media/exemption/x/x/file.jpg",
                "https://jeeda-media.s3.us-west-2.amazonaws.com/media/exemption/x/x/file.jpg",
            ],
        )

    def test_placeholder_url_has_no_s3_fallback(self):
        url = "https://media.test.jeeda.net/media/exemption/{{file_url}}"

        self.assertEqual(review.fallback_download_urls(url), [url])


class DownloadTests(unittest.TestCase):
    def test_download_tries_s3_fallback_after_cdn_failure(self):
        args = argparse.Namespace(
            url="https://media.test.jeeda.net/media/exemption/x/x/file.jpg",
            out="/tmp/out.jpg",
        )
        responses = [Exception("cdn denied"), mock.Mock()]
        responses[1].read.return_value = b"image"
        responses[1].__enter__ = lambda value: value
        responses[1].__exit__ = lambda *exc: None

        with mock.patch("tax_exemption_review.urllib.request.urlopen", side_effect=responses):
            with mock.patch("tax_exemption_review.Path.write_bytes") as write_bytes:
                with mock.patch("tax_exemption_review.Path.mkdir"):
                    with mock.patch("tax_exemption_review.print"):
                        review.cmd_download(args)

        self.assertEqual(write_bytes.call_args.args[0], b"image")


if __name__ == "__main__":
    unittest.main()
