# Round 1: CMO position

The data supports one marketing view: company-wide monthly S&M beside new logos by industry. It cannot attribute any customer to a channel, campaign or lead, and gold must not imply otherwise. I accept most of the baseline. My changes: (1) keep the 7 native S&M columns with two roll-ups; (2) flag a suspect cohort in the CAC denominator, because Feb-2022 looks inflated; (3) label any CAC-type number unvalidated until the owners confirm scope; (4) map an unknown industry to UNKNOWN instead of quarantining it; (5) no spend-to-industry allocation in gold. All figures below were re-run on `data/*.csv` with `python3 -I`.

## M1 Inventory

**Agree:** three datasets; S3 keys and sizes match `data/` (read-only listing: 49,402 / 2,063 / 1,302,387 bytes).
**Add:** no lead, trial, signup-date, channel, campaign, geo or sales-vs-marketing field exists. `Industry.csv` holds only customers who paid at least once (0 of 1,961 never paid), so funnel conversion cannot be computed.

## M2 Profile (figures I re-checked)

| Figure | Result |
|---|---|
| S&M mix | 34 months, 238/238 cells conform. Media 59.3% (PaidMedia 44.4%, PublicidadNoWeb 15.0%), people 30.0%, other 10.7%. Monthly average 274.6M / 209.2M / 197.5M (2022 / 2023 / Jan-Oct 2024) |
| Budget pattern | Totals on a 0.05 grid in 34/34 months. Travel, PublicidadNoWeb, Freelance and SoftwareTools are whole-percent shares of the total in 34/34 months (PaidMedia 33/34); Team 22/34, PayrollExpenses 21/34 (the plug). Treat as planned spend until confirmed |
| New logos | 377 pre-existing + 1,584 new (Feb-22 to Oct-24, 48.0/month) = 1,961. Jan-May 2023: 301M spend, 45.2 new/month; Jul-Dec 2023: 138M, 63.0 |
| Feb-2022 | 108 new vs 30 in Mar-22. Of 95 with a next paid month, 32 paid a first amount 1.9-2.1x the next, vs 0-1 per month in Mar-Dec 2022: many are late January payers |
| Gaps | 468 gaps, 155 catch-ups (33.1%). Non-catch-up resumptions 313 (19.8% of new logos); win-backs after 3+ zero months 65 (4.1%) |
| Spend vs new logos | Whole window r = -0.48 (lag 0), -0.50 (lag 1), n=33. Within each regime (Mar-22 to May-23, Jun-23 to Oct-24) \|r\| <= 0.14, n=15/17. New logos vs prior-month paying base: +0.63. Spend fell while the base grew: a trend artifact |
| Scope | S&M / revenue in full amounts: 5.75x (2022), 3.21x (2023), 2.30x (2024). S&M per new logo 4.79M vs median first paid month 42,000 and mean in-window revenue per new logo 0.74M |
| Industry | Retail share of new logos 17.9% (Feb-Dec 2022), 26.0% (2023), 24.0% (2024), z = 2.9; Tecnologia 14.2% to about 10.4%, z = -2.1. Median first paid month: Salud 58,800; Restaurantes and Tecnologia 52,500; Produccion 42,000; Serv. prof. 31,500; Retail 25,200 |

## M3 Bronze security checks

No position: outside my area.

## M4 Silver quality rules

**Agree:** SQ-01 to SQ-13 are structurally sound. **Change:** replace SQ-04.

| Rule | Verdict | Reason |
|---|---|---|
| SQ-04 | flag | Replacement: map an unseen `Industria` value to `UNKNOWN`, flag it, keep the row. Quarantine drops the customer from revenue and from the new-logo count. Verified: 6 values, 0 variants, counts 529/454/428/241/165/144 |
| SQ-09 | keep | 34 unique contiguous months verified. A missing month stays NULL, never zero-filled |
| SQ-10 | keep | 238/238 match; the 5 negatives parse (`-$0.053` to `-$0.003`) |
| SQ-11 | keep | Negatives only in PayrollExpenses, at most 3.5% of a month. Zero Freelance (17 months) passes; it marks a regime, not an error |
| SQ-12 / SQ-13 | keep | 100% key match, identical 34-month window. Orphan quarantine would silently shrink the CAC denominator; CMO-04 reconciles it |

## M5 Silver business rules

**Agree:** reactivations are never new logos, because cohort = first paid month. **Add:**

| ID | Layer | Dataset | Rule | Evidence | onFailure | Inferred |
|---|---|---|---|---|---|---|
| CMO-01 | silver | transactions | `acquisition_confidence`: `pre_existing` (first paid Jan-2022), `suspect_late_first_payment` (first paid amount 1.9-2.1x the next paid amount), else `observed`. Suspects stay in counts, flagged | Feb-2022: 32 of 95; Mar-Jun 2024 also 5/8/5/7, so flag, not drop | flag | yes |
| CMO-02 | silver | sm_spend | Every spend row carries `currency = UNCONFIRMED` and `basis = UNCONFIRMED` (actual vs budget) until the owners answer | Whole-percent allocation of round totals (M2) | flag | yes |
| CMO-03 | silver | sm_spend | Map the 7 source column names to `spend_group` (media / people / other) and `channel_class` (digital_paid / offline / non_media). A new column fails the load | Meanings inferred from names (dictionary §6) | quarantine | yes |

