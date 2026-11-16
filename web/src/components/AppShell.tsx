import { useEffect, useState, type ReactNode } from "react";
import { Link, NavLink } from "react-router-dom";
import { getMeta } from "../api/client";
import { useAsync } from "../api/hooks";
import { useI18n, type TranslationKey } from "../i18n";
import { GlobalSearch } from "./GlobalSearch";

interface NavItem {
  to: string;
  labelKey: TranslationKey;
  end?: boolean;
}

const NAV_ITEMS: NavItem[] = [
  { to: "/brief", labelKey: "nav.brief" },
  { to: "/", labelKey: "nav.overview", end: true },
  { to: "/organizations", labelKey: "nav.organizations" },
  { to: "/events", labelKey: "nav.events" },
  { to: "/compare", labelKey: "nav.compare" },
  { to: "/sources", labelKey: "nav.sources" },
  { to: "/data-status", labelKey: "nav.dataStatus" },
  { to: "/devices", labelKey: "nav.devices" },
  { to: "/review", labelKey: "nav.review" },
];

export function AppShell({ children }: { children: ReactNode }) {
  const { lang, setLang, t } = useI18n();
  const [navOpen, setNavOpen] = useState(false);
  const meta = useAsync(() => getMeta(), []);

  useEffect(() => {
    setNavOpen(false);
  }, [children]);

  const navLinks = NAV_ITEMS.map((item) => (
    <NavLink
      key={item.to}
      to={item.to}
      end={item.end}
      className={({ isActive }) => (isActive ? "active" : undefined)}
      onClick={() => setNavOpen(false)}
    >
      {t(item.labelKey)}
    </NavLink>
  ));

  const snapshot = meta.data?.snapshot;
  const freshness = meta.data?.freshness;
  const collected = snapshot?.collected_at ? snapshot.collected_at.slice(0, 10) : t("snapshot.unknown");
  const dotClass = freshness?.state === "stale" ? "dot warn" : freshness?.state === "fresh" ? "dot" : "dot";

  return (
    <>
      <a className="sr-only" href="#main">
        Skip to content
      </a>
      <header className="app-bar">
        <Link to="/" className="brand" aria-label="MedRadar home">
          <span className="brand-name">MedRadar</span>
          <span className="brand-subtitle">{t("app.subtitle")}</span>
        </Link>

        <nav className="nav" aria-label={t("nav.primary")}>
          {navLinks}
        </nav>

        <button
          type="button"
          className="nav-toggle"
          aria-expanded={navOpen}
          aria-controls="mobile-nav"
          onClick={() => setNavOpen((open) => !open)}
        >
          {navOpen ? "x" : t("nav.menu")}
        </button>

        <GlobalSearch />

        <span
          className="snapshot-chip"
          title={
            snapshot
              ? "Snapshot " + snapshot.id + ", collected " + snapshot.collected_at + ". Source last updated: " + (snapshot.openfda_last_updated ?? "unknown") + "."
              : t("snapshot.labelTitle")
          }
        >
          <span className={dotClass} aria-hidden="true" />
          {t("snapshot.label")}: {collected}
          {freshness?.state === "stale" ? " (" + t("snapshot.stale") + ")" : ""}
        </span>

        <button
          type="button"
          className="lang-toggle"
          onClick={() => setLang(lang === "en" ? "zh" : "en")}
          aria-label={t("lang.toggleLabel")}
        >
          {t("lang.toggle")}
        </button>
      </header>

      {navOpen ? (
        <nav id="mobile-nav" className="nav-panel" aria-label={t("nav.primary")}>
          {navLinks}
          <button
            type="button"
            className="nav-lang"
            onClick={() => setLang(lang === "en" ? "zh" : "en")}
            aria-label={t("lang.toggleLabel")}
          >
            {lang === "en" ? "中文" : "English"}
          </button>
        </nav>
      ) : null}

      <main className="shell" id="main">
        {children}
      </main>
    </>
  );
}
