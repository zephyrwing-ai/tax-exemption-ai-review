---
name: tax-exemption-ai-review
description: >-
  Review FridayParts tax exemption certificate applications with AI/OCR assistance.
  Use when asked to fetch pending tax exemption applications, inspect exemption certificate
  files, compare certificate fields against submitted customer data, decide whether the
  audit status should be approved or rejected, compute expiration dates, call the external
  audit API, or summarize approved and rejected review results for human follow-up.
---

# Tax Exemption AI Review

## Goal

Review pending tax exemption applications quickly and conservatively. Use only the Friday external pending and audit APIs. Write every reviewed item back through the audit API with `status=approved` or `status=rejected`.

## Required References

- Read `references/api.md` before making backend requests.
- Read `references/review-rules.md` before deciding approval or expiration.
- Use `scripts/tax_exemption_review.py` for repeatable API calls, downloads, expiry calculation, and review JSON scaffolding.

## Credentials

- Treat the backend API key as the `X-API-Key` header for the Friday external tax exemption APIs.
- The helper script uses the Friday production backend by default: `https://oms.fridayparts.com`.
- Provide the backend API key at runtime with `--api-key` or `TAX_EXEMPTION_API_KEY`.
- Do not store AI/OCR provider keys in this skill or in generated review artifacts.
- AI/OCR provider keys are separate from the backend `X-API-Key`. Do not put AI service credentials in `references/api.md`.

## Fast Workflow

1. Fetch pending applications.
   - Use the production backend by default: `https://oms.fridayparts.com`.
   - Fetch pending applications with `GET /api/external/tax/exemption/pending`.
   - The API supports `page` and `size`; keep fetching pages/batches until the pending count is exhausted or the user-specified scope is complete.
   - Process only items with `status=pending`.
   - If `cert_url` is missing or contains unresolved placeholders such as `{{file_url}}` or `{{file_path}}`, write `status=rejected` with a concise technical reason because the standard three refusal reasons do not cover missing files.
   - If a test `cert_url` under `https://media.test.jeeda.net/` returns `403 AccessDenied`, retry the same object key through `https://jeeda-media.s3.us-west-2.amazonaws.com/` before deciding the file is inaccessible.

2. Precheck submitted metadata before reading the certificate.
   - Required submitted fields: `organization_name`, `state_code` or `state_name`, and at least one of `state_tax_number` or `exemption_num`.
   - If submitted metadata is incomplete enough that the certificate cannot be validated, write `status=rejected` with `the document provided is not a valid tax exemption certificate.`
   - If the certificate URL is absent or inaccessible, write `status=rejected` with a specific technical reason.

3. Download and extract certificate content.
   - Prefer deterministic extraction first: PDF text extraction for PDFs, OCR/vision for images or scanned PDFs.
   - For weak models, do not ask the model to inspect raw images unaided. Use a stronger vision/OCR provider, local OCR tool, or user-provided extracted text, then continue from structured fields.
   - If OCR confidence is low or key fields are unreadable, write `status=rejected` with `the image of the certificate is unclear and cannot be verified.`

4. Compare certificate fields against submitted data.
   - Compare state first; this is the fastest rejection-to-manual signal.
   - Compare organization/customer name with normalization.
   - Compare Tax ID / Exempt ID against `state_tax_number` and `exemption_num`.
   - Determine whether the certificate is valid, revoked, expired, incomplete, or ambiguous.
   - Extract explicit expiration date and issue/signature date when present.

5. Decide outcome.
   - `approved`: only when state, name/organization, ID, and validity evidence are all clear enough.
   - `rejected`: for every mismatch, missing field, weak OCR, unreadable file, ambiguous date, expired certificate, or unsupported certificate type.
   - Treat every `rejected` item as requiring human follow-up in the run summary.
   - Do not treat a transport check, API smoke test, or URL reachability check as a completed audit.

6. Write back results.
   - For approved cases, call `PUT /api/external/tax/exemption/{id}/audit` with `status=approved` and `expired_at`.
   - For rejected cases, call the same audit API with `status=rejected`, `expired_at`, and `refuse_reason`.
   - For rejected cases, set `expired_at` to the current local datetime in `YYYY-MM-DD HH:mm:ss` format. This field is operationally required by the backend validator even though business meaning comes from the rejected status and refusal reason.
   - Never use dummy epoch values such as `1970-01-01 00:00:00`.
   - Keep `refuse_reason` to 500 characters or fewer.
   - Dry-run or print the writeback payload before any batch write. For real audits, inspect files and produce per-item evidence before writing results.
   - Use only the two provided backend APIs; do not invent or call an `ai-review` endpoint.

7. Summarize the run.
   - Report processed count, approved count, rejected count, and the IDs/reasons requiring manual review.

## Weak-Model Guardrails

Use this structure even if the active model has poor OCR:

1. Never rely on freeform visual impressions when approving.
2. Require extracted fields in this shape before approval:

```json
{
  "certificate_state": "",
  "certificate_organization_name": "",
  "certificate_tax_id_or_exempt_id": "",
  "certificate_validity_status": "valid|expired|revoked|unknown",
  "explicit_expiration_date": "",
  "issue_or_signature_date": "",
  "ocr_confidence": "high|medium|low",
  "evidence": []
}
```

3. If the active model cannot produce this structure from the document with high confidence, use OCR/vision tooling or ask for extracted text. If still uncertain, write `status=rejected` with the unclear-image standard reason.
4. Use exact values and short evidence snippets; do not invent missing dates or IDs.
5. Fail closed: uncertainty means manual review, not approval.

## API Helper

Examples:

```bash
python3 ~/.codex/skills/tax-exemption-ai-review/scripts/tax_exemption_review.py \
  pending --page 1 --size 20

python3 ~/.codex/skills/tax-exemption-ai-review/scripts/tax_exemption_review.py \
  download --url "<cert_url from pending response>" --out "/tmp/tax-exemption-<exemption_id>"

python3 ~/.codex/skills/tax-exemption-ai-review/scripts/tax_exemption_review.py \
  draft --item-json /tmp/item.json --ocr-text /tmp/ocr.txt

python3 ~/.codex/skills/tax-exemption-ai-review/scripts/tax_exemption_review.py \
  expiry --explicit-expiration "2026-12-31" --submitted-at "2026-06-10 12:00:00"

python3 ~/.codex/skills/tax-exemption-ai-review/scripts/tax_exemption_review.py \
  audit --id 123 \
  --status approved --expired-at "2026-12-31 23:59:59" --dry-run

python3 ~/.codex/skills/tax-exemption-ai-review/scripts/tax_exemption_review.py \
  audit --id 123 \
  --status rejected --refuse-reason "the document provided is not a valid tax exemption certificate." \
  --dry-run
```


## Run summary

After processing, output only:

```json
{
  "processed_count": 0,
  "approved_count": 0,
  "rejected_count": 0,
  "rejected_items": [
    {
      "exemption_id": 0,
      "refuse_reason": ""
    }
  ]
}
```
