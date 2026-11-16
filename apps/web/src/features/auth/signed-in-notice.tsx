"use client";

import { useState } from "react";

import { Button, ButtonLink } from "@/components/ui/button";
import { Notice } from "@/components/ui/states";
import { hardNavigate } from "@/features/auth/session";
import { useSessionProbe } from "@/features/auth/use-signed-in";
import { auth } from "@/lib/api/endpoints";
import { setCsrfToken } from "@/lib/api/client";
import { DASHBOARD_HREF } from "@/lib/routes";

/**
 * Shown on the sign-in and sign-up pages only when the API confirms a live session in this
 * browser. Without it a signed-in person could open /login, see an ordinary form, and wonder
 * why the logo (rightly) leads to the dashboard. The form stays usable, so switching to
 * another account is still possible after signing out here.
 */
export function SignedInNotice() {
  const { status, info } = useSessionProbe();
  const [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState(false);
  if (status !== "signed-in" || !info) return null;

  async function signOut() {
    if (!info) return;
    setBusy(true);
    setFailed(false);
    try {
      setCsrfToken(info.csrf_token);
      await auth.logout();
      hardNavigate("/login");
    } catch {
      setFailed(true);
      setBusy(false);
    }
  }

  return (
    <Notice tone="info" title="You’re already signed in" className="mt-6">
      <p>
        As <strong>{info.user.full_name}</strong> in this browser.
      </p>
      <div className="mt-3 flex flex-wrap items-center gap-2">
        <ButtonLink href={DASHBOARD_HREF} variant="primary" size="sm">
          Go to dashboard
        </ButtonLink>
        <Button variant="secondary" size="sm" onClick={() => void signOut()} disabled={busy}>
          {busy ? "Signing out…" : "Sign out"}
        </Button>
      </div>
      {failed ? (
        <p role="alert" className="mt-2 text-rust">
          Couldn’t sign out. Try again.
        </p>
      ) : null}
    </Notice>
  );
}
