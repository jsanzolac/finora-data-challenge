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

/** Sign in on the DQ overview, then go to Acquisition through the header. */
async function openAcquisition(page: Page, email: string, query = "") {
  await page.goto("/login/");
  await page.getByLabel("Work email").fill(email);
  await page.getByLabel("Password", { exact: true }).fill(MOCK_PASSWORD);
  await page.getByTestId("login-submit").click();
  await expect(page.getByTestId("scorecard")).toHaveCount(3);
  if (query) {
    await page.goto(`/acquisition/${query}`);
  } else {
    await page.getByTestId("nav-acq").click();
    await expect(page).toHaveURL(/\/acquisition\/?$/);
  }
  await expect(page.getByTestId("nav-acq")).toHaveAttribute("aria-current", "page");
  // The scenarios come from Athena (2-5 s): the funnel shows a loading state first.
  await expect(page.getByTestId("funnel-stage")).toHaveCount(7, { timeout: 15_000 });
}

const stage = (page: Page, code: string) => page.locator(`[data-testid="funnel-stage"][data-stage="${code}"]`);

async function openAllDetails(page: Page) {
  for (const id of ["levers-details", "lost-details", "funnel-details", "time-details", "signals-details", "industries-details", "monthly-details"]) {
    await page.getByTestId(id).locator("summary").click();
  }
  await page.getByTestId("definition-toggle").click();
}

