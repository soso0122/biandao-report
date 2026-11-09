#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""新账户广告组逐日追踪表（冷启动爬坡观察）

背景（用户 2026-11-06 定）：
  新账户 125240890（扩量1022）冷启动期，6 个新建组（1105-图文1/2、1105-视频1~4），
  每天和新用户讨论各组爬坡情况。本脚本输出：
    1. 各组的逐日「花费/曝光/行为/转化/行为率/转化率/CPA」表
    2. 每组的累计值 + 学习状态提示（曝光是否在放大、行为是否在攒、是否已出单）
    3. 同素材跨组合计（避免被组级随机性误导）

用法：
    python3 scripts/new_account_group_tracker.py [账户ID]
    默认账户 125240890，可传老账户 125110802 对比。
数据源：data/kuaishou_shimo_data.json（先跑 fetch_shimo_kuaishou.py）。
"""
import json
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
OUT_JSON = BASE_DIR / "data" / "kuaishou_shimo_data.json"

DEFAULT_ACCT = "125240890"


def fmt(x, dec=2):
    return f"{x:.{dec}f}"


def main():
    acct = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_ACCT
    d = json.load(open(OUT_JSON, encoding="utf-8"))
    dates = d.get("dates", [])
    groups = d.get("groups", [])
    mats = d.get("materials", [])

    # 该账户有花费/曝光的组
    rows = []
    for g in groups:
        days = {}
        for day in dates:
            v = g.get("days", {}).get(day)
            if isinstance(v, dict) and acct in v and isinstance(v[acct], dict):
                b = v[acct]
                if b.get("sp", 0) > 0 or b.get("im", 0) > 0 or b.get("ac", 0) > 0:
                    days[day] = {
                        "sp": b.get("sp", 0), "im": b.get("im", 0),
                        "ac": b.get("ac", 0), "cv": b.get("cv", 0),
                    }
        if days:
            rows.append((g.get("name", "?"), g.get("names", []), days))

    if not rows:
        print(f"⚠️ 账户 {acct} 在 data/kuaishou_shimo_data.json 中暂无组级数据（可能还没投放或未拉取最新数据）")
        return

    # 组名排序：按首个有数据日期，再按组名
    rows.sort(key=lambda x: (min(x[2].keys()), x[0]))

    print(f"=== 账户 {acct} 广告组逐日追踪（花费/曝光/行为/转化）===\n")
    for name, names, days in rows:
        print(f"【{name}】 素材 {len(names)} 条")
        for day in sorted(days):
            b = days[day]
            br = b["ac"] / b["im"] if b["im"] else 0
            cr = b["cv"] / b["ac"] if b["ac"] else 0
            cpa = b["sp"] / b["cv"] if b["cv"] else 0
            print(f"  {day[5:]}  花费{b['sp']:>7.2f} 曝光{b['im']:>6.0f} 行为{b['ac']:>4.0f} "
                  f"行为率{br:>6.2%} 转化{b['cv']:>3.0f} 转化率{cr:>6.2%} CPA {cpa:>6.2f}")
        tot = {k: sum(b[k] for b in days.values()) for k in ("sp", "im", "ac", "cv")}
        br = tot["ac"] / tot["im"] if tot["im"] else 0
        cr = tot["cv"] / tot["ac"] if tot["ac"] else 0
        cpa = tot["sp"] / tot["cv"] if tot["cv"] else 0
        # 学习状态提示
        hints = []
        if tot["im"] < 100:
            hints.append("曝光<100，冷启动未起量")
        elif len(days) >= 2:
            last2 = sorted(days)[-2:]
            if days[last2[1]]["im"] < days[last2[0]]["im"] * 0.8:
                hints.append("曝光环比萎缩")
            elif days[last2[1]]["im"] >= days[last2[0]]["im"] * 1.2:
                hints.append("曝光环比放大")
        if tot["ac"] >= 50 and tot["cv"] == 0:
            hints.append("⚠️ 累计行为≥50 仍无转化")
        if tot["cv"] > 0:
            hints.append(f"已出单 {tot['cv']:.0f} 单")
        print(f"  累计: 花费{tot['sp']:.2f} 曝光{tot['im']:.0f} 行为{tot['ac']:.0f} "
              f"行为率{br:.2%} 转化{tot['cv']:.0f} 转化率{cr:.2%} CPA {cpa:.2f}"
              + (f"  ← {'；'.join(hints)}" if hints else ""))
        print()

    # 素材维度（该账户，跨组自然合并——判断素材好坏用这张，别只看单组）
    print("=== 素材维度累计（同素材跨组合并，判断素材好坏用这张）===\n")
    mat_agg = {}
    for m in mats:
        tot = {"sp": 0, "im": 0, "ac": 0, "cv": 0}
        for day, v in m.get("days", {}).items():
            if isinstance(v, dict) and acct in v and isinstance(v[acct], dict):
                mm = v[acct].get("m", {})
                for k in tot:
                    tot[k] += mm.get(k, 0)
        if tot["sp"] > 0.01 or tot["ac"] > 0:
            mat_agg[m["name"]] = (tot, m.get("type", ""), m.get("person", ""))
    if not mat_agg:
        print("  （暂无素材级数据）")
    else:
        for mn in sorted(mat_agg, key=lambda x: -mat_agg[x][0]["sp"]):
            tot, typ, person = mat_agg[mn]
            cr = tot["cv"] / tot["ac"] if tot["ac"] else 0
            cpa = tot["sp"] / tot["cv"] if tot["cv"] else 0
            print(f"  花费{tot['sp']:>7.2f} 曝光{tot['im']:>6.0f} 行为{tot['ac']:>4.0f} "
                  f"行为率{tot['ac']/tot['im'] if tot['im'] else 0:>6.2%} 转化{tot['cv']:>3.0f} "
                  f"转化率{cr:>6.2%} CPA {cpa:>6.2f}  [{typ}|{person}] {mn[:44]}")

    print(f"\n数据源: {OUT_JSON.name}（fetched_at {d.get('fetched_at','')}）")


if __name__ == "__main__":
    main()
