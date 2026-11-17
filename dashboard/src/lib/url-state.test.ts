import { describe, expect, it } from "vitest";
import { DEFAULT_PAGE_SIZE, EMPTY_URL_STATE, parseUrlState, serializeUrlState, type UrlState } from "./url-state";

const roundTrip = (state: UrlState) => parseUrlState(new URLSearchParams(serializeUrlState(state)));

describe("URL state", () => {
  it("round-trips a deep link to a cell with search, page and size", () => {
    const state: UrlState = { run: "r20261116T041000Z", rule: "SQ-07a", dataset: "sm_spend", q: "$0,4 & co", page: 3, size: 200 };
    expect(roundTrip(state)).toEqual(state);
  });

  it("keeps the plain overview as an empty query", () => {
    expect(serializeUrlState(EMPTY_URL_STATE)).toBe("");
    expect(roundTrip(EMPTY_URL_STATE)).toEqual(EMPTY_URL_STATE);
  });

  it("treats run=latest as the latest run and leaves defaults out", () => {
    const parsed = parseUrlState(new URLSearchParams("run=latest&rule=SQ-02&dataset=industry&page=1&size=50"));
    expect(parsed).toEqual({ ...EMPTY_URL_STATE, rule: "SQ-02", dataset: "industry" });
    expect(serializeUrlState(parsed)).toBe("rule=SQ-02&dataset=industry");
  });

  it("ignores half a cell and bad numbers", () => {
    expect(parseUrlState(new URLSearchParams("rule=SQ-02&q=x&page=4"))).toEqual(EMPTY_URL_STATE);
    const bad = parseUrlState(new URLSearchParams("rule=A&dataset=b&page=-2&size=999"));
    expect(bad.page).toBe(1);
    expect(bad.size).toBe(DEFAULT_PAGE_SIZE);
  });
});
