import { Link } from "react-router-dom";
import { listDevices } from "../api/devices";
import { useAsync } from "../api/hooks";
import { useI18n } from "../i18n";
import { Card, EmptyState, ErrorState, LoadingBlock, SectionHead, formatDate, formatNumber } from "./ui";

/** Device Intelligence inside the organization page: the same product, not a separate tool. */
export function OrgDevices({ organizationKey }: { organizationKey: string }) {
  const { bi } = useI18n();
  const devices = useAsync(
    () => listDevices({ org: organizationKey, page_size: 20, sort: "relevance" }),
    [organizationKey],
  );
  return (
    <Card
      title={bi("Devices and product families", "器械与产品家族")}
      note={bi(
        "Device identities come from the organization's own FDA applications. A 510(k) clearance identifies one cleared device; a PMA approval identifies one device whose supplements are versions. Relations are labelled confirmed or candidate.",
        "器械身份来自该企业自身的 FDA 申请：每个 510(k) 批准标识一个获批器械；每个 PMA 批准标识一个器械，其补充批准是该器械的版本。关系会标注为“已确认”或“候选”。",
      )}
      actions={
        <Link className="link small" to={"/devices?org=" + organizationKey}>
          {bi("Open in device explorer", "在器械浏览器中打开")}
        </Link>
      }
    >
      {devices.error ? <ErrorState message={devices.error.message} onRetry={devices.reload} /> : null}
      {!devices.data && devices.status === "loading" ? <LoadingBlock lines={4} /> : null}
      {devices.data && devices.data.total === 0 ? (
        <EmptyState
          title={bi("No device identities for this organization", "该企业暂无器械身份")}
          description={bi(
            "No FDA application in this snapshot is attributed to this organization, so no device identity can be created from its own records.",
            "本快照中没有归属到该企业的 FDA 申请，因此无法从其自身记录建立器械身份。",
          )}
        />
      ) : null}
      {devices.data && devices.data.total > 0 ? (
        <>
          <SectionHead
            title={bi("Device identities", "器械身份")}
            note={bi(formatNumber(devices.data.total) + " device identities in this snapshot", "本快照中共 " + formatNumber(devices.data.total) + " 个器械身份")}
          />
          <table className="data-table">
            <thead>
              <tr>
                <th scope="col">{bi("Device", "器械")}</th>
                <th scope="col">{bi("FDA identifier", "FDA 标识")}</th>
                <th scope="col">{bi("Pathway", "路径")}</th>
                <th scope="col" className="num">{bi("Versions", "版本")}</th>
                <th scope="col" className="num">{bi("Confirmed relations", "已确认关系")}</th>
                <th scope="col" className="num">{bi("Candidates", "候选")}</th>
                <th scope="col">{bi("First decision", "首个决定日期")}</th>
              </tr>
            </thead>
            <tbody>
              {devices.data.items.map((item) => (
                <tr key={item.device_id}>
                  <td>
                    <Link className="link" to={"/devices/" + encodeURIComponent(item.device_id)}>
                      {item.name.slice(0, 70)}
                    </Link>
                  </td>
                  <td className="mono small">{item.official_id}</td>
                  <td className="small">{item.kind === "510k" ? "510(k)" : "PMA"}</td>
                  <td className="num mono">{formatNumber(item.counts?.versions ?? 0)}</td>
                  <td className="num mono">{formatNumber(item.counts?.confirmed_relations ?? 0)}</td>
                  <td className="num mono">{formatNumber(item.counts?.candidate_relations ?? 0)}</td>
                  <td className="mono small">{formatDate(item.first_event_date)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      ) : null}
    </Card>
  );
}
