import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, getSummary, login, recordsPath, setAuthHandlers } from "./client";

function respond(status: number, body: unknown) {
  return vi.fn(async () => new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } }));
}

describe("API client", () => {
  const onUnauthorized = vi.fn();
  const onPasswordChangeRequired = vi.fn();

  beforeEach(() => {
    setAuthHandlers({ onUnauthorized, onPasswordChangeRequired });
  });
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.clearAllMocks();
    setAuthHandlers({});
  });

  it("calls same-origin with the cookie, never with a token", async () => {
    const fetchMock = respond(200, { run: {}, datasets: [], rules: [], trend: [] });
    vi.stubGlobal("fetch", fetchMock);
    await getSummary("latest");
    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe("/api/dq/summary?run=latest");
    expect(init.credentials).toBe("same-origin");
    expect(JSON.stringify(init.headers)).not.toMatch(/authorization/i);
  });

  it("on 401 throws an ApiError and sends the user to sign in", async () => {
    vi.stubGlobal("fetch", respond(401, { error: { code: "unauthorized", message: "No session." } }));
    const error = await getSummary("latest").catch((cause: unknown) => cause);
    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({ status: 401, code: "unauthorized" });
    expect(onUnauthorized).toHaveBeenCalledTimes(1);
    expect(onPasswordChangeRequired).not.toHaveBeenCalled();
  });

  it("on 403 password_change_required sends the user to the password screen", async () => {
    vi.stubGlobal("fetch", respond(403, { error: { code: "password_change_required", message: "Change it." } }));
    await expect(getSummary("latest")).rejects.toMatchObject({ status: 403, code: "password_change_required" });
    expect(onPasswordChangeRequired).toHaveBeenCalledTimes(1);
    expect(onUnauthorized).not.toHaveBeenCalled();
  });

  it("on any other 403 only reports the error", async () => {
    vi.stubGlobal("fetch", respond(403, { error: { code: "forbidden", message: "Not for your role." } }));
    await expect(getSummary("latest")).rejects.toMatchObject({ status: 403, code: "forbidden", message: "Not for your role." });
    expect(onPasswordChangeRequired).not.toHaveBeenCalled();
    expect(onUnauthorized).not.toHaveBeenCalled();
  });

  it("does not treat a wrong password on login as an expired session", async () => {
    vi.stubGlobal("fetch", respond(401, { error: { code: "invalid_credentials", message: "Wrong." } }));
    await expect(login("a@b.test", "x")).rejects.toMatchObject({ status: 401 });
    expect(onUnauthorized).not.toHaveBeenCalled();
  });

  it("turns a network failure and a non-JSON error into readable ApiErrors", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => Promise.reject(new TypeError("Failed to fetch"))));
    await expect(getSummary("latest")).rejects.toMatchObject({ status: 0, code: "network_error" });
    vi.stubGlobal("fetch", vi.fn(async () => new Response("<html>Bad gateway</html>", { status: 502 })));
    await expect(getSummary("latest")).rejects.toMatchObject({ status: 502, code: "http_502" });
  });

  it("builds the records path with encoded ids and page_size capped at 200", () => {
    const path = recordsPath({ ruleId: "SQ-07a", datasetId: "sm_spend", run: "latest", page: 2, pageSize: 500, q: "$0,4" });
    expect(path).toBe("/api/dq/rules/SQ-07a/datasets/sm_spend/records?run=latest&page=2&page_size=200&q=%240%2C4");
  });
});
