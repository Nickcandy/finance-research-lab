import type { RadarGenerationState, RadarGenerationStatus } from "../types/radar";

interface GenerateRadarResponse {
  status: RadarGenerationStatus;
  run_id: string;
  resumed: boolean;
}

export async function generateDailyRadar(): Promise<GenerateRadarResponse> {
  const response = await fetch("/api/radars/generate", {
    method: "POST",
    headers: { Accept: "application/json" },
  });
  if (!response.ok) {
    const payload = await readApiError(response);
    throw new Error(payload.message || `日报生成失败（HTTP ${response.status}）`);
  }
  return response.json() as Promise<GenerateRadarResponse>;
}

export async function loadCurrentRadar(): Promise<RadarGenerationState | null> {
  const response = await fetch("/api/radars/current", {
    headers: { Accept: "application/json" },
    cache: "no-store",
  });
  if (response.status === 404) return null;
  if (!response.ok) {
    const payload = await readApiError(response);
    throw new Error(payload.message || `更新状态读取失败（HTTP ${response.status}）`);
  }
  const payload: unknown = await response.json();
  if (
    typeof payload !== "object"
    || payload === null
    || !("schema_version" in payload)
    || payload.schema_version !== "1.0"
  ) {
    throw new Error("更新状态格式无效。");
  }
  return payload as RadarGenerationState;
}

export async function cancelDailyRadar(): Promise<RadarGenerationState> {
  const response = await fetch("/api/radars/current/cancel", {
    method: "POST",
    headers: { Accept: "application/json" },
  });
  if (!response.ok) {
    const payload = await readApiError(response);
    throw new Error(payload.message || `停止更新失败（HTTP ${response.status}）`);
  }
  return response.json() as Promise<RadarGenerationState>;
}

async function readApiError(response: Response): Promise<{ message?: string }> {
  try {
    return (await response.json()) as { message?: string };
  } catch {
    return {};
  }
}
