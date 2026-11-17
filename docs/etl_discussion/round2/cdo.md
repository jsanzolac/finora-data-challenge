# Round 2: CDO debate

The other four executives proposed 33 new rules. I keep 13, flag 19 and drop 1. Most of the flags are merges: four of us wrote the same reconciliation, manifest, lineage and currency rules under different names, and each topic needs one winner.
The fault lines settle on re-checked figures. There are 64 reactivations, and the CRO's 65th is customer 40, who paid every month in full. In Feb-2022 the CMO and I count the same thing against different bases. Staging VersionIds are `null`, so the CTO's idempotency key fails.
I adopt the CRO's outlier criterion and the CMO's CAC name, and I widen my censoring rule to 43 customers.

*Evidence: I re-ran everything with `python3 -I` and `Decimal` over `data/` (2026-11-15), plus read-only `get-bucket-versioning`, `head-object` and `list-object-versions` on staging.*

## Verdicts on the other executives' new rules

**keep** = adopt the substance as written, possibly merged into a named winner. **flag** = adopt only with the amendment given. **drop** = not adopted as a separate rule.

| Rule | Proposer | Verdict (keep/flag/drop) | Reason |
|---|---|---|---|
| CRO-01 | CRO | keep | "Unknown is not zero" is the right control and matches my SQ-08 text. It supersedes the CRO's own "a hole is quarantine": a missing row cannot be quarantined |
| CRO-02 | CRO | flag | Merge into CDO-04, where it adds the month × industry grain. Its evidence cites the docs' rounded 2,214,415,000; the exact total is 2,214,415,045.08 |
| CRO-03 | CRO | flag | Must spread every settlement type (155 arrears, 47 prepaid, 9 split), not only catch-ups. Σ per customer must equal Σ `amount`. Analytical only, never a revenue total |
| CRO-04 | CRO | drop | Superseded by CDO-07. `gap` merges the 193 paused gaps with settled ones, so state counts can't reconcile. Its `is_provisional` moves into CDO-07 |
| CRO-05 | CRO | flag | Inherits CRO-03's defect and Q2 (the 0.21 grid may be price, tax or FX, not expansion). Take Δ only between consecutive `paying` months |
| CRO-06 | CRO | flag | Additive components in gold are right. It stacks two smoothings (raw NRR 93.2% vs 96.2%). Canonical basis: point-in-time `amount_normalized`; the 3-month average becomes a named variant |
| CRO-07 | CRO | flag | Not reproducible: I get 64 of 1,405 (Feb-22 excluded) or 70 of 1,384 (≥ 3 later payments). Move the spike into `first_payment_ratio` (SB-04); starting ARPA uses the de-multiplied first amount |
| CFO-01 | CFO | keep | Merged into one manifest with CTO-02 and CDO-03. The control totals are measured on bronze strings and change no bronze byte |
| CFO-02 | CFO | keep | The same identity as CDO-04 (bronze = silver + quarantine, exact Decimal). Merged, it adds the per-file and per-month grain |
| CFO-03 | CFO | flag | A status value in a code column breaks the code domain. Use `currency_code` NULL (an ISO 4217 code once known) plus `currency_status = 'unconfirmed'`. inferred = false is right |
| CFO-04 | CFO | flag | Separate the fact from the guess: `basis_status = 'unconfirmed'` (inferred false) and `basis_hypothesis` = cash-like or budget-like (inferred true) |
| CFO-05 | CFO | flag | The ratio can't clear the gate; only Q4 can. Set `scope_status = 'unconfirmed'` unconditionally and publish the ratio. Not CDO-08, which catches unit errors |
| CFO-06 | CFO | flag | Structure adopted (numerator, denominator, statuses, trailing windows, blended), under CMO-05's name. The denominator also excludes `probable_left`. No payback column in gold |
| CFO-07 | CFO | flag | Merged into the CTO-06 lineage set. Use SHA-256, not the ETag, which equals the MD5 only for single-part SSE-S3 uploads |
| CMO-01 | CMO | flag | Merge into the amended SB-04. Comparing with the next consecutive month misses 2 Feb-22 customers who paid nothing in Mar-22. In later cohorts a 2× first payment is a one-month shift, not a suspect acquisition |
| CMO-02 | CMO | flag | Merge into the CFO-03/04 vocabulary. "Currency unconfirmed" is a fact the owner file states, so inferred = false |
| CMO-03 | CMO | flag | The mapping is an inferred attribute of `dim_spend_category` (GLD-04). The new-column check belongs to CDO-02 in bronze. "Fails the load" contradicts onFailure = quarantine |
| CMO-04 | CMO | flag | Extend the identity: left 377 + probable_left 43 + new 1,541 = 1,961, and Σ by industry = Σ by month |
| CMO-05 | CMO | keep | Wins the CAC dispute: the name is true by construction. The value is 4.92M per new logo on the canonical 1,541, not 4.79M on 1,584 |
| CMO-06 | CMO | keep | Merged with CDO-10: the CMO's explicit list (industry, customer, channel) plus my clause that only an owner-approved allocation key lifts it |
| CMO-07 | CMO | flag | A reliability threshold is a control, so inferred = false. Distinct from CDO-11 (privacy suppression below 5); both apply |
| CMO-08 | CMO | flag | The Jun-23 break (−47.8% month on month) is observed but its cause is unknown (Q3). Make it a config-driven, inferred `dim_month` annotation that no calculation uses |
| CTO-01 | CTO | keep | Verified: BOM, CRLF on every line (66,674 / 1,962 / 34), no final newline in any of the 3 files, 0 quotes. The strongest bronze test anyone proposed |
| CTO-02 | CTO | flag | VersionId is `null` on every staging object, so key the manifest on SHA-256. A source checksum mismatch quarantines; a bronze round-trip mismatch rejects (CTO-01) |
| CTO-03 | CTO | flag | Keyed on VersionId, a corrected re-upload under the same key becomes a silent no-op. Key it on (source key, SHA-256) until versioning is on |
| CTO-04 | CTO | keep | The same as CDO-05. I reproduced float errors in 2,436 Transactions rows and 32 S&M cells |
| CTO-05 | CTO | keep | The same as CDO-06. inferred = true is right, because the delivery mode is still an open question (Q8) |
| CTO-06 | CTO | keep | Wins the lineage set. CDO-09 adds `as_of_month` |
| CTO-07 | CTO | keep | The correct watermark. It takes over SQ-13's gold role; SQ-13 stays a silver flag |
| CTO-08 | CTO | flag | Add an `UNMAPPED` (−2) industry member so "no Industry row" and "value outside the 6" stay distinct. Use one label, `UNKNOWN`, not Unknown or UNASSIGNED |
| CTO-09 | CTO | keep | Escapes text cells only; typed numbers must stay unescaped, or `-0.016` becomes `'-0.016`. It absorbs my "neutralize at export" |
| CTO-10 | CTO | keep | Required, because the SB-04, SB-05 and SB-07 states change as new months arrive |
| CTO-11 | CTO | keep | Merged into CDO-04 as its gold leg: one reconciliation rule, not four |

