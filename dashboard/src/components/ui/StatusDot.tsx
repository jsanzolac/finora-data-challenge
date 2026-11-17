import { statusMeta } from "@/lib/status";

/** A small dot in the status colour. Decorative: the word or the cell's accessible name carries the status. */
export function StatusDot({ status, size = 9 }: { status: string; size?: number }) {
  const meta = statusMeta(status);
  return (
    <span
      aria-hidden="true"
      className={`tone-${meta.tone} bg-tone inline-block shrink-0 rounded-full`}
      style={{ width: size, height: size }}
      data-status-dot={meta.tone}
    />
  );
}
