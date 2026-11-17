import { mkdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { expect, test, type Page } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { MOCK_PASSWORD } from "../mocks/handler";

const SHOTS = "test-results/screenshots";
mkdirSync(SHOTS, { recursive: true });

async function expectNoSeriousA11yIssues(page: Page, label: string) {
  const results = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"]).analyze();
  const serious = results.violations.filter((v) => v.impact === "serious" || v.impact === "critical");
  const summary = serious.map((v) => `${v.id} (${v.impact}): ${v.nodes.length} nodes, e.g. ${v.nodes[0]?.target.join(" ")}`);
  expect(summary, `axe on ${label}`).toEqual([]);
}

async function signIn(page: Page, email = "finance@finora.test") {
  await page.goto("/login/");
  await page.getByLabel("Work email").fill(email);
  await page.getByLabel("Password", { exact: true }).fill(MOCK_PASSWORD);
  await page.getByTestId("login-submit").click();
  await expect(page.getByTestId("scorecard")).toHaveCount(3);
}

const voiceState = (page: Page) => page.getByTestId("voice-control").getAttribute("data-state");

// A fake microphone for the whole file (headless Chromium has none).
test.use({ launchOptions: { args: ["--use-fake-ui-for-media-stream", "--use-fake-device-for-media-stream"] } });

test.describe("voice agent, microphone allowed", () => {
  test.use({ permissions: ["microphone"] });

  test("mock session: show_chart opens the panel, highlight_kpi, go_to_page keeps the session", async ({ page }) => {
    await page.emulateMedia({ colorScheme: "light", reducedMotion: "reduce" });
    await signIn(page);
    // The control is on every page; start from Acquisition.
    await expect(page.getByTestId("voice-button")).toBeVisible();
    await page.getByTestId("nav-acq").click();
    await expect(page.getByTestId("funnel-stage")).toHaveCount(7, { timeout: 15_000 });
    await expect(page.getByTestId("voice-text")).toHaveText("Hablar con el analista");

    await page.getByTestId("voice-button").click();
    await expect.poll(() => voiceState(page)).toMatch(/listening|speaking/);
    await expect(page.getByTestId("voice-captions")).toContainText("Hola, estoy cargando los números de hoy.");

    // show_chart: the panel opens with the result fetched with the user's session.
    const panel = page.getByTestId("agent-panel");
    await expect(panel).toBeVisible();
    await expect(panel.getByRole("heading", { name: "Gráfico del analista" })).toBeVisible();
    await expect(page.getByTestId("agent-chart-title")).toContainText("por industria");
    await expect(page.getByTestId("agent-table")).toContainText("Retail");

    // highlight_kpi: the card scrolls into view and is highlighted briefly.
    await expect(page.locator('[data-kpi-id="acq.lost.starting_revenue"][data-highlighted="true"]')).toBeVisible();
    await expect(page.getByTestId("agent-caveats")).toContainText("Evidencia: observado");
    await expectNoSeriousA11yIssues(page, "voice panel and highlight (light)");
    await page.screenshot({ path: `${SHOTS}/voice-panel-light.png` });

    // go_to_page: client-side navigation; the session and the panel stay.
    await expect(page).toHaveURL(/\/mrr\/?$/, { timeout: 10_000 });
    await expect(page.getByTestId("driver-cards")).toBeVisible();
    await expect(page.getByTestId("voice-captions")).toContainText("Aquí está el MRR");
    await expect.poll(() => voiceState(page)).toMatch(/listening|speaking/);
    await expect(panel).toBeVisible();

    await page.emulateMedia({ colorScheme: "dark", reducedMotion: "reduce" });
    await expectNoSeriousA11yIssues(page, "voice on MRR (dark)");
    await page.screenshot({ path: `${SHOTS}/voice-panel-dark.png` });

    // Captions toggle, close the panel, end the conversation.
    await page.getByTestId("captions-toggle").click();
    await expect(page.getByTestId("voice-captions")).toBeHidden();
    await page.getByTestId("agent-panel-close").click();
    await expect(panel).toBeHidden();
    await page.getByTestId("voice-button").click();
    await expect.poll(() => voiceState(page)).toBe("ended");
    await expect(page.getByTestId("voice-text")).toHaveText("Conversación terminada");
  });

  test("the voice is unavailable (503) and says so in Spanish", async ({ page }) => {
    await page.emulateMedia({ colorScheme: "dark", reducedMotion: "reduce" });
    await signIn(page, "data@finora.test");
    await page.evaluate(() => window.sessionStorage.setItem("voice_mock_unavailable", "1"));
    await page.getByTestId("voice-button").click();
    await expect.poll(() => voiceState(page)).toBe("unavailable");
    await expect(page.getByTestId("voice-text")).toHaveText("La voz no está disponible ahora");
    await expect(page.getByTestId("voice-status")).toContainText("La voz no está disponible ahora");
    await expectNoSeriousA11yIssues(page, "voice unavailable (dark)");
  });

  test("mobile: the mic is an icon with a Spanish name, the panel is a bottom sheet", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.emulateMedia({ colorScheme: "light", reducedMotion: "reduce" });
    await signIn(page, "revops@finora.test");
    await page.goto("/acquisition/");
    await expect(page.getByTestId("funnel-stage")).toHaveCount(7, { timeout: 15_000 });
    await expect(page.getByRole("button", { name: "Hablar con el analista" })).toBeVisible();
    await page.getByTestId("voice-button").click();
    await expect(page.getByTestId("agent-panel")).toBeVisible({ timeout: 10_000 });
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    expect(overflow).toBeLessThanOrEqual(0);
    await expectNoSeriousA11yIssues(page, "voice on mobile (light)");
    await page.screenshot({ path: `${SHOTS}/voice-mobile-light.png` });
  });
});

