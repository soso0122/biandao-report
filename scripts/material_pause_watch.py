#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""快手素材关停-复开台账（material pause ledger）

背景（用户 2026-11-06 定）：
  用户会手动关闭素材当天的投放开关（规则：单日花费>20 仍无转化 → 关当日开关），
  但经常忘记复开，导致素材一次之后再也没机会。本台账负责兜底：
    1. 手动关停可登记（--pause），到期自动提醒复开（关停满 2 天）
    2. 数据侧自动检测：最新一天花费归零、前一天还有花费（>=1元）的素材 → 记入台账
    3. 台账中「已关停」素材一旦重新有花费 → 自动标记「已复开」
    4. 每次跑快手更新流程时输出「今日该复开」清单，贴在聊天框第一屏

用法：
    python3 scripts/material_pause_watch.py                # 扫描 data/kuaishou_shimo_data.json + 输出清单
    python3 scripts/material_pause_watch.py --list         # 只看台账清单，不做数据扫描
    python3 scripts/material_pause_watch.py --pause 素材名 [--reason 原因]   # 手动登记关停
    python3 scripts/material_pause_watch.py --reopen 素材名                 # 手动登记复开
    python3 scripts/material_pause_watch.py --drop 素材名                   # 降级：不再提醒复开

台账文件：data/material_pause_ledger.csv
列：素材名称,账户ID,类型,编导,关停日期,原因,状态,复开日期,备注
状态：已关停 / 已复开 / 已降级
"""
import csv
import json
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
OUT_JSON = DATA_DIR / "kuaishou_shimo_data.json"
LEDGER = DATA_DIR / "material_pause_ledger.csv"

MIN_PAUSE_SPEND = 1.0   # 自动检测阈值：前一天花费 >= 1 元才算「有投放」，过滤撒胡椒面噪声
REOPEN_AFTER_DAYS = 2   # 关停满 2 天进入「该复开」清单

COLS = ["素材名称", "账户ID", "类型", "编导", "关停日期", "原因", "状态", "复开日期", "备注"]


def read_ledger():
    rows = []
    if LEDGER.exists():
        with open(LEDGER, encoding="utf-8-sig", newline="") as fh:
            for r in csv.DictReader(fh):
                rows.append(r)
    return rows


def write_ledger(rows):
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    with open(LEDGER, "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=COLS)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in COLS})


def load_json():
    if not OUT_JSON.exists():
        print("⚠️ 未找到 data/kuaishou_shimo_data.json，请先运行 scripts/fetch_shimo_kuaishou.py")
        sys.exit(1)
    return json.load(open(OUT_JSON, encoding="utf-8"))


def material_spend(m, day):
    """某素材某天所有账户的花费合计"""
    v = m.get("days", {}).get(day)
    if not isinstance(v, dict):
        return 0.0
    s = 0.0
    for acct, body in v.items():
        if isinstance(body, dict) and isinstance(body.get("m"), dict):
            s += float(body["m"].get("sp", 0) or 0)
    return s


def find_material(name, mats):
    """精确匹配优先；否则唯一子串匹配"""
    exact = [m for m in mats if m["name"] == name]
    if exact:
        return exact[0]
    fuzzy = [m for m in mats if name in m["name"]]
    if len(fuzzy) == 1:
        return fuzzy[0]
    if len(fuzzy) > 1:
        print(f"❌ 「{name}」匹配到多条素材，请用更精确的名称：")
        for m in fuzzy:
            print("   -", m["name"])
        sys.exit(1)
    return None


def latest_spend_account(m, day):
    """某素材某天有花费的账户（第一个），用于台账登记账户ID"""
    v = m.get("days", {}).get(day)
    if isinstance(v, dict):
        for acct, body in v.items():
            if isinstance(body, dict) and isinstance(body.get("m"), dict):
                if float(body["m"].get("sp", 0) or 0) > 0:
                    return acct
    return "—"


def main():
    args = sys.argv[1:]
    mode = args[0] if args and args[0].startswith("--") else ""
    mats = load_json().get("materials", [])
    ledger = read_ledger()
    today = date.today().isoformat()
    changed = False

    def open_row_for(name, acct="—"):
        for r in ledger:
            if r.get("状态") == "已关停" and r.get("素材名称") == name:
                return r
        return None

    if mode == "--pause":
        name = args[1] if len(args) > 1 else ""
        m = find_material(name, mats)
        if not m:
            print(f"❌ 未找到素材：「{name}」")
            sys.exit(1)
        if open_row_for(m["name"]):
            print(f"⚠️ 「{m['name']}」已在台账中（已关停），无需重复登记")
        else:
            reason = ""
            if "--reason" in args:
                reason = args[args.index("--reason") + 1]
            d = load_json().get("dates", [])
            last_day = d[-1] if d else today
            ledger.append({
                "素材名称": m["name"], "账户ID": latest_spend_account(m, last_day) if d else "—",
                "类型": m.get("type", ""), "编导": m.get("person", ""),
                "关停日期": today, "原因": reason or "手动关停",
                "状态": "已关停", "复开日期": "", "备注": "",
            })
            changed = True
            print(f"✅ 已登记关停：{m['name']}（{today}，满 {REOPEN_AFTER_DAYS} 天后提醒复开）")

    elif mode == "--reopen":
        name = args[1] if len(args) > 1 else ""
        m = find_material(name, mats) or ({"name": name} if name else None)
        row = open_row_for(m["name"]) if m else None
        if not row:
            print(f"⚠️ 台账中没有「已关停」状态的「{name}」")
        else:
            row["状态"] = "已复开"
            row["复开日期"] = today
            row["备注"] = (row.get("备注") or "") + " 手动复开"
            changed = True
            print(f"✅ 已标记复开：{m['name']}")

    elif mode == "--drop":
        name = args[1] if len(args) > 1 else ""
        m = find_material(name, mats) or ({"name": name} if name else None)
        row = open_row_for(m["name"]) if m else None
        if not row:
            print(f"⚠️ 台账中没有「已关停」状态的「{name}」")
        else:
            row["状态"] = "已降级"
            row["备注"] = (row.get("备注") or "") + " 降级不再提醒"
            changed = True
            print(f"✅ 已降级（不再提醒复开）：{m['name']}")

    elif mode in ("", "--list"):
        if mode == "":
            # 自动扫描：最新两天对比 + 复开检测
            d = load_json()
            dates = d.get("dates", [])
            if len(dates) >= 2:
                y_day, t_day = dates[-2], dates[-1]
                added = []
                for m in mats:
                    sp_y, sp_t = material_spend(m, y_day), material_spend(m, t_day)
                    if sp_y >= MIN_PAUSE_SPEND and sp_t == 0 and not open_row_for(m["name"]):
                        ledger.append({
                            "素材名称": m["name"],
                            "账户ID": latest_spend_account(m, y_day),
                            "类型": m.get("type", ""), "编导": m.get("person", ""),
                            "关停日期": t_day, "原因": f"自动检测：{y_day[5:]}花费{sp_y:.2f}，{t_day[5:]}归零",
                            "状态": "已关停", "复开日期": "", "备注": "",
                        })
                        added.append((m["name"], sp_y))
                        changed = True
                if added:
                    print(f"🆕 自动检测新增关停 {len(added)} 条（{y_day[5:]}→{t_day[5:]}）：")
                    for name, sp in sorted(added, key=lambda x: -x[1]):
                        print(f"   - {name}（昨花费 {sp:.2f}）")
                    print()
            # 复开检测：已关停素材重新有花费
            reopened = []
            for r in ledger:
                if r.get("状态") != "已关停":
                    continue
                m = find_material(r["素材名称"], mats)
                if not m:
                    continue
                pause_d = r.get("关停日期", "")
                first = None
                for day in sorted(m.get("days", {}).keys()):
                    if pause_d and day > pause_d and material_spend(m, day) > 0:
                        first = day
                        break
                if first:
                    r["状态"] = "已复开"
                    r["复开日期"] = first
                    r["备注"] = (r.get("备注") or "") + " 自动复开"
                    reopened.append((r["素材名称"], first))
                    changed = True
            if reopened:
                print(f"🔓 自动检测到复开 {len(reopened)} 条（重新有花费）：")
                for name, day in reopened:
                    print(f"   - {name}（{day}）")
                print()

        # 输出清单
        due, waiting, dropped = [], [], []
        for r in ledger:
            st = r.get("状态")
            if st == "已关停":
                try:
                    days = (date.today() - datetime.strptime(r["关停日期"], "%Y-%m-%d").date()).days
                except (ValueError, TypeError):
                    days = 0
                (due if days >= REOPEN_AFTER_DAYS else waiting).append((r, days))
            elif st == "已降级":
                dropped.append(r)
        if due:
            print(f"📋 今日该复开（关停已满 {REOPEN_AFTER_DAYS} 天，共 {len(due)} 条）：")
            for r, days in sorted(due, key=lambda x: x[0]["关停日期"]):
                print(f"   1️⃣ {r['素材名称']}（{r['关停日期']}关停，已 {days} 天｜原因：{r.get('原因','')}）")
        else:
            print("📋 今日无待复开素材 ✅")
        if waiting:
            print(f"\n⏳ 仍在关停观察期（未满 {REOPEN_AFTER_DAYS} 天，共 {len(waiting)} 条）：")
            for r, days in sorted(waiting, key=lambda x: x[0]["关停日期"]):
                print(f"   · {r['素材名称']}（{r['关停日期']}，已 {days} 天）")
        print(f"\n台账：已关停 {len(due)+len(waiting)} 条 / 已降级 {len(dropped)} 条 / 历史已复开 {sum(1 for r in ledger if r.get('状态')=='已复开')} 条 → {LEDGER}")
    else:
        print(__doc__)
        sys.exit(1)

    if changed:
        write_ledger(ledger)


if __name__ == "__main__":
    main()
