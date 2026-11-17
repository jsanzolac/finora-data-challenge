"use client";

import { useState } from "react";
import clsx from "clsx";
import { ArrowDown, ArrowUp, RotateCcw } from "lucide-react";
import { formatCompact, formatExact, groupDigits } from "@/lib/acq/format";
import {
  AT_REST,
  baselineOf,
  industryRows,
  noMeasurableLink,
  pctChange,
  periodRows,
  plan,
  rankLevers,
  ticketReference,
  ticketStep,
  valueChange,
  type Evidence,
  type LeverInputs,
} from "@/lib/acq/planner";
import { Ratio } from "@/lib/acq/ratio";
import { aboutChance, findSummary } from "@/lib/acq/signals";
import type { AcqSummary, WonDefinition } from "@/lib/acq/types";
import { DetailItem, Disclosure } from "@/components/ui/Disclosure";
import { PlainSelect } from "@/components/ui/PlainSelect";
import { StatusDot } from "@/components/ui/StatusDot";

const EVIDENCE: Record<Evidence, { word: string; tone: string; hint: string }> = {
  observed: { word: "Observed", tone: "pass", hint: "Seen in the data" },
  assumption: { word: "Assumption", tone: "warn", hint: "No stage before Won is observed: the rates are assumed" },
  untested: { word: "Untested", tone: "na", hint: "Not measurable in these files: test it" },
};

export function EvidenceLabel({ evidence }: { evidence: Evidence }) {
  const meta = EVIDENCE[evidence];
  return (
    <span className="inline-flex items-center gap-1.5 text-sm font-medium whitespace-nowrap text-ink-2" title={meta.hint} data-evidence={evidence}>
      <StatusDot status={meta.tone} size={8} />
      {meta.word}
    </span>
  );
}

const FULL_MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];

/** 202306 -> "June 2023". */
function longMonth(key: number | null | undefined): string {
  if (!key) return "";
  return `${FULL_MONTHS[(key % 100) - 1]} ${Math.floor(key / 100)}`;
}

/** 202202 -> "Feb 2022". */
export function shortMonth(key: number | null | undefined): string {
  if (!key) return "";
  return `${FULL_MONTHS[(key % 100) - 1]!.slice(0, 3)} ${Math.floor(key / 100)}`;
}

function whole(value: Ratio | null): string {
  return value ? groupDigits(value.toFixed(0)) : "—";
}

function pctWord(value: Ratio | null): string {
  return value ? `${formatExact(value.sign() < 0 ? value.neg() : value, 0)}%` : "—";
}

function millions(value: Ratio | null): string {
  if (!value) return "—";
  const number = value.toNumber();
  return Math.abs(number) >= 1e6 ? `${(number / 1e6).toFixed(2)}M` : formatCompact(number);
}

function signedMillions(value: Ratio | null): string {
  if (!value) return "—";
  if (value.isZero()) return "0";
  return `${value.sign() > 0 ? "+" : "−"}${millions(value.sign() < 0 ? value.neg() : value)}`;
}

function Change({ now, then, goodWhenUp }: { now: Ratio | null; then: Ratio | null; goodWhenUp: boolean }) {
  const change = pctChange(then, now);
  if (!change || change.toFixed(1) === "0.0" || change.toFixed(1) === "-0.0") return <span className="text-ink-2">Today&apos;s level</span>;
  const up = change.sign() > 0;
  const good = up === goodWhenUp;
  const Icon = up ? ArrowUp : ArrowDown;
  return (
    <span className={clsx("inline-flex items-center gap-1 font-semibold", good ? "text-pass-ink" : "text-fail-ink")}>
      <Icon aria-hidden="true" size={15} />
      <span className="num font-mono">
        {up ? "+" : "−"}
        {formatExact(change.sign() < 0 ? change.neg() : change, 1)}%
      </span>
      <span className="sr-only">{good ? ", better" : ", worse"}</span>
    </span>
  );
}

const LEVER_NAME = { ticket: "Ticket size", conversion: "Conversion rates", mix: "Industry mix", spend: "Spend a month" } as const;

