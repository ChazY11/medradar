import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { searchOrganizations } from "../api/client";
import { useDebounced } from "../api/hooks";
import { useI18n } from "../i18n";
import type { SearchResponse } from "../api/types";

export function GlobalSearch() {
  const { t } = useI18n();
  const navigate = useNavigate();
  const inputRef = useRef<HTMLInputElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);
  const [payload, setPayload] = useState<SearchResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [cursor, setCursor] = useState(0);
  const debounced = useDebounced(query, 180);

  useEffect(() => {
    const handler = (event: KeyboardEvent) => {
      if (event.key === "/" && !isEditable(event.target)) {
        event.preventDefault();
        inputRef.current?.focus();
        setOpen(true);
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, []);

  useEffect(() => {
    const handler = (event: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  useEffect(() => {
    const text = debounced.trim();
    if (text.length < 1) {
      setPayload(null);
      setError(null);
      setLoading(false);
      return;
    }
    let cancelled = false;
    setLoading(true);
    searchOrganizations(text, 8)
      .then((data) => {
        if (cancelled) return;
        setPayload(data);
        setError(null);
        setCursor(0);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setError(err instanceof Error ? err.message : String(err));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [debounced]);

  const results = payload?.results ?? [];
  const applicants = payload?.applicant_matches ?? [];

  const flat = useMemo(() => results.map((row) => row.key), [results]);

  const go = (key: string) => {
    setOpen(false);
    setQuery("");
    navigate("/organizations/" + key);
  };

  return (
    <div className="search" ref={containerRef}>
      <input
        ref={inputRef}
        id="global-search"
        type="search"
        value={query}
        aria-label={t("search.placeholder")}
        placeholder={t("search.placeholder")}
        autoComplete="off"
        spellCheck={false}
        onFocus={() => setOpen(true)}
        onChange={(event) => {
          setQuery(event.target.value);
          setOpen(true);
        }}
        onKeyDown={(event) => {
          if (event.key === "Escape") {
            setOpen(false);
            inputRef.current?.blur();
          } else if (event.key === "ArrowDown") {
            event.preventDefault();
            setCursor((value) => Math.min(flat.length - 1, value + 1));
          } else if (event.key === "ArrowUp") {
            event.preventDefault();
            setCursor((value) => Math.max(0, value - 1));
          } else if (event.key === "Enter" && flat.length) {
            event.preventDefault();
            go(flat[Math.min(cursor, flat.length - 1)]);
          }
        }}
      />
      <span className="search-hint" aria-hidden="true">
        /
      </span>

      {open && debounced.trim().length > 0 ? (
        <div className="search-pop" role="listbox" aria-label={t("search.placeholder")}>
          {loading && !payload ? <div className="search-empty">{t("search.loading")}...</div> : null}
          {error ? <div className="search-empty">{t("search.error")}: {error}</div> : null}
          {!loading && !error && payload && !results.length && !applicants.length ? (
            <div className="search-empty">
              <div className="strong">{t("search.noResults")}</div>
              <div className="mt-8">{t("search.noResultsHelp")}</div>
            </div>
          ) : null}
          {results.length ? <div className="search-pop-group">{t("search.organizations")}</div> : null}
          {results.map((row, index) => (
            <Link
              key={row.key}
              to={"/organizations/" + row.key}
              className="search-item"
              role="option"
              aria-selected={cursor === index}
              onMouseEnter={() => setCursor(index)}
              onClick={() => {
                setOpen(false);
                setQuery("");
              }}
            >
              <span className="title">{row.display_name}</span>
              <span className="small muted truncate">
                {row.legal_name && row.legal_name !== row.display_name ? row.legal_name : ""}
                {row.ticker ? " - " + row.ticker : ""}
              </span>
              <span className="meta">
                {row.event_count.toLocaleString()} {t("common.records")}
              </span>
            </Link>
          ))}
          {applicants.length ? <div className="search-pop-group">{t("search.applicants")}</div> : null}
          {applicants.map((row) => (
            <div className="search-item muted" key={row.applicant_name}>
              <span className="mono small truncate">{row.applicant_name}</span>
              <span className="meta">{row.record_count.toLocaleString()}</span>
            </div>
          ))}
          {payload ? (
            <div className="search-empty tiny muted" style={{ borderTop: "1px solid var(--border)", marginTop: 4 }}>
              {payload.coverage.note}
            </div>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}

function isEditable(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  const tag = target.tagName;
  return tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT" || target.isContentEditable;
}
