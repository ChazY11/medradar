// Types transcribed from docs/product/API_CONTRACT.md (v1, PRODUCT-001).
// Do not add fields that are not declared in the contract.

export type EventType = "510k" | "pma" | "pma_supplement" | "recall";
export type SourceId = "openfda_510k" | "openfda_pma" | "openfda_recall";

export interface EventWindow {
  from: string | null;
  to: string | null;
}

export interface SnapshotRef {
  id: string;
  collected_at: string;
  openfda_last_updated: string | null;
  file_sha256: Record<string, string>;
  note: string;
}

export interface Freshness {
  state: "fresh" | "stale" | "unknown";
  age_days: number | null;
  threshold_days: number;
  collected_at: string | null;
}

export interface Basis {
  event_types: EventType[];
  window: EventWindow;
  org_keys: string[];
  snapshot_id: string;
  rule: string;
}

export interface SourceCount {
  source_id: SourceId;
  count: number;
}

export interface TypeCount {
  event_type: EventType;
  count: number;
}

export interface Counts {
  records: number;
  dated: number;
  undated: number;
  unmapped_category: number;
  pending_review: number;
  by_source: SourceCount[];
  by_type: TypeCount[];
}

export interface Category {
  id: string;
  label: string;
}

export interface EventAttribution {
  status: "attributed" | "unattributed" | "rejected";
  basis: "legal_name" | "brand" | "subsidiary" | "historical_name" | "division" | null;
  review: "curated" | "pending_review" | "rejected" | null;
}

export interface EventRecord {
  event_id: string;
  official_id: string;
  source_id: SourceId;
  source_name: string;
  event_type: EventType;
  event_date: string | null;
  published_at: string | null;
  published_at_status: "from_source" | "not_published_by_source";
  first_observed_at: string;
  available_at: string;
  record_updated_at: string | null;
  time_quality: "date_from_source" | "date_derived_from_source" | "unknown";
  organization_key: string | null;
  organization_name: string | null;
  applicant_name: string;
  attribution: EventAttribution;
  product_code: string | null;
  category: Category | null;
  device_class: "1" | "2" | "3" | null;
  device_name: string | null;
  title: string;
  summary: string | null;
  official_url: string;
  /** Verbatim source fields. Only present on the event detail response. */
  fields?: Record<string, string | null>;
}

export interface YearCount {
  year: string;
  counts: Record<EventType, number>;
  total: number;
}

export interface CategoryBreakdown {
  id: string;
  label: string;
  counts: Record<EventType, number>;
  total: number;
}

export interface ClassCount {
  device_class: "1" | "2" | "3" | "unknown";
  count: number;
}

export interface Aggregations {
  by_year: YearCount[];
  by_type: TypeCount[];
  by_category: CategoryBreakdown[];
  by_class: ClassCount[];
  undated_records: number;
}

export interface HealthResponse {
  status: "ok" | "degraded";
  snapshot: SnapshotRef | null;
  version: string;
  store: string;
}

export interface MetaProduct {
  name: "MedRadar";
  version: string;
  positioning_en: string;
  positioning_zh: string;
}

export interface MetaSource {
  source_id: SourceId;
  name: string;
  official_base_url: string;
  licence: string;
  collected: boolean;
  note: string;
}

export interface OutOfScopeItem {
  item: string;
  reason: string;
}

export interface EventTypeInfo {
  event_type: EventType;
  label: string;
  note: string;
}

export interface MetaCoverage {
  tracked_organizations: number;
  total_records: number;
  attributed_records: number;
  unattributed_records: number;
  earliest_event_date: string | null;
  latest_event_date: string | null;
}

export interface TimeSemantic {
  field: string;
  meaning: string;
}

export interface MetaResponse {
  product: MetaProduct;
  snapshot: SnapshotRef;
  freshness: Freshness;
  sources: MetaSource[];
  out_of_scope: OutOfScopeItem[];
  event_types: EventTypeInfo[];
  categories: Category[];
  coverage: MetaCoverage;
  time_semantics: TimeSemantic[];
  limitations: string[];
  methodology_url: string;
}

export interface SearchMatch {
  field: "legal_name" | "brand" | "ticker" | "alias" | "applicant" | "substring";
  value: string;
}

