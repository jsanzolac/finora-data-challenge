import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import * as Tooltip from "@radix-ui/react-tooltip";
import type { DqRecord } from "@/lib/api/types";
import { RawValue, RESTRICTED_HINT } from "./CellValue";
import { RecordsTable } from "./RecordsTable";

const wrap = (ui: React.ReactNode) => render(<Tooltip.Provider delayDuration={0}>{ui}</Tooltip.Provider>);

describe("raw value rendering", () => {
  it("shows a Restricted pill, never the sentinel, with the Finance-only hint on focus", async () => {
    wrap(<RawValue value="__restricted__" />);
    const pill = screen.getByRole("button", { name: /Restricted/ });
    expect(pill).toHaveAccessibleName(`Restricted: ${RESTRICTED_HINT}`);
    expect(screen.queryByText("__restricted__")).toBeNull();
    await userEvent.tab();
    expect(pill).toHaveFocus();
    expect((await screen.findAllByText(RESTRICTED_HINT)).length).toBeGreaterThan(0);
  });

  it("shows an empty string as an explicit (empty) token", () => {
    wrap(<RawValue value="" />);
    expect(screen.getByTestId("empty-value")).toHaveTextContent("(empty)");
  });

  it("keeps the value exactly, and makes control characters and edge spaces visible", () => {
    const { container } = wrap(<RawValue value={"-$0.016"} />);
    expect(container).toHaveTextContent("-$0.016");
    const tab = wrap(<RawValue value={"7.5\t"} />);
    expect(screen.getByTitle("U+0009")).toHaveTextContent("␉");
    tab.unmount();
    wrap(<RawValue value="Tecnologia " />);
    expect(screen.getByTitle("Trailing whitespace").textContent).toBe(" ");
  });
});

describe("records table", () => {
  const record: DqRecord = {
    source_line: 28,
    key: { Month: "2024-03" },
    values: { Month: "2024-03", PaidMedia: "$1.380", Team: "__restricted__", PayrollExpenses: "__restricted__" },
    failed_columns: ["PayrollExpenses"],
    reason: "NEGATIVE_SPEND: PayrollExpenses is below zero",
    action: "flag",
    other_failed_rules: ["SQ-10"],
  };

  it("shows the source columns only, restricted values, the failing column, and the reason one tap away", async () => {
    const onOpen = vi.fn();
    wrap(
      <RecordsTable
        records={[record]}
        columns={["Month", "PaidMedia", "Team", "PayrollExpenses"]}
        finding={false}
        firstIndex={0}
        otherRuleLink={(ruleId) => ({ ruleId, href: `/?rule=${ruleId}&dataset=sm_spend`, title: "Spend cells format" })}
        onOpenOtherRule={onOpen}
        caption="Records"
      />,
    );
    const headers = screen.getAllByRole("columnheader").map((th) => th.textContent);
    expect(headers).toEqual(["Month", "PaidMedia", "Team", "PayrollExpenses", "Why"]);
    expect(screen.getAllByTestId("restricted-value")).toHaveLength(2);
    const failed = document.querySelectorAll('td[data-failed="true"]');
    expect(failed).toHaveLength(1);
    expect(failed[0]).toHaveTextContent("(fails the rule)");

    // The reason is hidden until the row is expanded.
    expect(screen.getByTestId("record-reason")).not.toBeVisible();
    const toggle = screen.getByRole("button", { name: "Why line 28 fails" });
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    await userEvent.click(toggle);
    expect(toggle).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByTestId("record-reason")).toHaveTextContent("Line 28: PayrollExpenses is below zero. (NEGATIVE_SPEND)");
    await userEvent.click(screen.getByRole("link", { name: "Spend cells format" }));
    expect(onOpen).toHaveBeenCalledWith("SQ-10");
  });
});
