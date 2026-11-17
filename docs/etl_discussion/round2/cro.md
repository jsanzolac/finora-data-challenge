# Round 2: CRO debate

**Summary.** I re-ran the disputed figures over `data/` (`python3 -I`). The CDO is right on settled gaps and on 64 reactivations. I concede that prepayment is real and that "a hole is a quarantine" was wrong. The others still distort revenue in five places:
- churn dated at the first zero month shows a false collapse in the last two months;
- the 2x first-payment signature does not prove left-censoring, because 27 flat 2024 logos carry it too;
- the 1% outlier rule flips by itself as the window grows;
- the CFO and CMO still keep SB-07 as written (313);
- CTO-07, CTO-09 and CDO-05 can stall or corrupt revenue exports.

Rule overlaps are resolved below. Of the 37 new rules, I keep 13, flag 17 and drop 7.

Verdict scale: **keep** = adopt as written; **flag** = adopt with the amendment in the reason; **drop** = do not adopt (duplicate, or it distorts revenue).

## Verdicts on the other executives' new rules

| Rule | Proposer | Verdict | Reason |
|---|---|---|---|
| CFO-01 | CFO | flag | Control totals are right (Σ 221,441.504508; spend 77.818); fold them into the CTO-02 manifest, one manifest not three |
| CFO-02 | CFO | drop | Duplicate of CDO-04, which wins; its per-month grain moves there |
| CFO-03 | CFO | flag | Label the currency once per dataset (metadata), not as a text column on 66,674 rows; wins over CMO-02 |
| CFO-04 | CFO | flag | Label basis `unconfirmed`; "cash-like" is an inference (210 of 468 gaps settle early or late) and stays inferred |
| CFO-05 | CFO | drop | A ratio gate (>1.0) clears by arithmetic as S&M/revenue falls 5.75x to 2.30x; CDO-08 plus an owner-cleared status covers it |
| CFO-06 | CFO | flag | Windows and labels are good; "floor" has the wrong sign (scope overstates CAC, margin understates payback); view only, no payback column in the agg |
| CFO-07 | CFO | flag | Keep "lifecycle flags stored per as_of_month" so history is not rewritten; lineage columns go to CTO-06 |
| CMO-01 | CMO | flag | The 2x signature also hits 27 flat 2024 logos, so it is not "late first payment"; store the ratio, flag it, never exclude |
| CMO-02 | CMO | drop | Spend-only copy of CFO-03/04 |
| CMO-03 | CMO | flag | Mapping is fine as GLD-04's second hierarchy; "new column quarantines" duplicates CDO-02 |
| CMO-04 | CMO | keep | Verified: 377 + 1,584 = 1,961; make it three-way if a censored group is classified |
| CMO-05 | CMO | drop | Same column as CFO-06; 4.79M per logo against a 42,000 median first payment should not sit in an agg table |
| CMO-06 | CMO | drop | Duplicate of CDO-10, which wins (it has an unblock path: an owner-approved allocation key) |
| CMO-07 | CMO | flag | Apply `low_n` to the base of every rate, not only new logos: 16 of 72 industry-quarter cells and 140 of 198 monthly cells have under 10 new logos |
| CMO-08 | CMO | flag | The Jun-23 break is the CMO's finding; keep it as an inferred `dim_month` label, never as a basis for in-regime correlations (n=15/17) |
| CDO-01 | CDO | keep | Structural; reject keeps the last good publish live |
| CDO-02 | CDO | flag | A new column (plan, accountant ID: both wanted) quarantines the whole file; time-box the CDO classification |
| CDO-03 | CDO | drop | A third manifest; row count, LastModified and rule hits move into CTO-02 |
| CDO-04 | CDO | keep | Wins as the one reconciliation (over CFO-02, CRO-02); add a month x industry slice and show quarantined revenue as its own line |
| CDO-05 | CDO | flag | Never round, but reject on a sub-cent excursion freezes revenue; widen the scale and flag (all 66,674 rows are at most 2 decimals today) |
| CDO-06 | CDO | keep | Wins over CTO-05; a restated month rewrites NRR history; inferred (owner Q8) |
| CDO-07 | CDO | flag | Wins over CRO-04; the churn KPI for the last 2 months must be NULL; reject only the one-state-per-row invariant |
| CDO-08 | CDO | keep | Catches 10,000x slips (native mix is about 0.00035x); the window is snapshot-fitted, so inferred; wins over CFO-05 |
| CDO-09 | CDO | flag | `rule_version` per row, not per column; the lineage columns live in CTO-06; `as_of_month` stays |
| CDO-10 | CDO | keep | S&M has no customer key; wins over CMO-06 |
| CDO-11 | CDO | flag | Add Revenue and CS leaders to the named roles: they need account lists (237 churned, 46 in grace); suppression is a transform, not a flag |
| CTO-01 | CTO | keep | The byte round-trip is the only proof of "no other change"; same test as the CDO's BRZ-06 text |
| CTO-02 | CTO | keep | Wins as the one manifest; add CFO-01 totals and CDO-03 fields |
| CTO-03 | CTO | flag | Versioning is off, so VersionId is null; key on SHA-256 plus ETag until it is on |
| CTO-04 | CTO | keep | Float x 10,000 differs from the exact value on 2,436 rows (reproduced) |
| CTO-05 | CTO | drop | Duplicate of CDO-06 |
| CTO-06 | CTO | keep | Wins the lineage columns (over CFO-07 and CDO-09) |
| CTO-07 | CTO | flag | Use a per-KPI watermark: revenue KPIs depend only on Transactions; min() applies only to ratios that use S&M |
| CTO-08 | CTO | keep | Wins on naming (member -1, "Unknown") over UNASSIGNED and UNKNOWN; never drop revenue for a missing dimension row |
| CTO-09 | CTO | flag | Exempt numeric columns: a `'` prefix turns -$0.053 and any negative delta into text |
| CTO-10 | CTO | keep | The atomic swap keeps KPIs consistent; publish per fact family so a bad S&M file does not hold revenue |
| CTO-11 | CTO | keep | The gate that enforces CDO-04's identity at the gold boundary |

