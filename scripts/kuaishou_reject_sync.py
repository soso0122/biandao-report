#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""快手拒审台账同步：解析创意列表粘贴文本 → 匹配/追加石墨「拒审台账」 → 回写分类列 → 输出对话清单

用法：
  cat paste.txt | python3 scripts/kuaishou_reject_sync.py MMDD          # dry-run，只打印计划
  cat paste.txt | python3 scripts/kuaishou_reject_sync.py MMDD --apply  # 真正写石墨
  python3 scripts/kuaishou_reject_sync.py MMDD --file paste.txt --apply

台账列（0-based）：
  A上传日期 B视频名称(=M) C审核状态(=O) D创建时间 E时长 F视频来源 G视频素材评价(=AJ)
  H刚投放就拒审 I有消耗后拒审 J投放后限流
  K视频ID L视频标识 M视频名称 N视频标签 O审核状态(贴) P创建时间 ... T花费 ... AJ视频素材评价

回写规则（与用户确认）：
  - 审核未通过 + 花费=0  → H列打√（刚投放就拒审）
  - 审核未通过 + 花费>0  → I列打√（有消耗后拒审）
  - 投放中(部分流量未投放) → J列打√（投放后限流）
  - 投放中(部分流量未通过) → C列标注「⏳待复核(部分流量未通过)」（需用户点开复核是广告还是内容卡住）
  - 匹配：创意名称 == 台账 M列「视频名称」（B列为公式镜像，跳过）
  - 未匹配且需要关注的条目：在台账尾部追加新行（A=日期 B=名称 C=状态 H/I/J按类打√）
  - 正常投放中：不动，仅计数
