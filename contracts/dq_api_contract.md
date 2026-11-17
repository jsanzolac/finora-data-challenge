# DQ dashboard ↔ API contract (v1)

Shared by the ETL/API builder (`infra/`, `etl/`, `auth/`, `dq_api/`) and the dashboard builder (`dashboard/`). Source: the approved plan (2026-11-16). **Change it only by agreement, and bump the version.**

## Conventions

- **Same origin.** CloudFront serves the static dashboard at `/` and routes `/api/*` to the HTTP API, so there is no CORS.
- **Session:** an HttpOnly, Secure, `SameSite=Strict` cookie named `dq_session`, set by `POST /api/auth/login`. The frontend never reads it. It calls `fetch(url, { credentials: "same-origin" })`.
- **Errors:** JSON `{ "error": { "code": string, "message": string } }`.
  - `401`: no or expired session. The frontend redirects to `/login`.
  - `403`: the role is not allowed, or a password change is required (`code: "password_change_required"`).
  - `404`: unknown run, rule or dataset.
  - `429`: rate limited (login).
- **Types:**
  - Numbers are JSON numbers, and percentages are 0–100 with up to 2 decimals.
  - Money and raw values inside `records[].values` are **strings exactly as in the source**, never re-formatted.
  - Timestamps are ISO-8601 UTC (`2026-11-16T04:10:00Z`), and months are `YYYY-MM`.
- **Dataset ids and labels:** `transactions` "Transactions", `industry` "Industry", `sm_spend` "S&M spend". The labels come from the API (config) and must not be hard-coded in the UI.
- **Roles:** `data`, `finance` and `revops`. Only `finance` sees the HR-sensitive S&M columns (`Team`, `PayrollExpenses`, `Freelance`). For everyone else the API returns the value `"__restricted__"`, and the UI shows "Restricted".

## Auth

| Method and path | Request | 200 response |
|---|---|---|
| `POST /api/auth/login` | `{ "email": string, "password": string }` | `{ "user": User }` and sets the cookie |
| `POST /api/auth/logout` | — | `{ "ok": true }` and clears the cookie |
| `GET /api/auth/session` | — | `{ "user": User }` (401 if there is no session) |
| `POST /api/auth/password` | `{ "current": string, "new": string }` (new: ≥ 12 characters) | `{ "user": User }` |

`User = { "email": string, "role": "data" | "finance" | "revops", "must_change_password": boolean }`

While `must_change_password` is true, every `/api/dq/*` call returns 403 `password_change_required`.

## DQ endpoints

### `GET /api/dq/runs`

Newest first.

```json
[
  {
    "run_id": "r20261116T041000Z",
    "started_at": "2026-11-16T04:10:00Z",
    "finished_at": "2026-11-16T04:11:12Z",
    "as_of_month": "2024-10",
    "status": "succeeded",
    "datasets": {
      "transactions": { "source_key": "transactions/Transactions.csv", "sha256": "…", "rows_read": 66674 },
      "industry":     { "source_key": "industry/Industry.csv",         "sha256": "…", "rows_read": 1962 },
      "sm_spend":     { "source_key": "s_and_m/S&M_spend.csv",         "sha256": "…", "rows_read": 34 }
    }
  }
]
```

`status`: `succeeded` | `failed`. Only `succeeded` runs have summaries.

### `GET /api/dq/summary?run=latest|<run_id>`

```json
{
  "run": { "...": "same object as one entry of /api/dq/runs" },
  "datasets": [
    {
      "dataset_id": "industry",
      "label": "Industry",
      "rows_read": 1962,
      "rows_excluded": 1,
      "rows_flagged": 0,
      "row_compliance_pct": 99.95,
      "rules_evaluated": 6,
      "rules_failing": 1,
      "rank": 3
    }
  ],
  "rules": [
    {
      "rule_id": "SQ-02",
      "title": "Empty records",
      "description": "full rule text from approved_data_rules.md",
      "layer": "silver_quality",
      "kind": "row",
      "action": "exclude",
      "inferred": false,
      "counts_toward_compliance": true,
      "applies_to": ["transactions", "industry", "sm_spend"],
      "results": {
        "transactions": { "evaluated": 66674, "failed": 0, "compliance_pct": 100.0, "status": "pass" },
        "industry":     { "evaluated": 1962,  "failed": 1, "compliance_pct": 99.95, "status": "warn" },
        "sm_spend":     { "evaluated": 34,    "failed": 0, "compliance_pct": 100.0, "status": "pass" }
      }
    }
  ],
  "trend": [
    { "run_id": "r20261116T041000Z", "as_of_month": "2024-10", "transactions": 100.0, "industry": 99.95, "sm_spend": 100.0 }
  ]
}
```

- **`layer`:** `bronze` | `silver_quality` | `silver_business`.
- **`kind`:** `row` (it evaluates existing rows) | `finding` (an absence or a cross-row fact, such as a missing customer-month or a month gap). For `finding`, `evaluated` is the number of expected items and `failed` the number of findings.
- **`action`:** `exclude` (the row is kept out of silver and stored) | `flag` (the row stays in silver, flagged) | `finding`.
- **`status`:** `pass` | `warn` | `fail` | `na`. The thresholds are defined in `docs/approved_data_rules.md`. For a dataset not in `applies_to`, the result is `{ "evaluated": 0, "failed": 0, "compliance_pct": null, "status": "na" }`.
- **`datasets`:** sorted by `rank` (1 = most compliant). `trend` is oldest first, with up to 24 runs.

### `GET /api/dq/rules/{rule_id}/datasets/{dataset_id}/records?run=latest|<run_id>&page=1&page_size=50&q=`

- `page_size` is at most 200.
- `q` is a case-insensitive substring match over the key, the values and the reason.

```json
{
  "rule_id": "SQ-02",
  "dataset_id": "industry",
  "run_id": "r20261116T041000Z",
  "total": 1,
  "page": 1,
  "page_size": 50,
  "columns": ["ID", "Industria"],
  "records": [
    {
      "source_line": 1963,
      "key": { "ID": "" },
      "values": { "ID": "", "Industria": "" },
      "failed_columns": ["ID", "Industria"],
      "reason": "EMPTY_RECORD: every source column is empty",
      "action": "exclude",
      "other_failed_rules": []
    }
  ]
}
```

- **`source_line`:** 1-based line in the source file. The header is line 1.
- **`columns`:** the source columns in file order, without `_ingested_at`.
- **For a `finding` rule:** `source_line` is `null`, `key` identifies the missing or affected item (for example `{ "ID": "94", "month": "2023-05" }`), and `values` is `{}`.

## Serving store layout (built by the ETL, read by the API Lambda)

```
s3://al-test-dl-serving/dq/latest.json                                  {"run_id": "...", "published_at": "..."}  (written last)
s3://al-test-dl-serving/dq/runs.json                                    (the /api/dq/runs payload)
s3://al-test-dl-serving/dq/runs/<run_id>/summary.json                   (the /api/dq/summary payload, unmasked)
s3://al-test-dl-serving/dq/runs/<run_id>/records/<rule_id>/<dataset_id>/page-<n>.json   (200 records per page, unmasked)
```

The API Lambda applies role masking and the `q` and `page_size` handling.

## Mock data

The dashboard ships contract-shaped fixtures in `dashboard/mocks/`, including planted failures across all three datasets. A dev-only mock mode is enabled with `NEXT_PUBLIC_DQ_MOCKS=1`.