## Replies

**To the CDO.**
- *CDO-07 and churn dating.* Dating churn at the first zero month means it is only confirmed at the third. As of Oct-2024 the build shows 0 churn events for Sep-24 and Oct-24, against 14, 18 and 15 for Aug, Jul and Jun. The same two trailing zeros appear in the Apr-24 and Jul-24 cuts. A monthly chart would show a collapse that is only an artefact. Require `churn_confirmed_through = as_of_month - 2`, and report `grace` separately (46 customers: 33 + 13).
- *SB-04 `probable_left`.* I agree 34 of 108 Feb-2022 first payments are about 2x the next, against at most 2 a month in Mar-Dec 2022. But 27 customers in Mar-Jul 2024 (5, 8, 5, 7, 2) show the same pattern and stay flat at 1x. The window start cannot explain them, so the signature does not prove a pre-existing customer. The j>=3 tail adds 6 in Feb-22 and 3 in Mar-22, which I cannot separate from chance. Use j=2 only, flag, and publish new logos both ways. IDs add nothing: 0 order violations suggests they come from this extract.
- *SB-08 at 1% of window revenue.* This flag flips with no change in the customer. Customer 322 holds 1.86% today and would fall below 1% in about 19 months at the current 97M a month. Its trailing-12-month share is already 0.46%. The median ratio does not drift: 94 is 60.0x, 322 is 31.7x, and the next is 18.6x but has a single payment.
- *SB-06 text.* My re-run gives 155 arrears + 47 prepay + 8 split-only = 210 of 468 (44.9%; CDO 211). As written, the split test is true on 177 gaps, 169 of them already arrears or prepay, so "nearest multiple" cannot break the tie. Use a precedence: arrears, then prepay, then split. I concede that prepayment is real: 47 of 330 one-zero gaps (14.2%) against 0.28% (79 of 28,333) in unbroken triples.

