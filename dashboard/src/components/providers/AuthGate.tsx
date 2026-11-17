"use client";

import { useEffect } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useAuth } from "@/lib/auth/store";
import { changePasswordHref, loginHref, safeReturnTo } from "@/lib/auth/return-to";
import { FullPageLoader } from "@/components/ui/FullPageLoader";

/**
 * Wraps screens that need a session.
 * - Signed out: go to /login and remember where to return.
 * - Password change pending: go to the password-change screen (unless this is it).
 */
export function RequireAuth({
  children,
  allowPasswordChangePending = false,
}: {
  children: React.ReactNode;
  allowPasswordChangePending?: boolean;
}) {
  const { status, user, expired } = useAuth();
  const router = useRouter();
  const pathname = usePathname();
  const search = useSearchParams();
  const query = search.toString();
  const mustChange = Boolean(user?.must_change_password) && !allowPasswordChangePending;

  useEffect(() => {
    // On the password screen the page to return to is the one it was given, not itself.
    const here = allowPasswordChangePending
      ? safeReturnTo(new URLSearchParams(query).get("returnTo"))
      : query
        ? `${pathname}?${query}`
        : pathname;
    if (status === "signedOut") router.replace(loginHref(here, expired));
    else if (status === "signedIn" && mustChange) router.replace(changePasswordHref(here));
  }, [status, mustChange, expired, router, pathname, query, allowPasswordChangePending]);

  if (status !== "signedIn" || mustChange) return <FullPageLoader label="Checking your session" />;
  return <>{children}</>;
}

/** Wraps the login screen: a signed-in user is sent on to where they were going. */
export function RequireSignedOut({ children }: { children: React.ReactNode }) {
  const { status, user } = useAuth();
  const router = useRouter();
  const search = useSearchParams();
  const returnTo = safeReturnTo(search.get("returnTo"));

  useEffect(() => {
    if (status !== "signedIn" || !user) return;
    router.replace(user.must_change_password ? changePasswordHref(returnTo) : returnTo);
  }, [status, user, router, returnTo]);

  if (status !== "signedOut") return <FullPageLoader label="Checking your session" />;
  return <>{children}</>;
}