test("finance: the base funnel, editing a rate, impact, saving a scenario, light and dark", async ({ page }) => {
  await page.emulateMedia({ colorScheme: "light", reducedMotion: "reduce" });
  await openAcquisition(page, "finance@finora.test");

  // Base funnel, full period: spec §12.5 to display precision.
  await expect(stage(page, "NEW").getByTestId("stage-count")).toContainText("58,928.6");
  await expect(stage(page, "NEW").getByTestId("stage-cost")).toContainText("128,661");
  await expect(stage(page, "WON").getByTestId("stage-count")).toContainText("1,584");
  await expect(stage(page, "WON").getByTestId("stage-cost")).toContainText("4,786,490");
  await expect(stage(page, "WON").getByTestId("stage-basis")).toHaveText("Real");
  await expect(stage(page, "NEW").getByTestId("stage-basis")).toHaveText("Estimated");
  // Decision first: the §16.6 headline, the planner at rest (baseline from Jun 2023), the ranking.
  await expect(page.getByTestId("verdict")).toHaveText(
    "Spend per month fell 39% from June 2023 while new customers per month rose 52%: these files show no measurable link from spend to new customers. New MRR per month rose only 16%, because each new customer starts 24% smaller (55,768 → 42,551 a month), in every industry except Healthcare, and new customers keep paying as long as before. Plan with ticket size and industry mix (observed); treat conversion rates as assumptions; test spend before relying on it.",
  );
  await expect(page.getByTestId("verdict-timing")).toContainText("already lower in the Jan–Jun 2023 cohort (45,109 against 61,598 in Jul–Dec 2022)");
  await expect(page.getByTestId("planned-won").getByTestId("planned-value")).toHaveText("57.5");
  await expect(page.getByTestId("planned-mrr").getByTestId("planned-value")).toHaveText("2.45M");
  await expect(page.getByTestId("planned-payback").getByTestId("planned-value")).toHaveText("71.6 mo");
  await expect(page.getByTestId("ranked-lever")).toHaveCount(4);
  expect(await page.getByTestId("ranked-lever").evaluateAll((rows) => rows.map((row) => row.getAttribute("data-lever")))).toEqual([
    "ticket",
    "conversion",
    "mix",
    "spend",
  ]);
  await expect(page.getByTestId("lost-customers")).toContainText("+52%");
  await expect(page.getByTestId("lost-revenue")).toContainText("−24%");
  await expect(page.getByTestId("ticket-trend-line")).toContainText("It stepped down between H2 2022 and H1 2023");
  await expect(page.getByTestId("within-share")).toContainText("About 96% of the drop is inside each industry");
  await expect(page.getByTestId("dumbbell-row").first()).toHaveAttribute("data-industry", "RETAIL");
  await expect(page.getByTestId("cohort-headline")).toContainText("Paying at month 6: 91–95% in every complete cohort. Churn didn't rise.");
  // No label ties the ticket to the spend periods; the signals headline left the main surface.
  await expect(page.getByText(/spend (change|regime|cut) (lowered|reduced|caused)/i)).toHaveCount(0);
  await expect(page.getByText("No usable relationship between spend and new customers")).toHaveCount(0);
  await expect(page.getByTestId("signals-line")).toBeHidden();
  await expect(page.getByText("CAC")).toHaveCount(0);

  await expectNoSeriousA11yIssues(page, "acquisition (light)");
  await page.screenshot({ path: `${SHOTS}/acq-desktop-light.png`, fullPage: true });

  // Edit SQL -> Demo to 80% with the keyboard: the funnel recomputes at once (§12.6).
  const sql = page.getByTestId("rate-SQL");
  await sql.focus();
  for (let i = 0; i < 10; i += 1) await page.keyboard.press("ArrowUp");
  await expect(sql).toHaveValue("80");
  await expect(page.getByTestId("modified")).toBeVisible();
  await expect(stage(page, "NEW").getByTestId("stage-count")).toContainText("51,562.5");
  await expect(stage(page, "WON").getByTestId("stage-count")).toContainText("1,584");
  // The funnel's rates are the planner's volume lever: 8/7 more new customers (§12.6: +14.285714%).
  await expect(page.getByTestId("planned-won").getByTestId("planned-value")).toHaveText("65.7");
  await expect(page.getByTestId("conversion-impact")).toContainText("+350K");

  // An invalid value shows an error and blocks saving; Reset puts everything back.
  await sql.fill("120");
  await expect(page.getByText("The rate can't be above 100%.")).toBeVisible();
  await expect(page.getByTestId("save-scenario")).toBeDisabled();
  await page.getByTestId("reset-rates").click();
  await expect(page.getByTestId("modified")).toHaveCount(0);
  await expect(stage(page, "NEW").getByTestId("stage-count")).toContainText("58,928.6");

  await sql.fill("80");
  await expect(stage(page, "NEW").getByTestId("stage-count")).toContainText("51,562.5");
  await page.screenshot({ path: `${SHOTS}/acq-edited-light.png` });

  // Save as a new scenario: the reason is required, then it saves and becomes the selected scenario.
  await page.getByTestId("save-scenario").click();
  const dialog = page.getByTestId("save-dialog");
  await expect(dialog).toBeVisible();
  await dialog.getByTestId("save-label").fill("Demos booked faster");
  await expect(dialog.getByTestId("save-id")).toHaveValue("demos_booked_faster");
  await dialog.getByTestId("save-submit").click();
  await expect(dialog.getByText("Say why these rates.")).toBeVisible();
  await expectNoSeriousA11yIssues(page, "save dialog with an error (light)");
  await dialog.getByTestId("save-reason").fill("Sales ops expects faster demo booking");
  await dialog.getByTestId("save-submit").click();
  await expect(dialog).toBeHidden({ timeout: 10_000 });
  await expect(page).toHaveURL(/scenario=demos_booked_faster/);
  await expect(page.getByTestId("scenario-select")).toContainText("Demos booked faster");
  await expect(page.getByTestId("modified")).toHaveCount(0);
  await expect(stage(page, "NEW").getByTestId("stage-count")).toContainText("51,562.5");
  await expect(page.getByTestId("planned-won").getByTestId("planned-value")).toHaveText("65.7");

  // Dark: same page, same checks.
  await page.emulateMedia({ colorScheme: "dark", reducedMotion: "reduce" });
  await page.goto("/acquisition/");
  await expect(page.getByTestId("funnel-stage")).toHaveCount(7, { timeout: 15_000 });
  await page.evaluate(() => (document.activeElement as HTMLElement | null)?.blur());
  await expectNoSeriousA11yIssues(page, "acquisition (dark)");
  await page.screenshot({ path: `${SHOTS}/acq-desktop-dark.png`, fullPage: true });

  // Every Details panel open, industry split on: still accessible in dark and light.
  await page.getByTestId("split-industry").click();
  await expect(page.getByTestId("industry-legend")).toBeVisible();
  await openAllDetails(page);
  // The split also works without the customers probably already active (v1.1 won_by_industry_new_logo).
  // The radio is controlled by the URL, which updates a tick after the click.
  await page.getByTestId("definition-new_logo").click();
  await expect(page).toHaveURL(/def=new_logo/);
  await expect(page.getByTestId("definition-new_logo")).toBeChecked();
  await expect(page.getByTestId("split-industry")).toBeEnabled();
  await expect(page.getByTestId("industry-legend")).toBeVisible();
  await expect(stage(page, "WON").getByTestId("stage-count")).toContainText("1,541");
  await page.getByTestId("definition-user").click();
  await expect(page).not.toHaveURL(/def=new_logo/);
  await expect(page.getByTestId("share-paid")).toContainText("Restaurants: new 89.9%, earlier 88.9%");
  await expect(page.getByTestId("levers-details")).toContainText("currency not stated");
  await expect(page.getByTestId("invalid-scenarios")).toContainText("GR-03");
  await expect(page.getByTestId("signals-line")).toContainText(
    "These files show no measurable link from spend to new customers: 30 of 44 tests look related, but 3 of 44 once the trend is removed (about 2 by chance). Test spend with a holdout",
  );
  await expect(page.getByTestId("spend-guidance")).toContainText("hold out paid media in some regions, audiences or channels for 8–12 weeks");
  await expect(page.getByTestId("sensitivity-row")).toHaveCount(6);
  await expect(page.getByTestId("signals-grid").locator('[data-signal="true"]').first()).toBeVisible();
  await page.getByTestId("method-diff").click();
  await expect(page.getByTestId("signals-grid").locator('[data-signal="true"]')).toHaveCount(3);
  await expect(page.getByTestId("restricted-value")).toHaveCount(0);
  await expectNoSeriousA11yIssues(page, "acquisition, details open (dark)");
  await page.screenshot({ path: `${SHOTS}/acq-details-dark.png`, fullPage: true });
  await page.emulateMedia({ colorScheme: "light", reducedMotion: "reduce" });
  await expectNoSeriousA11yIssues(page, "acquisition, details open (light)");
  await page.screenshot({ path: `${SHOTS}/acq-details-light.png`, fullPage: true });

  // The charts read out a month from the keyboard.
  await page.getByTestId("time-charts").focus();
  await page.keyboard.press("End");
  await expect(page.getByTestId("time-tooltip")).toContainText("Oct 2024");
});

