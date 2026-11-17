# MRR page: design (draft, 2026-11-17)

**Status.** Draft by the CTO, for the coordinator to review. The definitions (what counts as MRR, each movement type and driver, how "pricing (inferred)" is detected) belong to the CDO in `docs/mrr_discounts_model.md`. That file didn't exist when this draft was written, so the definitions here are placeholders and that file wins wherever they differ. The data contract is `contracts/mrr_api_contract.draft.md`.

**The question (CFO).** Why did our MRR change, and how much of the change is customer behaviour, how much is pricing or discounts, and how much is only the timing of payments? Also: how much revenue do we not capture because of commercial decisions (discounts)?

**What today's data can answer.** It can answer behaviour (new, reactivation, expansion, contraction, churn) and timing, meaning cash against normalized MRR (CRO-03: catch-ups, prepays, splits and uneven splits). Pricing is **inferred**, from price steps shared by many customers. Discounts and list prices **aren't in any file**, so discount movements and leakage are `null` until billing data arrives, and the page says so in plain words. It never shows 0 for them.

Scale today (local silver, 2024-10): cash 97.0M, normalized MRR 96.4M (timing about 0.6M), expansion 2.1M, contraction 1.7M, 50 new and 3 reactivated customers.

---

## 1. Layout

The same rules as Acquisition apply:
- one big number per card, with a plain word and a coloured dot;
- no legends, formula captions or jargon on the main surface: the technical detail goes behind "Details";
- sans for text and mono for numbers;
- zebra rows on dense tables;
- light and dark follow the OS;
- no dual axes, and no section repeats another.

The route is `/mrr/`. The header gets a third tab: `Finora  Data quality  Acquisition  MRR`.

```
┌ Finora   Data quality   Acquisition   MRR ──────────────── Data as of Oct 2024 · updated 17 Nov 2026  (FI) ┐

 Period [ Last 12 months · Nov 2023 – Oct 2024 ▾ ]   Basis [ MRR (normalized) ▾ ]        › Details
                                                    (the Details toggle holds the basis explainer)

 ── Why MRR changed ───────────────────────────────────────────────────────────────────────────────
 MRR went from 88.4M to 96.4M (+8.0M, +9.0%).                     ← one hero line, generated from the data

 ┌ Customer behaviour ─┐ ┌ Pricing & discounts ─┐ ┌ Timing of payments ─┐
 │  +7.6M              │ │  +0.4M               │ │  +0.6M              │   one big signed number each
 │  ● most of the change│ │  ● Pricing inferred │ │  ● cash only, not MRR│   a dot plus one plain word
 └─────────────────────┘ └──────────────────────┘ └─────────────────────┘
   The three add up to the change in cash. Timing isn't part of MRR (Details says why).

 ── MRR bridge ────────────────────────────────────────────────────────────────────────────────────
 ┌──────────────────────────────────────────────────────────────────────────────────────────────┐
 │ 96.4M                                                                              ┌──┐       │
 │ 88.4M ┌──┐   ┌──┐                                                                  │  │       │
 │       │  │   │▓▓│ +12.1M  ┌─┐ +0.5M  ┌──┐ +9.8M                                   │  │       │
 │       │  │   │▓▓│         │▓│        │▓▓│        ┌──┐ −6.9M ┌──┐ −7.9M ┌─┐ +0.4M    │  │       │
 │       │  │   │▓▓│         │▓│        │▓▓│        │░░│       │░░│      │▒│  n/a     │  │       │
 │ Opening    New     Reactivation  Expansion  Contraction   Churn   Pricing Discounts Closing │
 │ └──────────── Customer behaviour ────────────────────────────┘   └─ Pricing & discounts ─┘    │
 └──────────────────────────────────────────────────────────────────────────────────────────────┘
   Increases in blue and decreases in orange, each with a signed label at the bar's end. Opening
   and closing are grey. "Discounts" is drawn as an empty dashed slot labelled "Not available".
   › Details: the bridge as a table (step, value, customers), the cash reconciliation
     (MRR closing + timing = cash), and the provisional-churn note.

 ── Revenue not captured (discounts) ──────────────────────────────────────────────────────────────
 ┌──────────────────────────────────────────────────────────────┐
 │  —        ● Not available until billing data                 │   a grey dot and the word, not a 0
 │  We need list price and discount per invoice line to show it. │
 └──────────────────────────────────────────────────────────────┘
   › Details: what "leakage" will mean (list MRR − net MRR), what Billing must send, and the
     CFO's three examples (§1.1).

 ── MRR by month ──────────────────────────────────────────────────────────────────────────────────
 ┌──────────────────────────────────────────────────────────────────────────────────────────────┐
 │ MRR  ▁▂▂▃▃▄▄▅▅▅▆▆▆▇▇▇█  closing MRR, one 2px line, end label "96.4M"                         │
 │ Change by driver (diverging columns, aligned months, a shared crosshair):                     │
 │   ▲ behaviour (blue)   ▲ pricing & discounts (violet)   ▼ timing (grey, outline only)          │
 │ 2023 ─────────────────────────── 2024                                                          │
 └──────────────────────────────────────────────────────────────────────────────────────────────┘
   The selected period is highlighted and other months are dimmed (as on Acquisition). There is a
   3-item legend. The last 2 months are hatched and marked "provisional" (churn isn't confirmed
   until 2 months later).

 › Top movers                       (Details: customer level, zebra table, 20 per page, by |Δ|)
   Customer · Month · Movement · Driver · Before → After · Change
   #1052 · Oct 2024 · Expansion · Behaviour · 84,000 → 126,000 · +42,000
   Filters: movement type and driver. "Open all movements" pages through /api/mrr/movements.

 › Monthly data                     (Details: the bridge per month, with CSV download)
```