export interface SearchResult {
  key: string;
  display_name: string;
  legal_name: string | null;
  ticker: string | null;
  country: string | null;
  organization_type: string;
  event_count: number;
  event_range: EventWindow;
  match: SearchMatch;
  ambiguous_name: boolean;
}

export interface ApplicantMatch {
  applicant_name: string;
  record_count: number;
  note: "not attributed to a tracked organization";
}

export interface SearchCoverage {
  tracked_organizations: number;
  note: string;
}

export interface SearchResponse {
  query: string;
  results: SearchResult[];
  applicant_matches: ApplicantMatch[];
  coverage: SearchCoverage;
  took_ms: number;
}

export interface OrganizationSummary {
  key: string;
  display_name: string;
  legal_name: string | null;
  ticker: string | null;
  country: string | null;
  organization_type: string;
  featured: boolean;
  event_count: number;
  event_range: EventWindow;
  attribution_review: "curated" | "pending_review";
}

export interface OrganizationsResponse {
  organizations: OrganizationSummary[];
  total: number;
  note: string;
}

export interface RegistryInfo {
  review_status: "curated" | "pending_review";
  metadata_source: string;
  updated_at: string;
  attribution_note: string;
}

export interface OwnershipLink {
  key: string;
  display_name: string;
  relation: string;
  status: "declared" | "pending_review" | "unknown";
}

export interface Ownership {
  parent: OwnershipLink | null;
  children: OwnershipLink[];
  note: string;
}

export interface RejectedSpelling {
  applicant_name: string;
  reason: string;
}

export interface AttributionExample {
  applicant_name: string;
  basis: string;
  review: "curated" | "pending_review";
  record_count: number;
}

export interface OrganizationAttribution {
  accepted_spellings: number;
  pending_review_spellings: number;
  rejected_spellings: RejectedSpelling[];
  unattributed_in_scope: number;
  examples: AttributionExample[];
}

export interface OrganizationSourceCoverage {
  source_id: SourceId;
  name: string;
  records: number;
  min_event_date: string | null;
  max_event_date: string | null;
  first_observed_at: string | null;
  published_field_available: boolean;
}

export interface OrganizationCoverage {
  window: EventWindow;
  sources: OrganizationSourceCoverage[];
}

export interface OrganizationProfile {
  key: string;
  display_name: string;
  display_name_zh: string | null;
  legal_name: string | null;
  ticker: string | null;
  exchange: string | null;
  country: string | null;
  country_name: string | null;
  organization_type: "public_company" | "private_company" | "subsidiary" | "unknown";
  description: string;
  registry: RegistryInfo;
  ownership: Ownership;
  attribution: OrganizationAttribution;
  coverage: OrganizationCoverage;
  counts: Counts;
  aggregations: Aggregations;
  recent_events: EventRecord[];
  data_quality_notes: string[];
  basis: Basis;
  snapshot: SnapshotRef;
  freshness: Freshness;
}

export interface EventsResponse {
  items: EventRecord[];
  page: number;
  page_size: number;
  total: number;
  total_pages: number;
  applied_filters: Record<string, string>;
  aggregations: Aggregations;
  counts: Counts;
  basis: Basis;
  snapshot: SnapshotRef;
}

export interface EventProvenance {
  source_id: SourceId;
  source_name: string;
  official_url: string;
  queried_endpoint: string;
  collected_at: string;
  official_identifier_label: string;
  raw: Record<string, string | null>;
}

export interface EventDetailResponse {
  event: EventRecord;
  provenance: EventProvenance;
  freshness: Freshness;
}

export interface CompareSourceCoverage {
  source_id: SourceId;
  name: string;
  records: number;
  min_event_date: string | null;
  max_event_date: string | null;
}

export interface CompareCoverage {
  window: EventWindow;
  sources: CompareSourceCoverage[];
  unmapped_category: number;
  pending_review: number;
}

export interface PerYearTotal {
  year: string;
  total: number;
  by_type: Record<EventType, number>;
}

export interface CompareOrganization {
  key: string;
  display_name: string;
  legal_name: string | null;
  ticker: string | null;
  country: string | null;
  counts: Counts;
  coverage: CompareCoverage;
  aggregations: Aggregations;
  per_year_totals: PerYearTotal[];
  share_of_all_tracked: Record<EventType, number>;
}

