import { FileQuestion } from "lucide-react";

import { PageContainer } from "@/components/shell/app-shell";
import { ButtonLink } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/states";

export default function AppNotFound() {
  return (
    <PageContainer>
      <EmptyState
        className="mt-16"
        icon={<FileQuestion className="size-5" aria-hidden />}
        title="We couldn’t find that page"
        description="It may have been deleted, or the link is out of date."
        action={
          <ButtonLink href="/app/dashboard" variant="primary">
            Back to dashboard
          </ButtonLink>
        }
      />
    </PageContainer>
  );
}
