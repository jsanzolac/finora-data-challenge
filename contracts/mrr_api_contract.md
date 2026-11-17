# MRR dashboard ↔ API contract (v1)

**Draft by the dashboard CTO (2026-11-17), for the coordinator to review and finalize.** It isn't binding until it's renamed `mrr_api_contract.md` and given v1. The definitions belong to the CDO in `docs/mrr_discounts_model.md`, which didn't exist when this was drafted. Every term marked *(CDO)* below is a placeholder that file must confirm or replace. Page design: `dashboard/docs/mrr_page_design.md`.

Everything in `contracts/dq_api_contract.md` "Conventions" applies unchanged: same origin, the `dq_session` cookie, the error shape `{ "error": { "code", "message" } }`, 401 → `/login`, 403 `password_change_required` (also on `/api/mrr/*`), the roles `data` / `finance` / `revops`, ISO-8601 UTC timestamps and `YYYY-MM` months. There are no HR-sensitive values here, so `"__restricted__"` isn't used.


## v1 decisions (coordinator, 2026-11-17). These override anything below that conflicts.

1. **Definitions come from the CDO** (`docs/mrr_discounts_model.md`, including its "Gold build spec" section). Every *(CDO)* placeholder below is settled by that document.
2. **Basis.** `run.mrr_basis` = `"cash_proxy"` today: MRR = silver `amount_normalized`, as in CDO §5. It becomes `"net_mrr"` when billing data lands. The UI shows "Based on payments (proxy until billing data)" in Details when the value is `cash_proxy`.
3. **Steps are metadata-driven.** The backend sends the CDO's `movement_type` codes in `steps` (for example `list_price_increase` / `list_price_decrease`, and `discount_start`, `discount_change`, `discount_base_effect`, `discount_end`, `discount_end_early`, `discount_released_on_churn`). The UI renders whatever `steps` lists, in `order`, grouped by `driver`. It must not hard-code step codes, except to style the `discount` driver as "Not available" while `drivers[].available` is false. The step codes in the example below are illustrative.
4. **Inferred flags.** Each movement row in `/api/mrr/movements` carries `"flags": []`, which may hold `late_price_step`, `temporary_dip`, `one_off_spike` or `candidate_list_price_change` (CDO §5). Inferred steps carry `"inferred": true`. The UI shows flags only in Details or the drill-down.
5. **Serving store** (written by the gold MRR job last, only on success; it never touches `dq/*` or `acq/*`):
   - `s3://al-test-dl-serving/mrr/latest.json` → `{run_id, published_at}`
   - `s3://al-test-dl-serving/mrr/runs/<run_id>/summary.json`: the `/api/mrr/summary` payload
   - `s3://al-test-dl-serving/mrr/runs/<run_id>/movements/page-<n>.json`: every movement row with a non-zero change, sorted by |change| descending, 200 per page. The API filters and pages from these.
6. **API.** `/api/mrr/*` routes are added to the existing `finora-dq-api` Lambda later, as a separate approved change. Until then the page uses mocks only.


## Types (as in `acq_api_contract.md` v1.1)

- **Money** is a JSON string holding an exact decimal in full units (revenue × 10,000), or `null` where the value isn't known. **`null` never means 0.** Field names end in `_value`. The UI sums with exact decimals and rounds HALF_UP only for display.
- **Counts** are integers.
- **Currency** is not stated. The UI shows "Currency not stated" once, in Details.
- **Signs.** A step value is signed: increases are positive and decreases negative (churn and contraction are negative). Opening and closing are levels.

## Definitions the backend applies *(CDO)*

- **MRR(m)** = Σ `amount_normalized_value` over customer-months of m with `lifecycle_state` in (`new`, `paying`, `reactivated`), where `amount_normalized_value` = silver `amount_normalized` × 10,000. This is the normalized basis: catch-ups, prepays, splits and uneven splits are spread over the months they cover (CRO-03, SB-11).
- **Cash(m)** = Σ `amount_value` of the month, as paid.
- **Timing(m)** = Cash(m) − MRR(m). It's a level, not part of MRR. **Timing change** over a period = Timing(last) − Timing(month before first).
- **Identities (run controls; the UI tests them too):**
  - **Month bridge:** `opening_mrr_value` + Σ step values = `closing_mrr_value`, exact.
  - **Continuity:** `closing_mrr_value`(m) = `opening_mrr_value`(m+1).
  - **Period:** Σ behaviour + Σ pricing + Σ discount + timing change = Cash(last) − Cash(month before first).
