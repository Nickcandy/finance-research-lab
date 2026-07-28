import type { NewsLink, RadarEventItem, RadarSnapshot } from "../types/radar";

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
    || payload.schema_version !== "2.3"
  ) {
    throw new Error("仅支持 DailyRadarSnapshot 2.3，请重新生成日报。");
  }
  return attachLegacyNewsLinks(payload as RadarSnapshot);
}

function attachLegacyNewsLinks(snapshot: RadarSnapshot): RadarSnapshot {
  const newsByEvent = new Map(
    snapshot.all_events.map((event) => [event.id, newsLinks(event.items)]),
  );
  const candidateLinks = (eventIds: string[], current?: NewsLink[]) => (
    current?.length
      ? current
      : newsLinks(eventIds.flatMap((eventId) => newsByEvent.get(eventId) ?? []))
  );
  const hydrateCandidate = <T extends { event_ids: string[]; news_links?: NewsLink[] }>(candidate: T): T => ({
    ...candidate,
    news_links: candidateLinks(candidate.event_ids, candidate.news_links),
  });
  const groups: RadarSnapshot["candidate_groups"] = {
    verified: snapshot.candidate_groups.verified.map(hydrateCandidate),
    unverified: snapshot.candidate_groups.unverified.map(hydrateCandidate),
    excluded: snapshot.candidate_groups.excluded.map(hydrateCandidate),
    watchlist: snapshot.candidate_groups.watchlist.map(hydrateCandidate),
  };
  return {
    ...snapshot,
    events: snapshot.events.map((event) => ({
      ...event,
      candidates: event.candidates.map(hydrateCandidate),
    })),
    all_events: snapshot.all_events.map((event) => ({
      ...event,
      related_stocks: event.related_stocks?.map((stock) => ({
        ...stock,
        news_links: stock.news_links?.length ? stock.news_links : newsByEvent.get(event.id) ?? [],
      })),
    })),
    candidate_groups: groups,
    research_candidates: snapshot.research_candidates.map(hydrateCandidate),
  };
}

function newsLinks(items: Array<RadarEventItem | NewsLink>): NewsLink[] {
  return [...new Map(items.filter((item) => item.url).map((item) => [item.url, {
    headline: item.headline,
    source: item.source,
    url: item.url,
    published_at: item.published_at,
  }])).values()];
}

async function readApiError(response: Response): Promise<ApiError> {
  try {
    return (await response.json()) as ApiError;
  } catch {
    return {};
  }
}
