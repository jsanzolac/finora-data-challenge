# Acquisition dashboard ↔ API contract (v1.3)

Shared by the gold/API builder (`etl/`, `dq_api/`, `infra/`) and the dashboard builder (`dashboard/`). Source: the gold model `docs/gold_acquisition_model.md` (CDO, 2026-11-17) and the user's request "start with the dashboard too" (2026-11-17). **Change it only by agreement, and bump the version.**

Everything in `contracts/dq_api_contract.md` "Conventions" applies unchanged: same origin, the `dq_session` cookie, the error shape, 401 → `/login`, 403 `password_change_required`, the roles `data` / `finance` / `revops`, `"__restricted__"` for values a role may not see, and ISO-8601 UTC timestamps and `YYYY-MM` months.

## Types

- **Money** is a JSON **string** (or `null` where the gold model allows NULL: e.g. `spend_total_value` when the month has no S&M line, `new_revenue_value` when not reportable) holding an exact decimal in full units (owner scale already applied: revenue × 10,000, spend × 100,000,000), for example `"200000000"` or `"105482511.96"`. Field names end in `_value`. The UI must do funnel arithmetic with an exact-decimal library (for example `decimal.js-light`), never with floats, so it matches the gold views.
- **Rates** are strings with 4 decimals, for example `"0.8000"`. 0 < rate ≤ 1.
- **Correlations** (`r`, `r_critical_5pct`) are JSON numbers with 4 decimals, or `null` when not computable.
- **Currency** is not stated in the data. Every money figure carries the statuses in `summary.statuses`; the UI shows "Currency not stated" once, in a Details disclosure. No label may call cost per Won "CAC".

## Funnel arithmetic (the UI computes it; it must equal `finora_gold.v_funnel_month` / `v_funnel_period`)

Stages in order: `NEW`, `WORKING`, `ENGAGED`, `SQL`, `DEMO`, `PROPOSAL`, `WON`. Six transitions, each from one stage to the next.

For a set of months P (one month, or a period) and a scenario's six rates:

- `won` = Σ Won over P (the selected Won definition). `spend` = Σ `spend_total_value` over P.
- `downstream(stage)` = the product of the rates from `stage` to `WON` (1 for `WON`).
- `count(stage)` = `won` ÷ `downstream(stage)`. It is **Real** for `WON` and **Estimated** for every other stage. Display it with 1 decimal, HALF_UP.
- `cost_per_unit(stage)` = `spend` × `downstream(stage)` ÷ `won`. Display it in whole units, HALF_UP. It is shown as unavailable ("—", with the reason in a tooltip) when `won` = 0, or when any month in P has a non-null `cost_null_reason`.
- **Scenario vs base**, the "if we move this variable" view. It is labelled *Assumption: stage volumes and rates are not observed*.
  - `overall(s)` = the product of the six rates.
  - Same New: `won_implied` = `won` × `overall(s)` ÷ `overall(base)`; delta and % against `won`.
  - Same Won: `new_required` = `won` ÷ `overall(s)`; delta and % against `won` ÷ `overall(base)`.
- **Sensitivity per transition** (+1 rate point = +0.01): `won_pct_change_per_point` = 1 ÷ `rate` (percent), and `won_change_per_point` = `won` × 0.01 ÷ `rate`. Both are `null` when `rate` + 0.01 > 1.

## `GET /api/acq/summary?run=latest|<run_id>`

Roles: all three. The API masks HR spend categories for non-`finance` roles. All `/api/acq/*` routes return 401 without a session and 403 `password_change_required` while `must_change_password` is true, exactly like `/api/dq/*`. When no gold run has been published yet (no `acq/latest.json`), or `<run_id>` is unknown, the response is 404 with code `no_gold_run` (resp. `unknown_run`).

