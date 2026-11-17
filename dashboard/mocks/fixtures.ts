/**
 * Contract-shaped fixtures for mock mode (contracts/dq_api_contract.md, v1).
 *
 * Rule ids, titles, layers, kinds, actions, `inferred`, `counts_toward_compliance`,
 * reason codes, the status thresholds and the rank tie-breaks follow the
 * machine-readable catalog and "DQ metric definitions" in
 * docs/approved_data_rules.md. Run controls are never in a summary, so they are
 * not here either.
 *
 * Everything is generated deterministically. The latest run carries planted
 * failures in all three departments (today's real files are almost clean, see
 * "Expected results on today's files"), so every UI state can be exercised:
 * non-numeric amounts, duplicate keys, a bad month, an unmapped industry, a bad
 * spend cell, missing customer-months, the empty Industry record, restricted HR
 * values, a rule with more than 200 failing records, and `na` cells.
 *
 * The UI reads none of this: it renders whatever /api/dq/summary returns.
 */
import type {
  CellStatus,
  DatasetSummary,
  DqRecord,
  Rule,
  RuleAction,
  RuleKind,
  RuleResult,
  Run,
  Summary,
  TrendPoint,
} from "../src/lib/api/types";

/** Only present in mock builds. scripts/check-no-mocks.mjs fails the real build if it finds it. */
export const MOCK_MARKER = "__DQ_MOCK_LAYER__";

/* ------------------------------------------------------------ datasets */

interface DatasetDef {
  id: string;
  label: string;
  sourceKey: string;
  columns: string[];
  rowsLatest: number;
  /** Rows added per monthly delivery. */
  rowsPerMonth: number;
  /** HR-sensitive columns: only the finance role sees their values. */
  restrictedColumns: string[];
}

/** In the fixed rank tie-break order of the rules document. */
export const DATASETS: DatasetDef[] = [
  {
    id: "transactions",
    label: "Transactions",
    sourceKey: "transactions/Transactions.csv",
    columns: ["ID", "month", "amount"],
    rowsLatest: 66674,
    rowsPerMonth: 1961,
    restrictedColumns: [],
  },
  {
    id: "industry",
    label: "Industry",
    sourceKey: "industry/Industry.csv",
    columns: ["ID", "Industria"],
    rowsLatest: 1962,
    rowsPerMonth: 0,
    restrictedColumns: [],
  },
  {
    id: "sm_spend",
    label: "S&M spend",
    sourceKey: "s_and_m/S&M_spend.csv",
    columns: ["Month", "PaidMedia", "Travel", "PublicidadNoWeb", "Freelance", "SoftwareTools", "Team", "PayrollExpenses"],
    rowsLatest: 34,
    rowsPerMonth: 1,
    restrictedColumns: ["Team", "PayrollExpenses", "Freelance"],
  },
];

export function datasetDef(id: string): DatasetDef | undefined {
  return DATASETS.find((d) => d.id === id);
}

/** Stage-A failures have no trusted column positions (§ Access): every value is restricted for non-finance roles. */
const STAGE_A_RULES = new Set(["CDO-01", "SQ-02", "SQ-01"]);
const STAGE_A_REASON = /^(UNDECODABLE_LINE|CONTROL_CHAR|FIELD_COUNT):/;

export function isStageAFailure(record: DqRecord): boolean {
  return STAGE_A_REASON.test(record.reason);
}

/* ---------------------------------------------------------------- runs */

interface RunDef {
  id: string;
  startedAt: string;
  seconds: number;
  asOfMonth: string;
  monthsBack: number;
  status: "succeeded" | "failed";
  /** Share of each dataset's planted failures present in this run. */
  share: Record<string, number>;
  /** Rules whose planted failures were fixed by this run: they pass everywhere. */
  clean?: string[];
}

/**
 * Oldest first. The story: Transactions improves run over run, Industry slips
 * a little, and S&M spend goes from clean to the least compliant department.
 */
const RUN_DEFS: RunDef[] = [
  { id: "r20260928T041000Z", startedAt: "2026-09-28T04:10:00Z", seconds: 61, asOfMonth: "2024-04", monthsBack: 6, status: "succeeded", share: { transactions: 1, industry: 0.4, sm_spend: 0 } },
  { id: "r20261005T041000Z", startedAt: "2026-10-05T04:10:00Z", seconds: 63, asOfMonth: "2024-05", monthsBack: 5, status: "succeeded", share: { transactions: 0.95, industry: 0.5, sm_spend: 0 } },
  { id: "r20261012T041000Z", startedAt: "2026-10-12T04:10:00Z", seconds: 66, asOfMonth: "2024-06", monthsBack: 4, status: "succeeded", share: { transactions: 0.9, industry: 0.5, sm_spend: 0.25 } },
  { id: "r20261019T041000Z", startedAt: "2026-10-19T04:10:00Z", seconds: 64, asOfMonth: "2024-07", monthsBack: 3, status: "succeeded", share: { transactions: 0.85, industry: 0.7, sm_spend: 0.25 } },
  { id: "r20261026T041000Z", startedAt: "2026-10-26T04:10:00Z", seconds: 70, asOfMonth: "2024-08", monthsBack: 2, status: "succeeded", share: { transactions: 0.8, industry: 0.8, sm_spend: 0.5 } },
  { id: "r20261102T041000Z", startedAt: "2026-11-02T04:10:00Z", seconds: 69, asOfMonth: "2024-09", monthsBack: 1, status: "succeeded", share: { transactions: 0.7, industry: 1, sm_spend: 0.5 } },
  { id: "r20261109T041000Z", startedAt: "2026-11-09T04:10:00Z", seconds: 12, asOfMonth: "2024-10", monthsBack: 0, status: "failed", share: { transactions: 0, industry: 0, sm_spend: 0 } },
  {
    id: "r20261116T041000Z",
    startedAt: "2026-11-16T04:10:00Z",
    seconds: 72,
    asOfMonth: "2024-10",
    monthsBack: 0,
    status: "succeeded",
    share: { transactions: 0.6, industry: 1, sm_spend: 1 },
    // Like today's real files, most rules pass: only some departments still have issues.
    clean: ["CDO-01", "SQ-05", "SQ-06", "CDO-05", "SQ-12", "CDO-06a", "SB-04", "SB-06", "SB-07", "CDO-08", "CRO-05", "CRO-07"],
  },
];

