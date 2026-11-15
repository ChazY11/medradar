import { useEffect } from "react";
import { getEvent } from "../api/client";
import { useAsync } from "../api/hooks";
import { useI18n, type TranslationKey } from "../i18n";
import { AsyncSection } from "./async";
import { Badge, EventTypeBadge, KeyValue, ReviewBadge, TimeQualityBadge, formatDate, formatDateTime } from "./ui";
import { VerificationBadge } from "./transparency";

export function EvidenceDrawer({ eventId, onClose }: { eventId: string; onClose: () => void }) {
  const { t, bi } = useI18n();
  const detail = useAsync(() => getEvent(eventId), [eventId]);

  useEffect(() => {
    const handler = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [onClose]);

  return (
    <>
      <div className="drawer-scrim" onClick={onClose} aria-hidden="true" />
      <aside className="drawer" role="dialog" aria-modal="true" aria-label={t("common.evidence")}>
        <div className="drawer-head">
          <div>
            <div className="eyebrow">{t("common.evidence")}</div>
            <div className="row" style={{ gap: 8, marginTop: 4 }}>
              <span className="mono small">{eventId}</span>
            </div>
          </div>
          <button type="button" className="btn sm" onClick={onClose} aria-label={t("common.close")}>
            Esc
          </button>
        </div>
        <div className="drawer-body">
          <AsyncSection status={detail.status} data={detail.data} error={detail.error} reload={detail.reload} loadingLines={8}>
            {(payload) => {
              const event = payload.event;
              const provenance = payload.provenance;
              return (
                <>
                  <div className="drawer-section">
                    <div className="row" style={{ gap: 10 }}>
                      <EventTypeBadge type={event.event_type} />
                      <Badge tone="neutral">{event.source_name}</Badge>
                      <TimeQualityBadge quality={event.time_quality} />
                    </div>
                    <div className="mt-8" style={{ fontSize: 15, fontWeight: 620, lineHeight: 1.4 }}>
                      {event.title}
                    </div>
                    {event.summary && event.summary.trim() && event.summary !== event.title ? (
                      <div className="small muted mt-8" style={{ lineHeight: 1.55 }}>
                        {event.summary}
                      </div>
                    ) : null}
                  </div>

                  <div className="drawer-section">
                    <h3>{t("common.officialId")}</h3>
                    <KeyValue
                      rows={[
                        { label: provenance.official_identifier_label, value: <span className="mono">{event.official_id}</span> },
                        {
                          label: t("common.source"),
                          value: (
                            <span>
                              {provenance.source_name}
                              <div className="tiny muted">openFDA device endpoint collection; the exact query URL is recorded in the snapshot manifest.</div>
                              {provenance.queried_endpoint ? (
                                <details className="mt-0">
                                  <summary className="tiny link" style={{ cursor: "pointer" }}>
                                    Show collection query
                                  </summary>
                                  <div className="tiny mono truncate" style={{ maxWidth: 380 }} title={provenance.queried_endpoint}>
                                    {provenance.queried_endpoint}
                                  </div>
                                </details>
                              ) : null}
                            </span>
                          ),
                        },
                        {
                          label: t("common.openRecord"),
                          value: (
                            <a className="link mono" href={event.official_url} target="_blank" rel="noopener noreferrer">
                              {event.official_url}
                            </a>
                          ),
                        },
                      ]}
                    />
                  </div>

                  <div className="drawer-section">
                    <h3>{bi("Time", "时间语义")}</h3>
                    <KeyValue
                      rows={[
                        {
                          label: (
                            <span className="def" title="When the regulatory event happened (decision date, or recall initiation).">
                              {t("common.eventDate")}
                            </span>
                          ),
                          value: (
                            <span>
                              {formatDate(event.event_date)}
                              {event.event_date ? null : <Badge tone="danger">{t("time.unknown")}</Badge>}
                            </span>
                          ),
                        },
                        {
                          label: (
                            <span className="def" title="When the source published the record, only if the source states it.">
                              {t("common.publishedAt")}
                            </span>
                          ),
                          value:
                            event.published_at_status === "not_published_by_source" ? (
                              <span className="muted">
                                {bi(
                                  "Not published by this source - openFDA states no publication time for 510(k)/PMA records.",
                                  "来源未公开该时间：openFDA 不为 510(k)/PMA 记录提供公开时间。",
                                )}
                              </span>
                            ) : (
                              formatDate(event.published_at)
                            ),
                        },
                        {
                          label: (
                            <span className="def" title="When MedRadar first ingested this record. Not the date the event became public.">
                              {t("common.firstObserved")}
                            </span>
                          ),
                          value: <span className="mono small">{formatDateTime(event.first_observed_at)}</span>,
                        },
                        {
                          label: <span className="def" title="Conservative lower bound of availability.">{t("common.availableAt")}</span>,
                          value: <span className="mono small">{formatDateTime(event.available_at)}</span>,
                        },
                      ]}
                    />
                  </div>

                  <div className="drawer-section">
                    <h3>{bi("Attribution", "归属")}</h3>
                    <KeyValue
                      rows={[
                        { label: t("common.applicant"), value: <span className="mono small">{event.applicant_name || "-"}</span> },
                        { label: t("common.organization"), value: event.organization_name ?? <span className="muted">{bi("Not attributed", "未归属")}</span> },
                        { label: t("common.review"), value: <ReviewBadge review={event.attribution.review} /> },
                        {
                          label: <span className="def" title="The strength of the claim behind this row's organization attribution. Rule-verified is not human review.">{bi("Verification", "核验状态")}</span>,
                          value: <VerificationBadge status={event.attribution.verification} labelEn={event.attribution.verification_label_en} labelZh={event.attribution.verification_label_zh} compact />,
                        },
                        ...(event.attribution.rule
                          ? [{ label: bi("Rule / evidence", "规则/证据"), value: <span className="small mono">{event.attribution.rule}{event.attribution.evidence_count ? " + " + event.attribution.evidence_count + " evidence" : ""}</span> }]
                          : []),
                        {
                          label: <span className="def" title="Who controlled the filing entity when the regulatory event happened. Only stated where a verified ownership relation with an effective date exists.">{bi("Owner at event time", "事件发生时所有者")}</span>,
                          value: (
                            <span className="small">
                              {event.attribution.historical_owner?.state === "verified"
                                ? event.attribution.historical_owner.reason === "verified_predecessor"
                                  ? bi("Predecessor: ", "前身实体：") + (event.attribution.historical_owner.display ?? "")
                                  : bi("This group", "本集团") + (event.attribution.historical_owner.effective_from ? " (relation effective " + event.attribution.historical_owner.effective_from + ")" : "")
                                : bi("UNKNOWN - ", "未知 - ") + (event.attribution.historical_owner?.reason_text ?? "")}
                            </span>
                          ),
                        },
                        {
                          label: bi("Basis", "归属依据"),
                          value: event.attribution.basis ? <Badge tone="outline">{event.attribution.basis}</Badge> : "-",
                        },
                      ]}
                    />
                  </div>

                  <div className="drawer-section">
                    <h3>{bi("Product", "产品与分类")}</h3>
                    <KeyValue
                      rows={[
                        { label: bi("Device name", "器械名称"), value: event.device_name ?? "-" },
                        { label: bi("Product code", "产品代码"), value: <span className="mono">{event.product_code ?? "-"}</span> },
                        { label: t("common.category"), value: event.category ? event.category.label : <span className="muted">{t("type.unclassified")}</span> },
                        { label: t("common.deviceClass"), value: event.device_class ? "Class " + event.device_class : "-" },
                      ]}
                    />
                  </div>

                  <div className="drawer-section">
                    <h3>{bi("Verbatim source fields", "来源原始字段")}</h3>
                    <div className="table-wrap">
                      <table className="raw-table">
                        <tbody>
                          {Object.entries(provenance.raw).map(([key, value]) => (
                            <tr key={key}>
                              <td>{key}</td>
                              <td>{value === null || value === "" ? <span className="muted">-</span> : String(value)}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>

                  <div className="drawer-section">
                    <h3>{bi("Collection provenance", "采集来源")}</h3>
                    <KeyValue
                      rows={[
                        { label: bi("Snapshot", "快照"), value: <span className="mono small">{payload.freshness.collected_at ?? "-"}</span> },
                        { label: bi("Collected at", "采集时间"), value: <span className="mono small">{provenance.collected_at}</span> },
                        { label: bi("Official record", "官方记录"), value: provenance.official_identifier_label },
                      ]}
                    />
                    <div className="callout mt-12">
                      {bi(
                        "Every value on this screen comes from the FDA record above. Attribution is an exact-string decision recorded by MedRadar; the verbatim applicant name is shown so the decision can be checked.",
                        "本页所有取值均来自上方的 FDA 原始记录。企业归属是 MedRadar 记录的精确字符串匹配决策；申请人原始名称一并显示，便于复核该决策。",
                      )}
                    </div>
                  </div>
                </>
              );
            }}
          </AsyncSection>
        </div>
      </aside>
    </>
  );
}

export function eventTypeLabelKey(type: string): TranslationKey {
  return ("type." + type) as TranslationKey;
}
