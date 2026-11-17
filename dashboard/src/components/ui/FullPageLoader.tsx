export function FullPageLoader({ label = "Loading" }: { label?: string }) {
  return (
    <div className="flex min-h-dvh items-center justify-center bg-bg" role="status" aria-live="polite">
      <div className="flex items-center gap-3 text-[0.9375rem] text-ink-2">
        <span aria-hidden="true" className="size-4 rounded-full border-2 border-line-strong border-t-accent motion-safe:animate-spin" />
        <span>{label}…</span>
      </div>
    </div>
  );
}