export interface CompareWindow {
  requested: EventWindow;
  effective: EventWindow;
  complete_years: string[];
  note: string;
}

export interface OrgValue {
  org_key: string;
  count: number;
}

export interface TotalsByType {
  event_type: EventType;
  label: string;
  values: OrgValue[];
  note: string;
}

export interface CategoryMatrix {
  id: string;
  label: string;
  values: OrgValue[];
  note: string;
}

export interface ClassMatrix {
  device_class: string;
  id: string;
  label: string;
  values: OrgValue[];
  note?: string;
}

export interface CompareWarning {
  code: string;
  severity: "info" | "warning";
  message: string;
  org_keys: string[];
}

export interface CompareResponse {
  organizations: CompareOrganization[];
  window: CompareWindow;
  totals_by_type: TotalsByType[];
  category_matrix: CategoryMatrix[];
  class_matrix: ClassMatrix[];
  warnings: CompareWarning[];
  disclaimer: string;
  basis: Basis;
  snapshot: SnapshotRef;
  freshness: Freshness;
}

export interface CoverageSource {
  source_id: SourceId;
  name: string;
  note?: string;
  endpoints: string[];
  records: number;
  min_event_date: string | null;
  max_event_date: string | null;
  official_base_url: string;
  licence: string;
  collected_at: string;
}

export interface CoverageOrgSource {
  source_id: SourceId;
  records: number;
  min_event_date: string | null;
  max_event_date: string | null;
}

export interface CoverageOrganization {
  key: string;
  display_name: string;
  records: number;
  sources: CoverageOrgSource[];
  pending_review_spellings: number;
}

export interface CollectionToken {
  token: string;
  org_key: string;
  endpoint: SourceId;
  records_retrieved: number;
  pages: number;
  urls: string[];
}

export interface CollectionUnattributed {
  applicant_name: string;
  records: number;
  endpoints: SourceId[];
}

export interface CollectionRejected {
  applicant_name: string;
  org_key: string;
  reason: string;
}

export interface CollectionAudit {
  tokens: CollectionToken[];
  unattributed: CollectionUnattributed[];
  rejected: CollectionRejected[];
}

export interface CoverageResponse {
  snapshot: SnapshotRef;
  freshness: Freshness;
  sources: CoverageSource[];
  organizations: CoverageOrganization[];
  collection_audit: CollectionAudit;
  out_of_scope: OutOfScopeItem[];
  time_semantics: TimeSemantic[];
  manifest: {
    id: string;
    collected_at: string;
    collection_started_at: string | null;
    openfda_last_updated: string | null;
    request_count: number | null;
    response_bytes: number | null;
    organization_count: number | null;
    counts: {
      records?: number;
      applicant_strings?: number;
      product_codes?: number;
      by_source?: Record<string, number>;
      by_event_type?: Record<string, number>;
    };
    data_quality: { implausible_event_date?: number; records?: number; truncated_text_fields?: number };
    errors: { url?: string; status?: string | number; body?: string }[];
    files: { name: string; sha256: string | null; bytes: number | null; records: number | null }[];
    notes: string[];
  };
  limitations: string[];
  attribution_summary: {
    curated_spellings: number;
    pending_review_spellings: number;
    rejected_spellings: number;
    unattributed_applicant_strings: number;
    unattributed_records: number;
  };
  reproduce: { collect: string; curate: string; serve: string; test: string };
}

export interface AttributionDecision {
  organization_key: string;
  organization_display: string;
  applicant_name: string;
  basis: string;
  review: "curated" | "pending_review";
  confidence: "high" | "medium" | "low";
  record_count: number;
  evidence: string;
}

export interface AttributionRejection {
  applicant_name: string;
  organization_key: string;
  reason: string;
}

export interface UnmatchedApplicant {
  applicant_name: string;
  records: number;
  endpoints: SourceId[];
  seen_with_tokens: string[];
}

export interface AttributionResponse {
  decisions: AttributionDecision[];
  rejected: AttributionRejection[];
  unmatched: UnmatchedApplicant[];
  policy: string[];
  snapshot: SnapshotRef;
}
