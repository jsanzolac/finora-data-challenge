"use client";

import { useEffect, useId, useRef, useState } from "react";
import Link from "next/link";
import clsx from "clsx";
import * as Select from "@radix-ui/react-select";
import { Check, ChevronDown, LogOut } from "lucide-react";
import type { Run } from "@/lib/api/types";
import { useAuth } from "@/lib/auth/store";
import { formatDateUtc, formatMonth, humanize, initials } from "@/lib/format";
import { Skeleton } from "@/components/ui/Skeleton";
import { VoiceControl } from "@finora/voice";

function runText(run: Run): string {
  return `Data as of ${formatMonth(run.as_of_month)} · updated ${formatDateUtc(run.started_at)}`;
}

/** Plain run picker: "Data as of Oct 2024 · updated 16 Nov 2026". Latest by default. */
export function RunSelect({
  runs,
  selectedRunId,
  onSelect,
}: {
  runs: Run[];
  selectedRunId: string | undefined;
  onSelect: (runId: string | null) => void;
}) {
  const latestId = runs.find((run) => run.status === "succeeded")?.run_id;
  const selected = runs.find((run) => run.run_id === selectedRunId);

  return (
    <Select.Root value={selected?.run_id ?? ""} onValueChange={(runId) => onSelect(runId === latestId ? null : runId)}>
      <Select.Trigger
        aria-label={selected ? `${runText(selected)}. Change the run` : "Select a run"}
        data-testid="run-select"
        className="flex min-h-10 max-w-full items-center gap-2 rounded-lg px-3 py-1.5 text-left text-[0.9375rem] text-ink-2 hover:bg-surface-3 hover:text-ink"
      >
        <span className="truncate">{selected ? runText(selected) : "Select a run"}</span>
        <Select.Icon>
          <ChevronDown aria-hidden="true" size={16} />
        </Select.Icon>
      </Select.Trigger>
      <Select.Portal>
        <Select.Content
          position="popper"
          sideOffset={4}
          align="end"
          className="z-50 max-h-[min(24rem,var(--radix-select-content-available-height))] min-w-[var(--radix-select-trigger-width)] overflow-hidden rounded-lg border border-line-strong bg-bg shadow-panel"
        >
          <Select.Viewport className="p-1">
            {runs.map((run) => {
              const failed = run.status !== "succeeded";
              return (
                <Select.Item
                  key={run.run_id}
                  value={run.run_id}
                  disabled={failed}
                  textValue={`${runText(run)}${failed ? ", failed" : ""}`}
                  className="relative flex cursor-pointer items-center gap-3 rounded-md py-2 pr-3 pl-8 text-[0.9375rem] outline-none select-none data-[disabled]:cursor-not-allowed data-[disabled]:text-ink-3 data-[highlighted]:bg-surface-3"
                >
                  <Select.ItemIndicator className="absolute left-2">
                    <Check aria-hidden="true" size={16} />
                  </Select.ItemIndicator>
                  <Select.ItemText>{runText(run)}</Select.ItemText>
                  <span className="ml-auto pl-3 text-sm text-ink-3">
                    {failed ? "Failed, no data" : run.run_id === latestId ? "Latest" : ""}
                  </span>
                </Select.Item>
              );
            })}
          </Select.Viewport>
        </Select.Content>
      </Select.Portal>
    </Select.Root>
  );
}

