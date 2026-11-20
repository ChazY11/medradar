import { ApiError } from "./client";

/** The radar API answers failures with a FastAPI {detail: {code, message}} envelope. */
async function fetchJson<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(path, {
      ...init,
      headers: { Accept: "application/json", "Content-Type": "application/json", ...(init?.headers || {}) },
    });
  } catch (error) {
    throw new ApiError(0, "network_error", error instanceof Error ? error.message : "Network request failed.");
  }
  if (!response.ok) {
    let code = "http_" + response.status;
    let message = "Request failed with status " + response.status + ".";
    try {
      const payload: unknown = await response.json();
      const detail = (payload as { detail?: unknown }).detail;
      if (typeof detail === "object" && detail !== null) {
        const candidate = detail as { code?: unknown; message?: unknown };
        if (typeof candidate.code === "string") code = candidate.code;
        if (typeof candidate.message === "string") message = candidate.message;
      } else if (typeof detail === "string") {
        message = detail;
      }
    } catch {
      /* keep the status-based message */
    }
    throw new ApiError(response.status, code, message);
  }
  return (await response.json()) as T;
}

export type ReviewState = "NEW" | "REVIEWING" | "CONFIRMED" | "DISMISSED";

export interface Watchlist {
  id: string;
  name: string;
  filter: Record<string, unknown>;
  created_at: string;
  updated_at: string;
  count?: number | null;
}

export interface ReviewDecision {
  observation_id: string;
  status: ReviewState;
  assignee: string | null;
  note: string | null;
  updated_at: string;
}

export interface ReviewEvent {
  seq: number;
  action: string;
  from_status: string | null;
  to_status: string | null;
  assignee: string | null;
  note: string | null;
  actor: string;
  at: string;
}

export interface CompanyRow {
  organization_id: string;
  display_name: string;
  canonical_name: string | null;
  label_zh: string | null;
  country: string | null;
  observations: number;
  recalls: number;
  newest_observation_at: string | null;
}

export interface CompanyRecord {
  observation_id: string;
  source: string;
  record_type?: string | null;
  title: string | null;
  source_url: string | null;
  published_at: string | null;
  event_at?: string | null;
  first_observed_at?: string | null;
  official_identifier?: string | null;
  decision?: string | null;
  tier?: string | null;
  score?: number | null;
}

export interface CompanyProfile {
  organization_id: string;
  display_name: string;
  canonical_name: string | null;
  label_zh: string | null;
  country: string | null;
  notes: string | null;
  known_in_taxonomy: boolean;
}

export interface CompanyResponse {
  available: boolean;
  company: CompanyProfile;
  totals: { observations: number; by_source: Record<string, number>; recalls: number };
  recent: CompanyRecord[];
  recalls: CompanyRecord[];
  topics: { topic_id: string; n: number }[];
  products: { product_key: string; n: number }[];
}

export interface QueueItem extends ReviewDecision {
  source?: string;
  title?: string | null;
  source_url?: string | null;
  first_observed_at?: string | null;
  published_at?: string | null;
}

export interface AuditRow {
  seq: number;
  at: string;
  actor: string;
  action: string;
  target: string | null;
  detail: string | null;
}

export const getWatchlists = (counts = true) =>
  fetchJson<{ count: number; items: Watchlist[] }>(
    "/api/radar/watchlists" + (counts ? "?counts=1" : ""));

export const createWatchlist = (name: string, filter: Record<string, unknown>) =>
  fetchJson<{ watchlist: Watchlist }>("/api/radar/watchlists", {
    method: "POST",
    body: JSON.stringify({ name, filter }),
  });

export const deleteWatchlist = (id: string) =>
  fetchJson<{ deleted: string }>("/api/radar/watchlists/" + id, { method: "DELETE" });

export const getReview = (observationId: string) =>
  fetchJson<{ review: ReviewDecision | null; history: ReviewEvent[] }>(
    "/api/radar/review/" + observationId);

export const setReview = (observationId: string, body: { status?: string; assignee?: string; note?: string }) =>
  fetchJson<{ review: ReviewDecision; history: ReviewEvent[] }>(
    "/api/radar/review/" + observationId, { method: "POST", body: JSON.stringify(body) });

export const getReviewQueue = (status?: string) =>
  fetchJson<{ count: number; items: QueueItem[]; stats: { reviews: number; by_status: Record<string, number> } }>(
    "/api/radar/review/queue" + (status ? "?status=" + encodeURIComponent(status) : ""));

export const getAudit = (limit = 100) =>
  fetchJson<{ items: AuditRow[] }>("/api/radar/audit?limit=" + limit);

export const getCompanies = () =>
  fetchJson<{ available: boolean; count: number; items: CompanyRow[] }>("/api/radar/companies");

export const getCompany = (id: string) =>
  fetchJson<CompanyResponse>("/api/radar/company/" + encodeURIComponent(id));

export const exportUrl = (params: Record<string, string | number | undefined>) => {
  const search = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== "") search.set(key, String(value));
  });
  return "/api/radar/export?" + search.toString();
};