test.describe("voice agent, microphone not yet allowed", () => {
  test("explains why it needs the microphone before asking", async ({ page }) => {
    await page.emulateMedia({ colorScheme: "light", reducedMotion: "reduce" });
    await signIn(page);
    await page.getByTestId("voice-button").click();
    const dialog = page.getByTestId("mic-dialog");
    await expect(dialog).toBeVisible();
    await expect(dialog).toContainText("Para hablar con el analista necesitamos tu micrófono");
    await expectNoSeriousA11yIssues(page, "microphone explanation (light)");
    await page.emulateMedia({ colorScheme: "dark", reducedMotion: "reduce" });
    await expectNoSeriousA11yIssues(page, "microphone explanation (dark)");
    await page.screenshot({ path: `${SHOTS}/voice-permission-dark.png` });
    await dialog.getByRole("button", { name: "Cancelar" }).click();
    await expect(dialog).toBeHidden();
    await expect.poll(() => voiceState(page)).toBe("idle");
  });
});

/**
 * docs/semantic_layer.md §1.6 (catalog sl-2026-11-17): every dashboard-card kpi_id resolves to
 * exactly one element on its page (the visible one, or one inside a Details panel that
 * highlight_kpi opens). Parameterized ids are expanded with real values.
 */
function catalogKpis(): { id: string; page: "dq" | "acquisition" | "mrr" }[] {
  const doc = readFileSync(join(__dirname, "..", "..", "docs", "semantic_layer.md"), "utf8");
  const section = doc.slice(doc.indexOf("### 1.6"), doc.indexOf("**Catalog size:**"));
  const expand: Record<string, string[]> = {
    "<dataset_id>": ["transactions", "industry", "sm_spend"],
    "<rule_id>.<dataset_id>": ["SQ-07b.transactions"],
    "<line>": ["new", "churn", "inferred_price_step", "first_payment_multiple"],
  };
  const out: { id: string; page: "dq" | "acquisition" | "mrr" }[] = [];
  for (const line of section.split("\n").filter((row) => row.startsWith("| `"))) {
    const cells = line.split(/(?<!\\)\|/).map((cell) => cell.trim());
    const page = cells[2] as "dq" | "acquisition" | "mrr";
    for (const raw of [...(cells[1] ?? "").matchAll(/`([^`]+)`/g)].map((match) => match[1]!.replace(/\\\|/g, "|"))) {
      const options = /<([a-z]+(?:\|[a-z]+)+)>/.exec(raw);
      if (options) {
        for (const option of options[1]!.split("|")) out.push({ id: raw.replace(options[0], option), page });
        continue;
      }
      const key = Object.keys(expand)
        .sort((a, b) => b.length - a.length)
        .find((token) => raw.endsWith(token));
      if (key) for (const value of expand[key]!) out.push({ id: raw.replace(key, value), page });
      else out.push({ id: raw, page });
    }
  }
  return out;
}

test("every catalog kpi_id resolves to exactly one card on its page", async ({ page }) => {
  const kpis = catalogKpis();
  // 28 fixed ids + 4 parameterized families (expanded here with real values).
  expect(new Set(kpis.map((kpi) => kpi.id.split(".").slice(0, 3).join("."))).size).toBeGreaterThan(20);
  await page.emulateMedia({ colorScheme: "light", reducedMotion: "reduce" });
  await signIn(page);
  const pages = { dq: "/", acquisition: "/acquisition/", mrr: "/mrr/" } as const;
  const ready = { dq: "scorecard", acquisition: "funnel-stage", mrr: "driver-cards" } as const;
  const misses: string[] = [];
  for (const [pageId, href] of Object.entries(pages) as [keyof typeof pages, string][]) {
    await page.goto(href);
    await expect(page.getByTestId(ready[pageId]).first()).toBeVisible({ timeout: 15_000 });
    for (const kpi of kpis.filter((entry) => entry.page === pageId)) {
      const count = await page.evaluate(
        (id) =>
          [...document.querySelectorAll(`[data-kpi-id="${CSS.escape(id)}"]`)].filter(
            (element) => element.getClientRects().length > 0 || element.closest("details"),
          ).length,
        kpi.id,
      );
      if (count !== 1) misses.push(`${kpi.id} on ${pageId}: ${count}`);
    }
  }
  expect(misses).toEqual([]);
  expect(kpis.length).toBeGreaterThanOrEqual(32);
});

/** The production CSP, read from the CDK stack that serves the site (infra/stacks/web.py). */
function productionCsp(): string {
  const source = readFileSync(join(__dirname, "..", "..", "infra", "stacks", "web.py"), "utf8");
  const block = /^CSP = \(([\s\S]*?)\)\s*$/m.exec(source)?.[1] ?? "";
  return [...block.matchAll(/"([^"]*)"/g)].map((match) => match[1]).join("");
}

test.describe("voice under the production CSP", () => {
  test.use({ permissions: ["microphone"] });

  test("the real SDK path and the scripted session make no request outside the CSP", async ({ page }) => {
    const csp = productionCsp();
    expect(csp).toContain("connect-src 'self' wss://api.elevenlabs.io;");
    expect(csp).not.toMatch(/blob:[^;]*;?\s*(?=.*script-src)|script-src[^;]*(blob:|data:|https:)/);

    // Every response carries the production CSP, as CloudFront serves it.
    await page.route("**/*", async (route) => {
      const response = await route.fetch();
      await route.fulfill({ response, headers: { ...response.headers(), "content-security-policy": csp } });
    });
    await page.addInitScript(() => {
      const sink: string[] = [];
      (window as unknown as { __csp: string[] }).__csp = sink;
      // Count script blobs: the SDK falls back to blob:/data: worklets only when no self-hosted path is given.
      const blobs: string[] = [];
      (window as unknown as { __scriptBlobs: string[] }).__scriptBlobs = blobs;
      const create = URL.createObjectURL.bind(URL);
      URL.createObjectURL = (object: Blob | MediaSource) => {
        if (object instanceof Blob && /javascript/.test(object.type)) blobs.push(object.type);
        return create(object);
      };
      document.addEventListener("securitypolicyviolation", (event) => sink.push(`${event.violatedDirective} ${event.blockedURI}`));
    });
    const consoleCsp: string[] = [];
    page.on("console", (message) => {
      if (/Content Security Policy|Refused to/i.test(message.text())) consoleCsp.push(message.text());
    });
    // A stand-in for the ElevenLabs server: the page's socket never reaches the internet.
    let clientInit = false;
    await page.routeWebSocket(/^wss:\/\/api\.elevenlabs\.io\/v1\/convai\//, (ws) => {
      ws.onMessage((message) => {
        if (String(message).includes("conversation_initiation_client_data")) {
          clientInit = true;
          ws.send(
            JSON.stringify({
              type: "conversation_initiation_metadata",
              conversation_initiation_metadata_event: {
                conversation_id: "conv_mock",
                agent_output_audio_format: "pcm_16000",
                user_input_audio_format: "pcm_16000",
              },
            }),
          );
        }
      });
    });
    const violations = () => page.evaluate(() => (window as unknown as { __csp: string[] }).__csp);

    await page.emulateMedia({ colorScheme: "light", reducedMotion: "reduce" });
    await signIn(page);
    await page.goto("/acquisition/");
    await expect(page.getByTestId("funnel-stage")).toHaveCount(7, { timeout: 15_000 });

    // 1) The real ElevenLabs SDK: lazy chunk, self-hosted worklets, websocket to the signed URL.
    await page.evaluate(() => window.sessionStorage.setItem("voice_mock_sdk", "1"));
    await page.getByTestId("voice-button").click();
    await expect.poll(() => voiceState(page), { timeout: 15_000 }).toBe("listening");
    expect(clientInit).toBe(true);
    // "Listening" means the SDK's input and output worklets loaded (it sets them up before connecting),
    // and none came from a blob: script: they are the self-hosted /voice/ files.
    expect(await page.evaluate(() => (window as unknown as { __scriptBlobs: string[] }).__scriptBlobs)).toEqual([]);
    expect(await violations()).toEqual([]);
    await page.getByTestId("voice-button").click();
    await expect.poll(() => voiceState(page)).toBe("ended");

    // 2) The scripted session: the panel, captions, highlight and client-side navigation.
    await page.evaluate(() => window.sessionStorage.removeItem("voice_mock_sdk"));
    await page.getByTestId("voice-button").click();
    await expect(page.getByTestId("agent-panel")).toBeVisible({ timeout: 10_000 });
    await expect(page).toHaveURL(/\/mrr\/?$/, { timeout: 15_000 });
    expect(await violations()).toEqual([]);
    expect(consoleCsp).toEqual([]);

    // The listener works: a connection outside the CSP is reported (and blocked by the browser).
    await page.evaluate(() => {
      try {
        new WebSocket("wss://blocked.example.invalid/");
      } catch {
        /* blocked */
      }
    });
    await expect.poll(async () => (await violations()).join(" ")).toContain("connect-src");
  });
});
