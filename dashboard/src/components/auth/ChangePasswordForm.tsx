"use client";

import { useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { Check, KeyRound, X } from "lucide-react";
import clsx from "clsx";
import { ApiError } from "@/lib/api/client";
import { useAuth } from "@/lib/auth/store";
import { safeReturnTo } from "@/lib/auth/return-to";
import { AuthShell, FormError } from "./AuthShell";

export const MIN_PASSWORD_LENGTH = 12;

function Requirement({ met, children }: { met: boolean; children: React.ReactNode }) {
  const Icon = met ? Check : X;
  return (
    <li className={clsx("flex items-center gap-1.5", met ? "text-pass-ink" : "text-ink-2")}>
      <Icon aria-hidden="true" size={14} />
      <span>
        {children}
        <span className="sr-only">{met ? " (met)" : " (not met yet)"}</span>
      </span>
    </li>
  );
}

export function ChangePasswordForm() {
  const { user, changePassword, signOut } = useAuth();
  const router = useRouter();
  const search = useSearchParams();
  const returnTo = safeReturnTo(search.get("returnTo"));
  const forced = Boolean(user?.must_change_password);

  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  const longEnough = next.length >= MIN_PASSWORD_LENGTH;
  const different = next.length > 0 && next !== current;
  const matches = confirm.length > 0 && confirm === next;

  async function onSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (pending) return;
    setError(null);
    if (!current) return setError("Enter your current password.");
    if (!longEnough) return setError(`The new password needs at least ${MIN_PASSWORD_LENGTH} characters.`);
    if (!different) return setError("The new password must be different from the current one.");
    if (!matches) return setError("The two new passwords don't match.");
    setPending(true);
    try {
      await changePassword(current, next);
      router.replace(returnTo);
    } catch (cause) {
      setPending(false);
      if (cause instanceof ApiError && cause.status === 401) return; // the guard sends the user to sign in
      setError(cause instanceof ApiError ? cause.message : "The password could not be changed. Try again.");
    }
  }

  return (
    <AuthShell
      title={forced ? "Set a new password" : "Change password"}
      subtitle={
        forced
          ? "Choose your own password to continue."
          : `Signed in as ${user?.email ?? "you"}.`
      }
    >
      <form className="flex flex-col gap-4" onSubmit={onSubmit} noValidate>
        {/* Lets password managers pair the new password with the account. */}
        <input type="email" name="username" autoComplete="username" value={user?.email ?? ""} readOnly hidden />
        <div className="flex flex-col gap-1.5">
          <label htmlFor="current" className="text-[0.9375rem] font-medium">
            {forced ? "Temporary password" : "Current password"}
          </label>
          <input
            id="current"
            type="password"
            autoComplete="current-password"
            className="field"
            value={current}
            onChange={(event) => setCurrent(event.target.value)}
            autoFocus
          />
        </div>
        <div className="flex flex-col gap-1.5">
          <label htmlFor="new" className="text-[0.9375rem] font-medium">
            New password
          </label>
          <input
            id="new"
            type="password"
            autoComplete="new-password"
            className="field"
            value={next}
            onChange={(event) => setNext(event.target.value)}
            aria-describedby="new-rules"
          />
          <ul id="new-rules" className="flex flex-col gap-0.5 text-sm">
            <Requirement met={longEnough}>At least {MIN_PASSWORD_LENGTH} characters</Requirement>
            <Requirement met={different}>Different from the current one</Requirement>
          </ul>
        </div>
        <div className="flex flex-col gap-1.5">
          <label htmlFor="confirm" className="text-[0.9375rem] font-medium">
            Repeat the new password
          </label>
          <input
            id="confirm"
            type="password"
            autoComplete="new-password"
            className="field"
            value={confirm}
            onChange={(event) => setConfirm(event.target.value)}
          />
        </div>
        <FormError message={error} />
        <button type="submit" className="btn-primary min-h-11" disabled={pending} data-testid="password-submit">
          <KeyRound aria-hidden="true" size={16} />
          {pending ? "Saving…" : "Save and continue"}
        </button>
        {forced ? (
          <button type="button" className="btn-ghost" onClick={() => void signOut()}>
            Log out instead
          </button>
        ) : (
          <button type="button" className="btn-ghost" onClick={() => router.replace(returnTo)}>
            Cancel
          </button>
        )}
      </form>
    </AuthShell>
  );
}
