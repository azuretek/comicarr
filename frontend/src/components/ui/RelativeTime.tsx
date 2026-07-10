import { format, formatDistanceToNowStrict } from "date-fns";

function parseDate(value: string): Date | null {
  if (!value) return null;
  const normalized = value.includes("T") ? value : value.replace(" ", "T");
  const date = new Date(normalized);
  return Number.isNaN(date.getTime()) ? null : date;
}

export default function RelativeTime({ value }: { value?: string | null }) {
  const date = parseDate(value || "");
  if (!date) return <span className="text-muted-foreground">—</span>;

  return (
    <time
      dateTime={date.toISOString()}
      title={format(date, "PPpp")}
      className="font-mono text-[11px] text-muted-foreground whitespace-nowrap"
    >
      {formatDistanceToNowStrict(date, { addSuffix: true })}
    </time>
  );
}