test("data role: tries rates locally but can't save; HR columns are Restricted", async ({ page }) => {
  await page.emulateMedia({ colorScheme: "dark", reducedMotion: "reduce" });
  await openAcquisition(page, "data@finora.test");
  await expect(page.getByTestId("funnel").getByRole("spinbutton")).toHaveCount(6);
  await expect(page.getByTestId("not-saved-note")).toHaveCount(0);

  // Everyone can modify the rates; saving is what is restricted.
  await page.getByTestId("rate-SQL").fill("80");
  await expect(stage(page, "NEW").getByTestId("stage-count")).toContainText("51,562.5");
  await expect(page.getByTestId("planned-won").getByTestId("planned-value")).toHaveText("65.7");
  await expect(page.getByTestId("modified")).toBeVisible();
  await expect(page.getByTestId("not-saved-note")).toContainText("Finance and RevOps can save rates");
  await expect(page.getByTestId("save-scenario")).toHaveCount(0);
  await expectNoSeriousA11yIssues(page, "acquisition, data role editing (dark)");
  await page.getByTestId("reset-rates").click();
  await expect(page.getByTestId("rate-SQL")).toHaveValue("70");
  await expect(page.getByTestId("modified")).toHaveCount(0);

  // Picking another saved scenario still shows its effect against Base.
  await page.getByTestId("scenario-select").click();
  await page.getByRole("option", { name: "SQL to Demo at 80%" }).click();
  await expect(page).toHaveURL(/scenario=sql_demo_080/);
  await expect(page.getByTestId("planned-won").getByTestId("planned-value")).toHaveText("65.7");
  await page.getByTestId("scenario-select").click();
  await expect(page.getByRole("option", { name: /Q4 plan \(typo\)/ })).toHaveAttribute("aria-disabled", "true");
  await page.keyboard.press("Escape");

  await page.getByTestId("monthly-details").locator("summary").click();
  await expect(page.getByTestId("monthly-table").getByTestId("restricted-value")).toHaveCount(33 * 3);
  await expectNoSeriousA11yIssues(page, "acquisition, data role (dark)");
});

