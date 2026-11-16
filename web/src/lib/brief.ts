import type { Bilingual, EventType } from "../api/types";

export type Lang = "en" | "zh";

export function pickText(value: Bilingual | string | null | undefined, lang: Lang): string {
  if (value === null || value === undefined) return "";
  if (typeof value === "string") return value;
  return lang === "zh" ? value.zh || value.en : value.en || value.zh;
}

export function typeLabel(type: EventType | string, lang: Lang): string {
  const en: Record<string, string> = {
    "510k": "510(k)",
    pma: "PMA",
    pma_supplement: "PMA supplement",
    recall: "Recall",
  };
  const zh: Record<string, string> = {
    "510k": "510(k)",
    pma: "PMA 原始批准",
    pma_supplement: "PMA 补充申请",
    recall: "召回",
  };
  return (lang === "zh" ? zh : en)[type] ?? String(type);
}

export function fmtNumber(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return value.toLocaleString();
}

export function fmtPercent(value: number | null | undefined, digits = 1): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return `${(value * 100).toFixed(digits)}%`;
}

export function fmtDate(value: string | null | undefined): string {
  return value ? value.slice(0, 10) : "—";
}

export function fmtWindow(scope: { from: string; to: string; label_short: string }, lang: Lang): string {
  return lang === "zh" ? `${scope.from} 至 ${scope.to}` : `${scope.from} to ${scope.to}`;
}


/** The API returns human labels in some tiles; map them back for localisation. */
const TYPE_BY_EN_LABEL: Record<string, EventType> = {
  "510(k) clearance": "510k",
  "PMA original approval": "pma",
  "PMA supplement": "pma_supplement",
  Recall: "recall",
};

export function localisePathwayLabel(value: string, lang: Lang): string {
  const type = TYPE_BY_EN_LABEL[value];
  return type ? typeLabel(type, lang) : value;
}
