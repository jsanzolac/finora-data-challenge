import { describe, expect, it } from "vitest";
import fixture from "@mocks/acq/summary.json";
import { RESTRICTED_VALUE } from "@/lib/api/types";
import { formatCompact, formatR, groupDigits } from "./format";
import { buildMonthlyTable, monthlyCsv } from "./monthly-table";
import { Ratio } from "./ratio";
import { fieldErrorsFromDetails, parsePercentDraft, suggestId, toScenarioRates, validateSaveDraft } from "./scenario-form";
import { aboveChance, binomialTail, correlationGrid, readSignals } from "./signals";
import type { AcqSummary } from "./types";
import { parseAcqUrlState, serializeAcqUrlState } from "./url-state";

const summary = fixture as unknown as AcqSummary;

describe("acquisition URL state", () => {
  it("omits defaults and round-trips", () => {
    const state = parseAcqUrlState(new URLSearchParams(""));
    expect(state).toEqual({ period: "full", scenario: "base", def: "user", run: null });
    expect(serializeAcqUrlState(state)).toBe("");
    const deep = parseAcqUrlState(new URLSearchParams("period=2023-Q2&scenario=sql_demo_080&def=new_logo"));
    expect(deep).toEqual({ period: "2023-Q2", scenario: "sql_demo_080", def: "new_logo", run: null });
    expect(serializeAcqUrlState(deep)).toBe("period=2023-Q2&scenario=sql_demo_080&def=new_logo");
  });

  it("drops values that are not plain tokens", () => {
    const state = parseAcqUrlState(new URLSearchParams("period=%3Cscript%3E&scenario=a%20b&def=other&run=latest"));
    expect(state).toEqual({ period: "full", scenario: "base", def: "user", run: null });
  });
});

describe("signals reading (§7.5)", () => {
  it("says no usable relationship for today's files, with the summary numbers", () => {
    const reading = readSignals(summary.signal_summary, "user");
    expect(reading.noUsableRelationship).toBe(true);
    expect([reading.level?.signals, reading.level?.tests_with_r]).toEqual([30, 44]);
    expect([reading.diff?.signals, reading.diff?.tests_with_r, reading.diff?.expected_by_chance]).toEqual([3, 44, 2.2]);
    expect(reading.withinRegime?.signals).toBe(3);
    expect(readSignals(summary.signal_summary, "new_logo").noUsableRelationship).toBe(true);
  });

  it("flags a family only when its signals exceed chance (binomial, 5%)", () => {
    expect(binomialTail(44, 0, 0.05)).toBe(1);
    expect(binomialTail(44, 3, 0.05)).toBeGreaterThan(0.3);
    expect(aboveChance({ tests_with_r: 44, signals: 3 })).toBe(false);
    expect(aboveChance({ tests_with_r: 44, signals: 5 })).toBe(false);
    expect(aboveChance({ tests_with_r: 44, signals: 6 })).toBe(true);
    expect(aboveChance({ tests_with_r: 44, signals: 30 })).toBe(true);
    const planted = summary.signal_summary.map((row) =>
      row.method === "diff" && row.won_definition === "user" && row.scope_type === "company" ? { ...row, signals: 12 } : row,
    );
    expect(readSignals(planted, "user").noUsableRelationship).toBe(false);
  });

  it("builds the series × lag grid (§12.8, company, level)", () => {
    const grid = correlationGrid(summary.correlations, "user", "company", "level");
    expect(grid.lags).toEqual([0, 1, 2, 3]);
    expect(grid.rows).toHaveLength(11);
    const total = grid.rows.find((row) => row.series === "total")!;
    expect(total.cells.map((cell) => cell?.r)).toEqual([-0.4795, -0.4964, -0.419, -0.2609]);
    expect(total.cells.map((cell) => cell?.is_signal)).toEqual([true, true, true, false]);
    expect(total.cells.map((cell) => cell?.n)).toEqual([33, 33, 32, 31]);
    expect(formatR(-0.4795)).toBe("−0.48");
    expect(formatR(0.5996)).toBe("+0.60");
  });
});