- **Steps** (gold `fact_mrr_movement`: `movement_type` × `driver`):
  - **Behaviour:**
    - `new`: first payment of a new logo;
    - `reactivation`: SB-07;
    - `expansion` and `contraction`: CRO-05 on `amount_normalized`, **minus** the part attributed to pricing or discounts;
    - `churn`: the MRR of the month before the first churned month (SB-05).
  - **Pricing (inferred):** `price_increase` and `price_decrease`. A change between consecutive paying months that matches a price step applied to many customers in the same month (the "0.21 price grid"; detection rule *(CDO)*). Every value carries `inferred: true`.
  - **Discount:** `discount_start`, `discount_end`, `discount_change`. These need list price and discount per invoice line. They are **`null` until billing data exists**.
- **List MRR(m)** = MRR at list price. **Discount(m)** = list MRR − MRR, ≥ 0. **Leakage** = Discount. All three are `null` today.
- **Provisional.** Months after `churn_confirmed_through` (SB-05: `as_of_month` − 2) have `is_provisional: true`. Their churn step can still change.

## `GET /api/mrr/summary?run=latest|<run_id>`

Roles: all three. 404 `no_gold_run` before the first publish; 404 `unknown_run` for an unknown id.

```json
{
  "run": {
    "run_id": "r20261118T040000Z",
    "silver_run_id": "r20261117T150932Z",
    "built_at": "2026-11-18T04:08:00Z",
    "as_of_month": "2024-10",
    "data_complete_through": "2024-10",
    "churn_confirmed_through": "2024-08",
    "gold_model_version": "sha256:…",
    "mrr_basis": "cash_proxy"
  },
  "statuses": {
    "currency_status": "unconfirmed",
    "revenue_basis_status": "unconfirmed",
    "pricing_status": "inferred",
    "discount_data_status": "not_available",
    "list_price_status": "not_available"
  },
  "drivers": [
    { "code": "behaviour", "label": "Customer behaviour", "inferred": false, "available": true },
    { "code": "pricing",   "label": "Pricing",            "inferred": true,  "available": true },
    { "code": "discount",  "label": "Discounts",          "inferred": false, "available": false },
    { "code": "timing",    "label": "Timing of payments", "inferred": false, "available": true, "in_mrr": false }
  ],
  "steps": [
    { "code": "new",             "label": "New",               "driver": "behaviour", "order": 1 },
    { "code": "reactivation",    "label": "Reactivation",      "driver": "behaviour", "order": 2 },
    { "code": "expansion",       "label": "Expansion",         "driver": "behaviour", "order": 3 },
    { "code": "contraction",     "label": "Contraction",       "driver": "behaviour", "order": 4 },
    { "code": "churn",           "label": "Churn",             "driver": "behaviour", "order": 5 },
    { "code": "price_increase",  "label": "Price increases",   "driver": "pricing",   "order": 6 },
    { "code": "price_decrease",  "label": "Price decreases",   "driver": "pricing",   "order": 7 },
    { "code": "discount_start",  "label": "Discounts started", "driver": "discount",  "order": 8 },
    { "code": "discount_end",    "label": "Discounts ended",   "driver": "discount",  "order": 9 },
    { "code": "discount_change", "label": "Discount changes",  "driver": "discount",  "order": 10 }
  ],
  "months": [
    {
      "month": "2024-10",
      "opening_mrr_value": "92788811.00",
      "closing_mrr_value": "96360647.00",
      "cash_value": "97007447.00",
      "timing_value": "646800.00",
      "step_value": {
        "new": "3100000.00", "reactivation": "180000.00", "expansion": "2129004.00",
        "contraction": "-1681735.00", "churn": "-155433.00",
        "price_increase": "0.00", "price_decrease": "0.00",
        "discount_start": null, "discount_end": null, "discount_change": null
      },
      "step_customers": { "new": 50, "reactivation": 3, "expansion": 151, "contraction": 129, "churn": 14,
                          "price_increase": 0, "price_decrease": 0,
                          "discount_start": null, "discount_end": null, "discount_change": null },
      "customers_opening": 1645,
      "customers_closing": 1678,
      "list_mrr_value": null,
      "discount_value": null,
      "is_provisional": true,
      "is_complete": true,
      "null_reason": { "discount": "no_billing_data", "list": "no_billing_data" }
    }
  ]
}
```
The month values above illustrate the shape. The opening, closing, cash and expansion/contraction magnitudes are close to today's local silver for 2024-10; the other steps are illustrative.

