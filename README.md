# Finora data challenge

An end-to-end analytics solution for Finora, a B2B SaaS company selling financial software to SMBs, built from three files: payments by customer and month, customer industry, and S&M spend. It answers two executive questions:

- **Funnel (CRO):** "We grew volume at the top of the funnel, but new customers aren't growing at the same pace. Where are we losing growth, and why?"
- **MRR (CFO):** "If a customer paid 100 and now pays 80, did they contract or get a discount? How much revenue are we leaving on the table?"

The answer is a **simulation front end**: a dashboard where you move business levers and immediately see their impact on new MRR and payback. It is backed by a governed AWS data lake and a Spanish voice analyst.

> **The finding in one line:** we are not losing customers, we are losing value per customer. New customers per month rose 52%, but each one starts paying 24% less, so new MRR grew only 16%.

---

## 1. Run the simulation locally (no AWS needed)

The dashboard ships a mock API built from the real files, so you can use every screen on your laptop. You need Node 22.12 or later.

```bash
cd dashboard
npm ci
npm run dev:mock
```

Open http://localhost:3000 and sign in with a demo account. They exist only in mock mode, and the password for all of them is `finora-demo-2026`.

| Email | Role | What you'll see |
|---|---|---|
| `finance@finora.test` | finance | Every value, and can save rate scenarios |
| `revops@finora.test` | revops | HR spend shown as "Restricted"; can save rate scenarios |
| `data@finora.test` | data | HR spend shown as "Restricted"; can try rates but not save them |
| `new.analyst@finora.test` | data | The forced password change on first sign-in |

The header links the three pages: **Data quality**, **Acquisition** and **MRR**.

---

## 2. Using the simulator (Acquisition page)

Go to **Acquisition**. The page is decision-first: it tells you what to move before it shows any chart.

### Step 1: read the headline

The top line summarises the situation in plain words: new customers up, starting revenue per customer down, and new MRR growing much less than customers. A sub-line explains the timing: the drop in ticket started in early 2023, before the spend cut.

### Step 2: choose the baseline

In **Start from**, pick the period the simulation starts from. The default is Jun 2023 – Oct 2024, which is today's level. The planner shows that period's **Today's level**:

| Measure | Today's level (Jun 2023 – Oct 2024) |
|---|---|
| New customers a month | 57.5 |
| Starting revenue per new customer | 42,550.70 |
| New MRR a month | 2,447,916.75 |
| Payback | 71.6 months |

Under **Details** you can switch the definition of a new customer. You can keep every first payment, the default, or exclude the 43 customers who were probably already active.

### Step 3: move the levers

The planner has four levers. Every outcome updates instantly and carries an evidence label, so you always know how far to trust it:

| Lever | How to move it | What it changes | Evidence |
|---|---|---|---|
| **Ticket size** | Set a % change in what each new customer pays in their first months. The reference "back to the earlier ticket at today's industry mix" is **+29.7%** | Starting revenue per customer, new MRR, payback | **Seen in the data** |
| **Industry mix** | Choose **From industry**, **To industry** and how many points of share to move, for example from Retail (lowest ticket) to Healthcare or Technology | New MRR through each industry's observed ticket | **Seen in the data** |
| **Conversion rates** | Edit the rate between any two funnel stages in the funnel below (New → Working → Engaged → SQL → Demo → Proposal → Won) | New customers a month, new MRR | **Assumption**: the files contain no stage data |
| **Spend a month** | Change the monthly S&M spend | Cost per new customer and payback only | **Not measurable**: test it with a holdout |

Each outcome shows the weakest label among the levers you moved. If you combine an observed lever with an assumed one, the result says "Assumption".

**Worked example:** set **Ticket size +10%** and leave the rest unchanged. New MRR rises by about **244,800 a month** (2,447,916.75 → 2,692,708.43), and payback drops from **71.6 to 65.1 months**.

### Step 4: compare levers

**Biggest levers for a 10% move** ranks the levers by the new MRR each one adds for a comparable 10% change. Today, ticket size comes first.

### Step 5: understand where growth is lost

**Where growth is lost** shows the evidence behind the levers:
- new customers vs starting revenue per customer;
- the ticket by half-year cohort;
- retention at months 6 and 12 (stable at 91–95% at month 6);
- each industry before and after, split into **mix vs within-industry**. About 96% of the drop is within industries; Retail fell about 33% and Healthcare held.

### Step 6: work with the funnel and scenarios

- **Editing rates:** each rate between two stages is an editable percentage. Arrow keys step 1 point, Shift steps 0.1, and the −/+ buttons also step 1 point. The funnel recalculates with exact decimals, and **Reset** returns to the selected scenario.
- **Choosing a scenario:** the **Conversion rates** selector switches between *Base* (the agreed assumptions) and saved scenarios.
- **Saving a scenario** (finance and revops): **Save as scenario** stores your rates with an id, a name and a reason. Rates are never overwritten; every change is a new row, so the history is its own audit log. Changing *Base* asks for confirmation.
- **+1 point on one rate** (in Details) shows how much each transition is worth. The lowest rate always gives the most per point. That is arithmetic, not evidence that it is the easiest to move.

### Sharing a view