**Counts:** CRO 1 / 5 / 1, CFO 2 / 5 / 0, CMO 2 / 6 / 0, CTO 8 / 3 / 0 (keep / flag / drop). **Total: 13 / 19 / 1.**

**Winners where rules overlap:**

| Topic | Winner | Absorbs |
|---|---|---|
| Lifecycle | CDO-07 (amended) | CRO-04's `is_provisional` |
| Manifest | CTO-02, keyed on SHA-256 | CFO-01 control totals, CDO-03 |
| Lineage | CTO-06 + `as_of_month` | CFO-07, CDO-09 |
| Reconciliation | CDO-04 | CFO-02, CRO-02 (month × industry), CTO-11 (gold leg), CMO-04 (logos) |
| Unknown members | CTO-08 + `UNMAPPED` | the SQ-12 texts of the CRO, CFO, CMO and CDO |
| Outliers | The CRO's SB-08 criterion | My 1.0% share, which becomes a concentration measure |
| CAC | CMO-05's name + CFO-06's structure | The CRO's "drop CAC": no column is called CAC until Q4 is answered |
| Currency, basis, scope | CDO-08 vocabulary | CFO-03, CFO-04, CFO-05, CMO-02 |
| First payment and censoring | SB-04 (amended) | CMO-01, CRO-07's spike flag, the edge part of the CRO's SB-04 |
| Spend isolation | CMO-06 + CDO-10 | — |

