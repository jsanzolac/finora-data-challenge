# Round 1: CRO position

**Stance.** The baseline is close on revenue rules. I keep the 3-month grace (SB-05) and the ±5% catch-up (SB-06): both pass my tests. Four defects would distort what I report: SB-07 counts 313 win-backs where 65 are real; the left edge leaks (34 of Feb-2022's 106 "new" logos look like Jan-2022 customers paying late); SB-08 has no criterion and ignores customer 322; and silver and gold cannot yet compute GRR/NRR (Oct-2024: NRR 93-96%, GRR 86-87%, so growth is acquisition-led). Gold must be additive so total → industry → cohort → customer → month reconciles. Figures were re-run by me with `python3 -I` over `data/`, unless marked "(profile)".

## M1 Inventory
**Agree:** three datasets; Transactions is a customer × month panel, not a log. **Add:** all 1,961 customers have at least one paid month, so there are no trials or lost leads (no conversion funnel), and no plan, module, channel or accountant field (see M8). No rules.

## M2 Profile
**Agree:** 66,674 rows, 0 duplicate keys, 0 negatives, 50.55% zeros, IDs ordered by first paid month (0 violations). **Add:**
- Normalising catch-ups cuts 2022 month-on-month stdev only from 15.4% to 12.5%: catch-ups explain about a fifth of the swings, not most.
- Feb-2022 has 108 "new" logos against 17-38 a month after; 34 of 106 first payments are ≈2× the next (0-6% in other months checked).
- No regular billing cadence exists (0 customers with ≥3 payments at a constant interval ≥2 months).
- "S&M is 2.3-5.8× revenue" does not reproduce: 1.61-7.62× by month (Oct-2024 200.0M vs 97.0M). CFO/CDO to settle.

**Verdicts:** none (no rules).

## M3 Bronze security
No position: outside my area. Remark: keep zero rows verbatim; zero-versus-missing underlies every churn rule.

## M4 Silver quality rules
**Agree:** SQ-05/07/08/12 hold today (0 duplicate keys, 0 negatives, 66,674 = 1,961 × 34, 0 orphans). **Change** (replacement text), because in a dense panel the onFailure would drop or distort revenue:
- SQ-05: quarantine all rows of a duplicate key and store the cell as unknown (CRO-01); never sum or pick one.
- SQ-07: non-numeric → quarantine; negative → load, flag, exclude from `is_paying` (a refund is contraction and must stay visible).
- SQ-08: check completeness up to each load's latest month; a hole is quarantine, not flag.
- SQ-12: orphan Transactions ID → load with industry `Unknown`, flag; Industry-only ID → keep in `dim_customer` with no cohort, flag.

| ID | Layer | Dataset | Rule | Evidence | onFailure | Inferred |
|---|---|---|---|---|---|---|
| CRO-01 | silver | transactions | Unknown is not zero: a missing, duplicate-key or quarantined customer-month is NULL (`amount_status='unknown'`), never 0; NULL does not count as a zero month in SB-05 and makes the customer provisional | Panel is 100% dense today, so a hole is a load defect | flag | no |
| CRO-02 | silver, gold | transactions | Revenue reconciles: Σ `amount_value` = bronze Σ `amount` × 10,000, per month and industry, at every layer; a variance blocks the gold load | 221,441.50 native = 2,214,415,000 full | reject | no |

| Rule | Verdict | Reason |
|---|---|---|
| SQ-05 | flag | Holds, but "reject" drops revenue; use the text above |
| SQ-07 | flag | 0 negatives; quarantining a refund hides contraction |
| SQ-08 | flag | Holds; a hole breaks consecutive-zero counts |
| SQ-12 | flag | 0 orphans; quarantine breaks reconciliation (CRO-02) |

## M5 Silver business rules
**Agree:** SB-01/02 (owner-stated); flag, never delete. **Change** (replacement text):
- **SB-04:** Cohort = first paid month. Jan-2022 = pre-existing (377, IDs 1-377). Feb-2022 is `is_cohort_edge`; a first payment within ±5% of 2× the next is `is_first_catch_up`. Edge logos stay out of new-logo trends until owners confirm.
- **SB-05:** Churned = ≥3 consecutive zero months after the last paid month, with no catch-up after them. Dated at the first zero month, confirmed at the third. Trailing 1-2 zeros are provisional (46 in Oct-2024; 14-18 should return, my estimate from the M7 hazards). A plain return after ≥3 zeros is a reactivation; only a catch-up reverses a churn.
- **SB-07:** Reactivation = first paid month after a churned run that is not a catch-up. Non-catch-up gaps of 1-2 zeros are `short_gap` (late or missed). Of 468 gaps: 248 short non-catch-up, 144 short catch-up, 65 true reactivations, 11 long catch-up.
- **SB-08:** `is_outlier` = median paid amount ≥25× the portfolio median (5.25). Flags exactly 94 and 322 (6.63% of revenue); the next is 18.6×. It lives on `dim_customer`; every KPI is published for all and ex-outliers.
- **SB-09:** SCD1 now, but build `dim_customer` SCD2-ready (`valid_from`, `valid_to`, `is_current`).

| ID | Layer | Dataset | Rule | Evidence | onFailure | Inferred |
|---|---|---|---|---|---|---|
| CRO-03 | silver | transactions | `amount_normalized`: a catch-up after k zeros is spread over k+1 months; `amount` untouched | 155 catch-ups; total unchanged | flag | yes |
| CRO-04 | silver | transactions | `lifecycle_state`: `pre_customer`, `paying`, `gap` (1-2 zeros, or closed by catch-up), `churned`; plus `is_provisional` | 221 zero customer-months sit in catch-up gaps (active, paid late) | flag | yes |
| CRO-05 | silver | transactions | `expansion_amount` = max(Δ,0), `contraction_amount` = max(−Δ,0) on `amount_normalized` between consecutive paid months (not new, reactivation or catch-up); `amount_lag12` | 91.7% unchanged; naive Oct-2024 expansion 2.36% vs contraction 2.37% of prior MRR; contraction larger in 9 of 12 months | flag | yes |
| CRO-07 | silver | transactions | New-logo starting ARPA = median first paid amount; flag `is_first_month_spike` (first payment ≥3× later median) | 64 of 1,384 customers; 2022 cohort first-payment mean 12.15 vs median 6.30 | flag | yes |

| Rule | Verdict | Reason |
|---|---|---|
| SB-03 | keep | Min positive 0.14, no dust; rename `is_paid_month`, "active" is CRO-04 |
| SB-04 | flag | Feb-2022 spike (108 vs 17-38); owner confirmation |
| SB-05 | flag | Threshold holds (M7); needs dating, provisional state, catch-up precedence |
| SB-06 | keep | ±5% on a flat plateau, placebo-clean (M7) |
| SB-07 | flag | Contradicts SB-05: 313 "win-backs" vs 65 real |
| SB-08 | flag | No criterion; 322 (second largest, last paid Jan-2024) exits; removing 94+322 moves raw NRR 93.2% → 94.9% |
| SB-09 | flag | Unverifiable (no dates); Retail share 15.4% → 26.0% by cohort is mix, not drift; owners to confirm |

## M6 Gold dimensional model
**Agree:** customer × month fact plus dimensions. **Add:** `cohort_month_key` role-plays `dim_month`.

| ID | Layer | Dataset | Rule | Evidence | onFailure | Inferred |
|---|---|---|---|---|---|---|
| CRO-06 | gold | retention | GRR, NRR, logo churn from additive components (base MRR, churned, contraction, expansion, ending MRR; base, retained, churned logos), 12-month lookback, MRR proxy = 3-month average of `amount_normalized`; raw variant kept. CDO to confirm | Oct-2024 vs Oct-2023: NRR 93.2% raw vs 96.2% smoothed; GRR 85.8% vs 87.3%; logo retention 90.0% point vs 92.2% with grace | flag | yes |

| Rule | Verdict | Reason |
|---|---|---|
| GLD-01 | keep | Add `month_index`, window-start flag |
| GLD-02 | keep | Add `Unknown` member (SQ-12) |
| GLD-03 | flag | Add `first_paid_month`, `first_paid_amount`, `last_paid_month`, `churn_status`, `is_pre_existing`, `is_cohort_edge`, `is_outlier` |
| GLD-05 | flag | Add `amount_normalized`, `lifecycle_state`, `expansion_amount`, `contraction_amount`, `amount_lag12`, `is_provisional`; keep zero rows |
| GLD-07 | flag | Rebuild at month × industry × cohort year × outlier flag, additive columns only; drop CAC until M8-4 (Oct-2024 S&M per new logo 4.0M vs ARPPU 57.8k = 69 months). CFO owns CAC |

## M7 Verification: threshold tests
| Rule | Test | Result |
|---|---|---|
| SB-05 | Return hazard by zero-run length | After 1 zero 43.9%, 2: 16.0%, 3: 7.7%, 4: 6.5%, 5: 3.3%, 7-8: 1.0%. No sharp knee; 3 is where it falls below 10% |
| SB-05 | Churn events that later return, by k | k=2 35.6%, k=3 24.3%, k=6 11.9% (lower bounds). Holds; expect ≥24% restatement |
| SB-05/06 | Conflict | 11 of 76 gaps ≥3 end in a catch-up; SB-06 takes precedence |
| SB-06 | Tolerance sweep | 0%: 137; ±2%: 152; ±5%: 155; ±10%: 163; ±20%: 181. Plateau at ±5% |
| SB-06 | Placebo, 1-zero gaps (n=330) | 2× matches 122; 3× and 4× match 3 each. Holds |
| SB-08 | Alternatives | Customer lifetime > Q3+1.5·IQR flags 123 customers = 33.6% of revenue: the tail, not outliers. ≥25× median flags 2 |

Industry (Oct-2024 vs Oct-2023, smoothed, bootstrap 95% CI): Retail NRR 89.7% (84.5-95.4), Tecnología 103.8% (96.5-112.4). Retail logo churn is 14.6% vs 8.0% for the rest (z≈3), yet cohort-based 12-month logo retention is 90.7-94.6% in all six industries (n=56-233). Not robust, so gold must make it drillable.

## M8 Open questions for the data owners
1. Zero months: unbilled, unpaid, paused or churned?
2. Invoiced, collected or recognised? What are the first-month spikes (setup fee?) and the off-grid amounts (24% → 46% of paying rows, profile)? This decides expansion versus contraction.
3. Customers 94 and 322: enterprise or multi-entity? Did 322 leave after Jan-2024?
4. Does Transactions cover the whole base, including pre-2022 churned customers and never-paid signups? Blocks CAC.
5. Feb-2022 spike: a migration or late Jan payments?
6. Who assigns industry; can it change?
7. Can we get plan, module, channel and accountant-partner IDs per customer? Without them I cannot size the accountant channel or expansion.