**`months`**
- The window's months after the first, oldest first: today 2022-02 → 2024-10. The first month of the window has no opening.
- `step_value` has **every** code in `steps`. A step with no data is `null` (today the discount steps), and a step that happened but summed to nothing is `"0.00"`. `step_customers` follows the same rule.
- `timing_value` is the level Cash − MRR for the month, not a change.
- `is_complete` is false when the month has a hole (H1) or comes after `data_complete_through`. Its MRR is then `null`, and a period containing it has no bridge, with that reason.

**Period rule (UI).** For a set of consecutive months P, the UI computes:
- opening = `opening_mrr_value` of the first month, and closing = `closing_mrr_value` of the last;
- each step = the exact Σ over P, which is `null` if any month's value is `null`;
- timing change = `timing_value`(last) − `timing_value`(month before first), or `null` if that month isn't in the window;
- leakage = the mean of `discount_value` over P, or `null` if any month is `null`.

The UI does no other arithmetic.

## `GET /api/mrr/movements` (top movers drill-down)

Roles: all three (customer-level, pseudonymous `customer_id`; CDO-11(1) named roles only).

Query: `from=YYYY-MM&to=YYYY-MM&run=latest|<id>&step=<code>&driver=<code>&sort=abs_desc|asc|desc&page=1&page_size=50` (`page_size` at most 200). `step` and `driver` are optional and may repeat.

```json
{
  "run_id": "r20261118T040000Z",
  "total": 1342,
  "page": 1,
  "page_size": 50,
  "movements": [
    { "customer_id": 1052, "month": "2024-10", "step": "expansion", "driver": "behaviour", "inferred": false,
      "industry_code": "TECHNOLOGY",
      "mrr_before_value": "84000.00", "mrr_after_value": "126000.00", "change_value": "42000.00",
      "list_before_value": null, "list_after_value": null, "discount_before_value": null, "discount_after_value": null,
      "settlement_type": null }
  ]
}
```

- One row per customer × month × step with a non-zero change. A month can hold two rows for a customer, for example `price_increase` and `expansion`. The `change_value` of a customer-month sums to that customer's MRR change.
- `customer_id` is silver's pseudonym. The response has no names and no `Cliente N` labels.
- 400 `invalid_query` for bad months, codes or paging, with the same `error.details` `{check, field, message}` as `acq` v1.1.

## Serving store (gold job writes, API Lambda reads)

```
s3://al-test-dl-serving/mrr/latest.json                         {"run_id", "published_at"} (written last)
s3://al-test-dl-serving/mrr/runs/<run_id>/summary.json          the summary payload
s3://al-test-dl-serving/mrr/runs/<run_id>/movements.json.gz     every non-zero movement row (filtered and paged by the Lambda)
```

## Open points for the coordinator and the CDO

1. **MRR basis.** Normalized MRR, with timing as a separate cash reconciliation (proposed), or cash as MRR?
2. **Pricing detection rule** and its threshold, given the 0.21 price grid (CRO-05 note) and "141 are a price step billed one month late" (SB-11 note).
3. **Churn step value.** The prior month's MRR (proposed). How should churn reversed by a later settlement be restated (SB-05)?
4. **Billing feed** for list price and discounts (owner Finance and Billing). Until it exists, `discount_data_status: "not_available"`.
5. Whether `industry_code` on movements is wanted. It enables a later per-industry bridge without spend, so CDO-10 isn't affected.
