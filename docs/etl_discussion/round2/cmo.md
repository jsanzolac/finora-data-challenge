# Round 2: CMO debate

Gold can still put new logos by month and industry next to spend by category without implying attribution, if four things hold: a stable `is_new_logo` that does not depend on the lifecycle build; no small-cell suppression of internal counts (CDO-11); CDO-10 reworded so it stops forbidding month × category spend; and no spend column on any industry-grain table. I adopt the CDO's censoring rule for the CAC denominator (1,550 new logos, not 1,584). I withdraw four round-1 positions (SB-07, SQ-12, SQ-11, CMO-02) and amend CMO-01, 03, 05. My main disagreements are with the CRO (drop CAC), the CDO (CDO-11) and the CFO (CFO-06 payback and denominators). All figures were re-run on `data/*.csv` with `python3 -I`.

## Verdicts on the other executives' new rules

Key: keep = adopt as written; flag = adopt with the stated change or merge into the named winner; drop = do not adopt.

| Rule | Proposer | Verdict (keep/flag/drop) | Reason |
|---|---|---|---|
| CRO-01 | CRO | flag | Unknown is not zero, but a NULL before the first payment can move a cohort month: add `cohort_provisional`; on duplicate keys the CDO's reject-file wins |
| CRO-02 | CRO | flag | Fold into CDO-04 (wins) and keep its month × industry grain so logo and revenue drill-downs tie out |
| CRO-03 | CRO | flag | Modelled revenue in months paid at zero: silver only, never feeds `is_paying`, new logos or first-paid amount |
| CRO-04 | CRO | drop | CDO-07 wins: it has `new`, `reactivated`, `settled_gap`, `grace`; CRO-04's single `gap` merges a pause with a settled gap |
| CRO-05 | CRO | flag | Expansion 2.36% vs contraction 2.37% on an unconfirmed basis (Q2): a view, not a silver rule |
| CRO-06 | CRO | flag | I need NRR/GRR by industry and cohort year for ICP weighting; show raw beside smoothed, and never decide on Retail's 84.5-95.4% CI alone |
| CRO-07 | CRO | flag | A pricing signal, not a cohort rule: I get 61-73 flags depending on definition, 9 of them in Feb-2022; it must never remove a logo from counts |
| CFO-01 | CFO | flag | One manifest only (CTO-02 is the container); add CFO-01's control totals to it |
| CFO-02 | CFO | flag | Same identity as CDO-04 (wins); fold in the per-month grain |
| CFO-03 | CFO | keep | One currency label ("currency units", UNCONFIRMED); replaces the currency half of my CMO-02 |
| CFO-04 | CFO | flag | Wins over the basis half of CMO-02, but "cash-like"/"budget-like" put guesses in a label: use UNCONFIRMED plus a note |
| CFO-05 | CFO | flag | Set UNCONFIRMED by default and clear it only on an owner answer, not by a ratio > 1.0; it is the single source for my `cac_status` |
| CFO-06 | CFO | flag | Labelled blended CAC with trailing windows is right; use strict new logos (1,550; 4.89M, not 1,584; 4.79M) and drop the payback column until Q1 |
| CFO-07 | CFO | flag | Fold into CTO-06 (columns) and CDO-09 (`as_of_month`); churn flags per `as_of_month` is the useful part |
| CDO-01 | CDO | keep | Byte hygiene; same as the CTO's BRZ-01 text, so merge them; reject vs quarantine does not touch marketing |
| CDO-02 | CDO | keep | Right gate for new PII, but it needs a versioned contract bump so acquisition-source columns (my M8-6) can land |
| CDO-03 | CDO | flag | A third manifest: fold staging LastModified and write-once into CTO-02 |
| CDO-04 | CDO | keep | The reconciliation identity that wins over CFO-02, CRO-02 and CTO-11's text; CMO-04 adds distinct-customer counts |
| CDO-05 | CDO | keep | Exact DECIMAL; wins over CTO-04 |
| CDO-06 | CDO | keep | Wins over CTO-05; include Industry.csv cells in the diff, because a reassignment restates the ICP trend |
| CDO-07 | CDO | flag | Wins over CRO-04; define the state of a `probable_left` first month, compute `is_new_logo` outside it, and flag (not reject) a state hole |
| CDO-08 | CDO | flag | The 0.5 floor is too tight: unit errors give 0.00035 or ~35,000, so use [0.01, 100] |
| CDO-09 | CDO | flag | "Every derived column" is unworkable: make it table-level, merge with CFO-07 and CTO-06, snapshot at month close |
| CDO-10 | CDO | flag | Right principle, wins over CMO-06; "no S&M below company × month" forbids GLD-06 (month × category), so reword to "no customer, industry, cohort or channel key" |
| CDO-11 | CDO | flag | Marketing is not a permitted role, and <5 suppression hides 63 of 198 month × industry cells: restrict customer-level facts, not internal counts |
| CTO-01 | CTO | keep | The proof of the one-new-column contract; it is the test for the CDO's BRZ-06 text |
| CTO-02 | CTO | keep | The one manifest |
| CTO-03 | CTO | keep | One idempotent `_ingested_at` per staging VersionId |
| CTO-04 | CTO | drop | Duplicate of CDO-05 (wins); keep the 2,436-row float evidence as a test fixture |
| CTO-05 | CTO | drop | Duplicate of CDO-06 |
| CTO-06 | CTO | keep | Wins as the lineage-columns rule over CFO-07 and CDO-09 |
| CTO-07 | CTO | flag | Apply the watermark only to views that join spend; revenue-only new-logo views run to the latest revenue month |
| CTO-08 | CTO | keep | Unknown members keep a customer in new-logo counts; matches my SQ-04/SQ-12 stance |
| CTO-09 | CTO | flag | Gold has no free-text cell; without a numeric exemption it corrupts negative payroll cells (`-0.016`); flag, not reject |
| CTO-10 | CTO | keep | Full rebuild and atomic swap protect the new-logo series; keep run folders for CDO-09 snapshots |
| CTO-11 | CTO | keep | Publish gate; add the distinct-customer identity |

