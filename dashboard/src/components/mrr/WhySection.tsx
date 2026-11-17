"use client";

import { formatMonth } from "@/lib/format";
import { formatCompact, formatExact, formatSignedCompact } from "@/lib/acq/format";
import { rangeLabel } from "@/lib/acq/periods";
import { Ratio } from "@/lib/acq/ratio";
import type { PeriodBridge } from "@/lib/mrr/bridge";
import type { MrrSummary } from "@/lib/mrr/types";
import { DetailItem, Disclosure } from "@/components/ui/Disclosure";
import { StatusDot } from "@/components/ui/StatusDot";

export const DRIVER_COLOR: Record<string, string> = {
  behaviour: "var(--viz-1)",
  pricing: "var(--viz-2)",
  discount: "var(--viz-2)",
  timing: "var(--viz-spend)",
};

function Swatch({ driver }: { driver: string }) {
  return <span aria-hidden="true" className="inline-block size-2.5 shrink-0 rounded-sm" style={{ background: DRIVER_COLOR[driver] ?? "var(--ink-3)" }} />;
}

/** The CFO's cases, from docs/mrr_discounts_model.md §3.2. Static explainer copy, not data. */
const CASES: [string, string, string, string][] = [
  ["Pays 100 → 80, seats removed", "100 → 80", "Contraction −20", "It contracted 20"],
  ["Pays 100 → 80, 20% promo", "100 → 80", "Discount started −20", "A discount. Behaviour 0, leakage 20"],
  ["Pays 100 → 80, price book cut", "100 → 80", "List price decrease −20", "Pricing, not the customer"],
  ["Pays 80, MRR is still 100", "100 → 100", "No MRR change; timing −20 in cash", "A short payment: collections, not MRR"],
  ["Grew 100 → 130 with a 30 discount", "100 → 100", "Expansion +30, discount started −30", "MRR flat, but the business grew 30 and we gave away 30"],
  ["That discount ends", "100 → 130", "Discount ended +30", "Not expansion: a discount roll-off"],
];

/** The worked bridge, docs/mrr_discounts_model.md §4.2 (7 customers, illustrative units). */
const WORKED: [string, string][] = [
  ["Opening MRR", "600"],
  ["New, expansion, contraction, churn", "+80"],
  ["List-price change", "+20"],
  ["Discounts started, base effect, ended, released on churn", "−74"],
  ["Closing MRR", "626"],
];

