/** Client for the Device Intelligence API (PRODUCT-003). */
import type { EventType } from "./types";

const BASE = "";

export class DeviceApiError extends Error {
  status: number;
  code: string;
  constructor(status: number, code: string, message: string) {
    super(message);
    this.name = "DeviceApiError";
    this.status = status;
    this.code = code;
  }
}

async function request<T>(path: string): Promise<T> {
  const response = await fetch(BASE + path);
  let payload: unknown = null;
  try {
    payload = await response.json();
  } catch {
    payload = null;
  }
  if (!response.ok) {
    const envelope = payload as { error?: { code?: string; message?: string; hint?: string } } | null;
    throw new DeviceApiError(
      response.status,
      envelope?.error?.code ?? "http_" + response.status,
      (envelope?.error?.message ?? "Request failed with status " + response.status) +
        (envelope?.error?.hint ? " " + envelope.error.hint : ""),
    );
  }
  return payload as T;
}

export interface RelationEvidence {
  kind: string;
  field: string;
  value: string;
  official_url: string | null;
  event_id: string | null;
  note: string | null;
}

export interface DeviceRelationPayload {
  relation_id: string;
  relation_type: string;
  status: "confirmed" | "evidence_supported" | "candidate" | "unlinked";
  status_label_en: string;
  status_label_zh: string;
  source_id: string;
  source_kind: string;
  target_id: string;
  target_kind: string;
  rule: string;
  evidence: RelationEvidence[];
  snapshot_id: string;
  target_in_snapshot: boolean;
  score: number | null;
  note: string | null;
}

export interface DeviceCounts {
  applications: number;
  versions: number;
  recalls: number;
  confirmed_relations: number;
  candidate_relations: number;
}

export interface DeviceSummary {
  device_id: string;
  identity_basis: "510k_clearance" | "pma_approval" | string;
  identity_basis_text: string;
  application_id: string;
  kind: "510k" | "pma" | string;
  official_id: string;
  name: string;
  applicant_name: string;
  organization_key: string | null;
  organization_display?: string | null;
  product_code: string | null;
  category_id: string | null;
  category_label: string | null;
  device_class: string | null;
  first_event_date: string | null;
  application_ids: string[];
  models: string[];
  family_id: string | null;
  record_count: number;
  counts?: DeviceCounts;
}

export interface DevicesResponse {
  items: DeviceSummary[];
  page: number;
  page_size: number;
  total: number;
  total_pages: number;
  filters: Record<string, string | null>;
  definitions: Record<string, string>;
  pathway_counts: Record<string, number>;
  categories: { id: string; label: string }[];
  quality_summary: Record<string, number | null>;
  index_build_ms: number;
}

export interface DevicesQuery {
  q?: string;
  org?: string;
  product_code?: string;
  category?: string;
  pathway?: string;
  relation?: string;
  sort?: string;
  page?: number;
  page_size?: number;
}

function query(params: Record<string, string | number | undefined>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === "") continue;
    search.set(key, String(value));
  }
  const text = search.toString();
  return text ? "?" + text : "";
}

export async function listDevices(params: DevicesQuery): Promise<DevicesResponse> {
  return request<DevicesResponse>("/api/devices" + query(params as Record<string, string | number | undefined>));
}

export function devicesCsvUrl(params: DevicesQuery): string {
  return "/api/export/devices.csv" + query(params as Record<string, string | number | undefined>);
}

export interface TimelineItem {
  kind: EventType | string;
  kind_label: string;
  official_id: string;
  date: string | null;
  event_date: string | null;
  first_observed_at: string;
  date_note: string;
  official_url: string;
  relation_status: string;
  detail: string | null;
  event_id: string;
  version_of?: string;
}

export interface ApplicationPayload {
  application_id: string;
  official_id: string;
  kind: string;
  kind_label: string;
  official_url: string;
  event_id: string;
  applicant_name: string;
  organization_key: string | null;
  product_code: string | null;
  advisory_committee: string | null;
  device_name: string | null;
  trade_name: string | null;
  decision_date: string | null;
  decision_code: string | null;
  pma_number: string | null;
  supplement_number: string | null;
  supplement_type: string | null;
  supplement_reason: string | null;
  parent_application_id: string | null;
}

