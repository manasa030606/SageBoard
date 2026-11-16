"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useState, type FormEvent } from "react";

import { AnalyticsIllustration } from "@/components/brand/analytics-illustration";
import { HomeLink } from "@/components/brand/home-link";
import { Logo } from "@/components/brand/logo";
import { Button } from "@/components/ui/button";
import { Field, Input, PasswordInput } from "@/components/ui/field";
import { Notice } from "@/components/ui/states";
import { hardNavigate } from "@/features/auth/session";
import { SignedInNotice } from "@/features/auth/signed-in-notice";
import { auth } from "@/lib/api/endpoints";
import { ApiError } from "@/lib/api/errors";

type Mode = "login" | "register";

const MIN_PASSWORD = 10;

function safeNext(raw: string | null): string {
  // Only same-app paths: never redirect to another site after sign-in.
  return raw && raw.startsWith("/app") && !raw.startsWith("//") ? raw : "/app/data";
}

export function AuthForm({ mode }: { mode: Mode }) {
  const params = useSearchParams();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  const [touched, setTouched] = useState(false);

  const isRegister = mode === "register";
  const passwordTooShort = isRegister && password.length > 0 && password.length < MIN_PASSWORD;
  const fieldError = (code: string) => (error?.code === code ? error.message : undefined);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setTouched(true);
    if (isRegister && password.length < MIN_PASSWORD) return;
    setBusy(true);
    setError(null);
    try {
      if (isRegister) await auth.register(email, password, name);
      else await auth.login(email, password);
      hardNavigate(safeNext(params.get("next")));
    } catch (e) {
      setError(
        e instanceof ApiError
          ? e
          : new ApiError({
              status: 0,
              code: "UNKNOWN",
              message: "Something went wrong. Try again.",
            }),
      );
      setBusy(false);
    }
  }

  const formLevelError =
    error && !["INVALID_EMAIL", "WEAK_PASSWORD", "INVALID_NAME"].includes(error.code)
      ? error
      : null;

  return (
    <div className="grid min-h-dvh lg:grid-cols-[minmax(0,5fr)_minmax(0,6fr)]">
      <aside className="relative hidden min-w-0 flex-col bg-navy px-10 py-10 text-warm lg:flex lg:h-dvh lg:min-h-[600px] xl:px-12 xl:py-12 [@media(max-height:760px)]:py-8">
        <HomeLink className="w-fit rounded-sm">
          <Logo inverted />
        </HomeLink>
        {/* The illustration takes whatever height the text leaves, so it is shown on every
            laptop screen and only gets smaller on short ones. */}
        <div className="flex min-h-0 flex-1 flex-col justify-center py-6 [@media(max-height:760px)]:py-3">
          <div className="max-w-md">
            <p className="eyebrow text-sage">Sageboard</p>
            <p className="mt-4 text-display text-[34px] leading-[1.1] text-warm xl:text-[40px] [@media(max-height:760px)]:mt-2 [@media(max-height:760px)]:text-[32px]">
              Your data. Your questions. Clear decisions.
            </p>
          </div>
          <div className="relative my-6 min-h-[170px] w-full max-w-[520px] flex-1 [@media(max-height:760px)]:my-3">
            <AnalyticsIllustration className="absolute inset-0" />
          </div>
          <ul className="grid max-w-md gap-3 text-[14px] leading-6 text-warm/80 [@media(max-height:760px)]:gap-2">
            <li className="border-l-2 border-sage/60 pl-4">
              Every dataset lives in its own isolated schema that only you can query.
            </li>
            <li className="border-l-2 border-sage/60 pl-4">
              Analysis runs on a read-only connection, so nothing can change your data.
            </li>
            <li className="border-l-2 border-sage/60 pl-4">
              Sensitive columns are detected and masked by default.
            </li>
          </ul>
        </div>
        <p className="text-2xs text-warm/60">
          Passwords are stored as argon2id hashes, never in plain text.
        </p>
      </aside>

      <main className="flex items-center justify-center bg-warm px-5 py-12">
        <div className="w-full max-w-[380px]">
          <HomeLink className="mb-10 block w-fit rounded-sm lg:hidden">
            <Logo />
          </HomeLink>
          <h1 className="text-title text-[28px] text-ink">
            {isRegister ? "Create your account" : "Sign in"}
          </h1>
          <p className="mt-2 text-sm text-ink-2">
            {isRegister ? (
              <>
                Already have one?{" "}
                <Link
                  href="/login"
                  className="font-medium text-forest underline-offset-2 hover:underline"
                >
                  Sign in
                </Link>
              </>
            ) : (
              <>
                New to Sageboard?{" "}
                <Link
                  href="/register"
                  className="font-medium text-forest underline-offset-2 hover:underline"
                >
                  Create an account
                </Link>
              </>
            )}
          </p>

          <SignedInNotice />

          <form className="mt-8 grid gap-4" onSubmit={submit} noValidate>
            {formLevelError ? (
              <Notice
                tone="error"
                title={formLevelError.status === 0 ? "Can’t reach Sageboard" : undefined}
              >
                {formLevelError.message}
              </Notice>
            ) : null}
            {isRegister ? (
              <Field label="Full name" error={fieldError("INVALID_NAME")}>
                {({ id, describedBy, invalid }) => (
                  <Input
                    id={id}
                    autoComplete="name"
                    required
                    maxLength={200}
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    aria-describedby={describedBy}
                    aria-invalid={invalid}
                  />
                )}
              </Field>
            ) : null}
            <Field label="Email" error={fieldError("INVALID_EMAIL")}>
              {({ id, describedBy, invalid }) => (
                <Input
                  id={id}
                  type="email"
                  autoComplete="email"
                  required
                  maxLength={320}
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  aria-describedby={describedBy}
                  aria-invalid={invalid}
                />
              )}
            </Field>
            <Field
              label="Password"
              hint={
                isRegister
                  ? `At least ${MIN_PASSWORD} characters. A short phrase works well.`
                  : undefined
              }
              error={
                fieldError("WEAK_PASSWORD") ??
                (touched && passwordTooShort
                  ? `Use at least ${MIN_PASSWORD} characters.`
                  : undefined)
              }
            >
              {({ id, describedBy, invalid }) => (
                <PasswordInput
                  id={id}
                  autoComplete={isRegister ? "new-password" : "current-password"}
                  required
                  maxLength={128}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  aria-describedby={describedBy}
                  aria-invalid={invalid}
                />
              )}
            </Field>
            <Button
              type="submit"
              variant="primary"
              size="lg"
              className="mt-2 w-full"
              disabled={busy || !email || !password || (isRegister && !name.trim())}
            >
              {busy
                ? isRegister
                  ? "Creating account…"
                  : "Signing in…"
                : isRegister
                  ? "Create account"
                  : "Sign in"}
            </Button>
          </form>
        </div>
      </main>
    </div>
  );
}
