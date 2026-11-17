# Round 2: CFO debate

I read all 37 new rules from the CRO (7), CMO (8), CDO (11) and CTO (11): **keep 16, flag 13, drop 8**. Most drops are merges of duplicates (reconciliation x4, manifest x3, lineage x3, status labels x3). The remaining fights are about what may reach a board pack: payback in gold, "ex-outlier" ratios, and onFailure on integrity checks. I re-ran the disputed figures over `data/` (`python3 -I`, Decimal) and checked S3 read-only. Feb-2022 reproduces as the CDO's 34 of 108, which moves CAC by only +2.2%, so it is not worth pipeline complexity. Figures from the CRO's smoothed series (CRO-05/06/07) were not re-run.

## Verdicts on the other executives' new rules

keep = accept as written; flag = accept with the change stated; drop = remove or merge into the named winner.

| Rule | Proposer | Verdict | Reason |
|---|---|---|---|
| CRO-01 | CRO | keep | A missing cell must never sum as 0; pairs with the month completeness gate in CDO-04. |
| CRO-02 | CRO | drop | Duplicate of CDO-04 (spec) and CTO-11 (gate); keep its per-month-and-industry grain. |
| CRO-03 | CRO | flag | Management view only: rename `amount_smoothed_mgmt`, never in revenue totals or reconciliation; months restate on every rebuild. |
| CRO-04 | CRO | drop | CDO-07 wins: exclusive and exhaustive states, and it has `new` and `reactivated`, which a revenue bridge needs. |
| CRO-05 | CRO | flag | Built on smoothed amounts with unconfirmed revenue basis; net is about 0 (CRO: 2.36% vs 2.37%), so label "movement proxy". |
| CRO-06 | CRO | flag | Raw NRR/GRR primary (I reproduce 93.2%/85.8%), smoothed as sensitivity (CRO: 96.2%); never call it MRR/ARR until basis is confirmed. |
| CRO-07 | CRO | keep | Descriptive, flag-only, and what a payback sensitivity needs (CRO's 64 spike customers, not re-run). |
| CMO-01 | CMO | drop | CDO's SB-04 `cohort_censoring` wins; the 2x-next test fits only window-edge cohorts, not Mar-Jun 2024. |
| CMO-02 | CMO | drop | Duplicate of amended CFO-03/04 and CDO-08; a generic `basis` blurs revenue basis and spend basis. |
| CMO-03 | CMO | flag | Fail closed on a new column, but reject the run (quarantine of what?); a missed category understates S&M. |
| CMO-04 | CMO | flag | Keep, but reconcile three buckets: 377 pre-existing + 34 probable-left + 1,550 new = 1,961. |
| CMO-05 | CMO | keep | `sm_spend_per_new_logo` is the honest name; merged into CFO-06 with trailing windows and one status column. |
| CMO-06 | CMO | drop | CDO-10 wins: same ban plus an owner-approved allocation-key exit. |
| CMO-07 | CMO | keep | `low_n` under 10 new logos is cheap and stops small-cell rates reaching a deck. |
| CMO-08 | CMO | keep | A calendar marker is fine; it must not be read as the cause of the Jun-2023 drop. |
| CDO-01 | CDO | keep | Testable and cheap; absorbs the CTO's BRZ-01 text. |
| CDO-02 | CDO | keep | A new column could be PII or a margin field; hold the file until classified. |
| CDO-03 | CDO | drop | Merged into CTO-02 (schema), with write-once kept and mismatch = reject. |
| CDO-04 | CDO | keep | The reconciliation spec: bronze = silver + quarantine, exact Decimal, and silver to gold; wins over CFO-02 and CRO-02. |
| CDO-05 | CDO | keep | Wins over CTO-04; use native spend DECIMAL(12,3) for headroom; any precision loss fails. |
| CDO-06 | CDO | keep | Wins over CTO-05 (same rule); add a restatement log signed off before the gold swap. |
| CDO-07 | CDO | flag | Winner over CRO-04; one-state-per-row invariant rejects the build, but semantic ambiguity only flags. |
| CDO-08 | CDO | flag | Good tripwire (1.61-7.62x today); on trip the ratio KPIs must be NULL, not merely flagged. |
| CDO-09 | CDO | keep | `rule_version` + `as_of_month` + snapshot; wins with CTO-06 over CFO-07. |
| CDO-10 | CDO | flag | Reword: "no allocation of S&M to customer, industry, cohort or channel"; as written it forbids GLD-06's month x category. |
| CDO-11 | CDO | flag | Exempt concentration disclosure (top-1/5/10 share) from small-cell suppression; auditors and the board need customer 94. |
| CTO-01 | CTO | keep | The proof of BRZ-06 (SHA-256 round-trip); same test as the CDO's BRZ-06 replacement. |
| CTO-02 | CTO | flag | Manifest schema wins; add control totals (CFO-01); checksum mismatch rejects, not quarantines. |
| CTO-03 | CTO | keep | One `_ingested_at` per staging VersionId, idempotent; required for reproducibility. |
| CTO-04 | CTO | drop | Merged into CDO-05; keep its float evidence (2,436 rows, 32 of 238 cells). |
| CTO-05 | CTO | drop | Duplicate of CDO-06. |
| CTO-06 | CTO | keep | Lineage column set wins; CDO-09 supplies the `as_of_month` semantics. |
| CTO-07 | CTO | flag | Only KPIs needing both datasets stop at the earlier month; single-dataset KPIs run to their own. |
| CTO-08 | CTO | flag | Limit Unknown (-1) to industry and customer; an unparseable month must never map to Unknown; alert on non-zero Unknown revenue. |
| CTO-09 | CTO | flag | Escape string-typed columns only; negative spend must stay numeric; the action is escape, not "reject". |
| CTO-10 | CTO | keep | Atomic swap and previous-run-stays-live keep the board number stable. |
| CTO-11 | CTO | keep | The publish gate for CDO-04; hard-coded totals belong only in test fixtures. |

## Replies

**To the CRO.** (1) You drop CAC from GLD-07. I disagree: anyone can divide gold's S&M by new logos and get 4.79M, so gold should supply the labelled ratio, not leave the field to a spreadsheet. But I concede the other half: see my CFO-06 amendment below. (2) SB-06 "keep" omits prepayments. With the text as written I get 155 arrears, 50 prepayments and 11 split-only gaps, 216 of 468 (46.2%); the CDO's 211 (45.1%) is within 2%. Prepayment is not noise: shifted multiples match 1 and 0 gaps against 50, and a "double then back" pattern occurs in 0.28% of ungapped triples against 15.2% of one-zero gaps. In money it is small (arrears payments 1.59% of revenue, prepayments 0.23%), so my interest is churn labels, not revenue. (3) Your `is_outlier` and the CDO's 1% share rule both flag exactly 94 and 322 (shares 4.77%, 1.86%, next 0.75%; median multiples 60.0x, 31.7x, next 18.6x). I prefer your median multiple for the flag, since a share rule depends on tenure and window length, and I want `revenue_share` published as a measure for concentration. But "ex-outlier" can flatter: Oct-24 vs Oct-23 NRR is 93.2% all-in, 92.6% ex-94, and 94.9% ex-94 and 322, because 322 (1.66M a month until Dec-23, 1.34M in Jan-24, nothing since) churned. The all-in figure is primary; ex-outlier lines must name the customers removed.

**To the CDO.** (1) Your `probable_left` is right to restrict to cohorts up to 2022-03. I reproduce 34 of 108 at +-5% (36 at +-10%); the CMO's 32/95 and the CRO's 34/106 use smaller denominators I could not reproduce (all 108 have a later paid month). Excluding them lifts CAC from 4.79M to 4.89M (+2.2%), so publish both counts and use the conservative one, but this does not justify more machinery. (2) Your `split` test overlaps arrears and prepayment (183 matches by my reading), so it must be a residual evaluated last, with a stated tie-break. (3) Baseline SB-07 gives 313 reactivations; resumption payments after those gaps total 51.2M (2.3% of revenue) against 13.8M (0.62%) for gaps of 3+ months that nothing settles (62; CRO 65, CDO 64). A bridge using 313 overstates win-back revenue 3.7x. I agree with your SB-07 flag and disagree with the CMO's "keep". (4) I accept dropping SQ-11 into SB-10, and SQ-05 and SQ-10 rejecting the file.

**To the CMO.** CMO-01 applies "2x next" to every month. I reproduce your Mar-Jun 2024 counts (5/8/5/7), but those customers cannot be pre-window, so the mechanism is not censoring; 25 customers are 1.6% of the denominator. Send it to the owners. Your monthly ratio ranges 1.67M to 20.6M (12x), so I keep trailing 3/6/12-month windows; I agree there are no lag columns (a 0-3 month lag moves CAC by at most -5%).

**To the CTO.** (1) CTO-02: a checksum mismatch is an integrity failure; reject. (2) BRZ-02's 50% truncation floor is too loose for a dense panel that only grows (+1,961 rows a month): the new Transactions snapshot must contain every prior (customer, month) key, otherwise reject. (3) Silver/gold noncurrent versions expire at 30 days, but a board pack must be reproducible next year: retain published run snapshots for the audit retention period, which legal sets (jurisdiction is unknown while the currency is). (4) Agree on the root-key and CloudTrail priorities. Checked today: identity is `:root`, `describe-trails` is empty, no bucket policy on any of the four buckets, versioning never enabled. Without CloudTrail, the CDO's "all reads are logged" is unenforceable. (5) BRZ-04: with the numeric exemption there are 0 hits, so any hit is anomalous; I accept your file quarantine and withdraw my "flag-only".

## Where I changed my mind

- **Withdrawn (merged):** CFO-01 into CTO-02 (control totals kept); CFO-02 into CDO-04; CFO-07 into CTO-06 + CDO-09; CFO-04 into amended CFO-03.
- **CFO-03 (amended):** "One `dim_source_status` row per money dataset: `currency_code` NULL, `currency_status = 'unconfirmed'`, `revenue_basis_status` / `spend_basis_status = 'unconfirmed'`, `basis_hint` ('cash-like' / 'budget-like'). Facts carry the FK; every KPI view exposes the columns. Changed only by a recorded owner answer. flag." A literal 'UNCONFIRMED' in a currency column pollutes the ISO domain.
- **CFO-05 (amended):** "`scope_status = 'UNCONFIRMED'` always, until a recorded owner answer; the S&M/revenue ratio is evidence, not the test." A ratio below 1.0 would not confirm scope either.
- **CFO-06 (amended):** "Gold publishes components (S&M total and media-only, new logos by censoring class) and `sm_spend_per_new_logo` (CMO-05 name) as trailing 3/6/12-month windows, NULL while the CDO-08 tripwire fires or the window includes Jan-22, with `scope_status`, `spend_basis_status` and `currency_status` in the same row; revenue KPIs with and without outliers. No payback or LTV column: payback needs a scope share and a gross margin the data cannot supply." My `payback_months_revenue_floor` was wrong-footed: it is a floor against margin but a ceiling against scope. It lives in the CFO analysis as a grid (scope 100/50/25/10% gives 90/45/22.5/9 months at 100% margin). Correction: 53,201 is monthly revenue averaged over a new customer's first three months (the 3-month total is 159,603).
- **SQ-05, SQ-10:** now reject the file (CDO); a duplicate key has no true amount, and a quarantined spend row deletes a month. **SQ-07** stays: quarantine an unparseable cell, NULL via CRO-01, withhold that month's KPIs; negatives load, stay in sums, and are flagged. **SQ-12** is unchanged (load to Unknown, flag).
- **Held:** SB-08 flag-only with and without outliers; GLD-05 and GLD-07 flag; SB-10 keeps the sign as received.
