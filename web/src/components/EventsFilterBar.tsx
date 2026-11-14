import type { Category } from "../api/types";
import { useI18n, type TranslationKey } from "../i18n";
import { EVENT_TYPES, type EventsFilterState } from "../pages/eventsFilters";

export function EventsFilterBar({
  state,
  categories,
  organizations,
  onChange,
  onReset,
  showOrganization = true,
  resultCount,
}: {
  state: EventsFilterState;
  categories: Category[];
  organizations?: { key: string; display_name: string }[];
  onChange: (next: EventsFilterState) => void;
  onReset: () => void;
  showOrganization?: boolean;
  resultCount?: number;
}) {
  const { t } = useI18n();
  const update = (patch: Partial<EventsFilterState>) => onChange({ ...state, page: 1, ...patch });
  const toggleType = (type: string) => {
    const asType = EVENT_TYPES.find((item) => item === type);
    if (!asType) return;
    const has = state.types.includes(asType);
    update({ types: has ? state.types.filter((item) => item !== asType) : [...state.types, asType] });
  };
  return (
    <div className="filter-bar">
      {showOrganization && organizations ? (
        <label className="field">
          <span className="field-label">{t("common.organization")}</span>
          <select className="select" value={state.org} onChange={(event) => update({ org: event.target.value })}>
            <option value="">{t("common.all")}</option>
            {organizations.map((org) => (
              <option key={org.key} value={org.key}>
                {org.display_name}
              </option>
            ))}
          </select>
        </label>
      ) : null}

      <div className="field">
        <span className="field-label">{t("common.type")}</span>
        <div className="chip-group">
          {EVENT_TYPES.map((type) => (
            <button
              key={type}
              type="button"
              className="chip"
              aria-pressed={state.types.includes(type)}
              onClick={() => toggleType(type)}
            >
              <span
                className="dot"
                style={{
                  background:
                    type === "510k"
                      ? "var(--510k)"
                      : type === "pma"
                        ? "var(--pma)"
                        : type === "pma_supplement"
                          ? "var(--pma_supplement)"
                          : "var(--recall)",
                }}
                aria-hidden="true"
              />
              {t(("type." + type) as TranslationKey)}
            </button>
          ))}
        </div>
      </div>

      <label className="field">
        <span className="field-label">{t("common.from")}</span>
        <input className="input" type="date" value={state.from} onChange={(event) => update({ from: event.target.value })} />
      </label>
      <label className="field">
        <span className="field-label">{t("common.to")}</span>
        <input className="input" type="date" value={state.to} onChange={(event) => update({ to: event.target.value })} />
      </label>

      <label className="field">
        <span className="field-label">{t("common.category")}</span>
        <select className="select" value={state.category} onChange={(event) => update({ category: event.target.value })}>
          <option value="">{t("common.all")}</option>
          {categories.map((category) => (
            <option key={category.id} value={category.id}>
              {category.label}
            </option>
          ))}
          <option value="unclassified">{t("type.unclassified")}</option>
        </select>
      </label>

      <label className="field">
        <span className="field-label">{t("common.review")}</span>
        <select className="select" value={state.review} onChange={(event) => update({ review: event.target.value })}>
          <option value="">{t("common.all")}</option>
          <option value="curated">{t("review.curated")}</option>
          <option value="pending_review">{t("review.pending_review")}</option>
        </select>
      </label>

      <label className="field" style={{ minWidth: 220, flex: 1 }}>
        <span className="field-label">{t("common.applicant") + " / " + t("common.device")}</span>
        <input
          className="input"
          type="search"
          value={state.q}
          placeholder="K-number, device, applicant"
          onChange={(event) => update({ q: event.target.value })}
        />
      </label>

      <div className="row" style={{ marginLeft: "auto" }}>
        {typeof resultCount === "number" ? (
          <span className="filter-summary">
            <span className="count">{resultCount.toLocaleString()}</span> {t("common.records")}
          </span>
        ) : null}
        <button type="button" className="btn sm" onClick={onReset}>
          {t("common.reset")}
        </button>
      </div>
    </div>
  );
}
