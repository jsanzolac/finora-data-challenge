# Round 3: CDO decision on uneven splits (SB-11)

**Date:** 2026-11-17. **Status:** approved by the CDO and added to `docs/approved_data_rules.md` as **SB-11**, with status `flag (Q17)`. The user asked for it after reviewing customer 12. **Implementer:** CTO. **Classification:** Confidential-Financial. Customer IDs are pseudonyms (`Cliente N`), and readers are limited to the `finance`, `revops` and `data` roles (CDO-11). Amounts are native `amount` values: multiply by 10,000 for the full amount (owner definition). The currency is not stated.

**Source checked:** `data/Transactions.csv`, SHA-256 `2dcbe59e…3ae95`, which is byte-identical to `s3://al-test-dl-staging/transactions/Transactions.csv` (read-only hash, 2026-11-17). The figures come from `python3 -I` with exact `Decimal`. Effects were measured by running the deployed `etl/silver_build/engine.py` on the golden inputs, with SB-11 applied through the engine's `lifecycle_map` hook. All run controls passed.

## Verdict

- **Definition.** Months m and m+1 of a customer form an uneven split when months m−1, m, m+1 and m+2 are all known-paid with no `settlement_type`, x_{m−1} = x_{m+2} = b, x_m ≠ b, and x_m + x_{m+1} = 2b. Every test is **exact** Decimal equality.
- **Today:** 11 pairs in 10 customers (22 rows). Customer 12 (Nov–Dec 2022) is one of them.
- **Effect:** both months get `settlement_type` = `uneven_split` and `amount_normalized` = b. Raw `amount` and every revenue total are unchanged. Σ expansion and Σ contraction each fall by 82.483002, and the net is unchanged.
- **DQ:** the rule is a row `flag`, so the 22 rows are visible on the dashboard. It does not count toward compliance, and department row compliance stays 100.00 / 99.95 / 100.00.
- **Deferred:** runs of 3 or more months (6 runs), pairs whose two baselines differ (including customer 12's own Oct–Nov 2023), and a large related family (141 one-month-late price steps). All are named below and routed to Billing.

## 1. The case

| Customer 12 | 2022-10 | 2022-11 | 2022-12 | 2023-01 |
|---|---|---|---|---|
| `amount` (raw line) | 6.72 | 7.154784 (line 386) | 6.285216 (line 387) | 6.72 |
| CRO-05 today | — | expansion 0.434784 | contraction 0.869568 | expansion 0.434784 |
| CRO-05 with SB-11 | — | 0 | 0 | 0 |

7.154784 + 6.285216 = 13.440000 = 2 × 6.72, exactly. All four rows pass every quality rule and are `paying`. SB-06 never looks at them, because there is no unpaid month.

## 2. Candidate definitions tested

Notation: x is the native amount. The pair is months (m, m+1), and both must be known-paid in every candidate.

| # | Baseline b | Sum test | Other conditions | Pairs | Customers | Verdict |
|---|---|---|---|---|---|---|
| A | x_{m−1} only | exact | x_m ≠ b | 20 | 17 | Too loose: the 9 extra are price changes, coincidences, half of a back-to-back run and pairs with an unpaid far side (§3) |
| B | x_{m+2} only | exact | x_m ≠ b | 173 | 169 | Wrong pattern: 141 of the 162 extra are price steps billed one month late |
| A ∪ B | either side | exact | x_m ≠ b | 182 | 175 | Inherits both problems |
| **C** | **x_{m−1} = x_{m+2}** | **exact** | **x_m ≠ b** | **11** | **10** | **Chosen** |
| C | both sides | abs ≤ 0.000001, 0.0001 or 0.01 | x_m ≠ b and x_{m+1} ≠ b | 11 | 10 | Same set: there is no rounding near-miss |
| C | both sides | relative ≤ 0.5% or 1% | x_m ≠ b and x_{m+1} ≠ b | 11 | 10 | Same set |
| C | both sides | relative ≤ 2% or 5% | x_m ≠ b and x_{m+1} ≠ b | 12 | 11 | Adds a false positive: customer 40, 2022-03 and 2022-04 (24.6036, then 24.1164 and 24.1164, then 24.6036), a two-month dip |
| C | both sides | relative ≤ 5% (the SB-06 tolerance) | x_m ≠ b only | 29 | 24 | Adds customer 40 and 17 one-month bumps, for example customer 45 (9.03, 9.658824, 9.03, 9.03) |
| A | x_{m−1} only | relative ≤ 5% | x_m ≠ b and x_{m+1} ≠ b | 452 | 327 | Dominated by price changes |

**Why C, exact:**
1. **Both baselines.** The month after the pair must return to the month before it. That is what separates "the same two-month total, split unevenly" from a price change. Each one-sided version mostly catches price changes.
2. **Exact.** The count is flat from exact equality up to a ±1% tolerance. The first case added beyond that, at ±2%, is a false positive. Exactness also makes `amount_normalized` = b exact, so CRO-03's per-customer identity holds without a remainder. That is why the tolerance is fixed in the rule text and is not a parameter.
3. **x_m ≠ b.** Without it, two ordinary months would match. Given the sum, it also implies x_{m+1} ≠ b.
4. **Minimum history: one known-paid month on each side.** Requiring two equal months before the pair would drop 3 of the 11 (78, 370 and 437) and remove no false positive. All 11 also have x_{m+3} = b, but requiring it adds nothing.
5. **Condition (2), no settlement in the window.** It blocks no window today. It exists for precedence (§5).

## 3. Near-misses (not tagged)

| Family | Found by | Count | Cases | Why not tagged |
|---|---|---|---|---|
| Price step billed one month late | B only | 141 pairs in 141 customers (137 increases; 126 with the catch-up month in 2024-05 to 2024-09; typical step +3.7% to +4.5%) | For example customer 64: 5.093298 (2024-07), 5.342904 (2024-08), then 5.218101 from 2024-09. The new price plus the missed difference is billed in the first new month | A different meaning: a price change, not an unchanged total. Today it adds 64.679832 to both Σ expansion and Σ contraction. Proposed Q18 (§9) |
| Baselines differ (a price change at the pair) | A or B only | 5 (A) + 9 (B) | A: 15 2022-11 (the first half of a back-to-back run, §5), 36 2023-12, 78 2022-04, 97 2022-10, 97 2024-02. B: **12 2023-10**, 51 2022-10, 95 2023-08, 144 2023-11, 161 2024-05, 412 2023-03, 1026 2024-04, 1167 2024-06, 1259 2024-07 | The "usual amount" is ambiguous. Several are arithmetic coincidences (97's price oscillates; the A hit of 78 overlaps its real pair by one month) |
| Customer 12's own near-miss | B only | 1 | 6.72 (2023-09), 7.05012 (2023-10), 6.80988 (2023-11), 6.93 from 2023-12: 7.05012 + 6.80988 = 2 × 6.93, the new price | Baselines differ (6.72 before, 6.93 after). CRO-05 keeps +0.33012, −0.24024, +0.12012, which nets to the +0.21 price step. Covered by Q17(c) |
| Far side not paid | A only | 2 | 310: 15.12, then 12.6 and 17.64 (2024-08, 2024-09), then 0 in 2024-10 (`grace`). 313: 14.7, then 13.65 and 15.75 (2022-06, 2022-07), then 0 in 2022-08 (`paused`) and 29.4 in 2022-09 | Without month m+2 a split cannot be told apart from a price change. For 313, smoothing p would have let the 2022-08 gap settle as arrears (29.4 = 2 × 14.7). SB-06 runs on raw amounts and first, so this is not chained (deferred) |
| Near side not paid, or before W | B only | 9 | 47 and 128 at 2022-01 (m−1 falls before W); 486, 537, 871, 887, 1006, 1196, 1324 (m is the first paid month) | First-payment patterns, already described by SB-04 and CRO-07. A pair can never include the first paid month |
| One-month bump or first-payment ramp | A or B only | 2 (A) + 3 (B) | A: 113 2022-05, 487 2022-04 (m−1 is the first paid month). B: 15 2023-01, 172 2022-02, 378 2022-09 | One of the pair equals the baseline on the far side |

## 4. Every occurrence (11 pairs, 10 customers, 22 rows)

| # | Customer | m−1 | m | m+1 | m+2 | b = x_{m−1} = x_{m+2} | x_m | x_{m+1} | d = x_m − b | x_m ÷ b | `source_line` m, m+1 | Cohort (censoring) | Gross CRO-05 today: expansion = contraction = 2·abs(d) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 12 | 2022-10 | 2022-11 | 2022-12 | 2023-01 | 6.72 | 7.154784 | 6.285216 | +0.434784 | 1.064700 | 386, 387 | 2022-01 (left) | 0.869568 |
| 2 | 34 | 2022-04 | 2022-05 | 2022-06 | 2022-07 | 26.25 | 32.8125 | 19.6875 | +6.5625 | 1.250000 | 1128, 1129 | 2022-01 (left) | 13.125000 |
| 3 | 78 | 2022-04 | 2022-05 | 2022-06 | 2022-07 | 1.575 | 2.3625 | 0.7875 | +0.7875 | 1.500000 | 2624, 2625 | 2022-01 (left) | 1.575000 |
| 4 | 93 | 2023-06 | 2023-07 | 2023-08 | 2023-09 | 8.979369 | 8.349369 | 9.609369 | −0.63 | 0.929839 | 3148, 3149 | 2022-01 (left) | 1.260000 |
| 5 | 191 | 2022-04 | 2022-05 | 2022-06 | 2022-07 | 6.51 | 7.665 | 5.355 | +1.155 | 1.177419 | 6466, 6467 | 2022-01 (left) | 2.310000 |
| 6 | 336 | 2022-05 | 2022-06 | 2022-07 | 2022-08 | 9.45 | 1.05 | 17.85 | −8.4 | 0.111111 | 11397, 11398 | 2022-01 (left) | 16.800000 |
| 7 | 336 | 2023-01 | 2023-02 | 2023-03 | 2023-04 | 9.45 | 1.05 | 17.85 | −8.4 | 0.111111 | 11405, 11406 | 2022-01 (left) | 16.800000 |
| 8 | 370 | 2022-01 | 2022-02 | 2022-03 | 2022-04 | 3.15 | 4.2 | 2.1 | +1.05 | 1.333333 | 12549, 12550 | 2022-01 (left) | 2.100000 |
| 9 | 437 | 2023-12 | 2024-01 | 2024-02 | 2024-03 | 9.22068 | 13.172397 | 5.268963 | +3.951717 | 1.428571 | 14850, 14851 | 2022-02 (none) | 7.903434 |
| 10 | 576 | 2024-02 | 2024-03 | 2024-04 | 2024-05 | 9.45 | 3.15 | 15.75 | −6.3 | 0.333333 | 19578, 19579 | 2022-06 (none) | 12.600000 |
| 11 | 651 | 2023-01 | 2023-02 | 2023-03 | 2023-04 | 7.98 | 11.55 | 4.41 | +3.57 | 1.447368 | 22115, 22116 | 2022-08 (none) | 7.140000 |
| | | | | | | | | | Σ abs(d) = 41.241501 | | | | **82.483002** |

**Facts:**
- All 44 window months are `paying` with no `settlement_type`.
- The first month is above b in 7 pairs and below it in 4.
- 7 of the 10 customers are left-censored. Three pairs (34, 78 and 191) fall in the same months, May and June 2022.
- Customer 336 repeats the identical split (1.05 and 17.85 around 9.45) eight months apart.
- None of the customers is an outlier (94 and 322 have no pair).
- Industries: Restaurantes 5, Producción 2, Retail 1, Tecnología 1, Salud 1.

**Inference (unconfirmed):** the ratios x_m ÷ b range from 0.11 to 1.5, so no single proration formula explains them. The shared May–June 2022 months suggest a billing event that Billing can identify.

## 5. Longer runs (3 or more months): they exist, and they are deferred

**General test:** a run of L ≥ 2 known-paid months, with b on both sides, a sum of exactly L × b, and the first and last months different from b. It finds the same 11 pairs at L = 2, plus 6 runs at L ≥ 3:

| Customer | Months | L | Pattern (b) | Gross CRO-05 inside the run (expansion = contraction) |
|---|---|---|---|---|
| 15 | 2022-11 to 2023-02 | 4 | 3.15, 15.75, 3.15, 15.75 (9.45): two uneven pairs back to back | 25.200000 |
| 72 | 2024-02 to 2024-05 | 4 | 1.26 three times, then 27.833736 (7.903434): partial payments, then a catch-up | 26.573736 |
| 125 | 2023-11 to 2024-04 | 6 | 13.17561 five times, then 9.72195 (12.6): over-billed, then credited | 3.453660 |
| 390 | 2023-04 to 2023-06 | 3 | 23.855895, 15.945426, 31.878756 (23.893359) | 15.933330 |
| 881 | 2024-03 to 2024-08 | 6 | 20.685, 19.425 four times, 18.165 (19.425): two unrelated one-month bumps, a coincidence | 2.520000 |
| 999 | 2023-11 to 2024-01 | 3 | 3.074316 twice, then 2.671368 (2.94): over-billed, then credited | 0.402948 |

**Decision: defer.** The six runs carry at least four different meanings: back-to-back splits, partial payment with a catch-up (arrears-like, but with no zero month), over-billing followed by a credit, and coincidence (881). One rule would assert a single meaning for all of them. False positives also grow with L, as 881 shows. Overlap and minimal-run semantics would need their own decision. This returns with the Q17 answer.

## 6. Precedence

| Topic | Decision |
|---|---|
| Stage order | Stage E: SB-06 → SB-05 / SB-07 / CDO-07 → **SB-11** → CRO-03 → CRO-05. SB-11 reads final lifecycle states and SB-06 settlement types, and must finish before CRO-05 computes movements |
| SB-06 (arrears > prepay > split) | SB-06 settles first, and a month with any `settlement_type` is neither a pair month nor a baseline. A pair month can never be an SB-06 settling month by construction, because a settling month always borders an unpaid month and every window month is paid. Only a baseline month can be one, and condition (2) excludes it. Today condition (2) blocks 0 windows |
| Re-tagging | Windows are tested in increasing m, and a tagged month is never re-tagged and never serves as a baseline. With exact equality, two pairs can never overlap: (m, m+1) and (m+1, m+2) would force x_m = b. Two pairs may share an untagged baseline month |
| Holes and excluded months (H1–H11) | Every window month must be known-paid, so a window with a hole is not tested and gets no flag and no finding. CRO-05's H9 already flags the movement next to a hole (`MOVEMENT_UNKNOWN`). A broken stretch (H3) can never touch a pair |
| Negative or zero amounts | Not paid (SB-03), so the window fails |
| Outliers (SB-08) | The rule applies to them too. Their medians use raw amounts and do not change. Today neither 94 nor 322 has a pair |
| `lifecycle_state` | Unchanged. The pair months are always `paying`, and the CTO should assert it. Month m−1 may be `new` or `reactivated`: allowed, and CRO-05 already gives 0 at m in that case. Month m+2 is `paying` |
| Censoring and cohorts | Left-censored customers are covered (7 of 10 today). The earliest possible pair is 2022-02 and 2022-03 (customer 370). Because m−1 must be paid, a pair never contains the first paid month, so `cohort_month`, `cohort_censoring`, new logos and SB-04 / CRO-07 are untouched |
| Right edge, `churn_confirmed_through`, `is_provisional` | Month m+2 must be delivered, so the last pair can start at `as_of_month` − 2 (2024-08 today). A pair in the last two months of W is undecided until the next delivery, and the full rebuild (CTO-10) then tags it retroactively, as it already does for lifecycle states. No unpaid month is involved, so `churn_confirmed_through` plays no part. `is_provisional` is unchanged |
| CDO-06 (restatement) | A change in the tagged set between runs is derived, not a restated value, and is not written to the restatement log. A restated amount inside a window is logged by CDO-06b as today |

## 7. Effect on silver and on downstream metrics

**`finora_silver.customer_month`** (the only table that changes):

| Column | Pair months | Everything else |
|---|---|---|
| `settlement_type` | `uneven_split` (a fourth value next to `arrears`, `prepay` and `split`) | as today |
| `settlement_confidence` | `high` (exact match, baseline confirmed on both sides) | as today |
| `amount_normalized` | b on both months, which is (x_m + x_{m+1}) ÷ 2 exactly | as today |
| `uneven_split_start_month` (**new**, string `YYYY-MM`) | month m on both rows, so (`customer_id`, `uneven_split_start_month`) identifies the pair | NULL, holes included |
| `expansion_amount`, `contraction_amount`, `amount_lag12` | recomputed by CRO-05 from `amount_normalized` | recomputed where t−1 or t−12 is a pair month |
| `amount`, `amount_value`, `is_paying`, `lifecycle_state`, `is_catch_up`, `is_prepaid`, `is_provisional`, `is_churn_event` | unchanged | unchanged |

The `transactions`, `customer`, `gap`, `month_control`, `industry`, `sm_spend`, `source_status` and `restatement_log` tables are identical before and after; this was verified row by row, ignoring lineage columns. Σ `amount` per month and per customer is unchanged. Σ `amount_normalized` per customer still equals Σ `amount` (CRO-03), while Σ `amount_normalized` per month moves inside a pair, as it already does for settled gaps.

| Uses raw `amount` (unchanged by SB-11) | Uses `amount_normalized` (changed by SB-11) |
|---|---|
| Revenue totals (`month_control.revenue_total`, Σ `amount_value`), ARPA and ARPPU, cohort revenue, `is_paying` (SB-03), first paid amount and cohort censoring (SB-04, CRO-07), medians and outliers (SB-08), the S&M ÷ revenue tripwire (CDO-08), settlement tests (SB-06) | CRO-05 `expansion_amount`, `contraction_amount`, `amount_lag12`; later the NRR and GRR built from them (CRO-06, gold, deferred) |

## 8. DQ dashboard

- **Rule:** SB-11 "Uneven split of a two-month total". Layer `silver_business`, kind `row`, action `flag`, inferred `true`, `counts_toward_compliance` false, status `flag (Q17)`.
- **Counts:** `evaluated` = included Transactions rows (66,674); `failed` = included rows with `settlement_type` = `uneven_split` (22). Today: 66,674 / 22 / 99.97 / `warn`. A flag never reaches `fail`.
- **Records:** 22, one per row, so a user can tap the rule and see both rows of every pair with their raw `ID`, `month` and `amount`. `failed_columns` is `["amount"]`. The reason names the pair and its baselines and holds no amount, for example `UNEVEN_SPLIT: 2022-11 and 2022-12 sum to twice the amount of 2022-10 and 2023-01`.
- **Department figures:**
  - `row_compliance_pct` is unchanged (transactions 100.00, industry 99.95, sm_spend 100.00), because flags never change it.
  - `rules_evaluated` and `rules_failing` are unchanged (SB-11 does not count).
  - `rows_flagged` for `transactions` goes from 0 to 22.
  - `rank` is unchanged. Tie-break 3 compares 22 / 66,674 = 0.03% with sm_spend's 5 / 34 = 14.7%, so transactions stays first.
- **Access:** customer-level records are Confidential-Financial, for `finance`, `revops` and `data` (CDO-11 (1)). No HR-sensitive column is involved.

## 9. Expected results on today's files

**Unchanged (verified):**
- Transactions: 66,674 rows; Σ `amount` 221,441.504508 (Σ `amount_value` 2,214,415,045.08); Σ `amount_normalized` 221,441.504508.
- Cohorts: 377 left, 43 probable_left, 1,541 new logos (68 in Feb-2022); 116 and 64 first-month spikes.
- Lifecycle states: paying 31,366; pre_acquisition 29,321; churned 3,811; new 1,541; settled_gap 281; paused 231; reactivated 64; grace 59.
- Gaps: 468, of which 211 are settled (arrears 155, prepay 47, split 9) and 193 are paused; 64 reactivations in 60 customers; 237 open churn spells; 46 customers in grace; 5,399 provisional rows.
- Outliers: {94, 322}, with a portfolio median of 5.25.
- DQ: row compliance 100.00 / 99.95 / 100.00, the ranks, and every other rule result.
- Controls: all 16 run controls pass, and the CRO-03 identity holds for 1,961 of 1,961 customers.

**Changed:**

| Figure | Before | After |
|---|---|---|
| `transactions.rows_flagged` | 0 | 22 |
| SB-11 (`transactions`) | — | 66,674 / 22 / 99.97 / warn |
| Flagged records | 5 | 27 |
| `customer_month` rows with `settlement_type` = `uneven_split` | 0 | 22 (11 pairs, 10 customers) |
| Σ `expansion_amount` (full amount) | 3,582.386454 (35,823,864.54) | 3,499.903452 (34,999,034.52) |
| Σ `contraction_amount` (full amount) | 4,739.020784 (47,390,207.84) | 4,656.537782 (46,565,377.82) |
| Rows with expansion > 0; with contraction > 0 | 1,230; 969 | 1,212; 954 |
| Net movement | −1,156.634330 | −1,156.634330 |
| `customer_month` cells that differ | — | `settlement_type`, `settlement_confidence`, `amount_normalized`, `uneven_split_start_month`: 22 each; `expansion_amount` 18; `contraction_amount` 15; `amount_lag12` 18 (the 9 pairs that start no later than 2023-09) |
| `_rules_version` | current hash | a new hash, because the rules config changes. This is expected on every row |

## 10. Question for Billing (Q17), ready to send

> **Subject: Two consecutive monthly charges that differ but add up to two normal months (11 cases)**
>
> In the monthly revenue extract (`Transactions.csv`) we found 11 cases, in 10 customers, where a customer who pays the same amount every month is charged two different amounts in two consecutive months, and those two months add up exactly to two normal months. Example: customer 12 pays 6.72 every month, was charged 7.154784 in November 2022 and 6.285216 in December 2022 (together 13.44 = 2 × 6.72), and is back at 6.72 from January 2023. The 11 cases are in the attached table (customer, months, amounts).
>
> 1. What causes this: proration after a change of billing date, a payment applied to the wrong month, a correction between two invoices, or something else? Is the cause the same in all 11 cases? Three of them (customers 34, 78 and 191) are in May and June 2022.
> 2. For growth reporting, may we treat each pair as two normal months, meaning the customer neither expanded nor contracted? Or do the uneven amounts reflect a real change in what the customer bought in those months?
> 3. We also see 6 longer runs (3 to 6 months) that add up to the usual amount, and one similar pair at a price change. Examples: customer 72 paid 1.26 for three months and then 27.833736 (together 4 × 7.903434). Customer 125 paid 13.17561 for five months and then 9.72195 (together 6 × 12.6). Customer 12 paid 7.05012 and 6.80988 in October and November 2023 (together 2 × 6.93, its new price from December 2023). Are these partial payments, credits after an overcharge, or the same mechanism as above? Should they be treated the same way?
>
> Amounts are in the extract's native units (× 10,000 for the full amount). Until we hear from you, we smooth only these 11 pairs, and only in growth metrics (expansion and contraction). Revenue totals and raw amounts are unchanged.

The attachment is the table in §4 with the `source_line`, d and ratio columns removed. Attach it only to the Billing owner, because it is Confidential-Financial.

**Proposed Q18 (not yet in `approved_data_rules.md`; the CRO and Billing should decide whether to raise it):** 141 customers show a price step billed one month late, 126 of them with the catch-up month in May to September 2024. Example: customer 64 paid 5.093298 through July 2024, 5.342904 in August 2024 and 5.218101 from September 2024, so the new price plus the missed difference for July was billed in August. Was that price increase effective one month before it was first billed? If so, an analogous smoothing would place the increase in the right month and remove 64.679832 from both Σ expansion and Σ contraction. That is a separate rule decision and needs this answer first.

## 11. Notes for the CTO

**Where.** In `engine.lifecycle()`, after every state is assigned (after the `for i in P: … state[i] = "paying"` block) and before the `# CRO-05 / H9` loop. The Spark path (`lifecycle_map`, applyInPandas) then gets it unchanged. Return the new per-month list (`uneven_split_start_month`) and the list of pairs in the lifecycle output.

**Exact algorithm** (x = `cells`, all `Decimal` parsed from the raw strings; never float; no quantize before comparing. `Decimal("6.72") == Decimal("6.720000")` is true, which is intended):

```
for m in range(1, n - 2):                       # needs m-1 >= 0 and m+2 <= n-1
    win = (m - 1, m, m + 1, m + 2)
    if any(hole[i] for i in win):         continue
    if not all(cells[i] > 0 for i in win): continue
    if any(stype[i] is not None for i in win): continue   # SB-06 or an earlier pair
    b = cells[m - 1]
    if cells[m + 2] != b:                 continue
    if cells[m] == b:                     continue
    if cells[m] + cells[m + 1] != 2 * b:  continue
    assert state[m] == "paying" and state[m + 1] == "paying"
    for i in (m, m + 1):
        stype[i], sconf[i], norm[i], us_start[i] = "uneven_split", "high", b, W[m]
    pairs.append(m)
```

**In `build()`:**
- Add `uneven_split_start_month` to each `cm_rows` entry, to `common/schemas.py` (`customer_month`, `string`) and to the Iceberg schema. Each run is a full rebuild, so this is a column addition only.
- In the per-customer loop where SB-05 and CRO-05 are counted, call `cnt.add("SB-11", "transactions")` for every included row.
- For each tagged month, call `r.flag("SB-11", ["amount"], f"UNEVEN_SPLIT: {W[m]} and {W[m+1]} sum to twice the amount of {W[m-1]} and {W[m+2]}")` and `cnt.add("SB-11", "transactions", 0, True)`.
- Add `figures["uneven_split_pairs"]` (11) and `figures["uneven_split_customers"]` (10).

**Elsewhere:**
- **Glue DQ:** nothing to add. SB-11 is cross-row and runs in the Spark business stage like SB-05 and CRO-05.
- **Config:** regenerate `etl/config/dl_rules.yaml` and `.json` with `python etl/config/build_rules_yaml.py`. I checked that its `build()` parses the amended document: 44 catalog entries, SB-11 with its description, CRO-03's new sentence.
- **Dashboard:** no change is expected. `dashboard_rules()` picks SB-11 up as a row rule, and its records page like SB-10's.
- **Parity check:** `scripts/compare_dq_runs.py <old> <new>` should differ only in the SB-11 rule, `transactions.rows_flagged` and `records/SB-11/transactions/`.
- **Golden tests** (`etl/tests/test_golden.py`): add SB-11 (66674, 22, 99.97, "warn") and transactions `rows_flagged` 22, plus the 22 SB-11 records with the source lines in §4 and the CRO-05 totals in §9. Keep every unchanged figure asserted as it is.

**Fixtures to add** (synthetic, one customer per case):

| # | Case | Expected |
|---|---|---|
| F1 | Customer 12 pattern: 6.72, 6.72, 7.154784, 6.285216, 6.72, 6.72 | Tagged; `amount_normalized` 6.72 on both months; expansion and contraction 0 at m, m+1 and m+2; reason text and `uneven_split_start_month` as specified |
| F2 | First month below b: 9.45, 1.05, 17.85, 9.45 | Tagged |
| F3 | Sum off by 0.000001 | Not tagged |
| F4 | Baselines differ: 6.72, 7.05012, 6.80988, 6.93 | Not tagged |
| F5 | Month m+2 unpaid: 15.12, 12.6, 17.64, 0; and a pair in the last two months of W | Neither is tagged |
| F6 | Month m−1 is the first paid month (`new`): 0, 6.72, 7.0, 6.44, 6.72 | Tagged; CRO-05 0 at m (as today), 0 at m+1 and m+2 |
| F7 | Hole at m+2 (an excluded row, for example a bad amount) | Not tagged; no SB-11 flag; CRO-05 `MOVEMENT_UNKNOWN` as today |
| F8 | Hole at m−1 | Not tagged |
| F9 | Baseline m−1 is the catch-up month q of an arrears gap: 6, 0, 12, 14, 10, 12 | Not tagged (condition 2) |
| F10 | Two pairs sharing a baseline: b, x, 2b−x, b, y, 2b−y, b | Both tagged; the shared month untagged |
| F11 | Back-to-back (customer 15): 9.45, 9.45, 3.15, 15.75, 3.15, 15.75, 9.45 | Nothing tagged (runs of 3+ are deferred) |
| F12 | Price step billed late: old, old, 2·new − old, new | Not tagged |
| F13 | Two-month dip (customer 40): 24.6036, 24.1164, 24.1164, 24.6036 | Not tagged |
| F14 | A negative amount in the window | Not tagged |
| F15 | Pair at W[1] and W[2] for a customer paying in W[0] (left-censored, customer 370) | Tagged; `cohort_censoring` stays `left` |
| F16 | Pair with 14+ months of W after it | `amount_lag12` at m+12 and m+13 equals b |
| F17 | Raw strings `6.72` and `6.720000` as the two baselines | Equal (Decimal) and tagged |
| F18 | Outlier customer with a pair | Tagged; median and `is_outlier_customer` unchanged |

**Invariants to assert in tests:**
- The CRO-03 identity holds per customer.
- Σ `amount` per month is unchanged.
- Every pair month is `paying`.
- Every pair has exactly 2 rows sharing one `uneven_split_start_month`.
- The SB-11 flag count equals the number of `uneven_split` rows.
