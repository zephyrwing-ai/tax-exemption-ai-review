#!/usr/bin/env python3
"""Helpers for Friday tax exemption AI review.

This script keeps API calls, downloads, date calculation, and JSON scaffolding
deterministic so weaker models can focus on review decisions.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict, Optional


DEFAULT_KEY_ENV = "TAX_EXEMPTION_API_KEY"
DEFAULT_API_KEY = "fW2eKh3wsBqMtOHQ6jyYn8xpiPZvaVXb"
TEST_CDN_PREFIX = "https://media.test.jeeda.net/"
TEST_S3_PREFIX = "https://jeeda-media.s3.us-west-2.amazonaws.com/"


def load_api_key(args: argparse.Namespace) -> str:
    api_key = args.api_key or os.environ.get(args.api_key_env or DEFAULT_KEY_ENV, "") or DEFAULT_API_KEY
    if not api_key:
        raise SystemExit(
            f"Missing API key. Pass --api-key or set {args.api_key_env or DEFAULT_KEY_ENV}."
        )
    return api_key


def request_json(method: str, url: str, api_key: str, payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    data = None
    headers = {"X-API-Key": api_key, "Accept": "application/json"}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"

    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = resp.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise SystemExit(f"HTTP {exc.code} from {url}: {body}") from exc
    except urllib.error.URLError as exc:
        raise SystemExit(f"Request failed for {url}: {exc}") from exc

    try:
        return json.loads(body)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Response was not JSON from {url}: {body[:500]}") from exc


def normalize_base_url(base_url: str) -> str:
    return base_url.rstrip("/")


def format_api_datetime(value: dt.datetime) -> str:
    return value.strftime("%Y-%m-%d %H:%M:%S")


def build_audit_payload(args: argparse.Namespace, now=dt.datetime.now) -> Dict[str, Any]:
    payload: Dict[str, Any] = {"status": args.status}
    if args.status == "approved":
        if not args.expired_at:
            raise SystemExit("--expired-at is required when --status approved.")
        payload["expired_at"] = args.expired_at
        return payload

    if args.status == "rejected":
        if not args.refuse_reason:
            raise SystemExit("--refuse-reason is required when --status rejected.")
        if len(args.refuse_reason) > 500:
            raise SystemExit("--refuse-reason must be 500 characters or fewer.")
        payload["expired_at"] = args.expired_at or format_api_datetime(now())
        payload["refuse_reason"] = args.refuse_reason
        return payload

    raise SystemExit("--status must be approved or rejected.")


def fallback_download_urls(url: str) -> list[str]:
    urls = [url]
    if "{{" in url or "}}" in url:
        return urls
    if url.startswith(TEST_CDN_PREFIX):
        urls.append(TEST_S3_PREFIX + url[len(TEST_CDN_PREFIX):])
    return urls


def cmd_pending(args: argparse.Namespace) -> None:
    api_key = load_api_key(args)
    url = f"{normalize_base_url(args.base_url)}/api/external/tax/exemption/pending"
    params = {}
    if args.page is not None:
        params["page"] = str(args.page)
    if args.size is not None:
        params["size"] = str(args.size)
    if params:
        url = url + "?" + urllib.parse.urlencode(params)
    print(json.dumps(request_json("GET", url, api_key), ensure_ascii=False, indent=2))


def cmd_audit(args: argparse.Namespace) -> None:
    url = f"{normalize_base_url(args.base_url)}/api/external/tax/exemption/{args.id}/audit"
    payload = build_audit_payload(args)
    if args.dry_run:
        print(json.dumps({"method": "PUT", "url": url, "payload": payload}, ensure_ascii=False, indent=2))
        return
    api_key = load_api_key(args)
    print(json.dumps(request_json("PUT", url, api_key, payload), ensure_ascii=False, indent=2))


def cmd_download(args: argparse.Namespace) -> None:
    errors = []
    content = None
    source_url = ""
    for candidate_url in fallback_download_urls(args.url):
        req = urllib.request.Request(candidate_url, headers={"User-Agent": "tax-exemption-ai-review/1.0"})
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                content = resp.read()
            source_url = candidate_url
            break
        except Exception as exc:
            errors.append(f"{candidate_url}: {exc}")
    if content is None:
        raise SystemExit("Download failed: " + " | ".join(errors))

    out = Path(args.out).expanduser()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(content)
    print(json.dumps({"path": str(out), "bytes": len(content), "source_url": source_url}, indent=2))


def parse_date(value: str) -> dt.datetime:
    value = value.strip()
    formats = [
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d",
        "%m/%d/%Y",
        "%m-%d-%Y",
        "%B %d, %Y",
        "%b %d, %Y",
    ]
    for fmt in formats:
        try:
            parsed = dt.datetime.strptime(value, fmt)
            if "%H" not in fmt:
                parsed = parsed.replace(hour=23, minute=59, second=59)
            return parsed
        except ValueError:
            pass
    raise SystemExit(f"Unsupported date format: {value}")


def add_one_year(value: dt.datetime) -> dt.datetime:
    try:
        return value.replace(year=value.year + 1)
    except ValueError:
        return value.replace(month=2, day=28, year=value.year + 1)


def cmd_expiry(args: argparse.Namespace) -> None:
    source = ""
    if args.explicit_expiration:
        expiry = parse_date(args.explicit_expiration)
        source = "explicit_expiration"
    elif args.issue_date:
        expiry = add_one_year(parse_date(args.issue_date))
        source = "issue_date_plus_one_year"
    elif args.submitted_at:
        expiry = add_one_year(parse_date(args.submitted_at))
        source = "submitted_at_plus_one_year"
    else:
        raise SystemExit("Provide --explicit-expiration, --issue-date, or --submitted-at.")

    expiry = expiry.replace(hour=23, minute=59, second=59)
    print(json.dumps({"expired_at": expiry.strftime("%Y-%m-%d %H:%M:%S"), "source": source}, indent=2))


def cmd_draft(args: argparse.Namespace) -> None:
    item = json.loads(Path(args.item_json).expanduser().read_text())
    ocr_text = ""
    if args.ocr_text:
        ocr_text = Path(args.ocr_text).expanduser().read_text(errors="replace")
    draft = {
        "exemption_id": item.get("exemption_id"),
        "submitted": {
            "organization_name": item.get("organization_name", ""),
            "state_code": item.get("state_code", ""),
            "state_name": item.get("state_name", ""),
            "state_tax_number": item.get("state_tax_number", ""),
            "exemption_num": item.get("exemption_num", ""),
            "created_at": item.get("created_at", ""),
            "cert_url": item.get("cert_url", ""),
        },
        "certificate_extracted": {
            "certificate_state": "",
            "certificate_organization_name": "",
            "certificate_tax_id_or_exempt_id": "",
            "certificate_validity_status": "unknown",
            "explicit_expiration_date": "",
            "issue_or_signature_date": "",
            "ocr_confidence": "unknown",
            "evidence": [],
        },
        "ocr_text_preview": ocr_text[:2000],
        "status": "rejected",
        "expired_at": "",
        "refuse_reason": "",
        "checks": {
            "state": "unknown",
            "organization_name": "unknown",
            "tax_or_exempt_id": "unknown",
            "validity": "unknown",
            "dates": "unknown",
        },
    }
    print(json.dumps(draft, ensure_ascii=False, indent=2))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Friday tax exemption AI review helper")
    parser.add_argument("--api-key", help="Backend X-API-Key. Prefer env var instead.")
    parser.add_argument("--api-key-env", default=DEFAULT_KEY_ENV, help="Environment variable for backend API key.")

    sub = parser.add_subparsers(dest="command", required=True)

    pending = sub.add_parser("pending", help="Fetch pending exemption applications")
    pending.add_argument("--base-url", required=True)
    pending.add_argument("--page", type=int)
    pending.add_argument("--size", type=int)
    pending.set_defaults(func=cmd_pending)

    audit = sub.add_parser("audit", help="Write approved or rejected audit result")
    audit.add_argument("--base-url", required=True)
    audit.add_argument("--id", required=True)
    audit.add_argument("--status", choices=["approved", "rejected"], required=True)
    audit.add_argument("--expired-at")
    audit.add_argument("--refuse-reason")
    audit.add_argument("--dry-run", action="store_true")
    audit.set_defaults(func=cmd_audit)

    download = sub.add_parser("download", help="Download certificate file")
    download.add_argument("--url", required=True)
    download.add_argument("--out", required=True)
    download.set_defaults(func=cmd_download)

    expiry = sub.add_parser("expiry", help="Compute expiration date")
    expiry.add_argument("--explicit-expiration")
    expiry.add_argument("--issue-date")
    expiry.add_argument("--submitted-at")
    expiry.set_defaults(func=cmd_expiry)

    draft = sub.add_parser("draft", help="Create structured review draft JSON")
    draft.add_argument("--item-json", required=True)
    draft.add_argument("--ocr-text")
    draft.set_defaults(func=cmd_draft)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