```json
{
  "run": {
    "run_id": "r20261117T160000Z",
    "silver_run_id": "r20261117T160000Z",
    "built_at": "2026-11-17T16:06:00Z",
    "as_of_month": "2024-10",
    "data_complete_through": "2024-10",
    "gold_model_version": "sha256:…",
    "base_rates_match_seed": true
  },
  "statuses": { "currency_status": "unconfirmed", "revenue_basis_status": "unconfirmed",
                "spend_basis_status": "unconfirmed", "scope_status": "unconfirmed" },
  "stages": [ { "code": "NEW", "label": "New", "order": 1 } ],
  "industries": [ { "code": "RESTAURANTS", "label": "Restaurants" } ],
  "spend_categories": [ { "code": "PaidMedia", "label": "Paid media", "hr_sensitive": false, "group": "media" } ],
  "regimes": [ { "id": "pre_2023_06", "label": "Before Jun 2023", "first_month": "2022-02", "last_month": "2023-05", "inferred": true } ],
  "months": [
    {
      "month": "2024-10",
      "regime": "from_2023_06",
      "won": 50,
      "won_new_logo": 50,
      "won_by_industry": { "RESTAURANTS": 18, "RETAIL": 7 },
      "won_by_industry_new_logo": { "RESTAURANTS": 18, "RETAIL": 7 },
      "new_revenue_value": "2201333.00",
      "spend_value": { "PaidMedia": "78000000", "Team": "__restricted__" },
      "spend_people_value": "76000000",
      "spend_total_value": "200000000",
      "won_is_complete": true,
      "is_unit_tripwire": false,
      "cost_null_reason": null,
      "is_low_n": false
    }
  ],
  "industry_profile": [
    { "industry_code": "RESTAURANTS", "customer_scope": "all", "customers": 529, "won": 420,
      "avg_monthly_payment_value": "83208.00", "avg_monthly_payment_excl_outliers_value": "67499.00",
      "median_monthly_payment_value": "…", "outlier_customers": 2,
      "avg_months_paying": "17.2000", "avg_months_observable": "…", "share_of_observable_months_paid": "…",
      "is_low_n": false }
  ],
  "correlations": [
    { "won_definition": "user", "scope": "company", "series": "total", "lag": 0, "method": "level",
      "r": -0.4800, "n": 33, "r_critical_5pct": 0.3440, "is_signal": true,
      "is_low_volume": false, "null_reason": null }
  ],
  "signal_summary": [
    { "method": "level", "won_definition": "user", "scope_type": "company",
      "tests": 44, "tests_with_r": 44, "signals": 30, "expected_by_chance": 2.2 }
  ]
}
```

**`months`**
- The Won-reportable months only, oldest first: today 2022-02 → 2024-10 (33 months). The window's first month is excluded, because its customers were already customers.
- `won` follows the user's definition. `won_new_logo` is the CDO-canonical count, without the customers silver tags as probably already customers.
- `won_by_industry` has every industry code, with 0 where there were none. Industries follow the user's Won definition.
- `spend_value` has every category in `spend_categories`. For non-`finance` roles, the HR categories (`hr_sensitive: true`: Team, PayrollExpenses, Freelance) are `"__restricted__"`.
- `spend_people_value` and `spend_total_value` are shared with all three roles (decision A1 of the gold model).
- `won_by_industry_new_logo`: the same split for the `new_logo` definition.
- `cost_null_reason` is one of `spend_missing`, `beyond_data_complete_through`, `unit_tripwire`, `won_incomplete`, or `null`. It is **independent of the Won definition**: `won_zero` is not sent, because the UI derives it from the selected definition (Won = 0 ⇒ cost unavailable, reason `won_zero`).
- **Periods:** a multi-month period only sums months up to `run.data_complete_through` (gold §7.1). A period containing a month with a non-null `cost_null_reason` has no period cost.

