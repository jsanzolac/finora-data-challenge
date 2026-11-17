/** Shared frame for the sign-in and password screens. */
export function AuthShell({ title, subtitle, children }: { title: string; subtitle?: string; children: React.ReactNode }) {
  return (
    <main className="flex min-h-dvh items-center justify-center px-5 py-12">
      <div className="flex w-full max-w-sm flex-col gap-8">
        <p className="text-base font-semibold">Finora</p>
        <div className="flex flex-col gap-2">
          <h1 className="text-3xl font-semibold">{title}</h1>
          {subtitle ? <p className="text-base text-ink-2">{subtitle}</p> : null}
        </div>
        {children}
        <p className="text-[0.9375rem] text-ink-2">Need access or a reset? Ask your Data admin.</p>
      </div>
    </main>
  );
}

export function FormError({ message }: { message: string | null }) {
  return (
    <div aria-live="assertive" className="empty:hidden">
      {message ? (
        <p
          role="alert"
          className="tone-fail rounded-lg border border-[var(--tone)] bg-[var(--tone-tint)] px-3 py-2 text-[0.9375rem] text-ink"
          data-testid="form-error"
        >
          {message}
        </p>
      ) : null}
    </div>
  );
}
