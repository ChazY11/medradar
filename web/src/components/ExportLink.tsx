import type { ReactNode } from "react";

export function ExportLink({ href, children, title }: { href: string; children: ReactNode; title?: string }) {
  return (
    <a className="btn" href={href} title={title}>
      <span aria-hidden="true" style={{ fontFamily: "var(--mono)", fontSize: 11 }}>
        {"\u2193"}
      </span>
      {children}
    </a>
  );
}
