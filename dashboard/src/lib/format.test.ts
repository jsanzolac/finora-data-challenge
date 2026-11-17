import { describe, expect, it } from "vitest";
import { firstSentence, formatDeltaArrow, initials, plural } from "./format";

describe("plain-language formatting", () => {
  it("takes the first sentence of a description, ignoring dots inside code and numbers", () => {
    expect(firstSentence("Spend keeps its sign. It is never made absolute.")).toBe("Spend keeps its sign.");
    expect(firstSentence("`amount` matches `^-?[0-9]+(\\.[0-9]+)?$`; otherwise it fails. `1e3` fails.")).toBe(
      "`amount` matches `^-?[0-9]+(\\.[0-9]+)?$`; otherwise it fails.",
    );
    expect(firstSentence("S < 0.5 × R. Then it fires.")).toBe("S < 0.5 × R.");
    expect(firstSentence("No full stop")).toBe("No full stop");
  });

  it("makes initials from the email's local part", () => {
    expect(initials("data@finora.test")).toBe("DA");
    expect(initials("new.analyst@finora.test")).toBe("NA");
  });

  it("writes counts and changes plainly", () => {
    expect(plural(1, "row", "rows")).toBe("1 row");
    expect(plural(1234, "row", "rows")).toBe("1,234 rows");
    expect(formatDeltaArrow(0.1)).toBe("▲ 0.10 pts");
    expect(formatDeltaArrow(-2.67)).toBe("▼ 2.67 pts");
  });
});