The URL keeps your state, so you can send a link to exactly what you're looking at:

```
/acquisition/?period=<period>&scenario=<scenario_id>&def=new_logo
```

---

## 3. The MRR page

**MRR** answers "why did our MRR change?". It splits the change into **customer behaviour**, **pricing** (inferred) and **timing of payments**:

| Feb 2022 → Oct 2024 | |
|---|---|
| Opening MRR | 35.0M |
| Customer behaviour (new, expansion, contraction, churn, reactivation) | **+63.2M** |
| Pricing (inferred from 140 late price steps) | +0.57M |
| Timing of payments | −2.4M |
| Discounts | *Not available until billing data*, never shown as 0 |
| Closing MRR | 96.4M |

- **Choose the period** to see the bridge for it.
- **Open Details** for the top movers, the monthly data (with CSV) and the CFO's cases: a discount start, change or end is its own movement and never counts as expansion or contraction.

---

## 4. The Data quality page

**Data quality** ranks the three data sources (Transactions, Industry, S&M spend) by compliance with the approved rules. Click any percentage to see the exact records that fail a rule. Today: Transactions 100%, S&M spend 100% (5 flagged rows), Industry 99.95% (1 empty record excluded).

---

## 5. The voice analyst (live deployment)

On the deployed site, every page has a **"Hablar con el analista"** button: a Spanish voice agent built on ElevenLabs Agents. It:
- opens with a briefing of the latest numbers, written by **Kimi K3 on Amazon Bedrock**, with every figure checked against the KPI table;
- answers follow-up questions by turning them into governed queries over the gold layer. The model never writes SQL, and no customer-level rows reach the agent;
- shows charts, highlights the card it is talking about and moves between pages;
- says when a question can't be answered with this data (stage-level funnel, discounts, currency, causal spend claims) and offers the closest alternative.

In mock mode, a scripted voice session demonstrates the same on-screen actions without a microphone or ElevenLabs.

---

## 6. The live deployment

- **URL:** https://d1smzfxmkay9lx.cloudfront.net (sign-in required).
- **Accounts:** an admin creates them; the password prompt is hidden, and the user must change the password at first sign-in:

  ```bash
  infra/.venv/bin/python scripts/create_user.py --email <email> --role finance|revops|data
  ```

**Architecture,** following `docs/aws_architecture/data-lake-voice-dashboard-architecture.html`:

```
S3 staging ─► EventBridge ─► Step Functions
                               ├─ Glue: bronze (byte-faithful copy + _ingested_at)
                               ├─ Glue Spark: silver (Iceberg) + Glue Data Quality, quarantine table
                               ├─ Glue: DQ snapshot
                               ├─ Glue Spark: gold acquisition (levers) ─► gold MRR bridge
                               └─ Glue: voice briefing (Kimi K3 on Bedrock)
serving snapshots (S3) ─► API Gateway + Lambda (auth, /api/dq, /api/acq, /api/mrr, /api/agent) ─► CloudFront ─► Next.js dashboard
                                                                                  ElevenLabs agent ◄─┘ (signed URL, short-lived token)
```

Everything is infrastructure as code (AWS CDK in Python, `infra/`), in us-west-2. Bedrock (Kimi K3) runs in us-east-1.

---

## 7. Repository map

| Path | What it holds |
|---|---|
| `dashboard/` | The Next.js simulation front end, its mocks and tests (see `dashboard/README.md` for details) |
| `etl/` | Bronze, silver, gold and MRR jobs (Glue / PySpark), the rules config and tests |
| `dq_api/`, `auth/`, `voice/` | API Lambdas: dashboard data, sign-in and sessions, and the voice agent (semantic-layer compiler, Kimi K3 calls) |
| `infra/` | AWS CDK stacks and deploy evidence |
| `contracts/` | API contracts shared by the front end and the back end |
| `docs/` | Definitions and decisions: `approved_data_rules.md` (data rules), `gold_acquisition_model.md` (funnel and levers, §16), `mrr_discounts_model.md` (MRR and discounts), `semantic_layer.md` (voice catalog) |
| `analysis/` | The first Python analysis of the funnel and drivers |
| `data/` | The three source files |
| `scripts/` | User creation, parity checks, voice agent setup and eval |

---

## 8. Tests

```bash
# Front end
cd dashboard && npm test && npx playwright install chromium && npm run test:e2e

# Back end (each suite separately)
infra/.venv/bin/python -m pytest -q etl/tests
infra/.venv/bin/python -m pytest -q dq_api
infra/.venv/bin/python -m pytest -q auth
```

The Spark and Iceberg tests need PySpark 3.5 with the Iceberg 1.7 runtime jar (`etl/tests/spark_support.py`). Without it they are skipped.

---

## Notes on the data

- **Amounts:** revenue `amount` is multiplied by 10,000, and S&M spend by 100,000,000 (owner definitions). The **currency is not stated** in the files, so amounts are shown in data units.
- **Funnel stages:** stages before *Won* are not observed. They are estimated from Won with editable conversion rates and always labelled as assumptions.
- **MRR basis:** MRR is based on payments, with late payments and prepayments spread over the months they cover, until billing data with list prices and discounts exists.