function fakeSha(seed: string): string {
  let h1 = 0x811c9dc5;
  let out = "";
  for (let round = 0; round < 8; round += 1) {
    for (let i = 0; i < seed.length; i += 1) {
      h1 ^= seed.charCodeAt(i) + round;
      h1 = Math.imul(h1, 0x01000193) >>> 0;
    }
    out += h1.toString(16).padStart(8, "0");
  }
  return out;
}

function rowsRead(def: DatasetDef, run: RunDef): number {
  return def.rowsLatest - def.rowsPerMonth * run.monthsBack;
}

function toRun(run: RunDef): Run {
  const finished = new Date(new Date(run.startedAt).getTime() + run.seconds * 1000);
  const datasets: Run["datasets"] = {};
  for (const def of DATASETS) {
    datasets[def.id] = {
      source_key: def.sourceKey,
      sha256: fakeSha(`${def.id}:${run.asOfMonth}`),
      rows_read: rowsRead(def, run),
    };
  }
  return {
    run_id: run.id,
    started_at: run.startedAt,
    finished_at: finished.toISOString().replace(".000Z", "Z"),
    as_of_month: run.asOfMonth,
    status: run.status,
    datasets,
  };
}

/* ------------------------------------------------------ record helpers */

const MONTH_COUNT = 34; // 2022-01 .. 2024-10
const CUSTOMERS = 1961;

function ym(monthIndex: number): string {
  const year = 2022 + Math.floor(monthIndex / 12);
  const month = (monthIndex % 12) + 1;
  return `${year}-${String(month).padStart(2, "0")}`;
}

/** Non-padded M/D/YYYY month-end, as in Transactions.csv. */
function monthEnd(monthIndex: number): string {
  const year = 2022 + Math.floor(monthIndex / 12);
  const month = (monthIndex % 12) + 1;
  const day = new Date(Date.UTC(year, month, 0)).getUTCDate();
  return `${month}/${day}/${year}`;
}

/** Line of (customer, month) in Transactions.csv: sorted by ID then month, header on line 1. */
function txLine(id: number, monthIndex: number): number {
  return 2 + (id - 1) * MONTH_COUNT + monthIndex;
}

function plain(value: number): string {
  return String(Number(value.toFixed(2)));
}

const TX_ALL = ["ID", "month", "amount"];

function tx(
  id: number,
  monthIndex: number,
  overrides: Partial<{ month: string; amount: string; line: number; idRaw: string }>,
  failed: string[],
  reason: string,
  action: RuleAction,
): DqRecord {
  const month = overrides.month ?? monthEnd(monthIndex);
  const idRaw = overrides.idRaw ?? String(id);
  return {
    source_line: overrides.line ?? txLine(id, monthIndex),
    key: { ID: idRaw, month },
    values: { ID: idRaw, month, amount: overrides.amount ?? plain(4 + ((id * 13 + monthIndex * 7) % 900) / 10) },
    failed_columns: failed,
    reason,
    action,
    other_failed_rules: [],
  };
}

const SM_SPEND_COLUMNS = ["PaidMedia", "Travel", "PublicidadNoWeb", "Freelance", "SoftwareTools", "Team", "PayrollExpenses"] as const;
const SM_ALL = ["Month", ...SM_SPEND_COLUMNS];
/** The five negative PayrollExpenses months of today's file (2023-11, 2023-12, 2024-02, 2024-03, 2024-07). */
const NEGATIVE_PAYROLL: Record<number, string> = { 22: "-$0.016", 23: "-$0.053", 25: "-$0.003", 26: "-$0.021", 30: "-$0.042" };

function smRow(monthIndex: number, overrides: Record<string, string> = {}): Record<string, string> {
  const base = 0.6 + ((monthIndex * 37) % 50) / 100;
  const values: Record<string, string> = { Month: ym(monthIndex) };
  SM_SPEND_COLUMNS.forEach((column, i) => {
    const cell = column === "Freelance" && monthIndex >= 16 ? 0 : base / (i + 1) + ((monthIndex + i * 3) % 7) / 100;
    values[column] = `$${cell.toFixed(3)}`;
  });
  const negative = NEGATIVE_PAYROLL[monthIndex];
  if (negative) values.PayrollExpenses = negative;
  return { ...values, ...overrides };
}

function sm(
  monthIndex: number,
  overrides: Record<string, string>,
  failed: string[],
  reason: string,
  action: RuleAction,
): DqRecord {
  const values = smRow(monthIndex, overrides);
  return {
    source_line: monthIndex + 2,
    key: { Month: values.Month ?? ym(monthIndex) },
    values,
    failed_columns: failed,
    reason,
    action,
    other_failed_rules: [],
  };
}

function ind(line: number, id: string, industria: string, failed: string[], reason: string, action: RuleAction): DqRecord {
  return {
    source_line: line,
    key: { ID: id },
    values: { ID: id, Industria: industria },
    failed_columns: failed,
    reason,
    action,
    other_failed_rules: [],
  };
}

function finding(key: Record<string, string>, reason: string): DqRecord {
  return { source_line: null, key, values: {}, failed_columns: [], reason, action: "finding", other_failed_rules: [] };
}

function bySourceLine(a: DqRecord, b: DqRecord): number {
  return (a.source_line ?? 0) - (b.source_line ?? 0);
}

/* ------------------------------------------- planted failures: Transactions */

const TX_CONTROL_CHAR: DqRecord[] = [
  tx(1333, 15, { amount: "7.5\t" }, TX_ALL, "CONTROL_CHAR: the line holds U+0009 (TAB)", "exclude"),
];

const TX_FIELD_COUNT: DqRecord[] = [
  tx(256, 5, { amount: "25,0" }, TX_ALL, "FIELD_COUNT: the line has 4 fields, the registry has 3", "exclude"),
  tx(1419, 22, { amount: "" }, TX_ALL, "FIELD_COUNT: the line has 2 fields, the registry has 3", "exclude"),
];

const TX_KEY: DqRecord[] = [
  tx(845, 9, { idRaw: "0" }, ["ID"], 'BAD_ID: "0" does not match ^[1-9][0-9]*$', "exclude"),
  ...([
    [118, 14, "18.4", "18.4"],
    [733, 2, "6.3", "0"],
    [1502, 30, "44.1", "41.4"],
  ] as const).flatMap(([id, monthIndex, first, second]) => {
    const line = txLine(id, monthIndex);
    const reason = `DUPLICATE_KEY: (${id}, ${ym(monthIndex)}) is on lines ${line} and ${line + 1}. Every copy is excluded`;
    return [
      tx(id, monthIndex, { amount: first, line }, ["ID", "month"], reason, "exclude"),
      tx(id, monthIndex, { amount: second, line: line + 1 }, ["ID", "month"], reason, "exclude"),
    ];
  }),
];

