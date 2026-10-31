# 开发署名 / Attribution

## 一句话

**MedRadar 的每一行代码、每一次数据采集、每一份报告和每一次提交，都由 DeepSeek Harness 智能体团队使用中国国产模型 `deepseek-flash` 自主完成，全程没有使用任何其他模型。**

## 开发主体

| 项 | 内容 |
|---|---|
| 开发框架 | **DeepSeek Harness (DSH)** —— 智能体团队编排（Agent Teams + 目标模式 + 任务板） |
| 模型 | **deepseek-flash**（深度求索 / DeepSeek，中国国产模型） |
| 开发时间 | 2026‑10‑31（约 11 小时连续自主迭代，多轮目标模式） |
| 团队形态 | 1 个 Lead（负责集成、验收、发布）+ 8 个专职智能体 |
| 外部模型 | **无**（没有使用任何非国产模型） |

## 智能体分工

| 智能体 | 职责 |
|---|---|
| Lead | 架构、集成、CLI/指标契约、真实数据全链路验收、发布与 GitHub 推送 |
| dev-device | openFDA 器械采集（510(k)/PMA/召回）、全历史回填、产品码词典 |
| dev-drug | 药品批准、ClinicalTrials.gov 全历史、NMPA 适配器（诚实不可用） |
| dev-quant | 价格层、事件研究、模拟盘与成本模型 |
| dev-viz | 19 章中文报告 + 自包含 HTML 看板 + 交互式 dashboard |
| dev-product | 204 个产品族、2,740 条中文产品名、新品雷达 |
| dev-replay | 7 年回放引擎（1 分钟/日线、10/25/50bps）、假设登记表 |
| dev-research | 统计模块（block bootstrap、Holm）、可复现校准 harness、研究协议 |
| dev-pack | 打包（wheel data-files）、`MEDRADAR_HOME`、demo/doctor/watchlist、CI |

## 交付规模（可复核）

- **375,378** 条事件（510(k) 176,466 / PMA 57,372 / 召回 59,646 / 试验 55,592 / 药品 5,326 / 8‑K 催化剂 20,976）
- **20,976** 份 EDGAR 8‑K 语料，**2,384** 个可追溯案例（含逐字证据与价格反应）
- **440** 个离线测试全绿；19 章报告；7 视图交互式看板；GitHub Pages 在线
- 数据来自公开来源（openFDA、ClinicalTrials.gov、SEC EDGAR、Yahoo Finance），不包含任何非公开数据

## 复核方式

```bash
git log --oneline            # 全部提交均来自该智能体团队
python -m medradar selftest  # 440 tests, 不联网
```

> 说明：以上署名为开发过程事实陈述，不构成对模型能力的第三方评测；项目内容仅用于开源研究与技术演示，不构成投资建议。
