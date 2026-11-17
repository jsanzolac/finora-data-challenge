# MRR with discounts: separating subscription value from price paid

Owner: CDO. Date: 2026-11-17. Status: **proposed**, not yet approved. Nothing here changes `docs/approved_data_rules.md` until the CFO (definitions of MRR and leakage), the CRO (movement taxonomy) and Billing (the source contract) sign off. Rule IDs `MRR-xx` are proposals.

Units: `Transactions.amount` is native × 10,000 (owner definition). The currency is not stated. Figures in §1 are native. The worked examples in §3 and §4 use illustrative whole units.

**Verdict.** The current model (customer + month + amount paid) measures **cash collected**, not **subscription value**. It cannot tell a discount from a contraction, a price change from a usage change, or a late payment from a churn. Once discounts are introduced, every discount will be booked as contraction when it starts and as expansion when it ends. Finora needs three numbers per customer-month (list MRR, discount, net MRR) and two cash numbers (billed, collected). All five must come from billing and subscription data, not from payments.

---

## 1. What the current model can and cannot answer

### 1.1 What it answers well (cash basis)

| Question | How | Caveat |
|---|---|---|
| How much did each customer pay each month? | `amount` | Cash, not MRR. Billed versus collected is unknown (Q2) |
| Paying customers, new logos, cohorts, ARPPU | `is_paying`, first paid month, CDO-07 | 377 left-censored customers. First payments that are 2× or 3× multiples make up 10.1% of new revenue |
| Churn and reactivation | 3-month grace window | About ⅓ of gaps are later caught up, so a zero month is not churn |
| A movement proxy | CRO-05 on `amount_normalized` (CRO-03 + SB-11) | CRO-05 itself says "a change may come from price, tax, FX or a plan change" |

### 1.2 What it cannot answer

| Question | Why not |
|---|---|
| Did the customer contract, or receive a discount? | There is only one number, and price paid = list − discount is a single unknown |
| Is a change volume (seats, usage) or price (a list-price change)? | There is no quantity and no unit price |
| What is the subscription worth while the customer is not paying? | A zero month is ambiguous: an arrears gap, a pause, a 100% discount or churn |
| How much revenue do commercial decisions leave on the table? | List value is never observed |
| How much MRR comes back when discounts expire? | There are no end dates |
| Which month does a charge belong to? | There is a payment month, but no service period |

### 1.3 Evidence from today's data (`python3 -I` over the silver engine, golden run)

| Check | Result | What it shows |
|---|---|---|
| Naive paid-delta movement (both months > 0) versus CRO-05 on `amount_normalized` | Expansion 4,116.70 (1,294 events) → 3,499.90 (1,212). Contraction 9,090.57 (1,247) → 4,656.54 (954) | **15% of naive expansion and 49% of naive contraction are timing or lifecycle effects, not behaviour.** Movement on settled-gap rows alone is +332.86 and −2,515.97. SB-11 removes 82.48 from each side |
| Late price steps (Q18) | 141 customers. 64.68 of spurious expansion, offset by the same contraction one month later (a quick strict re-count finds 140 and 63.87) | A list-price change billed one month late looks like expansion followed by contraction |
| Contractions that return to the exact previous amount within 1–3 months | 31 of 954 events (3.2%), 107.53 of 4,656.54 (2.3%). 17 return in 1 month, 6 in 2, 8 in 3 | **This is the signature a temporary discount will leave.** Today such a dip counts as contraction and then expansion |
| Expansions that return to the previous amount within 1–3 months | 211 of 1,212 events (17.4%), 1,273.31 of 3,499.90 (36.4%), 185 of them in the next month. Example: customer 5, 10.50 → 19.53 → 10.50 | One-off charges (usage, extras, double billing) inflate expansion, and the reversal inflates contraction |
| Customer 94 (outlier) | 444.21 expansion (12.7%) and 389.34 contraction (8.4%) of the CRO-05 totals | One customer can dominate the bridge, so the bridge needs drill-down to customer and item |
| Discounts in the data | None | Finora is introducing them now. The current data is our only clean baseline where list = net (assumed, not confirmed) |

**Conclusion.** Even before discounts exist, about a third of the raw movement (5,050.83 of 13,207.27) is cash timing. Add discounts, and the model can no longer answer the CFO's question at all.

---

## 2. Separating subscription value from price paid

### 2.1 Canonical definitions (proposed)

