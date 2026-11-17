/** The lever planner against docs/gold_acquisition_model.md §16.3 and §16.5 (contract v1.3). */
import { describe, expect, it } from "vitest";
import fixture from "@mocks/acq/summary.json";
import {
  AT_REST,
  baselineFor,
  industryRows,
  noMeasurableLink,
  pctChange,
  plan,
  rankLevers,
  ticketReference,
  valueChange,
  weakest,
  type Plan,
} from "./planner";
import { Ratio } from "./ratio";
import type { AcqSummary } from "./types";

const summary = fixture as unknown as AcqSummary;
const levers = summary.levers!;
const base = baselineFor(levers, "user", "from_2023_06")!;
const pre = baselineFor(levers, "user", "pre_2023_06")!;
const r = (text: string) => Ratio.parse(text);

function row(result: Plan): string[] {
  return [
    result.wonPerMonth.toFixed(6),
    result.runRate.toFixed(2),
    result.newMrr.toFixed(2),
    result.costPerWon!.toFixed(2),
    result.payback!.toFixed(1),
  ];
}

describe("§16.5 planner fixtures (baseline from_2023_06, user's Won)", () => {
  it("None", () => {
    expect(row(plan(base, AT_REST))).toEqual(["57.529412", "42550.70", "2447916.75", "3047955.01", "71.6"]);
    expect(plan(base, AT_REST).evidence).toBeNull();
  });

  it("Ticket +10%", () => {
    const result = plan(base, { ...AT_REST, ticketPct: r("10") });
    expect(row(result)).toEqual(["57.529412", "46805.77", "2692708.43", "3047955.01", "65.1"]);
    expect(result.evidence).toBe("observed");
  });

  it("Mix: 10 points Retail → Technology (Δmix 2,447.28)", () => {
    const industries = industryRows(levers, "user", "from_2023_06");
    const retail = industries.find((entry) => entry.industry_code === "RETAIL")!;
    const technology = industries.find((entry) => entry.industry_code === "TECHNOLOGY")!;
    const result = plan(base, { ...AT_REST, mix: { points: r("10"), fromRunRate: retail.runRate, toRunRate: technology.runRate } });
    expect(row(result)).toEqual(["57.529412", "44997.98", "2588707.33", "3047955.01", "67.7"]);
    expect(technology.runRate.sub(retail.runRate).mul(r("0.1")).toFixed(2)).toBe("2447.28");
  });

  it("Spend −20%", () => {
    const result = plan(base, { ...AT_REST, spendPct: r("-20") });
    expect(row(result)).toEqual(["57.529412", "42550.70", "2447916.75", "2438364.01", "57.3"]);
    expect(result.evidence).toBe("untested");
  });

  it("Conversion f = 1.05", () => {
    const result = plan(base, { ...AT_REST, volume: r("1.05") });
    expect(row(result)).toEqual(["60.405883", "42550.70", "2570312.61", "2902814.30", "68.2"]);
    expect(result.evidence).toBe("assumption");
  });

  it("reproduces every published baseline exactly, for both definitions", () => {
    for (const period of levers.periods) {
      const own = baselineFor(levers, period.won_definition === "new_logo" ? "new_logo" : "user", period.period_code)!;
      const result = plan(own, AT_REST);
      expect(result.newMrr.toFixed(2), `${period.won_definition} ${period.period_code}`).toBe(period.new_mrr_per_month_value);
      expect(result.payback!.toFixed(1)).toBe(period.payback_months);
    }
  });

  it("labels an output with the weakest lever moved", () => {
    expect(plan(base, { ...AT_REST, ticketPct: r("10"), volume: r("1.05") }).evidence).toBe("assumption");
    expect(plan(base, { ...AT_REST, ticketPct: r("10"), spendPct: r("5") }).evidence).toBe("untested");
    expect(weakest(["observed", "observed"])).toBe("observed");
  });
});

describe("§16.5 changes, reference and value change", () => {
  it("pre → from Jun 2023: +51.9% Won, −23.7% run-rate, +15.9% new MRR, payback 136.1 → 71.6", () => {
    expect(pctChange(pre.wonPerMonth, base.wonPerMonth)!.toFixed(1)).toBe("51.9");
    expect(pctChange(pre.runRate, base.runRate)!.toFixed(1)).toBe("-23.7");
    expect(base.newMrr.sub(pre.newMrr).toFixed(2)).toBe("335718.14");
    expect(pctChange(pre.newMrr, base.newMrr)!.toFixed(1)).toBe("15.9");
    expect([pre.payback!.toFixed(1), base.payback!.toFixed(1)]).toEqual(["136.1", "71.6"]);
  });

  it("splits the run-rate change into mix and within-industry (run-rate weights), both orders", () => {
    const change = valueChange(levers, "user")!;
    expect([change.mix.toFixed(2), change.within.toFixed(2), change.total.toFixed(2)]).toEqual(["-558.82", "-12658.10", "-13216.92"]);
    expect([change.mixReverse.toFixed(2), change.withinReverse.toFixed(2)]).toEqual(["-428.14", "-12788.78"]);
    expect(change.total.equals(base.runRate.sub(pre.runRate))).toBe(true);
    const newLogo = valueChange(levers, "new_logo")!;
    expect([newLogo.mix.toFixed(2), newLogo.within.toFixed(2), newLogo.total.toFixed(2)]).toEqual(["-618.47", "-12232.04", "-12850.52"]);
  });

  it("prices pre-period tickets at today's mix: 55,208.80, +29.7%", () => {
    const reference = ticketReference(levers, "user")!;
    expect(reference.level.toFixed(2)).toBe("55208.80");
    expect(reference.pct.toFixed(1)).toBe("29.7");
  });

  it("ranks ticket size first for a 10% move (ties go to the stronger evidence)", () => {
    const industries = industryRows(levers, "user", "from_2023_06");
    const order = rankLevers(base, industries.at(-1)!.runRate, industries[0]!.runRate);
    expect(order.map((entry) => entry.lever)).toEqual(["ticket", "conversion", "mix", "spend"]);
    expect(order[0]!.delta!.toFixed(2)).toBe("244791.68");
    expect(order[3]!.delta).toBeNull();
  });

  it("shows the §16.6 'no measurable link' clause only when de-trended signals ≤ 2 × chance", () => {
    expect(noMeasurableLink(summary.signal_summary)).toBe(true);
    const planted = summary.signal_summary.map((entry) =>
      entry.method === "within_regime" && entry.won_definition === "user" && entry.scope_type === "company" ? { ...entry, signals: 5 } : entry,
    );
    expect(noMeasurableLink(planted)).toBe(false);
  });
});
