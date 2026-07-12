# cmb-tracker · JSON 产出方案（待审核，未实现）

> 目的：让 `cmb-tracker` 像 `xiaoxu-fear` 产出 `xxfi_report.json` 那样，产出一个机器可读的 JSON 文件，供你本地 `investment-tracker` 项目直接 `fetch` 调用。
> 本文件为**方案**，确认后再实现。

---

## 1. 现状对齐（你已确认的引用方式）

`investment-tracker/js/api.js`（第 831 行）当前这样取小旭恐慌指数：

```js
const xxfiData = await fetchAPI(
  'https://raw.githubusercontent.com/homjanon/xiaoxu-fear/main/output/xxfi_report.json'
);
if (xxfiData && xxfiData.XXFI != null) {
  result.xxfi = {
    value:   xxfiData.XXFI,
    signal:  xxfiData.contrarian_signal || '',
    level:   xxfiData.level || '',
    advice:  xxfiData.advice || '',
    dataDate:xxfiData._data_date || ''
  };
}
```

即：它用一个 `raw.githubusercontent.com/<owner>/<repo>/<branch>/<path>` 的固定 URL 拉 JSON，再抽取若干顶层字段。**注意它并不依赖 Pages**，raw 文件即可。

---

## 2. 产出文件与路径

| 项 | 值 |
|----|----|
| 文件名 | `cmb_report.json` |
| 仓库内路径 | `output/cmb_report.json` |
| 调用 URL | `https://raw.githubusercontent.com/homjanon/cmb-tracker/main/output/cmb_report.json` |
| 生成时机 | 每次 `run_daily.py` 运行末尾（与 `history.jsonl`/`docs` 同步） |

> 放在 `output/` 而非 `docs/`：与 `xiaoxu-fear` 一致，且 raw 取数不受 Pages 目录限制。`docs/` 仍只服务于人类浏览的 HTML。

---

## 3. JSON Schema 设计（参考 xxfi_report.json 的扁平风格）

```json
{
  "tracker": "cmb-tracker",
  "model": "招招五维模型",
  "generated_at": "2026-07-12T22:30:00+08:00",
  "data_date": "2026-07-12",
  "summary": {
    "total_banks": 6,
    "strong_buy": 0,
    "buy": 5,
    "hold": 1,
    "reduce": 0
  },
  "banks": [
    {
      "code": "600036",
      "name": "招商银行",
      "short": "招行",
      "price": 36.88,
      "pe": 6.17,
      "pb": 0.82,
      "div_yield": 5.42,
      "score_total": 83.0,
      "score_dims": {
        "asset_quality": 14.5,
        "liability": 14.8,
        "intermediary": 19.4,
        "capital": 17.4,
        "management": 16.5
      },
      "signal": "BUY",
      "signal_cn": "买入",
      "valuation_style": "yield",
      "reason": "PB0.82破净附近 + 股息5.4%，低估"
    }
    /* …其余 5 只同理… */
  ]
}
```

设计要点：
- **顶层对齐 xxfi 心智**：保留 `model` / `data_date` / `generated_at` 等元信息字段，方便你以后统一渲染。
- **每只银行一行**：把五维分、估值、信号、买入理由全带上，`investment-tracker` 想怎么展示都行（卡片、列表、雷达）。
- **隐私**：全文件不出现原作者昵称相关字串（含中英文），模型名即「招招五维模型」。
- **估值风格可见**：`valuation_style` 字段让调用方知道该行用的是收益型还是成长型信号（宁波=growth）。

---

## 4. 本项目侧改动（实现阶段才做）

1. **`scripts/run_daily.py`**：在步骤 5（渲染 HTML）之后新增步骤 6，调用 `render_report.build(rows, merged, t0, out_path)` 写出 `output/cmb_report.json`。
2. **新增 `scripts/render_report.py`**：纯函数，输入与 `render_html.render` 相同的 `rows`，输出上面的 JSON；`ensure_ascii=False`、缩进 2。
3. **`.github/workflows/daily.yml`**：`Commit & push` 步骤的 `git add` 增加 `output/`（目前只 add `fundamentals.json history.jsonl docs/`）。
4. **`.gitignore`**：确认不忽略 `output/`（目前未忽略，无需改）。

---

## 5. investment-tracker 侧改动（你确认后，我可一并给代码）

在 `js/api.js` 的 `fetchIndicators()` 内、`xxfi` 抓取块之后新增一段（与你现有风格一致）：

```js
// 招招五维·五大行追踪(cmb-tracker): raw GitHub
if (!result.cmbTracker) {
  try {
    const cmb = await fetchAPI(
      'https://raw.githubusercontent.com/homjanon/cmb-tracker/main/output/cmb_report.json'
    );
    if (cmb && Array.isArray(cmb.banks)) {
      result.cmbTracker = {
        dataDate: cmb.data_date || '',
        model:    cmb.model || '',
        summary:  cmb.summary || {},
        banks:    cmb.banks.map(b => ({
          code: b.code, name: b.name, price: b.price,
          pb: b.pb, pe: b.pe, divYield: b.div_yield,
          total: b.score_total, signal: b.signal, reason: b.reason
        }))
      };
      hasNew = true;
    }
  } catch (e) { console.warn('cmb-tracker失败:', e.message); }
}
```

随后在 `app.js` / `ui.js` 里加一个「银行五维」卡片即可（展示各行 PB、五维总分、信号徽章）。**这部分在你仓库，确认后我再给完整 UI 代码或直接改。**

---

## 6. 待你确认的几个点

1. **文件名/路径**：用 `output/cmb_report.json`（对齐 xiaoxu-fear）可以吗？还是你想放 `docs/` 或改名（如 `tracker_report.json`）？
2. **字段取舍**：上面 schema 够用吗？需要额外加「买入区间 zone_low/zone_high」或「历史近 N 日趋势」吗？（目前引擎 zone 为 null）
3. **investment-tracker 联动**：要我顺便把 `js/api.js` + UI 改了，还是你只想先拿到 JSON、自己接？
4. **提交方式**：实现后同样经 GitHub API 推到 `homjanon/cmb-tracker`（本机 git push 被墙）。

确认后我立即实现第 4、5 节。
