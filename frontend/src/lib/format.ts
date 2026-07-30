import { format } from "date-fns";

export function formatLatency(ms: number): string {
  if (ms >= 1000) {
    return (
      new Intl.NumberFormat("en-US", {
        minimumFractionDigits: 1,
        maximumFractionDigits: 1,
      }).format(ms / 1000) + "s"
    );
  }

  return (
    new Intl.NumberFormat("en-US", { maximumFractionDigits: 3 }).format(ms) +
    "ms"
  );
}

export function formatMilliseconds(value: number) {
  return new Intl.NumberFormat("en-US", { maximumFractionDigits: 3 }).format(
    value,
  );
}

export function formatDate(value: Date | string) {
  return format(new Date(`${value}`), "LLL dd, y HH:mm");
}

/** Storage / API sentinel for unknown comic issue dates (MySQL zero-date style). */
const UNKNOWN_DATE_SENTINELS = new Set(["0000-00-00"]);

/** User-facing placeholder when an issue date is absent or a sentinel. */
export const UNKNOWN_DATE_DISPLAY = "—";

/**
 * True when a value is not a displayable calendar date for issue tables.
 * Treats null, empty/whitespace, and the 0000-00-00 storage sentinel as unknown.
 */
export function isUnknownComicDate(value: unknown): boolean {
  if (value == null) return true;
  const trimmed = String(value).trim();
  if (trimmed === "") return true;
  return UNKNOWN_DATE_SENTINELS.has(trimmed);
}

/**
 * First usable date among candidates (release date preferred over cover/issue date).
 * Skips null, empty, and sentinel values so a known cover date is not hidden by
 * a zero release date.
 */
export function pickComicDate(
  ...candidates: Array<string | null | undefined>
): string | null {
  for (const candidate of candidates) {
    if (!isUnknownComicDate(candidate)) {
      return String(candidate).trim();
    }
  }
  return null;
}

/**
 * Presentation-boundary formatting for series issue dates.
 * Valid ISO-like strings pass through unchanged; unknown/sentinel → placeholder.
 */
export function displayComicDate(
  value: unknown,
  placeholder: string = UNKNOWN_DATE_DISPLAY,
): string {
  if (isUnknownComicDate(value)) return placeholder;
  return String(value).trim();
}

export function formatCompactNumber(value: number) {
  if (value >= 100 && value < 1000) {
    return value.toString(); // Keep the number as is if it's in the hundreds
  } else if (value >= 1000 && value < 1000000) {
    return (value / 1000).toFixed(1) + "k"; // Convert to 'k' for thousands
  } else if (value >= 1000000) {
    return (value / 1000000).toFixed(1) + "M"; // Convert to 'M' for millions
  } else {
    return value.toString(); // Optionally handle numbers less than 100 if needed
  }
}
