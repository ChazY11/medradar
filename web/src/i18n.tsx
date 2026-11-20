import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

export type Lang = "en" | "zh";

const STORAGE_KEY = "medradar.lang";

const en = {
  "app.subtitle": "Medical Technology Intelligence",
  "nav.brief": "Brief",
  "nav.overview": "Overview",
  "nav.organizations": "Organizations",
  "nav.events": "Events",
  "nav.compare": "Compare",
  "nav.sources": "Sources",
  "nav.dataStatus": "Data status",
  "nav.devices": "Devices",
  "nav.review": "Review",
  "nav.radar": "Live radar",
  "nav.technologyMap": "Technology map",
  "nav.companies": "Companies",
  "nav.reviewQueue": "Review queue",
  "nav.primary": "Primary navigation",
  "nav.menu": "Menu",
  "search.placeholder": "Search organizations, tickers, applicant names",
  "search.hint": "Press / to search",
  "search.organizations": "Tracked organizations",
  "search.applicants": "Applicant names not attributed to a tracked organization",
  "search.noResults": "No tracked organization matches this query.",
  "search.noResultsHelp": "Search covers the tracked organizations in this snapshot. Unattributed applicant names appear above and are not companies in this product.",
  "search.loading": "Searching",
  "search.error": "Search failed",
  "snapshot.label": "Snapshot",
  "snapshot.unknown": "unknown",
  "snapshot.fresh": "fresh",
  "snapshot.stale": "stale",
  "snapshot.labelTitle": "Data snapshot",
  "state.loading": "Loading",
  "state.retry": "Retry",
  "state.error": "Something went wrong",
  "state.empty": "Nothing to show",
  "state.notAvailable": "Not available",
  "state.none": "None",
  "lang.toggle": "中文",
  "lang.toggleLabel": "Switch interface language",
  "common.records": "records",
  "common.record": "record",
  "common.eventDate": "Event date",
  "common.firstObserved": "First observed by MedRadar",
  "common.publishedAt": "Published by source",
  "common.availableAt": "Available at",
  "common.officialId": "Official ID",
  "common.type": "Type",
  "common.organization": "Organization",
  "common.category": "Category",
  "common.deviceClass": "Device class",
  "common.source": "Source",
  "common.evidence": "Evidence",
  "common.review": "Attribution review",
  "common.actions": "Actions",
  "common.export": "Export",
  "common.compare": "Compare",
  "common.filters": "Filters",
  "common.reset": "Reset",
  "common.from": "From",
  "common.to": "To",
  "common.all": "All",
  "common.page": "Page",
  "common.of": "of",
  "common.noData": "No data",
  "common.unknown": "Unknown",
  "common.notAvailableShort": "-",
  "common.pendingReview": "Attribution pending review",
  "common.curated": "Curated attribution",
  "common.device": "Device",
  "common.applicant": "Applicant",
  "common.year": "Year",
  "common.total": "Total",
  "common.share": "Share",
  "common.note": "Note",
  "common.methodology": "Methodology",
  "common.sources": "Sources",
  "common.coverage": "Coverage",
  "common.localTime": "Local time",
  "common.copy": "Copy",
  "common.openRecord": "Open official record",
  "common.close": "Close",
  "type.510k": "510(k)",
  "type.pma": "PMA",
  "type.pma_supplement": "PMA supplement",
  "type.recall": "Recall",
  "type.unclassified": "Unclassified",
  "type.unknown": "Unknown type",
  "review.curated": "Curated",
  "review.pending_review": "Pending review",
  "review.rejected": "Rejected",
  "time.date_from_source": "Date from source",
  "time.date_derived_from_source": "Date derived from source",
  "time.unknown": "No usable date",
  "overview.title": "Medical technology intelligence workbench",
  "overview.desc":
    "Traceable FDA regulatory records for the medical technology companies you track: what each company filed, when it happened, how it was attributed, and where the official record is.",
  "overview.coverage": "Snapshot coverage",
  "overview.startHere": "Start here",
  "overview.featured": "Featured organizations",
  "overview.latest": "Latest observed records",
  "overview.methodology": "How to read this data",
  "orgs.title": "Tracked organizations",
  "orgs.desc": "Organizations covered by this snapshot. Attribution review state is shown for every organization.",
  "orgs.search": "Filter organizations",
  "org.title": "Organization",
  "org.tab.overview": "Overview",
  "org.tab.events": "Regulatory events",
  "org.tab.attribution": "Attribution",
  "events.title": "Regulatory event browser",
  "events.desc": "Every attributed record in the snapshot. Filter by organization, event type, date, category or attribution state, then open any record's official evidence.",
  "compare.title": "Compare organizations",
  "compare.desc": "Side-by-side regulatory activity over one complete-year window. Coverage differences and counting limits are stated above every comparison.",
  "sources.title": "Sources, coverage and limits",
  "sources.desc": "What this snapshot contains, what it does not, how records were collected and attributed, and which questions this data cannot answer.",
  "dataStatus.title": "Data synchronization",
  "dataStatus.desc": "Which FDA sources are monitored, when they were last checked, which official version the active snapshot represents, and what changed at the last publication. Discovery time is never used as a regulatory event date.",
} as const;

