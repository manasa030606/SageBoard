"use client";

import {
  Database,
  FileText,
  History,
  LayoutDashboard,
  LogOut,
  Menu,
  MessageSquareText,
  Settings,
  type LucideIcon,
} from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { Suspense, useState, type ReactNode } from "react";

import { Logo, LogoMark } from "@/components/brand/logo";
import { Button } from "@/components/ui/button";
import { Drawer } from "@/components/ui/drawer";
import { ErrorState } from "@/components/ui/states";
import { ToastProvider } from "@/components/ui/toast";
import { initials, SessionProvider, useSession } from "@/features/auth/session";
import { cn } from "@/lib/cn";

interface NavItem {
  href: string;
  label: string;
  icon: LucideIcon;
}

const PRIMARY: NavItem[] = [
  { href: "/app/dashboard", label: "Dashboard", icon: LayoutDashboard },
  { href: "/app/analyst", label: "Analyst", icon: MessageSquareText },
  { href: "/app/data", label: "Data sources", icon: Database },
  { href: "/app/history", label: "History", icon: History },
  { href: "/app/reports", label: "Reports", icon: FileText },
];
const SECONDARY: NavItem[] = [{ href: "/app/settings", label: "Settings", icon: Settings }];

/*
 * Instant navigation: the shell and the page render immediately (they're static).
 * Only the active-nav highlight reads the URL, so only it sits behind a Suspense
 * boundary. The user menu appears once the session is known. Pages fetch their own
 * data from the API, which enforces authentication and ownership.
 */
function NavLinks(props: { items: NavItem[]; onNavigate?: () => void }) {
  return (
    <Suspense fallback={<NavList {...props} pathname={null} />}>
      <ActiveNavList {...props} />
    </Suspense>
  );
}

function ActiveNavList(props: { items: NavItem[]; onNavigate?: () => void }) {
  return <NavList {...props} pathname={usePathname()} />;
}

function NavList({
  items,
  pathname,
  onNavigate,
}: {
  items: NavItem[];
  pathname: string | null;
  onNavigate?: () => void;
}) {
  return (
    <ul className="grid gap-0.5">
      {items.map(({ href, label, icon: Icon }) => {
        const active = pathname !== null && (pathname === href || pathname.startsWith(`${href}/`));
        return (
          <li key={href}>
            <Link
              href={href}
              onClick={onNavigate}
              aria-current={active ? "page" : undefined}
              className={cn(
                "group flex h-8 items-center gap-2.5 rounded-sm px-2.5 text-[13.5px] transition-colors duration-150",
                active
                  ? "bg-paper font-medium text-ink shadow-[0_0_0_1px_var(--color-line)]"
                  : "text-ink-2 hover:bg-warm-300/60 hover:text-ink",
              )}
            >
              <Icon
                className={cn(
                  "size-4 shrink-0",
                  active ? "text-forest" : "text-ink-3 group-hover:text-ink-2",
                )}
                aria-hidden
                strokeWidth={1.75}
              />
              {label}
            </Link>
          </li>
        );
      })}
    </ul>
  );
}

function SidebarContent({ onNavigate }: { onNavigate?: () => void }) {
  return (
    <div className="flex h-full flex-col">
      <div className="flex h-14 items-center px-4">
        <Link href="/" className="rounded-sm" onClick={onNavigate} aria-label="Sageboard home">
          <Logo />
        </Link>
      </div>
      <nav aria-label="Main" className="flex flex-1 flex-col gap-6 px-2.5 pt-2">
        <NavLinks items={PRIMARY} onNavigate={onNavigate} />
        <div className="mt-auto grid gap-3 pb-3">
          <NavLinks items={SECONDARY} onNavigate={onNavigate} />
          <UserMenu />
        </div>
      </nav>
    </div>
  );
}

