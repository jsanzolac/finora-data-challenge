/**
 * Rate inputs and the "Save as scenario" form. The client checks mirror the
 * contract's POST validation, so most mistakes are caught before the 2-5 s
 * Athena round trip; the server's 400 `invalid_scenario` details are mapped
 * back onto the same fields.
 */
import { Ratio } from "./ratio";
import { LABEL_MAX, REASON_MAX, SCENARIO_ID_PATTERN, type ApiErrorDetail, type ScenarioRate } from "./types";
import type { Transition } from "./funnel";
import { ratePercentText } from "./format";

const HUNDRED = Ratio.of(100n);

export type RateDraft = { ok: true; rate: Ratio } | { ok: false; message: string };

/**
 * A rate typed as a percent ("80", "81.25", "80%"). Valid: a plain number above
 * 0 and up to 100, with at most 2 decimals (the contract's 4-decimal rate).
 */
export function parsePercentDraft(text: string): RateDraft {
  const cleaned = text.trim().replace(/%$/, "").trim().replace(",", ".");
  if (cleaned === "") return { ok: false, message: "Enter a rate." };
  const value = Ratio.tryParse(cleaned);
  if (!value) return { ok: false, message: "Enter a number, for example 40 or 42.5." };
  if (value.sign() <= 0) return { ok: false, message: "The rate must be above 0%." };
  if (value.compare(HUNDRED) > 0) return { ok: false, message: "The rate can't be above 100%." };
  if (!value.hasAtMostDecimals(2)) return { ok: false, message: "Use at most 2 decimals." };
  return { ok: true, rate: value.div(HUNDRED) };
}

export function percentText(rate: Ratio): string {
  return ratePercentText(rate);
}

/** The 6 transitions as the API expects them: 4-decimal strings, in stage order. */
export function toScenarioRates(transitions: Transition[]): ScenarioRate[] {
  return transitions.map((transition) => ({
    from_stage: transition.from,
    to_stage: transition.to,
    rate: transition.rate.toFixed(4),
  }));
}

export type SaveField = "scenario_id" | "label" | "change_reason" | "rates" | "form";
export type FieldErrors = Partial<Record<SaveField, string>>;

export interface SaveDraft {
  scenario_id: string;
  label: string;
  change_reason: string;
}

export function validateSaveDraft(draft: SaveDraft): FieldErrors {
  const errors: FieldErrors = {};
  if (!SCENARIO_ID_PATTERN.test(draft.scenario_id)) {
    errors.scenario_id = "Use 1–40 lowercase letters, digits or _, starting with a letter (for example sql_demo_080).";
  }
  const label = draft.label.trim();
  if (label.length < 1) errors.label = "Give the scenario a name.";
  else if (label.length > LABEL_MAX) errors.label = `Keep the name to ${LABEL_MAX} characters.`;
  const reason = draft.change_reason.trim();
  if (reason.length < 1) errors.change_reason = "Say why these rates.";
  else if (reason.length > REASON_MAX) errors.change_reason = `Keep the reason to ${REASON_MAX} characters.`;
  return errors;
}

const FIELDS: SaveField[] = ["scenario_id", "label", "change_reason", "rates"];

/** Used only when an item has no recognised `field`. */
const CHECK_FIELD: Record<string, SaveField> = {
  "GR-01": "scenario_id",
  "GR-02": "rates",
  "GR-03": "rates",
  "GR-04": "rates",
  "GR-06": "change_reason",
  LABEL_LENGTH: "label",
  REASON_LENGTH: "change_reason",
};

/** Maps the server's `error.details` onto the form by `field`; anything else goes to the form. */
export function fieldErrorsFromDetails(details: ApiErrorDetail[]): FieldErrors {
  const errors: FieldErrors = {};
  for (const detail of details) {
    const field = (FIELDS as string[]).includes(detail.field) ? (detail.field as SaveField) : (CHECK_FIELD[detail.check] ?? "form");
    const text = detail.message || detail.check;
    errors[field] = errors[field] ? `${errors[field]} ${text}` : text;
  }
  return errors;
}

/** A suggested id from a label: "SQL to Demo at 80%" -> "sql_to_demo_at_80". */
export function suggestId(label: string): string {
  const slug = label
    .toLowerCase()
    .normalize("NFKD")
    .replace(/[̀-ͯ]/g, "")
    .replace(/[^a-z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "")
    .replace(/^[^a-z]+/, "");
  return slug.slice(0, 40).replace(/_+$/, "");
}
