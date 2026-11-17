/**
 * The identities of contracts/mrr_api_contract.md v1, checked on the mock fixtures
 * (generated from today's real files), and the UI's period rule.
 */
import { describe, expect, it } from "vitest";
import summaryFixture from "@mocks/mrr/summary.json";
import movementsFixture from "@mocks/mrr/movements.json";
import { resolvePeriod } from "@/lib/acq/periods";
import { Ratio } from "@/lib/acq/ratio";
import { bridgeCloses, LAST_12, mrrPeriodOptions, periodBridge, sumOrNull } from "./bridge";
import { buildMrrTable, mrrCsv } from "./monthly";
import type { MrrMovement, MrrSummary } from "./types";
import { parseMrrUrlState, serializeMrrUrlState } from "./url-state";

const summary = summaryFixture as unknown as MrrSummary;
const movements = movementsFixture as unknown as MrrMovement[];
const money = (value: string | null) => (value === null ? null : Ratio.parse(value));

describe("bridge identities on the fixture", () => {
  it("closes every month: opening + Σ steps = closing, exactly", () => {
    for (const month of summary.months) {
      const steps = Object.values(month.step_value).reduce((sum, value) => (value === null ? sum : sum.add(Ratio.parse(value))), Ratio.ZERO);
      expect(money(month.opening_mrr_value)!.add(steps).equals(money(month.closing_mrr_value)!), month.month).toBe(true);
    }
  });

  it("is continuous: closing(m) = opening(m+1)", () => {
    summary.months.slice(1).forEach((month, index) => {
      expect(month.opening_mrr_value).toBe(summary.months[index]!.closing_mrr_value);
    });
  });

  it("reconciles to cash: Σ steps + timing change = cash change, every month", () => {
    summary.months.slice(1).forEach((month, index) => {
      const before = summary.months[index]!;
      const steps = Object.values(month.step_value).reduce((sum, value) => (value === null ? sum : sum.add(Ratio.parse(value))), Ratio.ZERO);
      const timing = money(month.timing_value)!.sub(money(before.timing_value)!);
      const cash = money(month.cash_value)!.sub(money(before.cash_value)!);
      expect(steps.add(timing).equals(cash), month.month).toBe(true);
    });
  });

  it("sends every step code in every month, with null (never 0) for the lines cash_proxy can't observe", () => {
    const codes = summary.steps.map((step) => step.code).sort();
    const discount = summary.steps.filter((step) => step.driver === "discount").map((step) => step.code);
    expect(discount.length).toBeGreaterThan(0);
    // §6.3: lines 9 (list_price_change) and 11-15 (discounts) are NULL on cash_proxy.
    const unobservable = [...discount, "list_price_change"];
    for (const month of summary.months) {
      expect(Object.keys(month.step_value).sort()).toEqual(codes);
      for (const code of unobservable) {
        expect(month.step_value[code]).toBeNull();
        expect(month.step_customers[code]).toBeNull();
      }
      expect([month.list_mrr_value, month.discount_value]).toEqual([null, null]);
    }
    expect(summary.drivers.find((driver) => driver.code === "discount")?.available).toBe(false);
    expect(summary.run.mrr_basis).toBe("cash_proxy");
  });

  it("matches the movements: Σ change per month and step = the step value", () => {
    const totals = new Map<string, Ratio>();
    for (const row of movements) {
      const key = `${row.month}|${row.step}`;
      totals.set(key, (totals.get(key) ?? Ratio.ZERO).add(Ratio.parse(row.change_value!)));
    }
    for (const month of summary.months) {
      for (const [code, value] of Object.entries(month.step_value)) {
        if (value === null) continue;
        expect((totals.get(`${month.month}|${code}`) ?? Ratio.ZERO).equals(Ratio.parse(value)), `${month.month} ${code}`).toBe(true);
      }
    }
    expect(movements.every((row) => Array.isArray(row.flags))).toBe(true);
    expect(movements.filter((row) => row.driver === "pricing").every((row) => row.inferred && row.flags.includes("late_price_step"))).toBe(true);
    expect(movements).toHaveLength(4589);
  });

  it("marks the months after churn_confirmed_through as provisional", () => {
    const provisional = summary.months.filter((month) => month.is_provisional).map((month) => month.month);
    expect(provisional).toEqual(["2024-09", "2024-10"]);
    expect(summary.run.churn_confirmed_through).toBe("2024-08");
  });
});

