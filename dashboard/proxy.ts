// The authentication and authorization boundary (PRD contract C). Next 16 calls
// this the "proxy" (the former middleware convention); it runs before any route
// renders. proxy uses the standard Request type.
//
// Layers:
//   - In the dev/test bypass (CONTIG_AUTH_DISABLED=1, or no Auth0 env) this is a
//     no-op: every request passes through and the app treats the caller as admin.
//     Local dev and the Playwright suite need no real tenant.
//   - When auth is live, auth0.middleware mounts the /auth/* routes (login,
//     logout, callback) and rolls the session. An unauthenticated request to any
//     app route is redirected to login. A request to a write (action) API route
//     without the writer/admin role is rejected with 403; the action routes also
//     re-check this themselves (requireWriter), so authorization never rests on
//     this matcher alone.
import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

import { auth0, hasWriterRole, isAuthDisabled, rolesOf } from "./lib/auth0";

// The write (action) API routes: anything that dispatches, controls, verifies a
// run, or mutates the corpus. A POST to one of these needs the writer/admin role.
// Read views and read-only API routes (manifest, progress, plan preview) are
// allowed for any authenticated user. Matched as path prefixes/suffixes against
// /api/runs/<...> and /api/corpus/promote.
function isWriteApiPath(pathname: string): boolean {
  if (pathname === "/api/corpus/promote") return true;
  if (pathname === "/api/runs/dispatch" || pathname === "/api/runs/launch") {
    return true;
  }
  // /api/runs/<id>/{cancel,resume,approve,reproduce,verify}
  return /^\/api\/runs\/[^/]+\/(cancel|resume|approve|reproduce|verify)$/.test(
    pathname,
  );
}

export async function proxy(request: NextRequest): Promise<NextResponse> {
  // Dev/test bypass: pass everything through untouched. No tenant needed.
  if (isAuthDisabled()) {
    return NextResponse.next();
  }

  const { pathname } = request.nextUrl;

  // Let the SDK own its own routes (login, logout, callback) and roll the
  // session cookie. Its response (a redirect or a next() with refreshed cookies)
  // is what we return for those paths and what we build on for the rest.
  const authRes = await auth0().middleware(request);
  if (pathname.startsWith("/auth/")) {
    return authRes;
  }

  // Every other route requires a session. Send an unauthenticated caller to
  // login, preferring the SDK's own response when it already redirects.
  const session = await auth0().getSession(request);
  if (!session) {
    const loginUrl = new URL("/auth/login", request.nextUrl.origin);
    // returnTo brings the user back to where they were after authenticating.
    loginUrl.searchParams.set("returnTo", pathname + request.nextUrl.search);
    return NextResponse.redirect(loginUrl);
  }

  // Authenticated. A write (action) API route additionally needs the writer or
  // admin role; a viewer is read-only and gets a 403 here (the route re-checks).
  if (isWriteApiPath(pathname) && !hasWriterRole(rolesOf(session.user))) {
    return NextResponse.json(
      { error: "A writer or admin role is required for this action." },
      { status: 403 },
    );
  }

  // Carry the SDK response forward so any refreshed session cookie is preserved.
  return authRes;
}

export const config = {
  matcher: [
    // Run on every route except Next internals and static metadata files, so the
    // session is rolled everywhere and no page renders before the gate.
    "/((?!_next/static|_next/image|favicon.ico|sitemap.xml|robots.txt).*)",
  ],
};
