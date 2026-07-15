#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
生成机器可读 JSON 报告 output/cmb_report.json。

设计对齐 xiaoxu-fear 的 xxfi_report.json：
  - 顶层放元信息（tracker / model / generated_at / data_date / summary）
  - banks 数组逐行承载五维分、估值、信号、买入区间、理由
  - 调用方用固定 raw URL 即可 fetch：
      https://raw.githubusercontent.com/homjanon/cmb-tracker/main/output/cmb_report.json
"""
import json
import os
from datetime import datetime

from zhaozhao_five_dim import SIGNAL_CN

DIM_KEYS = ["asset_quality", "liability", "intermediary", "capital", "management"]


def build(rows, merged, t0):
    """构造报告字典。rows 来自 run_daily（含 score / signal）。"""
    banks = []
    for r in rows:
        sc = r["score"]
        sig = r["signal"]
        cn, _ = SIGNAL_CN.get(sig["signal"], ("未知", "#999999"))
        dims = {k: round(sc["dims"][k]["score"], 1) for k in DIM_KEYS}
        code = r["code"]
        f = merged.get(code, {})
        banks.append({
            "code": code,
            "name": r["name"],
            "short": r["short"],
            "as_of": f.get("as_of", "未知"),
            "price": r["price"],
            "pe": r["pe"],
            "pb": r["pb"],
            "div_yield": r["div_yield"],
            "price_source": r.get("price_source"),
            "pe_source": r.get("pe_source"),
            "pb_source": r.get("pb_source"),
            "quote_time": r.get("quote_time"),
            "net_interest_margin": f.get("net_interest_margin"),
            "research_rating": f.get("research_rating"),
            "research_count_1m": f.get("research_count_1m"),
            "research_institution": f.get("research_institution"),
            "research_as_of": f.get("research_as_of"),
            # research_target_* 已移除（2026-07-15）：巨潮 stock_rank_forecast_cninfo 数据量大且不常更新
            "score_total": sc["total"],
            "score_dims": dims,
            "signal": sig["signal"],
            "signal_cn": cn,
            "valuation_style": sig.get("valuation_style", "yield"),
            "zone_low": sig.get("zone_low"),
            "zone_high": sig.get("zone_high"),
            "reason": sig.get("reason", ""),
        })

    counts = {"STRONG_BUY": 0, "BUY": 0, "HOLD": 0, "REDUCE": 0, "UNKNOWN": 0}
    for b in banks:
        counts[b["signal"]] = counts.get(b["signal"], 0) + 1

    return {
        "tracker": "cmb-tracker",
        "model": "招招五维模型",
        "generated_at": datetime.now().astimezone().isoformat(),
        "data_date": t0.strftime("%Y-%m-%d"),
        "summary": {
            "total_banks": len(banks),
            "strong_buy": counts["STRONG_BUY"],
            "buy": counts["BUY"],
            "hold": counts["HOLD"],
            "reduce": counts["REDUCE"],
        },
        "banks": banks,
    }


def write(rows, merged, t0, out_path):
    """写出 JSON 到 out_path（ensure_ascii=False, indent=2）。"""
    data = build(rows, merged, t0)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as fp:
        json.dump(data, fp, ensure_ascii=False, indent=2)
    print(f"    已写出 {out_path}（{len(data['banks'])} 只）")