| Term | Definition | Owner of meaning |
|---|---|---|
| **List MRR** (subscription value) | Σ over the active subscription items of quantity (seats, plan units, rated usage) × unit list price from the price-book version in effect, normalized to one month. It does not depend on what was paid | CFO + Billing |
| **Price book** | The versioned list price per product, unit and currency, with `valid_from` and `valid_to`. A **list-price change** is a new version applied to a customer | CFO / Pricing |
| **Discount** | A commercial concession that reduces list MRR. It is a first-class object with a type, a value, a start, an end (or `is_open_ended`), a reason and an approver. A negotiated permanent price below list is a discount of type `price_override`, open-ended, so that every concession is visible | CRO (grants it), CFO (policy) |
| **Discount MRR** | The monthly value of all discounts active in the month, capped at list MRR | Derived |
| **Net MRR** | List MRR − discount MRR. **This is the headline MRR** | Derived |
| **Billed** | Invoice lines for the service month: net MRR ± proration, one-offs and credit notes. Tax is excluded | Billing |
| **Collected** | Cash allocated to the service month. This is today's `Transactions.amount` | Finance |
| **Discount leakage** | Discount MRR: revenue not captured because of commercial decisions (§4.3) | CFO |

Rule of thumb: **behaviour moves list MRR at a constant price, pricing moves the price book, commercial decisions move discounts, and timing moves only cash.**

### 2.2 What the source systems must deliver (data contract for Billing)

Payments alone are not enough. The contract is one staging prefix per entity, a full or CDC extract, pseudonymized `customer_id` (the same integer N as `Transactions.ID`), with `source_system` and `extracted_at` on every row.

| Entity | Minimum fields | Why |
|---|---|---|
| `subscriptions` | subscription_id, customer_id, status, start_date, cancel_date, cancel_reason_code, billing_frequency, currency | Churn is a subscription status, not a zero payment |
| `subscription_items` (change log) | item_id, subscription_id, product_code, quantity, price_book_version, effective_from, effective_to, change_reason_code | Volume versus price |
| `usage_rated` | item_id, service_month, usage_qty, unit_list_price | Usage-driven MRR is behaviour |
| `price_book` | product_code, unit, currency, unit_list_price, version, valid_from, valid_to | List-price changes |
| `discounts` | discount_id, customer_id, subscription_id, scope (subscription or item_id), type (`percent`, `fixed`, `free_months`, `price_override`), value, currency, start_month, end_month, is_open_ended, reason_code, approver_id, approved_at, campaign_id, stacking_order, revoked_at | Separating commercial decisions |
| `invoice_lines` | invoice_id, line_id, customer_id, item_id, discount_id, line_type (`recurring`, `usage`, `discount`, `proration`, `one_off`, `credit_note`), service_period_start, service_period_end, amount_excl_tax | Billed and service-period assignment |
| `payment_allocations` | payment_id, invoice_id, paid_date, amount | Collected, and the reconciliation to today's `amount` |

**PII.** We need no names, emails or tax IDs, so they are not ingested. `approver_id` is staff personal data: it is pseudonymized in bronze, and the mapping to a person is visible only to the Finance role. Free-text discount notes are **not** ingested, because they routinely contain names. Only `reason_code` from a closed domain is kept. Discount and price data are Confidential-Financial (CDO-11): only named roles get access, and the dashboard shows aggregates by reason and team, never by approver.

### 2.3 Medallion fit

