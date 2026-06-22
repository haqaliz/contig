// Server wrapper for the header account widget (PRD contract C). It resolves the
// current user (the synthetic "Local admin" in the dev/test bypass, else the
// Auth0 session user) and hands the plain data to the client menu island. If
// there is somehow no user behind the gate, it shows a login link instead.
import { buttonVariants } from "@/components/ui/button";
import { UserMenuClient } from "@/components/auth/user-menu";
import { headerUser } from "@/lib/auth0";

// The session is per-request, so this must never be statically cached.
export const dynamic = "force-dynamic";

export async function UserMenuServer() {
  const user = await headerUser();
  if (!user) {
    // Unauthenticated (only reachable if the gate is off for this path): offer a
    // login link. Auth routing must use a plain anchor (not next/link) so the
    // request reaches the server and the SDK can start the flow.
    return (
      <a
        href="/auth/login"
        className={buttonVariants({ variant: "ghost", size: "sm" })}
      >
        Log in
      </a>
    );
  }
  return (
    <UserMenuClient
      name={user.name}
      email={user.email}
      roles={user.roles}
      bypass={user.bypass}
    />
  );
}