describe("rate drafts and the save form", () => {
  it("parses percents into 4-decimal rates", () => {
    const ok = parsePercentDraft("81.25");
    expect(ok.ok && ok.rate.toFixed(4)).toBe("0.8125");
    expect(parsePercentDraft("80 %").ok).toBe(true);
    expect(parsePercentDraft("100").ok).toBe(true);
    expect(parsePercentDraft("0")).toEqual({ ok: false, message: "The rate must be above 0%." });
    expect(parsePercentDraft("100.5")).toEqual({ ok: false, message: "The rate can't be above 100%." });
    expect(parsePercentDraft("12.345")).toEqual({ ok: false, message: "Use at most 2 decimals." });
    expect(parsePercentDraft("abc").ok).toBe(false);
    expect(parsePercentDraft("").ok).toBe(false);
  });

  it("validates id, label and reason like the API", () => {
    expect(validateSaveDraft({ scenario_id: "sql_demo_080", label: "SQL to Demo at 80%", change_reason: "Faster demos" })).toEqual({});
    const errors = validateSaveDraft({ scenario_id: "SQL demo", label: " ", change_reason: "x".repeat(501) });
    expect(Object.keys(errors).sort()).toEqual(["change_reason", "label", "scenario_id"]);
    expect(validateSaveDraft({ scenario_id: "a".repeat(41), label: "x", change_reason: "y" }).scenario_id).toBeDefined();
    expect(suggestId("SQL to Demo at 80%")).toBe("sql_to_demo_at_80");
    expect(suggestId("2025 plan")).toBe("plan");
  });

  it("maps the server's error.details onto fields by `field` (v1.1)", () => {
    expect(
      fieldErrorsFromDetails([
        { check: "GR-01", field: "scenario_id", message: "Bad id." },
        { check: "GR-03", field: "rates", message: "Rate out of range." },
        { check: "LABEL_LENGTH", field: "label", message: "Too long." },
        { check: "REASON_LENGTH", field: "change_reason", message: "Reason needed." },
        { check: "X-99", field: "", message: "Something else." },
      ]),
    ).toEqual({ scenario_id: "Bad id.", rates: "Rate out of range.", label: "Too long.", change_reason: "Reason needed.", form: "Something else." });
    // Without a recognised field, the check id still lands on the right input.
    expect(fieldErrorsFromDetails([{ check: "LABEL_LENGTH", field: "", message: "Too long." }])).toEqual({ label: "Too long." });
  });

  it("sends rates as 4-decimal strings in stage order", () => {
    expect(
      toScenarioRates([
        { from: "NEW", to: "WORKING", rate: Ratio.parse("0.8") },
        { from: "WORKING", to: "ENGAGED", rate: Ratio.parse("0.4125") },
      ]),
    ).toEqual([
      { from_stage: "NEW", to_stage: "WORKING", rate: "0.8000" },
      { from_stage: "WORKING", to_stage: "ENGAGED", rate: "0.4125" },
    ]);
  });
});

describe("fixture shape (contract v1.1)", () => {
  it("carries the new-logo industry split, low-volume flags and one Won per industry", () => {
    const newLogo = summary.months.reduce((sum, month) => sum + Object.values(month.won_by_industry_new_logo).reduce((a, b) => a + b, 0), 0);
    expect(newLogo).toBe(1541);
    expect(summary.months.every((month) => month.cost_null_reason !== "won_zero")).toBe(true);
    const low = new Set(summary.correlations.filter((row) => row.won_definition === "user" && row.is_low_volume).map((row) => row.scope));
    expect([...low].sort()).toEqual(["HEALTHCARE", "PROFESSIONAL_SERVICES", "TECHNOLOGY"]);
    expect(summary.correlations.every((row) => row.null_reason === null && row.r !== null)).toBe(true);
    const restaurants = summary.industry_profile.filter((row) => row.industry_code === "RESTAURANTS");
    expect(restaurants.map((row) => [row.customer_scope, row.won, row.share_of_observable_months_paid])).toEqual([
      ["all", 420, "0.8952"],
      ["won", 420, "0.8990"],
      ["left_censored", 420, "0.8886"],
    ]);
  });
});

describe("monthly table and CSV", () => {
  it("has one row per month with exact values, and Restricted for masked HR values", () => {
    const masked: AcqSummary = {
      ...summary,
      months: summary.months.map((month) => ({ ...month, spend_value: { ...month.spend_value, Team: RESTRICTED_VALUE } })),
    };
    const table = buildMonthlyTable(masked);
    expect(table.rows).toHaveLength(33);
    expect(table.columns).toHaveLength(1 + 2 + 6 + 1 + 7 + 2);
    const csv = monthlyCsv(table).split("\r\n");
    expect(csv[0]).toContain("Month,Won,\"Won, without probably active\"");
    const last = csv[33]!.split(",");
    expect(last[0]).toBe("2024-10");
    expect(last[1]).toBe("50");
    expect(last[last.length - 1]).toBe("200000000");
    expect(csv[33]).toContain("Restricted");
    expect(csv[33]).toContain("2201333.40");
  });
});

describe("formatting", () => {
  it("groups digits with a real minus and compacts", () => {
    expect(groupDigits("-7366.1")).toBe("−7,366.1");
    expect(groupDigits("4786490")).toBe("4,786,490");
    expect(formatCompact(8146315.79)).toBe("8.1M");
    expect(formatCompact(200000000)).toBe("200M");
    expect(formatCompact(3565884.48)).toBe("3.6M");
  });
});