/** §16.6: the decision-oriented headline, templated from `levers` and `signal_summary`. */
function Headline({ summary, definition }: { summary: AcqSummary; definition: WonDefinition }) {
  const levers = summary.levers;
  const change = valueChange(levers, definition);
  const rows = periodRows(levers, definition);
  const from = rows.find((row) => row.period_code === change?.from);
  const to = rows.find((row) => row.period_code === change?.to);
  const before = baselineOf(from);
  const after = baselineOf(to);
  if (!change || !from || !to || !before || !after) return null;
  const spend = pctChange(Ratio.tryParse(from.spend_per_month_value), Ratio.tryParse(to.spend_per_month_value));
  const won = pctChange(before.wonPerMonth, after.wonPerMonth);
  const mrr = pctChange(before.newMrr, after.newMrr);
  const ticket = pctChange(before.runRate, after.runRate);
  const link = noMeasurableLink(summary.signal_summary);
  const label = (code: string) => summary.industries.find((industry) => industry.code === code)?.label ?? code;
  const held = change.rows
    .filter((row) => {
      const c = pctChange(Ratio.tryParse(row.value_from), Ratio.tryParse(row.value_to));
      return c !== null && c.compare(Ratio.of(-5n)) > 0;
    })
    .map((row) => label(row.industry_code));
  const share = (value: string | null) => Ratio.tryParse(value);
  const keepPaying =
    [
      [share(from.paying_m6_share), share(to.paying_m6_share)],
      [share(from.paying_m12_share), share(to.paying_m12_share)],
    ].every(([a, b]) => a && b && b.compare(a.sub(Ratio.parse("0.01"))) >= 0);

  const step = ticketStep(levers, definition);
  const halfLabel = (half: string) => `${half.endsWith("H1") ? "Jan–Jun" : "Jul–Dec"} ${half.slice(0, 4)}`;

  return (
    <div className="flex max-w-4xl flex-col gap-2" data-kpi-id="acq.verdict">
      <p className="text-lg leading-relaxed" data-testid="verdict">
        Spend per month {spend && spend.sign() < 0 ? "fell" : "rose"} {pctWord(spend)} from {longMonth(to.first_month_key)} while new customers per month{" "}
        {won && won.sign() >= 0 ? "rose" : "fell"} {pctWord(won)}
        {link === false ? (
          ". Some de-trended tests show a link between spend and new customers; review them with the data team before using it."
        ) : (
          <>: these files show no measurable link from spend to new customers.</>
        )}{" "}
        New MRR per month {mrr && mrr.sign() >= 0 ? (won && mrr.compare(won) < 0 ? "rose only" : "rose") : "fell"} {pctWord(mrr)}
        {ticket && ticket.sign() < 0 ? (
          <>
            , because each new customer starts {pctWord(ticket)} smaller ({whole(before.runRate)} → {whole(after.runRate)} a month)
            {held.length > 0 ? `, in every industry except ${held.join(" and ")}` : ", in every industry"}
          </>
        ) : null}
        {keepPaying ? ", and new customers keep paying as long as before." : ", and fewer new customers keep paying."}{" "}
        <strong className="font-semibold">
          Plan with ticket size and industry mix (observed); treat conversion rates as assumptions; test spend before relying on it.
        </strong>
      </p>
      {step ? (
        <p className="text-[0.9375rem] text-ink-2" data-testid="verdict-timing">
          Starting revenue per new customer was already lower in the {halfLabel(step.after.cohort_half)} cohort (
          {whole(Ratio.tryParse(step.after.run_rate_mrr_per_won_value))} against {whole(Ratio.tryParse(step.before.run_rate_mrr_per_won_value))} in{" "}
          {halfLabel(step.before.cohort_half)}), mostly before the spend change, so its timing does not tie it to spend.
        </p>
      ) : null}
    </div>
  );
}

