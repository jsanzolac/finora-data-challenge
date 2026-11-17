import { mkdirSync } from "node:fs";
import { expect, test, type Page } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { MOCK_PASSWORD } from "../mocks/handler";

const SHOTS = "test-results/screenshots";
mkdirSync(SHOTS, { recursive: true });

const LIGHT_BG = "rgb(255, 255, 255)";
const DARK_BG = "rgb(12, 12, 14)";

async function expectNoSeriousA11yIssues(page: Page, label: string) {
  const results = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"]).analyze();
  const serious = results.violations.filter((v) => v.impact === "serious" || v.impact === "critical");
  const summary = serious.map((v) => `${v.id} (${v.impact}): ${v.nodes.length} nodes, e.g. ${v.nodes[0]?.target.join(" ")}`);
  expect(summary, `axe on ${label}`).toEqual([]);
}

async function signIn(page: Page, email = "data@finora.test") {
  await page.goto("/");
  await expect(page).toHaveURL(/\/login\/?/);
  await page.getByLabel("Work email").fill(email);
  await page.getByLabel("Password", { exact: true }).fill(MOCK_PASSWORD);
  await page.getByTestId("login-submit").click();
  await expect(page.getByTestId("scorecard")).toHaveCount(3);
}

const background = (page: Page) => page.evaluate(() => getComputedStyle(document.body).backgroundColor);