**The other sections**
- **`regimes`:** the S&M spend regimes, which are inferred. They are used as period presets ("Before / after Jun 2023").
- **`industry_profile`:** every (industry × `customer_scope`) row of `finora_gold.agg_industry_profile`. `customer_scope` is `all`, `won` or `left_censored` (gold §5.11). `avg_monthly_payment_excl_outliers_value` is gold's `avg_monthly_payment_ex_outlier_value`. `avg_months_paying`, `avg_months_observable` and `share_of_observable_months_paid` are decimal strings with 4 dp (the UI displays 1 dp). `won` = the industry's Won count (user definition) over the reportable months; it is the same on every scope row of that industry.
- **`correlations`:** every row of `finora_gold.agg_won_spend_lag_corr`.
  - `scope` is `company` or an industry code.
  - `series` is one of the 7 category codes, or a group: `media`, `other`, `people` (gold `GROUP_MEDIA`, `GROUP_OTHER`, `GROUP_PEOPLE`), or `total` (gold `TOTAL`). That's 11 series, so 44 company-level tests per method and definition.
  - `is_low_volume` and `null_reason` (`too_few_pairs`, `constant_series` or `null`) as in gold §5.12. `n` is gold's `n_pairs`; `is_signal` is `is_signal_5pct`.
  - `method` is `level`, `diff` or `within_regime`.
  - `won_definition` is `user` (gold `first_payment`) or `new_logo`.
- **`signal_summary`:** every row of `finora_gold.v_corr_signal_summary`.

## `GET /api/acq/scenarios`

Roles: all three. The scenarios are read live (Athena `finora_gold.v_funnel_rate_current` joined with `v_funnel_scenario_status`). The UI shows a loading state, because this takes about 2 to 5 seconds.

```json
{
  "can_edit": true,
  "scenarios": [
    {
      "scenario_id": "base",
      "label": "Base (user rates 2026-11-17)",
      "status": "valid",
      "failed_checks": [],
      "rates": [ { "from_stage": "NEW", "to_stage": "WORKING", "rate": "0.8000" } ],
      "changed_at": "2026-11-17T16:00:00Z",
      "changed_by": "seed",
      "change_reason": "User definition 2026-11-17, docs/gold_acquisition_model.md"
    }
  ]
}
```

- `can_edit` is `true` for `finance` and `revops`, and `false` for `data`.
- `base` is listed first.
- `rates` holds the current rate per transition, in stage order. An `invalid` scenario lists its `failed_checks` (GR-01…GR-06) and must not be selectable for the funnel.
- `changed_at`, `changed_by` and `change_reason` are those of the latest row of the scenario.

## `POST /api/acq/scenarios`

Roles: `finance`, `revops`. Any other role gets 403 `role_not_allowed`.

Request:
```json
{ "scenario_id": "sql_demo_080", "label": "SQL to Demo at 80%", "change_reason": "What if demos are booked faster",
  "rates": [ { "from_stage": "NEW", "to_stage": "WORKING", "rate": "0.8000" } ] }
```

**Behaviour**
- The request must carry all 6 transitions. The API appends **one row per transition whose rate differs from the scenario's current rate**, or all 6 for a new scenario. It runs Athena `INSERT INTO finora_gold.funnel_conversion_rate` with `changed_at = current_timestamp`. It never runs UPDATE or DELETE.
- Editing `base` is allowed, but it needs a reason. The UI asks for confirmation ("This changes the base assumptions for everyone").
- **`changed_by`** = `dashboard:` + the first 12 hex characters of SHA-256 of the user's email. It is never the email itself, per the gold model §6.1 (A5).

**Validation, before the insert.** 400 with `details` **inside** `error`:
`{ "error": { "code": "invalid_scenario", "message": "…", "details": [ { "check": "GR-03", "field": "rates", "message": "…" } ] } }`.
`field` is one of `scenario_id`, `label`, `change_reason`, `rates`. `check` is a GR id, or `LABEL_LENGTH` / `REASON_LENGTH` for the length rules.
- `scenario_id` matches `^[a-z][a-z0-9_]{0,39}$`;
- the label has 1 to 200 characters and `change_reason` 1 to 500;
- exactly the 6 consecutive transitions;
- 0 < rate ≤ 1, with at most 4 decimals.