export interface FamilyPayload {
  family_id: string;
  kind: string;
  name: string;
  organization_key: string | null;
  applicant_name: string;
  device_id: string | null;
  application_id: string | null;
  version_application_ids: string[];
  supplement_count: number;
  first_event_date: string | null;
  last_event_date: string | null;
  models: string[];
  original_in_snapshot: boolean;
  basis: string;
}

export interface RecallPayload {
  event_id: string;
  official_id: string;
  official_url: string;
  applicant_name: string;
  organization_key: string | null;
  product_code: string | null;
  product_description: string | null;
  reason_for_recall: string | null;
  root_cause: string | null;
  recall_status: string | null;
  initiated_date: string | null;
  posted_date: string | null;
  res_event_number: string | null;
  product_res_number: string | null;
  k_numbers: string[];
}

export interface ApplicantBlock {
  applicant_name: string;
  state: "attributed" | "rejected" | "unattributed";
  organization_key: string | null;
  organization_display: string | null;
  verification: string;
  verified: boolean;
  rule?: string | null;
  note: string;
}

export interface DeviceDetailResponse {
  device: DeviceSummary;
  counts: DeviceCounts;
  identity: {
    basis: string;
    basis_text: string;
    what_this_page_represents: string;
    not_impersonating_fda: string;
    name_is_not_unique: boolean;
  };
  applicant: ApplicantBlock;
  application: ApplicationPayload | null;
  versions: ApplicationPayload[];
  family: FamilyPayload | null;
  timeline: TimelineItem[];
  relations: {
    confirmed: DeviceRelationPayload[];
    candidate: DeviceRelationPayload[];
    relation_types: Record<string, string>;
  };
  related_recalls: { confirmed: RecallPayload[]; candidate: DeviceRelationPayload[]; note: string };
  evidence: { label: string; official_url: string; official_id: string }[];
  disclosures: Record<string, string | null>;
  definitions: Record<string, string>;
}

export interface FamilyResponse {
  family: FamilyPayload;
  device: DeviceSummary | null;
  application: ApplicationPayload | null;
  versions: ApplicationPayload[];
  versions_count: number;
  related_recalls: RecallPayload[];
  applicant: ApplicantBlock;
  disclosures: Record<string, string | null>;
  timeline: TimelineItem[];
  definitions: Record<string, string>;
}

export interface UnlinkedResponse {
  items: { recall: RecallPayload; reason: string; official_url: string }[];
  page: number;
  page_size: number;
  total: number;
  total_pages: number;
  note: string;
}

export async function getDevice(deviceId: string): Promise<DeviceDetailResponse> {
  return request<DeviceDetailResponse>("/api/devices/" + encodeURIComponent(deviceId));
}

export async function getFamily(familyId: string): Promise<FamilyResponse> {
  return request<FamilyResponse>("/api/device-families/" + encodeURIComponent(familyId));
}

export async function listUnlinkedRecalls(page = 1, pageSize = 25): Promise<UnlinkedResponse> {
  return request<UnlinkedResponse>("/api/devices/unlinked" + query({ page, page_size: pageSize }));
}

export interface DeviceQualityResponse {
  applications: number;
  applications_by_kind: Record<string, number>;
  devices: number;
  families: Record<string, unknown>;
  recalls: Record<string, number | string>;
  relations: Record<string, unknown>;
  coverage: Record<string, unknown>;
  conflicts_and_ambiguity: Record<string, number | string>;
  verification_levels: Record<string, unknown>;
  not_modelled: Record<string, string>;
  limitations: string[];
  index_build_ms: number;
}

export async function getDeviceQuality(): Promise<DeviceQualityResponse> {
  return request<DeviceQualityResponse>("/api/devices/quality");
}

export function deviceMarkdownUrl(deviceId: string): string {
  return "/api/export/device.md" + query({ device: deviceId });
}
