export const LOGIN_PATH = "/login/";
export const CHANGE_PASSWORD_PATH = "/change-password/";
export const HOME_PATH = "/";

/**
 * Only same-origin paths are accepted as a return URL. Anything else
 * (absolute URLs, `//host`, backslashes, the auth screens themselves) falls
 * back to the overview, so the login screen cannot be used as an open redirect.
 */
export function safeReturnTo(raw: string | null | undefined): string {
  if (!raw) return HOME_PATH;
  if (!raw.startsWith("/") || raw.startsWith("//") || raw.includes("\\")) return HOME_PATH;
  if (/[\u0000-\u001f]/.test(raw)) return HOME_PATH;
  const path = raw.split(/[?#]/)[0] ?? "";
  if (path.startsWith("/login") || path.startsWith("/change-password") || path.startsWith("/api/")) return HOME_PATH;
  return raw;
}

/** `/login/?returnTo=…&reason=expired`. The return URL is left out when it is just the overview. */
export function loginHref(returnTo: string, expired: boolean): string {
  const params = new URLSearchParams();
  const target = safeReturnTo(returnTo);
  if (target !== HOME_PATH) params.set("returnTo", target);
  if (expired) params.set("reason", "expired");
  const query = params.toString();
  return query ? `${LOGIN_PATH}?${query}` : LOGIN_PATH;
}

export function changePasswordHref(returnTo: string): string {
  const target = safeReturnTo(returnTo);
  return target === HOME_PATH ? CHANGE_PASSWORD_PATH : `${CHANGE_PASSWORD_PATH}?returnTo=${encodeURIComponent(target)}`;
}
