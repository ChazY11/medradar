import type { ReactNode } from "react";
import { useI18n } from "../i18n";

export interface Column<T> {
  key: string;
  header: ReactNode;
  render: (row: T) => ReactNode;
  align?: "left" | "right";
  mono?: boolean;
  sortKey?: string;
  width?: number | string;
  hideOnMobile?: boolean;
}

export function DataTable<T>({
  columns,
  rows,
  rowKey,
  onRowClick,
  caption,
  empty,
}: {
  columns: Column<T>[];
  rows: T[];
  rowKey: (row: T) => string;
  onRowClick?: (row: T) => void;
  caption?: string;
  empty?: ReactNode;
}) {
  if (!rows.length) return <>{empty ?? null}</>;
  return (
    <div className="table-wrap">
      <table className="data">
        {caption ? <caption className="sr-only">{caption}</caption> : null}
        <thead>
          <tr>
            {columns.map((column) => (
              <th
                key={column.key}
                className={column.align === "right" ? "num" : undefined}
                style={{ width: column.width }}
                scope="col"
              >
                {column.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr
              key={rowKey(row)}
              className={onRowClick ? "clickable" : undefined}
              onClick={onRowClick ? () => onRowClick(row) : undefined}
              tabIndex={onRowClick ? 0 : undefined}
              onKeyDown={
                onRowClick
                  ? (event) => {
                      if (event.key === "Enter" || event.key === " ") {
                        event.preventDefault();
                        onRowClick(row);
                      }
                    }
                  : undefined
              }
            >
              {columns.map((column) => (
                <td
                  key={column.key}
                  className={[column.align === "right" ? "num" : "", column.mono ? "mono" : ""].join(" ").trim() || undefined}
                >
                  {column.render(row)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function SimpleTable<T>({
  columns,
  rows,
  rowKey,
  empty,
}: {
  columns: { key: string; header: ReactNode; align?: "left" | "right"; render: (row: T) => ReactNode }[];
  rows: T[];
  rowKey: (row: T) => string;
  empty?: ReactNode;
}) {
  const { t } = useI18n();
  if (!rows.length) return <div className="empty-inline">{empty ?? t("state.empty")}</div>;
  return (
    <DataTable
      columns={columns.map((column) => ({ ...column, align: column.align }))}
      rows={rows}
      rowKey={rowKey}
    />
  );
}
