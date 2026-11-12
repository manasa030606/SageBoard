"use client";

import { PageContainer } from "@/components/shell/app-shell";
import { Button } from "@/components/ui/button";
import { ErrorState } from "@/components/ui/states";

/** Route-level error boundary for every app page. */
export default function AppError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <PageContainer>
      <ErrorState
        title="This page failed to load"
        description="Something went wrong while rendering it. Your data is unaffected. Try again, or come back in a moment."
        code={error.digest ? `ref ${error.digest}` : undefined}
        action={
          <Button variant="primary" onClick={reset}>
            Try again
          </Button>
        }
      />
    </PageContainer>
  );
}
