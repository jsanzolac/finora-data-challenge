"use client";

import { useId, useState } from "react";
import * as Dialog from "@radix-ui/react-dialog";
import { TriangleAlert, X } from "lucide-react";
import { ApiError } from "@/lib/api/client";
import type { Transition } from "@/lib/acq/funnel";
import { useSaveScenario } from "@/lib/acq/queries";
import {
  fieldErrorsFromDetails,
  suggestId,
  toScenarioRates,
  validateSaveDraft,
  type FieldErrors,
  type SaveDraft,
} from "@/lib/acq/scenario-form";
import { BASE_SCENARIO_ID, LABEL_MAX, REASON_MAX, type Scenario } from "@/lib/acq/types";
import { FormError } from "@/components/auth/AuthShell";

type Target = "new" | "update";

function Field({
  id,
  label,
  hint,
  error,
  children,
}: {
  id: string;
  label: string;
  hint?: string;
  error?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="flex flex-col gap-1.5">
      <label htmlFor={id} className="text-[0.9375rem] font-medium">
        {label}
      </label>
      {children}
      {hint && !error ? (
        <p id={`${id}-hint`} className="text-sm text-ink-2">
          {hint}
        </p>
      ) : null}
      {error ? (
        <p id={`${id}-error`} className="tone-fail text-tone text-sm" data-testid={`error-${id}`}>
          {error}
        </p>
      ) : null}
    </div>
  );
}

/**
 * "Save as scenario": a new scenario, or new rows for the current one. Updating
 * Base needs an explicit confirmation, because everyone's base changes.
 */
