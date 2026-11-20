import { Link, useParams } from "react-router-dom";
import { useAsync } from "../api/hooks";
import { getCompany } from "../api/human";
import { useI18n } from "../i18n";
import { Badge, Card, KeyValue, PageHeader, formatNumber } from "../components/ui";
import { AsyncSection } from "../components/async";

export function CompanyPage() {
  const { bi } = useI18n();
  const { organizationId } = useParams();
  const id = organizationId || "";
  const company = useAsync(() => getCompany(id), [id]);

  return (
    <>
      <PageHeader
        eyebrow={bi("Company", "公司")}
        title={bi("Company profile", "公司档案")}
        description={bi(
          "What this product actually holds about one company: recent records, recalls, topics and products, all from the ledger.",
          "本产品对一家公司实际掌握的内容：最近的记录、召回、技术主题与产品，全部来自账本。",
        )}
      />
      <AsyncSection status={company.status} data={company.data} error={company.error} reload={company.reload} loadingLines={6}>
        {(payload) => (
          <>
            <Card title={bi(payload.company.display_name, payload.company.label_zh || payload.company.display_name)}>
              <KeyValue
                rows={[
                  { label: bi("Identifier", "标识"), value: <span className="mono small">{payload.company.organization_id}</span> },
                  { label: bi("Canonical name", "标准名"), value: payload.company.canonical_name || "-" },
                  { label: bi("Country", "国家"), value: payload.company.country || "-" },
                  { label: bi("Records", "记录总数"), value: formatNumber(payload.totals.observations) },
                  { label: bi("Recalls", "召回"), value: formatNumber(payload.totals.recalls) },
                  {
                    label: bi("By source", "按来源"),
                    value: Object.entries(payload.totals.by_source)
                      .map(([key, value]) => key + " " + value)
                      .join(" · ") || "-",
                  },
                ]}
              />
            </Card>

            {payload.recalls.length > 0 ? (
              <Card title={bi("Recalls and safety", "召回与安全")}>
                <ul style={{ margin: 0, paddingLeft: 18 }}>
                  {payload.recalls.map((row) => (
                    <li key={row.observation_id} style={{ marginBottom: 6 }}>
                      <a href={row.source_url || undefined} target="_blank" rel="noreferrer noopener">
                        {row.title}
                      </a>
                      <div className="small muted">
                        {row.official_identifier || ""} · {row.published_at || ""}
                      </div>
                    </li>
                  ))}
                </ul>
              </Card>
            ) : null}

            <Card title={bi("Most recent records", "最近的记录")}>
              <ul style={{ margin: 0, paddingLeft: 18 }}>
                {payload.recent.map((row) => (
                  <li key={row.observation_id} style={{ marginBottom: 8 }}>
                    <div className="row wrap" style={{ gap: 6 }}>
                      {row.tier ? <Badge tone={row.decision === "FEED" ? "ok" : "warn"}>{row.tier}</Badge> : null}
                      <a href={row.source_url || undefined} target="_blank" rel="noreferrer noopener">
                        {row.title}
                      </a>
                    </div>
                    <div className="small muted">
                      {row.source} · {row.published_at || row.event_at || ""}
                      {row.first_observed_at ? " · " + row.first_observed_at.slice(0, 10) : ""}
                    </div>
                  </li>
                ))}
              </ul>
            </Card>

            <div className="grid two" style={{ display: "grid", gap: 12, gridTemplateColumns: "1fr 1fr" }}>
              <Card title={bi("Topics", "技术主题")}>
                <ul style={{ margin: 0, paddingLeft: 18 }}>
                  {payload.topics.map((row) => (
                    <li key={row.topic_id}>{row.topic_id} <span className="small muted">({row.n})</span></li>
                  ))}
                </ul>
              </Card>
              <Card title={bi("Products", "产品")}>
                <ul style={{ margin: 0, paddingLeft: 18 }}>
                  {payload.products.map((row) => (
                    <li key={row.product_key} className="small">
                      {row.product_key.split(":")[0]} <span className="muted">({row.n})</span>
                    </li>
                  ))}
                </ul>
              </Card>
            </div>
            <p className="small muted">
              <Link to="/radar/companies">{bi("All companies", "所有公司")}</Link>
            </p>
          </>
        )}
      </AsyncSection>
    </>
  );
}