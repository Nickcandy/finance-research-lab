import fixture from "../fixtures/daily-radar.json";
import type { RadarSnapshot } from "../types/radar";

export type PreviewState = "success" | "loading" | "empty" | "error";

const snapshot = fixture as RadarSnapshot;

export function getPreviewState(search = window.location.search): PreviewState {
  const state = new URLSearchParams(search).get("state");
  if (state === "loading" || state === "empty" || state === "error") {
    return state;
  }
  return "success";
}

export async function loadRadarPreview(state: PreviewState): Promise<RadarSnapshot> {
  if (state === "loading") {
    return new Promise<RadarSnapshot>(() => undefined);
  }
  await new Promise((resolve) => window.setTimeout(resolve, 180));
  if (state === "error") {
    throw new Error("本地日报数据暂时无法读取");
  }
  if (state === "empty") {
    return {
      ...snapshot,
      summary: {
        event_count: 0,
        verified_count: 0,
        unverified_count: 0,
        excluded_count: 0,
        source_count: 0,
      },
      events: [],
      candidate_groups: {
        verified: [],
        unverified: [],
        excluded: [],
        watchlist: [],
      },
      validation_tasks: [],
    };
  }
  return snapshot;
}
