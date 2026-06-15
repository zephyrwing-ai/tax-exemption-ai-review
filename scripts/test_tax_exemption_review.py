import argparse
import datetime as dt
import os
import unittest
from unittest import mock

import tax_exemption_review as review


class ApiKeyTests(unittest.TestCase):
    def test_load_api_key_requires_runtime_key(self):
        args = argparse.Namespace(api_key=None, api_key_env="MISSING_TEST_KEY")

        with mock.patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(SystemExit):
                review.load_api_key(args)

    def test_load_api_key_uses_runtime_env_key(self):
        args = argparse.Namespace(api_key=None, api_key_env="TAX_EXEMPTION_API_KEY")

        with mock.patch.dict(os.environ, {"TAX_EXEMPTION_API_KEY": "prod-key"}, clear=True):
            self.assertEqual(review.load_api_key(args), "prod-key")


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
            base_url=review.DEFAULT_BASE_URL,
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
        self.assertIn('"url": "https://oms.fridayparts.com/api/external/tax/exemption/123/audit"', printed)
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


class ExpiryTests(unittest.TestCase):
    def test_parse_date_uses_eastern_business_timezone(self):
        parsed = review.parse_date("2026-06-16")

        self.assertEqual(parsed.tzinfo.key, "America/New_York")
        self.assertEqual(parsed.strftime("%Y-%m-%d %H:%M:%S"), "2026-06-16 23:59:59")

    def test_expiry_outputs_eastern_business_end_of_day_string(self):
        args = argparse.Namespace(
            explicit_expiration="2026-06-16",
            issue_date=None,
            submitted_at=None,
        )

        with mock.patch("tax_exemption_review.print") as print_mock:
            review.cmd_expiry(args)

        printed = print_mock.call_args.args[0]
        self.assertIn('"expired_at": "2026-06-16 23:59:59"', printed)
        self.assertIn('"source": "explicit_expiration"', printed)


if __name__ == "__main__":
    unittest.main()
