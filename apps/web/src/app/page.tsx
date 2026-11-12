import { SystemStatusPanel } from "@/features/system-status/system-status-panel";

/**
 * Phase 1 home: a system status page proving web ↔ API connectivity.
 * It is replaced by the marketing landing page in Phase 8.
 */
export default function HomePage() {
  return (
    <main className="flex flex-1 flex-col">
      <div className="border-b border-sage-300 bg-paper">
        <div className="mx-auto flex h-14 w-full max-w-5xl items-center gap-3 px-6">
          <span aria-hidden className="grid size-6 place-items-center rounded-sm bg-forest-700">
            <span className="block size-2.5 rounded-[1px] bg-warm-white" />
          </span>
          <span className="text-[15px] font-semibold tracking-tight text-navy-950">Sageboard</span>
        </div>
      </div>
      <div className="mx-auto flex w-full max-w-5xl flex-1 justify-center px-6 py-16">
        <SystemStatusPanel />
      </div>
    </main>
  );
}
