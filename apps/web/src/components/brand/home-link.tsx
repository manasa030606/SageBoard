"use client";

import Link from "next/link";
import type { ReactNode } from "react";

import { useSignedIn } from "@/features/auth/use-signed-in";
import { DASHBOARD_HREF, LANDING_HREF } from "@/lib/routes";

/**
 * The Sageboard logo link for pages outside the app shell. It leads to the dashboard only
 * once the API has confirmed a live session; while that is still being checked, and for
 * visitors, on any error, it leads to the public landing page.
 */
export function HomeLink({ className, children }: { className?: string; children: ReactNode }) {
  const status = useSignedIn();
  const signedIn = status === "signed-in";
  return (
    <Link
      // Visible in the browser's inspector, so "why did it go there?" has a one-glance answer.
      data-auth-state={status}
      href={signedIn ? DASHBOARD_HREF : LANDING_HREF}
      aria-label={signedIn ? "Sageboard dashboard" : "Sageboard home"}
      className={className}
    >
      {children}
    </Link>
  );
}
