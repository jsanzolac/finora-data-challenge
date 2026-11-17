/**
 * The funnel arithmetic against docs/gold_acquisition_model.md §12.5 and §12.6
 * (counts to 6 dp and costs to 2 dp, HALF_UP, as the gold views store them),
 * and the display rounding the page uses (counts 1 dp, costs whole units).
 */
import { describe, expect, it } from "vitest";
import fixture from "@mocks/acq/summary.json";
import { compareScenario, computeFunnel, overallRate, sensitivities, transitionsFor, type Transition } from "./funnel";
import { formatCount, formatMoney } from "./format";
import { periodOptions, periodTotals, resolvePeriod } from "./periods";
import { Ratio } from "./ratio";
import type { AcqSummary, FunnelStage, ScenarioRate } from "./types";

const summary = fixture as unknown as AcqSummary;

const STAGES: FunnelStage[] = [
  { code: "NEW", label: "New", order: 1 },
  { code: "WORKING", label: "Working", order: 2 },
  { code: "ENGAGED", label: "Engaged", order: 3 },
  { code: "SQL", label: "SQL", order: 4 },
  { code: "DEMO", label: "Demo", order: 5 },
  { code: "PROPOSAL", label: "Proposal", order: 6 },
  { code: "WON", label: "Won", order: 7 },
];

function rates(values: string[]): ScenarioRate[] {
  return values.map((rate, index) => ({ from_stage: STAGES[index]!.code, to_stage: STAGES[index + 1]!.code, rate }));
}

const BASE_RATES = rates(["0.8000", "0.4000", "0.5000", "0.7000", "0.6000", "0.4000"]);
const SQL_DEMO_080 = rates(["0.8000", "0.4000", "0.5000", "0.8000", "0.6000", "0.4000"]);
const base = transitionsFor(STAGES, BASE_RATES)!;

function funnel(won: number, spend: string, transitions: Transition[] = base) {
  return computeFunnel({ stages: STAGES, transitions, won: Ratio.of(BigInt(won)), spend: Ratio.parse(spend), costNullReason: null });
}

/** [count 6 dp, cost 2 dp] per stage, New first. */
function stored(result: ReturnType<typeof funnel>): [string, string][] {
  return result.stages.map((stage) => [stage.count.toFixed(6), stage.costPerUnit?.toFixed(2) ?? "null"]);
}

describe("base funnel (§12.5)", () => {
  it("reproduces the full period, user Won", () => {
    expect(stored(funnel(1584, "7581800000"))).toEqual([
      ["58928.571429", "128660.85"],
      ["47142.857143", "160826.06"],
      ["18857.142857", "402065.15"],
      ["9428.571429", "804130.30"],
      ["6600.000000", "1148757.58"],
      ["3960.000000", "1914595.96"],
      ["1584.000000", "4786489.90"],
    ]);
  });

  it("reproduces the full period, new-logo Won", () => {
    expect(stored(funnel(1541, "7581800000"))).toEqual([
      ["57328.869048", "132251.00"],
      ["45863.095238", "165313.74"],
      ["18345.238095", "413284.36"],
      ["9172.619048", "826568.72"],
      ["6420.833333", "1180812.46"],
      ["3852.500000", "1968020.77"],
      ["1541.000000", "4920051.91"],
    ]);
  });

  it("reproduces 2024-10", () => {
    expect(stored(funnel(50, "200000000"))).toEqual([
      ["1860.119048", "107520.00"],
      ["1488.095238", "134400.00"],
      ["595.238095", "336000.00"],
      ["297.619048", "672000.00"],
      ["208.333333", "960000.00"],
      ["125.000000", "1600000.00"],
      ["50.000000", "4000000.00"],
    ]);
  });

  it("reproduces 2022-09 and 2022-02", () => {
    const sep = stored(funnel(17, "350000000"));
    expect(sep[0]).toEqual(["632.440476", "553411.76"]);
    expect(sep[6]).toEqual(["17.000000", "20588235.29"]);
    const feb = stored(funnel(108, "230000000"));
    expect(feb[0]).toEqual(["4017.857143", "57244.44"]);
    expect(feb[6]).toEqual(["108.000000", "2129629.63"]);
  });

  it("displays counts to 1 dp and costs in whole units, HALF_UP", () => {
    const month = funnel(50, "200000000");
    expect(formatCount(month.stages[0]!.count)).toBe("1,860.1");
    expect(formatMoney(month.stages[0]!.costPerUnit)).toBe("107,520");
    const full = funnel(1584, "7581800000");
    expect(formatCount(full.stages[0]!.count)).toBe("58,928.6");
    expect(formatMoney(full.stages[0]!.costPerUnit)).toBe("128,661");
    expect(formatMoney(full.stages[6]!.costPerUnit)).toBe("4,786,490");
    expect(full.stages.map((stage) => stage.real)).toEqual([false, false, false, false, false, false, true]);
  });

  it("keeps count(stage) × rate = count(next) exactly", () => {
    const full = funnel(1584, "7581800000");
    for (let index = 0; index < base.length; index += 1) {
      expect(full.stages[index]!.count.mul(base[index]!.rate).equals(full.stages[index + 1]!.count)).toBe(true);
    }
    expect(overallRate(base).toFixed(6)).toBe("0.026880");
  });

  it("shows cost as unavailable when Won is 0 or a month has a cost_null_reason, counts still shown", () => {
    const zero = computeFunnel({ stages: STAGES, transitions: base, won: Ratio.ZERO, spend: Ratio.parse("100"), costNullReason: null });
    expect(zero.costUnavailable).toBe("won_zero");
    expect(zero.stages.every((stage) => stage.costPerUnit === null && stage.count.isZero())).toBe(true);
    const missing = computeFunnel({ stages: STAGES, transitions: base, won: Ratio.of(41n), spend: null, costNullReason: "spend_missing" });
    expect(missing.costUnavailable).toBe("spend_missing");
    expect(missing.stages[0]!.costPerUnit).toBeNull();
    expect(formatCount(missing.stages[0]!.count)).toBe("1,525.3");
  });
});

