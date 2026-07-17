import type { EventAnalysisResponse } from "../types/radar";

export async function loadEventAnalysis(eventId: string): Promise<EventAnalysisResponse | null> {
  const response = await fetch(`/api/radars/latest/events/${eventId}/analysis`, {
    headers: { Accept: "application/json" },
    cache: "no-store",
  });
  if (response.status === 404) return null;
  return readAnalysisResponse(response);
}

export async function startEventAnalysis(eventId: string): Promise<EventAnalysisResponse> {
  const response = await fetch(`/api/radars/latest/events/${eventId}/analysis`, {
    method: "POST",
    headers: { Accept: "application/json" },
  });
  return readAnalysisResponse(response);
}

async function readAnalysisResponse(response: Response): Promise<EventAnalysisResponse> {
  const payload = (await response.json()) as EventAnalysisResponse & { message?: string };
  if (!response.ok) {
    throw new Error(payload.message || `事件分析接口请求失败（HTTP ${response.status}）`);
  }
  return payload;
}
