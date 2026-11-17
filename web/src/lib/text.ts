/** Display-only text cleanup. The stored record keeps the source's own bytes. */

/** Crossref/JATS titles can carry inline markup such as `<scp>M</scp>`; strip it for display. */
export function cleanTitle(value: string | null | undefined): string {
  if (!value) return "";
  return value
    .replace(/<[^>]+>/g, "")
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .replace(/&amp;/g, "&")
    .replace(/\s+/g, " ")
    .trim();
}
