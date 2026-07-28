interface GenerateRadarResponse {
  status: "succeeded";
  run_id: string;
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

async function readApiError(response: Response): Promise<{ message?: string }> {
  try {
    return (await response.json()) as { message?: string };
  } catch {
    return {};
  }
}
