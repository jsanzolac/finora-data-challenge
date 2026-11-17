/**
 * The funnel arithmetic of contracts/acq_api_contract.md ("Funnel arithmetic"),
 * which must equal finora_gold.v_funnel_month / v_funnel_period and
 * v_funnel_scenario_compare / v_funnel_rate_sensitivity.
 *
 * Only Won is observed. Every other stage is Won divided by the product of the
 * assumed rates from that stage down to Won, so the shape of the funnel is the
 * same in every month by construction.
 */
import { Ratio } from "./ratio";
import type { FunnelStage, ScenarioRate } from "./types";

export const RATE_POINT = Ratio.parse("0.01");
const HUNDRED = Ratio.of(100n);

export interface Transition {
  from: string;
  to: string;
  rate: Ratio;
}

/** Stages in funnel order (by `order`). */
export function orderedStages(stages: FunnelStage[]): FunnelStage[] {
  return [...stages].sort((a, b) => a.order - b.order);
}

/**
 * The scenario's rates as one transition per consecutive stage pair, in stage
 * order. Returns null when the rates do not cover exactly the consecutive pairs
 * or a rate is outside 0 < rate <= 1 (such a scenario produces no funnel).
 */
export function transitionsFor(stages: FunnelStage[], rates: ScenarioRate[]): Transition[] | null {
  const ordered = orderedStages(stages);
  if (ordered.length < 2 || rates.length !== ordered.length - 1) return null;
  const out: Transition[] = [];
  for (let index = 0; index < ordered.length - 1; index += 1) {
    const from = ordered[index]!.code;
    const to = ordered[index + 1]!.code;
    const entry = rates.find((rate) => rate.from_stage === from);
    if (!entry || entry.to_stage !== to) return null;
    const rate = Ratio.tryParse(entry.rate);
    if (!rate || rate.sign() <= 0 || rate.compare(Ratio.ONE) > 0) return null;
    out.push({ from, to, rate });
  }
  return out;
}

/** Product of every rate: the share of New that reaches Won. */
export function overallRate(transitions: Transition[]): Ratio {
  return transitions.reduce((product, transition) => product.mul(transition.rate), Ratio.ONE);
}

export interface StageFigure {
  code: string;
  label: string;
  /** Product of the rates from this stage down to Won (1 for the last stage). */
  downstream: Ratio;
  /** Won for the last stage (observed); Won ÷ downstream elsewhere (estimated). */
  count: Ratio;
  /** Spend × downstream ÷ Won; null when unavailable. */
  costPerUnit: Ratio | null;
  real: boolean;
}

export interface FunnelInput {
  stages: FunnelStage[];
  transitions: Transition[];
  won: Ratio;
  /** Σ total spend over the same months; null when any month has no spend. */
  spend: Ratio | null;
  /** The first non-null `cost_null_reason` among the months, if any. */
  costNullReason: string | null;
}

export interface FunnelResult {
  stages: StageFigure[];
  /** Why cost per unit is unavailable (`won_zero`, or a month's `cost_null_reason`); null when it is shown. */
  costUnavailable: string | null;
}

export function computeFunnel({ stages, transitions, won, spend, costNullReason }: FunnelInput): FunnelResult {
  const ordered = orderedStages(stages);
  const costUnavailable = won.isZero() ? "won_zero" : (costNullReason ?? (spend === null ? "spend_missing" : null));

  const figures: StageFigure[] = ordered.map((stage, index) => {
    const downstream = transitions.slice(index).reduce((product, transition) => product.mul(transition.rate), Ratio.ONE);
    const last = index === ordered.length - 1;
    const count = last ? won : won.div(downstream);
    const costPerUnit = costUnavailable === null && spend !== null ? spend.mul(downstream).div(won) : null;
    return { code: stage.code, label: stage.label, downstream, count, costPerUnit, real: last };
  });

  return { stages: figures, costUnavailable };
}

export interface ScenarioComparison {
  overall: Ratio;
  overallBase: Ratio;
  /** Won ÷ overall(base): the New that base implies. */
  newEstimatedBase: Ratio;
  /** Won × overall(s) ÷ overall(base): Won with the same New. */
  wonImplied: Ratio;
  wonImpliedDelta: Ratio;
  /** Percent, against the actual Won; null when Won is 0. */
  wonImpliedDeltaPct: Ratio | null;
  /** Won ÷ overall(s): the New needed for the same Won. */
  newRequired: Ratio;
  newRequiredDelta: Ratio;
  /** Percent, against Won ÷ overall(base); null when Won is 0. */
  newRequiredDeltaPct: Ratio | null;
  /** Spend ÷ Won implied; null without spend or when Won implied is 0. */
  costPerWonImplied: Ratio | null;
}

export function compareScenario(won: Ratio, spend: Ratio | null, scenario: Transition[], base: Transition[]): ScenarioComparison {
  const overall = overallRate(scenario);
  const overallBase = overallRate(base);
  const newEstimatedBase = won.div(overallBase);
  const wonImplied = won.mul(overall).div(overallBase);
  const wonImpliedDelta = wonImplied.sub(won);
  const newRequired = won.div(overall);
  const newRequiredDelta = newRequired.sub(newEstimatedBase);
  return {
    overall,
    overallBase,
    newEstimatedBase,
    wonImplied,
    wonImpliedDelta,
    wonImpliedDeltaPct: won.isZero() ? null : wonImpliedDelta.div(won).mul(HUNDRED),
    newRequired,
    newRequiredDelta,
    newRequiredDeltaPct: newEstimatedBase.isZero() ? null : newRequiredDelta.div(newEstimatedBase).mul(HUNDRED),
    costPerWonImplied: spend === null || wonImplied.isZero() ? null : spend.div(wonImplied),
  };
}

export interface Sensitivity {
  from: string;
  to: string;
  rate: Ratio;
  /** 1 ÷ rate, in percent: Won gained per +0.01 on this rate, New held fixed. Null when rate + 0.01 > 1. */
  wonPctPerPoint: Ratio | null;
  /** Won × 0.01 ÷ rate. */
  wonPerPoint: Ratio | null;
  /** −1 ÷ (rate + 0.01), in percent: the change in New needed for the same Won. */
  newRequiredPctPerPoint: Ratio | null;
}

export function sensitivities(won: Ratio, transitions: Transition[]): Sensitivity[] {
  return transitions.map(({ from, to, rate }) => {
    const capped = rate.add(RATE_POINT).compare(Ratio.ONE) > 0;
    return {
      from,
      to,
      rate,
      wonPctPerPoint: capped ? null : Ratio.ONE.div(rate),
      wonPerPoint: capped ? null : won.mul(RATE_POINT).div(rate),
      newRequiredPctPerPoint: capped ? null : Ratio.ONE.neg().div(rate.add(RATE_POINT)),
    };
  });
}

/** True when two rate sets are equal transition by transition. */
export function sameRates(a: Transition[], b: Transition[]): boolean {
  return a.length === b.length && a.every((transition, index) => transition.rate.equals(b[index]!.rate));
}
