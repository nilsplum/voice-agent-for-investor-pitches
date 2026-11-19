/**
 * How times are shown in the German interface, decided in one place. The backend sends every time
 * as an ISO 8601 string in UTC; the browser shows it in the user's local time.
 */
const DATE_TIME = new Intl.DateTimeFormat("de-DE", { dateStyle: "medium", timeStyle: "short" });

export function formatDateTime(iso: string): string {
  return DATE_TIME.format(new Date(iso));
}