test("dark: issues by default, all rules on toggle, keyboard into a cell, records, search, paging, Escape", async ({ page }) => {
  await page.emulateMedia({ colorScheme: "dark", reducedMotion: "reduce" });
  await signIn(page);
  expect(await background(page)).toBe(DARK_BG);

  // Three cards, most compliant first, each with a plain status word. No ticker, no ring card.
  const cards = page.getByTestId("scorecard");
  await expect(cards.nth(0)).toHaveAttribute("data-rank", "1");
  const values = (await cards.getByTestId("row-compliance").allInnerTexts()).map((text) => Number.parseFloat(text));
  expect([...values].sort((a, b) => b - a)).toEqual(values);
  const words = await cards.locator("[data-status-word]").allInnerTexts();
  for (const word of words) expect(["Good", "Review", "Action needed"]).toContain(word.trim());
  await expect(page.getByTestId("ticker")).toHaveCount(0);
  await expect(page.getByTestId("rule-checks")).toHaveCount(0);
  await expect(page.getByText("silver", { exact: false })).toHaveCount(0);

  // Rules: issues only by default, worst first; the toggle shows all 27.
  const rows = page.locator('[data-testid="matrix"] tbody tr');
  const issuesButton = page.getByTestId("show-issues");
  await expect(issuesButton).toHaveAttribute("aria-pressed", "true");
  const issueCount = Number(/\((\d+)\)/.exec(await issuesButton.innerText())?.[1]);
  expect(issueCount).toBeGreaterThan(0);
  expect(issueCount).toBeLessThan(27);
  await expect(rows).toHaveCount(issueCount);
  await expect(rows.first().locator('[data-status="fail"]').first()).toBeVisible();
  await expect(page.getByText("Tap a number to see the records.")).toBeVisible();

  await page.getByTestId("user-menu").click();
  await expect(page.getByTestId("current-user")).toContainText("data@finora.test");
  await expect(page.getByTestId("current-user")).toContainText("Role: Data");
  await page.keyboard.press("Escape");
  await page.evaluate(() => (document.activeElement as HTMLElement | null)?.blur());

  await expectNoSeriousA11yIssues(page, "overview (dark)");
  await page.screenshot({ path: `${SHOTS}/overview-dark.png`, fullPage: true });
  await page.screenshot({ path: `${SHOTS}/overview.png`, fullPage: true });

  await page.getByTestId("show-all").click();
  await expect(page.getByTestId("show-all")).toHaveText("All rules (27)");
  await expect(rows).toHaveCount(27);
  await expectNoSeriousA11yIssues(page, "overview, all rules (dark)");
  await page.screenshot({ path: `${SHOTS}/overview-all-rules.png`, fullPage: true });
  await page.getByTestId("show-issues").click();
  await expect(rows).toHaveCount(issueCount);

  // Keyboard only: the table is one tab stop; walk into the Transactions column, then down to SQ-07b.
  await page.locator('[data-testid="matrix"] [data-cell-key][tabindex="0"]').focus();
  const active = () => page.evaluate(() => ({ ...(document.activeElement as HTMLElement | null)?.dataset }));
  for (let i = 0; i < 20 && (await active()).dataset !== "transactions"; i += 1) {
    const before = (await active()).cellKey;
    await page.keyboard.press("ArrowLeft");
    if ((await active()).cellKey === before) await page.keyboard.press("ArrowDown");
  }
  for (let i = 0; i < 30 && (await active()).rule !== "SQ-07b"; i += 1) await page.keyboard.press("ArrowDown");
  for (let i = 0; i < 30 && (await active()).rule !== "SQ-07b"; i += 1) await page.keyboard.press("ArrowUp");
  const focused = page.locator(":focus");
  await expect(focused).toHaveAttribute("data-rule", "SQ-07b");
  await expect(focused).toHaveAttribute("data-dataset", "transactions");
  await page.keyboard.press("Enter");

  const sheet = page.getByTestId("records-sheet");
  await expect(sheet).toBeVisible();
  await expect(page).toHaveURL(/rule=SQ-07b/);
  await expect(page).toHaveURL(/dataset=transactions/);
  await expect(sheet.getByTestId("records-summary")).toContainText(/\d+ of [\d,]+ rows fail · \d+\.\d+%/);
  await expect(sheet.getByTestId("record-row").first()).toBeVisible();
  await expect(sheet.locator('td[data-failed="true"]').first()).toBeVisible();
  await expect(sheet.getByTestId("details")).not.toHaveAttribute("open", "");
  const range = sheet.getByTestId("records-range");
  await expect(range).toContainText(/Showing 1–50 of (\d{3})/);
  const totalAll = Number(/of (\d+)/.exec(await range.innerText())?.[1]);
  expect(totalAll).toBeGreaterThan(200);

  // The reason is one tap away.
  await sheet.getByTestId("reason-toggle").first().click();
  await expect(sheet.getByTestId("record-reason").first()).toBeVisible();
  await expect(sheet.getByTestId("record-reason").first()).toContainText("NEGATIVE_AMOUNT");

  await expectNoSeriousA11yIssues(page, "records sheet (dark)");
  await page.screenshot({ path: `${SHOTS}/sheet-dark.png` });
  await page.screenshot({ path: `${SHOTS}/sheet.png` });

  // Details holds the technical part.
  await sheet.getByTestId("details").locator("summary").click();
  await expect(sheet.getByTestId("details")).toContainText("SQ-07b");
  await expect(sheet.getByTestId("details")).toContainText("Inferred");
  await expectNoSeriousA11yIssues(page, "records sheet with details (dark)");
  await sheet.getByTestId("details").locator("summary").click();

  // Server-side search behind the icon (debounced, written to the URL).
  await sheet.getByTestId("records-search-toggle").click();
  await sheet.getByTestId("records-search").fill("/2022");
  await expect(page).toHaveURL(/q=%2F2022/);
  await expect(range).toContainText("matching “/2022”");
  const totalSearch = Number(/of (\d+)/.exec(await range.innerText())?.[1]);
  expect(totalSearch).toBeGreaterThan(0);
  expect(totalSearch).toBeLessThan(totalAll);

  // Clear the search, then page forward and back.
  await sheet.getByTestId("records-search").fill("");
  await expect(range).toContainText(`Showing 1–50 of ${totalAll}`);
  await sheet.getByTestId("next-page").click();
  await expect(range).toContainText(`Showing 51–100 of ${totalAll}`);
  await expect(page).toHaveURL(/page=2/);
  await page.goBack();
  await expect(range).toContainText(`Showing 1–50 of ${totalAll}`);

  // Escape closes the sheet and focus returns to the cell that opened it.
  await sheet.getByTestId("records-search").focus();
  await page.keyboard.press("Escape");
  await expect(sheet).toBeHidden();
  await expect(page).not.toHaveURL(/rule=/);
  const back = page.locator(":focus");
  await expect(back).toHaveAttribute("data-rule", "SQ-07b");
  await expect(back).toHaveAttribute("data-dataset", "transactions");
});

test("light: overview and records sheet are readable and accessible", async ({ page }) => {
  await page.emulateMedia({ colorScheme: "light", reducedMotion: "reduce" });
  await signIn(page);
  expect(await background(page)).toBe(LIGHT_BG);
  await expectNoSeriousA11yIssues(page, "overview (light)");
  await page.screenshot({ path: `${SHOTS}/overview-light.png`, fullPage: true });

  await page.getByTestId("show-all").click();
  await expectNoSeriousA11yIssues(page, "overview, all rules (light)");
  await page.getByTestId("show-issues").click();

  await page.locator('[data-testid="matrix"] [data-cell-key="SQ-07b|transactions"]').click();
  const sheet = page.getByTestId("records-sheet");
  await expect(sheet.getByTestId("record-row").first()).toBeVisible();
  await sheet.getByTestId("reason-toggle").first().click();
  await expectNoSeriousA11yIssues(page, "records sheet (light)");
  await page.screenshot({ path: `${SHOTS}/sheet-light.png` });
  await sheet.getByTestId("details").locator("summary").click();
  await expectNoSeriousA11yIssues(page, "records sheet with details (light)");
});

