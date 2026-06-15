# Tax Exemption Review Rules

## Decision Policy

Approve only when all approval checks pass:

- Submitted application is pending.
- Certificate file is accessible and readable.
- Certificate state matches submitted `state_code` or `state_name`.
- Certificate organization/customer name reasonably matches submitted `organization_name`.
- Certificate Tax ID / Exempt ID matches at least one submitted identifier: `state_tax_number` or `exemption_num`.
- Certificate is currently valid and not visibly expired, revoked, void, sample-only, or incomplete.
- Expiration date can be computed by the rules below.
- OCR/vision confidence is high enough to support the decision.

Return `status=rejected` for everything else and write the result through the audit API.

## Speed Rules

1. State mismatch is an early stop.
   - If certificate state is confidently extracted and differs from submitted state, stop and return `status=rejected`.
   - If certificate state cannot be extracted, continue only if other OCR evidence is strong enough; otherwise return `status=rejected`.

2. Avoid full document reasoning until needed.
   - Use metadata and submitted state first.
   - Use deterministic PDF text extraction before image OCR.
   - OCR only certificate pages or images that contain text.

3. Batch cautiously.
   - Fetch small batches.
   - Approve one item at a time after producing evidence.
   - Do not bulk approve without per-item evidence.
   - Count every reviewed item as `approved` or `rejected`.

## Field Normalization

- State: compare both two-letter code and full name when available. Normalize case, spaces, and punctuation.
- Organization name: normalize case, punctuation, legal suffixes, and repeated spaces. Accept clear variants such as `Inc` vs `Incorporated`; reject when the entity appears different.
- Tax ID / Exempt ID: ignore spaces, hyphens, and casing for comparison. Do not approve if all IDs are missing.
- Dates: parse common US date formats. If only a year/month is present, return `status=rejected` unless the certificate explicitly states a policy that resolves the date.

## Expiration Rules

Return `expired_at` as `YYYY-MM-DD 23:59:59` in US Eastern business time unless the certificate provides a more precise end time. This value is the certificate effective cutoff date, not the audit time.

1. Explicit expiration date exists:
   - Use the certificate expiration date.

2. No explicit expiration date, but issue/signature date exists:
   - Use issue/signature date plus one year.

3. No explicit expiration date and no issue/signature date:
   - Use submitted `created_at` plus one year.

If a computed expiration date is already in the past, return `status=rejected` .

## Refuse Reason Mapping

Use one of the three standard `refuse_reason` strings whenever possible:

1. Expired certificate:
   - Use `the submitted tax exemption certificate is expired.`
   - Applies when the certificate explicitly expired or the computed expiration date is already in the past.

2. Invalid tax exemption certificate:
   - Use `the document provided is not a valid tax exemption certificate.`
   - Applies when the document is not a tax exemption certificate, state mismatches, organization mismatches, Tax ID / Exempt ID mismatches, required certificate fields are missing, the certificate is revoked/void/sample-only, or the document cannot prove exemption validity.

3. Unclear certificate image:
   - Use `the image of the certificate is unclear and cannot be verified.`
   - Applies when the image/PDF scan is blurry, OCR confidence is low, or key fields cannot be read.

Use a specific non-standard reason only for technical cases not covered by the three standard reasons, such as a missing or inaccessible certificate file. For example, `certificate file is missing or inaccessible.`

Keep detailed internal analysis in the run summary, not in `refuse_reason`.

## Required Summary

After processing a batch, report:

- Total pending records processed.
- Approved count.
- Rejected count.
- Skipped/error count.
- Rejected IDs, standard refuse reasons, and concise internal details requiring human follow-up.
