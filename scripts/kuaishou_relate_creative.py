#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""快手「拒审台账-子账户」关联创意回写

用户从快手素材库页面复制文本（块状：名称 / ID：xxx / 各行含 创建时间+关联创意数+...），
本脚本按【素材名称】匹配台账 B 列（与粘贴顺序无关），把「关联创意数」原样写入 H 列「关联创意」。

名称归一化：去首尾空格；名称首部「图文」前缀去掉一次（素材库粘贴带类型前缀，台账不带）。

特殊处理：
  - 粘贴名称多「AI修复」前缀（AI修复AI拒审修复_xxx）→ 台账「AI拒审修复_xxx」做前缀回退匹配
  - 同名多条（AI拒审修复_2026110323:57 ×2）→ 用视频ID前6位对应，剩余1:1按排除法分配，结果打印待复核
  - 台账有行但粘贴无此名称 → 写空串并打印提醒

用法：
  python3 scripts/kuaishou_relate_creative.py --paste paste.txt          # dry-run 预览
  python3 scripts/kuaishou_relate_creative.py --paste paste.txt --apply  # 真正写入石墨
"""
import json
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fetch_shimo_kuaishou import ShimoClient, FILE_GUID  # noqa: E402

EXCEL_EPOCH = datetime(1899, 12, 30)

SHEET = "拒审台账-子账户"   # 默认子账户；主账户用 --sheet 拒审台账-主账户
COL_B = 1    # 视频名称（匹配键）
COL_C = 2    # 审核状态（上传卡审判定源，MCP 读回的是解析后的值）
COL_H = 7    # 关联创意（写入列）
COL_I = 8    # 上传卡审（写入列：审核状态=审核未通过 → 1）
COL_J = 9    # 投放卡审（写入列：关联创意含未通过 且 审核状态≠审核未通过 → 1）
COL_K = 11   # 视频ID（L列；表结构 2026-11-11 新增「卡审详情」后右移）

TS = re.compile(r"20\d\d-\d\d-\d\d \d\d:\d\d:\d\d")


def norm_paste_name(n):
    """粘贴侧名称归一：剥掉平台 UI 加的类型前缀「图文」一个（图文集合 的第二个图文是名字本体，不动）"""
    n = n.strip()
    if n.startswith("图文"):
        n = n[2:].strip()
    return n


def norm_sheet_name(n):
    """台账侧名称归一：只去空格，不剥任何前缀（图文集合 是真名的一部分）"""
    return n.strip()


def parse_material_paste(text):
    """素材库粘贴文本 → [{name, norm, id, links, status, tags, created, dur, source}]

    块结构（素材库页面复制）：
      [图文]素材名
      ID：xxx
      视频标签           (可能为空或 历史跑/爆、1022扩量 等)
      审核状态           (- / 审核通过 / 审核未通过)
      查看原因           (仅审核未通过时有)
      可用
      原创\t创建时间\t关联创意数\t关联素材包\t视频时长\t视频来源\t花费(元)\t封面曝光数...
    """
    chunks = [c.strip() for c in re.split(r"\n\s*\n", text) if c.strip()]
    out = []
    for ch in chunks:
        lines = [l.rstrip() for l in ch.split("\n")]
        id_line = None
        for i, l in enumerate(lines):
            if l.startswith("ID："):
                id_line = i
                break
        if id_line is None:
            continue
        vid = lines[id_line][3:].strip()
        # 名称 = ID 行之前最近的非空行
        name = None
        for l in reversed(lines[:id_line]):
            if l.strip():
                name = l.strip()
                break
        if not name:
            continue
        # 数据行：含时间戳且含 tab
        data_line = None
        for l in lines:
            if "\t" in l and TS.search(l):
                data_line = l
                break
        parts = data_line.split("\t") if data_line else []
        # 找到时间戳列位置
        ts_idx = None
        for i, p in enumerate(parts):
            if TS.fullmatch(p.strip()):
                ts_idx = i
                break
        def at(idx):
            return parts[idx].strip() if 0 <= idx < len(parts) else ""
        links = at(ts_idx + 1) if ts_idx is not None else ""
        created = at(ts_idx) if ts_idx is not None else ""
        pack = at(ts_idx + 2) if ts_idx is not None else ""
        # 时长/来源在数据行里；时长是 00:xx / '-'，来源是 本地上传/AI修复
        dur, source = "", ""
        if ts_idx is not None:
            rest = parts[ts_idx + 2:]
            for p in rest:
                if re.fullmatch(r"\d\d:\d\d(:\d\d)?", p.strip()):
                    dur = p.strip()
                    break
            for p in rest:
                if p.strip() in ("本地上传", "AI修复"):
                    source = p.strip()
                    break
        # 来源之后的 16 个数字列 = U..AJ 指标
        metrics = []
        if ts_idx is not None:
            src_idx = None
            for i in range(ts_idx + 2, len(parts)):
                if parts[i].strip() in ("本地上传", "AI修复"):
                    src_idx = i
                    break
            if src_idx is not None:
                metrics = [p.strip() for p in parts[src_idx + 1:]][:16]
        # ID行之后、数据行之前：标签/状态/可用 等（数据行之前逐行）
        tail = lines[id_line + 1:]
        if data_line:
            tail = [l for l in tail if l != data_line]
        # 去掉 查看原因 / 可用 / 原创 之类已知行后，第一行=标签、剩余找状态
        status = ""
        tags = ""
        statuses = ("-", "审核通过", "审核未通过")
        non_junk = [l for l in tail if l.strip() not in ("查看原因", "可用", "原创", "...")]
        # 标签：第一行如果不是状态、也不是视频来源
        if non_junk:
            first = non_junk[0].strip()
            if first not in statuses and not first.startswith("原创"):
                tags = first
        for l in tail:
            s = l.strip()
            if s in statuses:
                status = s
                break
        out.append({"name": name, "norm": norm_paste_name(name), "id": vid,
                    "links": links, "status": status, "tags": tags,
                    "created": created, "dur": dur, "source": source,
                    "pack": pack, "metrics": metrics})
    return out


def read_sheet(client, sheet_name=None):
    sn = sheet_name or SHEET
    rows = []
    start = 1
    while True:
        r = client.call("shimo_get_spreadsheet_content",
                        {"file_guid": FILE_GUID, "range": f"{sn}!A{start}:L{start + 199}"})
        if not r:
            raise SystemExit("读表无响应")
        txt = [c.get("text", "") for c in (r.get("result", {}).get("content") or []) if c.get("type") == "text"]
        try:
            vals = json.loads("\n".join(txt)).get("values") or []
        except Exception:
            raise SystemExit("读表解析失败")
        if not vals:
            break
        nonempty = [v for v in vals if any(x not in (None, "") for x in v)]
        rows.extend(vals)
        if len(nonempty) < 200:
            break
        start += 200
    out = []
    for i, v in enumerate(rows):
        rn = i + 1
        b = str(v[COL_B]).strip() if len(v) > COL_B and v[COL_B] is not None else ""
        c = str(v[COL_C]).strip() if len(v) > COL_C and v[COL_C] is not None else ""
        h = str(v[COL_H]).strip() if len(v) > COL_H and v[COL_H] is not None else ""
        i_cur = str(v[COL_I]).strip() if len(v) > COL_I and v[COL_I] is not None else ""
        j_cur = str(v[COL_J]).strip() if len(v) > COL_J and v[COL_J] is not None else ""
        vid = str(v[COL_K]).strip() if len(v) > COL_K and v[COL_K] is not None else ""
        if i == 0 or b:
            out.append({"rn": rn, "name": b, "norm": norm_sheet_name(b), "id": vid,
                        "C": c, "H": h, "I": i_cur, "J": j_cur})
    return out


def main():
    args = sys.argv[1:]
    # --sheet 目标表名（默认子账户）
    sheet_name = SHEET
    if "--sheet" in args:
        sheet_name = args[args.index("--sheet") + 1]
    apply = "--apply" in args

    # --paste 可选；不给就只做 I/J 补写（上传/投放卡审）
    pfile = None
    if "--paste" in args:
        pfile = args[args.index("--paste") + 1]

    paste = parse_material_paste(open(pfile, encoding="utf-8").read()) if pfile else []
    print(f"[粘贴] 解析 {len(paste)} 条 (sheet={sheet_name})")

    client = ShimoClient()
    client.start()
    try:
        sheet = read_sheet(client, sheet_name)
        rows = [s for s in sheet if s["rn"] > 1]
        print(f"[台账] {len(rows)} 行")

        p_map = {}
        for p in paste:
            p_map.setdefault(p["norm"], []).append(p)

        writes = []        # (rn, H value)  只含「粘贴里匹配到的行」或全量模式下的空值行
        writes_i = []      # (rn, I value)
        writes_j = []      # (rn, J value)
        unmatched = []     # 台账有、粘贴无
        matched = []       # 本次粘贴匹配到的行号
        for s in rows:
            h_new = s["H"]          # 默认维持现状
            if paste:      # 有粘贴才推 H 列
                cand = p_map.get(s["norm"], [])
                if not cand and not s["norm"].startswith("AI修复"):
                    cand = p_map.get("AI修复" + s["norm"], [])
                if not cand:
                    unmatched.append(s)
                    continue        # 增量模式：未匹配的行不写（保留原值）
                matched.append(s["rn"])
                if len(cand) == 1:
                    h_new = cand[0]["links"] or ""
                else:
                    # 多条候选：按视频ID最长公共前缀唯一匹配
                    prefs = []
                    for c in cand:
                        plen = 0
                        for a, b in zip(s["id"], c["id"]):
                            if a == b:
                                plen += 1
                            else:
                                break
                        prefs.append((plen, c))
                    prefs.sort(key=lambda x: -x[0])
                    if prefs[0][0] > prefs[1][0]:                       # 最长前缀唯一
                        h_new = prefs[0][1]["links"] or ""
                    elif len({p[1]["links"] for p in prefs}) == 1:      # 关联值相同，写谁一样
                        h_new = prefs[0][1]["links"] or ""
                    else:
                        h_new = "❓待定"
                        print(f"  ⚠️ 行{s['rn']} {s['norm']} 多条候选且无法按ID区分，标记待定："
                              + " ".join(f"{c['id']}({c['links']})" for c in cand))
                if h_new != s["H"]:
                    writes.append((s["rn"], h_new))

            # I 上传卡审：C列审核状态 = 审核未通过 → 1
            i_val = "1" if s["C"] == "审核未通过" else ""
            if s["I"] != i_val:
                writes_i.append((s["rn"], i_val))
            # J 投放卡审：H(关联创意新值)含"未通过" 且 C列 ≠ 审核未通过 → 1
            j_val = "1" if ("未通过" in h_new and s["C"] != "审核未通过") else ""
            if s["J"] != j_val:
                writes_j.append((s["rn"], j_val))

        if unmatched:
            print(f"\n⚠️ 台账有、本次粘贴无（{len(unmatched)} 行，跳过不写）：")
            for s in unmatched[:10]:
                print(f"  行{s['rn']}: {s['name']}")

        # ---- 追加：粘贴里有、台账里没有的素材（按与上面相同的匹配规则回放，记录被消耗的条目）----
        consumed_ids = set()
        for s in rows:
            cand = p_map.get(s["norm"], [])
            if not cand and not s["norm"].startswith("AI修复"):
                cand = p_map.get("AI修复" + s["norm"], [])
            if not cand:
                continue
            if len(cand) == 1:
                consumed_ids.add(cand[0]["id"])
            else:
                prefs = sorted(
                    ((sum(1 for a, b in zip(s["id"], c["id"]) if a == b), c) for c in cand),
                    key=lambda x: -x[0])
                if prefs[0][0] > prefs[1][0]:
                    consumed_ids.add(prefs[0][1]["id"])
                elif len({p[1]["links"] for p in prefs}) == 1:
                    consumed_ids.add(prefs[0][1]["id"])
        appends = [p for p in paste if p["id"] not in consumed_ids]
        if appends:
            print(f"\n➕ 新增素材 {len(appends)} 条，将追加到表尾：")
            for p in appends:
                print(f"   + {p['norm'][:30]} | 状态={p['status']} | 关联={p['links']}")

        def append_row(p):
            """把一条素材库条目转成台账行（A..AK 37 列）"""
            row = [""] * 37
            created = p["created"] or ""
            dur = p["dur"] or ""
            # A 上传日期 / D 创建时间 / Q 创建时间
            row[0] = created
            row[3] = created
            row[16] = created          # Q
            # B/N 视频名称（台账侧无图文前缀）
            row[1] = p["norm"]
            row[13] = p["norm"]        # N
            # C/P 审核状态
            row[2] = p["status"]
            row[15] = p["status"]      # P
            # E/S 时长（图文为 '-'）
            row[4] = dur if dur else "-"
            row[18] = dur if dur else "-"   # S
            # F/T 视频来源
            row[5] = p["source"] or "本地上传"
            row[19] = p["source"] or "本地上传"   # T
            # G/AK 视频素材评价
            row[6] = "原创；-"
            row[36] = "原创；-"         # AK
            # H 关联创意
            row[7] = p["links"] or ""
            # I 上传卡审 / J 投放卡审
            if p["status"] == "审核未通过":
                row[8] = "1"
            elif "未通过" in (p["links"] or ""):
                row[9] = "1"
            # L 视频ID
            row[11] = p["id"]
            # O 视频标签
            row[14] = p["tags"] if p["tags"] else "[]"
            # R 关联素材包（数据行第2位）
            row[17] = p.get("pack", "") or ""
            # U..AJ 指标：花费/封面曝光/封面点击/素材曝光/行为/封面点击率/千次封面曝光/千次素材曝光/封面点击单价/行为单价/曝光/行为率/直播3秒/直播3秒成本/直播商品点击/直播商品点击成本
            metrics = p.get("metrics", [])
            for k, m in enumerate(metrics[:16]):
                row[20 + k] = m
            return row

        filled_h = [x for x in writes if x[1] not in ("", "❓待定")]
        print(f"\n计划：H列写 {len(writes)} 行（其中有效 {len(filled_h)}）；"
              f"I列改 {len(writes_i)} 行；J列改 {len(writes_j)} 行；追加 {len(appends)} 行")

        if not apply:
            if writes:
                print("\nH列将写入（行: 值）:", [(rn, v) for rn, v in writes[:10]], "…" if len(writes) > 10 else "")
            if writes_i:
                print("I列将写入（行: 值）:", [(rn, v) for rn, v in writes_i[:10]], "…" if len(writes_i) > 10 else "")
            if writes_j:
                print("J列将写入（行: 值）:", [(rn, v) for rn, v in writes_j[:10]], "…" if len(writes_j) > 10 else "")
            print("…（未加 --apply，仅预览）")
            return

        # 写 H 列：逐单元格（增量模式下 writes 行号稀疏，不能整列覆盖）
        for rn, v in writes:
            r = client.call("shimo_update_spreadsheet",
                            {"file_guid": FILE_GUID,
                             "range": f"{sheet_name}!H{rn}", "values": [[v]]})
        print(f"✅ H列写入 {len(writes)} 个")

        # 写 I 列（单单元格写，避免整列覆盖手填）
        for rn, v in writes_i:
            r = client.call("shimo_update_spreadsheet",
                            {"file_guid": FILE_GUID,
                             "range": f"{sheet_name}!I{rn}", "values": [[v]]})
        print(f"✅ I列差异写入 {len(writes_i)} 个")
        # 写 J 列
        for rn, v in writes_j:
            r = client.call("shimo_update_spreadsheet",
                            {"file_guid": FILE_GUID,
                             "range": f"{sheet_name}!J{rn}", "values": [[v]]})
        print(f"✅ J列差异写入 {len(writes_j)} 个")

        # 追加新素材行：读当前最后非空行号，逐行往下写
        if appends:
            last = max([s["rn"] for s in rows], default=1)
            for idx, p in enumerate(appends):
                rn = last + 1 + idx
                row_vals = append_row(p)
                r = client.call("shimo_update_spreadsheet",
                                {"file_guid": FILE_GUID,
                                 "range": f"{sheet_name}!A{rn}:AK{rn}",
                                 "values": [row_vals]})
                print(f"  ➕ 追加行{rn}: {p['norm'][:30]}")
            print(f"✅ 追加 {len(appends)} 行完成")

        # 抽验几行
        for rn in (2, 5, 29, 30, 32, 130, 131, 252):
            r2 = client.call("shimo_get_spreadsheet_content",
                             {"file_guid": FILE_GUID, "range": f"{sheet_name}!B{rn}:K{rn}"})
            txt = [c.get("text", "") for c in (r2.get("result", {}).get("content") or [])]
            print(f"  抽验行{rn}:", txt)
    finally:
        client.stop()


if __name__ == "__main__":
    main()
