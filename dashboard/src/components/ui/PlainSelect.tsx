"use client";

import * as Select from "@radix-ui/react-select";
import { Check, ChevronDown } from "lucide-react";

export interface SelectItem {
  value: string;
  text: string;
  /** Quiet text on the right of the item ("11 months", "Invalid"). */
  note?: string;
  disabled?: boolean;
}

export interface SelectGroup {
  label?: string;
  items: SelectItem[];
}

/**
 * A labelled Radix select with optional groups and disabled items. The visible
 * label sits above the trigger; the trigger shows the chosen item's text.
 */
export function PlainSelect({
  label,
  value,
  onValueChange,
  groups,
  testId,
  triggerText,
  className,
  hideLabel = false,
}: {
  label: string;
  value: string;
  onValueChange: (value: string) => void;
  groups: SelectGroup[];
  testId?: string;
  /** Overrides the trigger text (for example "2022 · 11 months"). */
  triggerText?: string;
  className?: string;
  /** Keep the label for assistive tech only (the trigger's name still carries it), e.g. inside a sentence. */
  hideLabel?: boolean;
}) {
  const selected = groups.flatMap((group) => group.items).find((item) => item.value === value);
  return (
    <div className={className}>
      <Select.Root value={value} onValueChange={onValueChange}>
        <span className={hideLabel ? "sr-only" : "mb-1 block text-sm text-ink-2"} aria-hidden="true">
          {label}
        </span>
        <Select.Trigger
          aria-label={`${label}: ${triggerText ?? selected?.text ?? ""}`}
          data-testid={testId}
          className="flex min-h-10 w-full min-w-0 items-center justify-between gap-2 rounded-lg border border-line-strong bg-bg px-3 py-1.5 text-left text-[0.9375rem] text-ink hover:border-ink-3"
        >
          <span className="truncate">{triggerText ?? selected?.text ?? ""}</span>
          <Select.Icon>
            <ChevronDown aria-hidden="true" size={16} className="text-ink-2" />
          </Select.Icon>
        </Select.Trigger>
        <Select.Portal>
          <Select.Content
            position="popper"
            sideOffset={4}
            align="start"
            className="z-50 max-h-[min(26rem,var(--radix-select-content-available-height))] min-w-[var(--radix-select-trigger-width)] overflow-hidden rounded-lg border border-line-strong bg-bg shadow-panel"
          >
            <Select.Viewport className="p-1">
              {groups.map((group, index) => (
                <Select.Group key={group.label ?? index}>
                  {group.label ? (
                    <Select.Label className="px-3 pt-2.5 pb-1 text-sm font-medium text-ink-2">{group.label}</Select.Label>
                  ) : null}
                  {group.items.map((item) => (
                    <Select.Item
                      key={item.value}
                      value={item.value}
                      disabled={item.disabled}
                      textValue={item.note ? `${item.text}, ${item.note}` : item.text}
                      className="relative flex cursor-pointer items-center gap-3 rounded-md py-2 pr-3 pl-8 text-[0.9375rem] outline-none select-none data-[disabled]:cursor-not-allowed data-[disabled]:text-ink-3 data-[highlighted]:bg-surface-3"
                      data-value={item.value}
                    >
                      <Select.ItemIndicator className="absolute left-2">
                        <Check aria-hidden="true" size={16} />
                      </Select.ItemIndicator>
                      <Select.ItemText>{item.text}</Select.ItemText>
                      {item.note ? <span className="ml-auto pl-3 text-sm text-ink-2">{item.note}</span> : null}
                    </Select.Item>
                  ))}
                </Select.Group>
              ))}
            </Select.Viewport>
          </Select.Content>
        </Select.Portal>
      </Select.Root>
    </div>
  );
}
