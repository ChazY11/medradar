import type {
  AttributionResponse,
  Brief,
  ChangesResponse,
  DataStatusResponse,
  ExplainResponse,
  MetricsResponse,
  OwnershipResponse,
  CompareResponse,
  CoverageResponse,
  EventDetailResponse,
  EventsResponse,
  HealthResponse,
  MetaResponse,
  OrganizationProfile,
  OrganizationsResponse,
  SearchResponse,
} from "./types";

const BASE = "";
const REQUEST_TIMEOUT_MS = 10_000;

export class ApiError extends Error {
  status: number;
  code: string;

  constructor(status: number, code: string, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
  }
}

interface ErrorEnvelope {
  error: {
    code: string;
    message: string;
    hint?: string;
  };
}

function isErrorEnvelope(value: unknown): value is ErrorEnvelope {
  if (typeof value !== "object" || value === null) return false;
  const error = (value as { error?: unknown }).error;
  if (typeof error !== "object" || error === null) return false;
  const candidate = error as { code?: unknown; message?: unknown };
  return typeof candidate.code === "string" && typeof candidate.message === "string";
}

async function readError(response: Response): Promise<{ code: string; message: string }> {
  try {
    const payload: unknown = await response.json();
    if (isErrorEnvelope(payload)) {
      return { code: payload.error.code, message: payload.error.message };
    }
  } catch {
    // The body was empty or not JSON; fall back to the HTTP status.
  }
  return {
    code: `http_${response.status}`,
    message: `Request failed with status ${response.status}.`,
  };
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);

  let response: Response;
  try {
    response = await fetch(`${BASE}${path}`, { ...init, signal: controller.signal });
  } catch (error) {
    if (controller.signal.aborted) {
      throw new ApiError(0, "timeout", `Request timed out after ${REQUEST_TIMEOUT_MS} ms.`);
    }
    throw new ApiError(
      0,
      "network_error",
      error instanceof Error ? error.message : "Network request failed.",
    );
  } finally {
    clearTimeout(timeoutId);
  }

  if (!response.ok) {
    const { code, message } = await readError(response);
    throw new ApiError(response.status, code, message);
  }

  try {
    return (await response.json()) as T;
  } catch {
    throw new ApiError(
      response.status,
      "invalid_json",
      "The server returned a response that is not valid JSON.",
    );
  }
}

export interface EventsQuery {
  org?: string[];
  types?: string[];
  from?: string;
  to?: string;
  category?: string[];
  product_code?: string;
  q?: string;
  review?: string;
  basis?: string;
  sort?: string;
  page?: number;
  page_size?: number;
}

export interface BriefQuery {
  mode: "company" | "compare" | "device";
  org?: string;
  orgs?: string[];
  device?: string;
  years?: number;
  from?: string;
  to?: string;
  types?: string[];
  basis?: string;
  review?: string;
}

export interface CompareQuery {
  from?: string;
  to?: string;
  types?: string[];
  basis?: string;
  review?: string;
}

export function buildQuery(
  params: Record<string, string | number | string[] | undefined>,
): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined) continue;
    if (Array.isArray(value)) {
      const values = value.filter((item) => item.length > 0);
      if (values.length === 0) continue;
      search.set(key, values.join(","));
      continue;
    }
    if (typeof value === "string") {
      if (value.length === 0) continue;
      search.set(key, value);
      continue;
    }
    search.set(key, String(value));
  }
  const query = search.toString();
  return query ? `?${query}` : "";
}

function eventsQueryParams(
  params: EventsQuery,
): Record<string, string | number | string[] | undefined> {
  return {
    org: params.org,
    types: params.types,
    from: params.from,
    to: params.to,
    category: params.category,
    product_code: params.product_code,
    q: params.q,
    review: params.review,
    basis: params.basis,
    sort: params.sort,
    page: params.page,
    page_size: params.page_size,
  };
}

export async function getHealth(): Promise<HealthResponse> {
  return request<HealthResponse>("/api/health");
}

export async function getMeta(): Promise<MetaResponse> {
  return request<MetaResponse>("/api/meta");
}

export async function searchOrganizations(q: string, limit = 8): Promise<SearchResponse> {
  return request<SearchResponse>(`/api/search${buildQuery({ q, limit })}`);
}

