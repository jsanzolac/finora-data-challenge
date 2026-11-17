import { CircleAlert, RotateCw } from "lucide-react";

export function ErrorState({
  title,
  message,
  onRetry,
  action,
}: {
  title: string;
  message: string;
  onRetry?: () => void;
  action?: React.ReactNode;
}) {
  return (
    <div role="alert" className="card tone-fail flex flex-col items-start gap-4 p-6">
      <div className="flex items-start gap-3">
        <CircleAlert aria-hidden="true" size={20} className="text-tone mt-0.5 shrink-0" />
        <div className="flex flex-col gap-1">
          <p className="text-base font-semibold">{title}</p>
          <p className="text-[0.9375rem] text-ink-2">{message}</p>
        </div>
      </div>
      <div className="flex flex-wrap gap-2">
        {onRetry ? (
          <button type="button" onClick={onRetry} className="btn-secondary">
            <RotateCw aria-hidden="true" size={16} />
            Try again
          </button>
        ) : null}
        {action}
      </div>
    </div>
  );
}
