# Voice agent ↔ API contract (v1.1)

Shared by the voice backend (`dq_api/`, `etl/`, `infra/`), the dashboard voice UI (`dashboard/`) and the ElevenLabs agent configuration. Source: the reference architecture (`docs/aws_architecture/data-lake-voice-dashboard-architecture.html`, "Voice agent" sections) and the user's decisions of 2026-11-17:
- ElevenLabs Agents for voice, with the **ElevenLabs-hosted conversation LLM**;
- the analysis LLM is **Kimi K3 on Bedrock in us-east-1** (inference profile `us.moonshotai.kimi-k3`), replacing "Claude on Bedrock" in the reference;
- **Spanish only**;
- **briefing + questions over gold** (the full reference flow).

All conventions of `contracts/dq_api_contract.md` apply: same origin, error shape, roles `data` / `finance` / `revops`, `"__restricted__"` masking, exact-decimal money strings. **Change this contract only by agreement, and bump the version.**


## v1.1 changes (2026-11-17, CDO semantic layer `docs/semantic_layer.md`, catalog `sl-2026-11-17`). These win over anything above.

1. **The catalog is binding.** Metric ids, dimensions, `kpi_id`s (32 dashboard cards), the compiler rules, the out-of-scope rules, the caveats, the briefing candidates and the 20-question eval set are all in `docs/semantic_layer.md`.
2. **Data-quality answers** compile against the DQ snapshot and `finora_dq`, not `finora_gold`.
3. **`POST /api/agent/ask` response:** `status` ∈ `answered` | `pending` | `out_of_scope` | `error`. Each response also carries:
   - `reason_code` (the out-of-scope rule id, or null);
   - `evidence` (observado / inferido / supuesto / no probado);
   - `caveats_es` (an array; the mandatory caveats attach automatically);
   - `kpi_ids` (an array) and `gold_run_id`.

   Kimi K3 never receives rows. Answers are cached by (spec hash, role, run), not by the question text.
4. **Spoken limits:** at most 5 values in `summary_es`, and at most 200 rows in `/api/agent/results/{id}`. A money cell built from fewer than 5 customers is never spoken. Stocks such as MRR are never summed across months.
5. **HR categories** (Team, PayrollExpenses, Freelance): never spoken, even to Finance; they appear only in the chart for Finance. Until a Finance-only Athena workgroup exists, questions about them return `out_of_scope` for every role.
6. **`GET /api/agent/briefing`** adds `status` (`ok` | `degraded`) and an `evidence` field on each fact. A fact that fails the number check is regenerated once, then replaced by its fixed template, then dropped.
7. **`highlight_kpi`** uses the catalog's `kpi_id`s. The dashboard adds matching `data-kpi-id` attributes to the cards.

## Secrets and identities

- **ElevenLabs API key:** SSM SecureString `/toldo/prod/elevenlabs/api_key` in **us-east-1** (the el_toldo key, same account). It is read at runtime by the session Lambda only, and never copied, logged or returned.
- **Agent token:**
  - **Form:** a dedicated, short-lived (45 min), **read-only** bearer token, issued per voice session to a logged-in user whose password is not pending a change. Store it SHA-256-hashed with a TTL, like the el_toldo sessions.
  - **Holder:** it carries the user's role. It is valid only on `/api/agent/briefing` and `/api/agent/ask`.
  - **Delivery:** it is given to ElevenLabs as a **secret dynamic variable** (`secret__agent_token`), used in tool headers only and never in the LLM prompt.
  - **Never:** the agent never gets the `dq_session` cookie or a refresh token.

## Routes

### `POST /api/agent-session` (browser; `dq_session` cookie)

Returns everything the browser needs to start the voice session.

```json
{ "signed_url": "wss://…", "agent_id": "…", "agent_token": "…", "expires_at": "2026-11-17T21:45:00Z",
  "dynamic_variables": { "user_role": "finance", "as_of_month": "2024-10" } }
```

- 401 without a session, 403 `password_change_required`.
- 503 `voice_unavailable` if ElevenLabs or the key is unreachable. The UI then shows "La voz no está disponible ahora".
- The browser passes `agent_token` as `secret__agent_token`. It never stores the token beyond the session.

### `GET /api/agent/briefing` (ElevenLabs webhook tool; `Authorization: Bearer <agent token>`)

Returns the briefing precomputed at the last refresh. It is not generated per request.