| Rule | Verdict | Reason |
|---|---|---|
| SB-02 | keep | 1.040 gives 104,000,000 (owner example). Use DECIMAL, not float |
| SB-04 | flag | 377 pre-existing verified (IDs 1-377, 0 order violations), but Feb-2022 is also suspect: add CMO-01 |
| SB-07 | keep | Win-backs are 4.1% of new logos, so excluding them from the denominator is safe |
| SB-09 | flag | Owners must say whether industry is set at signup (Q7). Compare cohorts on new logos only: the pre-2022 base is a survivor mix |
| SB-10 | flag | Keep the negative, never floor it; PayrollExpenses is the plug, so owner confirmation is needed (Q2). It overlaps SQ-11: keep one check, one interpretation |

## M6 Gold dimensional model

**Agree:** a star schema with a long-format spend fact; aggregates only from facts. **Add:**

| ID | Layer | Dataset | Rule | Evidence | onFailure | Inferred |
|---|---|---|---|---|---|---|
| CMO-04 | gold | cross | Reconcile: pre-existing + new logos = distinct customers; new logos summed by industry = summed by month | 377 + 1,584 = 1,961 | reject | no |
| CMO-05 | gold | agg_month_kpis | Name it `sm_spend_per_new_logo` (total and media-only), NULL for Jan-2022, with `cac_status = unvalidated` until Q1 is answered | 4.79M per new logo vs median first paid month 42,000 | flag | yes |
| CMO-06 | gold | cross | No fact or view joins spend to `dim_industry`, `dim_customer` or a channel. `dim_month` is the only link between revenue and spend | S&M has no customer, industry or channel key | reject | no |
| CMO-07 | gold | agg | Industry rates carry `low_n` when a cell has under 10 new logos; report by quarter | Salud median 3 new logos a month (0-7), Serv. prof. 3.5 (0-9) | flag | yes |
| CMO-08 | gold | dim_month | Add `sm_regime` (`pre_2023_06` / `post`) | Spend -48% in Jun-2023, Freelance to 0, Team fixed; in-regime r about 0 | flag | yes |

| Rule | Verdict | Reason |
|---|---|---|
| GLD-02 | flag | Add an `UNKNOWN` member and `taxonomy_confirmed = false` (supports SQ-04). 6 industries verified |
| GLD-03 | flag | Add `acquisition_confidence` (CMO-01), a `cohort_month` key into `dim_month` and `first_paid_amount_value`. Keep churn out: it changes over time |
| GLD-04 | flag | Right for finance. Marketing needs a second hierarchy, `channel_class` (PaidMedia digital, PublicidadNoWeb offline); keep the 7 raw names as leaves. Team and PayrollExpenses mix sales and marketing, so gold can say "S&M", and "marketing" only for the 2 media columns. Travel and Freelance need owner confirmation (Q4) |
| GLD-06 | keep | Month x category is the right grain; carry the CMO-02 columns through |
| GLD-07 | flag | CAC becomes CMO-05. Add media-only and fully loaded variants, new logos by industry and `acquisition_confidence` counts. No lag columns: show month-level spend and new logos side by side, with CMO-08 |

| Gold supports | Gold must not claim |
|---|---|
| New logos by month, quarter and industry; entry ticket by industry | Channel, campaign or lead attribution |
| Spend by month and category, two roll-ups | Spend by industry, or spend split by new-logo share |
| Co-movement within a regime, with caveats | Causal lift or a spend-to-acquisition lag |
| Unvalidated S&M per new logo | A CAC or payback figure for the board |

## M7 Verification

| Claim | Attempt to disprove | Result |
|---|---|---|
| Data shows no spend-to-acquisition link | Lags 0-6, by regime, first differences (r = 0.14) | No link found, and none excluded: n=15/17 per regime, budgeted spend |
| Feb-2022 is inflated | First vs next payment, all cohorts | Holds: 32 of 95 vs 0-1 per later month |
| Retail shift is real | z-test vs Feb-Dec 2022, not the survivor base | Holds: z = 2.9 |

Attribution needs UTMs on signup, an accountant referral code and a holdout or geo test on PaidMedia; the CTO owns the build.

## M8 Open questions for the data owners

1. Does `Transactions.csv` cover every customer the S&M spend is meant to acquire? (Blocks CAC; CFO.)
2. Is S&M actual or budget? What do the negative PayrollExpenses months mean?
3. What sits in PaidMedia and PublicidadNoWeb? Where are accountant-partner commissions and referral fees?
4. Are Team, PayrollExpenses, Travel and Freelance sales or marketing?
5. Is the first paid month the signup month? Is there a trial or sales cycle (sets the lag)?
6. What drove the Jun-2023 break, and which channels carried the +39% in new logos afterwards? Is there an acquisition-source field in the CRM?
7. Who assigns industry, and when? Do "Servicios profesionales" customers include accountants?
8. Are the Feb-2022 "new" customers really new? (CDO decides the definition.)
9. Which currency?
