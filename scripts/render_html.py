#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
HTML 渲染：仪表盘（index.html）+ 历史趋势（history.html）
纯静态，Chart.js 走 CDN，GitHub Pages 直接打开。
"""
import json
import os
from datetime import datetime

SIGNAL_CN = {
    "STRONG_BUY": ("强烈买入", "#c23531"),
    "BUY": ("买入", "#d48265"),
    "HOLD": ("持有", "#e6a23c"),
    "REDUCE": ("减配", "#749f83"),
    "UNKNOWN": ("未知", "#999999"),
}

DIM_NAMES = ["资产质量", "负债结构", "中间业务", "资本实力", "管理层"]
DIM_SHORT = ["质量", "负债", "中间", "资本", "管理"]
DIM_KEYS = ["asset_quality", "liability", "intermediary", "capital", "management"]

def _signal_badge(sig):
    cn, color = SIGNAL_CN.get(sig, ("未知", "#999"))
    return f'<span class="badge" style="background:{color}">{cn}</span>'

def render(rows, fund, t0, out_path):
    date_str = t0.strftime("%Y-%m-%d %H:%M")
    # 表格行
    trs = []
    for r in rows:
        sc = r["score"]
        dims = " ".join(
            f'<span class="dim" title="{DIM_NAMES[i]}">{sc["dims"][DIM_KEYS[i]]["score"]:.0f}</span>'
            for i in range(5)
        )
        total = sc["total"]
        total_color = "#c23531" if total >= 100 else ("#d48265" if total >= 85 else "#e6a23c")
        # 买入区间（由五维引擎按估值风格算出：yield=PB0.7~0.9 / growth=PE6~8 对应价）
        zl = r["signal"].get("zone_low")
        zh = r["signal"].get("zone_high")
        price = r["price"]
        if zl is not None and zh is not None:
            if price is not None:
                if price < zl:
                    status, scolor = "低于强买线", "#c23531"
                elif price <= zh:
                    status, scolor = "区间内", "#2e7d32"
                else:
                    status, scolor = "高于区间", "#e6a23c"
            else:
                status, scolor = "—", "#999"
            zone_cell = (f'{zl:.2f} ~ {zh:.2f}'
                         f'<br><span style="color:{scolor};font-size:11px">{status}</span>')
        else:
            zone_cell = "—"
        trs.append(f"""
        <tr>
          <td><b>{r['name']}</b><br><span class="code">{r['code']}</span></td>
          <td class="num" title="价数据源：{r.get('price_source','')}｜抓取：{r.get('quote_time','')}">{r['price'] if r['price'] else '—'}</td>
          <td class="num">{zone_cell}</td>
          <td class="num" title="PE 数据源：{r.get('pe_source','')}">{r['pe'] if r['pe'] else '—'}</td>
          <td class="num" title="PB 数据源：{r.get('pb_source','')}">{r['pb'] if r['pb'] else '—'}</td>
          <td class="num">{r['div_yield'] if r['div_yield'] else '—'}</td>
          <td class="dims">{dims}</td>
          <td class="num"><b style="color:{total_color};font-size:1.1em">{total:.0f}</b><span class="sub">/100</span></td>
          <td>{_signal_badge(r['signal']['signal'])}</td>
        </tr>""")
    # 雷达图数据
    radar = {r["short"]: [round(sc["dims"][k]["score"], 1) for k in DIM_KEYS] for r, sc in
             [(r, r["score"]) for r in rows]}
    radar_json = json.dumps(radar, ensure_ascii=False)
    colors = [r["color"] for r in rows]
    shorts = [r["short"] for r in rows]
    # 构建 Chart.js 配置对象（Python dict → json.dumps，避免 f-string {{}} 转义 bug）
    radar_datasets = []
    for i, s in enumerate(shorts):
        radar_datasets.append({
            "label": s,
            "data": radar[s],
            "borderColor": colors[i],
            "backgroundColor": colors[i] + "22",
            "pointBackgroundColor": colors[i]
        })
    radar_cfg_json = json.dumps({
        "type": "radar",
        "data": {"labels": DIM_NAMES, "datasets": radar_datasets},
        "options": {
            "scales": {"r": {"min": 0, "max": 20, "ticks": {"stepSize": 5}}},
            "plugins": {"legend": {"position": "bottom"}}
        }
    }, ensure_ascii=False)
    totals_list = [sum(radar[s]) for s in shorts]
    bar_cfg_json = json.dumps({
        "type": "bar",
        "data": {
            "labels": shorts,
            "datasets": [{"label": "总分", "data": totals_list, "backgroundColor": colors}]
        },
        "options": {
            "plugins": {"legend": {"display": False}},
            "scales": {"y": {"beginAtZero": True, "max": 100}}
        }
    }, ensure_ascii=False)

    # 分析师研报评级 展示面板（事件型字段，不计入五维评分）
    # 注：北向个股持股数据止于 2024-08-16（2024-08-19 起沪深港通暂停北向披露），本阶段不接入。
    trs_research = []
    for r in rows:
        f = fund.get(r["code"], {})
        rating = f.get("research_rating")
        cnt = f.get("research_count_1m")
        inst = f.get("research_institution")
        ra = f.get("research_as_of")
        trs_research.append(f"""
        <tr>
          <td><b>{r['name']}</b></td>
          <td>{rating if rating else '—'}</td>
          <td>{inst if inst else '—'}</td>
          <td class="num">{cnt if cnt is not None else '—'}</td>
          <td class="code">{ra or '—'}</td>
        </tr>""")

    html = f"""<!DOCTYPE html>
