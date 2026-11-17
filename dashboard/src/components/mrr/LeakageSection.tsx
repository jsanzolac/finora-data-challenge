"use client";

import { formatExact, formatMoney } from "@/lib/acq/format";
import { Ratio } from "@/lib/acq/ratio";
import type { PeriodBridge } from "@/lib/mrr/bridge";
import type { MrrSummary } from "@/lib/mrr/types";
import { DetailItem, Disclosure } from "@/components/ui/Disclosure";
import { StatusDot } from "@/components/ui/StatusDot";

/**
 * Revenue not captured because of commercial decisions (docs/mrr_discounts_model.md §4.3):
 * discount leakage = list MRR − net MRR. Today there is no list price or discount data, so
 * the panel says so in plain words and never shows 0.
 */
export function LeakageSection({ summary, bridge }: { summary: MrrSummary; bridge: PeriodBridge }) {
  const available = summary.statuses.discount_data_status !== "not_available" && bridge.leakage !== null;
  const listMrr = bridge.months.map((month) => Ratio.tryParse(month.list_mrr_value));
  const lastList = listMrr[listMrr.length - 1] ?? null;
  const rate = available && bridge.leakage && lastList && !lastList.isZero() ? bridge.leakage.div(lastList).mul(Ratio.of(100n)) : null;

  return (
    <section aria-labelledby="leakage-title" className="flex flex-col gap-5" data-testid="leakage">
      <h2 id="leakage-title" className="text-xl font-semibold">
        Revenue not captured (discounts)
      </h2>
      <div className="card flex flex-col gap-2 p-6" data-kpi-id="mrr.leakage">
        <p className="num font-mono text-4xl leading-none font-semibold" data-testid="leakage-value">
          {available ? formatMoney(bridge.leakage) : "—"}
        </p>
        {available ? (
          <p className="text-[0.9375rem] text-ink-2">
            A month on average{rate ? `, ${formatExact(rate, 1)}% of list MRR` : ""}.
          </p>
        ) : (
          <>
            <p className="flex items-center gap-2 text-base font-semibold text-ink-2" data-testid="leakage-status">
              <StatusDot status="na" size={10} />
              Not available until billing data
            </p>
            <p className="text-[0.9375rem] text-ink-2">It needs the list price and the discount on every invoice line.</p>
          </>
        )}
      </div>
      <Disclosure testId="leakage-details">
        <dl className="divide-y divide-line">
          <DetailItem term="Discount leakage">
            The discounts given in a month: list MRR minus the MRR customers actually pay. It is revenue not captured because of commercial
            decisions.
          </DetailItem>
          <DetailItem term="Also shown, once available">
            The discount rate (leakage ÷ list MRR), temporary against open-ended discounts, leakage by reason, cohort and industry, and the
            scheduled roll-off: discounts ending in the next 1, 3 or 6 months. Roll-off is contracted uplift, not a forecast.
          </DetailItem>
          <DetailItem term="Not leakage">Failed collections and write-offs (credit risk), and partner or accountant commissions (S&amp;M cost).</DetailItem>
          <DetailItem term="What Billing must send">
            Subscriptions and their items, the versioned price book, discounts (type, value, start, end, reason) and invoice lines with their
            service period. Until then, a discount is indistinguishable from contraction.
          </DetailItem>
        </dl>
      </Disclosure>
    </section>
  );
}