const TX_BAD_MONTH: DqRecord[] = [
  tx(57, 13, { month: "2/30/2023" }, ["month"], 'BAD_MONTH: "2/30/2023" is not a calendar date', "exclude"),
  tx(412, 11, { month: "13/31/2022", amount: "N/A" }, ["month"], 'BAD_MONTH: "13/31/2022" is not a calendar date', "exclude"),
  tx(903, 13, { month: "02/28/2023" }, ["month"], 'BAD_MONTH: "02/28/2023" is zero-padded. The format is non-padded M/D/YYYY', "exclude"),
  tx(1288, 17, { month: "6/15/2023" }, ["month"], 'BAD_MONTH: "6/15/2023" is not the last day of its month', "exclude"),
];

const TX_BAD_AMOUNT: DqRecord[] = [
  tx(77, 8, { amount: "12,5" }, ["amount"], 'BAD_AMOUNT: "12,5" is not a plain decimal number', "exclude"),
  tx(412, 11, { month: "13/31/2022", amount: "N/A" }, ["amount"], 'BAD_AMOUNT: "N/A" is not a plain decimal number', "exclude"),
  tx(640, 20, { amount: "abc" }, ["amount"], 'BAD_AMOUNT: "abc" is not a plain decimal number', "exclude"),
  tx(1011, 3, { amount: "" }, ["amount"], "BAD_AMOUNT: the amount is empty. No 0 or NULL is substituted", "exclude"),
  tx(1730, 27, { amount: "1e3" }, ["amount"], 'BAD_AMOUNT: "1e3" is not a plain decimal number', "exclude"),
];

const TX_PRECISION: DqRecord[] = [
  tx(88, 6, { amount: "6.3000001" }, ["amount"], "PRECISION: 7 decimals, the registered scale is 6. Nothing is rounded", "exclude"),
  tx(951, 19, { amount: "0.1234567" }, ["amount"], "PRECISION: 7 decimals, the registered scale is 6. Nothing is rounded", "exclude"),
  tx(1650, 31, { amount: "12.00000001" }, ["amount"], "PRECISION: 8 decimals, the registered scale is 6. Nothing is rounded", "exclude"),
];

/** 420 rows: more than one page at the maximum page size of 200. */
const TX_NEGATIVE: DqRecord[] = Array.from({ length: 420 }, (_, i) => {
  const planted: [number, number][] = [
    [94, 4],
    [94, 17],
    [322, 9],
  ];
  const [id, monthIndex] = planted[i] ?? [3 + ((i * 37) % 1900), (i * 11) % MONTH_COUNT];
  const amount = `-${plain(0.5 + ((i * 7919) % 4000) / 100)}`;
  return tx(id, monthIndex, { amount }, ["amount"], "NEGATIVE_AMOUNT: the amount is below zero. It stays in every sum and is not a paying month", "flag");
})
  .filter((record, index, all) => all.findIndex((other) => other.source_line === record.source_line) === index)
  .sort(bySourceLine);

const TX_MISSING_CUSTOMER_MONTHS: DqRecord[] = [
  ...Array.from({ length: 20 }, (_, i) => ({ id: 1204, m: 8 + i })),
  ...Array.from({ length: 14 }, (_, i) => ({ id: 1877, m: 2 + i })),
].map(({ id, m }) =>
  finding({ ID: String(id), month: ym(m) }, `MISSING_CUSTOMER_MONTH: customer ${id} has no row for ${ym(m)}. No amount is imputed`),
);

/** Customers whose history now has a hole (an excluded or a missing month). */
const HOLE_CUSTOMERS = [57, 77, 88, 118, 256, 412, 640, 733, 845, 903, 951, 1011, 1204, 1288, 1333, 1419, 1502, 1650, 1730, 1877];

const TX_COHORT_UNKNOWN: DqRecord[] = [1011, 256, 77].map((id) =>
  finding({ ID: String(id) }, `COHORT_UNKNOWN: customer ${id}'s first paid month sits next to a hole, so its cohort censoring is unknown`),
);

const TX_STATE_UNKNOWN: DqRecord[] = [412, 640, 1288, 1204, 1877, 57].flatMap((id, i) =>
  Array.from({ length: 4 }, (_, k) => {
    const m = 12 + ((i * 5 + k) % 18);
    return tx(id, m, {}, [], `STATE_UNKNOWN: the stretch around ${ym(m)} has a hole, so the lifecycle state is unknown`, "flag");
  }),
).sort(bySourceLine);

const TX_SETTLEMENT_HOLE: DqRecord[] = [
  finding({ ID: "903", month: "2023-03" }, "SETTLEMENT_HOLE: month p−1 (2023-02) is a hole, so the prepay and split tests cannot run"),
  finding({ ID: "57", month: "2023-03" }, "SETTLEMENT_HOLE: month p−1 (2023-02) is a hole, so the prepay and split tests cannot run"),
];

const TX_REACTIVATION_UNKNOWN: DqRecord[] = [
  tx(640, 23, {}, [], "REACTIVATION_UNKNOWN: this payment ends a stretch with a hole. It is paying, not a reactivation", "flag"),
  tx(1730, 29, {}, [], "REACTIVATION_UNKNOWN: this payment ends a stretch with a hole. It is paying, not a reactivation", "flag"),
];

const TX_OUTLIER_INCOMPLETE: DqRecord[] = HOLE_CUSTOMERS.map((id) =>
  finding({ ID: String(id) }, `OUTLIER_INCOMPLETE_HISTORY: customer ${id} has excluded or missing months, so its outlier test uses known-paid months only`),
);

const TX_MOVEMENT_UNKNOWN: DqRecord[] = [77, 412, 640, 1011, 1288, 1502].flatMap((id, i) =>
  [1, 12].map((offset) => {
    const m = Math.min(MONTH_COUNT - 1, 6 + i * 3 + offset);
    return tx(id, m, {}, [], `MOVEMENT_UNKNOWN: month t−${offset} is a hole, so expansion and contraction are NULL`, "flag");
  }),
).sort(bySourceLine);

const TX_FIRST_PAYMENT_UNKNOWN: DqRecord[] = [1011, 256].map((id) =>
  finding({ ID: String(id) }, `FIRST_PAYMENT_UNKNOWN: the month after customer ${id}'s first payment is a hole, so the first-payment ratio is NULL`),
);

