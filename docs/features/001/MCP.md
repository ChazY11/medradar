# MCP 接入 / Read-only MCP server

本仓库自带一个只读 MCP 服务端，让 Claude Desktop、IDE 代理或自建脚本直接查询雷达数据，
**不需要**经过网页或用 HTTP 认证。

---

## 1. 启动

```bash
python -m medradar.mcp_server --radar-dir /srv/medradar/data/radar
```

它走 **stdio**（JSON-RPC 2.0），不监听端口，不发网络请求。

---

## 2. 客户端配置

Claude Desktop（`claude_desktop_config.json`）：

```json
{
  "mcpServers": {
    "medradar": {
      "command": "python",
      "args": ["-m", "medradar.mcp_server", "--radar-dir", "/srv/medradar/data/radar"]
    }
  }
}
```

其它客户端只要支持 stdio MCP，配置同理。

---

## 3. 工具

| 工具 | 参数 | 返回 |
| --- | --- | --- |
| `radar_digest` | `hours` (1–168, 默认 24)、`limit` (1–10) | 过去 N 小时的到货、值得看的、安全事件、待确认、告警提示 |
| `radar_search` | `query`、`source`、`scope`、`limit` | 准入记录的 id 与标题 |
| `radar_record` | `observation_id` | 单条记录 + 判定维度 + 理由 + 官方链接 |
| `radar_company` | `organization_id`、`limit` | 一家公司最近的记录与档案 |
| `radar_sources` | 无 | 来源状态（含被策略封禁的） |

**能力边界**：没有任何写工具。代理不能改判定、不能改账本、不能触发采集。

---

## 4. 协议细节

- `initialize`：回显客户端协议版本，回 `serverInfo: medradar-radar`
- `tools/list`：五个工具的 JSON Schema
- `tools/call`：结果放在 `content[0].text` 里，是一段 JSON
- 工具内部错误返回 `isError: true` 而不是让进程死掉
- 未知方法返回 `-32601`
- 通知（`notifications/*`）不产生响应

手动试一下：

```bash
printf '%s\n' \
 '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}' \
 '{"jsonrpc":"2.0","id":2,"method":"tools/list"}' \
 | python -m medradar.mcp_server --radar-dir /srv/medradar/data/radar
```