const zh: Record<keyof typeof en, string> = {
  "app.subtitle": "医疗技术情报",
  "nav.brief": "简报",
  "nav.overview": "总览",
  "nav.organizations": "企业",
  "nav.events": "监管事件",
  "nav.compare": "企业对比",
  "nav.sources": "数据来源",
  "nav.dataStatus": "数据同步",
  "nav.devices": "医疗器械",
  "nav.review": "身份复核",
  "nav.radar": "实时雷达",
  "nav.technologyMap": "科技地图",
  "nav.companies": "公司",
  "nav.reviewQueue": "评审队列",
  "nav.primary": "主导航",
  "nav.menu": "菜单",
  "search.placeholder": "搜索企业、股票代码、申请人名称",
  "search.hint": "按 / 开始搜索",
  "search.organizations": "已收录企业",
  "search.applicants": "未归属到收录企业的申请人名称",
  "search.noResults": "没有匹配的收录企业。",
  "search.noResultsHelp": "搜索范围为本快照收录的企业；上方列出的未归属申请人名称不是本产品中的企业实体。",
  "search.loading": "搜索中",
  "search.error": "搜索失败",
  "snapshot.label": "数据快照",
  "snapshot.unknown": "未知",
  "snapshot.fresh": "较新",
  "snapshot.stale": "已过期",
  "snapshot.labelTitle": "数据快照",
  "state.loading": "加载中",
  "state.retry": "重试",
  "state.error": "出错了",
  "state.empty": "暂无内容",
  "state.notAvailable": "不可用",
  "state.none": "无",
  "lang.toggle": "EN",
  "lang.toggleLabel": "切换界面语言",
  "common.records": "条记录",
  "common.record": "条记录",
  "common.eventDate": "事件日期",
  "common.firstObserved": "MedRadar 首次采集",
  "common.publishedAt": "来源公开时间",
  "common.availableAt": "可用于分析的时间",
  "common.officialId": "官方标识",
  "common.type": "类型",
  "common.organization": "企业",
  "common.category": "类别",
  "common.deviceClass": "器械等级",
  "common.source": "来源",
  "common.evidence": "证据",
  "common.review": "归属复核",
  "common.actions": "操作",
  "common.export": "导出",
  "common.compare": "对比",
  "common.filters": "筛选",
  "common.reset": "重置",
  "common.from": "起始",
  "common.to": "截止",
  "common.all": "全部",
  "common.page": "第",
  "common.of": "页，共",
  "common.noData": "无数据",
  "common.unknown": "未知",
  "common.notAvailableShort": "-",
  "common.pendingReview": "归属待人工复核",
  "common.curated": "已复核归属",
  "common.device": "器械",
  "common.applicant": "申请人",
  "common.year": "年份",
  "common.total": "合计",
  "common.share": "占比",
  "common.note": "说明",
  "common.methodology": "方法",
  "common.sources": "来源",
  "common.coverage": "覆盖",
  "common.localTime": "本地时间",
  "common.copy": "复制",
  "common.openRecord": "打开官方记录",
  "common.close": "关闭",
  "type.510k": "510(k)",
  "type.pma": "PMA",
  "type.pma_supplement": "PMA 补充批准",
  "type.recall": "召回",
  "type.unclassified": "未分类",
  "type.unknown": "未知类型",
  "review.curated": "已复核",
  "review.pending_review": "待复核",
  "review.rejected": "已排除",
  "time.date_from_source": "来源明确日期",
  "time.date_derived_from_source": "由来源推出日期",
  "time.unknown": "无可用日期",
  "overview.title": "医疗技术情报工作台",
  "overview.desc": "以可追溯的 FDA 监管记录回答：目标企业申报了什么、事件发生在何时、记录如何归属、官方原始记录在哪里。",
  "overview.coverage": "快照覆盖",
  "overview.startHere": "从这里开始",
  "overview.featured": "重点企业",
  "overview.latest": "最新采集记录",
  "overview.methodology": "如何阅读这些数据",
  "orgs.title": "收录企业",
  "orgs.desc": "本快照覆盖的企业。每家企业的归属复核状态都会显示。",
  "orgs.search": "筛选企业",
  "org.title": "企业",
  "org.tab.overview": "概览",
  "org.tab.events": "监管事件",
  "org.tab.attribution": "归属详情",
  "events.title": "监管事件浏览器",
  "events.desc": "快照中全部已归属记录。按企业、事件类型、日期、类别或归属状态筛选，并打开任意记录的官方证据。",
  "compare.title": "企业对比",
  "compare.desc": "在同一个完整年度窗口内并列比较监管活动。所有对比都会先说明覆盖差异与统计口径。",
  "sources.title": "数据来源、覆盖与限制",
  "sources.desc": "本快照包含什么、不包含什么、记录如何采集与归属，以及这批数据无法回答哪些问题。",
  "dataStatus.title": "数据同步",
  "dataStatus.desc": "哪些 FDA 数据源正在被监控、上次检查时间、当前快照对应的官方版本，以及上次发布发现了什么变化。发现时间绝不会被当作监管事件日期。",
};

