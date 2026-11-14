import { Link } from "react-router-dom";
import type { EventRecord, EventType } from "../api/types";
import { useI18n } from "../i18n";
import { EventTypeBadge, ReviewBadge, formatDate } from "./ui";

export type EventSortKey = "event_date_desc" | "event_date_asc" | "official_id_asc";

function SortHeader({
  label,
  active,
  onClick,
}: {
  label: string;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button type="button" className="link" onClick={onClick} style={{ fontWeight: active ? 700 : 500 }}>
      {label}
      {active ? " \u25be" : ""}
    </button>
  );
}

export function EventTable({
  items,
  onOpen,
  sort,
  onSort,
  compact = false,
  showOrganization = true,
}: {
  items: EventRecord[];
  onOpen: (event: EventRecord) => void;
  sort?: EventSortKey;
  onSort?: (sort: EventSortKey) => void;
  compact?: boolean;
  showOrganization?: boolean;
}) {
  const { t } = useI18n();
  const dateHeader = onSort ? (
    <SortHeader
      label={t("common.eventDate")}
      active={sort === "event_date_desc" || sort === "event_date_asc"}
      onClick={() => onSort(sort === "event_date_desc" ? "event_date_asc" : "event_date_desc")}
    />
  ) : (
    t("common.eventDate")
  );
  const idHeader = onSort ? (
    <SortHeader label={t("common.officialId")} active={sort === "official_id_asc"} onClick={() => onSort("official_id_asc")} />
  ) : (
    t("common.officialId")
  );

  return (
    <div className="table-wrap">
      <table className="data">
        <thead>
          <tr>
            <th scope="col" style={{ width: 92 }}>{dateHeader}</th>
            <th scope="col" style={{ width: 126 }}>{t("common.type")}</th>
            {showOrganization ? <th scope="col">{t("common.organization")}</th> : null}
            <th scope="col" style={{ width: 120 }}>{idHeader}</th>
            <th scope="col">{t("common.device")}</th>
            {compact ? null : <th scope="col">{t("common.category")}</th>}
            <th scope="col" style={{ width: 104 }}>{t("common.review")}</th>
            <th scope="col" style={{ width: 70 }}>{t("common.evidence")}</th>
          </tr>
        </thead>
        <tbody>
          {items.map((event) => (
            <tr key={event.event_id} className="clickable" onClick={() => onOpen(event)} tabIndex={0} onKeyDown={(input) => {
              if (input.key === "Enter" || input.key === " ") {
                input.preventDefault();
                onOpen(event);
              }
            }}>
              <td className="num nowrap" data-label={t("common.eventDate")}>
                {formatDate(event.event_date)}
              </td>
              <td data-label={t("common.type")}>
                <EventTypeBadge type={event.event_type} short={compact} />
              </td>
              {showOrganization ? (
                <td data-label={t("common.organization")}>
                  {event.organization_key ? (
                    <Link className="cell-primary" to={"/organizations/" + event.organization_key} onClick={(input) => input.stopPropagation()}>
                      {event.organization_name}
                    </Link>
                  ) : (
                    <span className="muted">{t("state.notAvailable")}</span>
                  )}
                  <div className="cell-sub mono truncate" title={event.applicant_name}>
                    {event.applicant_name}
                  </div>
                </td>
              ) : null}
              <td className="mono nowrap" data-label={t("common.officialId")}>
                {event.official_id}
              </td>
              <td data-label={t("common.device")}>
                <div className="truncate" style={{ maxWidth: 380 }} title={event.device_name ?? event.title}>
                  {event.device_name ?? event.title}
                </div>
                {event.product_code ? <div className="cell-sub mono">{event.product_code}</div> : null}
              </td>
              {compact ? null : (
                <td className="small" data-label={t("common.category")}>
                  <div>{event.category ? event.category.label : <span className="muted">{t("type.unclassified")}</span>}</div>
                  <div className="cell-sub">
                    {event.device_class ? "Class " + event.device_class : "-"}
                    {event.product_code ? " \u00b7 " + event.product_code : ""}
                  </div>
                </td>
              )}
              <td data-label={t("common.review")}>
                <ReviewBadge review={event.attribution.review} compact />
              </td>
              <td data-label={t("common.evidence")}>
                <button
                  type="button"
                  className="evidence-link"
                  title={"Open official record " + event.official_url}
                  onClick={(input) => {
                    input.stopPropagation();
                    onOpen(event);
                  }}
                >
                  {t("common.evidence")}
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <div className="card-footer">
        {t("common.eventDate")}: FDA decision date (510(k)/PMA) or firm recall-initiation date - never a publication date. Open a
        row's evidence panel for the four separate time fields.
      </div>
    </div>
  );
}

export function typeLabel(type: EventType): string {
  return type;
}
