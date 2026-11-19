import { useAsync } from "../api/hooks";
import { getRadarDigest, type DigestItem, type RadarDigest } from "../api/radar";
import { useI18n } from "../i18n";
import { AsyncSection } from "./async";
import { Badge, Card, formatNumber } from "./ui";

/** Category labels the digest can name. An unknown category falls back to its raw key. */
const CATEGORY_ZH: Record<string, string> = {
  methods_benchmark_on_monitoring_data: "基于监护数据的方法学对比",
  measurement_without_technology_focus: "只做测量，未研究监护技术",
  security_architecture: "安全/架构类，与监护设备无关",
  monitoring_technology_evaluation: "监护设备/算法性能研究",
  monitoring_technology_review: "监护技术综述",
  measurement_without_technology_focus_transfer: "测量文献，可迁移性待判断",
  device_or_algorithm_needs_confirmation: "设备或算法线索，待确认",
  plausible_monitoring_technology: "可能相关，待确认",
  regulatory_record: "监管记录（FDA）",
};

function Meta({ item }: { item: DigestItem }) {
  const { bi } = useI18n();
  const parts: string[] = [];
  if (item.source) parts.push(item.source);
  const stated = item.published_at ?? item.event_at;
  if (stated) parts.push(bi(`stated ${stated}`, `来源日期 ${stated}`));
  if (item.relevance) {
    parts.push(item.relevance === "DIRECT" ? bi("directly relevant", "直接相关") : item.relevance);
  }
  if (item.duplicates > 1) parts.push(bi(`${item.duplicates} records merged`, `已合并 ${item.duplicates} 条`));
  return <span className="small muted">{parts.join(" · ")}</span>;
}

function ItemRow({ item, index }: { item: DigestItem; index: number }) {
  const { bi } = useI18n();
  return (
    <li style={{ marginBottom: 8, minWidth: 0 }}>
      <div className="row" style={{ gap: 8, alignItems: "baseline", minWidth: 0 }}>
        <span className="small muted" style={{ minWidth: 16 }}>{index}.</span>
        <a
          href={item.source_url ?? undefined}
          target="_blank"
          rel="noreferrer noopener"
          style={{ minWidth: 0, overflowWrap: "anywhere" }}
        >
          {item.title ?? item.observation_id}
        </a>
        {item.future_dated ? <Badge tone="warn">{bi("future date", "日期在未来")}</Badge> : null}
      </div>
      <div style={{ marginLeft: 24, minWidth: 0, overflowWrap: "anywhere" }}>
        <Meta item={item} />
      </div>
    </li>
  );
}

export function DailyDigest() {
  const { bi } = useI18n();
  const digest = useAsync<RadarDigest>(() => getRadarDigest(24, 5), []);

  return (
    <Card
      title={bi("Today", "今日摘要")}
      note={bi(
        "Everything that arrived in the last 24 hours, ranked by the admission decision rather than listed. A quiet day says so.",
        "过去 24 小时新记录的一句话总结。按准入判定排序，不是流水账；没有东西就直说没有。",
      )}
    >
      <AsyncSection status={digest.status} data={digest.data} error={digest.error} reload={digest.reload} loadingLines={3}>
        {(payload) => <DigestBody payload={payload} />}
      </AsyncSection>
    </Card>
  );
}

function DigestBody({ payload }: { payload: RadarDigest }) {
  const { bi } = useI18n();
  const totals = payload.totals;
  const warnings = payload.warnings ?? [];
  const futureWarning = warnings.find((warning) => warning.code === "future_dated");
  const duplicateWarning = warnings.find((warning) => warning.code === "near_duplicates");
  const blockedWarning = warnings.find((warning) => warning.code === "blocked_sources");

  if (payload.empty || totals.arrived === 0) {
    return (
      <p className="small">
        {bi(
          "Nothing new was recorded in the last 24 hours. That is a statement about collection, not about the industry: no source reported a new or updated record.",
          "过去 24 小时没有新记录。这是关于采集的事实，不是关于行业的结论：所有来源都没有报告新的或更新的记录。",
        )}
      </p>
    );
  }

  return (
    <>
      <p style={{ marginTop: 0 }}>
        {bi(
          `${formatNumber(totals.arrived)} record(s) arrived; ${formatNumber(totals.feed)} are worth your attention and ${formatNumber(totals.excluded)} were excluded as unrelated to monitoring technology.`,
          `过去 24 小时新增 ${formatNumber(totals.arrived)} 条，其中 ${formatNumber(totals.feed)} 条值得看，${formatNumber(totals.excluded)} 条被判为与监护技术无关。`,
        )}
      </p>

      {payload.items.length > 0 ? (
        <>
          <h3 className="h4">{bi("Worth a look", "值得看")}</h3>
          <ol style={{ listStyle: "none", paddingLeft: 0, margin: 0 }}>
            {payload.items.map((item, index) => (
              <ItemRow key={item.observation_id} item={item} index={index + 1} />
            ))}
          </ol>
        </>
      ) : (
        <p className="small muted">
          {bi(
            "Nothing reached the feed today. Every record that arrived was judged out of scope.",
            "今天没有记录进入情报流；到货的记录都被判为不在范围内。",
          )}
        </p>
      )}

      <h3 className="h4">{bi("Safety and recalls", "安全与召回")}</h3>
      {payload.safety.length > 0 ? (
        <ol style={{ listStyle: "none", paddingLeft: 0, margin: 0 }}>
          {payload.safety.map((item, index) => (
            <ItemRow key={item.observation_id} item={item} index={index + 1} />
          ))}
        </ol>
      ) : (
        <p className="small muted">
          {bi(
            "No new recall or safety notice today. The recall channel ran and reported no new records.",
            "今天没有新的召回或安全通报。召回通道正常运行，未报告新记录。",
          )}
        </p>
      )}

      {payload.review.count > 0 ? (
        <>
          <h3 className="h4">{bi("Waiting for your judgement", "等你确认")}</h3>
          <p className="small" style={{ marginTop: 0 }}>
            {bi(
              `${payload.review.count} record(s) sit between the feed and the bin: `,
              `${payload.review.count} 条记录处在「进情报流」和「丢掉」之间：`,
            )}
            {payload.review.categories
              .map((entry) => `${bi(entry.category, CATEGORY_ZH[entry.category] ?? entry.category)} ${entry.count}`)
              .join(" · ")}
          </p>
        </>
      ) : null}

      {futureWarning || duplicateWarning || blockedWarning ? (
        <p className="small muted" style={{ marginBottom: 0 }}>
          {futureWarning
            ? bi(
                `${futureWarning.count} visible record(s) state a publication date more than a week ahead; they are sorted last and marked, because they are not news from today.`,
                `有 ${futureWarning.count} 条可见记录的来源日期在未来一周以上，已排在最后并标记——它们不是今天的新闻。`,
              )
            : null}{" "}
          {duplicateWarning
            ? bi(
                `${duplicateWarning.count} near-duplicate record(s) were merged into one line.`,
                `已合并 ${duplicateWarning.count} 条近重复记录。`,
              )
            : null}{" "}
          {blockedWarning
            ? bi(
                `Blocked by policy, not failing: ${(blockedWarning.sources ?? []).join(", ")}.`,
                `被策略封禁（不是故障）：${(blockedWarning.sources ?? []).join("、")}。`,
              )
            : null}
        </p>
      ) : null}
    </>
  );
}