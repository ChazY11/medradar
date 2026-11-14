import { useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { listOrganizations } from "../api/client";
import { useAsync } from "../api/hooks";
import { AsyncSection } from "../components/async";
import { Badge, Card, EmptyState, PageHeader, formatDate } from "../components/ui";
import { useI18n } from "../i18n";

export function OrganizationsPage() {
  const { t, bi } = useI18n();
  const navigate = useNavigate();
  const result = useAsync(() => listOrganizations(), []);
  const [filter, setFilter] = useState("");

  const rows = useMemo(() => {
    const items = result.data?.organizations ?? [];
    const needle = filter.trim().toLowerCase();
    const filtered = needle
      ? items.filter((org) =>
          [org.display_name, org.legal_name ?? "", org.ticker ?? "", org.key].some((value) => value.toLowerCase().includes(needle)),
        )
      : items;
    return [...filtered].sort((a, b) => (b.featured ? 1 : 0) - (a.featured ? 1 : 0) || b.event_count - a.event_count);
  }, [result.data, filter]);

  return (
    <>
      <PageHeader
        eyebrow={bi("Coverage", "覆盖范围")}
        title={t("orgs.title")}
        description={t("orgs.desc")}
        actions={
          <Link className="btn" to="/compare">
            {t("compare.title")}
          </Link>
        }
      />
      <div className="stack">
        <div className="filter-bar">
          <label className="field" style={{ flex: 1, minWidth: 260 }}>
            <span className="field-label">{t("orgs.search")}</span>
            <input
              className="input"
              type="search"
              value={filter}
              placeholder={bi("Name, legal name or ticker", "名称、法定名称或股票代码")}
              onChange={(event) => setFilter(event.target.value)}
            />
          </label>
          <div className="filter-summary">
            <span className="count">{rows.length}</span> / {result.data?.total ?? "?"} {bi("organizations", "家企业")}
          </div>
        </div>

        <Card flush>
          <AsyncSection status={result.status} data={result.data} error={result.error} reload={result.reload} loadingLines={8}>
            {() =>
              rows.length ? (
                <div className="table-wrap">
                  <table className="data">
                    <thead>
                      <tr>
                        <th scope="col">{t("common.organization")}</th>
                        <th scope="col">{bi("Ticker", "股票代码")}</th>
                        <th scope="col">{bi("Country", "国家/地区")}</th>
                        <th scope="col" className="num">{t("common.records")}</th>
                        <th scope="col">{bi("Event date range", "事件日期范围")}</th>
                        <th scope="col">{t("common.review")}</th>
                        <th scope="col">{t("common.actions")}</th>
                      </tr>
                    </thead>
                    <tbody>
                      {rows.map((org) => (
                        <tr
                          key={org.key}
                          className="clickable"
                          onClick={() => navigate("/organizations/" + org.key)}
                          tabIndex={0}
                          onKeyDown={(event) => {
                            if (event.key === "Enter" || event.key === " ") {
                              event.preventDefault();
                              navigate("/organizations/" + org.key);
                            }
                          }}
                        >
                          <td data-label={t("common.organization")}>
                            <div className="row" style={{ gap: 6 }}>
                              <span className="cell-primary">{org.display_name}</span>
                              {org.featured ? <Badge tone="info">{bi("Featured", "重点")}</Badge> : null}
                            </div>
                            <div className="cell-sub">{org.legal_name ?? ""}</div>
                          </td>
                          <td className="mono small" data-label={bi("Ticker", "股票代码")}>{org.ticker ?? "-"}</td>
                          <td className="small" data-label={bi("Country", "国家/地区")}>{org.country ?? <span className="muted">-</span>}</td>
                          <td className="num" data-label={t("common.records")}>{org.event_count.toLocaleString()}</td>
                          <td className="small muted nowrap" data-label={bi("Event date range", "事件日期范围")}>
                            {formatDate(org.event_range.from)} {"\u2192"} {formatDate(org.event_range.to)}
                          </td>
                          <td data-label={t("common.review")}>
                            {org.attribution_review === "pending_review" ? (
                              <Badge tone="warn">{t("review.pending_review")}</Badge>
                            ) : (
                              <Badge tone="neutral">{t("review.curated")}</Badge>
                            )}
                          </td>
                          <td data-label={t("common.actions")}>
                            <Link className="link small" to={"/organizations/" + org.key} onClick={(event) => event.stopPropagation()}>
                              {bi("Open", "打开")}
                            </Link>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <EmptyState
                  title={bi("No organization matches this filter", "没有匹配的企业")}
                  description={bi(
                    "Tracked coverage is a reviewed list, not the full FDA applicant universe. Unattributed applicant names are listed on the sources page.",
                    "收录范围是经过复核的名单，而不是 FDA 全量申请人数据库。未归属的申请人名称列在“数据来源与覆盖”页面。",
                  )}
                  actions={
                    <button type="button" className="btn" onClick={() => setFilter("")}>
                      {t("common.reset")}
                    </button>
                  }
                />
              )
            }
          </AsyncSection>
        </Card>
      </div>
    </>
  );
}
