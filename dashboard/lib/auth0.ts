// Auth0 integration for the dashboard (PRD contract C). Authentication AND
// role-based authorization, on the free tier, configured entirely from env so
// Contig stays open source with no tenant baked in.
//
// Two layers protect the app:
//   1. proxy.ts gates navigation: an unauthenticated request is redirected to
//      login, and a request to a write (action) API without the writer role is
//      rejected with 403.
//   2. Each action route also calls requireWriter() here, so authorization is
//      enforced at the route itself and never depends on the proxy matcher alone
//      (Next warns that a matcher change can silently drop proxy coverage).
//
// The dev/test bypass: when CONTIG_AUTH_DISABLED is "1", or no Auth0 env is
// configured, authentication is a no-op and the caller is treated as an admin.
// Local dev and the Playwright suite then run with no real tenant.
import "server-only";

import { Auth0Client } from "@auth0/nextjs-auth0/server";
import type { SessionData, User } from "@auth0/nextjs-auth0/types";

// The namespaced claim our Auth0 tenant adds the role list to (set by an Action
// or a rule). Namespaced because Auth0 silently drops non-namespaced custom
// claims from the ID token. Overridable for a tenant that uses another namespace.
export const ROLES_CLAIM =
  process.env.AUTH0_ROLES_CLAIM ?? "https://contig/roles";

// The roles allowed to run the action (write) routes. A viewer (any other
// authenticated user) gets read-only access; these two may also act.
const WRITER_ROLES = new Set(["writer", "admin"]);

/**
 * Whether the Auth0 env is configured. We treat the integration as active only
 * when a domain (or issuer base url), client id, and secret are all present.
 * Missing any of these means we cannot run a real flow, so we fall back to the
 * dev bypass rather than crashing at request time.
 */
export function isAuthConfigured(): boolean {
  const domain = process.env.AUTH0_DOMAIN ?? process.env.AUTH0_ISSUER_BASE_URL;
  return Boolean(
    domain &&
      process.env.AUTH0_CLIENT_ID &&
      process.env.AUTH0_CLIENT_SECRET &&
      process.env.AUTH0_SECRET,
  );
}

/**
 * Whether the auth gate is disabled. True when CONTIG_AUTH_DISABLED is "1" (the
 * explicit dev/test bypass) OR no Auth0 env is configured. When disabled the
 * proxy is a no-op and every caller is treated as an admin, so local dev and the
 * Playwright suite work without a real tenant.
 */
export function isAuthDisabled(): boolean {
  return process.env.CONTIG_AUTH_DISABLED === "1" || !isAuthConfigured();
}

// A single Auth0 client, created lazily so importing this module never throws
// when the env is absent (the bypass path must not need a configured tenant).
// The client reads AUTH0_DOMAIN / AUTH0_CLIENT_ID / AUTH0_CLIENT_SECRET /
// AUTH0_SECRET / APP_BASE_URL from the environment itself.
let client: Auth0Client | null = null;

/** The shared Auth0 client. Only call this when isAuthDisabled() is false. */
export function auth0(): Auth0Client {
  if (!client) client = new Auth0Client();
  return client;
}

/**
 * The roles on a user, read from the namespaced claim. Returns an empty list for
 * a user with no roles (a viewer). The claim is whatever Auth0 put there, so we
 * accept only a string array and ignore anything else.
 */
export function rolesOf(user: User | undefined | null): string[] {
  if (!user) return [];
  const raw = user[ROLES_CLAIM];
  if (!Array.isArray(raw)) return [];
  return raw.filter((r): r is string => typeof r === "string");
}

/** Whether a role list grants write access (writer or admin). */
export function hasWriterRole(roles: readonly string[]): boolean {
  return roles.some((r) => WRITER_ROLES.has(r));
}

/**
 * The current session, or null. In the bypass this returns null (there is no
 * real session) and callers treat that as an admin via isAuthDisabled(); when
 * auth is live it returns the real SessionData or null if unauthenticated.
 */
export async function currentSession(): Promise<SessionData | null> {
  if (isAuthDisabled()) return null;
  return auth0().getSession();
}

// What the header shows. In the bypass we present a synthetic "Local admin" so
// the logged-in chrome renders identically in dev and test.
export interface HeaderUser {
  name: string;
  email: string | null;
  picture: string | null;
  roles: string[];
  // True in the dev/test bypass, so the header can omit a real logout link.
  bypass: boolean;
}

/** The user to render in the header: the synthetic admin in the bypass, else the session user. */
export async function headerUser(): Promise<HeaderUser | null> {
  if (isAuthDisabled()) {
    return {
      name: "Local admin",
      email: null,
      picture: null,
      roles: ["admin"],
      bypass: true,
    };
  }
  const session = await auth0().getSession();
  if (!session) return null;
  const user = session.user;
  const roles = rolesOf(user);
  return {
    name: user.name ?? user.nickname ?? user.email ?? "Account",
    email: user.email ?? null,
    picture: user.picture ?? null,
    roles,
    bypass: false,
  };
}

/**
 * Guard for an action (write) route. Returns null when the caller may write
 * (the dev bypass, or an authenticated writer/admin), or a ready-to-return
 * Response when they may not: 401 if unauthenticated, 403 if authenticated but
 * lacking the writer role. Each action route calls this first.
 */
export async function requireWriter(): Promise<Response | null> {
  if (isAuthDisabled()) return null;
  const session = await auth0().getSession();
  if (!session) {
    return Response.json(
      { error: "Authentication required." },
      { status: 401 },
    );
  }
  if (!hasWriterRole(rolesOf(session.user))) {
    return Response.json(
      { error: "A writer or admin role is required for this action." },
      { status: 403 },
    );
  }
  return null;
}