<html lang="zh-CN"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>招招五维 · 五大行追踪</title>
<script src="vendor/chart.umd.min.js"></script>
<style>
 *{{box-sizing:border-box}} body{{font-family:-apple-system,"PingFang SC","Microsoft YaHei",sans-serif;
   margin:0;background:#f5f6f8;color:#222}}
 .wrap{{max-width:1080px;margin:0 auto;padding:24px}}
 header{{background:linear-gradient(135deg,#1f2d3d,#3a4a5e);color:#fff;padding:22px 28px;border-radius:12px}}
 header h1{{margin:0 0 4px;font-size:22px}} header .meta{{opacity:.85;font-size:13px}}
 .cards{{display:flex;gap:14px;flex-wrap:wrap;margin:20px 0}}
 .card{{flex:1;min-width:150px;background:#fff;border-radius:10px;padding:14px 16px;box-shadow:0 1px 4px rgba(0,0,0,.06)}}
 .card .t{{font-size:12px;color:#888}} .card .v{{font-size:22px;font-weight:700;margin-top:4px}}
 table{{width:100%;border-collapse:collapse;background:#fff;border-radius:10px;overflow:hidden;
   box-shadow:0 1px 4px rgba(0,0,0,.06);margin:16px 0}}
 th,td{{padding:10px 12px;text-align:left;font-size:13px;border-bottom:1px solid #f0f0f0}}
 th{{background:#fafafa;color:#666;font-weight:600}}
 td.num{{text-align:right;font-variant-numeric:tabular-nums}}
 .code{{color:#aaa;font-size:11px}} .sub{{color:#aaa;font-size:11px}}
 .dims{{text-align:center}} .dim{{display:inline-block;width:26px;height:26px;line-height:26px;
   border-radius:6px;background:#eef2f7;margin:1px;font-size:12px;font-weight:600;color:#3a4a5e}}
 .badge{{display:inline-block;color:#fff;padding:3px 10px;border-radius:12px;font-size:12px;font-weight:600}}
 .grid{{display:grid;grid-template-columns:1fr 1fr;gap:18px}}
 .panel{{background:#fff;border-radius:10px;padding:16px;box-shadow:0 1px 4px rgba(0,0,0,.06)}}
 .panel h3{{margin:0 0 10px;font-size:15px;color:#333}}
 .note{{font-size:12px;color:#999;line-height:1.7;margin-top:18px;
   background:#fff;padding:14px 16px;border-radius:10px}}
 @media(max-width:720px){{.grid{{grid-template-columns:1fr}}}}
</style></head>
<body><div class="wrap">
<header><h1>招招五维模型 · 五大行每日追踪</h1>
<div class="meta">更新时间：{date_str} ｜ 标的：招商/工商/建设/农业/中国/宁波（交行已排除）｜ 数据源：腾讯/新浪/akshare/baostock</div></header>

<div class="cards">
  <div class="card"><div class="t">追踪标的数</div><div class="v">{len(rows)}</div></div>
  <div class="card"><div class="t">强烈买入</div><div class="v" style="color:#c23531">{sum(1 for r in rows if r['signal']['signal']=='STRONG_BUY')}</div></div>
  <div class="card"><div class="t">买入</div><div class="v" style="color:#d48265">{sum(1 for r in rows if r['signal']['signal']=='BUY')}</div></div>
  <div class="card"><div class="t">持有/减配</div><div class="v" style="color:#e6a23c">{sum(1 for r in rows if r['signal']['signal'] in ('HOLD','REDUCE','UNKNOWN'))}</div></div>
</div>

<table>
<tr><th>银行</th><th class="num">现价</th><th class="num">买入区间(元)</th><th class="num">PE</th><th class="num">PB</th><th class="num">股息率%</th><th>五维(质量/负债/中间/资本/管理)</th><th class="num">总分</th><th>信号</th></tr>
{''.join(trs)}
</table>

<div class="grid">
  <div class="panel"><h3>五维雷达对比</h3><canvas id="radar" height="300"></canvas></div>
  <div class="panel"><h3>各维得分</h3><canvas id="bar" height="300"></canvas></div>
</div>

<div class="panel" style="margin-top:16px"><h3>分析师研报评级（事件更新 · 不计入五维评分）</h3>
<table>
<tr><th>银行</th><th>东财评级</th><th>最新机构</th><th class="num">近一月研报</th><th>数据日期</th></tr>
{''.join(trs_research)}
</table>
</div>

<div class="note">
<b>方法论</b>：评分采用招招五维模型（资产质量/负债结构/中间业务/资本实力/管理层，每维0-20，总分0-100）。
财务字段（不良率、拨备覆盖率、非息占比、资本充足率、ROE等）为季度数据，来自最近一期财报，每日不更新；
现价/PE/PB/股息率为每日盘后刷新。买入信号基于 PB 破净程度与股息率，结合五维总分判定。
<b>买入区间</b>：由五维引擎按估值风格动态计算——收益型（招行/四大行）取 PB 0.7~0.9 对应价，成长型（宁波）取 PE 6~8 对应价；
「区间内」为绿色、「低于强买线」为红色（更划算）、「高于区间」为橙色。
<b>免责</b>：本项目仅作个人研究记录，不构成任何投资建议。
</div>
</div>
<script>
new Chart(document.getElementById('radar'), {radar_cfg_json});
new Chart(document.getElementById('bar'), {bar_cfg_json});
</script></body></html>"""
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)


def render_history(history_path, out_path):
    if not os.path.exists(history_path):
        return
    dates, series = [], {}
    with open(history_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            e = json.loads(line)
            dates.append(e["date"])
            for b in e["banks"]:
                series.setdefault(b["code"], {})
                series[b["code"]][e["date"]] = {
                    "total": b["total"], "pb": b["pb"], "sig": b["signal"]}
    # 构建折线
    codes = list(series.keys())
    names = {c: next((b["name"] for e in [json.loads(l) for l in open(history_path, encoding="utf-8") if l.strip()] for b in e["banks"] if b["code"] == c), c) for c in codes}
    palette = ["#c23531", "#2f4554", "#61a0a8", "#d48265", "#91c7ae", "#749f83"]
    total_ds = [{"label": names[c], "data": [series[c].get(d, {}).get("total") for d in dates],
                 "borderColor": palette[i % len(palette)], "tension": .3, "pointRadius": 2}
                for i, c in enumerate(codes)]
    pb_ds = [{"label": names[c], "data": [series[c].get(d, {}).get("pb") for d in dates],
              "borderColor": palette[i % len(palette)], "tension": .3, "pointRadius": 2}
             for i, c in enumerate(codes)]
    # Chart.js 配置（json.dumps，避免 f-string 转义 bug）
    line_t_cfg_json = json.dumps({
        "type": "line",
        "data": {"labels": dates, "datasets": total_ds},
        "options": {
            "plugins": {"legend": {"position": "bottom"}},
            "scales": {"y": {"beginAtZero": False}}
        }
    }, ensure_ascii=False)
    line_p_cfg_json = json.dumps({
        "type": "line",
        "data": {"labels": dates, "datasets": pb_ds},
        "options": {
            "plugins": {"legend": {"position": "bottom"}},
            "scales": {"y": {"beginAtZero": False}}
        }
    }, ensure_ascii=False)
    html = f"""<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>历史趋势</title>
<script src="vendor/chart.umd.min.js"></script>
<style>body{{font-family:-apple-system,"PingFang SC",sans-serif;margin:0;background:#f5f6f8}}
.wrap{{max-width:1000px;margin:0 auto;padding:24px}}
.panel{{background:#fff;border-radius:10px;padding:16px;box-shadow:0 1px 4px rgba(0,0,0,.06);margin-bottom:18px}}
a{{color:#3a4a5e}}</style></head><body><div class="wrap">
<p><a href="index.html">← 返回仪表盘</a></p>
<div class="panel"><h3>五维总分历史趋势</h3><canvas id="t" height="320"></canvas></div>
<div class="panel"><h3>PB（市净率）历史趋势</h3><canvas id="p" height="320"></canvas></div>
</div>
<script>
new Chart(document.getElementById('t'), {line_t_cfg_json});
new Chart(document.getElementById('p'), {line_p_cfg_json});
</script></body></html>"""
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)