/* ----------------------------------------------- planted failures: Industry */

const IND_EMPTY: DqRecord[] = [ind(1963, "", "", ["ID", "Industria"], "EMPTY_RECORD: every source column is empty", "exclude")];

const IND_BAD_ID: DqRecord[] = [
  ind(13, "cliente 12", "Retail", ["ID"], 'BAD_CUSTOMER_ID: "cliente 12" does not match ^Cliente [1-9][0-9]*$', "exclude"),
  ind(95, "Cliente 094", "Servicios profesionales", ["ID"], 'BAD_CUSTOMER_ID: "Cliente 094" does not match ^Cliente [1-9][0-9]*$ (leading zero)', "exclude"),
  ind(1500, "Cliente", "Salud", ["ID"], 'BAD_CUSTOMER_ID: "Cliente" has no customer number', "exclude"),
  ind(501, "Cliente 500", "Restaurantes", ["ID"], "DUPLICATE_CUSTOMER_ID: customer_id 500 is on lines 501 and 502. Every copy is excluded", "exclude"),
  ind(502, "Cliente 500", "Restaurantes", ["ID"], "DUPLICATE_CUSTOMER_ID: customer_id 500 is on lines 501 and 502. Every copy is excluded", "exclude"),
];

const IND_UNMAPPED: DqRecord[] = [
  ind(208, "Cliente 207", "Hotelería", ["Industria"], 'UNMAPPED_INDUSTRY: "Hotelería" is not one of the 6 registered values. Loaded as UNMAPPED', "flag"),
  ind(644, "Cliente 643", "Retial", ["Industria"], 'UNMAPPED_INDUSTRY: "Retial" is not one of the 6 registered values. Loaded as UNMAPPED', "flag"),
  ind(1187, "Cliente 1186", "Tecnologia ", ["Industria"], 'UNMAPPED_INDUSTRY: "Tecnologia " (no accent, trailing space) is not one of the 6 registered values. Loaded as UNMAPPED', "flag"),
  ind(1702, "Cliente 1701", "", ["Industria"], "UNMAPPED_INDUSTRY: the industry is empty. Loaded as UNMAPPED", "flag"),
];

const IND_NO_ROW: DqRecord[] = [12, 94, 500, 1499].map((id) =>
  finding({ ID: String(id) }, `NO_INDUSTRY_ROW: customer ${id} has revenue but no included Industry row. Its industry is UNKNOWN`),
);

const IND_REMOVED: DqRecord[] = [1958, 1959].map((id) =>
  finding({ ID: String(id) }, "REMOVED_KEY: delivered in the previous run, absent from this one"),
);

const IND_RESTATED: DqRecord[] = [
  ind(41, "Cliente 40", "Salud", ["Industria"], 'RESTATED_VALUE: Industria was "Retail" in the previous run', "flag"),
  ind(1311, "Cliente 1310", "Producción", ["Industria"], 'RESTATED_VALUE: Industria was "Tecnología" in the previous run', "flag"),
];

/* ---------------------------------------------- planted failures: S&M spend */

const SM_FIELD_COUNT: DqRecord[] = [
  sm(10, { PayrollExpenses: "$0.120,$0.050" }, SM_ALL, "FIELD_COUNT: the line has 9 fields, the registry has 8", "exclude"),
];

const SM_BAD_MONTH: DqRecord[] = [sm(18, { Month: "2023-7" }, ["Month"], 'BAD_MONTH: "2023-7" does not match YYYY-MM', "exclude")];

// A reason never quotes an HR-sensitive value (Team, PayrollExpenses, Freelance).
const SM_BAD_SPEND: DqRecord[] = [
  sm(7, { PaidMedia: "1.380" }, ["PaidMedia"], 'BAD_SPEND_CELL: PaidMedia "1.380" has no $ prefix', "exclude"),
  sm(13, { Team: "$0,443" }, ["Team"], "BAD_SPEND_CELL: Team does not match the $0.000 format", "exclude"),
];

const SM_GAP: DqRecord[] = [
  finding({ Month: "2023-07" }, "MONTH_GAP: no valid source line carries 2023-07. It stays absent and is never zero-filled"),
];

const SM_NOT_IN_DATASET: DqRecord[] = [7, 10, 13, 18].map((m) =>
  finding({ month: ym(m) }, `MONTH_NOT_IN_DATASET: ${ym(m)} has Transactions rows but no included S&M line`),
);

const SM_RESTATED: DqRecord[] = [sm(27, {}, ["PaidMedia"], "RESTATED_VALUE: PaidMedia differs from the previous run", "flag")];

const SM_NEGATIVE: DqRecord[] = Object.keys(NEGATIVE_PAYROLL).map((m) =>
  sm(Number(m), {}, ["PayrollExpenses"], "NEGATIVE_SPEND: PayrollExpenses is below zero. The sign is kept; its nature is unconfirmed", "flag"),
);

const SM_TRIPWIRE: DqRecord[] = [
  sm(32, {}, ["PaidMedia", "Travel", "PublicidadNoWeb", "Freelance", "SoftwareTools", "Team", "PayrollExpenses"], "UNIT_TRIPWIRE: S&M is 23.4 × revenue for 2024-09, outside [0.5, 20]", "flag"),
];

/* --------------------------------------------------------------- rules */

interface EvalContext {
  rows: number;
  months: number;
  /** Rows that failed CDO-01. */
  cdo01: number;
  /** Rows that failed CDO-01 or SQ-02. */
  stageA2: number;
  /** Rows that failed any stage-A rule. */
  stageA: number;
  excluded: number;
  firstRun: boolean;
  /** Failures of a named rule on this dataset in this run. */
  failedOf: (ruleId: string) => number;
}

interface CellDef {
  records: DqRecord[];
  /** Items evaluated. Defaults to the rows read. */
  evaluated?: (ctx: EvalContext) => number;
}

interface RuleDef {
  rule_id: string;
  title: string;
  description: string;
  layer: string;
  kind: RuleKind;
  action: RuleAction;
  inferred: boolean;
  counts: boolean;
  /** One entry per dataset the rule applies to. */
  cells: Record<string, CellDef>;
}

const none: CellDef = { records: [] };
const passA = (ctx: EvalContext) => ctx.rows - ctx.stageA;
const included = (ctx: EvalContext) => ctx.rows - ctx.excluded;
const customers = () => CUSTOMERS;
const previousKeys = (keys: (ctx: EvalContext) => number) => (ctx: EvalContext) => (ctx.firstRun ? 0 : keys(ctx));

