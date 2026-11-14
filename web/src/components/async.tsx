import type { ReactNode } from "react";
import { ErrorState, LoadingBlock } from "./ui";
import type { ApiError } from "../api/client";

export function AsyncSection<T>({
  status,
  data,
  error,
  reload,
  children,
  loadingLines = 4,
  loadingHeight,
}: {
  status: "loading" | "error" | "ready";
  data: T | null;
  error: ApiError | null;
  reload: () => void;
  children: (data: T) => ReactNode;
  loadingLines?: number;
  loadingHeight?: number;
}) {
  if (status === "error" && error) {
    return <ErrorState message={error.message} hint={error.code === "dataset_unavailable" ? "Collect the snapshot with: python scripts/product_collect.py" : undefined} onRetry={reload} />;
  }
  if (status === "loading" && !data) {
    return <LoadingBlock lines={loadingLines} height={loadingHeight} />;
  }
  if (!data) {
    return <LoadingBlock lines={loadingLines} height={loadingHeight} />;
  }
  return <>{children(data)}</>;
}
