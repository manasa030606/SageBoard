/** Save a file the user asked for. Keeps the object URL alive only for the click. */
export function saveFile(filename: string, data: Blob | string, type = "text/plain"): void {
  const blob =
    typeof data === "string" ? new Blob([data], { type: `${type};charset=utf-8` }) : data;
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.append(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

/** The same header-safe slug the API uses for its Content-Disposition filenames. */
export function fileSlug(title: string, extension: string): string {
  const slug = title
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 60);
  return `${slug || "report"}.${extension}`;
}
