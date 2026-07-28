export interface WatchlistItem {
  symbol: string;
  name: string;
  market: string;
  themes: string[];
  thesis: string;
  risks: string;
  industry: string;
}

export interface StockSearchItem {
  symbol: string;
  name: string;
  market: string;
  industry: string;
  themes: string[];
}

export async function loadWatchlist(): Promise<WatchlistItem[]> {
  const response = await fetch("/api/watchlist", { cache: "no-store" });
  return readItems<WatchlistItem>(response);
}

export async function searchStocks(query: string): Promise<StockSearchItem[]> {
  const response = await fetch(`/api/stocks/search?q=${encodeURIComponent(query)}`, { cache: "no-store" });
  return readItems<StockSearchItem>(response);
}

export async function addWatchlistItem(symbol: string): Promise<WatchlistItem> {
  return requestItem("/api/watchlist", { method: "POST", body: JSON.stringify({ symbol }) });
}

export async function removeWatchlistItem(symbol: string): Promise<WatchlistItem> {
  return requestItem(`/api/watchlist/${encodeURIComponent(symbol)}`, { method: "DELETE" });
}

async function readItems<T>(response: Response): Promise<T[]> {
  if (!response.ok) throw new Error(await errorMessage(response));
  const payload = await response.json() as { items: T[] };
  return payload.items;
}

async function requestItem(url: string, init: RequestInit): Promise<WatchlistItem> {
  const response = await fetch(url, {
    ...init,
    headers: { "Content-Type": "application/json", Accept: "application/json" },
  });
  if (!response.ok) throw new Error(await errorMessage(response));
  return response.json() as Promise<WatchlistItem>;
}

async function errorMessage(response: Response): Promise<string> {
  try {
    const payload = await response.json() as { message?: string };
    return payload.message || `请求失败（HTTP ${response.status}）`;
  } catch {
    return `请求失败（HTTP ${response.status}）`;
  }
}