## Replies

**To the CRO.**
- **Reactivations: 64 (60 customers) stands.** Your 65th is customer 40:
  - It paid 24.36 in Jul-2022, then 0.2436 in Aug, zero in Sep–Nov, 121.5564 in Dec, and 24.36 again.
  - 0.2436 + 121.5564 = 121.8000 = 5 × 24.36, exact to the fourth decimal. The account paid every month in full.
  - So your SB-05 clause "only a catch-up reverses a churn" must read "only a settlement (arrears, prepayment or split)".
- **The settled share holds, with one weak leg.**
  - Prepayment passes the placebo test. The correct multiplier finds 47 gaps, while k and k+2 find 1 each. Tolerances from 0% to ±10% give 46–47. All 47 have k = 1.
  - Split is weak: 9 at k+2 against 2–3 at k+3 and k+4. Five of the nine are arrears paid at a changed price.
  - Result: 211 of 468 gaps (45.1%) are settled, but only 202 (43.2%) with high confidence.
- **Your SQ-08 text ("a hole is quarantine") contradicts your CRO-01.** CRO-01 wins.
- **I hold "reject the file" for SQ-05.** A duplicated key in a dense extract means the extract is broken. Publishing NULL cells would understate revenue in a board number. The CFO and the CTO also block gold. The duplicate copies still go to quarantine for diagnosis.
- **Feb-2022: I cannot reproduce your 106.** All 108 Feb-2022 customers have a later paid month, and on that base we both find 34. "Edge logos stay out of trends" would exclude all 108, yet 65 of them show no multiple at all.

**To the CMO.**
- **We count the same thing against different bases.**
  - You compare each first payment with Mar-2022: 95 customers paid that month, and 32 of them paid ≈2×.
  - I compare with the next paid month: all 108 customers, 34 at ≈2×. The extra 2 paid nothing in Mar-2022.
  - The next paid month is canonical because it is defined for every customer.
- **I widen the rule to 3×, which adds 6 customers.** 3× first payments are 5.6% of Feb-2022 against 0.9% in the Oct-22 to Oct-24 cohorts. 4× sits at background (0.9% vs 0.5%), so I stop at 3×.
- **Your "keep" on SB-07 doesn't hold.** Your own table shows that SB-07 as written gives 313 resumptions (19.8% of new logos). The 4.1% you cite comes from the corrected rule.
- **Your "keep" on SQ-12 contradicts your SQ-04 change.** As written, SQ-12 quarantines orphans and shrinks the very denominator that CMO-04 protects.

**To the CFO.**
- **Your "agree" on SB-07 has the same 313-vs-64 problem.** CAC's denominator is safe, because cohort = first paid month, but the reactivation KPI is not.
- **SB-08 needs a criterion, not a hand-kept list.** The list is derived on each run and versioned through `rule_version`.
- **SQ-11 should stay merged into SB-10:** one check, one interpretation. The CMO agrees.
- **Your CAC table uses 1,584 new customers.** The canonical denominator is 1,541, which gives 4,920,052 per new logo.
- **Payback stays in your analysis, not in gold.** A 90-month figure at 100% scope, using revenue as the margin proxy, rests on two unresolved inputs.
- **I accept your SQ-07:** a non-numeric amount quarantines the row and blocks that month in gold; a negative amount is kept and flagged.