| Layer | What changes | Contract check |
|---|---|---|
| Bronze | Each new entity is landed byte-faithfully plus `_ingested_at`, with the same manifests and `_current` as today | Exactly one new column, no transformation |
| Silver (`finora_silver`) | New Iceberg tables: `price_book` (SCD2), `subscription`, `subscription_item_month` (item × month: quantity, unit list price, `list_mrr`), `discount` (SCD2 on terms), `discount_month` (discount × month: base, `discount_mrr`), `invoice_line`, `payment_allocation`. `customer_month` gains `list_mrr`, `discount_mrr`, `net_mrr`, `billed_amount` and `collected_amount` (= today's `amount`), plus `mrr_basis` (`billing` or `cash_proxy`) | Quality and business rules. Inferred rules marked as inferred |
| Gold | `fact_subscription_item_month` (the finest MRR grain), `fact_discount_month`, `fact_mrr_movement` (customer × month × `movement_type`, optionally × item), `fact_cash_reconciliation` (customer × month). Dimensions: `dim_price_book` and `dim_discount` (SCD2), `dim_product`, `dim_discount_reason`, `dim_movement_type`. `fact_customer_month_revenue` stays the cash fact and joins on (`customer_id`, `month_key`) | Facts at the finest grain. The bridge is an aggregate on top of `fact_mrr_movement` |

All amounts are exact DECIMALs with `_value` columns in full units (× 10,000 for the Transactions-derived cash). They carry `currency_status = unconfirmed` until Finance confirms the currency, following the conventions of `docs/gold_acquisition_model.md`.

### 2.4 Grain and keys

| Table | Grain | Primary key |
|---|---|---|
| `subscription_item_month` | item × service month | (`item_id`, `month`) |
| `discount_month` | discount × item (or subscription) × service month | (`discount_id`, `item_id`, `month`) |
| `customer_month` | customer × month (dense panel, as today) | (`customer_id`, `month`) |
| `fact_mrr_movement` | customer × month × movement_type (× item) | (`customer_id`, `month_key`, `movement_type`, `item_id`) |

### 2.5 DQ rules (proposed)

| ID | Rule | Severity |
|---|---|---|
| MRR-01 | `net_mrr` = `list_mrr` − `discount_mrr` exactly, per item-month and per customer-month | control (error) |
| MRR-02 | 0 ≤ `discount_mrr` ≤ `list_mrr` per item-month after stacking. Net MRR is never negative | error |
| MRR-03 | Every discount has `end_month` ≥ `start_month` or `is_open_ended` = true, never both and never neither | error |
| MRR-04 | `percent` is in (0, 100]. `fixed` > 0 with the subscription's currency. `free_months` has an `end_month` | error |
| MRR-05 | `reason_code` is in the domain and `approver_id` is present. A discount rate above the policy threshold needs the second approval level | error / flag |
| MRR-06 | A discount applies only within [start, end] and only while the subscription is active. An expired discount that is still invoiced is an error | error |
| MRR-07 | `unit_list_price` equals the price-book version in effect. Any other price must be carried as a `price_override` discount | error |
| MRR-08 | An open-ended discount older than 12 months, or a temporary discount renewed more than once, is flagged for review | flag |
| MRR-09 | The bridge closes: Σ movements per customer-month = Δ `net_mrr`, and the list and discount sub-bridges each close (§4) | control (error) |
| MRR-10 | Σ recurring + usage + discount invoice lines of a service month = `net_mrr`. Any difference is explained by proration, one-off or credit-note lines | warn |
| MRR-11 | Σ `payment_allocations` per customer-month = `Transactions.amount`. This ties the new sources to the history we already trust | control (warn during migration) |
| MRR-12 | There is one currency per subscription, and `currency_status` is set | error |

---

## 3. Classifying discount start, change and end

### 3.1 Movement taxonomy

| Block | movement_type | Measured as | Counts in expansion or contraction? |
|---|---|---|---|
| Behaviour | `new`, `reactivation` | + list MRR of the month | No (own lines) |
| Behaviour | `expansion` / `contraction` | Σ items (q_t − q_{t−1}) × p_{t−1}, at the previous month's list price | **Yes, only these** |
| Behaviour | `churn` | − list MRR of t−1. Triggered by subscription status, not by a zero payment | No (own line) |
| Pricing | `list_price_increase` / `list_price_decrease` | Σ items q_t × (p_t − p_{t−1}) | No |
| Discount | `discount_start` | − D_t of a new `discount_id` (including discounts on new or reactivated customers) | No |
| Discount | `discount_change` (active) | Terms changed on the same id: (pct_t − pct_{t−1}) × base_{t−1}, or the change in the fixed amount | No |
| Discount | `discount_base_effect` | A % discount following a list change: pct_t × (base_t − base_{t−1}), or a fixed discount capped at a lower list | No |
| Discount | `discount_end` / `discount_end_early` | + D_{t−1} of an id that is scheduled to end or revoked | **No: this is a roll-off, never expansion** |
| Discount | `discount_released_on_churn` | + D_{t−1} of a churned customer (memo: net churn = churn + this) | No |
| Timing (cash only) | `arrears`, `prepay`, `split`, `uneven_split`, `proration`, `late_price_step` | Collected − net MRR | Not an MRR movement at all |

Order of operations per customer-month: (1) lifecycle from subscription status; (2) per item, volume at the old price and then price at the new quantity (an exact decomposition, because L_t − L_{t−1} = Σ (q_t − q_{t−1}) p_{t−1} + Σ q_t (p_t − p_{t−1})); (3) per `discount_id`, start, end, active change, then base effect (for a % discount, D_t − D_{t−1} = (pct_t − pct_{t−1}) × base_{t−1} + pct_t × (base_t − base_{t−1}), also exact); (4) the customer's expansion and contraction are netted per month, with item detail kept in the fact.

A 100% or `free_months` discount keeps the subscription **active with net MRR 0**. Today the same month would look like a gap or churn candidate, and the paid month that follows would look like a reactivation or catch-up. Subscription status removes that ambiguity.

### 3.2 The CFO's three examples

| Case | List t−1 → t | Discount t−1 → t | Net t−1 → t | Classification | Answer |
|---|---|---|---|---|---|
| 1a. Pays 100 → 80, seats removed | 100 → 80 | 0 → 0 | 100 → 80 | contraction −20 | It contracted 20 |
| 1b. Pays 100 → 80, 20% promo | 100 → 100 | 0 → 20 | 100 → 80 | discount_start −20 | It received a discount. Behaviour 0, leakage 20 |
| 1c. Pays 100 → 80, price book cut | 100 → 80 (q constant) | 0 → 0 | 100 → 80 | list_price_decrease −20 | Pricing, not the customer |
| 1d. Pays 80, net is still 100 | 100 → 100 | 0 → 0 | 100 → 100 | none (MRR). Timing −20 in cash | A short payment or a split: collections, not MRR |
| 2. Grew 100 → 130 with a 30 discount, still pays 100 | 100 → 130 | 0 → 30 | 100 → 100 | expansion +30, discount_start −30 | Net MRR is flat, but **the business grew 30** and we chose to give away 30 (leakage 30 = 23.1% of list) |
| 3. The discount from case 2 ends | 130 → 130 | 30 → 0 | 100 → 130 | discount_end +30 | **Not expansion.** Net MRR +30 from discount roll-off. Expansion and list-based NRR are unchanged |

Answer to "does it count as expansion when the discount disappears?": **no.** It counts in net MRR growth and in net NRR, but on its own line. Expansion stays a behaviour metric. If the customer downgrades in the same month the discount ends (list 130 → 110), the result is contraction −20 and discount_end +30, so net is +10: both facts stay visible instead of a misleading "+10 expansion".

### 3.3 Other combinations

| Situation | Classification |
|---|---|
| Discount and a real change in the same month (case 2) | Behaviour at list and the discount on its own line. Never netted together |
| A % discount on a growing customer (list 200 → 250 with 20%) | expansion +50, discount_base_effect −10. Behaviour stays at list |
| Price-book increase with a loyalty discount to soften it (+10 list, −10 discount) | list_price_increase +10, discount_start −10. Net 0, and the concession is visible as leakage |
| Grandfathered customer on an old price | No movement until migration. At migration the change is list_price_increase. The gap to the current price book is reported separately as a legacy price gap (§4.3) |
| New customer with a 50% first-month promo | new + list, discount_start − D. The next month, discount_end + D |
| Retention save (a discount instead of churn) | discount_start with `reason_code = retention_save`. The CRO can report "saved MRR" net of the concession |
| Churn in the month after the discount ends | churn at list. The customer carries the attribute `months_since_discount_end` for discount-cliff analysis |

---

## 4. The MRR bridge

### 4.1 Structure

```
Opening net MRR (t−1)
  + New + Expansion − Contraction − Churn + Reactivation      [behaviour, at list]
  ± List-price changes                                         [pricing]
  − Discount starts ± Discount changes and base effects
  + Discount ends + Discount released on churn                 [commercial decisions]
= Closing net MRR (t)
```

There are two sub-bridges that must each close (MRR-09):
- **List bridge:** L_{t−1} + new + expansion − contraction − churn + reactivation ± price = L_t.
- **Discount bridge:** D_{t−1} + starts + increases − decreases − ends − released on churn = D_t.

Net MRR is always L − D.

### 4.2 Worked bridge (one month, 7 customers, illustrative units)

| Customer | Event in month t | List t−1 | List t | Disc t−1 | Disc t | Net t−1 | Net t |
|---|---|---|---|---|---|---|---|
| A | Removes seats | 100 | 80 | 0 | 0 | 100 | 80 |
| B | 3-month 20% promo starts | 100 | 100 | 0 | 20 | 100 | 80 |
| C | Grows to 130 with a 30 discount (CFO case 2) | 100 | 130 | 0 | 30 | 100 | 100 |
| D | 30 discount ends (CFO case 3) | 130 | 130 | 30 | 0 | 100 | 130 |
| E | +10% price book, open-ended 20% contract discount | 200 | 220 | 40 | 44 | 160 | 176 |
| F | Churns while discounted | 50 | 0 | 10 | 0 | 40 | 0 |
| G | New, with a 50% first-month promo | 0 | 120 | 0 | 60 | 0 | 60 |
| **Total** | | **680** | **780** | **80** | **154** | **600** | **626** |

| Bridge line | Amount | From |
|---|---|---|
| **Opening net MRR** | **600** | |
| New | +120 | G |
| Expansion | +30 | C |
| Contraction | −20 | A |
| Churn (at list) | −50 | F |
| Reactivation | 0 | |
| *Subtotal: customer behaviour* | *+80* | |
| List-price change | +20 | E (200 × 10%) |
| *Subtotal: pricing* | *+20* | |
| Discount starts | −110 | B 20, C 30, G 60 |
| Discount base effect | −4 | E (20% × 20) |
| Discount ends | +30 | D |
| Discount released on churn | +10 | F (memo: net churn = −40) |
| *Subtotal: discounts* | *−74* | |
| **Closing net MRR** | **626** | 600 + 80 + 20 − 74 |

Check: list 680 + 120 + 30 − 20 − 50 + 20 = 780. Discount 80 + 110 + 4 − 30 − 10 = 154. Net 780 − 154 = 626.

**Why did MRR change (+26)?** Customers added +80, pricing added +20, and discounts took −74. Behaviour accounts for +80 of the +26, and pricing and discounts together account for −54.

**Reconciliation to cash (month t).** In the example, D pays its 130 late (arrears, collected in t+1), and E prepays two months (352).

| Line | Amount |
|---|---|
| Closing net MRR | 626 |
| ± Proration, one-offs, credit notes (billed − net) | 0 |
| = Billed for service month t | 626 |
| − Arrears: billed, not yet collected (D) | −130 |
| + Prepayment of t+1 collected in t (E) | +176 |
| = **Collected in t** (what `Transactions.amount` shows) | **672** |

The current model would read this month as 672, with D "dropping to 0" (a churn candidate) and E "expanding +176". Both are timing effects.

### 4.3 Revenue not captured because of commercial decisions

| Metric | Definition | Example (month t) |
|---|---|---|
| **Discount leakage** | Σ discount MRR in the month = list MRR − net MRR | 154 |
| **Discount rate** | Discount leakage ÷ list MRR | 154 ÷ 780 = 19.7% |
| Temporary versus open-ended leakage | Split by `is_open_ended` | 110 temporary, 44 open-ended |
| Leakage by reason, cohort, industry, team | Group `fact_discount_month` by `dim_discount_reason` and the other dimensions | Acquisition promo 80 (B, G), expansion incentive 30 (C), contractual 44 (E) |
| **Scheduled roll-off** | Σ discount MRR of discounts ending in the next 1, 3 or 6 months. This is contracted uplift, **not** a forecast: apply discount-cliff churn | B 20 in 3 months, G 60 next month |
| Cumulative leakage | Σ over months of discount MRR | Board view |
| Legacy price gap (separate, optional) | Σ q × (current price-book price − price in effect) for grandfathered customers | Reported apart from discount leakage, because it is a pricing policy rather than a discount |

Out of scope for leakage: failed collections and write-offs (credit risk, not a commercial decision), and partner or accountant commissions (S&M cost, not a price concession).

---

## 5. What we can do with today's data until billing data arrives

Everything below is **inferred**. It is labelled `mrr_basis = 'cash_proxy'` and is never presented as list or net MRR.

| Approximation | How | Status |
|---|---|---|
| MRR proxy = `amount_normalized` | CRO-03 + SB-11 already remove the settlement and uneven-split timing | Approved rules, inferred meaning |
| Assume list = net before the first discount | True only if no concessions existed before. Billing must confirm | Inferred |
| `late_price_step` flag | Pattern: x_m = x_{m−1}, x_m + x_{m+1} = 2·x_{m+2}, x_{m+2} ≠ x_{m−1}. Treat it as a price change effective at m (m+1 carries the catch-up for m), not as expansion and contraction (Q18). See GLD-MRR-01 | Inferred, not yet a rule |
| `temporary_dip` / `one_off_spike` flags | A contraction or expansion that returns to the exact prior amount within 1–3 months (31 and 211 events today) | Inferred: a discount, credit, usage or extra charge |
| Candidate list-price change | The same % step in the same month across many customers on the same price-grid point | Inferred. Needs the price book to confirm |
| **Minimum viable discount register, from day 1** | If billing cannot export discounts yet, Sales Ops keeps a register (discount_id, customer_id, type, value, start, end or open-ended, reason_code, approver_id) landed in staging under a new `discounts/` prefix. Then discount_mrr = Σ register × list proxy, with list proxy = net proxy + discount. The CTO builds it after approval; no AWS change now | Required before launch |

**Recommendation:** do not launch discounts until at least the register exists. Without it, every discount enters the history as contraction followed by expansion, and **that history cannot be repaired later**, because a payment does not record why it was lower.

### 5.1 Open questions (named asks)

| ID | Ask | Owner |
|---|---|---|
| MQ-01 | Does the billing system hold subscriptions, items, quantities and a versioned price book? Can it export them with effective dates? | Billing |
| MQ-02 | Is `Transactions.amount` collected cash, net of discounts, excluding tax? (extends Q2) | Billing + Finance |
| MQ-03 | How are discounts modelled: coupons, % or fixed, free months, stacking order, proration of partial months? | Billing |
| MQ-04 | Is usage rated in arrears (billed in t+1 for t)? MRR should follow the service month | Billing |
| MQ-05 | Can invoice lines carry `line_type`, `service_period` and `discount_id`, and can payments be allocated to invoices? | Billing |
| MQ-06 | Headline MRR on net (proposed), with list as the behaviour basis: approve? | CFO |
| MQ-07 | Does a permanent negotiated price count as a discount (`price_override`, proposed) or as a lower list price? | CFO + CRO |
| MQ-08 | What are the discount approval thresholds and approver levels (MRR-05), and the closed `reason_code` domain? | CFO + CRO |
| MQ-09 | Is a free trial a discount on an active subscription, or pre-subscription (not new until first billed)? | CRO + CFO |
| MQ-10 | Revenue recognition: are discounts spread over the contract term (IFRS 15 / ASC 606)? MRR stays operational and is reconciled to recognized revenue separately | Finance |
| MQ-11 | Currency (still unstated) and whether multi-currency subscriptions exist | Finance |
| MQ-12 | Is the 141-customer late price step (Q18) a billing-cycle artefact? Is the 0.21 grid the price book? | Billing |

---

## 6. Gold build spec (for the CTO)

Scope: phase 1 builds on silver `customer_month` (one run, `as_of_month` 2024-10, `churn_confirmed_through` 2024-08) with `mrr_basis = 'cash_proxy'`. The billing columns exist, are NULL, and are filled by phase 2 without a schema change. Conventions follow `docs/gold_acquisition_model.md`: exact DECIMALs, native columns DECIMAL(18,6), `_value` = native × 10,000 as DECIMAL(18,2) (exact, because native values have 6 decimals), `month_key` as in `dim_month`, `currency_status = 'unconfirmed'`, and `_run_id` on every row. Access: Confidential-Financial (CDO-11), the same roles as `fact_customer_month_revenue`.

**Layer note.** GLD-MRR-01 is an inferred business rule. Under the layer contract it belongs in silver (proposed SB-12). Until it is approved there, gold computes it and labels it `is_inferred`. Nothing in silver changes.

### 6.1 `fact_customer_month_mrr`: customer × month

Dense panel. PK (`customer_id`, `month_key`). 66,674 rows.

| Column | Type | Definition |
|---|---|---|
| `customer_id`, `month_key`, `industry_key`, `cohort_month_key` | INT, INT, SMALLINT, INT | Keys, as in `fact_customer_month_revenue` |
| `lifecycle_state` | STRING | Silver `customer_month.lifecycle_state` |
| `mrr_basis` | STRING | `cash_proxy` today, `billing` once billing data arrives |
| `collected_amount`, `_value` | DECIMAL(18,6), DECIMAL(18,2) | Silver `amount` (cash) |
| `mrr_proxy`, `_value` | DECIMAL(18,6), DECIMAL(18,2) | Silver `amount_normalized`, except that months m and m+1 of a GLD-MRR-01 step = x_{m+2} |
| `list_mrr`, `discount_mrr`, `net_mrr`, `billed_amount` (+ `_value` each) | DECIMAL(18,6) / (18,2), **NULL** | Filled from billing (§2). MRR-01: `net_mrr` = `list_mrr` − `discount_mrr` |
| `mrr`, `mrr_value` | DECIMAL(18,6), DECIMAL(18,2) | Headline: `net_mrr` when `mrr_basis` = `billing`, else `mrr_proxy`. NULL for a hole |
| `timing_adjustment`, `_value` | DECIMAL(18,6), DECIMAL(18,2) | `collected_amount` − `mrr` |
| `timing_type` | STRING | Silver `settlement_type` (`arrears`, `prepay`, `split`, `uneven_split`), else `late_price_step` on GLD-MRR-01 months, else NULL |
| `is_inferred_price_step`, `price_step_start_month` | BOOLEAN, STRING | True on months m and m+1. `YYYY-MM` of m |
| `is_hole`, `is_provisional` | BOOLEAN | From silver. `is_provisional` = month > `churn_confirmed_through` |
| `currency_status`, `_run_id` | STRING | |

### 6.2 `fact_mrr_movement`: customer × month × movement

One row per non-zero movement. PK (`customer_id`, `month_key`, `movement_type`, `item_id`, `discount_id`). 4,589 rows today.

| Column | Type | Definition |
|---|---|---|
| `customer_id`, `month_key`, `industry_key`, `cohort_month_key` | INT, INT, SMALLINT, INT | Keys |
| `movement_type` | STRING | Domain in `dim_movement_type` (6.4) |
| `driver` | STRING | `behaviour`, `pricing`, `discount` or `timing` |
| `amount`, `amount_value` | DECIMAL(18,6), DECIMAL(18,2) | Signed. Σ per customer-month = `mrr`(t) − `mrr`(t−1) |
| `prior_state`, `state` | STRING | `lifecycle_state` at t−1 and at t |
| `is_inferred`, `inference_rule` | BOOLEAN, STRING | For example `GLD-MRR-01`, `GLD-MRR-02.pause` |
| `cro05_covered` | BOOLEAN | True when both months are `paying` (where silver CRO-05 computes a value) |
| `is_one_off_spike`, `is_temporary_dip` | BOOLEAN | GLD-MRR-03 flags (inferred). The movement itself is not reclassified |
| `is_outlier_customer` | BOOLEAN | Customer in the silver outlier list (94, 322) |
| `is_provisional`, `mrr_basis` | BOOLEAN, STRING | |
| `item_id`, `discount_id` | STRING NOT NULL | `-` today (they are PK members, so not NULL) |
| `price_book_version`, `discount_reason_key` | STRING, SMALLINT, NULL | Phase 2 |
| `_run_id` | STRING | |

### 6.3 `agg_mrr_bridge_month`: the bridge aggregate (month × line)

PK (`month_key`, `line`). It covers 2022-02 → 2024-10, which is 33 months × 24 lines = 792 rows. 2022-01 exists only as the opening balance of 2022-02. Columns: `month_key`, `section` (`mrr` or `cash`), `line`, `line_order` SMALLINT, `driver`, `amount` DECIMAL(18,6) NULL, `amount_value` DECIMAL(18,2) NULL, `events` INT (rows of `fact_mrr_movement`; for opening and closing, customers with `mrr` > 0), `mrr_basis`, `is_provisional`, `_run_id`.

| Section | Lines (line_order) |
|---|---|
| mrr | `opening` 0, `new` 1, `reactivation` 2, `expansion` 3, `contraction` 4, `churn` 5, `pause` 6, `resume` 7, `grace_drop` 8, `list_price_change` 9, `inferred_price_step` 10, `discount_start` 11, `discount_change` 12, `discount_base_effect` 13, `discount_end` 14, `discount_released_on_churn` 15, `first_payment_multiple` 16, `closing` 17 |
| cash | `timing_arrears` 20, `timing_prepay` 21, `timing_split` 22, `timing_uneven_split` 23, `timing_late_price_step` 24, `collected` 25 |

**Lines that cannot be observed on `cash_proxy` (9 and 11–15) are NULL, not 0.** Discounts are unknown, not absent. Other lines with no events are 0.

### 6.4 Classification rules on today's data

ACTIVE = {`new`, `paying`, `reactivated`, `settled_gap`}, which are exactly the states with `mrr_proxy` > 0. `paused`, `grace`, `churned` and `pre_acquisition` have `mrr_proxy` = 0.

**GLD-MRR-01: late price step (inferred).** For each customer, scan m from the earliest month upward. The window m−1 … m+2 matches when: all four months are `paying` with `amount` > 0 and `settlement_type` NULL; no month of the window is already tagged; and, in exact Decimal arithmetic with x = `amount`, x_m = x_{m−1}, x_m + x_{m+1} = 2·x_{m+2} and x_{m+2} ≠ x_{m−1}. Then `mrr_proxy` of m and m+1 = x_{m+2}. Σ per customer is preserved.

**GLD-MRR-02: one movement per customer-month, first match wins** (t > 2022-01, Δ = `mrr`(t) − `mrr`(t−1)):

| # | Condition | movement_type | driver | amount | Inferred |
|---|---|---|---|---|---|
| 1 | t is the customer's first month with `amount` > 0 | `new` | behaviour | `mrr`(t) | no |
| 2 | `state`(t) = `reactivated` | `reactivation` | behaviour | `mrr`(t) | no |
| 3 | `is_churn_event`(t) | `churn` | behaviour | −`mrr`(t−1) | no |
| 4 | `state`(t−1) ∈ ACTIVE and `state`(t) = `paused` | `pause` | behaviour | −`mrr`(t−1) | yes: a pause or uncollected revenue |
| 5 | `state`(t−1) = `paused` and `state`(t) ∈ ACTIVE | `resume` | behaviour | `mrr`(t) | yes |
| 6 | `state`(t−1) ∈ ACTIVE and `state`(t) = `grace` | `grace_drop` | behaviour | −`mrr`(t−1) | no, provisional (a later run restates it as churn, resume or settlement) |
| 7a | Both ACTIVE, Δ ≠ 0, t = m of GLD-MRR-01 | `inferred_price_step` | pricing | Δ | yes |
| 7b | Both ACTIVE, Δ ≠ 0, `state`(t−1) = `new`, `state`(t) = `paying`, `mrr`(t−1) ∈ {2, 3} × `mrr`(t) exactly | `first_payment_multiple` | timing | Δ | yes: a prepaid first invoice |
| 7c | Both ACTIVE, Δ ≠ 0 | `expansion` if Δ > 0, else `contraction` | behaviour | Δ | no. `cro05_covered` = both months `paying` |

Run control: in every case the amount equals Δ, and every Δ ≠ 0 gets exactly one row. Today Δ = 0 for every other pair.

**GLD-MRR-03: flags (inferred).** For an `expansion` or `contraction` at t: if `mrr` returns exactly to `mrr`(t−1) at t+1, t+2 or t+3 (the first match), with the state in ACTIVE, set `is_one_off_spike` (expansion) or `is_temporary_dip` (contraction).

**Phase 2 (billing).** When `mrr_basis = 'billing'`, the movements follow §3.1 on `list_mrr` and `discount_mrr` per item and discount. Churn comes from subscription status. The cash lines become `collected − net_mrr`, split by invoice `line_type` and payment allocation. GLD-MRR-01 and rule 7b are retired for those months.

### 6.5 Run controls (the build fails on any miss)

| ID | Control |
|---|---|
| GC-MRR-1 | Σ `mrr_proxy` = Σ `collected_amount` per customer, for all 1,961 customers, exact (Σ `timing_adjustment` per customer = 0) |
| GC-MRR-2 | Per customer-month, Σ `fact_mrr_movement.amount` = Δ `mrr`, exact |
| GC-MRR-3 | Per month, `opening` + Σ mrr lines 1–16 = `closing`, and `closing` + Σ cash lines 20–24 = `collected` = Σ silver `amount`. `opening`(t) = `closing`(t−1) |
| GC-MRR-4 | Σ (`expansion` + `contraction` where `cro05_covered`) + Σ `inferred_price_step` = Σ silver (`expansion_amount` − `contraction_amount`) = −1,156.634330 |
| GC-MRR-5 | Billing lines 9 and 11–15 are NULL when `mrr_basis` = `cash_proxy`. MRR-01 and MRR-02 hold when it is `billing` |

### 6.6 Expected figures on today's files (golden run, native units, 2022-02 → 2024-10)

| Item | Expected |
|---|---|
| GLD-MRR-01 steps | 140 windows in 140 customers. Timing on `late_price_step` months: 280 rows, Σ |adj| 127.739094. The brief's Q18 figure (141 customers, 64.68) is not reproduced by this strict test: see MQ-12 |
| Opening `mrr` (2022-01) | 3,500.030835 (35,000,308.35 full), 377 customers |
| Closing `mrr` (2024-10) | 9,636.064683 (96,360,646.83 full), 1,678 customers |
| Net movement | +6,136.033848 = behaviour +6,320.070330 + pricing (inferred) +57.436743 + timing −241.473225 + discount NULL |
| `new` | 1,584 events, +10,548.251196 |
| `reactivation` | 64, +1,602.749232 |
| `expansion` | 1,116, +3,707.896089 (`cro05_covered` 1,072, +3,375.380760; other 44, +332.515329) |
| `contraction` | 897, −6,281.965923 (`cro05_covered` 814, −4,589.451833; other 83, −1,692.514090) |
| `churn` | 301, −3,486.389529 |
| `pause` / `resume` | 193, −1,901.644479 / 193, +2,457.988533 |
| `grace_drop` | 46, −326.814789 |
| `inferred_price_step` | 140, +57.436743 |
| `first_payment_multiple` | 55, −241.473225 |
| `fact_mrr_movement` rows | 4,589, of which 581 have `is_inferred` (193 + 193 + 140 + 55) |
| GLD-MRR-03 flags | `is_one_off_spike` 222 (+1,325.161824). `is_temporary_dip` 31 (−110.196093) |
| GC-MRR-4 | CRO-05 expansion 3,499.903452 − covered expansion 3,375.380760 = 124.522692. CRO-05 contraction 4,656.537782 − 4,589.451833 = 67.085949. The difference, 57.436743, equals `inferred_price_step` |
| Timing Σ |adj| by type (rows) | arrears 4,105.445054 (376), prepay 498.743700 (94), split 938.687596 (31), uneven_split 82.483002 (22), late_price_step 127.739094 (280). Net over all rows: 0 |
| Customers 94 and 322 | Customer 94: 29 movements, expansion +450.147852, contraction −389.343129 |
| Bridge mismatches (GC-MRR-3) | 0 of 33 months |

**Test fixture, 2024-10** (provisional, because 2024-10 > `churn_confirmed_through`):

| Line | Amount |
|---|---|
| opening | 9,274.712517 |
| new | +220.133340 |
| reactivation | +217.944993 |
| expansion | +212.900352 |
| contraction | −174.803937 |
| churn, pause, inferred_price_step | 0 |
| resume | +116.008620 |
| grace_drop | −230.012202 |
| first_payment_multiple | −0.819000 |
| list_price_change, discount_* | NULL |
| **closing** | **9,636.064683** |
| timing_arrears | +64.680000 |
| other timing lines | 0 |
| **collected** | **9,700.744683** (= Σ `Transactions.amount` for 2024-10) |