export function WhySection({ summary, bridge }: { summary: MrrSummary; bridge: PeriodBridge }) {
  const driver = (code: string) => bridge.drivers.find((entry) => entry.driver.code === code);
  const behaviour = driver("behaviour");
  const pricing = driver("pricing");
  const discount = driver("discount");
  const timing = driver("timing");
  const discountAvailable = Boolean(discount?.driver.available);
  const pricingAndDiscounts =
    pricing?.value && discountAvailable ? (discount?.value ? pricing.value.add(discount.value) : null) : (pricing?.value ?? null);
  const pct =
    bridge.change && bridge.opening && !bridge.opening.isZero() ? bridge.change.div(bridge.opening).mul(Ratio.of(100n)) : null;

  const cards = [
    {
      key: "behaviour",
      title: behaviour?.driver.label ?? "Customer behaviour",
      value: behaviour?.value ?? null,
      note: "What customers did: new, expansion, contraction, churn",
    },
    {
      key: "pricing",
      title: discountAvailable ? "Pricing & discounts" : `${pricing?.driver.label ?? "Pricing"}${pricing?.driver.inferred ? " (inferred)" : ""}`,
      value: pricingAndDiscounts,
      note: discountAvailable ? "Price-book changes and discounts" : "Discounts not available until billing data",
    },
    {
      key: "timing",
      title: timing?.driver.label ?? "Timing of payments",
      value: timing?.value ?? null,
      note: "Prepaid first invoices (inferred)",
    },
  ];

  return (
    <section aria-labelledby="why-title" className="flex flex-col gap-5" data-testid="why">
      <div className="flex flex-col gap-1.5">
        <h2 id="why-title" className="text-xl font-semibold">
          Why MRR changed
        </h2>
        <p className="text-base" data-testid="mrr-hero" data-kpi-id="mrr.why.hero">
          {bridge.opening && bridge.closing ? (
            <>
              MRR went from <span className="num font-mono">{formatCompact(bridge.opening.toNumber())}</span> to{" "}
              <span className="num font-mono">{formatCompact(bridge.closing.toNumber())}</span>:{" "}
              <span className="num font-mono font-semibold">{formatSignedCompact(bridge.change)}</span>
              {pct ? <span className="num font-mono text-ink-2"> ({pct.sign() > 0 ? "+" : ""}{formatExact(pct, 1)}%)</span> : null}, {rangeLabel(bridge.months.map((month) => month.month))}.
            </>
          ) : (
            "MRR isn't available for every month of this period."
          )}
        </p>
        {bridge.provisionalMonths.length > 0 ? (
          <p className="flex items-center gap-2 text-[0.9375rem] text-ink-2" data-testid="provisional">
            <StatusDot status="warn" size={9} />
            <span>
              <span className="font-medium text-ink">Provisional:</span> churn for {rangeLabel(bridge.provisionalMonths)} isn&apos;t confirmed yet.
            </span>
          </p>
        ) : null}
      </div>

      <ul className="grid gap-4 md:grid-cols-3" aria-label="Change by driver" data-testid="driver-cards">
        {cards.map((card) => (
          <li key={card.key} className="card flex flex-col gap-2 p-6" data-testid={`driver-${card.key}`} data-kpi-id={`mrr.why.driver.${card.key}`}>
            <h3 className="flex items-center gap-2 text-base font-medium text-ink-2">
              <Swatch driver={card.key} />
              {card.title}
            </h3>
            <p className="num font-mono text-4xl leading-none font-semibold tracking-tight" data-testid="driver-value">
              {formatSignedCompact(card.value)}
            </p>
            <p className="text-[0.9375rem] text-ink-2">{card.note}</p>
          </li>
        ))}
      </ul>

      <Disclosure title="How the drivers are separated" testId="why-details">
        <dl className="divide-y divide-line">
          <DetailItem term="In one sentence">
            Behaviour moves list MRR at a constant price, pricing moves the price book, commercial decisions move discounts, and timing moves
            only cash.
          </DetailItem>
          {summary.run.mrr_basis === "cash_proxy" ? (
            <DetailItem term="Basis">
              Based on payments (proxy until billing data). MRR is what customers paid, with catch-ups, prepayments and split payments spread
              over the months they cover. Without list prices and discounts, a discount would show up here as contraction, and pricing is
              inferred from price steps that many customers share in the same month.
            </DetailItem>
          ) : null}
          <DetailItem term="The three cards">
            They add up to the change in MRR. Timing here is first invoices paid for 2 or 3 months at once. The rest of payment timing
            (catch-ups, prepayments, split payments) moves only cash
            {bridge.timingChange ? (
              <>
                {" "}
                (<span className="num font-mono">{formatSignedCompact(bridge.timingChange)}</span> in this period)
              </>
            ) : null}
            , so MRR spreads it over the months it covers.
          </DetailItem>
          <DetailItem term="The CFO's cases">
            <div className="overflow-x-auto" tabIndex={0} role="region" aria-label="The CFO's cases, scrolls sideways on small screens">
              <table className="w-full min-w-[36rem] border-separate border-spacing-0 text-[0.9375rem]" data-testid="cfo-cases">
                <caption className="sr-only">How each of the CFO&apos;s cases is booked</caption>
                <thead>
                  <tr className="text-left text-ink-2">
                    <th scope="col" className="border-b border-line py-2 pr-3 font-medium">Case</th>
                    <th scope="col" className="border-b border-line py-2 pr-3 font-medium">MRR</th>
                    <th scope="col" className="border-b border-line py-2 pr-3 font-medium">Booked as</th>
                    <th scope="col" className="border-b border-line py-2 font-medium">Answer</th>
                  </tr>
                </thead>
                <tbody>
                  {CASES.map(([event, net, booked, answer], index) => (
                    <tr key={event} className={index % 2 === 0 ? "zebra-a" : "zebra-b"}>
                      <th scope="row" className="py-2 pr-3 pl-1 text-left font-normal">{event}</th>
                      <td className="num py-2 pr-3 font-mono whitespace-nowrap">{net}</td>
                      <td className="py-2 pr-3">{booked}</td>
                      <td className="py-2 pr-1">{answer}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </DetailItem>
          <DetailItem term="A worked month">
            <p className="mb-2 text-ink-2">Seven customers, illustrative units: one removes seats, one gets a promo, one grows with a discount, one discount ends, one price rise, one churn, one new customer.</p>
            <dl className="grid max-w-md grid-cols-[1fr_auto] gap-x-6 gap-y-1">
              {WORKED.map(([term, value]) => (
                <div key={term} className="contents">
                  <dt className="text-ink-2">{term}</dt>
                  <dd className="num text-right font-mono">{value}</dd>
                </div>
              ))}
            </dl>
            <p className="mt-2">MRR rose 26: customers added 80 and pricing 20, while discounts took 74.</p>
          </DetailItem>
          <DetailItem term="Money">Full units. Currency not stated in the data.</DetailItem>
          <DetailItem term="Data">
            As of {formatMonth(summary.run.as_of_month)}. Churn is confirmed through {formatMonth(summary.run.churn_confirmed_through)}.
          </DetailItem>
        </dl>
      </Disclosure>
    </section>
  );
}