const RULE_DEFS: RuleDef[] = [
  /* ---- silver quality: stage A, structure */
  {
    rule_id: "CDO-01",
    title: "Line is valid UTF-8, no control chars",
    description:
      "The bytes of each data record decode as strict UTF-8 (the BOM is stripped from record 1 only) and contain no C0 control character U+0000–U+001F. The line terminator is not part of the record. A failing row is excluded with `UNDECODABLE_LINE` or `CONTROL_CHAR` and is evaluated by no other rule.",
    layer: "silver_quality",
    kind: "row",
    action: "exclude",
    inferred: false,
    counts: true,
    cells: { transactions: { records: TX_CONTROL_CHAR }, industry: none, sm_spend: none },
  },
  {
    rule_id: "SQ-02",
    title: "Empty records",
    description:
      "A data record whose fields are all zero-length (a blank line, `,`, `,,` and so on) is excluded with `EMPTY_RECORD` and is evaluated by no other rule. It is tested before SQ-01. Every empty record is a failure: none is \"expected\".",
    layer: "silver_quality",
    kind: "row",
    action: "exclude",
    inferred: false,
    counts: true,
    cells: {
      transactions: { records: [], evaluated: (c) => c.rows - c.cdo01 },
      industry: { records: IND_EMPTY, evaluated: (c) => c.rows - c.cdo01 },
      sm_spend: { records: [], evaluated: (c) => c.rows - c.cdo01 },
    },
  },
  {
    rule_id: "SQ-01",
    title: "Line has the registered field count",
    description:
      "Fields are split on every `,` with no quote handling and no trimming, and columns are assigned by position. A data record that does not split into exactly 3 (`transactions`), 2 (`industry`) or 8 (`sm_spend`) fields is excluded with `FIELD_COUNT` and is evaluated by no other rule.",
    layer: "silver_quality",
    kind: "row",
    action: "exclude",
    inferred: false,
    counts: true,
    cells: {
      transactions: { records: TX_FIELD_COUNT, evaluated: (c) => c.rows - c.stageA2 },
      industry: { records: [], evaluated: (c) => c.rows - c.stageA2 },
      sm_spend: { records: SM_FIELD_COUNT, evaluated: (c) => c.rows - c.stageA2 },
    },
  },
  /* ---- silver quality: stage B, cells and keys */
  {
    rule_id: "SQ-03",
    title: "Customer ID valid and unique",
    description:
      "(a) `ID` matches `^Cliente [1-9][0-9]*$` and yields the integer `customer_id`; otherwise the row is excluded with `BAD_CUSTOMER_ID`. (b) The derived `customer_id` is unique among rows that pass (a); otherwise every copy is excluded with `DUPLICATE_CUSTOMER_ID`, identical copies included. The pipeline never picks a winner.",
    layer: "silver_quality",
    kind: "row",
    action: "exclude",
    inferred: false,
    counts: true,
    cells: { industry: { records: IND_BAD_ID, evaluated: passA } },
  },
  {
    rule_id: "SQ-04",
    title: "Industry outside the registered list",
    description:
      "On included rows, `Industria` is normalized to Unicode NFC and mapped to one of the 6 registered values: Restaurantes, Producción, Retail, Tecnología, Servicios profesionales, Salud. Any other value, an empty one included, keeps its row in silver with `industry_code` = `UNMAPPED` and the raw value kept; reason `UNMAPPED_INDUSTRY`.",
    layer: "silver_quality",
    kind: "row",
    action: "flag",
    inferred: true,
    counts: false,
    cells: { industry: { records: IND_UNMAPPED, evaluated: included } },
  },
  {
    rule_id: "SQ-05",
    title: "Customer-month key valid and unique",
    description:
      "(a) `ID` matches `^[1-9][0-9]*$` and yields `customer_id`; otherwise the row is excluded with `BAD_ID`. (b) (`customer_id`, month) is unique among rows whose `ID` and `month` both parse, whatever their amount; otherwise every copy is excluded with `DUPLICATE_KEY`.",
    layer: "silver_quality",
    kind: "row",
    action: "exclude",
    inferred: false,
    counts: true,
    cells: { transactions: { records: TX_KEY, evaluated: passA } },
  },
  {
    rule_id: "SQ-06",
    title: "Month is a month-end date",
    description:
      "`month` matches the non-padded month/day/year pattern, is a real calendar date and is the last day of its month. It is converted to `YYYY-MM`. A padded date (`01/31/2022`), another format or a day that is not month-end is excluded with `BAD_MONTH`.",
    layer: "silver_quality",
    kind: "row",
    action: "exclude",
    inferred: false,
    counts: true,
    cells: { transactions: { records: TX_BAD_MONTH, evaluated: passA } },
  },
  {
    rule_id: "SQ-07a",
    title: "Amount is a plain decimal number",
    description:
      "`amount` matches `^-?[0-9]+(\\.[0-9]+)?$`; otherwise the row is excluded with `BAD_AMOUNT`. `1e3`, `NaN`, `Infinity`, `+5`, `.5`, `5.`, `1,5`, an empty value and any space all fail. No NULL or 0 is ever substituted.",
    layer: "silver_quality",
    kind: "row",
    action: "exclude",
    inferred: false,
    counts: true,
    cells: { transactions: { records: TX_BAD_AMOUNT, evaluated: passA } },
  },
  {
    rule_id: "SQ-09a",
    title: "Month valid and unique",
    description:
      "`Month` matches `^[0-9]{4}-(0[1-9]|1[0-2])$`; otherwise the line is excluded with `BAD_MONTH`. A `Month` repeated among lines that pass the pattern excludes every copy with `DUPLICATE_MONTH`.",
    layer: "silver_quality",
    kind: "row",
    action: "exclude",
    inferred: false,
    counts: true,
    cells: { sm_spend: { records: SM_BAD_MONTH, evaluated: passA } },
  },
  {
    rule_id: "SQ-10",
    title: "Spend cells match the $0.000 format",
    description:
      "Each of the 7 spend cells matches `^-?\\$[0-9]{1,6}\\.[0-9]{3}$`. The `$` is stripped and the sign is kept. If any cell fails, the whole month line is excluded with `BAD_SPEND_CELL`, and `failed_columns` lists the failing cells.",
    layer: "silver_quality",
    kind: "row",
    action: "exclude",
    inferred: false,
    counts: true,
    cells: { sm_spend: { records: SM_BAD_SPEND, evaluated: passA } },
  },
  {
    rule_id: "CDO-05",
    title: "Value fits its registered precision",
    description:
      "Money is DECIMAL, never float: `amount` DECIMAL(12,6) → `amount_value` DECIMAL(18,2); spend DECIMAL(12,3) → `spend_value` DECIMAL(18,0). Nothing is rounded, truncated or widened. A Transactions row whose `amount` needs more than 6 decimal places or more than 6 integer digits is excluded with `PRECISION`. For `sm_spend` the spend pattern already limits a cell, so the rule cannot fail there.",
    layer: "silver_quality",
    kind: "row",
    action: "exclude",
    inferred: false,
    counts: true,
    cells: {
      transactions: { records: TX_PRECISION, evaluated: (c) => passA(c) - c.failedOf("SQ-07a") },
      sm_spend: { records: [], evaluated: (c) => passA(c) - c.failedOf("SQ-10") },
    },
  },
  /* ---- silver quality: stage C, row flags */
  {
    rule_id: "SQ-07b",
    title: "Negative amount",
    description:
      "On included rows, an amount below 0 keeps its row in silver with `is_negative_amount` = true; it stays in every sum and is not a paying month; reason `NEGATIVE_AMOUNT`.",
    layer: "silver_quality",
    kind: "row",
    action: "flag",
    inferred: true,
    counts: false,
    cells: { transactions: { records: TX_NEGATIVE, evaluated: included } },
  },
  {
    rule_id: "CDO-06b",
    title: "Values restated since previous run",
    description:
      "An included row whose key was included in the previous run with a different typed value (the amount; the NFC `Industria`; any spend cell) stays in silver with `is_restated` = true, reason `RESTATED_VALUE`, and its old and new values go to the restatement log. On a dataset's first run, evaluated = 0 and the status is `na`.",
    layer: "silver_quality",
    kind: "row",
    action: "flag",
    inferred: true,
    counts: false,
    cells: {
      transactions: { records: [], evaluated: previousKeys((c) => included(c) - 1961) },
      industry: { records: IND_RESTATED, evaluated: previousKeys(included) },
      sm_spend: { records: SM_RESTATED, evaluated: previousKeys((c) => included(c) - 1) },
    },
  },
  /* ---- silver quality: stage D, findings */
  {
    rule_id: "SQ-08",
    title: "Missing customer-months",
    description:
      "The delivery is expected to be a dense panel. A finding `MISSING_CUSTOMER_MONTH` is recorded for each panel cell (customers × months) that no source row carries. A cell whose rows were excluded is also a hole, but it is counted under the rule that excluded it, not here. Nothing is imputed.",
    layer: "silver_quality",
    kind: "finding",
    action: "finding",
    inferred: true,
    counts: true,
    cells: { transactions: { records: TX_MISSING_CUSTOMER_MONTHS, evaluated: (c) => CUSTOMERS * c.months } },
  },
  {
    rule_id: "SQ-09b",
    title: "Missing months in the series",
    description:
      "A finding `MONTH_GAP` is recorded for each calendar month between the earliest and the latest included month that no source line carries. The month stays absent and is never zero-filled.",
    layer: "silver_quality",
    kind: "finding",
    action: "finding",
    inferred: true,
    counts: true,
    cells: { sm_spend: { records: SM_GAP, evaluated: (c) => c.months } },
  },
  {
    rule_id: "SQ-12",
    title: "Customers with no Industry row",
    description:
      "A finding `NO_INDUSTRY_ROW` is recorded, against `industry`, for each `customer_id` in included Transactions rows that has no included Industry row. In silver that customer has `industry_code` = `UNKNOWN`. No Transactions row is excluded, flagged or changed.",
    layer: "silver_quality",
    kind: "finding",
    action: "finding",
    inferred: true,
    counts: false,
    cells: { industry: { records: IND_NO_ROW, evaluated: customers } },
  },
  {
    rule_id: "SQ-13",
    title: "Month covered by only one dataset",
    description:
      "The two money datasets are expected to cover the same months. A finding `MONTH_NOT_IN_DATASET` is recorded for each month that has at least one included row in one of them and none in the other, against the dataset that lacks it.",
    layer: "silver_quality",
    kind: "finding",
    action: "finding",
    inferred: true,
    counts: false,
    cells: {
      transactions: { records: [], evaluated: (c) => c.months },
      sm_spend: { records: SM_NOT_IN_DATASET, evaluated: (c) => c.months },
    },
  },
  {
    rule_id: "CDO-06a",
    title: "Keys removed since the previous run",
    description:
      "Each delivery is treated as a full snapshot and compared with the previous succeeded run of the same dataset. A finding `REMOVED_KEY` is recorded for each key delivered in the previous run and not delivered now. On a dataset's first run, evaluated = 0 and the status is `na`.",
    layer: "silver_quality",
    kind: "finding",
    action: "finding",
    inferred: true,
    counts: true,
    cells: {
      transactions: { records: [], evaluated: previousKeys((c) => c.rows - 1961) },
      industry: { records: IND_REMOVED, evaluated: previousKeys(() => 1961) },
      sm_spend: { records: [], evaluated: previousKeys((c) => c.rows - 1) },
    },
  },
  /* ---- silver business */
  {
    rule_id: "SB-04",
    title: "Cohort and left-censoring",
    description:
      "`cohort_month` is the customer's first known-paid month. `cohort_censoring` is `left`, `unknown` (a hole next to the first payment), `probable_left` or `none`; only `none` is a new logo. A finding `COHORT_UNKNOWN` is recorded for each customer with `unknown`.",
    layer: "silver_business",
    kind: "finding",
    action: "finding",
    inferred: true,
    counts: false,
    cells: { transactions: { records: TX_COHORT_UNKNOWN, evaluated: customers } },
  },
  {
    rule_id: "SB-05",
    title: "Churn after 3 unpaid months",
    description:
      "A churn spell is an unsettled clean stretch of at least 3 unpaid months after the first known-paid month. A clean trailing stretch of 1–2 unpaid months is `grace`. An included row inside a stretch with a hole has state `unknown` and is flagged `STATE_UNKNOWN`.",
    layer: "silver_business",
    kind: "row",
    action: "flag",
    inferred: true,
    counts: false,
    cells: { transactions: { records: TX_STATE_UNKNOWN, evaluated: included } },
  },
  {
    rule_id: "SB-06",
    title: "Settled gaps: arrears, prepay, split",
    description:
      "A gap is a clean internal stretch of unpaid months between two known-paid months. The arrears, prepay and split tests run in that order and the first match settles the gap. A finding `SETTLEMENT_HOLE` is recorded for each gap whose month before the first payment is a hole.",
    layer: "silver_business",
    kind: "finding",
    action: "finding",
    inferred: true,
    counts: false,
    cells: { transactions: { records: TX_SETTLEMENT_HOLE, evaluated: () => 468 } },
  },
  {
    rule_id: "SB-07",
    title: "Reactivation versus pause",
    description:
      "The first known-paid month that ends an internal churn spell is `reactivated`. A stretch of 1–2 unpaid months is `paused`. A known-paid month that ends a stretch with a hole is `paying` and is flagged `REACTIVATION_UNKNOWN`.",
    layer: "silver_business",
    kind: "row",
    action: "flag",
    inferred: true,
    counts: false,
    cells: { transactions: { records: TX_REACTIVATION_UNKNOWN, evaluated: () => 468 } },
  },
  {
    rule_id: "SB-08",
    title: "Outlier customers",
    description:
      "`is_outlier_customer` is true when the customer has at least 3 known-paid amounts and their median is ≥ 25 × the portfolio median. Outliers are never removed from silver. A finding `OUTLIER_INCOMPLETE_HISTORY` is recorded for each customer with excluded or missing months.",
    layer: "silver_business",
    kind: "finding",
    action: "finding",
    inferred: true,
    counts: false,
    cells: { transactions: { records: TX_OUTLIER_INCOMPLETE, evaluated: customers } },
  },
  {
    rule_id: "SB-10",
    title: "Negative spend",
    description:
      "Spend keeps its sign as received. It is never made absolute, clipped, floored or reclassified. A negative cell has `is_negative_spend` = true, and its line is flagged with `NEGATIVE_SPEND` and the negative columns in `failed_columns`. Its nature is unconfirmed: an adjustment and a budget plug are both possible.",
    layer: "silver_business",
    kind: "row",
    action: "flag",
    inferred: true,
    counts: false,
    cells: { sm_spend: { records: SM_NEGATIVE, evaluated: included } },
  },
  {
    rule_id: "CDO-08",
    title: "Unit tripwire: S&M ÷ revenue",
    description:
      "For each month with included rows in both money datasets, S&M at full amount (S) is compared with revenue at full amount (R). The tripwire fires when R ≤ 0, S < 0.5 × R or S > 20 × R. The S&M line of that month is flagged with `UNIT_TRIPWIRE`, and Data and Finance are alerted.",
    layer: "silver_business",
    kind: "row",
    action: "flag",
    inferred: true,
    counts: false,
    cells: { sm_spend: { records: SM_TRIPWIRE, evaluated: included } },
  },
  {
    rule_id: "CRO-05",
    title: "Expansion and contraction proxy",
    description:
      "Δ = `amount_normalized`(t) − `amount_normalized`(t−1), computed only when the customer is `paying` in both months. `expansion_amount` = max(Δ, 0) and `contraction_amount` = max(−Δ, 0). An included row whose values are NULL because month t−1 or t−12 is a hole is flagged `MOVEMENT_UNKNOWN`.",
    layer: "silver_business",
    kind: "row",
    action: "flag",
    inferred: true,
    counts: false,
    cells: { transactions: { records: TX_MOVEMENT_UNKNOWN, evaluated: included } },
  },
  {
    rule_id: "CRO-07",
    title: "First-month spike",
    description:
      "`is_first_month_spike` = first paid amount ≥ 1.9 × next paid amount; `first_payment_band` is `<1.9`, `1.9–3` or `≥3`. They are descriptive and never remove a logo. A finding `FIRST_PAYMENT_UNKNOWN` is recorded for each customer whose month after the first payment is a hole.",
    layer: "silver_business",
    kind: "finding",
    action: "finding",
    inferred: true,
    counts: false,
    cells: { transactions: { records: TX_FIRST_PAYMENT_UNKNOWN, evaluated: customers } },
  },
];

