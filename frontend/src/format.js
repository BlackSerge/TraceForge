export function formatDate(value) {
  return value ? new Date(value).toLocaleString("en-US") : "—";
}
