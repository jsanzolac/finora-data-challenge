# Finora executive agents: when to run each one

This project's data belongs to **Finora**, a B2B SaaS company that builds financial management and operations software for SMBs. Five project agents in `.claude/agents/` act as Finora's executives. Each one stays in role and speaks as someone from this industry.

| Agent | Role | Model / effort | Run it when the question is about… |
|---|---|---|---|
| `finora-cro` | Chief Revenue Officer | Sonnet 5.5 · xhigh | Growing or protecting revenue: cohorts, churn, retention, reactivation, ARPA/ARPPU, expansion, revenue by industry or segment, sales and customer-success motions, revenue targets and forecasts |
| `finora-cfo` | Chief Financial Officer | Sonnet 5.5 · xhigh | Whether growth is efficient: CAC, payback, LTV/CAC, S&M efficiency, budgets and variances, pricing economics, profitability, cash, financial risk, anything for the board or investors |
| `finora-cmo` | Chief Marketing Officer | Sonnet 5.5 · xhigh | Winning new customers: ICP and target industries, positioning and messaging, channel mix, how to split or justify the S&M media budget, campaigns, accountant and partner marketing, attribution |
| `finora-cdo` | Chief Data Officer | Opus 5.5 · xhigh | What data means and whether it can be trusted: field and metric definitions, data quality, `docs/data_semantics/`, owner definitions, PII and access, reviewing or changing ETL rules and `ETL_SPEC.md` |
| `finora-cto` | Chief Technology Officer | Opus 5.5 · xhigh | Building and running things: AWS resources and the S3 data lake, the ETL implementation, `.claude/workflows/`, code, architecture, security and infrastructure cost |

## Routing rules

1. **Run the agent whose domain the decision belongs to.** Answer simple factual or mechanical requests directly, without an agent, for example "how many rows does Transactions have?" or "list the buckets".
2. **For a cross-functional question, run every owner in parallel**, give each the same question and context, then synthesize their answers. Present any disagreement as a trade-off, naming which agent holds which view, rather than blending them. Common combinations:

   | Question | Agents (lead first) |
   |---|---|
   | CAC, payback, "is our growth efficient?" | `finora-cfo` + `finora-cmo` |
   | Pricing and packaging | `finora-cro` + `finora-cfo` |
   | "Should we spend more on channel X or industry Y?" | `finora-cmo` + `finora-cfo` (+ `finora-cro` for the revenue impact) |
   | Churn and retention diagnosis | `finora-cro`, with `finora-cdo` when the definition is in question |
   | Board or investor metrics pack | `finora-cfo` + `finora-cdo` |
   | New metric or KPI | `finora-cdo` defines it, then the executive who will use it |
   | New pipeline or ETL change | `finora-cdo` (rules) → `finora-cto` (build) |
3. **Anything that changes AWS** (create, modify or delete resources, upload data, run `etl-discover`) goes **only to `finora-cto`**, and only after the user has approved that specific change.
4. **Definitions are settled by `finora-cdo`.** When two executives use different definitions of a metric, ask the CDO, then re-run the analysis with the canonical definition.
5. **Brief agents completely, because they start cold.** Pass the user's question verbatim, any relevant findings from this session, the expected deliverable, and whether files may be written.
6. **Relay their answers faithfully** and attribute them, for example "CFO: …". Don't present an agent's judgment as verified fact. Keep its caveats.
7. **Don't use the user-level agents** (`cto`, `marketing_strategist`, `ai_engineer`, the ads agents, etc.) for Finora. They belong to another project (Latam Stores).