/** Initials button that opens a small panel: email, role and Log out. */
function UserMenu() {
  const { user, signOut } = useAuth();
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const buttonRef = useRef<HTMLButtonElement>(null);
  const panelId = useId();

  useEffect(() => {
    if (!open) return;
    function onPointer(event: PointerEvent) {
      if (!rootRef.current?.contains(event.target as Node)) setOpen(false);
    }
    function onKey(event: KeyboardEvent) {
      if (event.key === "Escape") {
        setOpen(false);
        buttonRef.current?.focus();
      }
    }
    document.addEventListener("pointerdown", onPointer);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("pointerdown", onPointer);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  if (!user) return null;

  return (
    <div ref={rootRef} className="relative" data-testid="current-user">
      <button
        ref={buttonRef}
        type="button"
        aria-expanded={open}
        aria-controls={panelId}
        onClick={() => setOpen((value) => !value)}
        className="flex size-10 items-center justify-center rounded-full border border-line-strong bg-surface text-sm font-semibold text-ink hover:bg-surface-3"
        data-testid="user-menu"
      >
        {initials(user.email)}
        <span className="sr-only">: account menu for {user.email}</span>
      </button>
      <div
        id={panelId}
        hidden={!open}
        className="absolute top-12 right-0 z-50 w-64 rounded-lg border border-line-strong bg-bg p-4 shadow-panel"
      >
        <p className="truncate text-[0.9375rem] font-medium" title={user.email}>
          {user.email}
        </p>
        <p className="text-[0.9375rem] text-ink-2">Role: {humanize(user.role)}</p>
        <button type="button" className="btn-secondary mt-3 w-full" onClick={() => void signOut()}>
          <LogOut aria-hidden="true" size={16} />
          Log out
        </button>
      </div>
    </div>
  );
}

export type DashboardSection = "dq" | "acq" | "mrr";

const SECTIONS: { id: DashboardSection; label: string; href: string }[] = [
  { id: "dq", label: "Data quality", href: "/" },
  { id: "acq", label: "Acquisition", href: "/acquisition/" },
  { id: "mrr", label: "MRR", href: "/mrr/" },
];

/** Two plain text tabs. The current one is in full ink with a short underline. */
function SectionNav({ current }: { current: DashboardSection }) {
  return (
    <nav aria-label="Dashboards">
      <ul className="flex items-center gap-0.5 sm:gap-1">
        {SECTIONS.map((section) => {
          const active = section.id === current;
          return (
            <li key={section.id}>
              <Link
                href={section.href}
                aria-current={active ? "page" : undefined}
                data-testid={`nav-${section.id}`}
                className={clsx(
                  "relative flex min-h-10 items-center rounded-md px-1.5 text-sm whitespace-nowrap sm:px-2.5 sm:text-[0.9375rem]",
                  active
                    ? "font-semibold text-ink after:absolute after:inset-x-1.5 after:-bottom-[0.8125rem] after:h-0.5 after:rounded-full after:bg-ink sm:after:inset-x-2.5"
                    : "text-ink-2 hover:bg-surface-3 hover:text-ink",
                )}
              >
                {section.label}
              </Link>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}

/**
 * Brand, the two dashboards, a page-specific control on the right (the DQ run
 * picker, or the acquisition data date) and the user menu.
 */
export function AppHeader({ section, aside }: { section: DashboardSection; aside?: React.ReactNode }) {
  return (
    <header className="border-b border-line">
      <div className="mx-auto flex max-w-[1200px] flex-wrap items-center gap-x-3 gap-y-2 px-5 py-3 sm:gap-x-4 md:px-8">
        <div className="mr-auto flex min-w-0 items-center gap-2 sm:gap-5">
          <span className="text-base font-semibold whitespace-nowrap">Finora</span>
          <SectionNav current={section} />
        </div>
        {aside ? <div className="order-3 w-full sm:order-none sm:w-auto">{aside}</div> : null}
        <VoiceControl />
        <UserMenu />
      </div>
    </header>
  );
}

/** The DQ header control: the run picker, or its skeleton while the runs load. */
export function RunAside({
  runs,
  selectedRunId,
  onSelectRun,
}: {
  runs: Run[] | undefined;
  selectedRunId: string | undefined;
  onSelectRun: (runId: string | null) => void;
}) {
  return runs ? (
    <RunSelect runs={runs} selectedRunId={selectedRunId} onSelect={onSelectRun} />
  ) : (
    <Skeleton className="h-10 w-full rounded-lg sm:w-80" />
  );
}