describe("periods from the fixture (§12.5 period table)", () => {
  const options = periodOptions(summary);
  const won = (id: string, definition: "user" | "new_logo" = "user") => periodTotals(summary, resolvePeriod(options, id), definition);
  const costPerWon = (id: string) => {
    const totals = won(id);
    return totals.spend!.div(totals.won).toFixed(2);
  };

  it("full period: 33 months, Won 1,584 (new logo 1,541), spend 7,581,800,000", () => {
    const full = won("full");
    expect(full.months).toHaveLength(33);
    expect(full.won.toFixed(0)).toBe("1584");
    expect(won("full", "new_logo").won.toFixed(0)).toBe("1541");
    expect(full.spend!.toFixed(0)).toBe("7581800000");
  });

  it("regimes, years and quarters", () => {
    expect([won("pre_2023_06").months.length, won("pre_2023_06").won.toFixed(0), costPerWon("pre_2023_06")]).toEqual([16, "606", "7592244.22"]);
    expect([won("from_2023_06").months.length, won("from_2023_06").won.toFixed(0), costPerWon("from_2023_06")]).toEqual([17, "978", "3047955.01"]);
    expect([won("2022").won.toFixed(0), costPerWon("2022")]).toEqual(["380", "8146315.79"]);
    expect([won("2023").won.toFixed(0), costPerWon("2023")]).toEqual(["650", "3862615.38"]);
    expect([won("2024").won.toFixed(0), costPerWon("2024")]).toEqual(["554", "3565884.48"]);
    expect([won("2022-Q1").won.toFixed(0), won("2022-Q1").spend!.toFixed(0), costPerWon("2022-Q1")]).toEqual(["138", "460000000", "3333333.33"]);
    expect([won("2023-Q3").won.toFixed(0), costPerWon("2023-Q3")]).toEqual(["187", "2194117.65"]);
    expect([won("2024-Q2").won.toFixed(0), costPerWon("2024-Q2")]).toEqual(["219", "3014611.87"]);
    expect(resolvePeriod(options, "2022").partial).toBe(true);
    expect(resolvePeriod(options, "2023").partial).toBe(false);
    expect(resolvePeriod(options, "2022-Q1").partial).toBe(true);
  });

  it("falls back to the full period for an unknown id", () => {
    expect(resolvePeriod(options, "1999-13").id).toBe("full");
    expect(resolvePeriod(options, null).id).toBe("full");
  });
});

