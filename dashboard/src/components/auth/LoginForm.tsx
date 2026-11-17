"use client";

import { useState } from "react";
import { useSearchParams } from "next/navigation";
import { Eye, EyeOff, LogIn } from "lucide-react";
import { ApiError } from "@/lib/api/client";
import { useAuth } from "@/lib/auth/store";
import { AuthShell, FormError } from "./AuthShell";

const MOCKS_ENABLED = process.env.NEXT_PUBLIC_DQ_MOCKS === "1";

function loginMessage(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.status === 401) return "Email or password is incorrect.";
    if (error.status === 429) return "Too many attempts. Wait a few minutes and try again.";
    return error.message;
  }
  return "Sign-in failed. Try again.";
}

export function LoginForm() {
  const { signIn } = useAuth();
  const search = useSearchParams();
  const expired = search.get("reason") === "expired";
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  async function onSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (pending) return;
    setError(null);
    if (!email.trim() || !password) {
      setError("Enter your email and password.");
      return;
    }
    setPending(true);
    try {
      // On success the route guard sends the user on (or to the password-change screen).
      await signIn(email.trim(), password);
    } catch (cause) {
      setError(loginMessage(cause));
      setPending(false);
    }
  }

  return (
    <AuthShell title="Sign in">
      {expired ? (
        <p role="status" className="rounded-lg border border-line-strong bg-surface px-3 py-2 text-[0.9375rem]" data-testid="session-expired">
          Your session ended. Sign in to continue.
        </p>
      ) : null}
      {MOCKS_ENABLED ? (
        <p className="rounded-lg border border-dashed border-line-strong px-3 py-2 text-sm text-ink-2">
          Mock mode: demo accounts are in dashboard/README.md.
        </p>
      ) : null}
      <form className="flex flex-col gap-4" onSubmit={onSubmit} noValidate>
        <div className="flex flex-col gap-1.5">
          <label htmlFor="email" className="text-[0.9375rem] font-medium">
            Work email
          </label>
          <input
            id="email"
            name="email"
            type="email"
            autoComplete="username"
            inputMode="email"
            className="field"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            required
            autoFocus
          />
        </div>
        <div className="flex flex-col gap-1.5">
          <label htmlFor="password" className="text-[0.9375rem] font-medium">
            Password
          </label>
          <div className="relative">
            <input
              id="password"
              name="password"
              type={showPassword ? "text" : "password"}
              autoComplete="current-password"
              className="field pr-11"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              required
            />
            <button
              type="button"
              className="absolute top-1/2 right-1 flex size-8 -translate-y-1/2 items-center justify-center text-ink-2 rounded-md hover:bg-surface-3"
              onClick={() => setShowPassword((value) => !value)}
              aria-label={showPassword ? "Hide password" : "Show password"}
              aria-pressed={showPassword}
            >
              {showPassword ? <EyeOff aria-hidden="true" size={16} /> : <Eye aria-hidden="true" size={16} />}
            </button>
          </div>
        </div>
        <FormError message={error} />
        <button type="submit" className="btn-primary min-h-11" disabled={pending} data-testid="login-submit">
          <LogIn aria-hidden="true" size={16} />
          {pending ? "Signing in…" : "Sign in"}
        </button>
      </form>
    </AuthShell>
  );
}