**Responses**
- 400 `no_change` when nothing differs.
- 201 with the scenario object as listed by `GET /api/acq/scenarios`, read back after the insert.

## Serving store (written by the gold job, read by the API Lambda)

```
s3://al-test-dl-serving/acq/latest.json                       {"run_id": "...", "published_at": "..."}   (written last, only after gold publish succeeded)
s3://al-test-dl-serving/acq/runs/<run_id>/summary.json        (the /api/acq/summary payload, unmasked)
```

The API Lambda applies role masking. A gold failure leaves `acq/latest.json` on the previous good run, and never touches `dq/*`.

## Mock data

The dashboard ships contract-shaped fixtures in `dashboard/mocks/acq/`, built from today's real figures (`analysis/acquisition/output/*.csv` and `docs/gold_acquisition_model.md` §12). It includes at least one month with `cost_null_reason`, one `invalid` scenario and a `data`-role session (`can_edit: false`). Dev-only mock mode uses `NEXT_PUBLIC_DQ_MOCKS=1`, as for DQ.


## v1.2 addition: `levers` (2026-11-17)

The user's feedback was: "The funnel page does not allow to take any decisions … I need a way to provide an insight on what variable I could move." The page leads with a **lever planner**, so `GET /api/acq/summary` gains one top-level block, `levers`. Definitions are owned by the CDO (gold model addendum §16). The ones below are the coordinator's working definitions until §16 lands; §16 wins on any conflict.

```json
"levers": {
  "definitions_version": "draft-2026-11-17",
  "periods": [
    { "period": "pre_2023_06", "first_month": "2022-02", "last_month": "2023-05", "months": 16,
      "won": 606, "won_per_month": "37.875000",
      "run_rate_mrr_per_won_value": "56383.00", "run_rate_customers": 600,
      "new_mrr_per_month_value": "2135500.00",
      "spend_per_month_value": "287556250", "cost_per_won_value": "7592244.00",
      "payback_months": "134.7",
      "paying_m6_pct": "…", "paying_m12_pct": "…" }
  ],
  "industries": [
    { "industry_code": "RETAIL", "period": "from_2023_06", "won": 239, "share_pct": "24.4",
      "run_rate_mrr_per_won_value": "28733.00", "paying_m12_pct": "…", "is_low_n": false }
  ],
  "value_change": { "from_period": "pre_2023_06", "to_period": "from_2023_06",
                    "total_value": "-13818.00", "mix_value": "-849.00", "within_industry_value": "-12969.00" },
  "cohorts": [
    { "cohort": "2023-H2", "won": 378, "paying_m6_pct": "95.2", "paying_m12_pct": "91.0",
      "run_rate_mrr_per_won_value": "…", "is_complete_m6": true, "is_complete_m12": true }
  ]
}
```

**Working definitions**
- **Run-rate MRR per new customer:** for each Won customer, the mean full-value paid amount over the 3 months after the first-payment month (months 2–4). The first payment is excluded, because it is often a multiple or catch-up. Only months that are paid and inside the data window count. A customer with none of those months paid is left out of the mean, and the number kept is `run_rate_customers`.
- **`new_mrr_per_month_value`** = `won_per_month` × run-rate MRR per Won.
- **`payback_months`** = `cost_per_won_value` ÷ run-rate MRR per Won. This is a cash payback on revenue, not on margin, with the currency not stated.
- **`paying_m6_pct` / `paying_m12_pct`:** the share of Won customers who are paying in their 6th or 12th month, counting the first-payment month as month 1. Only cohorts whose month 6 or 12 is within the data count.
- **`value_change`:** a shift-share split of the change in run-rate per Won between two periods. Mix = Σ (Δshare × old value), and within-industry = Σ (new share × Δvalue). The two parts add up exactly to the total.
- **`cohorts`:** half-year cohorts of the Won month.

