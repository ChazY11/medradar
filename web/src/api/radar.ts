/**
 * RADAR-001 client: the Live Intelligence feed and the Company Technology Graph.
 *
 * Separate from `client.ts` because the radar API mounts a different error envelope
 * (`{detail: {code, message}}` from FastAPI's HTTPException) and because every call is a
 * *read* of a different store (the radar ledger and the bitemporal graph), not the FDA
 * snapshot.
 */

import { ApiError } from "./client";

const BASE = "";

export interface RadarMeta {
  schema: string;
  available: boolean;
  graph_available: boolean;
  paths: Record<string, string>;
  taxonomy: { version: string; fingerprint: string; topics: number; organizations: number };
  sources: {
    source_id: string;
    display_name: string;
    kind: string;
    enabled: boolean;
    access: string;
    cadence_hours: number;
    licence: string | null;
  }[];
}

export interface DetectionLatency {
  exact_samples: number;
  approximate_samples: number;
  exact_median_hours: number | null;
  exact_p90_hours: number | null;
  exact_min_hours: number | null;
  exact_max_hours: number | null;
  approximate_median_hours: number | null;
  note: string;
  cannot_do: string;
}

export interface RadarSource {
  source_id: string;
  label: string;
  enabled: boolean;
  access_state: "ENABLED" | "BLOCKED" | "UNVERIFIED";
  access_reason: string | null;
  status: string;
  cadence_hours: number;
  declared_cadence_basis: string | null;
  licence: { name?: string; url?: string; redistribution?: string } | null;
  last_checked_at: string | null;
  last_success_check_at: string | null;
  last_observed_update_at: string | null;
  watermark: string | null;
  consecutive_failures: number;
  last_failure_message: string | null;
  next_due_at: string | null;
  due: boolean;
  observations_total: number;
  backlog: number;
  detection_latency: DetectionLatency;
  discovery_phases: { initial: number; incremental: number; backfill: number };
  adapter_version: string;
}

export interface RadarHealth {
  schema: string;
  available: boolean;
  state: string;
  message?: string;
  counts?: Record<string, number>;
  sources: RadarSource[];
  blocked_sources?: string[];
  degraded_sources?: string[];
  never_checked_sources?: string[];
  backlog?: { by_state: Record<string, number>; backlog: number; running: number; total: number };
  resources?: Record<string, number | string | null>;
  ai?: Record<string, unknown>;
  last_cycle?: Record<string, unknown>;
  consistency?: { ok: boolean; problems: { kind: string; count: number }[]; counts: Record<string, number> };
  change_counts?: Record<string, number>;
  blocked_explanation?: string;
  graph?: {
    nodes: number;
    edges: number;
    edges_by_type: Record<string, number>;
    confirmations: Record<string, number>;
    graph_version: string;
    taxonomy_version: string;
  };
  terminology?: { statement?: string };
}

export type Confirmation = "CONFIRMED" | "CANDIDATE" | "TOPIC_RELATED" | "UNKNOWN";

export interface IntelEvent {
  observation_id: string;
  source: string;
  official_identifier: string | null;
  title: string;
  source_url: string | null;
  record_type: string;
  event_date: string | null;
  event_date_precision: string;
  source_published_at: string | null;
  source_published_at_precision: string;
  first_observed_at: string;
  last_checked_at: string | null;
  source_updated_at: string | null;
  content_hash: string;
  version: number;
  change_state: string;
  observation_status: string;
  discovery_phase: "INITIAL_DISCOVERY" | "INCREMENTAL_DISCOVERY" | "HISTORICAL_BACKFILL";
  processing_state: string;
  organization_candidates: {
    organization_id: string;
    display_name: string;
    label_zh: string | null;
    confirmation: Confirmation;
    method: string;
    confidence: number | null;
  }[];
  product_candidates: { product_key: string; confirmation: Confirmation; method: string }[];
  technology_topics: {
    topic_id: string;
    label_en: string;
    label_zh: string | null;
    family: string | null;
    confirmation: Confirmation;
    method: string;
  }[];
  site_domain: string | null;
  latest_version_changed_fields: string[];
  evidence_references: EvidenceRef[];
}

export interface EvidenceRef {
  evidence_id: string;
  observation_id: string;
  content_hash: string;
  source: string;
  url: string | null;
  captured_at?: string;
  change_state?: string;
}

