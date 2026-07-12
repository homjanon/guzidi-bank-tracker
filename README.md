# 招招五维模型 · 五大行每日追踪

基于 **招招五维模型** 的选股框架，每日盘后自动抓取招商银行、工商银行、建设银行、农业银行、中国银行、宁波银行的行情与财务数据，计算五维评分、买入信号与买入区间，并发布到 GitHub Pages。

> ⚠️ 本项目仅作个人投资研究记录，**不构成任何投资建议**。

## 标的范围

| 代码 | 银行 | 备注 | 估值风格 |
|------|------|------|----------|
| 600036 | 招商银行 | 零售之王，五维标杆 | 收益型 |
| 601398 | 工商银行 | 国有大行 | 收益型 |
| 601939 | 建设银行 | 国有大行 | 收益型 |
| 601288 | 农业银行 | 县域存款优势 | 收益型 |
| 601988 | 中国银行 | 海外布局 | 收益型 |
| 002142 | 宁波银行 | 高 ROE 成长型城商行 | 成长型（PE+ROE） |

- **交通银行**：默认排除（估值陷阱，通常不推荐）。
- **招商银行 H（03968）**：沙箱/接口稳定性待验证，默认 `INCLUDE_H=False`。数据源稳定后可置 `True` 纳入（`scripts/bank_universe.py`）。
- **估值风格差异**：招行/四大行为「收益型」银行（高分红、低估值），买入信号基于 PB 破净 + 股息率；宁波银行为「成长型」银行（高 ROE、低分红率），买入信号基于 PE + ROE，避免低股息率误判为"持有"。

## 五维模型

每维 0–20 分，总分 0–100：

1. **资产质量**：不良率↓、拨备覆盖率↑
2. **负债结构**：活期占比↑、零售存款占比↑
3. **中间业务**：非息收入占比↑
4. **资本实力**：RORWA↑、核心一级资本充足率↑
5. **管理层**：ROE、分红率连续性、零售护城河（代理指标）

评分阈值详见 [`docs/scoring.md`](docs/scoring.md)。

## 数据源与架构（关键）

银行的五维财务字段中，质量字段（不良率/拨备/资本充足率/存款结构/RORWA）是**季度**数据、每日不变；而现价/PE/PB/股息率与部分财务字段是**每日**变化。因此采用「底表为真源 + 每日轻量刷新」的稳健设计：

