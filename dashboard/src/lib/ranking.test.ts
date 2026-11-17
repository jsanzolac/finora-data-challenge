import { describe, expect, it } from "vitest";
import type { DatasetSummary, Rule, TrendPoint } from "@/lib/api/types";
import { deltaVsPrevious, hasIssue, rankDatasets, visibleRules } from "./ranking";

function ds(id: string, label: string, pct: number, rank: number): DatasetSummary {
  return {
    dataset_id: id,
    label,
    rows_read: 100,
    rows_excluded: 0,
    rows_flagged: 0,
    row_compliance_pct: pct,
    rules_evaluated: 4,
    rules_failing: 0,
    rank,
  };
}

function rule(id: string, layer: string, kind: "row" | "finding", pcts: Record<string, number | null>): Rule {
  const results: Rule["results"] = {};
  for (const [dataset, pct] of Object.entries(pcts)) {
    results[dataset] =
      pct === null
        ? { evaluated: 0, failed: 0, compliance_pct: null, status: "na" }
        : { evaluated: 100, failed: 100 - pct, compliance_pct: pct, status: pct === 100 ? "pass" : "warn" };
  }
  return {
    rule_id: id,
    title: `Rule ${id}`,
    description: "",
    layer,
    kind,
    action: kind === "finding" ? "finding" : "exclude",
    inferred: false,
    counts_toward_compliance: true,
    applies_to: Object.keys(pcts).filter((key) => pcts[key] !== null),
    results,
  };
}

describe("rankDatasets", () => {
  it("orders by the API rank, most compliant first, whatever order the payload uses", () => {
    const ranked = rankDatasets([ds("industry", "Industry", 99.95, 3), ds("transactions", "Transactions", 100, 1), ds("sm_spend", "S&M spend", 100, 2)]);
    expect(ranked.map((d) => d.dataset_id)).toEqual(["transactions", "sm_spend", "industry"]);
  });

  it("falls back to compliance, then the label, when ranks tie or are missing", () => {
    const ranked = rankDatasets([ds("b", "Beta", 90, Number.NaN), ds("a", "Alpha", 90, Number.NaN), ds("c", "Gamma", 95, Number.NaN)]);
    expect(ranked.map((d) => d.dataset_id)).toEqual(["c", "a", "b"]);
  });

  it("does not mutate its input", () => {
    const input = [ds("x", "X", 50, 2), ds("y", "Y", 60, 1)];
    rankDatasets(input);
    expect(input.map((d) => d.dataset_id)).toEqual(["x", "y"]);
  });
});

describe("deltaVsPrevious", () => {
  const trend: TrendPoint[] = [
    { run_id: "r1", as_of_month: "2024-08", transactions: 99.9 },
    { run_id: "r2", as_of_month: "2024-09", transactions: 99.95 },
    { run_id: "r3", as_of_month: "2024-10", transactions: 99.5 },
  ];
  it("gives the signed change in points and a direction", () => {
    expect(deltaVsPrevious(trend, "r2", "transactions")).toMatchObject({ value: 0.05, direction: "up" });
    expect(deltaVsPrevious(trend, "r3", "transactions")).toMatchObject({ value: -0.45, direction: "down" });
  });
  it("is null for the first run", () => {
    expect(deltaVsPrevious(trend, "r1", "transactions")).toBeNull();
  });
});

describe("visibleRules", () => {
  const ids = ["transactions", "industry"];
  const rules = [
    rule("SQ-02", "silver_quality", "row", { transactions: 100, industry: 99 }),
    rule("SQ-08", "silver_quality", "finding", { transactions: 100, industry: null }),
    rule("SB-10", "silver_business", "row", { transactions: 80, industry: null }),
    rule("SQ-10", "silver_quality", "row", { transactions: 99.5, industry: null }),
  ];
  // SQ-10 is a fail at a higher compliance than SB-10's warn: status decides first.
  rules[3]!.results.transactions!.status = "fail";

  it("shows only rules with an issue by default, worst status first, then lowest compliance", () => {
    expect(visibleRules(rules, ids, true).map((r) => r.rule_id)).toEqual(["SQ-10", "SB-10", "SQ-02"]);
  });

  it("shows every rule with the toggle, passing rules last", () => {
    expect(visibleRules(rules, ids, false).map((r) => r.rule_id)).toEqual(["SQ-10", "SB-10", "SQ-02", "SQ-08"]);
  });

  it("counts a rule with failures as an issue, and a rule that passes everywhere as none", () => {
    expect(hasIssue(rules[0]!, ids)).toBe(true);
    expect(hasIssue(rules[1]!, ids)).toBe(false);
  });

  it("does not mutate its input", () => {
    visibleRules(rules, ids, false);
    expect(rules.map((r) => r.rule_id)).toEqual(["SQ-02", "SQ-08", "SB-10", "SQ-10"]);
  });
});