type Dict = typeof en;
export type TranslationKey = keyof Dict;

interface I18nContextValue {
  lang: Lang;
  setLang: (lang: Lang) => void;
  t: (key: TranslationKey) => string;
  bi: (english: string, chinese: string) => string;
}

const I18nContext = createContext<I18nContextValue | null>(null);

function readInitialLang(): Lang {
  if (typeof window === "undefined") return "zh";
  const stored = window.localStorage.getItem(STORAGE_KEY);
  if (stored === "zh" || stored === "en") return stored;
  // First launch defaults to Chinese: the first users of this alpha are Chinese medical-device
  // R&D leads. An explicit toggle choice is always remembered, and an English-locale browser is
  // still allowed to fall back to English.
  const preferred = (window.navigator.language || "").toLowerCase();
  return preferred.startsWith("en") ? "en" : "zh";
}

export function I18nProvider({ children }: { children: ReactNode }) {
  const [lang, setLangState] = useState<Lang>(readInitialLang);

  useEffect(() => {
    window.localStorage.setItem(STORAGE_KEY, lang);
    document.documentElement.lang = lang === "zh" ? "zh-CN" : "en";
  }, [lang]);

  const setLang = useCallback((next: Lang) => setLangState(next), []);

  const value = useMemo<I18nContextValue>(() => {
    const dictionary: Dict = en;
    const localised: Record<TranslationKey, string> = lang === "zh" ? { ...dictionary, ...zh } : dictionary;
    return {
      lang,
      setLang,
      t: (key: TranslationKey) => localised[key] ?? dictionary[key] ?? String(key),
      bi: (english: string, chinese: string) => (lang === "zh" ? chinese : english),
    };
  }, [lang, setLang]);

  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}

export function useI18n(): I18nContextValue {
  const value = useContext(I18nContext);
  if (!value) throw new Error("useI18n must be used inside I18nProvider");
  return value;
}
