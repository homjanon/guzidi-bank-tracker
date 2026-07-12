#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
每日编排器：抓取行情 → 载入财务 → 五维评分 → 买入信号 → 历史累积 → 渲染 HTML
用法：python run_daily.py
环境变量：
  BIYING_API_KEY  必盈 API key（可选，用于财务兜底抓取）
  GITHUB_PAGES    是否输出到 docs/（默认 True）
"""
import sys, io, os, json, time
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
from datetime import datetime, timedelta

from bank_universe import all_banks
import fetch_quotes
import fetch_fundamentals as ff
from zhaozhao_five_dim import (Fundamentals, score_all, buy_signal, SIGNAL_CN)
import render_html
import render_report

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FUND_JSON = os.path.join(ROOT, "fundamentals.json")
HISTORY = os.path.join(ROOT, "history.jsonl")
DOCS = os.path.join(ROOT, "docs")

def load_fundamentals():
    if not os.path.exists(FUND_JSON):
        return {}
    with open(FUND_JSON, encoding="utf-8") as f:
        return json.load(f)

def main():
    t0 = datetime.now()
    print("=" * 60)
    print(f"招招五维 · 五大行每日追踪  {t0.strftime('%Y-%m-%d %H:%M')}")
    print("=" * 60)
    banks = all_banks()

    # 1) 财务底表（每日刷新 BVPS/ROE/EPS + 非息占比；质量字段以底表真源）
    fund_cache = load_fundamentals()
    print("\n[1] 财务底表（fundamentals.json）...")
    refreshed = ff.refresh_light(banks, fund_cache)   # BVPS/ROE/EPS（动态报告期）
    nii = ff.refresh_nii(banks)                       # 非息占比（半自动，必盈）
    merged = {}
    for b in banks:
        base = fund_cache.get(b.code, {})
        rec = dict(base)
        for src in (refreshed.get(b.code, {}), nii.get(b.code, {})):
            rec.update({k: v for k, v in src.items() if v is not None})
        rec["code"] = b.code
        rec["name"] = b.name
        rec.setdefault("as_of", base.get("as_of", "未知"))
        merged[b.code] = rec
    # 写回（仅当有新数据；质量字段因不在 refreshed/nii 中，原样保留）
    if any(refreshed.values()) or any(nii.values()):
        with open(FUND_JSON, "w", encoding="utf-8") as f:
            json.dump(merged, f, ensure_ascii=False, indent=2)
        print(f"    已刷新 {len([1 for v in refreshed.values() if v])} 只 BVPS/ROE/EPS、"
              f"{len([1 for v in nii.values() if v])} 只非息占比")

    # 2) 行情
    bvps_map = {b.code: merged[b.code].get("bvps") for b in banks}
    div_ps_map = {b.code: merged[b.code].get("div_ps") for b in banks}
    print("\n[2] 行情抓取（腾讯价 / baostock PE·PB / 底表股息）...")
    quotes = fetch_quotes.fetch_quotes(banks, bvps_map, div_ps_map)
    ok = [c for c, q in quotes.items() if q.get("price")]
    print(f"    成功 {len(ok)}/{len(banks)} 只；缺失：{set(b.code for b in banks)-set(ok)}")

    # 3) 五维评分 + 买入信号
    print("\n[3] 五维评分 + 买入信号...")
    rows = []
    for b in banks:
        q = quotes.get(b.code, {})
        f = merged.get(b.code, {})
        fun = Fundamentals(
            code=b.code, name=b.name, as_of=f.get("as_of", "未知"),
            npl=f.get("npl"), provision_coverage=f.get("provision_coverage"),
            npl_generate=f.get("npl_generate"),
            current_deposit_ratio=f.get("current_deposit_ratio"),
            deposit_ratio=f.get("deposit_ratio"),
            retail_deposit_ratio=f.get("retail_deposit_ratio"),
            non_interest_ratio=f.get("non_interest_ratio"),
            rorwa=f.get("rorwa"), core_tier1=f.get("core_tier1"),
            roe=f.get("roe"), div_payout=f.get("div_payout"),
            retail_focus=f.get("retail_focus"),
            pb=q.get("pb"), pe=q.get("pe"),
            div_yield=q.get("div_yield"), price=q.get("price"),
        )
        sc = score_all(fun)
        sig = buy_signal(fun, valuation_style=b.valuation_style)
        rows.append({
            "code": b.code, "name": b.name, "short": b.short, "color": b.color,
            "price": q.get("price"), "pe": q.get("pe"), "pb": q.get("pb"),
            "div_yield": q.get("div_yield"),
            "score": sc, "signal": sig,
        })

    # 4) 历史累积（jsonl，按日期去重）
    print("\n[4] 历史累积（history.jsonl）...")
    _append_history(rows, t0)

    # 5) 渲染 HTML
    print("\n[5] 渲染 HTML → docs/index.html ...")
    os.makedirs(DOCS, exist_ok=True)
    render_html.render(rows, merged, t0, os.path.join(DOCS, "index.html"))
    render_html.render_history(HISTORY, os.path.join(DOCS, "history.html"))

    # 6) JSON 产出（供外部 fetch 调用，对齐 xiaoxu-fear 的 xxfi_report.json）
    print("\n[6] 生成 output/cmb_report.json ...")
    out_dir = os.path.join(ROOT, "output")
    render_report.write(rows, merged, t0, os.path.join(out_dir, "cmb_report.json"))

    dt = (datetime.now() - t0).total_seconds()
    print(f"\n✅ 完成 ({dt:.1f}s)")

def _append_history(rows, t0):
    today = t0.strftime("%Y-%m-%d")
    # 去重：若今日已有记录则覆盖
    existing = []
    if os.path.exists(HISTORY):
        with open(HISTORY, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    existing.append(json.loads(line))
    existing = [e for e in existing if e.get("date") != today]
    rec = {
        "date": today,
        "banks": [
            {
                "code": r["code"], "name": r["name"],
                "price": r["price"], "pe": r["pe"], "pb": r["pb"],
                "div_yield": r["div_yield"],
                "total": r["score"]["total"],
                "signal": r["signal"]["signal"],
            }
            for r in rows
        ],
    }
    existing.append(rec)
    with open(HISTORY, "w", encoding="utf-8") as f:
        for e in existing:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")
    print(f"    历史记录 {len(existing)} 条")

if __name__ == "__main__":
    main()
