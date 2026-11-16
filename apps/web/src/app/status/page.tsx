import type { Metadata } from "next";
import { HomeLink } from "@/components/brand/home-link";
import { Logo } from "@/components/brand/logo";
import { SystemStatusPanel } from "@/features/system-status/system-status-panel";

export const metadata: Metadata = { title: "System status" };

/** Developer-facing connectivity check (web ↔ API ↔ database), kept from Phase 1. */
export default function StatusPage() {
  return (
    <main className="flex flex-1 flex-col">
      <div className="border-b border-line bg-paper">
        <div className="mx-auto flex h-14 w-full max-w-5xl items-center px-6">
          <HomeLink>
            <Logo />
          </HomeLink>
        </div>
      </div>
      <div className="mx-auto flex w-full max-w-5xl flex-1 justify-center px-6 py-16">
        <SystemStatusPanel />
      </div>
    </main>
  );
}
