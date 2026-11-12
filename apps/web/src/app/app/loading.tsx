import { PageContainer } from "@/components/shell/app-shell";
import { Skeleton } from "@/components/ui/states";

/** Shown while an app page streams in. */
export default function AppLoading() {
  return (
    <PageContainer wide>
      <div aria-busy="true" aria-label="Loading" className="grid gap-8">
        <div className="grid gap-3">
          <Skeleton className="h-3 w-40" />
          <Skeleton className="h-8 w-64" />
          <Skeleton className="h-4 w-96 max-w-full" />
        </div>
        <Skeleton className="h-28 w-full" />
        <div className="grid gap-8 xl:grid-cols-[2fr_1fr]">
          <Skeleton className="h-80 w-full" />
          <Skeleton className="h-80 w-full" />
        </div>
      </div>
    </PageContainer>
  );
}