export interface FeedResponse {
  schema: string;
  total: number;
  count: number;
  page: number;
  page_size: number;
  new_since: number;
  since: string | null;
  items: IntelEvent[];
  labels: { change_states: string[]; phases: Record<string, string> };
  note: string;
}

export interface FeedFacets {
  organizations: {
    organization_id: string;
    display_name: string;
    label_zh: string | null;
    confirmation: Confirmation;
    n: number;
  }[];
  topics: {
    topic_id: string;
    label_en: string;
    label_zh: string | null;
    confirmation: Confirmation;
    n: number;
  }[];
  sources: { source: string; n: number; newest: string | null }[];
}

export interface IntelDetail extends IntelEvent {
  versions: {
    version_id: string;
    version_seq: number;
    captured_at: string;
    change_state: string;
    content_hash: string;
    changed_fields: string[];
    adapter_version: string;
    run_id: string | null;
    payload_keys: string[];
  }[];
  changes: {
    change_state: string;
    observed_at: string;
    changed_fields: string[];
    run_id: string | null;
  }[];
  ai_candidates: {
    model_id: string;
    model_version: string;
    prompt_version: string;
    created_at: string;
    validation_state: string;
    validation: Record<string, unknown>;
  }[];
}

export interface TimeSemantics {
  recorded_at: string;
  valid_from: string;
  mode: string;
  statement: string;
  cannot_do: string;
}

export interface GraphCapability {
  confirmation: Confirmation;
  basis: string | null;
  evidence_id: string | null;
  source: string | null;
  valid_from: string;
  recorded_at: string;
}

export interface GraphProduct {
  product_id: string;
  name: string | null;
  confirmation: Confirmation;
  edge_type: string;
  evidence_id: string | null;
  source: string | null;
  source_url: string | null;
  valid_from: string;
  first_recorded_at: string;
  capabilities: GraphCapability[];
}

export interface GraphEvidenceRow {
  record_node: string;
  record_type: string;
  confirmation: Confirmation;
  method: string | null;
  matched_terms: string[];
  evidence_id: string | null;
  source: string | null;
  source_url: string | null;
  title: string | null;
  valid_from: string;
  public_time: string | null;
  recorded_at: string;
}

export interface TechnologyBranch {
  topic_id: string;
  family: string | null;
  label_en: string;
  label_zh: string | null;
  description: string | null;
  companies: {
    organization_id: string;
    display_name: string;
    label_zh: string | null;
    products: GraphProduct[];
    evidence: GraphEvidenceRow[];
    earliest_evidence: string | null;
    latest_change: string | null;
  }[];
}

export interface TechnologyMap {
  schema: string;
  known_at: string;
  valid_at: string | null;
  mode: "public_time_reconstruction" | "knowledge_time";
  reconstructed: boolean;
  requested_mode: string;
  companies: string[];
  topics: TechnologyBranch[];
  counts: { topics_with_evidence: number; nodes: number; edges: number };
  time_semantics: TimeSemantics;
  available_topics: { id: string; family: string; label_en: string; label_zh: string }[];
}

export interface CompareCell {
  organization_id: string;
  display_name: string;
  label_zh: string | null;
  state: "EVIDENCE_PRESENT" | "NO_EVIDENCE_FOUND" | "NOT_MONITORED" | "SOURCE_UNAVAILABLE";
  reported_capability_evidence: number;
  regulatory_topic_evidence: number;
  publication_topic_evidence: number;
  official_document_topic_evidence: number;
  evidence_ids: string[];
  statement: string;
}

export interface CompareResponse {
  schema: string;
  known_at: string;
  valid_at: string | null;
  mode: "public_time_reconstruction" | "knowledge_time";
  reconstructed: boolean;
  requested_mode: string;
  rows: {
    topic_id: string;
    label_en: string;
    label_zh: string | null;
    family: string | null;
    cells: CompareCell[];
  }[];
  not_comparable_warning: string;
  no_evidence_means: string;
  time_semantics: TimeSemantics;
  organizations: { id: string; display_name: string; label_zh: string; canonical_name: string }[];
}

export interface EdgeView {
  edge_type: string;
  src: { node_type: string; node_id: string };
  dst: { node_type: string; node_id: string };
  confirmation: Confirmation;
  method: string | null;
  evidence_id: string | null;
  observation_id: string | null;
  source: string | null;
  source_url: string | null;
  matched_terms: string[] | null;
  valid_from: string;
  public_time: string | null;
  recorded_at: string;
  rule_version: string | null;
  confidence: number | null;
}