```json
{
  "as_of_month": "2024-10", "refreshed_at": "2026-11-17T19:12:00Z",
  "facts": [ { "id": "acq_ticket_drop", "page": "acquisition", "kpi_ids": ["acq.run_rate_per_won"],
               "text_es": "Los clientes nuevos por mes subieron 52%, pero cada uno empieza pagando 24% menos…",
               "numbers": [ { "kpi_id": "acq.run_rate_per_won", "value": "42550.70", "unit": "money" } ] } ],
  "definitions": [ { "metric_id": "acq.run_rate_per_won", "text_es": "Pago mensual promedio de un cliente nuevo en sus meses 2 a 4." } ]
}
```

- 5 to 8 facts covering Data quality, Acquisition and MRR.
- Every number in `text_es` appears in `numbers` and was **checked against the KPI table** at refresh. A fact that fails the check is dropped and logged.
- The briefing holds no HR-sensitive amounts (Team, PayrollExpenses, Freelance), so one briefing serves every role.
- 401 makes the agent say: "Por favor recarga la página para continuar."

### `POST /api/agent/ask` (ElevenLabs webhook tool; Bearer agent token)

Request: `{ "question": "¿Qué industria bajó más su ticket?", "previous_result_id": null }`

```json
{ "status": "answered", "result_id": "r_7f3a…", "summary_es": "Retail fue la que más bajó: de 43.671 a 29.407 por cliente nuevo.",
  "chart": { "type": "bar", "title_es": "Ticket por cliente nuevo por industria" } }
```

- `status` is one of:
  - `answered`;
  - `out_of_scope`, with `reason_es` and an `alternative_es` (as in the reference, case 3);
  - `error`, with `reason_es`.
- **How a question is answered:**
  - **Kimi K3 (Bedrock, us-east-1)** turns the question, the matching **semantic-layer catalog** entries and the previous result into a **query spec**, through a tool-use JSON schema. The model never writes SQL.
  - **The semantic layer** compiles the spec into SQL over the governed `finora_gold` views and tables, and Athena (workgroup `finora-dl`) runs it.
  - **Role masking and HR rules** are applied in the compiler.
- **What the agent receives:** a short summary and IDs. **Rows are never sent to the agent.**
- **Timing:**
  - A result is cached by (normalized question, role, run).
  - If the answer takes longer than about 20 s, the route returns `status: "pending"` with a `result_id`. The agent says it is still working, and calls `ask` again with `previous_result_id`.

### `GET /api/agent/results/{result_id}` (browser; `dq_session` cookie)

The chart data for a result, re-checked against the **caller's** role. A result created under one role is never served to a lower role.

```json
{ "result_id": "r_7f3a…", "question": "…", "title_es": "…",
  "chart": { "type": "bar|line|table", "x": "industry", "y": ["run_rate_value"], "unit": "money" },
  "columns": ["industry", "run_rate_value"], "rows": [ ["Retail", "28733.00"] ],
  "sql_hash": "…", "run_id": "r…", "created_at": "…" }
```

## Client tools (registered by the page with `@elevenlabs/react` `useConversation`)

| Tool | Parameters | What the page does |
|---|---|---|
| `show_chart` | `{ "result_id": string }` | Fetches `/api/agent/results/{id}` and opens the chart panel, using the same chart components as the pages |
| `highlight_kpi` | `{ "kpi_id": string }` | Scrolls to and highlights the KPI card the agent is talking about. The `kpi_id`s are in the catalog |
| `go_to_page` | `{ "page": "dq" \| "acquisition" \| "mrr" }` | Navigates without ending the session |

The agent passes only IDs to the browser. The browser fetches the data itself, with the user's own session.

## ElevenLabs agent (configured by API, idempotent, from code in `infra/` or `scripts/`)

- **Language and voice:** Spanish (`es`), with a Spanish voice. Signed URLs are required (authentication enabled).
- **First message:** "Hola, estoy cargando los números de hoy."
- **Prompt rules** (from the reference):
  - Never state a number that did not come from a tool result.
  - If a tool returns 401, ask the user to reload the page.
  - Keep answers short and offer to show the chart.
  - Name evidence levels (observado / supuesto / no probado), following the decision-first rules in `docs/gold_acquisition_model.md` §16.
- **Tools:** the webhook tools `get_briefing` and `ask` (header `Authorization: Bearer {{secret__agent_token}}`) and the client tools above. The webhook base is `https://d1smzfxmkay9lx.cloudfront.net`.
- **Retention:** transcripts and audio at the minimum the plan allows. A post-call webhook is optional and out of scope for v1.
