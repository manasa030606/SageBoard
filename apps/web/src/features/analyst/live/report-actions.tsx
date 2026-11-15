"use client";

import { FileDown, FileText } from "lucide-react";
import { useEffect, useState } from "react";

import { Button, ButtonLink } from "@/components/ui/button";
import { useToast } from "@/components/ui/toast";
import { reports } from "@/lib/api/endpoints";
import { fileSlug, saveFile } from "@/lib/download";
import { errorMessage, toApiError } from "@/lib/use-api";

/**
 * Save an answer as a report, then open or download it. Whether this analysis already has a
 * report comes from the server, so reopening an old analysis shows its real saved state.
 */
export function ReportActions({ sessionId }: { sessionId: string }) {
  const { notify } = useToast();
  const [report, setReport] = useState<{ id: string; title: string } | null>(null);
  const [busy, setBusy] = useState<"save" | "pdf" | null>(null);

  useEffect(() => {
    let active = true;
    reports
      .forSession(sessionId)
      .then((items) => {
        if (active && items[0]) setReport({ id: items[0].id, title: items[0].title });
      })
      .catch(() => {
        // Not knowing is fine: the button simply offers to save.
      });
    return () => {
      active = false;
    };
  }, [sessionId]);

  async function save() {
    setBusy("save");
    try {
      const created = await reports.create(sessionId);
      setReport({ id: created.id, title: created.title });
      notify({
        tone: "success",
        title: "Saved as report",
        description: `“${created.title}” is now under Reports.`,
      });
    } catch (err) {
      notify({
        tone: "error",
        title: "Couldn’t save the report",
        description: toApiError(err).message,
      });
    } finally {
      setBusy(null);
    }
  }

  async function download() {
    if (!report) return;
    setBusy("pdf");
    try {
      saveFile(fileSlug(report.title, "pdf"), await reports.pdf(report.id));
    } catch (err) {
      notify({ tone: "error", title: "Couldn’t download the PDF", description: errorMessage(err) });
    } finally {
      setBusy(null);
    }
  }

  if (!report) {
    return (
      <Button
        size="sm"
        variant="secondary"
        disabled={busy !== null}
        leadingIcon={<FileText className="size-3.5" aria-hidden />}
        onClick={() => void save()}
      >
        {busy === "save" ? "Saving…" : "Save as report"}
      </Button>
    );
  }
  return (
    <div className="flex flex-wrap items-center gap-2">
      <ButtonLink
        href={`/app/reports/${report.id}`}
        size="sm"
        variant="secondary"
        leadingIcon={<FileText className="size-3.5" aria-hidden />}
      >
        View report
      </ButtonLink>
      <Button
        size="sm"
        variant="secondary"
        disabled={busy !== null}
        leadingIcon={<FileDown className="size-3.5" aria-hidden />}
        onClick={() => void download()}
      >
        {busy === "pdf" ? "Preparing PDF…" : "Download PDF"}
      </Button>
    </div>
  );
}
