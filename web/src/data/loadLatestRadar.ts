import type { RadarSnapshot } from "../types/radar";

interface ApiError {
  message?: string;
}

export async function loadLatestRadar(): Promise<RadarSnapshot | null> {
  const response = await fetch("/api/radars/latest", {
    headers: { Accept: "application/json" },
    cache: "no-store",
  });
  if (response.status === 404) return null;
  if (!response.ok) {
    const payload = await readApiError(response);
    throw new Error(payload.message || `日报接口请求失败（HTTP ${response.status}）`);
  }
  const payload: unknown = await response.json();
  if (
    typeof payload !== "object"
    || payload === null
    || !("schema_version" in payload)
    || payload.schema_version !== "2.2"
  ) {
    throw new Error("仅支持 DailyRadarSnapshot 2.2，请重新生成日报。");
  }
  return payload as RadarSnapshot;
}

async function readApiError(response: Response): Promise<ApiError> {
  try {
    return (await response.json()) as ApiError;
  } catch {
    return {};
  }
}
