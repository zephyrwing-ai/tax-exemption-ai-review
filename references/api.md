# Friday Tax Exemption External API

This reference documents backend APIs used by the skill. The local helper script uses the Friday production backend by default. Provide credentials at runtime through `--api-key` or `TAX_EXEMPTION_API_KEY`.

## Environments

- Development: `http://localhost:6006`
- Production: `https://oms.fridayparts.com`
- Test: `https://jd.test.jeeda.net`

## Authentication

Pass the backend API key in the request header:

```http
X-API-Key: <runtime key>
```

The backend key is only for this backend header. It is not an OCR or AI model API key.

## Fetch Pending Applications

```http
GET /api/external/tax/exemption/pending
Use the production environment by default: `https://oms.fridayparts.com`.
X-API-Key: <runtime key>
```

Optional query parameters:

- `page`: page number.
- `size`: page size.

Successful response:

```json
{
  "code": 0,
  "message": "",
  "data": {
    "count": 2,
    "enable_create": false,
    "list": [
      {
        "cert_url": "",
        "country_code": "US",
        "created_at": "2024-12-26 16:53:29",
        "customer_id": 11,
        "email": "summer@fridayparts.com",
        "exemption_id": 2,
        "exemption_num": "",
        "exemption_type": "other",
        "operation_type": "Other",
        "organization_name": "Example Org",
        "state_code": "OR",
        "state_name": "Oregon",
        "state_tax_number": "ABC123",
        "status": "pending"
      }
    ]
  }
}
```

Use only records whose status is `pending`. Treat missing or empty `cert_url` as manual review.
For the test environment, `cert_url` may use the CDN prefix `https://media.test.jeeda.net/`.
If that CDN URL returns `403 AccessDenied`, retry the same object key through
`https://jeeda-media.s3.us-west-2.amazonaws.com/` before deciding the file is
inaccessible.

## Audit Application

```http
PUT /api/external/tax/exemption/{id}/audit
Content-Type: application/json
X-API-Key: <runtime key>

{
  "status": "approved",
  "expired_at": "2026-12-31 23:59:59"
}
```

Rejected request:

```http
PUT /api/external/tax/exemption/{id}/audit
Content-Type: application/json
X-API-Key: <runtime key>

{
  "status": "rejected",
  "expired_at": "2026-06-11 09:08:07",
  "refuse_reason": "the document provided is not a valid tax exemption certificate."
}
```

Response:

```json
{
  "code": 0,
  "message": "",
  "data": "audit success"
}
```

Call this endpoint for both `approved` and `rejected` audit results.

## Request Fields

The audit endpoint supports:

- `status`
- `expired_at`
- `refuse_reason`

Rules:

- `status` is always required and must be `approved` or `rejected`.
- `expired_at` is required when `status=approved`.
- `refuse_reason` is required when `status=rejected`.
- For `status=rejected`, send `expired_at` as the current local datetime in
  `YYYY-MM-DD HH:mm:ss` format to satisfy the backend validator.
- Do not send dummy epoch values such as `1970-01-01 00:00:00`.
- `refuse_reason` must be 500 characters or fewer.
- Use only this audit endpoint for writeback; do not call an `ai-review` endpoint.
- Prefer a dry-run payload preview before writeback.

## Standard Refuse Reasons

Prefer exactly one of these strings for rejected cases:

- `the submitted tax exemption certificate is expired.`
- `the document provided is not a valid tax exemption certificate.`
- `the image of the certificate is unclear and cannot be verified.`

Use a specific non-standard reason only for technical cases not covered by the three standard reasons, such as `certificate file is missing or inaccessible.`