describe("scenario vs base and sensitivity (§12.6)", () => {
  const won = Ratio.of(1584n);
  const spend = Ratio.parse("7581800000");
  const scenario = transitionsFor(STAGES, SQL_DEMO_080)!;

  it("sql_demo_080 against base, full period, user Won", () => {
    const result = compareScenario(won, spend, scenario, base);
    expect(result.overall.toFixed(5)).toBe("0.03072");
    expect(result.overallBase.toFixed(5)).toBe("0.02688");
    expect(result.newEstimatedBase.toFixed(6)).toBe("58928.571429");
    expect(result.wonImplied.toFixed(6)).toBe("1810.285714");
    expect(result.wonImpliedDelta.toFixed(6)).toBe("226.285714");
    expect(result.wonImpliedDeltaPct!.toFixed(6)).toBe("14.285714");
    expect(result.newRequired.toFixed(6)).toBe("51562.500000");
    expect(result.newRequiredDelta.toFixed(6)).toBe("-7366.071429");
    expect(result.costPerWonImplied!.toFixed(2)).toBe("4188178.66");
  });

  it("base against itself changes nothing", () => {
    const result = compareScenario(won, spend, base, base);
    expect(result.wonImpliedDelta.isZero()).toBe(true);
    expect(result.newRequiredDelta.isZero()).toBe(true);
    expect(result.costPerWonImplied!.toFixed(2)).toBe("4786489.90");
  });

  it("sensitivity per transition, base, full period", () => {
    const rows = sensitivities(won, base).map((row) => [
      `${row.from}→${row.to}`,
      row.rate.toFixed(2),
      row.wonPctPerPoint!.toFixed(6),
      row.wonPerPoint!.toFixed(6),
    ]);
    expect(rows).toEqual([
      ["NEW→WORKING", "0.80", "1.250000", "19.800000"],
      ["WORKING→ENGAGED", "0.40", "2.500000", "39.600000"],
      ["ENGAGED→SQL", "0.50", "2.000000", "31.680000"],
      ["SQL→DEMO", "0.70", "1.428571", "22.628571"],
      ["DEMO→PROPOSAL", "0.60", "1.666667", "26.400000"],
      ["PROPOSAL→WON", "0.40", "2.500000", "39.600000"],
    ]);
    expect(sensitivities(won, base)[0]!.newRequiredPctPerPoint!.toFixed(6)).toBe("-1.234568");
  });

  it("is null when the rate cannot move up a point", () => {
    const capped = transitionsFor(STAGES, rates(["1.0000", "0.4000", "0.5000", "0.9950", "0.9900", "0.4000"]))!;
    const rows = sensitivities(won, capped);
    expect(rows[0]!.wonPctPerPoint).toBeNull();
    expect(rows[3]!.wonPerPoint).toBeNull();
    expect(rows[4]!.wonPctPerPoint!.toFixed(4)).toBe("1.0101");
  });

  it("rejects rate sets that are not the 6 consecutive transitions in (0, 1]", () => {
    expect(transitionsFor(STAGES, BASE_RATES.slice(1))).toBeNull();
    expect(transitionsFor(STAGES, rates(["0.8000", "0.4000", "0.5000", "1.2000", "0.6000", "0.4000"]))).toBeNull();
    expect(transitionsFor(STAGES, rates(["0.8000", "0.4000", "0.0000", "0.7000", "0.6000", "0.4000"]))).toBeNull();
    const swapped = BASE_RATES.map((rate, index) => (index === 2 ? { ...rate, to_stage: "DEMO" } : rate));
    expect(transitionsFor(STAGES, swapped)).toBeNull();
  });
});

describe("Ratio", () => {
  it("parses, rounds HALF_UP away from zero and keeps exactness", () => {
    expect(Ratio.parse("-0.016").toFixed(2)).toBe("-0.02");
    expect(Ratio.parse("2.5").toFixed(0)).toBe("3");
    expect(Ratio.parse("-2.5").toFixed(0)).toBe("-3");
    expect(Ratio.parse("0.125").toFixed(2)).toBe("0.13");
    expect(Ratio.of(1n, 3n).mul(Ratio.of(3n)).equals(Ratio.ONE)).toBe(true);
    expect(Ratio.tryParse("1e5")).toBeNull();
    expect(Ratio.tryParse("__restricted__")).toBeNull();
    expect(Ratio.parse("0.8125").hasAtMostDecimals(4)).toBe(true);
    expect(Ratio.parse("0.81255").hasAtMostDecimals(4)).toBe(false);
  });
});
