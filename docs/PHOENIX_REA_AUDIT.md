# PHOENIX-001 — REA 审查与部署记录

审查时间：2026-11-06（UTC 日志从 2026-11-05 晚间开始）。

## 结论

**BLOCKED，未安装、未注册 MCP、未执行 REA 代码。** 这不是分析失败，也不是工具调用成功率为零；本轮根本没有发起工具调用。阻碍是当前 Node.js 不满足官方版本要求，且精确 MCP 配置尚未得到环境所有者批准。后续源码与论文复现不依赖 REA。

## 官方来源与锁定版本

- 上游：`https://github.com/morluto/rea`
- npm：`rea-agents`
- npm `latest` 与安装文档所示当前发布版：**6.8.0**
- npm 发布时间：2026-10-25T09:07:31.585Z
- 官方 tarball：`https://registry.npmjs.org/rea-agents/-/rea-agents-6.8.0.tgz`
- SHA-512 integrity：`sha512-9QDeRnGqEDzABZyr04eLnBXBv/c6I9/TWu/6M0MD4pEfkySI/BIgwTODIbAReX3C1x6hjw9+Jlx4A2yUSPZ9ww==`
- 许可证：REA 自有代码 MIT；第三方材料沿用各自许可，见上游 `THIRD_PARTY_NOTICES.md`。

仅查询了官方 README、安装文档、许可证、第三方声明和 npm 元数据。没有使用镜像或 Fork，没有执行 `curl ... | bash`、`npx`、`npm setup` 或全局安装。

## 环境与依赖审查

| 项目 | 实测 |
|---|---|
| OS | Linux x86_64，glibc 2.36 |
| Node.js | v20.20.2 |
| npm | 11.19.0 |
| Python | 3.12.12 |
| REA Node 要求 | `^22.23.4 || ^24.22.1 || >=26.12.1` |
| npm 包解包大小 | 49,251,336 bytes，2,398 个文件 |
| 直接运行时依赖 | 39 个 |
| 可选依赖 | `frida@17.23.2` |
| 值得关注的攻击面 | 浏览器自动化、PTY、MCP 服务、压缩包与 JavaScript 解析、可选 Frida |
| GPU | 静态 JavaScript 分析不需要 |
| 商业分析引擎 | 未安装；REA 不授予 Hopper、IDA、JEB 许可 |

另一个部署风险是当前持久化挂载不支持硬链接，而上游首次配置发布流程使用排他硬链接。即使升级 Node，也必须先在兼容文件系统上验证 dry-run，不能假设注册一定成功。

## MCP 变更预览（未应用）

只考虑项目本地注册，不安装全局 workflow skill：

```json
{
  "mcpServers": {
    "rea": {
      "command": "/absolute/path/to/supported/node",
      "args": ["/absolute/path/to/rea/scripts/rea.mjs", "mcp"]
    }
  }
}
```

应用前的硬条件：

1. 使用官方支持的 Node 版本与官方 npm 包，核对上述 integrity。
2. 在不向 MedRadar 写依赖的隔离目录审查包内容，禁用未审查生命周期脚本。
3. 运行 `setup --dry-run --skill=false`，把解析后的绝对路径和备份方案交给环境所有者。
4. 所有者批准精确配置后才应用；当前没有这项批准。
5. 重启后读取真实 `tools/list`，记录版本、启动时间和工具目录，再分析自己创建的无害 JavaScript 程序。

## 实测与资源记录

- REA 启动时间：未测量（未启动）。
- MCP 工具列表：空（未连接，不代表上游没有工具）。
- 工具调用：0 次成功 / 0 次总数。
- 静态分析 smoke test：未运行。
- npm 元数据审查命令及退出状态保存在 `experiments/phoenix_001/logs/`。

完整机器可读记录：`experiments/phoenix_001/rea_audit.json`。
