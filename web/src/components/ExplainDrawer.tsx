import { useAsync } from "../api/hooks";
import { getExplain, type ExplainQuery } from "../api/client";
import type { ExplainResponse } from "../api/types";
import { useI18n } from "../i18n";
import { fmtDate, fmtNumber, pickText, typeLabel } from "../lib/brief";
import { ErrorState, LoadingBlock } from "./ui";

interface ExplainDrawerProps {
  query: ExplainQuery;
  onClose: () => void;
}

export function ExplainDrawer({ query, onClose }: ExplainDrawerProps) {
  const { lang } = useI18n();
  const explain = useAsync(() => getExplain(query), [JSON.stringify(query)]);

  return (
    <>
      <div className="drawer-scrim" onClick={onClose} aria-hidden="true" />
      <aside className="drawer" role="dialog" aria-modal="true" aria-label={pickText(explain.data?.label ?? null, lang) || "Explain this difference"}>
        <div className="drawer-head">
          <div>
            <div className="eyebrow">{lang === "zh" ? "解释这一差异" : "Explain this difference"}</div>
            <div className="card-title" style={{ marginTop: 4 }}>
              {explain.data ? pickText(explain.data.label, lang) : lang === "zh" ? "载入中" : "Loading"}
            </div>
          </div>
          <button type="button" className="btn sm" onClick={onClose} aria-label={lang === "zh" ? "关闭" : "Close"}>
            ×
          </button>
        </div>
        <div className="drawer-body">
          {explain.status === "error" && explain.error ? (
            <ErrorState message={explain.error.message} onRetry={explain.reload} />
          ) : !explain.data ? (
            <LoadingBlock lines={6} />
          ) : (
            <ExplainBody data={explain.data} lang={lang} />
          )}
        </div>
      </aside>
    </>
  );
}

function ExplainBody({ data, lang }: { data: ExplainResponse; lang: "en" | "zh" }) {
  const { t } = useI18n();
  return (
    <>
      <section className="drawer-section">
        <h3>{lang === "zh" ? "指标定义" : "Definition"}</h3>
        <p className="state-desc">{pickText(data.definition, lang)}</p>
      </section>

      <section className="drawer-section">
        <h3>{lang === "zh" ? "统计范围" : "Scope"}</h3>
        <dl className="kv">
          <dt>{lang === "zh" ? "时间窗口" : "Window"}</dt>
          <dd>
            {data.scope.from} → {data.scope.to}
          </dd>
          <dt>{lang === "zh" ? "事件类型" : "Event types"}</dt>
          <dd>{data.event_types.map((type) => typeLabel(type, lang)).join(", ")}</dd>
          {data.filters.category ? (
            <>
              <dt>{lang === "zh" ? "类别筛选" : "Category filter"}</dt>
              <dd className="mono">{data.filters.category}</dd>
            </>
          ) : null}
          {data.filters.product_code ? (
            <>
              <dt>{lang === "zh" ? "产品代码筛选" : "Product-code filter"}</dt>
              <dd className="mono">{data.filters.product_code}</dd>
            </>
          ) : null}
          <dt>{lang === "zh" ? "归属口径" : "Ownership basis"}</dt>
          <dd className="mono">{data.filters.ownership_basis}</dd>
          <dt>{lang === "zh" ? "复核筛选" : "Review filter"}</dt>
          <dd className="mono">{data.filters.review_filter}</dd>
          <dt>{lang === "zh" ? "分母" : "Denominator"}</dt>
          <dd>
            {pickText(data.denominator.label, lang)}: <b className="num">{fmtNumber(data.denominator.value)}</b>
          </dd>
        </dl>
      </section>

      {data.sides.map((side) => (
        <section className="drawer-section" key={side.key}>
          <h3>
            {side.name} — <span className="num">{fmtNumber(side.count)}</span> {t("common.records")}
          </h3>
          <div className="row wrap" style={{ gap: 8, marginBottom: 8 }}>
            <a className="btn sm" href={side.drilldown}>
              {lang === "zh" ? "在事件浏览器中打开同一筛选" : "Open the same filter in the event browser"}
            </a>
          </div>
          {side.records.length ? (
            <div className="table-wrap">
              <table className="data">
                <thead>
                  <tr>
                    <th>{lang === "zh" ? "事件日期" : "Event date"}</th>
                    <th>{lang === "zh" ? "官方标识" : "Official ID"}</th>
                    <th>{lang === "zh" ? "类型" : "Type"}</th>
                    <th>{lang === "zh" ? "器械 / 申请人" : "Device / applicant"}</th>
                    <th>{lang === "zh" ? "核验" : "Verification"}</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {side.records.map((record) => (
                    <tr key={record.event_id}>
                      <td>{fmtDate(record.event_date)}</td>
                      <td className="mono">{record.official_id}</td>
                      <td>{typeLabel(record.event_type, lang)}</td>
                      <td>
                        <div className="cell-primary">{record.device_name || record.official_id}</div>
                        <div className="cell-sub">{record.applicant_name}</div>
                      </td>
                      <td>{lang === "zh" ? record.verification_label_zh : record.verification_label_en}</td>
                      <td>
                        {record.official_url ? (
                          <a className="link small" href={record.official_url} target="_blank" rel="noreferrer">
                            {lang === "zh" ? "官方记录" : "Official record"}
                          </a>
                        ) : null}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="empty-inline">{lang === "zh" ? "该侧在此筛选下没有记录。" : "No records on this side under this filter."}</div>
          )}
          {side.records.length ? (
            <div className="small muted" style={{ marginTop: 6 }}>
              {lang === "zh"
                ? `显示最近 ${side.records.length} 条；完整集合请使用上方链接。`
                : `Showing the latest ${side.records.length}; use the link above for the complete set.`}
            </div>
          ) : null}
        </section>
      ))}

      <div className="callout">{pickText(data.note, lang)}</div>
    </>
  );
}