/* ---------------------------------------------------------- run builds */

/** HALF_UP to 2 decimals, never 100 with a failure, never 0 with a pass (DQ metric definitions). */
export function compliancePct(evaluated: number, failed: number): number | null {
  if (evaluated <= 0) return null;
  const raw = ((evaluated - failed) / evaluated) * 100;
  let pct = Math.floor(raw * 100 + 0.5 + 1e-9) / 100;
  if (failed > 0 && pct >= 100) pct = 99.99;
  if (failed < evaluated && pct <= 0) pct = 0.01;
  return pct;
}

/** Status thresholds from the rules document: 100 for pass, 99 for warn on a counting rule. */
export function statusFor(evaluated: number, failed: number, counts: boolean): CellStatus {
  if (evaluated <= 0) return "na";
  if (failed === 0) return "pass";
  const raw = ((evaluated - failed) / evaluated) * 100;
  return !counts || raw >= 99 ? "warn" : "fail";
}

interface BuiltRun {
  run: Run;
  summaryBase: Omit<Summary, "trend">;
  records: Map<string, DqRecord[]>;
}

function recordsKey(ruleId: string, datasetId: string): string {
  return `${ruleId}|${datasetId}`;
}

function distinctLines(lists: DqRecord[][]): Set<number> {
  const lines = new Set<number>();
  for (const list of lists) for (const record of list) if (record.source_line !== null) lines.add(record.source_line);
  return lines;
}

