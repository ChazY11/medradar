import { Link } from "react-router-dom";
import { useAsync } from "../api/hooks";
import { getCompanies } from "../api/human";
import { useI18n } from "../i18n";
import { Card, EmptyState, PageHeader, formatNumber } from "../components/ui";
import { AsyncSection } from "../components/async";

/** The unit a reader actually thinks in: the company, not the document. */
export function CompaniesPage() {
  const { bi } = useI18n();
  const companies = useAsync(() => getCompanies(), []);

  return (
    <>
      <PageHeader
        eyebrow={bi("Company technology", "公司技术")}
        title={bi("Companies", "公司")}
        description={bi(
          "Every company the taxonomy tracks, with how much evidence the ledger holds for it. Open one to see what changed, not just how many rows exist.",
          "税则里跟踪的每家公司，以及账本里为它积累了多少证据。点开一家看到的是「最近发生了什么」，而不是「有几行数据」。",
        )}
      />
      <Card title={bi("Tracked companies", "受跟踪公司")}>
        <AsyncSection status={companies.status} data={companies.data} error={companies.error} reload={companies.reload}>
          {(payload) =>
            payload.items.length === 0 ? (
              <EmptyState title={bi("No company has evidence yet", "还没有公司有证据")} />
            ) : (
              <table className="table">
                <thead>
                  <tr>
                    <th>{bi("Company", "公司")}</th>
                    <th>{bi("Country", "国家")}</th>
                    <th style={{ textAlign: "right" }}>{bi("Records", "记录")}</th>
                    <th style={{ textAlign: "right" }}>{bi("Recalls", "召回")}</th>
                    <th>{bi("Newest", "最新")}</th>
                  </tr>
                </thead>
                <tbody>
                  {payload.items.map((row) => (
                    <tr key={row.organization_id}>
                      <td>
                        <Link to={"/radar/companies/" + row.organization_id}>
                          {bi(row.display_name, row.label_zh || row.display_name)}
                        </Link>
                      </td>
                      <td className="small muted">{row.country || "-"}</td>
                      <td style={{ textAlign: "right" }}>{formatNumber(row.observations)}</td>
                      <td style={{ textAlign: "right" }}>{formatNumber(row.recalls)}</td>
                      <td className="small muted">{row.newest_observation_at?.slice(0, 10) || "-"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
        </AsyncSection>
      </Card>
    </>
  );
}