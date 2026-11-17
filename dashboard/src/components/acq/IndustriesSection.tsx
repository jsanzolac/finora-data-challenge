"use client";

import { formatInt, formatMonth } from "@/lib/format";
import { formatMoneyString } from "@/lib/acq/format";
import { Ratio } from "@/lib/acq/ratio";
import type { AcqSummary, IndustryProfileRow } from "@/lib/acq/types";
import { DetailItem, Disclosure } from "@/components/ui/Disclosure";

function months(value: string | null): string {
  const parsed = Ratio.tryParse(value);
  return parsed ? parsed.toFixed(1) : "—";
}

/** One row per industry (customer scope `all`), most customers first. */
export function IndustriesSection({ summary }: { summary: AcqSummary }) {
  const rows = summary.industries
    .map((industry) => ({
      industry,
      all: summary.industry_profile.find((row) => row.industry_code === industry.code && row.customer_scope === "all"),
      won: summary.industry_profile.find((row) => row.industry_code === industry.code && row.customer_scope === "won"),
      earlier: summary.industry_profile.find((row) => row.industry_code === industry.code && row.customer_scope === "left_censored"),
    }))
    .filter((row): row is typeof row & { all: IndustryProfileRow } => Boolean(row.all))
    .sort((a, b) => b.all.customers - a.all.customers);

  const outlierRows = rows.filter(
    (row) => row.all.avg_monthly_payment_excl_outliers_value !== null && row.all.avg_monthly_payment_excl_outliers_value !== row.all.avg_monthly_payment_value,
  );
  const newPayLess = rows.filter((row) => {
    const a = Ratio.tryParse(row.won?.avg_monthly_payment_value ?? null);
    const b = Ratio.tryParse(row.earlier?.avg_monthly_payment_value ?? null);
    return a && b && a.compare(b) < 0;
  }).length;

  const sharePct = (value: string | null | undefined) => {
    const parsed = Ratio.tryParse(value ?? null);
    return parsed ? `${parsed.mul(Ratio.of(100n)).toFixed(1)}%` : null;
  };
  const shareRows = rows
    .map((row) => ({
      code: row.industry.code,
      label: row.industry.label,
      won: sharePct(row.won?.share_of_observable_months_paid),
      earlier: sharePct(row.earlier?.share_of_observable_months_paid),
    }))
    .filter((row): row is { code: string; label: string; won: string; earlier: string } => Boolean(row.won && row.earlier));

  const header = "border-b border-line-strong bg-surface px-4 py-3 font-medium text-ink-2";

  return (
    <section aria-labelledby="industries-title" className="flex flex-col gap-5" data-testid="industries" data-kpi-id="acq.industries">
      <div className="flex flex-col gap-1">
        <h2 id="industries-title" className="text-xl font-semibold">
          Industries
        </h2>
        <p className="text-[0.9375rem] text-ink-2">Every paying customer, up to {formatMonth(summary.run.as_of_month)}.</p>
      </div>

      <div className="card hidden overflow-clip md:block">
        <table className="w-full border-separate border-spacing-0 text-[0.9375rem]" data-testid="industries-table">
          <caption className="sr-only">Customers, new customers, average monthly payment and average months paying, by industry</caption>
          <thead>
            <tr>
              <th scope="col" className={`${header} text-left`}>
                Industry
              </th>
              <th scope="col" className={`${header} text-right`}>
                Customers
              </th>
              <th scope="col" className={`${header} text-right`}>
                New customers
              </th>
              <th scope="col" className={`${header} text-right`}>
                Average monthly payment
              </th>
              <th scope="col" className={`${header} text-right`}>
                Average months paying
              </th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row, index) => (
              <tr key={row.industry.code} className={index % 2 === 0 ? "zebra-a" : "zebra-b"} data-industry={row.industry.code}>
                <th scope="row" className="px-4 py-3 text-left font-normal">
                  {row.industry.label}
                </th>
                <td className="num px-4 py-3 text-right font-mono">{formatInt(row.all.customers)}</td>
                <td className="num px-4 py-3 text-right font-mono">{formatInt(row.all.won)}</td>
                <td className="num px-4 py-3 text-right font-mono">{formatMoneyString(row.all.avg_monthly_payment_value)}</td>
                <td className="num px-4 py-3 text-right font-mono">{months(row.all.avg_months_paying)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Narrow screens: one block per industry, the four figures in two columns. */}
      <ul className="card overflow-clip md:hidden" aria-label="Industries" data-testid="industries-list">
        {rows.map((row, index) => (
          <li key={row.industry.code} className={`${index % 2 === 0 ? "zebra-a" : "zebra-b"} px-4 py-3`}>
            <p className="mb-1.5 text-base font-medium">{row.industry.label}</p>
            <dl className="grid grid-cols-2 gap-x-4 gap-y-1 text-[0.9375rem]">
              {[
                ["Customers", formatInt(row.all.customers)],
                ["New customers", formatInt(row.all.won)],
                ["Average monthly payment", formatMoneyString(row.all.avg_monthly_payment_value)],
                ["Average months paying", months(row.all.avg_months_paying)],
              ].map(([term, value]) => (
                <div key={term} className="flex flex-col">
                  <dt className="text-sm text-ink-2">{term}</dt>
                  <dd className="num font-mono">{value}</dd>
                </div>
              ))}
            </dl>
          </li>
        ))}
      </ul>

      <Disclosure testId="industries-details">
        <dl className="divide-y divide-line">
          <DetailItem term="Without outlier customers">
            {outlierRows.length === 0 ? (
              "No industry has outlier customers."
            ) : (
              <ul className="flex flex-col gap-1" data-testid="ex-outlier">
                {outlierRows.map((row) => (
                  <li key={row.industry.code}>
                    {row.industry.label}: <span className="num font-mono">{formatMoneyString(row.all.avg_monthly_payment_excl_outliers_value)}</span> a
                    month (with them, <span className="num font-mono">{formatMoneyString(row.all.avg_monthly_payment_value)}</span>).
                  </li>
                ))}
                <li className="text-ink-2">Every other industry is unchanged.</li>
              </ul>
            )}
          </DetailItem>
          <DetailItem term="Average months paying">
            Counted up to {formatMonth(summary.run.as_of_month)}. Many customers are still paying, so this is a lower bound on how long they
            stay.
          </DetailItem>
          {newPayLess > 0 ? (
            <DetailItem term="New against earlier customers">
              <p>
                In {newPayLess} of {rows.length} industries, new customers pay less a month than customers who were already paying when the
                data starts. That does not show that quality fell: the earlier group has survived longer and had more time to grow.
              </p>
              {shareRows.length > 0 ? (
                <>
                  <p className="mt-2">Share of their months in which customers paid, which compares groups of different ages fairly:</p>
                  <ul className="mt-1 flex flex-col gap-0.5" data-testid="share-paid">
                    {shareRows.map((row) => (
                      <li key={row.code}>
                        {row.label}: new <span className="num font-mono">{row.won}</span>, earlier{" "}
                        <span className="num font-mono">{row.earlier}</span>
                      </li>
                    ))}
                  </ul>
                </>
              ) : null}
            </DetailItem>
          ) : null}
          <DetailItem term="Money">Average of every paid customer-month, catch-up payments included. Full units.</DetailItem>
        </dl>
      </Disclosure>
    </section>
  );
}