test("revops: can edit, but HR columns are Restricted; editing Base needs a confirmation", async ({ page }) => {
  await page.emulateMedia({ colorScheme: "light", reducedMotion: "reduce" });
  await openAcquisition(page, "revops@finora.test");
  await page.getByTestId("monthly-details").locator("summary").click();
  await expect(page.getByTestId("monthly-table").getByTestId("restricted-value").first()).toBeVisible();

  await page.getByTestId("rate-PROPOSAL").fill("42");
  await page.getByTestId("save-scenario").click();
  const dialog = page.getByTestId("save-dialog");
  await dialog.getByTestId("save-target-update").check();
  await expect(dialog.getByTestId("base-warning")).toContainText("This changes the base assumptions for everyone.");
  await dialog.getByTestId("save-reason").fill("Q4 review");
  await dialog.getByTestId("save-submit").click();
  await expect(dialog.getByText("Confirm that you want to change Base for everyone.")).toBeVisible();
  await dialog.getByTestId("confirm-base").check();
  await dialog.getByTestId("save-submit").click();
  await expect(dialog).toBeHidden({ timeout: 10_000 });
  await expect(page.getByTestId("rate-PROPOSAL")).toHaveValue("42");
  await expect(page.getByTestId("modified")).toHaveCount(0);
});

test("deep links: period and scenario from the URL, an invalid scenario falls back to Base, cost unavailable", async ({ page }) => {
  await page.emulateMedia({ colorScheme: "light", reducedMotion: "reduce" });
  await openAcquisition(page, "finance@finora.test", "?period=2024-10&def=new_logo");
  await expect(page.getByTestId("period-select")).toContainText("Oct 2024");
  await expect(stage(page, "NEW").getByTestId("stage-count")).toContainText("1,860.1");
  await expect(stage(page, "NEW").getByTestId("stage-cost")).toContainText("107,520");
  await expect(page.getByTestId("definition-new_logo")).toBeChecked();

  await page.goto("/acquisition/?scenario=q4_typo");
  await expect(page.getByTestId("funnel-stage")).toHaveCount(7, { timeout: 15_000 });
  await expect(page.getByTestId("scenario-fallback")).toContainText("can't be used");
  await expect(page.getByTestId("scenario-select")).toContainText("Base");

  // A planted run has a month past the data watermark with no spend.
  await page.goto("/acquisition/?run=r20261117T120000Z&period=2024-11");
  await expect(page.getByTestId("funnel-stage")).toHaveCount(7, { timeout: 15_000 });
  await expect(page.getByTestId("cost-unavailable")).toContainText("Spend is missing");
  await expect(stage(page, "NEW").getByTestId("stage-cost")).toContainText("—");
  await page.goto("/acquisition/?run=r20261117T120000Z");
  await expect(page.getByTestId("funnel-stage")).toHaveCount(7, { timeout: 15_000 });
  await expect(page.getByTestId("cost-unavailable")).toHaveCount(0);
  await expect(stage(page, "WON").getByTestId("stage-count")).toContainText("1,584");

  // 404 unknown_run: say so and offer the latest run.
  await page.goto("/acquisition/?run=r19990101T000000Z");
  await expect(page.getByText("No data for this run")).toBeVisible();
  await page.getByRole("button", { name: "Go to the latest run" }).click();
  await expect(page.getByTestId("funnel-stage")).toHaveCount(7, { timeout: 15_000 });

  // 404 no_gold_run (before the first gold publish): "No acquisition data yet".
  await page.evaluate(() => window.sessionStorage.setItem("acq_mock_no_gold_run", "1"));
  await page.goto("/acquisition/");
  await expect(page.getByText("No acquisition data yet")).toBeVisible();
  await expectNoSeriousA11yIssues(page, "acquisition, no gold run (light)");
});

