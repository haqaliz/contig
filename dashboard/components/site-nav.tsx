"use client";

// Primary nav links with an active state. usePathname drives which link reads as
// current: the active link is foreground and emphasized, the rest stay muted.
// Kept as a small client component so the rest of the header can remain static.
import Link from "next/link";
import { usePathname } from "next/navigation";

import { cn } from "@/lib/utils";

const LINKS: { href: string; label: string }[] = [
  { href: "/runs", label: "Runs" },
  { href: "/eval", label: "Detector" },
  { href: "/pending", label: "Pending" },
];

export function SiteNav() {
  const pathname = usePathname();

  return (
    <div className="flex items-center gap-1 text-sm">
      {LINKS.map((link) => {
        // A link is active when the path is the link itself or nested under it
        // (so /runs/testpass2 still marks "Runs" as current).
        const active =
          pathname === link.href || pathname.startsWith(`${link.href}/`);
        return (
          <Link
            key={link.href}
            href={link.href}
            aria-current={active ? "page" : undefined}
            className={cn(
              "rounded-md px-2.5 py-1.5 font-medium transition-colors",
              active
                ? "bg-muted text-foreground"
                : "text-muted-foreground hover:text-foreground",
            )}
          >
            {link.label}
          </Link>
        );
      })}
    </div>
  );
}
