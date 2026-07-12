#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
校准工具：打印 fundamentals.json 中每只银行的五维评分与缺失字段，辅助手工维护。
用法：python calibration.py
"""
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bank_universe import all_banks
from guzidi_five_dim import Fundamentals, score_all

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
with open(os.path.join(ROOT, "fundamentals.json"), encoding="utf-8") as f:
    cache = json.load(f)

print("银行".ljust(10), "总分".rjust(6), " 缺失字段", "  as_of")
print("-" * 60)
for b in all_banks():
    f = cache.get(b.code, {})
    fun = Fundamentals(
        code=b.code, name=b.name, as_of=f.get("as_of", "?"),
        npl=f.get("npl"), provision_coverage=f.get("provision_coverage"),
        current_deposit_ratio=f.get("current_deposit_ratio"),
        retail_deposit_ratio=f.get("retail_deposit_ratio"),
        non_interest_ratio=f.get("non_interest_ratio"),
        rorwa=f.get("rorwa"), core_tier1=f.get("core_tier1"),
        roe=f.get("roe"), div_payout=f.get("div_payout"),
        retail_focus=f.get("retail_focus"),
    )
    sc = score_all(fun)
    miss = fun.missing()
    print(f"{b.name}({b.code})".ljust(14), f"{sc['total']:.0f}".rjust(5),
          f"  {miss if miss else '无'}", f"  {fun.as_of}")