test("the theme follows the OS colour scheme live, with no reload", async ({ page }) => {
  await page.emulateMedia({ colorScheme: "light", reducedMotion: "reduce" });
  await signIn(page, "finance@finora.test");
  expect(await background(page)).toBe(LIGHT_BG);
  await page.evaluate(() => ((window as unknown as Record<string, unknown>).__noReload = true));

  await page.emulateMedia({ colorScheme: "dark" });
  await expect.poll(() => background(page)).toBe(DARK_BG);
  await page.emulateMedia({ colorScheme: "light" });
  await expect.poll(() => background(page)).toBe(LIGHT_BG);

  expect(await page.evaluate(() => (window as unknown as Record<string, unknown>).__noReload)).toBe(true);
});

test("deep link opens the sheet; HR values are Restricted for non-finance roles", async ({ page }) => {
  await page.emulateMedia({ colorScheme: "dark", reducedMotion: "reduce" });
  await signIn(page, "revops@finora.test");
  await page.goto("/?rule=SB-10&dataset=sm_spend");
  const sheet = page.getByTestId("records-sheet");
  await expect(sheet.getByTestId("record-row")).toHaveCount(5);
  await expect(sheet.getByTestId("restricted-value").first()).toBeVisible();
  await sheet.getByTestId("restricted-value").first().focus();
  await expect(page.getByRole("tooltip")).toContainText("HR-sensitive values are visible to Finance only");
});

test("an expired session goes to login with a return URL", async ({ page }) => {
  await signIn(page);
  await page.goto("/?rule=SQ-02&dataset=industry");
  await expect(page.getByTestId("records-sheet").getByTestId("record-row")).toHaveCount(1);
  // The server forgets the session; the next API call answers 401.
  await page.evaluate(() => window.sessionStorage.clear());
  await page.getByTestId("page-size").selectOption("100");
  await expect(page).toHaveURL(/\/login\/\?returnTo=%2F%3Frule%3DSQ-02%26dataset%3Dindustry.*&reason=expired/);
  await expect(page.getByTestId("session-expired")).toBeVisible();
  await page.getByLabel("Work email").fill("data@finora.test");
  await page.getByLabel("Password", { exact: true }).fill(MOCK_PASSWORD);
  await page.getByTestId("login-submit").click();
  await expect(page).toHaveURL(/rule=SQ-02&dataset=industry/);
  const sheet = page.getByTestId("records-sheet");
  await expect(sheet.getByTestId("record-row")).toHaveCount(1);
  await sheet.getByTestId("reason-toggle").click();
  await expect(sheet.getByTestId("record-reason")).toContainText("EMPTY_RECORD");
});

test("first sign-in forces a password change", async ({ page }) => {
  await page.goto("/login/");
  await page.getByLabel("Work email").fill("new.analyst@finora.test");
  await page.getByLabel("Password", { exact: true }).fill(MOCK_PASSWORD);
  await page.getByTestId("login-submit").click();
  await expect(page).toHaveURL(/\/change-password\/?/);
  await page.getByLabel("Temporary password").fill(MOCK_PASSWORD);
  await page.getByLabel("New password", { exact: true }).fill("a-much-longer-passphrase");
  await page.getByLabel("Repeat the new password").fill("a-much-longer-passphrase");
  await page.getByTestId("password-submit").click();
  await expect(page.getByTestId("scorecard")).toHaveCount(3);
});

test("mobile: cards stack, rules become one list per department, the sheet is full screen", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.emulateMedia({ colorScheme: "light", reducedMotion: "reduce" });
  await signIn(page);
  await expect(page.getByTestId("matrix")).toBeHidden();
  await expect(page.getByTestId("dept-list")).toHaveCount(3);
  await expectNoSeriousA11yIssues(page, "mobile overview (light)");

  await page.emulateMedia({ colorScheme: "dark", reducedMotion: "reduce" });
  await expectNoSeriousA11yIssues(page, "mobile overview (dark)");
  await page.screenshot({ path: `${SHOTS}/overview-mobile.png`, fullPage: true });

  const cell = page.locator('[data-testid="dept-list"][data-dataset="sm_spend"] [data-cell-key="SQ-10|sm_spend"]');
  await cell.click();
  const sheet = page.getByTestId("records-sheet");
  await expect(sheet.getByTestId("record-row")).toHaveCount(2);
  const box = await sheet.boundingBox();
  expect(box?.width).toBe(390);
  await expectNoSeriousA11yIssues(page, "mobile sheet (dark)");
  await page.screenshot({ path: `${SHOTS}/sheet-mobile.png` });
  await sheet.getByTestId("close-sheet").click();
  await expect(cell).toBeFocused();
});