**The figures in the wireframe are illustrative** (scale only). They aren't computed; the real values come from gold.

**Why this order.** The hero line and the three cards answer the CFO's question in one glance ("mostly customer behaviour"). The bridge shows where the change came from. Leakage sits directly under the bridge, because it's the "what we're not capturing" half of the question, and today it's an honest "not available". The trend shows whether this period is typical. Everything at customer level is behind Details.

**No duplication.** The cards show three numbers, one per driver. The bridge shows the steps inside each driver (new, expansion and so on), not the same three numbers again. The trend shows the drivers by month, not the period totals.

**States.**
- Loading uses skeletons.
- A 401 or 403 follows the DQ and Acquisition patterns. A 404 `no_gold_run` shows "No MRR data yet".
- A provisional month (churn not yet confirmed) shows a yellow dot with "Provisional".
- A null money figure shows "—" with its reason. It never shows 0.

**URL.** `/mrr/?period=<id>&basis=mrr|cash&run=<run_id>`. Defaults are left out. Period ids follow Acquisition: `full`, `YYYY`, `YYYY-Qn`, `YYYY-MM`, plus `last12`.

### 1.1 The CFO's three examples (explainer, in Details)

Each example is three short rows. A tiny bridge with fixed text shows how the page books it. The examples are static copy, not data, and the CDO approves the wording.

| Case | Booked as (once billing data exists) | Today, without discount or list data |
|---|---|---|
| Paid 100, now pays 80, same plan, a 20 discount started | Discounts −20. Behaviour 0. Leakage +20 | Contraction −20 (behaviour). The page can't tell it apart, so it says "could be a discount" |
| Subscription grew 100 → 130 with a 30 discount, still paying 100 | Expansion +30 (behaviour, or pricing if the list price rose), discounts −30. Net 0, leakage +30 | Nothing: net MRR didn't change, so no movement is visible |
| The discount ends: 100 → 130 | Discounts +30 (discount end). **Not expansion.** Leakage −30 | Expansion +30 (behaviour), possibly flagged "pricing (inferred)" if it matches a price step |

This table is the reason the page shows the "Pricing & discounts" card as a separate driver, and why the leakage panel is honest about what can't be seen yet.

---

## 2. Data the page needs

See `contracts/mrr_api_contract.draft.md`. In short:
- `GET /api/mrr/summary`: bridge steps, drivers and statuses, plus one row per month with:
  - opening and closing MRR, cash and timing;
  - one value per bridge step, and customer counts per step;
  - list MRR, discount and leakage, each nullable;
  - a provisional flag.
- `GET /api/mrr/movements`: customer-level movements for the top movers drill-down, filtered and paged by the server.

The UI sums months for a period. It derives nothing else: every driver, step and timing value comes from gold.

---

## 3. Component plan

| Section | Reuses | New |
|---|---|---|
| Header tab | `AppHeader` (add `"mrr"` to `SECTIONS`) | none |
| Controls | `PlainSelect`, `src/lib/acq/periods.ts` (generalised to `src/lib/periods.ts`: options from `months` plus `last12`), `useAcqUrlState` pattern | `useMrrUrlState` |
| Hero line and 3 driver cards | Card and tone classes, `StatusDot`, `DeltaLine` from `FunnelWorkbench` (moved to `components/ui/Delta.tsx`) | `DriverCards` |
| Bridge waterfall | D3 scales, `columnPath` and the axis and grid code from `TimeSection` (moved to `components/charts/`), and the colour tokens `--viz-1` (up) and `--viz-2` (down) | `BridgeChart`: horizontal-baseline waterfall with floating bars, a signed label at each bar end, a null step drawn as a dashed empty slot labelled "Not available", driver brackets under the axis, per-bar focus and tooltip, and a sr-only table |
| Leakage panel | `Disclosure`, `DetailItem`, `StatusDot` (`na` tone) | `LeakagePanel` |
| Trend | `TimeSection` aligned-charts pattern (shared crosshair, keyboard reading, dimming outside the period) | `MrrTrend`: a line for closing MRR above diverging stacked columns by driver |
| Top movers | `RecordsTable` patterns (zebra, paging, `useRecords`-style query with `keepPreviousData`) | `TopMovers` + `useMrrMovements` |
| Monthly data and CSV | `MonthlySection` and `monthly-table.ts` (generalised: columns from a config) | the MRR column config |
| Exact maths | `src/lib/acq/ratio.ts` (move to `src/lib/ratio.ts`): exact sums, HALF_UP at display | none |
| Mocks | `mocks/acq` pattern: a Python generator from local silver for behaviour and timing, plus planted pricing steps. Discount fields stay null, and a second planted run has synthetic discounts so the panel's "available" state can be tested | `mocks/mrr/` |
| Tests | the vitest and Playwright plus axe patterns (light, dark, mobile), the no-mocks markers | bridge identities (opening + Σ steps = closing; Σ drivers + timing = Δcash), null handling, screenshots `mrr-*.png` |

**Chart rules.**
- Up and down use blue and orange, always with a signed label and a ▲/▼ glyph in the tooltip. They're never red or green, because a contraction isn't an error state.
- Opening and closing are neutral grey. Drivers use categorical slots 1, 7 and grey (blue, violet, neutral), validated with `validate_palette.js` against the card surfaces in both themes.
- One axis per chart, marks no wider than 24px with 4px rounded ends, a 2px surface gap, and hairline grids.
- Every chart has a table twin.

**Build estimate.**
- About 1 day once the contract is final. The mocks and the bridge chart are most of it.
- The generalising moves (periods, ratio, chart helpers, delta) are mechanical. They keep the Acquisition tests green.
