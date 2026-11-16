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
  previous_snapshot_id?: string | null;
  content_hash?: string | null;
  source_versions?: Record<string, string | null>;
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
  /** Not evidence-verified and not human-reviewed (rule-verified counts as pending). */
  pending_review: number;
  provisional?: number;
  verified_records?: number;
  rule_verified_records?: number;
  curated_share?: number | null;
  rule_verified_share?: number | null;
  provisional_share?: number | null;
  by_verification?: Record<string, number>;
  historical_verified_current_group?: number;
  historical_verified_predecessor?: number;
  historical_unknown?: number;
  historical_by_reason?: Record<string, number>;
  by_source: SourceCount[];
  by_type: TypeCount[];
}

export interface Category {
  id: string;
  label: string;
}

export interface EventAttribution {
  status: "attributed" | "unattributed" | "rejected";
  basis: string | null;
  review: "curated" | "pending_review" | "rejected" | null;
  /** PRODUCT-002: the strength of the claim behind this row's organization attribution. */
  verification?: VerificationStatus;
  verification_label_en?: string;
  verification_label_zh?: string;
  verified?: boolean;
  rule?: string | null;
  evidence_count?: number;
  reviewer?: string | null;
  reviewer_kind?: "human" | "agent" | null;
  provenance?: string | null;
  predecessor_entity?: boolean;
  /** PRODUCT-003: who controlled the filing entity on the event date (UNKNOWN when unproven). */
  historical_owner?: {
    state: "verified" | "unknown";
    reason: string;
    reason_text: string;
    organization_key: string | null;
    display: string | null;
    relation_id: string | null;
    effective_from: string | null;
  };
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
  record_state?: "ACTIVE" | "MISSING_ON_RECHECK" | "QUERY_SCOPE_CHANGED" | "UNKNOWN";
  missing_count?: number;
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

export interface HealthCheck {
  state: string;
  detail?: string;
  snapshot_id?: string | null;
  using_fallback?: boolean;
  error?: string | null;
  latest_run_status?: string;
  latest_run_id?: string | null;
  last_check_at?: string | null;
  last_successful_sync_at?: string | null;
  failed_sources?: string[];
  pending_sources?: string[];
  latest_official_version?: string | null;
  official_version_age_days?: number | null;
  snapshot_age_days?: number | null;
}

export interface HealthResponse {
  status: "ok" | "degraded" | "unknown" | "not_ready";
  snapshot: SnapshotRef | null;
  version: string;
  store: string;
  checks?: Record<string, HealthCheck>;
  generated_at?: string;
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
  global_aggregations?: Aggregations;
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
  verified_records?: number;
  rule_verified_records?: number;
  provisional_records?: number;
  curated_share?: number | null;
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
  basis_label?: string;
  review: "curated" | "pending_review";
  status?: VerificationStatus;
  status_label_en?: string;
  status_label_zh?: string;
  verified?: boolean;
  rule?: string | null;
  evidence_count?: number;
  decision_uid?: string | null;
  reviewer?: string | null;
  reviewer_kind?: "human" | "agent" | null;
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
  ownership: OrganizationOwnership;
  attribution: OrganizationAttribution;
  verification?: OrganizationVerification;
  metrics?: Record<string, unknown>;
  coverage: OrganizationCoverage;
  counts: Counts;
  aggregations: Aggregations;
  technology?: OrganizationTechnology;
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
  verification?: CompareVerification;
  historical_ownership?: CompareHistoricalOwnership;
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
  comparability?: CompareComparability;
  basis_exclusions?: Record<string, { records_without_historical_basis: number; excluded_unknown_owner: number; excluded_predecessor_owner: number; counted_records: number }>;
  basis_excluded_totals?: { excluded_unknown_owner: number; excluded_predecessor_owner: number };
  not_evidence_of?: string[];
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

/* ------------------------------------------------------------------ PRODUCT-002 */
export type VerificationStatus =
  | "proposed"
  | "rule_verified"
  | "evidence_verified"
  | "human_reviewed"
  | "rejected"
  | "unresolved"
  | "unattributed";

export interface EvidenceRef {
  evidence_type: string;
  url: string | null;
  title: string | null;
  accessed_at: string | null;
  source_id?: string | null;
  quote?: string | null;
  note?: string | null;
}

export interface StatusDefinition {
  status: VerificationStatus;
  label_en: string;
  label_zh: string;
  meaning_en: string;
  curated: boolean;
  rule_verified: boolean;
  provisional: boolean;
  count: number;
}

export interface MetricDefinition {
  id: string;
  name_en: string;
  name_zh: string;
  unit: string;
  definition_en: string;
  definition_zh: string;
  is_not: string;
}

export interface PrecisionEstimate {
  state: "unknown" | "estimated";
  estimate: number | null;
  confidence_interval_95: [number | null, number | null] | null;
  sample_size: number;
  decidable_sample_size?: number;
  undecidable?: number | null;
  reviewer_kind: "human" | "agent" | null;
  human_review_completed?: boolean;
  supported?: number;
  contradicted?: number;
  caveats?: string[];
  decision_rule?: string;
  reason?: string;
  protocol?: string;
}

export interface RecordLevelMetrics {
  collected_records: number;
  attributed_records: number;
  attributed_share: number | null;
  verified_records: number;
  curated_share: number | null;
  rule_verified_records: number;
  rule_verified_share: number | null;
  provisional_records: number;
  provisional_share: number | null;
  by_status: Record<string, number>;
  by_event_type: Record<string, Record<string, number>>;
  by_source: Record<string, Record<string, number>>;
}

export interface ApplicantLevelMetrics {
  applicant_strings_observed: number;
  attributed_applicant_strings: number;
  attributed_applicant_share: number | null;
  accepted_spellings_in_registry: number;
  verified_spellings: number;
  verified_spelling_share: number | null;
  rule_verified_spellings: number;
  rule_verified_share: number | null;
  attributed_records: number;
  verified_record_share: number | null;
  rule_verified_record_share: number | null;
  top10_applicant_record_share: number | null;
  largest_applicant_record_share: number | null;
  largest_applicant: string | null;
  by_status: Record<string, number>;
  concentration_note: string;
}

export interface OrganizationLevelMetrics {
  tracked_organizations: number;
  organizations_with_records: number;
  organizations_with_records_share: number | null;
  median_curated_share: number | null;
  min_curated_share: number | null;
  max_curated_share: number | null;
  organizations_with_zero_verified_records: number;
  organizations_whose_records_are_all_provisional: number;
  note: string;
}

export interface RetrievalCoverage {
  state: "unknown";
  value: null;
  reason: string;
  what_would_be_needed: string[];
  what_is_known: Record<string, unknown>;
  not_the_same_as: string;
}

export interface MetricsResponse {
  snapshot: SnapshotRef;
  collected_at: string;
  definitions: MetricDefinition[];
  status_vocabulary: StatusDefinition[];
  levels: {
    record: RecordLevelMetrics;
    applicant: ApplicantLevelMetrics;
    organization: OrganizationLevelMetrics;
  };
  estimated_attribution_precision: PrecisionEstimate;
  retrieval_coverage: RetrievalCoverage;
  ownership_basis: Record<string, string>;
  warnings: string[];
  review_ledger: { decisions_applied: number; db: string | null };
  freshness?: Freshness;
  metric_definitions?: MetricDefinition[];
}

export interface OwnershipEvidence {
  evidence_type: string;
  url: string | null;
  title: string | null;
  accessed_at: string | null;
  source_id?: string | null;
  quote?: string | null;
  note?: string | null;
}

export interface OwnershipRelationPublic {
  relation_id: string;
  organization_key: string;
  entity: string;
  relation_type: string;
  patterns: string[];
  effective_from: string | null;
  effective_to: string | null;
  historical_owner_before: string | null;
  status: "evidence_verified" | "unresolved" | string;
  verified: boolean;
  reviewer: string;
  reviewer_kind: string;
  reviewed_at: string | null;
  caveat: string;
  notes: string[];
  evidence: OwnershipEvidence[];
}

export interface HistoricalSplitRow {
  relation_id: string;
  entity: string;
  relation_type: string;
  effective_from: string;
  historical_owner_before: string | null;
  records_before_effective_date: number;
  records_on_or_after_effective_date: number;
  records_without_event_date: number;
  evidence_count: number;
  caveat: string;
}

export interface HistoricalRecordLevel {
  records_total: number;
  verified_current_group: number;
  verified_predecessor: number;
  unknown: number;
  by_reason: Record<string, number>;
  note: string;
}

export interface OrganizationOwnership {
  schema: string;
  updated_at: string;
  concepts: Record<string, string>;
  current_group_policy: string;
  relations: OwnershipRelationPublic[];
  verified_relation_count: number;
  unresolved_relation_count: number;
  covered_applicant_patterns: string[];
  historical_split: HistoricalSplitRow[];
  record_level?: HistoricalRecordLevel;
  uncertainty: string;
}

export interface OrganizationVerification {
  definition: string;
  attributed_records: number;
  verified_records: number;
  rule_verified_records: number;
  provisional_records: number;
  curated_share: number | null;
  rule_verified_share: number | null;
  provisional_share: number | null;
  by_status: Record<string, number>;
  accepted_spellings: number;
  verified_spellings: number;
  rule_verified_spellings: number;
  provisional_spellings: number;
  status_counts_spellings: Record<string, number>;
  human_reviewed_spellings: number;
  risk_note: string;
}

export interface OwnershipResponse {
  schema: string;
  updated_at: string;
  note: string;
  concepts: Record<string, string>;
  relations: OwnershipRelationPublic[];
  verified_count: number;
  unresolved_count: number;
  organizations_with_verified_history: string[];
}

export interface CompareVerification {
  attributed_records: number;
  verified_records: number;
  rule_verified_records: number;
  provisional_records: number;
  curated_share: number | null;
  rule_verified_share: number | null;
  provisional_share: number | null;
  by_status: Record<string, number>;
}

export interface CompareHistoricalOwnership {
  records_in_window: number;
  verified_current_group: number;
  verified_predecessor: number;
  unknown: number;
  unknown_by_reason: Record<string, number>;
  records_from_predecessor_entities: number;
  verified_relations: number;
  note: string;
  excluded_unknown_owner?: number;
  excluded_predecessor_owner?: number;
  records_without_historical_basis?: number;
}

export interface CompareComparability {
  window_shared: boolean;
  event_types_shared: boolean;
  counting_unit: string;
  ownership_basis: string;
  review_filter: string;
  coverage_symmetric: boolean;
  single_pathway_only: boolean;
  verdict: string;
}

// ---------------------------------------------------------------- DATA-001
export interface DataStatusSource {
  source_id: string;
  source_name: string;
  endpoint: string;
  is_support_source?: boolean;
  declared_frequency: string;
  check_interval_hours: number;
  official_last_updated: string | null;
  official_total: number | null;
  record_count: number;
  last_checked_at: string | null;
  last_success_check_at: string | null;
  last_success_sync_at: string | null;
  last_success_official_last_updated?: string | null;
  last_success_official_total?: number | null;
  last_failed_at: string | null;
  last_full_reconciliation_at?: string | null;
  last_full_reconciliation_snapshot_id?: string | null;
  sync_status?: string | null;
  reconciliation_mode?: string | null;
  consecutive_failures: number;
  status: string;
  message: string | null;
  update_available: boolean;
  added_since_previous: number | null;
  updated_since_previous: number | null;
  removed_confirmed_since_previous: number | null;
  missing_on_recheck_since_previous: number | null;
  unresolved_since_previous: number | null;
  freshness_age_days: number | null;
  freshness_basis: string;
  note: string;
}

export interface ChangeRecord {
  change_id: string;
  source_id: string;
  official_record_id: string;
  event_id: string;
  change_type: string;
  detected_at: string;
  source_updated_at: string | null;
  previous_content_hash: string | null;
  new_content_hash: string | null;
  previous_snapshot_id: string | null;
  candidate_snapshot_id: string;
  changed_fields: Record<string, { previous: unknown; current: unknown }>;
  evidence: Record<string, unknown>;
  organization_key: string | null;
  applicant_name: string | null;
  event_type: string | null;
  event_date: string | null;
  record: EventRecord | null;
}

export interface DataStatusResponse {
  schema: string;
  configured: boolean;
  state: string;
  message: string;
  terminology: {
    continuously_monitored: boolean;
    automatically_synchronized: boolean;
    real_time_claim: boolean;
    labels: string[];
  };
  snapshot: {
    id: string;
    schema: string;
    collected_at: string;
    published_at: string | null;
    previous_snapshot_id: string | null;
    content_hash: string | null;
    openfda_last_updated: string | null;
    counts: Record<string, unknown> | null;
    change_summary: Record<string, number> | null;
    source_versions: Record<string, { official_last_updated: string | null; official_total: number | null }> | null;
    path: string | null;
    time_semantics: { field: string; meaning: string }[];
  } | null;
  synchronization: {
    state: string;
    last_successful_sync: string | null;
    last_check_attempt: string | null;
    active_snapshot_id: string | null;
    change_feed_available: boolean;
    action?: string | null;
    actor?: string | null;
    updated_sources?: string[];
    note?: string;
  };
  sources: DataStatusSource[];
  health?: {
    data: { state: string; using_fallback?: boolean; snapshot_id?: string | null };
    sync: Record<string, unknown> & { state: string };
    freshness: Record<string, unknown> & { state: string };
  };
  change_counts: Record<string, number>;
  recent_runs: Record<string, unknown>[];
  incidents: Record<string, unknown>[];
  request_usage_today: Record<string, unknown> | null;
  change_feed: ChangeRecord[];
  latency: {
    official_source_version: string | null;
    last_checked_by_medradar: string | null;
    last_successful_sync: string | null;
    sync_lag_hours: number | null;
    statement: string;
  };
  data_snapshot?: SnapshotRef;
  freshness?: Freshness;
  dataset_error?: string | null;
}

export interface ChangesResponse {
  configured: boolean;
  items: ChangeRecord[];
  total: number;
  page?: number;
  page_size?: number;
  filters: Record<string, string | null>;
  note?: string;
  message?: string;
}

/* ------------------------------------------------------------------ PRODUCT-004 intelligence brief */

export interface Bilingual {
  en: string;
  zh: string;
}

export interface BriefScope {
  from: string;
  to: string;
  requested_years: number | null;
  complete_years: string[];
  partial_years: string[];
  label: string;
  label_short: string;
  note: string;
  event_types: EventType[];
  event_type_labels: string[];
  ownership_basis: string;
  review_filter: string;
  counting_rule: Bilingual;
  snapshot: SnapshotRef;
  freshness: Freshness;
  generated_at: string;
}

export interface BriefRecordRef {
  event_id: string;
  official_id: string;
  event_type: EventType;
  event_date: string | null;
  published_at?: string | null;
  first_observed_at?: string | null;
  official_url: string;
  device_name: string | null;
  applicant_name: string | null;
  organization_key: string | null;
  product_code: string | null;
  attribution_verification: string;
  attribution_verified: boolean;
  verification_label_en: string;
  verification_label_zh: string;
  record_state?: string;
}

export interface BriefFinding {
  id: string;
  category: "finding" | "caution";
  title: Bilingual;
  statement: Bilingual;
  cannot_conclude: Bilingual;
  basis: { rule: string; inputs: Record<string, unknown>; rules_version: string };
  evidence: { record_count: number; records: BriefRecordRef[]; note: Bilingual | null };
  drilldown: { url?: string; label?: Bilingual };
}

export interface BriefTypeRow {
  event_type: EventType;
  label: string;
  label_zh: string;
  count: number;
  share: number | null;
  definition: Bilingual;
}

export interface BriefYearRow {
  year: string;
  counts: Record<EventType, number>;
  total: number;
  partial: boolean;
}

export interface BriefProductFamily {
  product_code: string;
  official_name: string | null;
  specialty: string;
  device_class: string | null;
  regulation_number: string | null;
  in_classification_dictionary: boolean;
  records: number;
  by_type: Record<EventType, number>;
  first_event_date: string | null;
  last_event_date: string | null;
  share: number | null;
}

export interface BriefPmaFamily {
  pma_number: string;
  family_id: string;
  name: string;
  device_id: string | null;
  device_url: string;
  original_in_snapshot: boolean;
  supplement_count_total: number | null;
  supplements_in_window: number;
  records_in_window: number;
  first_event_date: string | null;
  last_event_date: string | null;
  evidence_records: BriefRecordRef[];
}

export interface BriefTile {
  id: string;
  label: Bilingual;
  value: string | number;
  note: Bilingual;
}

export interface BriefChangeItem {
  change_type?: string;
  source_id?: string;
  official_id?: string;
  observed_at?: string;
  created_at?: string;
  [key: string]: unknown;
}

export interface BriefChanges {
  state: string;
  observed_at: string;
  counts: Record<string, number>;
  items: BriefChangeItem[];
  note: Bilingual;
}

export interface BriefLimitations {
  scope?: Bilingual[];
  coverage?: Bilingual[];
  identity?: Bilingual[];
  time?: Bilingual[];
  relationship?: Bilingual[];
  cannot_answer?: Bilingual[];
}

export interface BriefLimitationsBlock extends BriefLimitations {
  organization_key?: string;
  display_name?: string;
  state?: string;
}

export interface CompanyBrief {
  schema: string;
  kind: "company";
  generated_at: string;
  rules_version: string;
  title: Bilingual;
  question: Bilingual;
  scope: BriefScope;
  organization: {
    key: string;
    display_name: string;
    display_name_zh: string | null;
    legal_name: string | null;
    ticker: string | null;
    exchange: string | null;
    country: string | null;
    country_name: string | null;
    description: string;
    registry_review: string;
    registry_updated_at: string;
  };
  summary: {
    records: number;
    dated: number;
    undated: number;
    by_type: BriefTypeRow[];
    tiles: BriefTile[];
    sources: CompareSourceCoverage[];
    verification: {
      attributed_records: number;
      verified_records: number;
      rule_verified_records: number;
      provisional_records: number;
      curated_share: number | null;
      rule_verified_share: number | null;
      provisional_share: number | null;
      by_status: Record<string, number>;
      note: Bilingual;
    };
    ownership: {
      state_at_event_time: { verified_current_group: number; verified_predecessor: number; unknown: number };
      note: Bilingual;
    };
  };
  activity: {
    by_type: BriefTypeRow[];
    by_year: BriefYearRow[];
    complete_years: string[];
    partial_years: string[];
    note: Bilingual;
  };
  technology: {
    specialty: {
      rows: { id: string; label: string; count: number; share: number | null; by_type: Record<EventType, number> }[];
      unknown_count: number;
      unknown_share: number | null;
      unclassified_count: number;
      note: Bilingual;
    };
    product_families: {
      rows: BriefProductFamily[];
      row_count: number;
      records: number;
      records_without_product_code: number;
      not_in_classification_dictionary: number;
      note: Bilingual;
    };
  };
  devices: {
    families: BriefPmaFamily[];
    total_families_in_window: number;
    note: Bilingual;
  };
  recent: { records: BriefRecordRef[]; note: Bilingual };
  findings: BriefFinding[];
  changes: BriefChanges;
  evidence: {
    sources: CompareSourceCoverage[];
    snapshot: SnapshotRef;
    official_links: { label: string; official_id: string; event_type?: string; event_date?: string; url: string }[];
    appendix: { rows: number; note: Bilingual };
  };
  limitations: BriefLimitations;
}

export interface CompareMetric {
  id: string;
  label: Bilingual;
  definition: Bilingual;
  unit: string;
  values: { key: string; name: string; value: number; share: number | null }[];
  drilldown: Record<string, string>;
}

export interface BriefSide {
  key: string;
  display_name: string;
  legal_name: string | null;
  ticker: string | null;
  country: string | null;
  counts: Counts;
  counts_by_type: Record<EventType, number>;
  coverage: CompareCoverage;
  verification: {
    attributed_records: number;
    verified_records: number;
    rule_verified_records: number;
    provisional_records: number;
    curated_share: number | null;
    rule_verified_share: number | null;
    provisional_share: number | null;
    by_status: Record<string, number>;
  };
  historical_ownership: CompareHistoricalOwnership;
  per_year_totals: PerYearTotal[];
}

export interface CompareBrief {
  schema: string;
  kind: "compare";
  generated_at: string;
  rules_version: string;
  title: Bilingual;
  question: Bilingual;
  scope: BriefScope;
  sides: BriefSide[];
  comparability: CompareComparability;
  coverage_assessment: {
    symmetric: boolean;
    status: string;
    per_side: { key: string; name: string; source_count: number; sources: CompareSourceCoverage[] }[];
    note: Bilingual;
  };
  warnings: CompareWarning[];
  metrics: CompareMetric[];
  by_year: { key: string; name: string; rows: BriefYearRow[] }[];
  specialty: { note: Bilingual };
  findings: BriefFinding[];
  changes: (BriefChanges & { organization_key: string; display_name: string })[];
  disclaimer: string;
  not_evidence_of: string[];
  evidence: {
    sources: { key: string; name: string; sources: CompareSourceCoverage[] }[];
    snapshot: SnapshotRef;
    official_links: { label: string; official_id: string; event_type?: string; event_date?: string; organization_key?: string; url: string }[];
    appendix: { rows: number; note: Bilingual };
  };
  limitations: BriefLimitations;
}

export interface DeviceBrief {
  schema: string;
  kind: "device";
  generated_at: string;
  title: Bilingual;
  question: Bilingual;
  scope: BriefScope;
  device: Record<string, unknown> & { name?: string; official_id?: string; applicant_name?: string; product_code?: string; device_class?: string; identity_basis?: string; identity_basis_text?: string };
  family: Record<string, unknown> | null;
  application: Record<string, unknown> | null;
  versions: Record<string, unknown>[];
  supplements_count: number;
  tiles: BriefTile[];
  timeline: Record<string, unknown>[];
  relations: { confirmed_count: number; candidate_count: number; confirmed_rule: Bilingual; candidate_rule: Bilingual };
  related_recalls: {
    confirmed: Record<string, unknown>[];
    candidate: Record<string, unknown>[];
    note: Bilingual;
    unlinked_url: string;
  };
  findings: BriefFinding[];
  changes: BriefChanges;
  evidence: {
    snapshot: SnapshotRef;
    official_links: { label: string; official_id: string; url: string; event_type?: string; event_date?: string }[];
    appendix: { rows: number; note: Bilingual };
  };
  limitations: BriefLimitations;
}

export type Brief = CompanyBrief | CompareBrief | DeviceBrief;

export interface ExplainRecord extends BriefRecordRef {}

export interface ExplainResponse {
  schema: string;
  metric: string;
  label: Bilingual;
  definition: Bilingual;
  unit: string;
  scope: BriefScope;
  event_types: EventType[];
  filters: { category: string | null; product_code: string | null; ownership_basis: string; review_filter: string };
  denominator: { label: Bilingual; value: number };
  sides: { key: string; name: string; count: number; records: ExplainRecord[]; drilldown: string }[];
  note: Bilingual;
}

export interface OrganizationTechnology {
  product_families: {
    rows: BriefProductFamily[];
    row_count: number;
    records: number;
    records_without_product_code: number;
    not_in_classification_dictionary: number;
    note: string;
  };
  specialty_note: string;
}