export function SaveScenarioDialog({
  open,
  onOpenChange,
  scenario,
  transitions,
  onSaved,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  scenario: Scenario;
  transitions: Transition[];
  onSaved: (scenarioId: string) => void;
}) {
  const formId = useId();
  const save = useSaveScenario();
  const [target, setTarget] = useState<Target>("new");
  const [id, setId] = useState("");
  const [idTouched, setIdTouched] = useState(false);
  const [label, setLabel] = useState("");
  const [reason, setReason] = useState("");
  const [confirmBase, setConfirmBase] = useState(false);
  const [errors, setErrors] = useState<FieldErrors & { confirm?: string }>({});

  const updatingBase = target === "update" && scenario.scenario_id === BASE_SCENARIO_ID;
  const idFieldId = `${formId}-scenario_id`;
  const labelFieldId = `${formId}-label`;
  const reasonFieldId = `${formId}-change_reason`;

  function reset() {
    setTarget("new");
    setId("");
    setIdTouched(false);
    setLabel("");
    setReason("");
    setConfirmBase(false);
    setErrors({});
    save.reset();
  }

  function chooseTarget(next: Target) {
    setTarget(next);
    setErrors({});
    if (next === "update") setLabel(scenario.label);
    else if (label === scenario.label) setLabel("");
  }

  async function onSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (save.isPending) return;
    const draft: SaveDraft = {
      scenario_id: target === "update" ? scenario.scenario_id : id.trim(),
      label: label.trim(),
      change_reason: reason.trim(),
    };
    const found: FieldErrors & { confirm?: string } = validateSaveDraft(draft);
    if (updatingBase && !confirmBase) found.confirm = "Confirm that you want to change Base for everyone.";
    setErrors(found);
    if (Object.keys(found).length > 0) return;

    try {
      const saved = await save.mutateAsync({ ...draft, rates: toScenarioRates(transitions) });
      reset();
      onSaved(saved.scenario_id);
    } catch (error) {
      if (error instanceof ApiError && error.code === "invalid_scenario" && error.details.length > 0) {
        setErrors(fieldErrorsFromDetails(error.details));
      } else if (error instanceof ApiError && error.code === "no_change") {
        setErrors({ form: "Nothing to save: these are already the current rates of this scenario." });
      } else if (error instanceof ApiError && error.code === "role_not_allowed") {
        setErrors({ form: "Your role can't change conversion rates." });
      } else {
        setErrors({ form: error instanceof Error ? error.message : "Saving failed. Try again." });
      }
    }
  }

  const describedBy = (fieldId: string, hasHint: boolean, error?: string) =>
    error ? `${fieldId}-error` : hasHint ? `${fieldId}-hint` : undefined;

  return (
    <Dialog.Root
      open={open}
      onOpenChange={(next) => {
        if (!next && save.isPending) return;
        if (!next) reset();
        onOpenChange(next);
      }}
    >
      <Dialog.Portal>
        <Dialog.Overlay className="overlay-enter fixed inset-0 z-40 bg-overlay" />
        <Dialog.Content
          className="overlay-enter fixed top-1/2 left-1/2 z-50 flex max-h-[calc(100dvh-2rem)] w-[calc(100vw-2rem)] max-w-lg -translate-x-1/2 -translate-y-1/2 flex-col overflow-y-auto rounded-xl border border-line-strong bg-bg p-6 shadow-panel"
          data-testid="save-dialog"
        >
          <div className="mb-4 flex items-start justify-between gap-4">
            <div className="flex flex-col gap-1">
              <Dialog.Title className="text-xl font-semibold">Save these rates</Dialog.Title>
              <Dialog.Description className="text-[0.9375rem] text-ink-2">
                Saved rates are shared with Finance, RevOps and Data. Every change is kept with its reason.
              </Dialog.Description>
            </div>
            <Dialog.Close className="btn-ghost -mt-1 -mr-2 px-2" aria-label="Close" disabled={save.isPending}>
              <X aria-hidden="true" size={18} />
            </Dialog.Close>
          </div>

          <form onSubmit={onSubmit} noValidate className="flex flex-col gap-4">
            <fieldset className="flex flex-col gap-2">
              <legend className="mb-1 text-[0.9375rem] font-medium">Save as</legend>
              {(
                [
                  { value: "new", text: "A new scenario" },
                  { value: "update", text: `New rates for “${scenario.label}”` },
                ] as { value: Target; text: string }[]
              ).map((option) => (
                <label key={option.value} className="flex cursor-pointer items-center gap-3">
                  <input
                    type="radio"
                    name={`${formId}-target`}
                    value={option.value}
                    checked={target === option.value}
                    onChange={() => chooseTarget(option.value)}
                    className="size-4 accent-[var(--accent)]"
                    data-testid={`save-target-${option.value}`}
                  />
                  <span className="text-[0.9375rem]">{option.text}</span>
                </label>
              ))}
            </fieldset>

            {target === "new" ? (
              <Field id={idFieldId} label="Id" hint="Lowercase letters, digits and _, starting with a letter. For example sql_demo_080." error={errors.scenario_id}>
                <input
                  id={idFieldId}
                  className="field font-mono"
                  value={id}
                  maxLength={40}
                  autoComplete="off"
                  spellCheck={false}
                  aria-invalid={errors.scenario_id ? true : undefined}
                  aria-describedby={describedBy(idFieldId, true, errors.scenario_id)}
                  onChange={(event) => {
                    setIdTouched(true);
                    setId(event.target.value);
                  }}
                  data-testid="save-id"
                />
              </Field>
            ) : null}

            <Field id={labelFieldId} label="Name" error={errors.label}>
              <input
                id={labelFieldId}
                className="field"
                value={label}
                maxLength={LABEL_MAX}
                autoComplete="off"
                aria-invalid={errors.label ? true : undefined}
                aria-describedby={describedBy(labelFieldId, false, errors.label)}
                onChange={(event) => {
                  setLabel(event.target.value);
                  if (target === "new" && !idTouched) setId(suggestId(event.target.value));
                }}
                data-testid="save-label"
              />
            </Field>

            <Field id={reasonFieldId} label="Why these rates" hint={`Up to ${REASON_MAX} characters. Shown to everyone who reads the rates.`} error={errors.change_reason}>
              <textarea
                id={reasonFieldId}
                className="field min-h-24 resize-y"
                value={reason}
                maxLength={REASON_MAX}
                aria-invalid={errors.change_reason ? true : undefined}
                aria-describedby={describedBy(reasonFieldId, true, errors.change_reason)}
                onChange={(event) => setReason(event.target.value)}
                data-testid="save-reason"
              />
            </Field>

            {updatingBase ? (
              <div className="tone-warn flex flex-col gap-3 rounded-lg border border-[var(--tone)] bg-[var(--tone-tint)] p-3" data-testid="base-warning">
                <p className="flex items-start gap-2 text-[0.9375rem] text-ink">
                  <TriangleAlert aria-hidden="true" size={18} className="text-tone mt-0.5 shrink-0" />
                  This changes the base assumptions for everyone.
                </p>
                <label className="flex cursor-pointer items-center gap-3 text-[0.9375rem] text-ink">
                  <input
                    type="checkbox"
                    checked={confirmBase}
                    onChange={(event) => setConfirmBase(event.target.checked)}
                    className="size-4 accent-[var(--accent)]"
                    aria-invalid={errors.confirm ? true : undefined}
                    data-testid="confirm-base"
                  />
                  Yes, change Base
                </label>
                {errors.confirm ? <p className="tone-fail text-tone text-sm">{errors.confirm}</p> : null}
              </div>
            ) : null}

            <FormError message={[errors.rates, errors.form].filter(Boolean).join(" ") || null} />

            <div className="mt-1 flex flex-wrap justify-end gap-2">
              <Dialog.Close className="btn-secondary" disabled={save.isPending}>
                Cancel
              </Dialog.Close>
              <button type="submit" className="btn-primary" disabled={save.isPending} data-testid="save-submit">
                {save.isPending ? "Saving…" : updatingBase ? "Change Base" : "Save"}
              </button>
            </div>
            <p className="sr-only" aria-live="polite">
              {save.isPending ? "Saving the scenario. This takes a few seconds." : ""}
            </p>
          </form>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
