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
  return (await response.json()) as RadarSnapshot;
}

async function readApiError(response: Response): Promise<ApiError> {
  try {
    return (await response.json()) as ApiError;
  } catch {
    return {};
  }
}
