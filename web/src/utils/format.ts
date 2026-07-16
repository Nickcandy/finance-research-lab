const dateTimeFormatter = new Intl.DateTimeFormat("zh-CN", {
  timeZone: "Asia/Shanghai",
  month: "2-digit",
  day: "2-digit",
  hour: "2-digit",
  minute: "2-digit",
  hour12: false,
});

const fullDateFormatter = new Intl.DateTimeFormat("zh-CN", {
  timeZone: "Asia/Shanghai",
  year: "numeric",
  month: "long",
  day: "numeric",
  weekday: "short",
});

export function formatDateTime(value: string): string {
  return dateTimeFormatter.format(new Date(value));
}

export function formatFullDate(value: string): string {
  return fullDateFormatter.format(new Date(value));
}

export function formatWindow(start: string, end: string): string {
  return `${formatDateTime(start)} — ${formatDateTime(end)}`;
}

export function freshnessLabel(value: string, now = new Date()): string {
  const minutes = Math.max(0, Math.floor((now.getTime() - new Date(value).getTime()) / 60_000));
  if (minutes < 1) return "刚刚更新";
  if (minutes < 60) return `${minutes} 分钟前更新`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours} 小时前更新`;
  return `${Math.floor(hours / 24)} 天前更新`;
}

export function isStale(value: string, now = new Date()): boolean {
  return now.getTime() - new Date(value).getTime() > 24 * 60 * 60 * 1000;
}