Counts: keep 13, flag 20, drop 3.

## Replies

**To the CDO, on SB-04 and the CAC denominator.** We are counting the same thing. My 32 of 95 requires the next calendar month to be paid (95 of 108 are); your 34 of 108 and the CRO's 34 of 106 take the next paid month at any distance. The background rate in Mar-Dec 2022 is 6 of 272 (2.2%), so about 2-3 of the 34 are real: true Feb-2022 new logos are about 74-77, and 74 is a slightly conservative denominator. I accept `cohort_censoring = none` only, with two limits. First, edge only: Mar-Jun 2024 has 25 customers (9.5% of 262) with a 2× first payment, all of whom paid the next month, across all six industries. That is not left-censoring. Second, publish the suspects as a separate count. Effect: S&M per new logo 4.79M to 4.89M (+2.2%); 2022 8.15M to 8.95M (+9.8%); Feb-2022 alone 2.13M to 3.11M. Retail's shift holds (18.8% to 25.1%, z 2.43, down from 2.89) and Tecnología's strengthens (15.0% to 10.4%, z -2.40).

**To the CDO, on CDO-11 and CDO-10.** Of 198 month × industry new-logo cells, 63 (32%) have fewer than 5 logos (Salud 24 of 33, Servicios profesionales 19 of 33). Suppressing them hides the industries I most need to read. By quarter only 4 of 72 are under 5. Counts of pseudonymous customers are not the re-identification risk; customer-level revenue is. Restrict that, and give marketing a `mart_new_logos_month_industry` with `low_n` flags (CMO-07). On SB-08 I prefer the CRO's criterion to your 1% share. Both flag exactly 94 and 322, but a share of window revenue depends on tenure: a customer at 25× the median who joined in Jan-2024 reaches only 0.59% by Oct-2024 and would not be flagged.