"""
import json
import re
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from kuaishou_reject_parse import parse, classify          # noqa: E402
from fetch_shimo_kuaishou import ShimoClient, FILE_GUID    # noqa: E402

SHEET = "拒审台账"
COL_END = "AJ"        # 36 列
PAGE_ROWS = 130       # 36 × 130 = 4680 单元格 < 5000

C_A, C_B, C_C = 0, 1, 2          # A上传日期 B视频名称 C审核状态
C_H, C_I, C_J = 7, 8, 9          # H刚投放就拒审 I有消耗后拒审 J投放后限流
C_M = 12                          # M视频名称（素材级名称，匹配键）
C_O = 14                          # O审核状态（素材库导出粘贴列）

COL_LETTER = {C_A: "A", C_B: "B", C_C: "C", C_H: "H", C_I: "I", C_J: "J"}

WAIT_REVIEW = "⏳待复核(部分流量未通过)"


def col_letter(i):
    s = ""
    while i >= 0:
        s = chr(65 + i % 26) + s
        i = i // 26 - 1
    return s


def cell(sheet, col, row1):
    return f"{sheet}!{col_letter(col)}{row1}"


def read_ledger(client):
    """读整张拒审台账，返回 (rows_1based: list[list], first_empty_row: int)"""
    rows = []          # 每项为原始行（含 None）
    start = 1
    seen = set()
    while True:
        r = client.call("shimo_get_spreadsheet_content",
                        {"file_guid": FILE_GUID, "range": f"{SHEET}!A{start}:{COL_END}{start + PAGE_ROWS - 1}"})
        if not r:
            raise SystemExit("读台账无响应")
        content = r.get("result", {})
        texts = [c.get("text", "") for c in (content.get("content") or []) if c.get("type") == "text"]
        txt = "\n".join(texts)
        if "failed" in txt:
            raise SystemExit(f"读台账失败: {txt[:300]}")
        try:
            vals = json.loads(txt).get("values")
        except Exception:
            raise SystemExit(f"读台账解析失败: {txt[:300]}")
        if not vals:
            break
        page_rows = [v for v in vals if any(x is not None and str(x).strip() for x in v)]
        for v in page_rows:
            sig = tuple("" if x is None else str(x)[:80] for x in v)
            if sig in seen:
                continue
            seen.add(sig)
            rows.append({"rn": start + len(rows), "vals": v})
        if len(page_rows) < PAGE_ROWS:
            break
        start += PAGE_ROWS
    last = max([r["rn"] for r in rows], default=1)
    return rows, last + 1


def name_index(rows):
    """M列视频名称 → 台账行号（1-based）；B列做兜底（跳过公式镜像）"""
    idx = {}
    for r in rows:
        v = r["vals"]
        m = (v[C_M] if len(v) > C_M else None)
        m = str(m).strip() if m is not None else ""
        if m:
            idx.setdefault(m, r["rn"])
        b = (v[C_B] if len(v) > C_B else None)
        b = str(b).strip() if b is not None else ""
        if b and not b.startswith("=") and b not in idx:
            idx[b] = r["rn"]
    return idx


def cur_val(rows, rn, col):
    for r in rows:
        if r["rn"] == rn:
            v = r["vals"][col] if len(r["vals"]) > col else None
            return "" if v is None else str(v).strip()
    return ""


def plan(blocks, rows, date_str):
    """返回 (writes: list[(rn,col,val)], appends: list[dict], summary)"""
    idx = name_index(rows)
    first_empty = max([r["rn"] for r in rows], default=1) + 1
    writes, appends = [], []
    seen_names = set()   # 本批已处理名称，防同批同名重复追加
    summary = {"待复核": [], "刚投放就拒审": [], "有消耗后拒审": [], "投放后限流": [], "正常": 0, "未知": []}

    for b in blocks:
        name = (b.get("创意名称") or "").strip()
        status = (b.get("状态") or "").strip()
        cls = classify(b)
        try:
            spend = float(b.get("花费(元)") or 0)
        except ValueError:
            spend = 0.0
        if cls == "正常投放中":
            summary["正常"] += 1
            continue
        if cls == "未知":
            summary["未知"].append(name)
            continue
        if name in seen_names:
            continue
        seen_names.add(name)
        row = idx.get(name)
        if cls == "待复核(部分流量未通过)":
            summary["待复核"].append(name)
            if row:
                cur = cur_val(rows, row, C_C)
                if not cur or cur.startswith("="):
                    writes.append((row, C_C, WAIT_REVIEW))
            else:
                appends.append({"名称": name, "状态": WAIT_REVIEW, "列": None})
            continue
        col = {"刚投放就拒审": C_H, "有消耗后拒审": C_I, "投放后限流": C_J}[cls]
        summary[cls].append(name)
        if row:
            cur = cur_val(rows, row, col)
            if not cur:
                writes.append((row, col, "√"))
        else:
            appends.append({"名称": name, "状态": status, "列": col})
    return writes, appends, summary, first_empty


def fmt_list(title, items):
    if not items:
        return ""
    return f"**{title}**\n" + "\n".join(f"- {x}" for x in items) + "\n"


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    apply = "--apply" in sys.argv
    mmdd = args[0] if args else datetime.now().strftime("%m%d")
    fname = None
    for i, a in enumerate(sys.argv[1:]):
        if a == "--file" and i + 2 < len(sys.argv):
            fname = sys.argv[i + 2]
    text = open(fname, encoding="utf-8").read() if fname else sys.stdin.read()
    yy = str(datetime.now().year)
    date_str = f"{yy}-{mmdd[:2]}-{mmdd[2:4]}" if mmdd.isdigit() and len(mmdd) == 4 else mmdd

    blocks = parse(text)
    if not blocks:
        raise SystemExit("没解析出任何创意块，请检查粘贴格式")
    print(f"[解析] {len(blocks)} 块")

    client = ShimoClient()
    client.start()
    try:
        rows, first_empty = read_ledger(client)
        print(f"[台账] 现有 {len(rows)} 行，追加起点 行{first_empty}")
        writes, appends, summary, fe = plan(blocks, rows, date_str)

        print("\n===== 计划（dry-run）=====" if not apply else "\n===== 执行 =====")
        fe_show = fe
        for rn, col, val in writes:
            print(f"  写 {cell(SHEET, col, rn)} = {val}")
        for a in appends:
            print(f"  追加行 {fe_show}: A={date_str} B={a['名称']} C={a['状态']}"
                  + (f" {COL_LETTER[a['列']]}=√" if a["列"] is not None else ""))
            fe_show += 1
        if not writes and not appends:
            print("  （无写入）")

        # 对话清单（dry-run 也打印）
        print("\n===== 对话清单 =====")
        print(fmt_list("⏳待复核（投放中-部分流量未通过，需点开看是广告还是内容卡住）", summary["待复核"]), end="")
        print(fmt_list("🚫刚投放就拒审（花费0）", summary["刚投放就拒审"]), end="")
        print(fmt_list("🚫有消耗后拒审（花费>0）", summary["有消耗后拒审"]), end="")
        print(fmt_list("⚠️投放后限流（部分流量未投放）", summary["投放后限流"]), end="")
        if summary["未知"]:
            print(fmt_list("❓无法归类", summary["未知"]), end="")
        print(f"正常投放中 {summary['正常']} 条（未改动）")

        if not apply:
            print("\n未加 --apply，仅预览。")
            return

        # 真正写入
        for rn, col, val in writes:
            r = client.call("shimo_update_spreadsheet",
                            {"file_guid": FILE_GUID, "range": cell(SHEET, col, rn),
                             "values": [[val]]})
            print(f"  已写 {cell(SHEET, col, rn)} = {val}"
                  if r and "failed" not in json.dumps(r.get("result", {}))[:200]
                  else f"  写入失败 {cell(SHEET, col, rn)}")
        for a in appends:
            rn = fe
            values = [""] * (C_J + 1)
            values[C_A], values[C_B], values[C_C] = date_str, a["名称"], a["状态"]
            if a["列"] is not None:
                values[a["列"]] = "√"
            r = client.call("shimo_update_spreadsheet",
                            {"file_guid": FILE_GUID, "range": f"{SHEET}!A{rn}:J{rn}",
                             "values": [values]})
            print(f"  已追加行 {rn}: {a['名称']}")
            fe += 1
        print("\n✅ 台账回写完成")
    finally:
        client.stop()


if __name__ == "__main__":
    main()