**The planner, computed in the UI with exact decimals from these fields and `months`:**
- **Baseline:** the selected period's `won_per_month`, run-rate per Won, `new_mrr_per_month_value` and `payback_months`.
- **The four levers the user can move:**
  1. **Conversion rates (volume):** Won/month × overall(s) ÷ overall(base). This is an assumption.
  2. **Ticket size:** run-rate per Won × (1 + x%). The observed reference is the gap to the earlier period's per-industry run-rate.
  3. **Industry mix:** move p points of share from one industry to another at their observed run-rates.
  4. **Spend per month:** changes cost per Won and payback only, with Won held flat. Labelled "effect on new customers not measurable in this data; test it".
- **Outputs:** new customers per month, new MRR per month (and its change), and payback months.
- **Evidence labels:** each lever's impact carries `Observed`, `Assumption` or `Untested`.


## v1.3: `levers` follows gold model §16 exactly (2026-11-17)

This **replaces the v1.2 working definitions and the field list of the `levers` example.** The CDO's §16 "Decision levers" in `docs/gold_acquisition_model.md` is canonical.

**Binding rule: the JSON mirrors the gold tables.**

| `levers` field | Contents |
|---|---|
| `periods` | The rows of `agg_acq_lever_period` |
| `industries` | The rows of `agg_acq_lever_industry` |
| `value_change` | **An array**: the rows of `agg_acq_value_change` |
| `cohorts` | The rows of `v_acq_cohort_half` |

- Every row keeps its §16.4 column names. That includes `won_definition` and the completeness counts (`run_rate_no_paid_customers`, `run_rate_immature_customers`, `paying_m6_eligible`, …) and the per-industry shift-share terms.
- Value types:
  - **Money (`*_value`):** decimal strings at 2 dp, HALF_UP. Example: `cost_per_won_value` is "7592244.22".
  - **Other decimals:** strings, at the scale §16.4 gives.
  - **Counts:** integers.
  - **NULL:** JSON `null`. `null` never means 0.
- Rows exist for both `won_definition` values. The UI filters on the selected definition.
- `agg_acq_cohort_quality` (customer × cohort detail) is **not** in the snapshot.

**UI rules from §16:**
- **Planner formulas and fixtures:** §16.3 and §16.5. The UI must reproduce the five §16.5 planner fixtures exactly (for example ticket +10% gives payback 65.1).
- **The ticket reference** is §16's "pre-period tickets at today's mix" (+29.7% today).
- **The signals headline and when its "no measurable link" clause shows:** §16.6.
- **Ticket size must not be tied to the spend periods.** The step in ticket size **precedes** the spend change. The before/after-Jun-2023 split is only a baseline, so no label may say or imply that the spend regime changed the ticket or Won. The ticket trend is shown by half-year cohort.

## Changelog

- **v1.1 (2026-11-17).** Resolves the gaps the dashboard build found:
  - correlation series ids (`media`, `other`, `people`, `total`; no `media_other`), plus `is_low_volume` and `null_reason`;
  - nullable money;
  - `details` placement in the 400 error, with a `field` and the length-rule check ids;
  - the meaning of `industry_profile.won`, the 4-dp strings and the extra profile columns;
  - 404 `no_gold_run` and `unknown_run`;
  - `won_by_industry_new_logo`;
  - `cost_null_reason` without `won_zero` (derived by the UI);
  - the `data_complete_through` period rule;
  - an explicit 403 `password_change_required` on `/api/acq/*`.

  There is no verdict field: the UI derives the signals headline from `signal_summary`, and that rule awaits CDO approval.
- **v1.2 (2026-11-17).** Adds the `levers` block (lever planner): period economics, industry value, a mix-vs-within split, and cohort quality.
- **v1.3 (2026-11-17).** `levers` mirrors the gold §16 tables exactly (it supersedes the v1.2 working definitions). Money is at 2 dp, `value_change` becomes an array, `won_definition` is on every row, and the §16.6 headline and the no-causal-labels rule apply.