function buildRun(def: RunDef, firstRun: boolean): BuiltRun {
  const run = toRun(def);
  const records = new Map<string, DqRecord[]>();

  // 1. Which planted failures exist in this run.
  for (const rule of RULE_DEFS) {
    for (const [datasetId, cell] of Object.entries(rule.cells)) {
      const rows = run.datasets[datasetId]?.rows_read ?? 0;
      let eligible = cell.records.filter((r) => r.source_line === null || r.source_line <= rows + 1);
      // A first run has nothing to compare with.
      if (firstRun && rule.rule_id.startsWith("CDO-06")) eligible = [];
      if (def.clean?.includes(rule.rule_id)) eligible = [];
      const count = Math.ceil(eligible.length * (def.share[datasetId] ?? 1));
      records.set(
        recordsKey(rule.rule_id, datasetId),
        eligible.slice(0, count).map((r) => ({ ...r, key: { ...r.key }, values: { ...r.values } })),
      );
    }
  }

  // 2. Cross-reference: the other rules the same source line failed.
  const byLine = new Map<string, Set<string>>();
  for (const [key, list] of records) {
    const [ruleId = "", datasetId = ""] = key.split("|");
    for (const record of list) {
      if (record.source_line === null) continue;
      const lineKey = `${datasetId}|${record.source_line}`;
      const rules = byLine.get(lineKey) ?? new Set<string>();
      rules.add(ruleId);
      byLine.set(lineKey, rules);
    }
  }
  for (const [key, list] of records) {
    const [ruleId = "", datasetId = ""] = key.split("|");
    for (const record of list) {
      if (record.source_line === null) continue;
      const rules = byLine.get(`${datasetId}|${record.source_line}`) ?? new Set<string>();
      record.other_failed_rules = [...rules].filter((id) => id !== ruleId).sort();
    }
  }

  // 3. Per-dataset context, then rule results.
  const contexts = new Map<string, EvalContext>();
  for (const dataset of DATASETS) {
    const of = (ruleId: string) => records.get(recordsKey(ruleId, dataset.id)) ?? [];
    const excludeRules = RULE_DEFS.filter((rule) => rule.action === "exclude" && rule.cells[dataset.id]);
    contexts.set(dataset.id, {
      rows: run.datasets[dataset.id]?.rows_read ?? 0,
      months: MONTH_COUNT - def.monthsBack,
      cdo01: of("CDO-01").length,
      stageA2: of("CDO-01").length + of("SQ-02").length,
      stageA: [...STAGE_A_RULES].reduce((sum, id) => sum + of(id).length, 0),
      excluded: distinctLines(excludeRules.map((rule) => of(rule.rule_id))).size,
      firstRun,
      failedOf: (ruleId) => of(ruleId).length,
    });
  }

  const rules: Rule[] = RULE_DEFS.map((rule) => {
    const results: Record<string, RuleResult> = {};
    for (const dataset of DATASETS) {
      const cell = rule.cells[dataset.id];
      const ctx = contexts.get(dataset.id);
      if (!cell || !ctx) {
        results[dataset.id] = { evaluated: 0, failed: 0, compliance_pct: null, status: "na" };
        continue;
      }
      const failed = records.get(recordsKey(rule.rule_id, dataset.id))?.length ?? 0;
      const evaluated = Math.max(0, cell.evaluated ? cell.evaluated(ctx) : ctx.rows);
      results[dataset.id] = {
        evaluated,
        failed: evaluated > 0 ? failed : 0,
        compliance_pct: compliancePct(evaluated, failed),
        status: statusFor(evaluated, failed, rule.counts),
      };
    }
    return {
      rule_id: rule.rule_id,
      title: rule.title,
      description: rule.description,
      layer: rule.layer,
      kind: rule.kind,
      action: rule.action,
      inferred: rule.inferred,
      counts_toward_compliance: rule.counts,
      applies_to: DATASETS.filter((d) => rule.cells[d.id]).map((d) => d.id),
      results,
    };
  });

  // 4. Department scorecards and the rank (DQ metric definitions).
  const unranked = DATASETS.map((dataset, order) => {
    const ctx = contexts.get(dataset.id);
    const rows = ctx?.rows ?? 0;
    const excluded = ctx?.excluded ?? 0;
    const flagRules = RULE_DEFS.filter((rule) => rule.kind === "row" && rule.action === "flag" && rule.cells[dataset.id]);
    const flagged = distinctLines(flagRules.map((rule) => records.get(recordsKey(rule.rule_id, dataset.id)) ?? [])).size;
    const counting = rules.filter(
      (rule) =>
        rule.counts_toward_compliance &&
        rule.applies_to.includes(dataset.id) &&
        (rule.results[dataset.id]?.evaluated ?? 0) > 0,
    );
    return {
      order,
      raw: rows > 0 ? (rows - excluded) / rows : -1,
      summary: {
        dataset_id: dataset.id,
        label: dataset.label,
        rows_read: rows,
        rows_excluded: excluded,
        rows_flagged: flagged,
        row_compliance_pct: compliancePct(rows, excluded) ?? 0,
        rules_evaluated: counting.length,
        rules_failing: counting.filter((rule) => (rule.results[dataset.id]?.failed ?? 0) > 0).length,
      },
    };
  });
  const datasets: DatasetSummary[] = [...unranked]
    .sort(
      (a, b) =>
        b.raw - a.raw ||
        a.summary.rules_failing - b.summary.rules_failing ||
        a.summary.rows_flagged / Math.max(1, a.summary.rows_read) - b.summary.rows_flagged / Math.max(1, b.summary.rows_read) ||
        a.order - b.order,
    )
    .map((entry, index) => ({ ...entry.summary, rank: index + 1 }));

  return { run, summaryBase: { run, datasets, rules }, records };
}