- **行情（每日）**：腾讯 `qt.gtimg.cn`（主）→ 新浪 `hq.sinajs.cn`（备）→ akshare `stock_zh_a_spot_em`（兜底）。这一多源容错链复用自「每日财经早报」项目。
- **财务底表（真源）**：`fundamentals.json` 保存各银行五维原始输入与每日刷新结果。
  - `scripts/fetch_fundamentals.py → refresh_light()`：**每日**用 akshare `stock_yjbb_em` 刷新每股净资产(BVPS)/ROE/**EPS（均按报告期年化）**，保证 PB 与派息率口径精确。
  - `refresh_nii()`：非息收入占比 —— **半自动**，每日用必盈利润表 API 推算，需 `BIYING_API_KEY` 环境变量；缺 key/失败则保留手工值。
  - `refresh_div()`：每股分红 `div_ps` —— **自动**，每日用 akshare `stock_history_dividend_detail` 按股权登记日倒序取最新 2 次「已实施」派息（元/10 股）求和÷10，等于最近一个完整年度（本组合均为半年派，规避滚动 365 天窗口跨年抓到 3 次导致股息率/派息率虚高）。
  - 派息率 `div_payout`：**自动**，由 `div_ps ÷ 年化EPS` 计算（不再手工维护）。
  - `refresh_deep()`：保留接口（当前休眠），质量字段仍按季度手工维护于底表。
- **为什么不全自动**：akshare 1.18.x 的 `stock_financial_analysis_indicator` 已失效，利润表/资产负债表原始科目列名漂移，港股接口在沙箱不稳定。质量字段（不良率/拨备/核心一级资本充足率/存款结构/RORWA/零售护城河）目前人工季度更新；BVPS/ROE/EPS/div_ps/非息占比已实现自动或半自动刷新。

## 每日运行

```bash
pip install -r requirements.txt
cd scripts
python run_daily.py
```

> 本地依赖（akshare / pandas / baostock 等）需装在 Python 3.11+ 虚拟环境中；若用本机托管环境，请先 `cd scripts` 再运行 `python run_daily.py`（脚本内部按仓库根目录定位文件）。可选环境变量：`BIYING_API_KEY`（开启非息占比半自动刷新）。

产出：
- `fundamentals.json` — 财务底表（每日刷新 BVPS/ROE/EPS/div_ps/非息占比 后写回）
- `history.jsonl` — 每日评分历史（按日期去重累积）
- `docs/index.html` — 仪表盘（表格 + 五维雷达 + 各维条形）
- `docs/history.html` — 历史趋势（总分 / PB）
- `output/cmb_report.json` — 机器可读报告（外部可直接 fetch，详见下文「JSON 产出」）

## GitHub Actions 自动运行

- 触发：`cron "30 7 * * 1-5"`（**UTC 07:30 = 北京时间 15:30**）+ 交易日历精确排除节假日/休市 + 手动 `workflow_dispatch`。GitHub Actions 实际存在约 1h 延迟，实跑时间约 **北京时间 16:30**，恰好盘后数据定稿窗口。
- 流程：checkout → 装依赖 → 交易日判断 → `run_daily.py`（设 `BIYING_API_KEY`）→ 自动 commit `fundamentals.json`/`history.jsonl`/`docs/`/`output/`
- Pages：仓库 Settings → Pages → Source 选 `main` 分支 `/docs` 目录

> 本机 `git push` 若被网络限制，可用仓库根目录的 `_api_sync.py`（GitHub Contents API 推送，需 `GITHUB_TOKEN`）替代。

## JSON 产出（output/cmb_report.json）

每日自动生成机器可读报告，供外部系统（如投资看板）直接 fetch：

```
https://raw.githubusercontent.com/homjanon/cmb-tracker/main/output/cmb_report.json
```

顶层结构：

```json
{
  "tracker": "cmb-tracker",
  "model": "招招五维模型",
  "generated_at": "2026-07-13T00:10:00+08:00",
  "data_date": "2026-07-13",
  "summary": { "total_banks": 6, "strong_buy": 0, "buy": 0, "hold": 6, "reduce": 0 },
  "banks": [
    {
      "code": "600036", "name": "招商银行", "as_of": "2026Q1",
      "price": 43.5, "pe": 7.3, "pb": 0.97, "div_yield": 4.6,
      "score_total": 82.5,
      "score_dims": { "asset_quality": 18, "liability": 16, "intermediary": 15, "capital": 14, "management": 19.5 },
      "signal": "HOLD", "signal_cn": "持有",
      "valuation_style": "yield",
      "zone_low": 31.44, "zone_high": 40.43,
      "reason": "PB 0.97 高于破净线，股息率 4.6% ..."
    }
  ]
}
```

字段说明：`score_dims` 为五维得分（0–20 各维）；`zone_low`/`zone_high` 为模型给出的买入区间上下限；`signal`/`signal_cn` 为买入信号（STRONG_BUY/BUY/HOLD/REDUCE）及中文。

## 维护财务报表

字段自动化程度分三类，无需全部手工维护：

| 自动化 | 字段 | 来源 |
|--------|------|------|
| 自动 | BVPS / ROE / EPS(年化) / div_ps(每股分红) | akshare（`refresh_light` / `refresh_div`） |
| 半自动 | 非息收入占比 | 必盈利润表 API（`refresh_nii`，需 `BIYING_API_KEY`） |
| 手工 | 不良率 / 拨备覆盖率 / 核心一级资本充足率 / 存款结构 / RORWA / 零售护城河 | 季度人工更新 `fundamentals.json` |

- **手工字段随季报更新**：直接编辑 `fundamentals.json` 对应字段，并改 `as_of`（如 `2026Q1`）。这些字段在 `_manual_maintain` 列表中，刷新时不会被覆盖。
- **派息率 `div_payout`** 由 `div_ps ÷ 年化EPS` 自动算出，已从 `_manual_maintain` 移除，无需手工填。
- 运行 `python calibration.py` 可查看当前评分与缺失字段。

## 目录结构

```
cmb-tracker/
├── .github/workflows/daily.yml   # 每日自动化（交易日 16:30 前后）
├── _api_sync.py                  # GitHub Contents API 推送（替代被墙的 git push）
├── scripts/
│   ├── bank_universe.py          # 标的清单
│   ├── fetch_quotes.py           # 行情（腾讯/新浪/akshare）
│   ├── fetch_fundamentals.py     # 财务底表刷新（light/nii/div 三路）
│   ├── zhaozhao_five_dim.py      # 五维评分引擎（纯计算）
│   ├── render_html.py            # HTML 渲染（仪表盘/历史）
│   ├── render_report.py          # JSON 产出（output/cmb_report.json）
│   ├── run_daily.py              # 每日编排器
│   ├── calibration.py            # 校准/缺失检查
│   └── retry_utils.py            # 重试/多源容错
├── fundamentals.json             # 财务底表（真源 + 每日刷新结果）
├── history.jsonl                 # 每日历史
├── output/
│   └── cmb_report.json           # 机器可读报告
├── docs/                         # GitHub Pages 产物
│   ├── index.html
│   ├── history.html
│   ├── scoring.md                # 评分阈值说明
│   └── vendor/chart.umd.min.js   # 本地内置 Chart.js（离线渲染图表）
└── requirements.txt
```

---
*以招招五维框架构建，仅供个人研究。*
