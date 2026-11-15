/**
 * Client for the internal identity-review service.
 *
 * The review service is a separate, loopback-bound process. The token is pasted once by the
 * operator and kept in sessionStorage: it is never in the bundle, never in localStorage and never
 * in a cookie, so a cross-site request has no way to carry it.
 */
const TOKEN_KEY = "medradar.review.token";

export function getReviewToken(): string | null {
  try {
    return window.sessionStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

export function setReviewToken(token: string | null): void {
  try {
    if (token) window.sessionStorage.setItem(TOKEN_KEY, token);
    else window.sessionStorage.removeItem(TOKEN_KEY);
  } catch {
    /* sessionStorage can be unavailable in private mode; the workspace then stays locked */
  }
}

export class ReviewApiError extends Error {
  status: number;
  code: string;
  constructor(status: number, code: string, message: string) {
    super(message);
    this.name = "ReviewApiError";
    this.status = status;
    this.code = code;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const token = getReviewToken();
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (token) headers["X-MedRadar-Review-Token"] = token;
  const response = await fetch(path, { ...init, headers: { ...headers, ...(init?.headers ?? {}) } });
  let payload: unknown = null;
  try {
    payload = await response.json();
  } catch {
    payload = null;
  }
  if (!response.ok) {
    const envelope = payload as { error?: { code?: string; message?: string; hint?: string } } | null;
    const code = envelope?.error?.code ?? "http_" + response.status;
    const message = envelope?.error?.message ?? "Request failed with status " + response.status;
    const hint = envelope?.error?.hint;
    throw new ReviewApiError(response.status, code, hint ? message + " " + hint : message);
  }
  return payload as T;
}

export interface ReviewRiskFlag {
  code: string;
  meaning: string;
}

export interface ReviewQueueItem {
  applicant_name: string;
  record_count: number;
  status: string;
  organization_key: string | null;
  basis: string | null;
  rule: string | null;
  reviewer: string | null;
  reviewer_kind: string | null;
  decision_uid: string | null;
  collection_scope: string[];
  sources: string[];
  risk_flags: ReviewRiskFlag[];
}

export interface ReviewQueueResponse {
  items: ReviewQueueItem[];
  page: number;
  page_size: number;
  total: number;
  total_pages: number;
  total_records_affected: number;
  sort: string;
  definitions: Record<string, string>;
}

export interface ReviewEvidence {
  evidence_type: string;
  url?: string | null;
  title?: string | null;
  accessed_at?: string | null;
  source_id?: string | null;
  quote?: string | null;
  note?: string | null;
}

export interface ReviewDecisionRecord {
  decision_uid: string;
  applicant_name: string;
  applicant_key: string;
  organization_key: string | null;
  prior_organization_key: string | null;
  action: string;
  status: string;
  basis: string | null;
  evidence_type: string | null;
  evidence: ReviewEvidence[];
  note: string | null;
  reviewer: string;
  reviewer_kind: string;
  authority_kind?: string;
  authority_method?: string | null;
  attestation?: string | null;
  status_recorded?: string;
  status_downgraded?: boolean;
  status_downgraded_reason?: string | null;
  created_at: string;
  supersedes_uid: string | null;
  revoked: boolean;
}

export interface ReviewSampleRecord {
  event_id: string;
  official_id: string;
  event_type: string;
  event_date: string | null;
  device_name: string | null;
  product_code: string | null;
  organization_key: string | null;
  verification: string;
  official_url: string;
}

export interface ReviewCandidateOrganization {
  organization_key: string;
  display_name: string;
  matched_tokens: string[];
  records: number;
  in_collection_scope: boolean;
}

export interface ReviewCase {
  applicant_name: string;
  applicant_key: string;
  record_count: number;
  by_source: Record<string, number>;
  collection_scope: string[];
  current: {
    status: string;
    organization_key: string | null;
    organization_display: string | null;
    basis: string | null;
    rule: string | null;
    rule_detail: string | null;
    provenance: string | null;
    verified: boolean;
    evidence: ReviewEvidence[];
    reviewer: string | null;
    reviewer_kind: string | null;
    decision_uid: string | null;
    rejection_reason: string | null;
  };
  risk_flags: ReviewRiskFlag[];
  candidate_organizations: ReviewCandidateOrganization[];
  ownership_relations: {
    relation_id: string;
    entity: string;
    relation_type: string;
    status: string;
    effective_from: string | null;
    historical_owner_before: string | null;
    evidence: ReviewEvidence[];
  }[];
  sample_records: ReviewSampleRecord[];
  history: ReviewDecisionRecord[];
}

export interface ReviewSummary {
  queue_strings: number;
  awaiting_review_strings: number;
  awaiting_review_records: number;
  by_status_strings: Record<string, number>;
  by_status_records: Record<string, number>;
  ledger: {
    decision_count: number;
    revoked_count: number;
    effective_count: number;
    human_reviewed_count: number;
    agent_recorded_count: number;
    db_path: string;
  };
}

export interface ReviewImpact {
  changed_organizations: {
    organization_key: string;
    records_before: number;
    records_after: number;
    records_delta: number;
    verified_before: number;
    verified_after: number;
  }[];
  unchanged_organizations: number;
  statement: string;
  applied_decisions: number;
}

export async function reviewPing() {
  return request<{
    ok: boolean;
    version: string;
    review_db: string;
    decisions_applied: number;
    boundary: string;
    reviewer_header: string;
  }>("/api/review/ping");
}

export async function reviewQueue(params: {
  status?: string;
  org?: string;
  risk?: string;
  q?: string;
  sort?: string;
  page?: number;
  pageSize?: number;
  includeVerified?: boolean;
}): Promise<ReviewQueueResponse> {
  const search = new URLSearchParams();
  if (params.status) search.set("status", params.status);
  if (params.org) search.set("org", params.org);
  if (params.risk) search.set("risk", params.risk);
  if (params.q) search.set("q", params.q);
  if (params.sort) search.set("sort", params.sort);
  if (params.page) search.set("page", String(params.page));
  if (params.pageSize) search.set("page_size", String(params.pageSize));
  if (params.includeVerified) search.set("include_verified", "true");
  return request<ReviewQueueResponse>("/api/review/queue?" + search.toString());
}

export async function reviewCase(applicantName: string): Promise<ReviewCase> {
  return request<ReviewCase>("/api/review/case/" + encodeURIComponent(applicantName));
}

export async function reviewSummary(): Promise<ReviewSummary> {
  return request<ReviewSummary>("/api/review/summary");
}

export async function reviewImpact(): Promise<ReviewImpact> {
  return request<ReviewImpact>("/api/review/impact");
}

export interface ReviewCapabilities {
  human_review_authority_available: boolean;
  human_review_reason: string;
  writable_statuses: string[];
  authority_kinds: string[];
  actor_kind_policy: string;
  evidence_status_note: string;
}

export async function reviewCapabilities(): Promise<ReviewCapabilities> {
  return request<ReviewCapabilities>("/api/review/capabilities");
}

/**
 * The actor kind is NOT part of this payload: the service derives it on the server. Sending a
 * reviewer_kind field is rejected with 400 by design, so the type does not allow it.
 */
export async function reviewDecide(body: {
  applicant_name: string;
  action: string;
  status: string;
  organization_key?: string | null;
  basis?: string | null;
  evidence_type?: string | null;
  evidence?: ReviewEvidence[];
  note?: string | null;
  reviewer: string;
}): Promise<{ ok: boolean; decision: ReviewDecisionRecord }> {
  return request<{ ok: boolean; decision: ReviewDecisionRecord }>("/api/review/decisions", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function reviewRevoke(decisionUid: string, body: { reviewer: string; note?: string }) {
  return request<{ ok: boolean; revocation: ReviewDecisionRecord }>(
    "/api/review/decisions/" + encodeURIComponent(decisionUid) + "/revoke",
    { method: "POST", body: JSON.stringify(body) },
  );
}

export function reviewExportUrl(): string {
  return "/api/review/export";
}