const BUILT = new Map<string, BuiltRun>();
RUN_DEFS.filter((def) => def.status === "succeeded").forEach((def, index) => BUILT.set(def.id, buildRun(def, index === 0)));

/** Newest first, as `GET /api/dq/runs` returns them. */
export const RUNS: Run[] = [...RUN_DEFS].reverse().map(toRun);

export const LATEST_RUN_ID: string = RUNS.find((run) => run.status === "succeeded")?.run_id ?? "";

/** Oldest first, every succeeded run. */
const TREND: TrendPoint[] = RUN_DEFS.filter((def) => BUILT.has(def.id)).map((def) => {
  const built = BUILT.get(def.id);
  const point: TrendPoint = { run_id: def.id, as_of_month: def.asOfMonth };
  for (const dataset of built?.summaryBase.datasets ?? []) point[dataset.dataset_id] = dataset.row_compliance_pct;
  return point;
});

export function resolveRunId(run: string | null): string | null {
  if (!run || run === "latest") return LATEST_RUN_ID;
  return BUILT.has(run) ? run : null;
}

export function summaryFor(runId: string): Summary | null {
  const built = BUILT.get(runId);
  if (!built) return null;
  // The trend ends at the requested run.
  const end = TREND.findIndex((point) => point.run_id === runId);
  return { ...built.summaryBase, trend: TREND.slice(0, end + 1).slice(-24) };
}

/** `null` for an unknown run, or a rule that does not apply to the dataset. */
export function recordsFor(runId: string, ruleId: string, datasetId: string): DqRecord[] | null {
  return BUILT.get(runId)?.records.get(recordsKey(ruleId, datasetId)) ?? null;
}