describe("period rule", () => {
  const options = mrrPeriodOptions(summary);

  it("defaults to the last 12 months and offers the Acquisition presets", () => {
    expect(options[0]!.id).toBe(LAST_12);
    expect(options[0]!.months).toHaveLength(12);
    expect(options[0]!.months.at(-1)).toBe("2024-10");
    expect(options.map((option) => option.id)).toEqual(expect.arrayContaining(["full", "2023", "2024-Q2", "2024-10"]));
  });

  it("chains the months: drivers add up to the MRR change, and with cash timing to the cash change", () => {
    for (const id of [LAST_12, "2023", "2024-Q2", "2024-10"]) {
      const bridge = periodBridge(summary, resolvePeriod(options, id));
      expect(bridgeCloses(bridge), id).toBe(true);
      const drivers = bridge.drivers.filter((entry) => entry.value).reduce((sum, entry) => sum.add(entry.value!), Ratio.ZERO);
      expect(drivers.equals(bridge.change!), id).toBe(true);
      expect(drivers.add(bridge.timingChange!).equals(bridge.cashChange!), id).toBe(true);
      expect(bridge.drivers.find((entry) => entry.driver.code === "discount")?.value, id).toBeNull();
      expect(bridge.leakage, id).toBeNull();
    }
  });

  it("shows the gold spec's figures (docs/mrr_discounts_model.md §6.6, × 10,000)", () => {
    const full = periodBridge(summary, resolvePeriod(options, "full"));
    const driver = (code: string) => full.drivers.find((entry) => entry.driver.code === code)?.value?.toFixed(2) ?? null;
    expect(full.opening!.toFixed(2)).toBe("35000308.35");
    expect(full.closing!.toFixed(2)).toBe("96360646.83");
    expect(full.change!.toFixed(2)).toBe("61360338.48");
    expect([driver("behaviour"), driver("pricing"), driver("timing"), driver("discount")]).toEqual([
      "63200703.30",
      "574367.43",
      "-2414732.25",
      null,
    ]);
    const october = periodBridge(summary, resolvePeriod(options, "2024-10"));
    expect([october.opening!.toFixed(2), october.closing!.toFixed(2)]).toEqual(["92747125.17", "96360646.83"]);
    const step = (code: string) => october.steps.find((entry) => entry.step.code === code)?.value?.toFixed(2) ?? null;
    expect([step("grace_drop"), step("resume"), step("first_payment_multiple"), step("list_price_change")]).toEqual([
      "-2300122.02",
      "1160086.20",
      "-8190.00",
      null,
    ]);
  });

  it("uses the first month's opening and the last month's closing", () => {
    const bridge = periodBridge(summary, resolvePeriod(options, "2023"));
    expect(bridge.opening!.toFixed(2)).toBe(summary.months.find((month) => month.month === "2023-01")!.opening_mrr_value);
    expect(bridge.closing!.toFixed(2)).toBe(summary.months.find((month) => month.month === "2023-12")!.closing_mrr_value);
  });

  it("has no timing change when the month before the period is outside the window", () => {
    const bridge = periodBridge(summary, resolvePeriod(options, "full"));
    expect(bridge.timingChange).toBeNull();
    expect(bridgeCloses(bridge)).toBe(true);
  });

  it("treats null as unknown, never 0", () => {
    expect(sumOrNull(["1.00", null, "2.00"])).toBeNull();
    expect(sumOrNull(["1.00", "2.50"])!.toFixed(2)).toBe("3.50");
  });
});

describe("URL state and the monthly CSV", () => {
  it("omits defaults", () => {
    expect(serializeMrrUrlState(parseMrrUrlState(new URLSearchParams("")))).toBe("");
    expect(parseMrrUrlState(new URLSearchParams("period=2023&run=r1"))).toEqual({ period: "2023", run: "r1" });
    expect(parseMrrUrlState(new URLSearchParams("period=%3Cx%3E")).period).toBe(LAST_12);
  });

  it("writes 'not available' for unknown values, never 0", () => {
    const csv = mrrCsv(buildMrrTable(summary)).split("\r\n");
    expect(csv[0]).toContain("Opening MRR");
    expect(csv[1]).toContain("not available");
    expect(csv).toHaveLength(summary.months.length + 2);
  });
});
