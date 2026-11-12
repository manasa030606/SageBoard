/** Join class names, skipping falsy values. Keeps conditional styling readable. */
export function cn(...classes: Array<string | false | null | undefined>): string {
  return classes.filter(Boolean).join(" ");
}
