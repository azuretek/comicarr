/** Return the normalized origin for an HTTP(S) URL, or null for invalid input. */
export function httpOrigin(value: unknown): string | null {
  try {
    const url = new URL(String(value ?? ""));
    return url.protocol === "http:" || url.protocol === "https:"
      ? url.origin
      : null;
  } catch {
    return null;
  }
}
