import { describe, expect, it } from "vitest";
import type { Rule } from "@/lib/api/types";
import { NA_RESULT, datasetStatus, resultFor, severity, statusMeta } from "./status";

describe("cell status mapping", () => {
  it("maps each API status to a plain-language word and interactivity", () => {
    expect(statusMeta("pass")).toMatchObject({ tone: "pass", label: "Good", interactive: true });
    expect(statusMeta("warn")).toMatchObject({ tone: "warn", label: "Review", interactive: true });
    expect(statusMeta("fail")).toMatchObject({ tone: "fail", label: "Action needed", interactive: true });
    expect(statusMeta("na")).toMatchObject({ tone: "na", label: "Doesn't apply", interactive: false });
  });

  it("orders statuses by severity: fail > warn > pass > na", () => {
    expect(["na", "pass", "warn", "fail"].map(severity)).toEqual([0, 1, 2, 3]);
  });

  it("treats an unknown or missing status as an inert N/A cell", () => {
    expect(statusMeta("bogus")).toMatchObject({ tone: "na", interactive: false });
    expect(statusMeta(undefined)).toMatchObject({ tone: "na", interactive: false });
    expect(statusMeta("toString")).toMatchObject({ tone: "na" });
  });

  it("reads a missing dataset result as the contract's na result", () => {
    const rule = { results: {} } as unknown as Rule;
    expect(resultFor(rule, "industry")).toEqual(NA_RESULT);
    expect(NA_RESULT).toEqual({ evaluated: 0, failed: 0, compliance_pct: null, status: "na" });
  });
});

describe("department status", () => {
  const cell = (status: "pass" | "warn" | "fail" | "na") => ({
    evaluated: status === "na" ? 0 : 10,
    failed: status === "pass" || status === "na" ? 0 : 1,
    compliance_pct: status === "na" ? null : 90,
    status,
  });
  const rules = [
    { rule_id: "A", results: { x: cell("pass"), y: cell("warn") } },
    { rule_id: "B", results: { x: cell("warn"), y: cell("na") } },
    { rule_id: "C", results: { x: cell("pass"), y: cell("fail") } },
  ] as unknown as Rule[];

  it("takes the worst API status of the department's rules", () => {
    expect(datasetStatus(rules, "x")).toBe("warn");
    expect(datasetStatus(rules, "y")).toBe("fail");
    expect(datasetStatus(rules, "z")).toBe("na");
  });

});
