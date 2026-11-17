# Finora dashboards: data quality and acquisition

Two pages behind one sign-in, linked from the header ("Data quality" | "Acquisition").

**Data quality.** A static Next.js 16 dashboard that answers two questions: **which department (dataset) is most and least compliant with the approved data rules**, and **which records fail each rule**. Every number comes from the DQ API (`contracts/dq_api_contract.md`, v1), and the UI hard-codes no rule, dataset or label. The only figures it derives are simple roll-ups of API values, listed under "Derived on screen" below.

- `/`: a minimalist page with two sections. **Departments**: three equal cards, most compliant first, each with one big row-compliance %, a plain status word with a coloured dot (Good, Review, Action needed), one quiet line ("1 row excluded · 5 flagged" or "No issues") and a ▲/▼ change against the previous run when it is non-zero. **Rules**: one table (Rule | one column per department) that shows only the rules with an issue by default, worst first; a toggle switches "Issues (n)" to "All rules (27)". Each cell is a dot and a %. Tapping a number opens the records sheet: the rule title and department, its first sentence, "252 of 66,659 rows fail · 99.62%", and the failing records (source columns only, the reason in an expandable row) with server-side search and paging. Everything technical (rule id, full description, action, kind, inferred, applies-to, the per-run trend, copy link) sits in a collapsed "Details" disclosure.
- `/acquisition/`: decision first, built on the gold model (`docs/gold_acquisition_model.md`, levers in §16) through `contracts/acq_api_contract.md` (v1.3).
  - **What to move:** the §16.6 headline (templated from `levers` and `signal_summary`) and its timing sub-line, then the **lever planner** (§16.3, exact fractions, HALF_UP at each step; it reproduces the five §16.5 fixtures): ticket size (Observed, with the +29.7% reference), industry mix (Observed), conversion rates from the funnel (Assumption) and spend a month (Untested, payback only). Each outcome carries the weakest label among the levers moved. Then "Biggest levers for a 10% move".
  - **Where growth is lost:** new customers a month and starting revenue per new customer, the ticket by half-year cohort (the step precedes the spend change; the spend periods are only a baseline), retention at months 6 and 12, and the per-industry before/after with the mix-vs-within split.
  - **Funnel** (the volume lever): 7 stages with editable rates for every role (saving needs `can_edit`), "+1 point on one rate" in its Details. Then new customers over time, industries, and in Details the spend-and-new-customers tests and the monthly data with CSV.
  - URL state: `/acquisition/?period=<id>&scenario=<id>&def=new_logo&run=<run_id>`, defaults left out.
