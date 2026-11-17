import clsx from "clsx";

export function Skeleton({ className }: { className?: string }) {
  return <div aria-hidden="true" className={clsx("bg-surface-3 motion-safe:animate-pulse", className)} />;
}