export interface GraphChanges {
  schema: string;
  earlier: string;
  later: string;
  added: EdgeView[];
  removed: EdgeView[];
  changed: EdgeView[];
  counts: { added: number; removed: number; changed: number };
  note: string;
}

export interface GraphNodeDetail {
  schema: string;
  node_type: string;
  node_id: string;
  node: { attrs?: Record<string, unknown>; valid_from?: string; recorded_at?: string } | null;
  known_at: string;
  valid_at: string | null;
  mode: string;
  reconstructed: boolean;
  earliest_evidence: string | null;
  latest_change: string | null;
  incoming: EdgeView[];
  outgoing: EdgeView[];
  time_semantics: TimeSemantics;
  requested_mode?: string;
}

export interface Notices {
  schema: string;
  since: string | null;
  new_count: number;
  items: {
    observation_id: string;
    source: string;
    change_state: string;
    observed_at: string;
    first_observed_at: string;
    title: string;
    url: string | null;
    record_type: string;
    discovery_phase: string;
  }[];
  note: string;
}

async function fetchJson<T>(path: string): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${BASE}${path}`, { headers: { Accept: "application/json" } });
  } catch (error) {
    throw new ApiError(0, "network_error", error instanceof Error ? error.message : "Network request failed.");
  }
  if (!response.ok) {
    let code = `http_${response.status}`;
    let message = `Request failed with status ${response.status}.`;
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
      const error = (payload as { error?: { code?: string; message?: string } }).error;
      if (error?.code) code = error.code;
      if (error?.message) message = error.message;
    } catch {
      // Non-JSON error body: keep the status-derived message.
    }
    throw new ApiError(response.status, code, message);
  }
  try {
    return (await response.json()) as T;
  } catch {
    throw new ApiError(response.status, "invalid_json", "The server returned a response that is not valid JSON.");
  }
}

function query(params: Record<string, string | number | undefined | null>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null || value === "") continue;
    search.set(key, String(value));
  }
  const text = search.toString();
  return text ? `?${text}` : "";
}

export interface FeedQuery {
  limit?: number;
  offset?: number;
  source?: string;
  organization?: string;
  topic?: string;
  change_state?: string;
  confirmation?: string;
  record_type?: string;
  phase?: string;
  published_from?: string;
  published_to?: string;
  observed_from?: string;
  observed_to?: string;
  q?: string;
  order?: "observed" | "published" | "event";
  since?: string;
}

export const getRadarMeta = () => fetchJson<RadarMeta>("/api/radar/meta");
export const getRadarHealth = () => fetchJson<RadarHealth>("/api/radar/health");
export const getRadarSources = () => fetchJson<{ available: boolean; sources: RadarSource[] }>("/api/radar/sources");
export const getFeed = (params: FeedQuery) => fetchJson<FeedResponse>(`/api/radar/feed${query({ ...params })}`);
export const getFeedFacets = () => fetchJson<FeedFacets>("/api/radar/feed/facets");
export const getIntelligence = (observationId: string) =>
  fetchJson<IntelDetail>(`/api/radar/intelligence/${encodeURIComponent(observationId)}`);
export const getNotices = (since: string | null) =>
  fetchJson<Notices>(`/api/radar/notices${query({ since: since ?? undefined, limit: 8 })}`);

export interface TimeQuery {
  mode: "public" | "knowledge";
  at?: string;
}
export const getTechnologyMap = (params: TimeQuery & { companies?: string; topics?: string }) =>
  fetchJson<TechnologyMap>(`/api/radar/technology-map${query({ ...params })}`);
export const getCompare = (params: TimeQuery & { companies?: string }) =>
  fetchJson<CompareResponse>(`/api/radar/compare${query({ ...params })}`);
export const getGraphChanges = (earlier: string, later?: string) =>
  fetchJson<GraphChanges>(`/api/radar/graph/changes${query({ earlier, later })}`);
export const getGraphNode = (
  nodeType: string,
  nodeId: string,
  params: TimeQuery,
) =>
  fetchJson<GraphNodeDetail>(
    `/api/radar/graph/node${query({ node_type: nodeType, node_id: nodeId, ...params })}`,
  );

export const GRAPH_NODE_TYPES = {
  company: "company",
  topic: "technology_topic",
  product: "product",
  record: "regulatory_record",
} as const;