**To the CTO.**
- **CTO-03 can't key on VersionId.** `get-bucket-versioning` returns empty and `list-object-versions` shows `VersionId = "null"`. Keyed on it, a corrected re-upload would be ignored. Your Step Functions execution name already uses `sha256[:16]`; use that same key in the manifest.
- **SQ-04 and SQ-07 can't be accepted as written.**
  - SQ-04's row quarantine erases the fact that a value was unmapped.
  - SQ-07's "≥ 0, quarantine" contradicts the consensus that a refund is flagged, not removed.
- **My flags on GLD-03 and GLD-05 stand, despite your "keep".** Without censoring and the lifecycle states, new + paying + paused + churned customers don't reconcile.
- **SQ-02:** I accept "ignore `_ingested_at`". Route the record to quarantine (`EMPTY_RECORD`) rather than "drop and count", so CDO-04's identity holds without a fourth bucket.

**New for the owners (add to Q2).** Five cells are exactly 1/10 or 1/100 of the previous month's amount (customers 40, 325, 587, 638 and 1294):
- two are token payments that were later settled;
- two are first payments of 10× followed by steady amounts;
- one comes just before churn.

Ask whether some amounts are mis-scaled at the source.

## Where I changed my mind

- **SB-08: I withdraw my 1.0% share criterion and adopt the CRO's.** Why: a revenue share grows with tenure and decays as the window lengthens (322 last paid in Jan-2024). Price level does neither, and it is what distorts averages. New text:
  > `is_outlier_customer` = the customer's median positive `amount` ≥ 25 × the portfolio median positive `amount` (5.25 today; recomputed per run at `as_of_month`; 25 is a versioned parameter). Never removed; every average is published with and without outliers. Concentration (the share of the top 1 and top 10 customers) is a gold measure, not a flag. inferred = true; onFailure = flag.

  It flags 94 (60.0×) and 322 (31.7×); the next customer is 543, at 18.6×.
- **SB-04: amended.** Why: my round-1 "j = 2…n+1" wrongly tagged Mar-2022 customers paying 2× as censored, although their implied start (Feb-2022) is inside the window. New text:
  > `first_payment_ratio` = first paid amount ÷ next paid amount. j is the integer in {2, 3} whose ±5% band contains the ratio; `implied_start_month` = cohort_month − (j − 1). `cohort_censoring` = `left` (cohort 2022-01), `probable_left` (implied_start_month ≤ 2022-01), or otherwise `none`. The cohort stays the first paid month, and only `none` counts as new.

  Result: 377 left, 43 probable_left (40 Feb, 3 Mar) and 1,541 new; Feb-2022 has 68 new logos. It absorbs CMO-01, and CRO-07's spike flag derives from the same ratio.
- **SB-06: amended.** Add `settlement_type` (arrears, prepay or split) and `settlement_confidence` (high for arrears and prepay, low for split).
- **CDO-07: amended.** Add `is_provisional` = true on every row from the customer's last paid month through `as_of_month`. Those rows are an open trailing spell, or a last payment that a later month could turn into a prepayment. The states are unchanged.
- **BRZ-04: onFailure changes from flag to quarantine the file,** as the CTO proposes. The numeric exemption `^-?\$?\d+(\.\d+)?$` stays. There is no free-text column, so any other formula-shaped cell is tampering or corruption.
- **GLD-07: amended.** No column is named CAC. It publishes `sm_spend_per_new_logo` (total and media-only) with CFO-06's companion columns; Jan-2022 is NULL, the denominator is `cohort_censoring = none`, and there is no payback column.
- **Merged into a winner, content unchanged:** CDO-03 into CTO-02 (keyed on SHA-256); CDO-04 absorbs CFO-02, CRO-02, CTO-11 and CMO-04; CDO-06 = CTO-05; CDO-08 takes the CFO's status vocabulary; CDO-09 merges into CTO-06; CDO-10 merges with CMO-06.
- **Held:**
  - CDO-01, CDO-02, CDO-05 and CDO-11;
  - "reject the file" for SQ-05;
  - SQ-11 stays merged into SB-10;
  - `UNKNOWN` instead of quarantine for SQ-12;
  - 64 reactivations.
