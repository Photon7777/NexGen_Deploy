const TZ = "America/New_York";

const dateTime = new Intl.DateTimeFormat("en-US", {
  weekday: "short",
  month: "short",
  day: "numeric",
  hour: "numeric",
  minute: "2-digit",
  timeZone: TZ,
});
const day = new Intl.DateTimeFormat("en-US", { weekday: "long", month: "short", day: "numeric", timeZone: TZ });
const clock = new Intl.DateTimeFormat("en-US", { hour: "numeric", minute: "2-digit", timeZone: TZ });

export const formatDue = (iso: string) => dateTime.format(new Date(iso));
export const formatDay = (iso: string) => day.format(new Date(iso));
export const formatClock = (iso: string) => clock.format(new Date(iso));
export const hoursBetween = (a: string, b: string) => (new Date(b).getTime() - new Date(a).getTime()) / 3_600_000;

export function relativeDays(daysLeft: number, overdue: boolean): string {
  if (overdue) return "Past due";
  if (daysLeft < 1) return "Due today";
  const d = Math.round(daysLeft * 10) / 10;
  return `${d} days left`;
}

export const DEFAULT_PLAN_SETTINGS = { daily_cap_hours: 4, start_hour: 9, end_hour: 22 };