test("mobile: the acquisition page in light and dark", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.emulateMedia({ colorScheme: "light", reducedMotion: "reduce" });
  await openAcquisition(page, "finance@finora.test");
  await expect(page.getByTestId("industries-list")).toBeVisible();
  await expect(page.getByTestId("industries-table")).toBeHidden();
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(0);
  await expectNoSeriousA11yIssues(page, "mobile acquisition (light)");
  await page.screenshot({ path: `${SHOTS}/acq-mobile-light.png`, fullPage: true });

  await page.emulateMedia({ colorScheme: "dark", reducedMotion: "reduce" });
  await expectNoSeriousA11yIssues(page, "mobile acquisition (dark)");
  await page.screenshot({ path: `${SHOTS}/acq-mobile-dark.png`, fullPage: true });
});

test("lever planner: §16.3 levers, baselines and evidence labels, light and dark", async ({ page }) => {
  await page.emulateMedia({ colorScheme: "light", reducedMotion: "reduce" });
  await openAcquisition(page, "revops@finora.test");

  // The other baseline, then back to the latest (the default).
  await page.getByTestId("baseline-pre_2023_06").click();
  await expect(page.getByTestId("planned-mrr").getByTestId("planned-value")).toHaveText("2.11M");
  await expect(page.getByTestId("planned-payback").getByTestId("planned-value")).toHaveText("136.1 mo");
  await page.getByTestId("baseline-from_2023_06").click();
  await expect(page.getByTestId("planned-payback").getByTestId("planned-value")).toHaveText("71.6 mo");

  // Ticket size: the §16 reference is +29.7%; the button rounds to whole points.
  await expect(page.getByTestId("ticket-reference")).toHaveText("Reference: +29.7%");
  await page.getByTestId("ticket-reference").click();
  await expect(page.getByTestId("ticket-value")).toHaveText("+30%");
  await expect(page.getByTestId("planned-mrr").getByTestId("planned-value")).toHaveText("3.18M");
  await expect(page.getByTestId("planned-payback").getByTestId("planned-value")).toHaveText("55.1 mo");
  await expect(page.getByTestId("planned-mrr").locator('[data-evidence="observed"]')).toBeVisible();
  await page.getByTestId("ticket-slider").focus();
  await page.keyboard.press("ArrowLeft");
  await expect(page.getByTestId("ticket-value")).toHaveText("+29%");

  // Industry mix: Retail → Healthcare by default (lowest to highest observed ticket).
  await page.getByTestId("reset-levers").click();
  await expect(page.getByTestId("mix-from")).toContainText("Retail");
  await expect(page.getByTestId("mix-to")).toContainText("Healthcare");
  await page.getByTestId("mix-points").fill("10");
  await expect(page.getByTestId("lever-mix")).toContainText("+179K");
  await expect(page.getByTestId("mix-reading")).toContainText("adds 3,120 a month per new customer");

  // Spend moves payback only, and the outcome takes the weakest label (Untested).
  await page.getByTestId("reset-levers").click();
  await page.getByTestId("spend-slider").fill("20");
  await expect(page.getByTestId("planned-mrr").getByTestId("planned-value")).toHaveText("2.45M");
  await expect(page.getByTestId("planned-payback").getByTestId("planned-value")).toHaveText("86.0 mo");
  await expect(page.getByTestId("planned-payback").locator('[data-evidence="untested"]')).toBeVisible();
  await expect(page.getByTestId("lever-ticket").locator('[data-evidence="observed"]')).toHaveText("Observed");
  await expect(page.getByTestId("lever-conversion").locator('[data-evidence="assumption"]')).toHaveText("Assumption");
  await expect(page.getByTestId("lever-spend").locator('[data-evidence="untested"]')).toHaveText("Untested");

  await expectNoSeriousA11yIssues(page, "lever planner (light)");
  await page.screenshot({ path: `${SHOTS}/acq-planner-light.png`, fullPage: true });
  await page.emulateMedia({ colorScheme: "dark", reducedMotion: "reduce" });
  await expectNoSeriousA11yIssues(page, "lever planner (dark)");
  await page.screenshot({ path: `${SHOTS}/acq-planner-dark.png`, fullPage: true });
});