**To the CFO.** CFO-06's 1,584 denominator and 4.79M include the 34 suspects, so re-run it on the canonical definition (routing rule 4). Your 90-month payback sensitivity belongs in your memo: as a gold column it will be quoted without its caveats, and the number is not interpretable until Q1 is answered. You agreed with SB-07 and kept SB-08; SB-07 gives 313 against about 64 real reactivations (my count 65 arrears-only, 62 after prepaid and split gaps; settled gaps 216 of 468 by my tie rules against the CDO's 211, both far from ⅓). A criterion beats a versioned customer list for SB-08. On SQ-10, a quarantined month blocked in gold is a state nobody can explain; I side with the CDO and reject the file.

**To the CRO.** Do not drop CAC from GLD-07. A labelled `sm_spend_per_new_logo` is the one place spend and logos meet, and dropping it makes every analyst rebuild it unlabelled. But a GLD-07 at month × industry × cohort year must carry no S&M: it would either repeat each month's spend on every row, so sums double count, or imply spend by industry. Your "2.3-5.8× does not reproduce" is granularity: annual is 5.75×, 3.21×, 2.30× and monthly is 1.61-7.62×. Both reproduce. The Retail move is not "mix, not drift": it is within new logos, and the 15.4% base includes the survivor base. SCD2-ready `valid_from` and `valid_to` would have no source date; use SCD1 and let the CDO-06 diff catch a reassignment.

**To the CTO.** GLD-03 and GLD-05 "keep" is wrong as written: neither carries `cohort_censoring`, so there is no stable new-logo flag. GLD-07 as a live view conflicts with CDO-09 snapshots; I need both, a view for exploration and a snapshot at close for anything leaving the data team. You asked the CMO and CFO to confirm GLD-04: as CMO I confirm media = PaidMedia + PublicidadNoWeb as a working mapping, still `inferred = true` until the owners answer.

## Where I changed my mind

- **SB-07 (withdrawn keep, now flag):** I reasoned from 65 win-backs, but SB-07 as written gives 313 and contradicts SB-05.
- **SQ-12 (withdrawn keep, now flag):** I kept quarantine while warning it shrinks the denominator. Load with UNKNOWN and flag. SQ-04 follows the CDO: NFC, then UNMAPPED, with UNKNOWN and UNMAPPED under one "Unknown" group on charts.
- **SQ-11 (withdrawn):** merged into SB-10, as the CDO says. **SQ-10:** keep the CDO's regex and reject the file.
- **CMO-02 (withdrawn):** CFO-03 and CFO-04 carry currency and basis.
- **CMO-06 (merged):** into CDO-10. My executable test stays: no table holds both spend measures and a customer, industry, cohort or channel key; `dim_month` and `dim_spend_category` are the only joins.
- **CMO-01 (amended):** `cohort_censoring` = `left` (first paid Jan-2022), `probable_left` (first paid month up to 2022-03 and first amount within ±5% of j × the next paid amount, j as in the CDO's SB-04), else `none`. `is_new_logo` = `none` and first paid from 2022-02. Publish `new_logos` beside `new_logos_probable_left`. Later cohorts are never excluded; a 1.9-2.1× first payment after Mar-2022 is only tagged `double_first_payment`. My round-1 "0-1 per later month" held for Mar-Dec 2022, not for 2024. Flag, inferred.
- **CMO-03 (amended):** map the 7 columns to `spend_group` and `channel_class`; an unmapped category loads as UNKNOWN and flags. A new column is caught at bronze by CDO-02.
- **CMO-04 (amended):** pre-existing + `probable_left` + new logos = distinct customers (377 + 34 + 1,550 = 1,961); new logos by industry = by month.
- **CMO-05 (amended):** `sm_spend_per_new_logo` = S&M full ÷ strict new logos, total and media-only, for the month and the trailing 3 months. NULL for Jan-2022 and for a month without spend. It carries CFO-05 `scope_status`, UNCONFIRMED currency and `sm_regime`, and has no payback column. It is not called CAC until Q1 is answered.
- **Held:** CMO-07 (`low_n`, quarterly reporting), CMO-08 (`sm_regime`), and no attribution claim. With strict logos, whole-window r moves from -0.48 to -0.55, but within regimes it stays 0.14 and -0.09: no link found, none excluded.
- **Still unresolved:** what happened in Mar-Jun 2024 (25 double first payments). Owners, please say whether a promotion or a billing change explains it.