export async function listOrganizations(): Promise<OrganizationsResponse> {
  return request<OrganizationsResponse>("/api/organizations");
}

export async function getOrganization(key: string): Promise<OrganizationProfile> {
  return request<OrganizationProfile>(`/api/organizations/${encodeURIComponent(key)}`);
}

export async function listOrganizationEvents(
  key: string,
  params: EventsQuery,
): Promise<EventsResponse> {
  return request<EventsResponse>(
    `/api/organizations/${encodeURIComponent(key)}/events${buildQuery(eventsQueryParams(params))}`,
  );
}

export async function listEvents(params: EventsQuery): Promise<EventsResponse> {
  return request<EventsResponse>(`/api/events${buildQuery(eventsQueryParams(params))}`);
}

export async function getEvent(eventId: string): Promise<EventDetailResponse> {
  return request<EventDetailResponse>(`/api/events/${encodeURIComponent(eventId)}`);
}

export async function getCompare(
  orgs: string[],
  params: CompareQuery,
): Promise<CompareResponse> {
  return request<CompareResponse>(
    `/api/compare${buildQuery({
      orgs: orgs.join(","),
      from: params.from,
      to: params.to,
      types: params.types,
      basis: params.basis,
      review: params.review,
    })}`,
  );
}

export async function getMetrics(): Promise<MetricsResponse> {
  return request<MetricsResponse>("/api/metrics");
}

export async function getOwnership(): Promise<OwnershipResponse> {
  return request<OwnershipResponse>("/api/ownership");
}

export async function getCoverage(): Promise<CoverageResponse> {
  return request<CoverageResponse>("/api/coverage");
}

export async function getAttribution(): Promise<AttributionResponse> {
  return request<AttributionResponse>("/api/attribution");
}

export function exportEventsCsvUrl(params: EventsQuery): string {
  return `/api/export/events.csv${buildQuery(eventsQueryParams(params))}`;
}

export function exportCompareMdUrl(orgs: string[], params: CompareQuery): string {
  return `/api/export/compare.md${buildQuery({
    orgs: orgs.join(","),
    from: params.from,
    to: params.to,
    types: params.types,
  })}`;
}

export function exportOrganizationMdUrl(key: string): string {
  return `/api/export/organization.md${buildQuery({ key })}`;
}

export async function getDataStatus(): Promise<DataStatusResponse> {
  return request<DataStatusResponse>("/api/data-status");
}

export async function getChanges(params: {
  source?: string;
  type?: string;
  org?: string;
  limit?: number;
  offset?: number;
}): Promise<ChangesResponse> {
  return request<ChangesResponse>(`/api/changes${buildQuery(params)}`);
}

/* ------------------------------------------------------------------ PRODUCT-004 intelligence brief */

export function briefQueryParams(
  params: BriefQuery,
): Record<string, string | number | string[] | undefined> {
  return {
    mode: params.mode,
    org: params.org,
    orgs: params.orgs && params.orgs.length ? params.orgs : undefined,
    device: params.device,
    years: params.years,
    from: params.from,
    to: params.to,
    types: params.types && params.types.length ? params.types : undefined,
    basis: params.basis,
    review: params.review,
  };
}

export async function getBrief(params: BriefQuery): Promise<Brief> {
  return request<Brief>(`/api/brief${buildQuery(briefQueryParams(params))}`);
}

export function briefMdUrl(params: BriefQuery, lang: "en" | "zh"): string {
  return `/api/export/brief.md${buildQuery({ ...briefQueryParams(params), lang })}`;
}

export function briefEvidenceUrl(params: BriefQuery): string {
  return `/api/export/brief-evidence.csv${buildQuery(briefQueryParams(params))}`;
}

export interface ExplainQuery {
  metric: string;
  orgs: string[];
  years?: number;
  from?: string;
  to?: string;
  types?: string[];
  basis?: string;
  review?: string;
}

export function explainUrl(params: ExplainQuery): string {
  return `/api/brief/explain${buildQuery({
    metric: params.metric,
    orgs: params.orgs,
    years: params.years,
    from: params.from,
    to: params.to,
    types: params.types,
    basis: params.basis,
    review: params.review,
  })}`;
}

export async function getExplain(params: ExplainQuery): Promise<ExplainResponse> {
  return request<ExplainResponse>(explainUrl(params));
}