- `/mrr/`: why MRR changed, from `contracts/mrr_api_contract.md` (v1) and the CDO's `docs/mrr_discounts_model.md`. Period select (last 12 months by default), a hero line, three driver cards (customer behaviour, pricing inferred, timing of payments), the MRR bridge as a horizontal waterfall grouped by driver (steps and drivers come from the API; discounts show "Not available until billing data", never 0), discount leakage (not available today), MRR by month with change by driver, and Top movers and Monthly data (CSV) behind Details. The explainer (the one-sentence rule, the CFO's cases §3.2, the worked bridge §4.2) is in Details. Mocks: `mocks/mrr/generate_fixture.py` builds `summary.json` and `movements.json` from today's files and asserts the bridge identities; `sessionStorage.setItem("mrr_mock_no_gold_run","1")` shows the "No MRR data yet" state.
- **Voice analyst (behind `NEXT_PUBLIC_VOICE=1`, off by default).** A mic button in the header of all three pages ("Hablar con el analista", "Escuchando…", "La voz no está disponible ahora"), per `contracts/agent_api_contract.md` v1.1. `POST /api/agent-session` gives a signed URL and a short-lived agent token, passed to `@elevenlabs/react` (`useConversation`, websocket) as `secret__agent_token` and never stored. The SDK loads lazily on the first click. Client tools: `show_chart` (fetches `/api/agent/results/{id}` with the cookie and opens "Gráfico del analista", with evidence, caveats and a table; last 5 kept), `highlight_kpi` (the 32 catalog `kpi_id`s of `docs/semantic_layer.md` §1.6 as `data-kpi-id`; it navigates to the card's page and opens a closed Details if needed) and `go_to_page` (client-side, the session survives). Captions of the last three turns are on by default. Without the flag, `@finora/voice` resolves to an inert stub (`src/lib/voice/disabled.tsx`), so no voice code ships. Mock builds turn it on and run a scripted session (`mocks/voice.ts`). **CSP:** the only addition is `connect-src wss://api.elevenlabs.io` (`infra/stacks/web.py`); the SDK's three audio worklets are self-hosted under `/voice/` by `scripts/voice-assets.mjs` (voice builds only), so `script-src` needs no `blob:`, `data:` or CDN. `e2e/voice.spec.ts` runs the real SDK path under the production CSP (read from `web.py`) against a Playwright-mocked socket and fails on any CSP violation.
- `/login/`: email and password. There is no sign-up and no "forgot password": users ask their Data admin.
- `/change-password/`: forced on first sign-in (`must_change_password`).

Stack: Next.js 16 (App Router, `output: "export"`), React 19, TypeScript (strict), Tailwind CSS v4, Radix UI (dialog, select, tooltip), TanStack Query, D3 (the trend sparkline in Details), and lucide icons. Text uses the system sans at 15px or more; JetBrains Mono (downloaded by `next/font/google` at build time and served from `/_next/static/media`, CSP `font-src 'self'`) is used only for big numbers, tabular figures and raw source values.

Theme: **follows the operating system, live**. Light (white page, soft-grey surfaces, rule rows alternating white / `#F3F4F6`) and dark (near-black page, rows alternating black / soft dark grey) are both defined as CSS variables in `globals.css`, switched by `@media (prefers-color-scheme: dark)`. There is no script and no toggle, so there is no flash of the wrong theme and an OS change applies with no reload.

## Commands

Node 22.12 or later.

| Command | What it does |
|---|---|
| `npm ci` | Install the pinned dependencies |
| `npm run dev:mock` | Dev server with the mock API (no backend needed): http://localhost:3000 |
| `npm run dev` | Dev server that calls the real `/api/*` on the same origin (needs a proxy or the deployed API) |
| `npm run build` | **Deployable** static export to `out/`, then `scripts/check-no-mocks.mjs` fails the build if any mock code reached it |
| `npm run build:mock` | Mock-mode export to `out-mock/` (for the e2e test only; never deploy it) |
| `npm run typecheck` / `npm run lint` | TypeScript and ESLint |
| `npm test` | Vitest and Testing Library unit tests |
| `npm run test:e2e` | Playwright tests (`e2e/smoke.spec.ts`, `e2e/acquisition.spec.ts`) against the mock export, with axe and screenshots in `test-results/screenshots/` (`npx playwright install chromium` once) |

## Environment variables

All are build-time. The deployable build needs **none**.

| Variable | Default | Meaning |
|---|---|---|
| `NEXT_PUBLIC_DQ_MOCKS` | unset | `1` turns on mock mode: `/api/*` is answered in the browser from `mocks/`. A production build with it set is refused unless `DQ_MOCK_EXPORT=1` is also set |
| `DQ_MOCK_EXPORT` | unset | `1` (with the variable above) writes a mock export to `out-mock/`. Used only by `npm run build:mock` |

How mocks are kept out of production: the only import of the mock layer is `@dq/mock-install`, which `next.config.ts` resolves to `mocks/install.ts` in mock mode and to a stub (`src/lib/mock-switch/disabled.ts`) otherwise. `scripts/check-no-mocks.mjs` then scans `out/` for strings that exist only in `mocks/` and fails the build if it finds one.

## Mock mode

`npm run dev:mock`, then sign in with one of these accounts. They exist only in mock builds; the password for all of them is `finora-demo-2026`.

| Email | Role | Shows |
|---|---|---|
| `data@finora.test` | data | HR-sensitive S&M values as "Restricted" |
| `finance@finora.test` | finance | Every value |
| `revops@finora.test` | revops | HR-sensitive S&M values as "Restricted" |
| `new.analyst@finora.test` | data | Forced password change on first sign-in |
| `locked@finora.test` | – | A 429 "too many attempts" answer |

**Acquisition fixtures** (`mocks/acq/`): `summary.json` is generated by `mocks/acq/generate_fixture.py` (run `infra/.venv/bin/python -I dashboard/mocks/acq/generate_fixture.py` from the repo root) from today's real files with the silver engine, and asserts the gold spec §12 figures (Won, spend, the §12.8 correlations, the §7.5 signal counts, the industry profile) before writing. Every value is real **except the three HR-sensitive spend categories** (Team, PayrollExpenses, Freelance), which are **synthetic placeholders** (the real people total split 50 / 35 / 15; CDO-11). The scenario rows behave like the append-only rate table: Base, `sql_demo_080` (the §12.6 fixture), `proposal_close_045`, and `q4_typo`, a planted invalid scenario (GR-03). A second, planted run `r20261117T120000Z` adds a synthetic 2024-11 month past the data watermark with no spend (`cost_null_reason: spend_missing`): open `/acquisition/?run=r20261117T120000Z&period=2024-11`. `GET /api/acq/scenarios` answers in 1.5 s in mock mode so the loading state shows; saved scenarios last for the browser tab (`sessionStorage`). To see the "No acquisition data yet" state (404 `no_gold_run`), run `sessionStorage.setItem("acq_mock_no_gold_run", "1")` in the console and reload; an unknown `?run=` gives 404 `unknown_run`.

The fixtures (`mocks/fixtures.ts`) follow the contract exactly and the machine-readable catalog in `docs/approved_data_rules.md`: the 27 dashboard rules (run controls never reach a summary), their ids, titles, kinds, actions, `inferred` and `counts_toward_compliance`, the rounding and pass/warn/fail thresholds, and the rank tie-breaks. Today's real files are almost clean, so the latest mock run has **planted failures** in all three departments: non-numeric amounts, duplicate keys, bad months, the empty Industry record, bad and duplicate customer IDs, unmapped industries, a bad spend cell, missing customer-months, a month gap, removed keys, restated values, a field-count failure, a control character, and more than 200 negative amounts (SQ-07b). There are 7 succeeded runs and 1 failed run for the trend. Like today's real files, 12 rules pass everywhere in the latest run, so the default "Issues" view (15 rules) differs from "All rules (27)". The mock API applies role masking, `q` search over the masked record and paging (`page_size` at most 200), as the API Lambda does. A session lives in `sessionStorage`, standing in for the HttpOnly cookie.

## Deploying (for the infra stack)

- **Upload `out/`** to the site bucket. `trailingSlash: true` is set, so the pages are `index.html`, `login/index.html`, `change-password/index.html` and `404.html`.
- **Clean-URL rewrite** (CloudFront Function, viewer request), the same rule `scripts/serve-static.mjs` applies:
  - a URI ending in `/` gets `index.html` appended (`/login/` → `/login/index.html`, `/` → `/index.html`);
  - a URI whose last segment has no `.` gets `/index.html` appended (`/login` → `/login/index.html`);
  - anything else is served as is (`/_next/static/…`, `/index.txt`, `/login/index.txt`: the `.txt` files are the client router's payloads and must be served, not rewritten);
  - `/api/*` goes to the API origin and is never rewritten.
- **Errors:** map S3 403/404 to `/404.html` with status 404. Do **not** map them to `/index.html`: this is a multi-page export, not a single-page app.
- **Caching:** `/_next/static/*` is content-hashed (`Cache-Control: public, max-age=31536000, immutable`). Serve HTML and `.txt` with `no-cache`.
- **Content-Security-Policy:** Next's static export inlines its router payload (`self.__next_f.push(…)`), and React writes inline `style` attributes (chart positions, virtual-table padding). A working policy:
  `default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; font-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'; object-src 'none'`
- **Same origin:** the app only calls relative `/api/...` with `credentials: "same-origin"`, so it needs no CORS and no API URL variable.

## Behaviour notes

- **Auth:** the session cookie is HttpOnly, so the app asks `GET /api/auth/session` on load. A 401 on any later call sends the user to `/login/?returnTo=<where they were>&reason=expired`. A 403 `password_change_required` sends them to `/change-password/`. A return URL must be a same-origin path, so the login page can't be used as an open redirect.
- **URL state:** `/?run=<id>&rule=<rule_id>&dataset=<dataset_id>&q=<search>&page=<n>&size=<n>`. Defaults are left out, `run` is omitted for the latest run, and the back button walks through cells, pages and runs.
- **Keyboard:** the rules table is one tab stop (roving tabindex). Arrow keys move between numbers and skip rules that don't apply, Home and End go to the row ends (with Ctrl or Cmd, the column ends), and Enter opens a cell. In the sheet, Escape clears the search box, a second Escape closes the sheet, and focus returns to the cell. On narrow screens the table becomes one list per department.
- **Status:** green / amber / red. Light uses `#1A7F37` / `#9A6700` / `#CF222E` (amber text is `#855900` so it stays ≥ 4.5:1 on the grey row); dark uses `#2ea043` / `#e3b341` / `#f85149` for dots and lighter inks for text. A department card always shows the status word next to the dot; a rule cell shows the dot and the % (in the status colour unless Good), and its accessible name and tooltip carry the word. Rules that don't apply show a faint dash.
- **Derived on screen** (roll-ups of API values, no thresholds of the UI's own): a department's status is the worst cell status the API gave that department (fail > warn > pass); a rule "has an issue" when any department's status is warn or fail or it has failures; "worst first" sorts by the worst status, then the lowest compliance.
- **Raw values** are shown exactly as received: an empty string is an explicit `(empty)` token, control characters show as their visible symbol (TAB as ␉), and leading or trailing spaces are marked. Masked HR values show a "Restricted" pill with the tooltip "HR-sensitive values are visible to Finance only".

## Layout

```
src/app/                 pages: overview, acquisition, login, change-password, not-found
src/components/          overview (department cards, sparkline), rules (rules table), records (sheet, table, values), acq (acquisition page), auth, layout (header with the two-page nav), ui
src/lib/                 API client and types (from the contract), queries, auth store, URL state, ranking, status, formatting
src/lib/acq/             acquisition types, exact arithmetic (ratio, funnel, periods), signals reading, scenario form, monthly table and CSV, queries, URL state
mocks/                   contract-shaped fixtures and the mock API (mock builds only); mocks/acq/ for acquisition
e2e/                     Playwright smoke test (DQ) and acquisition test
scripts/                 check-no-mocks.mjs, serve-static.mjs (local server with the CloudFront rewrite)
```
