"use client";

// The header account widget (PRD contract C). A small dropdown that shows the
// logged-in user and a logout link. Rendered from a server component (UserMenu
// below) that resolves the session; this island only renders what it is handed.
//
// In the dev/test bypass the user is a synthetic "Local admin" and there is no
// real logout link (there is no real session to end), so the menu omits it.
import { LogOut, User as UserIcon } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";

export interface UserMenuProps {
  name: string;
  email: string | null;
  roles: string[];
  // True in the dev/test bypass: no real session, so no logout link.
  bypass: boolean;
}

// The role shown as the user's badge: admin wins, then writer, else viewer.
function primaryRole(roles: string[]): string {
  if (roles.includes("admin")) return "admin";
  if (roles.includes("writer")) return "writer";
  return "viewer";
}

export function UserMenuClient({ name, email, roles, bypass }: UserMenuProps) {
  const role = primaryRole(roles);
  return (
    <DropdownMenu>
      <DropdownMenuTrigger
        render={
          <Button
            variant="ghost"
            size="sm"
            className="gap-1.5"
            aria-label="Account"
          >
            <UserIcon className="size-4" aria-hidden="true" />
            <span className="max-w-40 truncate">{name}</span>
          </Button>
        }
      />
      <DropdownMenuContent align="end" className="min-w-56">
        {/* A static account summary header. Kept a plain div (not a menu group
            label) so it needs no enclosing Menu.Group. */}
        <div className="flex flex-col gap-0.5 px-1.5 py-1">
          <span className="text-sm font-medium text-foreground">{name}</span>
          {email ? (
            <span className="text-xs text-muted-foreground">{email}</span>
          ) : null}
          <span className="text-xs text-muted-foreground">Role: {role}</span>
        </div>
        {bypass ? null : (
          <>
            <DropdownMenuSeparator />
            {/* Auth routing must use a plain anchor, not next/link, so the
                navigation hits the server and the SDK can end the session. */}
            <DropdownMenuItem
              variant="destructive"
              render={
                <a href="/auth/logout">
                  <LogOut className="size-4" aria-hidden="true" />
                  Log out
                </a>
              }
            />
          </>
        )}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
