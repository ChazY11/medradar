# PHOENIX-001 — 许可证与供应链审计

状态：全部项目已完成许可与供应链审查。外部源码只放在 `/mnt/agents/output/phoenix_external/` 隔离目录，不进入 MedRadar 源码树。

| 软件/项目 | 确认依据 | 允许方式 | 本轮处理 | 风险 |
|---|---|---|---|---|
| REA `rea-agents@6.8.0` | 官方 npm 与上游 MIT LICENSE；`THIRD_PARTY_NOTICES.md` | REA 自有代码可按 MIT 使用；商业分析引擎另行授权 | 仅元数据审查；未安装、未注册、未执行 | Node 不兼容；39 个直接依赖、可选 Frida、PTY/浏览器攻击面；配置发布依赖硬链接 |
| SciTrends `ddofer/Trends@81711b9` | GitHub API `license=null`，根目录无 LICENSE | 没有明确代码授权；论文开放获取不等于代码许可 | 隔离阅读、运行和数值复核；不把代码或上游数据复制进 MedRadar | 只能独立实现公开科学方法；依赖无锁定，结果存在配置漂移 |
| PubTrends `JetBrains-Research/pubtrends@8520f2a` | 官方 `LICENSE.txt`，Apache-2.0，JetBrains Research 2022 | 可使用、修改、再分发；须保留许可与归属，修改文件须明示 | 隔离执行单个上游算法；未整库集成 | 依赖很多，完整堆栈含数据库、Web、NLP 与可选 GPU；全历史引用快照有知识时间风险 |
| CatBoost `1.2.10` | PyPI wheel，作为 SciTrends notebook 的直接导入依赖 | 仅用于隔离复现 | 先尝试持久化隔离目录，因大文件写入失败；改用本地临时盘并保留两次日志 | 上游未锁版本；复现结果须记录本版本，不能声称与原环境完全一致 |
| pytest `8.4.2` | MedRadar `pyproject.toml` 已声明 `pytest>=8.0` | 仅运行项目测试 | 只安装 wheel，未执行源码安装脚本 | 环境依赖，不进入研究算法 |
| NIH iSearch Analytics | NIH 公开方法文档与预算文件 | 只研究公开定义与历史案例 | 未获得特定实现或训练快照 | 不得用同名 rMLC 算法冒充 NIH 方法 |
| The Lens | Terms of Use v2026.06.01 与 API 条款 | 公开网页按条款使用；API 需审批，商业/批量用途另议 | 未请求 token、未批量下载 | 不是 blanket CC0；回填引用有知识时间风险 |
| PTNS | Scientific Reports 开放论文；无公开代码库或数据包 | 只报告论文方法 | 未运行模型、未获取 Incopat 数据 | 数据仅应请求提供，论文指标不能当本地复现 |
| FDA AI 纵向研究 | PMC/JMIR 论文、Europe PMC 公开补充表、FDA 公开数据说明 | 独立复算公开聚合计数 | 下载官方补充 DOCX并实现统计 | 聚合表不能支持企业回归或设备级实体审计 |
| Clarivate DRG | 闭源商业平台公开页 | 只对标公开字段 | 未登录或购买 | 预测宣传无公开回测，不复制数据 |
| MedVantage | 预发布闭源平台公开页 | 独立吸收证据链接设计 | 未使用设计伙伴账户 | 示意图和供应商自述不是准确率审计 |
| CMOP | 闭源商业服务公开页 | 只审查宣传 | 未使用账户或 tokens | 绝对准确、实时与安全宣传缺公开评价 |
| NextDevice | 闭源商业数据库公开页/报告 | 独立研究技术代际与生命周期字段 | 使用当前官方域名，未登录 | 分类体系不可直接复制或回填历史 |
| GBI DEVINT | 闭源商业平台公开页 | 只对标生命周期展示 | 未登录 | AI 治理与可追溯没有公开质量指标 |
| DevicePro | 闭源商业数据库公开页 | 研究 AI+人工归一原则 | 未登录或复制规模数字 | 同页规模口径冲突，必须另建指标字典 |
| 众成医械大数据 | 闭源商业平台公开页/报告 | 研究标讯字段和描述性报告 | 未登录或批量下载 | 采购首次公开时间和覆盖完整性未验证 |

## 数据许可边界

- SciTrends 的 bundled CSV/Parquet 仅用于本地复现，不随 PR 转发。
- PubTrends 的 PubMed、Semantic Scholar 全量语料未下载。
- REA 的商业工具许可不由 MIT 许可证授予，本轮没有安装或使用任何商业引擎。
- 商业平台只研究公开页面与公开评价证据，不绕认证、付费或技术保护。
- MedRadar 既有数据库和冻结结果只读；不重新抓取来填补当前缺失资产。

## 供应链操作纪律

1. 官方仓库、官方 npm/PyPI 元数据优先，记录提交哈希或包版本。
2. 不执行 `curl | bash`、未审查的 `npx`、仓库初始化脚本或 notebook 下载单元。
3. notebook 采用单元白名单；SciTrends 排除下载、SHAP、预测输出和写文件单元。
4. 每个实际命令保存退出码、时间、日志和资源观测，包括安装失败与结果序列化失败。
