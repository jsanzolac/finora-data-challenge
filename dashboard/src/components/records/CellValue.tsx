"use client";

import * as Tooltip from "@radix-ui/react-tooltip";
import { Lock } from "lucide-react";
import { RESTRICTED_VALUE } from "@/lib/api/types";

export const RESTRICTED_LABEL = "Restricted";
export const RESTRICTED_HINT = "HR-sensitive values are visible to Finance only";

/** "Restricted" pill for a value the API masked for this role. Keyboard users get the tooltip on focus. */
export function RestrictedValue() {
  return (
    <Tooltip.Root>
      <Tooltip.Trigger asChild>
        <button
          type="button"
          className="inline-flex items-center gap-1.5 rounded-md border border-line-strong bg-surface-2 px-2 py-0.5 text-sm text-ink-2"
          aria-label={`${RESTRICTED_LABEL}: ${RESTRICTED_HINT}`}
          data-testid="restricted-value"
        >
          <Lock aria-hidden="true" size={13} />
          {RESTRICTED_LABEL}
        </button>
      </Tooltip.Trigger>
      <Tooltip.Portal>
        <Tooltip.Content
          sideOffset={4}
          className="z-[60] max-w-64 rounded-md border border-line-strong bg-bg px-2.5 py-1.5 text-sm text-ink shadow-panel"
        >
          {RESTRICTED_HINT}
          <Tooltip.Arrow className="fill-[var(--line-strong)]" />
        </Tooltip.Content>
      </Tooltip.Portal>
    </Tooltip.Root>
  );
}

const CONTROL = /[\u0000-\u001f\u007f]/;

function controlSymbol(char: string): string {
  const code = char.charCodeAt(0);
  if (code === 0x7f) return "␡";
  return String.fromCharCode(0x2400 + code);
}

/**
 * A raw source value, exactly as received. Nothing is trimmed or re-formatted:
 * - an empty string shows the explicit `(empty)` token;
 * - control characters show as their visible Unicode symbol (TAB as ␉);
 * - leading and trailing spaces are kept and marked, so "Retail " never looks like "Retail".
 */
export function RawValue({ value }: { value: string | undefined }) {
  if (value === undefined) {
    return <span className="font-sans text-sm text-ink-2 italic">(missing)</span>;
  }
  if (value === RESTRICTED_VALUE) return <RestrictedValue />;
  if (value === "") {
    return (
      <span
        className="rounded border border-dashed border-line-strong px-1.5 font-sans text-sm text-ink-2 italic"
        data-testid="empty-value"
      >
        (empty)
      </span>
    );
  }

  const match = /^(\s*)([\s\S]*?)(\s*)$/.exec(value);
  const [, lead = "", body = value, trail = ""] = match ?? [];
  const renderText = (text: string) =>
    CONTROL.test(text)
      ? [...text].map((char, index) =>
          CONTROL.test(char) ? (
            <abbr
              key={index}
              title={`U+${char.charCodeAt(0).toString(16).toUpperCase().padStart(4, "0")}`}
              className="tone-warn rounded bg-[var(--tone-tint)] px-0.5 text-ink no-underline"
            >
              {controlSymbol(char)}
            </abbr>
          ) : (
            char
          ),
        )
      : text;

  return (
    <span className="font-mono text-[0.9375rem] whitespace-pre text-ink">
      {lead ? (
        <span className="rounded-sm bg-surface-3" title="Leading whitespace">
          {renderText(lead)}
        </span>
      ) : null}
      {renderText(body)}
      {trail ? (
        <span className="rounded-sm bg-surface-3" title="Trailing whitespace">
          {renderText(trail)}
        </span>
      ) : null}
    </span>
  );
}
