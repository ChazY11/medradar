import type { EventType } from "../api/types";

export type EventSort = "event_date_desc" | "event_date_asc" | "official_id_asc";

export interface EventsFilterState {
  org: string;
  types: EventType[];
  from: string;
  to: string;
  category: string;
  productCode: string;
  q: string;
  review: string;
  sort: EventSort;
  page: number;
  pageSize: number;
}

export const EVENT_TYPES: EventType[] = ["510k", "pma", "pma_supplement", "recall"];
export const PAGE_SIZE = 25;

export function defaultFilters(): EventsFilterState {
  return { org: "", types: [], from: "", to: "", category: "", productCode: "", q: "", review: "", sort: "event_date_desc", page: 1, pageSize: PAGE_SIZE };
}

function isEventType(value: string): value is EventType {
  return (EVENT_TYPES as string[]).includes(value);
}

export function parseFilters(search: string): EventsFilterState {
  const params = new URLSearchParams(search);
  const state = defaultFilters();
  const org = params.get("org");
  if (org) state.org = org;
  const types = params.get("types");
  if (types) state.types = types.split(",").filter(isEventType);
  const from = params.get("from");
  if (from) state.from = from;
  const to = params.get("to");
  if (to) state.to = to;
  const category = params.get("category");
  if (category) state.category = category;
  const productCode = params.get("product_code");
  if (productCode) state.productCode = productCode.toUpperCase();
  const q = params.get("q");
  if (q) state.q = q;
  const review = params.get("review");
  if (review) state.review = review;
  const sort = params.get("sort");
  if (sort === "event_date_asc" || sort === "official_id_asc" || sort === "event_date_desc") state.sort = sort;
  const page = Number(params.get("page") ?? "1");
  if (Number.isFinite(page) && page >= 1) state.page = Math.floor(page);
  return state;
}

export function toQueryString(state: EventsFilterState): string {
  const params = new URLSearchParams();
  if (state.org) params.set("org", state.org);
  if (state.types.length) params.set("types", state.types.join(","));
  if (state.from) params.set("from", state.from);
  if (state.to) params.set("to", state.to);
  if (state.category) params.set("category", state.category);
  if (state.productCode) params.set("product_code", state.productCode.toUpperCase());
  if (state.q) params.set("q", state.q);
  if (state.review) params.set("review", state.review);
  if (state.sort !== "event_date_desc") params.set("sort", state.sort);
  if (state.page > 1) params.set("page", String(state.page));
  const text = params.toString();
  return text ? "?" + text : "";
}

export function activeFilterCount(state: EventsFilterState): number {
  let count = 0;
  if (state.org) count += 1;
  count += state.types.length;
  if (state.from) count += 1;
  if (state.to) count += 1;
  if (state.category) count += 1;
  if (state.productCode) count += 1;
  if (state.q) count += 1;
  if (state.review) count += 1;
  return count;
}
