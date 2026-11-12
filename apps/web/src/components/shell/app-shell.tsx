"use client";

import {
  Database,
  FileText,
  History,
  LayoutDashboard,
  Menu,
  MessageSquareText,
  Settings,
  type LucideIcon,
} from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState, type ReactNode } from "react";

import { Logo } from "@/components/brand/logo";
import { Drawer } from "@/components/ui/drawer";
import { ToastProvider } from "@/components/ui/toast";
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
  { href: "/app/history", label: "Query history", icon: History },
  { href: "/app/reports", label: "Reports", icon: FileText },
];
const SECONDARY: NavItem[] = [{ href: "/app/settings", label: "Settings", icon: Settings }];

function NavLinks({
  items,
  pathname,
  onNavigate,
}: {
  items: NavItem[];
  pathname: string;
  onNavigate?: () => void;
}) {
  return (
    <ul className="grid gap-0.5">
      {items.map(({ href, label, icon: Icon }) => {
        const active = pathname === href || pathname.startsWith(`${href}/`);
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

function SidebarContent({ pathname, onNavigate }: { pathname: string; onNavigate?: () => void }) {
  return (
    <div className="flex h-full flex-col">
      <div className="flex h-14 items-center px-4">
        <Link href="/" className="rounded-sm" onClick={onNavigate} aria-label="Sageboard home">
          <Logo />
        </Link>
      </div>
      <nav aria-label="Main" className="flex flex-1 flex-col gap-6 px-2.5 pt-2">
        <NavLinks items={PRIMARY} pathname={pathname} onNavigate={onNavigate} />
        <div className="mt-auto grid gap-3 pb-3">
          <NavLinks items={SECONDARY} pathname={pathname} onNavigate={onNavigate} />
          <div className="rounded-sm border border-amber/40 bg-amber-100/60 px-3 py-2.5">
            <p className="text-xs font-medium text-amber-ink">Demo data</p>
            <p className="mt-0.5 text-2xs leading-4 text-ink-2">
              Figures come from the bundled sample dataset. Live analysis arrives in a later phase.
            </p>
          </div>
          <div className="flex items-center gap-2.5 border-t border-line px-1.5 pt-3">
            <span
              aria-hidden
              className="grid size-7 place-items-center rounded-full bg-navy text-[11px] font-semibold text-warm"
            >
              PR
            </span>
            <div className="min-w-0 leading-tight">
              <p className="truncate text-[13px] font-medium text-ink">Priya Raman</p>
              <p className="truncate text-2xs text-ink-2">Northwind Retail</p>
            </div>
          </div>
        </div>
      </nav>
    </div>
  );
}

export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
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
          <SidebarContent pathname={pathname} />
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
        <SidebarContent pathname={pathname} onNavigate={() => setMenuOpen(false)} />
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
