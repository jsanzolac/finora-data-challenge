/**
 * The lever planner, docs/gold_acquisition_model.md §16.3 (contract v1.3). Exact
 * fractions, HALF_UP at each step, from the published period row:
 *
 *   Won′          = won_per_month × f                         (6 dp)
 *   run-rate′     = (run_rate_mrr_per_won_value + Δmix) × (1 + t)   (2 dp)
 *   new MRR′      = Won′ × run-rate′                          (2 dp)
 *   cost per Won′ = cost_per_won_value × (1 + g) ÷ f          (2 dp)
 *   payback′      = cost per Won′ ÷ run-rate′                 (1 dp)
 *
 * f = overall(s) ÷ overall(base) (conversion, Assumption); Δmix = p/100 × (v_B − v_A)
 * at the period's observed per-industry run-rates (Observed); t = ticket (Observed
 * baseline, the target is the user's); g = spend (Untested on Won: Won held flat).
 * With every lever at rest it reproduces the gold baseline exactly.
 */
import { Ratio } from "./ratio";
import type { LeverCohort, LeverIndustry, LeverPeriod, Levers, SignalSummaryRow, ValueChangeRow, WonDefinition } from "./types";
import { leverDefinition } from "./types";

export type Evidence = "observed" | "assumption" | "untested";

const HUNDRED = Ratio.of(100n);

function round(value: Ratio, places: number): Ratio {
  return Ratio.parse(value.toFixed(places));
}

export interface Baseline {
  period: LeverPeriod;
  wonPerMonth: Ratio;
  runRate: Ratio;
  newMrr: Ratio;
  costPerWon: Ratio | null;
  payback: Ratio | null;
}

export function periodRows(levers: Levers | undefined, definition: WonDefinition): LeverPeriod[] {
  return (levers?.periods ?? []).filter((row) => row.won_definition === leverDefinition(definition));
}

export function baselineOf(row: LeverPeriod | undefined): Baseline | null {
  if (!row) return null;
  const runRate = Ratio.tryParse(row.run_rate_mrr_per_won_value);
  const newMrr = Ratio.tryParse(row.new_mrr_per_month_value);
  const wonPerMonth = Ratio.tryParse(row.won_per_month);
  if (!runRate || !newMrr || !wonPerMonth || runRate.sign() <= 0) return null;
  return {
    period: row,
    wonPerMonth,
    runRate,
    newMrr,
    costPerWon: Ratio.tryParse(row.cost_per_won_value),
    payback: Ratio.tryParse(row.payback_months),
  };
}

export function baselineFor(levers: Levers | undefined, definition: WonDefinition, periodCode: string): Baseline | null {
  return baselineOf(periodRows(levers, definition).find((row) => row.period_code === periodCode));
}

export interface MixMove {
  /** Share points moved, 0-100. */
  points: Ratio;
  fromRunRate: Ratio;
  toRunRate: Ratio;
}

export interface LeverInputs {
  /** f = overall(s) ÷ overall(base). */
  volume: Ratio;
  /** t, percent. */
  ticketPct: Ratio;
  mix: MixMove | null;
  /** g, percent. */
  spendPct: Ratio;
}

export const AT_REST: LeverInputs = { volume: Ratio.ONE, ticketPct: Ratio.ZERO, mix: null, spendPct: Ratio.ZERO };

export interface Plan {
  wonPerMonth: Ratio;
  runRate: Ratio;
  newMrr: Ratio;
  newMrrDelta: Ratio;
  costPerWon: Ratio | null;
  payback: Ratio | null;
  /** The weakest label among the levers moved; null when none moved. */
  evidence: Evidence | null;
}

const STRENGTH: Record<Evidence, number> = { observed: 2, assumption: 1, untested: 0 };

export function weakest(labels: Evidence[]): Evidence | null {
  return labels.length === 0 ? null : labels.reduce((a, b) => (STRENGTH[b] < STRENGTH[a] ? b : a));
}

export function deltaMix(move: MixMove): Ratio {
  return move.points.div(HUNDRED).mul(move.toRunRate.sub(move.fromRunRate));
}

export function plan(base: Baseline, inputs: LeverInputs): Plan {
  const wonPerMonth = round(base.wonPerMonth.mul(inputs.volume), 6);
  const mixed = inputs.mix ? base.runRate.add(deltaMix(inputs.mix)) : base.runRate;
  const runRate = round(mixed.mul(Ratio.ONE.add(inputs.ticketPct.div(HUNDRED))), 2);
  const newMrr = round(wonPerMonth.mul(runRate), 2);
  const costPerWon =
    base.costPerWon && !inputs.volume.isZero() ? round(base.costPerWon.mul(Ratio.ONE.add(inputs.spendPct.div(HUNDRED))).div(inputs.volume), 2) : null;
  const moved: Evidence[] = [];
  if (!inputs.volume.equals(Ratio.ONE)) moved.push("assumption");
  if (!inputs.ticketPct.isZero() || (inputs.mix && !inputs.mix.points.isZero())) moved.push("observed");
  if (!inputs.spendPct.isZero()) moved.push("untested");
  return {
    wonPerMonth,
    runRate,
    newMrr,
    newMrrDelta: newMrr.sub(base.newMrr),
    costPerWon,
    payback: costPerWon && runRate.sign() > 0 ? round(costPerWon.div(runRate), 1) : null,
    evidence: weakest(moved),
  };
}

/** The period's industries with a run-rate, highest first; `is_low_n` cells cannot be moved (§16.3). */
export function industryRows(levers: Levers | undefined, definition: WonDefinition, periodCode: string): (LeverIndustry & { runRate: Ratio })[] {
  return (levers?.industries ?? [])
    .filter((row) => row.won_definition === leverDefinition(definition) && row.period_code === periodCode && !row.is_low_n)
    .map((row) => ({ ...row, runRate: Ratio.tryParse(row.run_rate_mrr_per_won_value) }))
    .filter((row): row is LeverIndustry & { runRate: Ratio } => row.runRate !== null)
    .sort((a, b) => b.runRate.compare(a.runRate));
}

