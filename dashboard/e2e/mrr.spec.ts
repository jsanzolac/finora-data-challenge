import { mkdirSync } from "node:fs";
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

async function openMrr(page: Page, email = "finance@finora.test", query = "") {
  await page.goto("/login/");
  await page.getByLabel("Work email").fill(email);
  await page.getByLabel("Password", { exact: true }).fill(MOCK_PASSWORD);
  await page.getByTestId("login-submit").click();
  await expect(page.getByTestId("scorecard")).toHaveCount(3);
  if (query) await page.goto(`/mrr/${query}`);
  else await page.getByTestId("nav-mrr").click();
  await expect(page.getByTestId("nav-mrr")).toHaveAttribute("aria-current", "page");
  await expect(page.getByTestId("driver-cards")).toBeVisible();
}

async function openAllDetails(page: Page) {
  for (const id of ["why-details", "bridge-details", "leakage-details", "movers-details", "mrr-monthly-details"]) {
    await page.getByTestId(id).locator("summary").first().click();
  }
}

test("MRR: why it changed, the bridge, leakage not available, light and dark", async ({ page }) => {
  await page.emulateMedia({ colorScheme: "light", reducedMotion: "reduce" });
  await openMrr(page);

  // Last 12 months by default; the hero and the three driver cards.
  await expect(page.getByTestId("mrr-period-select")).toContainText("Last 12 months · Nov 2023 – Oct 2024");
  await expect(page.getByTestId("mrr-hero")).toContainText("MRR went from");
  await expect(page.getByTestId("driver-cards").locator("li")).toHaveCount(3);
  await expect(page.getByTestId("driver-pricing")).toContainText("Discounts not available until billing data");
  await expect(page.getByTestId("provisional")).toContainText("Sep 2024 – Oct 2024");

  // The bridge renders the API's steps grouped by driver; discounts are "Not available", never 0.
  await expect(page.getByTestId("bridge-group")).toHaveCount(4);
  await expect(page.locator('[data-testid="bridge-group"][data-driver="discount"]').getByTestId("bridge-unavailable")).toContainText(
    "Not available until billing data",
  );
  // §6 lines: 8 behaviour, 2 pricing (list price changes "Not available"), 1 timing; discounts as one row.
  await expect(page.getByTestId("bridge-step")).toHaveCount(11);
  await expect(page.locator('[data-testid="bridge-step"][data-step="list_price_change"]')).toContainText("Not available");
  await expect(page.getByTestId("leakage-value")).toHaveText("—");
  await expect(page.getByTestId("leakage-status")).toContainText("Not available until billing data");
  await expect(page.getByTestId("trend-legend").locator("li")).toHaveCount(3);
  await expect(page.getByText("CAC")).toHaveCount(0);

  await expectNoSeriousA11yIssues(page, "MRR (light)");
  await page.screenshot({ path: `${SHOTS}/mrr-desktop-light.png`, fullPage: true });

  // Details: the explainer, the exact bridge table, top movers from the API, monthly data.
  await openAllDetails(page);
  await expect(page.getByTestId("why-details")).toContainText(
    "Behaviour moves list MRR at a constant price, pricing moves the price book, commercial decisions move discounts, and timing moves only cash.",
  );
  await expect(page.getByTestId("why-details")).toContainText("Based on payments (proxy until billing data)");
  await expect(page.getByTestId("cfo-cases").locator("tbody tr")).toHaveCount(6);
  await expect(page.getByTestId("why-details")).toContainText("Currency not stated");
  await expect(page.getByTestId("bridge-table")).toContainText("not available");
  await expect(page.getByTestId("mover-row")).toHaveCount(20);
  await expect(page.getByTestId("movers-range")).toContainText("movements, Nov 2023 – Oct 2024, largest first");
  await page.getByTestId("movers-next").click();
  await expect(page.getByTestId("movers-page")).toContainText("Page 2 of");
  await page.getByTestId("movers-step").click();
  await page.getByRole("option", { name: "Churn", exact: true }).click();
  await expect(page.getByTestId("movers-page")).toContainText("Page 1 of");
  await expect(page.getByTestId("mover-row").first()).toContainText("Churn");
  await expect(page.getByTestId("mrr-monthly-table").locator("tbody tr")).toHaveCount(33);

  await expectNoSeriousA11yIssues(page, "MRR, details open (light)");
  await page.screenshot({ path: `${SHOTS}/mrr-details-light.png`, fullPage: true });
  await page.emulateMedia({ colorScheme: "dark", reducedMotion: "reduce" });
  await expectNoSeriousA11yIssues(page, "MRR, details open (dark)");
  await page.screenshot({ path: `${SHOTS}/mrr-details-dark.png`, fullPage: true });

  // A deep link to one year; the trend reads a month from the keyboard.
  // Full period: the gold spec's figures (§6.6), rounded for display.
  await page.goto("/mrr/?period=full");
  await expect(page.getByTestId("mrr-hero")).toContainText("MRR went from 35M to 96.4M: +61.4M");
  await expect(page.getByTestId("driver-behaviour").getByTestId("driver-value")).toHaveText("+63.2M");
  await expect(page.getByTestId("driver-pricing").getByTestId("driver-value")).toHaveText("+574K");
  await expect(page.getByTestId("driver-timing").getByTestId("driver-value")).toHaveText("−2.4M");

  await page.goto("/mrr/?period=2023");
  await expect(page.getByTestId("mrr-period-select")).toContainText("2023 · Jan 2023 – Dec 2023");
  await expect(page.getByTestId("provisional")).toHaveCount(0);
  await page.evaluate(() => (document.activeElement as HTMLElement | null)?.blur());
  await expectNoSeriousA11yIssues(page, "MRR 2023 (dark)");
  await page.screenshot({ path: `${SHOTS}/mrr-desktop-dark.png`, fullPage: true });
  await page.getByTestId("trend-charts").focus();
  await page.keyboard.press("End");
  await expect(page.getByTestId("trend-tooltip")).toContainText("Oct 2024");
});

test("MRR: period select, no gold run yet, and mobile", async ({ page }) => {
  await page.emulateMedia({ colorScheme: "dark", reducedMotion: "reduce" });
  await openMrr(page, "data@finora.test");
  await page.getByTestId("mrr-period-select").click();
  await page.getByRole("option", { name: /^Q2 2024/ }).click();
  await expect(page).toHaveURL(/period=2024-Q2/);
  await expect(page.getByTestId("mrr-hero")).toContainText("Apr 2024 – Jun 2024");

  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/mrr/");
  await expect(page.getByTestId("driver-cards")).toBeVisible();
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(0);
  await expectNoSeriousA11yIssues(page, "mobile MRR (dark)");
  await page.screenshot({ path: `${SHOTS}/mrr-mobile-dark.png`, fullPage: true });
  await page.emulateMedia({ colorScheme: "light", reducedMotion: "reduce" });
  await expectNoSeriousA11yIssues(page, "mobile MRR (light)");
  await page.screenshot({ path: `${SHOTS}/mrr-mobile-light.png`, fullPage: true });

  await page.evaluate(() => window.sessionStorage.setItem("mrr_mock_no_gold_run", "1"));
  await page.goto("/mrr/");
  await expect(page.getByText("No MRR data yet")).toBeVisible();
});