export function LeversSection({ summary, definition, volume }: { summary: AcqSummary; definition: WonDefinition; volume: Ratio }) {
  const levers = summary.levers;
  const rows = periodRows(levers, definition);
  const latest = [...rows].sort((a, b) => b.last_month_key - a.last_month_key)[0];
  const [periodCode, setPeriodCode] = useState<string | null>(null);
  const [ticket, setTicket] = useState(0);
  const [spend, setSpend] = useState(0);
  const [points, setPoints] = useState(0);
  const [fromCode, setFromCode] = useState<string | null>(null);
  const [toCode, setToCode] = useState<string | null>(null);

  const period = rows.find((row) => row.period_code === periodCode) ?? latest;
  const base = baselineOf(period);
  if (!levers || !period || !base) {
    return (
      <section aria-labelledby="levers-title" className="flex flex-col gap-3" data-testid="levers">
        <h2 id="levers-title" className="text-xl font-semibold">
          What to move
        </h2>
        <p className="card p-6 text-ink-2">The lever planner isn&apos;t available for this run.</p>
      </section>
    );
  }

  const industries = industryRows(levers, definition, period.period_code);
  const lowest = industries[industries.length - 1];
  const highest = industries[0];
  const from = industries.find((row) => row.industry_code === fromCode) ?? lowest;
  const to = industries.find((row) => row.industry_code === toCode) ?? highest;
  const maxPoints = from ? Math.floor(Number(from.won_share) * 100) : 0;
  const movedPoints = Math.min(points, maxPoints);
  const mix = from && to && movedPoints > 0 ? { points: Ratio.of(BigInt(movedPoints)), fromRunRate: from.runRate, toRunRate: to.runRate } : null;
  const inputs: LeverInputs = { volume, ticketPct: Ratio.of(BigInt(ticket)), mix, spendPct: Ratio.of(BigInt(spend)) };
  const result = plan(base, inputs);
  const alone = (patch: Partial<LeverInputs>) => plan(base, { ...AT_REST, ...patch });
  const reference = period.period_code === valueChange(levers, definition)?.to ? ticketReference(levers, definition) : null;
  const label = (code: string) => summary.industries.find((industry) => industry.code === code)?.label ?? code;
  const ranking = rankLevers(base, lowest?.runRate ?? null, highest?.runRate ?? null);
  const maxDelta = Math.max(...ranking.map((entry) => entry.delta?.toNumber() ?? 0), 1);
  const leversMoved = ticket !== 0 || spend !== 0 || movedPoints !== 0;
  const signals = findSummary(summary.signal_summary, "diff", "user", "company");
  const spendSlider = alone({ spendPct: Ratio.of(BigInt(spend)) });

  const outputs = [
    { key: "won", title: "New customers a month", value: formatExact(result.wonPerMonth, 1), now: base.wonPerMonth, next: result.wonPerMonth, good: true },
    { key: "mrr", title: "New MRR a month", value: millions(result.newMrr), now: base.newMrr, next: result.newMrr, good: true },
    { key: "payback", title: "Payback", value: result.payback ? `${formatExact(result.payback, 1)} mo` : "—", now: base.payback, next: result.payback, good: false },
  ];
  const row = "grid grid-cols-1 items-center gap-x-6 gap-y-2 border-t border-line py-4 md:grid-cols-[12rem_minmax(0,1fr)_11rem]";

  return (
    <section aria-labelledby="levers-title" className="flex flex-col gap-5" data-testid="levers">
      <div className="flex flex-col gap-2">
        <h2 id="levers-title" className="text-xl font-semibold">
          What to move
        </h2>
        <Headline summary={summary} definition={definition} />
      </div>

      <div className="card p-4 md:p-6" data-testid="planner">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div role="group" aria-label="Planner baseline" className="flex flex-wrap items-center gap-2 text-[0.9375rem]">
            <span className="text-ink-2">Start from</span>
            <span className="inline-flex rounded-lg border border-line-strong p-0.5">
              {[...rows]
                .sort((a, b) => b.last_month_key - a.last_month_key)
                .map((entry) => (
                  <button
                    key={entry.period_code}
                    type="button"
                    aria-pressed={entry.period_code === period.period_code}
                    onClick={() => setPeriodCode(entry.period_code)}
                    className={clsx(
                      "min-h-9 rounded-md px-3 text-[0.9375rem] font-medium",
                      entry.period_code === period.period_code ? "bg-ink text-bg" : "text-ink-2 hover:bg-surface-3 hover:text-ink",
                    )}
                    data-testid={`baseline-${entry.period_code}`}
                  >
                    {shortMonth(entry.first_month_key)} – {shortMonth(entry.last_month_key)}
                  </button>
                ))}
            </span>
          </div>
          {leversMoved ? (
            <button
              type="button"
              className="btn-secondary"
              onClick={() => {
                setTicket(0);
                setSpend(0);
                setPoints(0);
              }}
              data-testid="reset-levers"
            >
              <RotateCcw aria-hidden="true" size={16} />
              Reset levers
            </button>
          ) : null}
        </div>

        <ul className="mt-4 grid gap-3 md:grid-cols-3" aria-label="Planned outcome" aria-live="polite" data-testid="planner-outputs">
          {outputs.map((output) => (
            <li
              key={output.key}
              className="rounded-lg border border-line bg-bg p-4"
              data-testid={`planned-${output.key}`}
              data-kpi-id={{ won: "acq.plan.won", mrr: "acq.plan.new_mrr", payback: "acq.plan.payback" }[output.key]}
            >
              <p className="text-sm text-ink-2">{output.title}</p>
              <p className="num mt-1 font-mono text-3xl leading-none font-semibold" data-testid="planned-value">
                {output.value}
              </p>
              <p className="mt-2 flex flex-wrap items-center justify-between gap-2 text-sm">
                <Change now={output.next} then={output.now} goodWhenUp={output.good} />
                {result.evidence && !output.next?.equals(output.now ?? Ratio.ZERO) ? <EvidenceLabel evidence={result.evidence} /> : null}
              </p>
            </li>
          ))}
        </ul>

        <div className="mt-5">
          <div className={row} data-testid="lever-ticket" data-kpi-id="acq.lever.ticket">
            <div className="flex flex-col gap-1">
              <label htmlFor="lever-ticket-input" className="font-medium">
                Ticket size
              </label>
              <EvidenceLabel evidence="observed" />
            </div>
            <div className="flex flex-col gap-1.5">
              <div className="flex items-center gap-3">
                <input
                  id="lever-ticket-input"
                  type="range"
                  min={-20}
                  max={50}
                  step={1}
                  value={ticket}
                  onChange={(event) => setTicket(Number(event.target.value))}
                  aria-valuetext={`${ticket > 0 ? "+" : ""}${ticket}% starting revenue per new customer`}
                  className="w-full accent-[var(--viz-1)]"
                  data-testid="ticket-slider"
                />
                <span className="num w-14 text-right font-mono" data-testid="ticket-value">
                  {ticket > 0 ? "+" : ""}
                  {ticket}%
                </span>
              </div>
              <p className="text-sm text-ink-2">
                New customers start at <span className="num font-mono">{whole(base.runRate)}</span> a month.
                {reference && reference.pct.sign() > 0 ? (
                  <>
                    {" "}
                    <button
                      type="button"
                      className="text-ink underline decoration-line-strong underline-offset-4 hover:decoration-ink"
                      onClick={() => setTicket(Math.min(50, Number(reference.pct.toFixed(0))))}
                      data-testid="ticket-reference"
                    >
                      Reference: +{formatExact(reference.pct, 1)}%
                    </button>{" "}
                    would bring each industry back to its earlier level at today&apos;s mix.
                  </>
                ) : null}
              </p>
            </div>
            <p className="text-[0.9375rem] md:text-right">
              <span className="num font-mono font-semibold">{signedMillions(alone({ ticketPct: Ratio.of(BigInt(ticket)) }).newMrrDelta)}</span>{" "}
              <span className="text-ink-2">new MRR a month</span>
            </p>
          </div>

          <div className={row} data-testid="lever-mix" data-kpi-id="acq.lever.mix">
            <div className="flex flex-col gap-1">
              <label htmlFor="lever-mix-input" className="font-medium">
                Industry mix
              </label>
              <EvidenceLabel evidence="observed" />
            </div>
            <div className="flex flex-col gap-1.5">
              <div className="flex flex-wrap items-center gap-2 text-[0.9375rem]">
                <span>Move</span>
                <input
                  id="lever-mix-input"
                  type="number"
                  min={0}
                  max={maxPoints}
                  step={1}
                  value={movedPoints}
                  onChange={(event) => setPoints(Math.max(0, Math.min(maxPoints, Math.floor(Number(event.target.value) || 0))))}
                  className="field num w-20 font-mono"
                  data-testid="mix-points"
                />
                <span>points of new customers from</span>
                <PlainSelect
                  label="From industry"
                  value={from?.industry_code ?? ""}
                  onValueChange={setFromCode}
                  groups={[{ items: industries.map((entry) => ({ value: entry.industry_code, text: label(entry.industry_code), note: whole(entry.runRate) })) }]}
                  testId="mix-from"
                  className="w-52"
                  hideLabel
                />
                <span>to</span>
                <PlainSelect
                  label="To industry"
                  value={to?.industry_code ?? ""}
                  onValueChange={setToCode}
                  groups={[{ items: industries.map((entry) => ({ value: entry.industry_code, text: label(entry.industry_code), note: whole(entry.runRate) })) }]}
                  testId="mix-to"
                  className="w-52"
                  hideLabel
                />
              </div>
              <p className="text-sm text-ink-2" data-testid="mix-reading">
                {from && to && movedPoints > 0
                  ? `Moving ${movedPoints} points from ${label(from.industry_code)} to ${label(to.industry_code)} adds ${whole(to.runRate.sub(from.runRate).mul(Ratio.of(BigInt(movedPoints), 100n)))} a month per new customer, if each industry's ticket holds and the volume can be won at today's cost.`
                  : "At each industry's observed ticket, if it holds and the volume can be won at today's cost."}
              </p>
            </div>
            <p className="text-[0.9375rem] md:text-right">
              <span className="num font-mono font-semibold">{signedMillions(alone({ mix }).newMrrDelta)}</span>{" "}
              <span className="text-ink-2">new MRR a month</span>
            </p>
          </div>

          <div className={row} data-testid="lever-conversion" data-kpi-id="acq.lever.conversion">
            <div className="flex flex-col gap-1">
              <span className="font-medium">Conversion rates</span>
              <EvidenceLabel evidence="assumption" />
            </div>
            <p className="text-[0.9375rem] text-ink-2">
              {volume.equals(Ratio.ONE) ? "The funnel shows the Base rates." : <>The funnel&apos;s rates give ×{formatExact(volume, 3)} new customers.</>} No stage
              before Won is observed.{" "}
              <a href="#funnel-title" className="text-ink underline decoration-line-strong underline-offset-4 hover:decoration-ink">
                Change the rates in the funnel
              </a>
            </p>
            <p className="text-[0.9375rem] md:text-right" data-testid="conversion-impact">
              <span className="num font-mono font-semibold">{signedMillions(alone({ volume }).newMrrDelta)}</span>{" "}
              <span className="text-ink-2">new MRR a month</span>
            </p>
          </div>

          <div className={row} data-testid="lever-spend" data-kpi-id="acq.lever.spend">
            <div className="flex flex-col gap-1">
              <label htmlFor="lever-spend-input" className="font-medium">
                Spend a month
              </label>
              <EvidenceLabel evidence="untested" />
            </div>
            <div className="flex flex-col gap-1.5">
              <div className="flex items-center gap-3">
                <input
                  id="lever-spend-input"
                  type="range"
                  min={-50}
                  max={50}
                  step={5}
                  value={spend}
                  onChange={(event) => setSpend(Number(event.target.value))}
                  aria-valuetext={`${spend > 0 ? "+" : ""}${spend}% S&M spend a month`}
                  className="w-full accent-[var(--ink-3)]"
                  data-testid="spend-slider"
                />
                <span className="num w-14 text-right font-mono">
                  {spend > 0 ? "+" : ""}
                  {spend}%
                </span>
              </div>
              <p className="text-sm text-ink-2">
                Changes what each new customer costs and the payback. Whether spend changes the number of new customers isn&apos;t measurable in these files:
                test it before relying on it.
              </p>
            </div>
            <p className="text-[0.9375rem] md:text-right">
              <span className="text-ink-2">Payback</span>{" "}
              <span className="num font-mono font-semibold">{spendSlider.payback ? `${formatExact(spendSlider.payback, 1)} mo` : "—"}</span>
            </p>
          </div>
        </div>
      </div>

      <div className="card p-4 md:p-6" data-testid="lever-ranking" data-kpi-id="acq.lever.ranking">
        <h3 className="mb-3 text-base font-medium">Biggest levers for a 10% move</h3>
        <ol className="flex flex-col">
          {ranking.map((entry, index) => {
            const what =
              entry.lever === "ticket"
                ? "+10% starting revenue per new customer"
                : entry.lever === "conversion"
                  ? "+10% new customers from better conversion"
                  : entry.lever === "mix"
                    ? `10 points of new customers from ${lowest ? label(lowest.industry_code) : "the lowest"} to ${highest ? label(highest.industry_code) : "the highest"}`
                    : "+10% spend a month";
            return (
              <li
                key={entry.lever}
                className={clsx(
                  "grid grid-cols-[1.5rem_minmax(0,1fr)_auto] items-center gap-x-3 gap-y-1 rounded-md px-2 py-2.5 md:grid-cols-[1.5rem_17rem_minmax(0,1fr)_7rem_7.5rem]",
                  index % 2 === 0 ? "zebra-a" : "zebra-b",
                )}
                data-testid="ranked-lever"
                data-lever={entry.lever}
              >
                <span className="num font-mono text-ink-2">{index + 1}</span>
                <span className="flex flex-col">
                  <span className="font-medium">{LEVER_NAME[entry.lever]}</span>
                  <span className="text-sm text-ink-2">{what}</span>
                </span>
                <span aria-hidden="true" className="col-span-3 col-start-2 row-start-2 h-2 md:col-span-1 md:col-start-auto md:row-start-auto">
                  {entry.delta ? (
                    <span className="block h-full rounded-full" style={{ width: `${(entry.delta.toNumber() / maxDelta) * 100}%`, background: "var(--viz-1)" }} />
                  ) : null}
                </span>
                <span className="num text-right font-mono font-semibold">
                  {entry.delta ? signedMillions(entry.delta) : <span className="font-sans text-sm font-normal text-ink-2">Not measurable</span>}
                </span>
                <span className="col-start-2 md:col-start-auto md:text-right">
                  <EvidenceLabel evidence={entry.evidence} />
                </span>
              </li>
            );
          })}
        </ol>
        <p className="mt-3 text-[0.9375rem] text-ink-2">New MRR a month. Ticket size and conversion give the same arithmetic; ticket size has been observed at higher levels.</p>
      </div>

      <Disclosure title="How the planner works" testId="levers-details">
        <dl className="divide-y divide-line">
          <DetailItem term="Starting revenue per new customer">
            The average a new customer pays in months 2 to 4 after the first payment (catch-ups spread over the months they settle). Only cohorts with
            all three months in the data count: today through {shortMonth(period.run_rate_last_cohort_month_key)}. New MRR a month = new customers a month ×
            this, an upper bound, because it also applies it to the {period.run_rate_no_paid_customers} early leavers.
          </DetailItem>
          <DetailItem term="Payback">
            Simple cash-revenue payback: months of starting revenue needed to cover S&amp;M spend per new customer. Revenue, not margin; undiscounted; assumes no
            churn; currency not stated.
          </DetailItem>
          <DetailItem term="Each lever">
            Ticket size scales the starting revenue. Industry mix moves share between two industries at their observed tickets. Conversion rates change new
            customers by the funnel&apos;s overall rate against Base. Spend changes cost per new customer only; new customers stay flat. An outcome carries the
            weakest label among the levers moved.
          </DetailItem>
          <DetailItem term="Baselines">
            {rows.map((entry) => `${shortMonth(entry.first_month_key)} – ${shortMonth(entry.last_month_key)}`).join(" and ")} are the two spend periods,
            inferred from the spend data. They are only starting points: they don&apos;t say what changed the ticket or the number of new customers.
          </DetailItem>
          <DetailItem term="Testing spend">
            <span data-testid="spend-guidance">
              Month to month, spend and new customers don&apos;t move together
              {signals ? ` (${signals.signals} of ${signals.tests_with_r} tests, ${aboutChance(signals.expected_by_chance)} by chance)` : ""}. A company-wide test
              would only detect a change of about a third in new customers. Instead, hold out paid media in some regions, audiences or channels for 8–12 weeks,
              register the metrics first, and compare new customers per cell. That needs lead source and campaign per customer first.
            </span>
          </DetailItem>
          <DetailItem term="Definitions">CDO §16 ({levers.definitions_version}).</DetailItem>
        </dl>
      </Disclosure>
    </section>
  );
}