function UserMenu() {
  const { user, authMode, signOut } = useSession();
  if (!user) return null;
  return (
    <div className="flex items-center gap-2.5 border-t border-line px-1.5 pt-3">
      <span
        aria-hidden
        className="grid size-7 shrink-0 place-items-center rounded-full bg-navy text-[11px] font-semibold text-warm"
      >
        {initials(user.full_name)}
      </span>
      <div className="min-w-0 flex-1 leading-tight">
        <p className="truncate text-[13px] font-medium text-ink">{user.full_name}</p>
        <p className="truncate text-2xs text-ink-2">
          {authMode === "demo" ? "Local demo user" : user.email}
        </p>
      </div>
      {authMode === "session" ? (
        <button
          type="button"
          onClick={() => void signOut()}
          className="grid size-8 shrink-0 place-items-center rounded-sm text-ink-2 hover:bg-warm-300/60 hover:text-ink"
          aria-label="Sign out"
          title="Sign out"
        >
          <LogOut className="size-4" aria-hidden strokeWidth={1.75} />
        </button>
      ) : null}
    </div>
  );
}

/**
 * Page area. Pages render straight away (so navigation is instant and the page is part
 * of the prerendered shell); once the session check says there is no session, or the
 * API is unreachable, the page is replaced by a redirect or error frame.
 */
function SessionGate({ children }: { children: ReactNode }) {
  const { status, error, retry } = useSession();
  if (status === "unavailable") {
    return (
      <div className="mx-auto w-full max-w-md px-5 py-16">
        <ErrorState
          title="Sageboard can’t reach its server"
          description={
            error?.message ?? "The API didn’t respond. Check that the backend is running."
          }
          code={error?.code}
          action={
            <Button variant="primary" onClick={retry}>
              Try again
            </Button>
          }
        />
      </div>
    );
  }
  if (status === "unauthenticated") {
    return (
      <div className="grid min-h-[60dvh] place-items-center" role="status" aria-live="polite">
        <div className="flex items-center gap-3 text-sm text-ink-2">
          <LogoMark className="animate-pulse" />
          Redirecting to sign in…
        </div>
      </div>
    );
  }
  return <>{children}</>;
}

export function AppShell({ children }: { children: ReactNode }) {
  return (
    <SessionProvider>
      <AppFrame>
        <SessionGate>{children}</SessionGate>
      </AppFrame>
    </SessionProvider>
  );
}

function AppFrame({ children }: { children: ReactNode }) {
  const [menuOpen, setMenuOpen] = useState(false);

  return (
    <ToastProvider>
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:fixed focus:top-3 focus:left-3 focus:z-50 focus:rounded-sm focus:bg-paper focus:px-3 focus:py-2 focus:text-sm focus:shadow-overlay"
      >
        Skip to content
      </a>
      <div className="flex min-h-dvh">
        <aside className="sticky top-0 hidden h-dvh w-[232px] shrink-0 border-r border-line bg-warm-200/70 lg:block">
          <SidebarContent />
        </aside>

        <div className="flex min-w-0 flex-1 flex-col">
          <header className="sticky top-0 z-30 flex h-14 items-center justify-between border-b border-line bg-warm/95 px-4 backdrop-blur-sm lg:hidden">
            <Link href="/app/dashboard" aria-label="Sageboard dashboard">
              <Logo />
            </Link>
            <button
              type="button"
              onClick={() => setMenuOpen(true)}
              className="grid size-9 place-items-center rounded-sm text-ink-2 hover:bg-warm-200 hover:text-ink"
              aria-label="Open navigation"
              aria-expanded={menuOpen}
            >
              <Menu className="size-5" aria-hidden />
            </button>
          </header>

          <main id="main" tabIndex={-1} className="min-w-0 flex-1 focus:outline-none">
            {children}
          </main>
        </div>
      </div>

      <Drawer
        open={menuOpen}
        onClose={() => setMenuOpen(false)}
        title="Navigation"
        side="left"
        widthClassName="w-[280px] bg-warm"
      >
        <SidebarContent onNavigate={() => setMenuOpen(false)} />
      </Drawer>
    </ToastProvider>
  );
}

/** Standard page container: consistent max width and gutters across app pages. */
export function PageContainer({
  children,
  className,
  wide = false,
}: {
  children: ReactNode;
  className?: string;
  wide?: boolean;
}) {
  return (
    <div
      className={cn(
        "mx-auto w-full px-5 py-8 sm:px-8 lg:py-10",
        wide ? "max-w-[1440px]" : "max-w-[1200px]",
        className,
      )}
    >
      {children}
    </div>
  );
}
