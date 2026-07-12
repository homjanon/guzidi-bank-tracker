#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
财务底表抓取与刷新

架构（落地后）：
  银行的五维财务字段分三类自动化程度：
    [自动]   BVPS / ROE(年化) / EPS(年化) / div_ps(每股分红)
             —— BVPS/ROE/EPS 每日用 akshare stock_yjbb_em 动态报告期刷新；
                div_ps 每日用 akshare stock_history_dividend_detail 取按股权登记日倒序最新2次已实施派息求和÷10（=最近一个完整年度，避免滚动365天窗口跨年抓到3次虚高）
    [半自动] 非息收入占比            —— 每日用必盈利润表(income)推算，需 BIYING_API_KEY，缺则回退手工
    [手工]   不良率/拨备/核心一级资本充足率/存款结构/RORWA/分红率(div_payout 由 div_ps÷年化EPS 自动算)
             —— 季度人工维护，见 fundamentals.json 的 _manual_maintain 标记，写回时不被覆盖
  → 设计：refresh_light() + refresh_nii() 每日调用；质量字段以 fundamentals.json 为真源。
"""

from datetime import datetime, timedelta


def _f(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def latest_report_periods(today=None):
    """按新→旧返回候选报告期(YYYYMMDD)。披露滞后规律：
       Q1(0331) 5月起 / 中报(0630) 9月起 / Q3(0930) 11月起 / 年报(1231) 次年5月起。"""
    d = today or datetime.now()
    y, m = d.year, d.month
    c = []
    if m >= 11:   c += [f"{y}0930", f"{y}0630", f"{y}0331", f"{y-1}1231"]
    elif m >= 9:  c += [f"{y}0630", f"{y}0331", f"{y-1}1231", f"{y-1}0930"]
    elif m >= 5:  c += [f"{y}0331", f"{y-1}1231", f"{y-1}0930", f"{y-1}0630"]
    else:         c += [f"{y-1}1231", f"{y-1}0930", f"{y-1}0630", f"{y-1}0331"]
    return c


def refresh_light(banks, cache: dict) -> dict:
    """每日轻量刷新 BVPS / ROE(年化) / EPS(年化)；动态报告期自动跟进。
    返回 {code: {bvps, roe, eps, as_of}}，仅在成功时返回非空字典。"""
    out = {}
    try:
        import akshare as ak
        target = {b.code for b in banks if not b.is_hk}
        chosen, df = None, None
        for period in latest_report_periods():          # 从新到旧尝试
            try:
                tmp = ak.stock_yjbb_em(date=period)
            except Exception:
                continue
            if tmp is None or getattr(tmp, "empty", True):
                continue
            got = set(str(x).strip() for x in tmp["股票代码"]) & target
            if len(got) >= max(1, len(target) // 2):      # 过半银行已披露才采用
                chosen, df = period, tmp
                break
        if df is None:
            print("    [refresh_light] 无可用报告期，沿用缓存")
            return out
        q = f"{chosen[:4]}Q{(int(chosen[4:6]) - 1) // 3 + 1}"   # 20260630 → 2026Q2
        print(f"    [refresh_light] 采用报告期 {chosen} ({q})")
        lut = {str(r.get("股票代码", "")).strip(): r for _, r in df.iterrows()}
        for b in banks:
            if b.is_hk:
                continue
            row = lut.get(b.code)
            if row is None:
                continue
            bvps = _f(row.get("每股净资产"))
            if bvps is None:
                continue
            rec = {"bvps": round(bvps, 3), "as_of": q}
            roe_q = _f(row.get("净资产收益率"))            # 季度 ROE
            eps = _f(row.get("每股收益"))
            mm = chosen[4:6]
            mult = {"03": 4, "06": 2, "09": 4 / 3, "12": 1}.get(mm, 1)   # 年化折算
            if roe_q is not None:
                rec["roe"] = round(min(roe_q * mult, 25.0), 2)          # 封顶 25
            if eps is not None:
                # EPS 与 ROE 同口径年化：季报期单季值 × mult，年报期 ×1
                rec["eps"] = round(eps * mult, 3)
            out[b.code] = rec
    except Exception as e:
        print(f"    [refresh_light] akshare yjbb 失败，沿用缓存：{e}")
    return out


def _biying_nii(code, key):
    """用必盈利润表推算单只 A 股非息占比。返回 (ratio, as_of) 或 None。"""
    import json as _json, urllib.request
    url = f"https://api.biyingapi.com/hsstock/financial/income/{code}.SH/{key}"
    with urllib.request.urlopen(url, timeout=20) as r:
        rows = _json.loads(r.read().decode("utf-8"))
    if not rows:
        return None
    rows = sorted(rows, key=lambda x: str(x.get("plrq") or x.get("jzrq") or ""), reverse=True)
    last = rows[0]
    rev = _f(last.get("yysr") or last.get("yyzsr"))
    if not rev:
        return None
    nii = sum(_f(last.get(k)) or 0 for k in
              ["sxfjyjsr", "tzsy", "gyjzbdsy", "hdsy", "qtywsr"])
    ratio = round(nii / rev * 100, 1)
    if 0 < ratio < 100:
        return ratio, str(last.get("jzrq") or last.get("plrq"))[:8]
    return None


def refresh_nii(banks) -> dict:
    """半自动：必盈利润表推算非息占比。需 BIYING_API_KEY；缺 key/失败则跳过(保持手工值)。
    返回 {code: {non_interest_ratio, nii_as_of}}。"""
    import os
    key = os.environ.get("BIYING_API_KEY")
    if not key:
        print("    [refresh_nii] 未设 BIYING_API_KEY，跳过（保持手工值）")
        return {}
    out = {}
    for b in banks:
        if b.is_hk:
            continue
        try:
            res = _biying_nii(b.code, key)
            if res:
                ratio, as_of = res
                out[b.code] = {"non_interest_ratio": ratio, "nii_as_of": as_of}
                print(f"    [refresh_nii] {b.code} 非息占比 ≈ {ratio}% (as_of {as_of})")
        except Exception as e:
            print(f"    [refresh_nii] {b.code} 失败，保持手工值：{e}")
    return out


def refresh_div(banks) -> dict:
    """自动获取每股分红 (div_ps)。派息单位=元/10股→÷10。
    取最近一个完整年度 = 按股权登记日倒序取最新 2 次「实施」派息求和÷10。
    说明：组合内 6 家银行均为半年派，最新 2 次恰好等于一个财年，避免滚动 365
    天窗口在跨年交界抓到 3 次分红导致 div_ps / 股息率 / 派息率虚高。
    返回 {code: {div_ps, div_as_of}}（div_payout 在 run_daily.py merge 阶段根据 eps 计算）。"""
    out = {}
    today_d = datetime.now().date()
    try:
        import akshare as ak
        import pandas as pd
        for b in banks:
            if b.is_hk:
                continue
            df = ak.stock_history_dividend_detail(symbol=b.code, indicator="分红")
            if df is None or df.empty:
                continue
            imp = df[df["进度"] == "实施"].copy()
            if imp.empty:
                continue
            # 解析股权登记日为 date，仅保留最近 18 个月内，按倒序取最新 2 笔
            recs = []
            for _, r in imp.iterrows():
                d = r.get("股权登记日")
                if pd.isna(d):
                    continue
                if hasattr(d, "date"):
                    d = d.date()
                if (today_d - d).days <= 540:  # 18 个月
                    recs.append((d, float(r["派息"])))
            recs.sort(key=lambda x: x[0], reverse=True)
            pick = recs[:2] if len(recs) >= 2 else recs
            total_10 = sum(x[1] for x in pick)
            if total_10 > 0:
                div_ps = round(total_10 / 10, 3)
                rec = {"div_ps": div_ps, "div_as_of": today_d.strftime("%Y%m%d")}
                out[b.code] = rec
                dates = ",".join(str(x[0]) for x in pick)
                print(f"    [refresh_div] {b.code} div_ps={div_ps} (近2次派息 {dates}, 合计{total_10}/10)")
    except Exception as e:
        print(f"    [refresh_div] 失败: {e}")
    return out


def refresh_deep(banks, cache: dict) -> dict:
    """深度刷新（季度/手动，休眠不用）：质量字段仍以 fundamentals.json 真源手工维护。
    必盈非息占比已独立由 refresh_nii 提供；不良率/拨备/资本充足率无免费机器接口，维持手工。"""
    return {}