export interface ValueChangeTotals {
  from: string;
  to: string;
  mix: Ratio;
  within: Ratio;
  total: Ratio;
  mixReverse: Ratio;
  withinReverse: Ratio;
  rows: ValueChangeRow[];
}

/** Totals of agg_acq_value_change = Σ terms, HALF_UP 2 dp; null when any row has a null_reason. */
export function valueChange(levers: Levers | undefined, definition: WonDefinition): ValueChangeTotals | null {
  const rows = (levers?.value_change ?? []).filter((row) => row.won_definition === leverDefinition(definition));
  if (rows.length === 0 || rows.some((row) => row.null_reason)) return null;
  const sum = (field: "mix_term_value" | "within_term_value" | "mix_reverse_term_value" | "within_reverse_term_value") => {
    let total = Ratio.ZERO;
    for (const row of rows) {
      const value = Ratio.tryParse(row[field]);
      if (!value) return null;
      total = total.add(value);
    }
    return total;
  };
  const mix = sum("mix_term_value");
  const within = sum("within_term_value");
  const mixReverse = sum("mix_reverse_term_value");
  const withinReverse = sum("within_reverse_term_value");
  if (!mix || !within || !mixReverse || !withinReverse) return null;
  // Each total is rounded from the unrounded sum, so total = v̄₁ − v̄₀ (it may differ by a cent from the rounded parts).
  return {
    from: rows[0]!.from_period_code,
    to: rows[0]!.to_period_code,
    mix: round(mix, 2),
    within: round(within, 2),
    total: round(mix.add(within), 2),
    mixReverse: round(mixReverse, 2),
    withinReverse: round(withinReverse, 2),
    rows,
  };
}

/**
 * §16.5: "each industry at its pre-period run-rate and today's run-rate shares" =
 * today's run-rate − within-industry change (55,208.80 today), as a % over today (+29.7%).
 */
export function ticketReference(levers: Levers | undefined, definition: WonDefinition): { level: Ratio; pct: Ratio } | null {
  const change = valueChange(levers, definition);
  const today = change ? baselineFor(levers, definition, change.to) : null;
  if (!change || !today) return null;
  const level = today.runRate.sub(change.within);
  return { level, pct: level.div(today.runRate).sub(Ratio.ONE).mul(HUNDRED) };
}

export interface RankedLever {
  lever: "ticket" | "conversion" | "mix" | "spend";
  /** Change in new MRR a month for a comparable 10% move; null when not measurable. */
  delta: Ratio | null;
  evidence: Evidence;
}

/** "Biggest levers for a 10% move", computed with plan(): largest first, ties to the stronger evidence. */
export function rankLevers(base: Baseline, lowest: Ratio | null, highest: Ratio | null): RankedLever[] {
  const ten = Ratio.of(10n);
  const rows: RankedLever[] = [
    { lever: "ticket", delta: plan(base, { ...AT_REST, ticketPct: ten }).newMrrDelta, evidence: "observed" },
    { lever: "conversion", delta: plan(base, { ...AT_REST, volume: Ratio.parse("1.1") }).newMrrDelta, evidence: "assumption" },
    {
      lever: "mix",
      delta: lowest && highest ? plan(base, { ...AT_REST, mix: { points: ten, fromRunRate: lowest, toRunRate: highest } }).newMrrDelta : null,
      evidence: "observed",
    },
    { lever: "spend", delta: null, evidence: "untested" },
  ];
  return rows.sort((a, b) => {
    if (a.delta && b.delta) {
      const byValue = b.delta.compare(a.delta);
      if (byValue !== 0) return byValue;
    } else if (a.delta || b.delta) {
      return a.delta ? -1 : 1;
    }
    return STRENGTH[b.evidence] - STRENGTH[a.evidence];
  });
}

export function pctChange(a: Ratio | null, b: Ratio | null): Ratio | null {
  return a && b && !a.isZero() ? b.div(a).sub(Ratio.ONE).mul(HUNDRED) : null;
}

/**
 * §16.6 rule for the "no measurable link" clause: at company scope for the user's Won,
 * both `diff` and `within_regime` have signals ≤ 2 × expected_by_chance. `level` is never used.
 */
export function noMeasurableLink(rows: SignalSummaryRow[]): boolean | null {
  const pick = (method: string) => rows.find((row) => row.method === method && row.won_definition === "user" && row.scope_type === "company");
  const diff = pick("diff");
  const within = pick("within_regime");
  if (!diff || !within) return null;
  return [diff, within].every((row) => row.signals <= 2 * row.expected_by_chance);
}

/**
 * The ticket step by half-year cohort (§16.1 finding): the first pair of consecutive
 * cohorts with a complete run-rate where it fell 10% or more. Null when there is none.
 */
export function ticketStep(levers: Levers | undefined, definition: WonDefinition): { before: LeverCohort; after: LeverCohort } | null {
  const cohorts = (levers?.cohorts ?? []).filter((row) => row.won_definition === leverDefinition(definition) && row.is_complete_run_rate);
  for (let i = 1; i < cohorts.length; i += 1) {
    const change = pctChange(Ratio.tryParse(cohorts[i - 1]!.run_rate_mrr_per_won_value), Ratio.tryParse(cohorts[i]!.run_rate_mrr_per_won_value));
    if (change && change.compare(Ratio.of(-10n)) <= 0) return { before: cohorts[i - 1]!, after: cohorts[i]! };
  }
  return null;
}