**To the CFO.**
- *SB-07.* You "agree" with SB-07, but as written it gives 313 (468 - 155). That is 4.9x the canonical 64, and it contradicts the 3-month grace in SB-05.
- *CFO-06 "floor".* S&M 7,581.8M over 1,584 logos is 4.79M (reproduced), or 4.89M without the 34 Feb-2022 suspects. Missing gross margin makes the true payback longer. If S&M funds customers outside Transactions (your 5.75x), the figure is overstated. The two biases point in opposite directions, so call it unbounded.
- *SB-06 "1.6% of revenue, never restate".* I reproduce 1.59% in catch-up payments plus 0.23% in prepayments. I agree `amount` is never restated. But 1.6% is the wrong materiality test: customer 94's catch-ups move the normalized Jun-22 by +14.0% and Aug-22 by -9.9% (its Aug-22 payment of 847.97 is 3x 283). A normalized column beside the raw one is needed, with and without 94.

**To the CMO.**
- *SB-07 "keep".* You justify it by saying win-backs are 4.1% of new logos (65). SB-07 as written produces 313 (19.8%). Your evidence supports my replacement, not the baseline text.
- *SQ-12 "keep".* You argue that orphan quarantine shrinks the CAC denominator. Both are true only if the rule changes to load as Unknown.
- *CMO-01 and CMO-05.* Your 32 of 95 and the CDO's 34 of 108 are the same fact: 95 is the subset that paid the next calendar month. Rename the flag to a numeric ratio. `sm_spend_per_new_logo` is better named than "CAC", but 4.79M against a 42,000 median first payment is 114 months. It stays out of the agg table.

**To the CTO.**
- *SQ-07 "as written".* It quarantines negative amounts, which hides contraction and refunds. The CFO, CDO and I all load and flag instead.
- *CTO-07.* min() of the watermarks stops revenue KPIs when the S&M file is late.
- *BRZ-02 truncation floor.* The 50% floor is useless on a dense panel: losing the last month shrinks the file by only 2.9% (1 of 34). Flag any row count below the previous snapshot.

## Where I changed my mind

| Rule | Decision | New text or reason |
|---|---|---|
| CRO-01 | amend | A missing or quarantined customer-month is NULL (`amount_status='unknown'`), never 0 and never a zero month in churn. Any NULL blocks that month's KPIs until an owner approves. onFailure flag |
| SQ-08, SQ-05 | withdraw "hole = quarantine" | There is nothing to quarantine in a hole. Flag + NULL (CDO), and a duplicate quarantines all copies and blocks gold (CFO, CTO) |
| CRO-02 | withdraw (fold into CDO-04) | Reconcile by month x industry x cohort year; show quarantined revenue as its own line; non-zero blocks publish |
| CRO-03 | amend | `amount_normalized` spreads a settled gap (arrears, then prepayment, then split) over its k+1 months; `amount` is untouched. Normalized 2022 month-on-month stdev is 11.7% against 15.4% raw (12.5% with arrears only) |
| CRO-04 | withdraw | CDO-07 wins; `is_provisional` is its `grace` state |
| CRO-05, CRO-06 | hold | Unchallenged. Expansion and contraction use `amount_normalized`; the CDO should confirm both definitions |
| CRO-07 | amend | Store `first_to_next_ratio`; flag at 1.9x and above, and at 3x and above (`is_first_month_spike`) |
| SB-07, SB-04 | amend | The count of 65 becomes 64 (one gap settled by a split). The Feb-2022 denominator is 108, not 106. SB-04 stays a flag |
| SB-08 | amend | `is_outlier` = median paid amount at least 25x the portfolio median and at least 6 paid months; an owner list can override; flags 94 and 322 |
| GLD-07 | amend | CAC and payback are out of `agg_month_kpis`. An indicative view is allowed with CFO-06's labels, no payback column and the scope status. I moved because CFO-06's sensitivity table is useful if it is labelled and kept out of exports |
