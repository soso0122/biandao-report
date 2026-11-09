#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""快手拒审粘贴文本解析器（创意列表页复制出来的文字）

用户从快手创意列表页复制文字贴到对话/石墨，本脚本把每块创意拆成结构化数据。

粘贴结构（每块创意）：
    4 个标签行（取值 AI / 原生 / 全自动）
    创意名称
    状态          （投放中 / 审核未通过 / 投放中(部分流量未通过) / 投放中(部分流量未投放)…）
    花费(元)      （如 0.000、0.027）
    计划名称
    一串数字      （有效线索+企微开口1次+行为数+素材曝光数，粘在一起，如 0000）

已知噪声：
  - 表头行：开关 / 创意名称 / 状态 / 计划名称
  - 详情/数据/编辑/体验 等按钮文字可能夹在块里
  - 状态与花费之间可能多空行
"""
import json
import re
import sys

LABELS = {"AI", "原生", "全自动"}
HEADER_JUNK = {"开关", "创意名称", "状态", "计划名称", "表头", "花费(元)", "有效线索数",
               "企微开口1次数量", "行为数", "素材曝光数"}
BUTTON_JUNK = {"详情", "数据", "编辑", "体验", "关闭", "开启", "预览", "复制", "投放"}
# 状态关键词（全角括号，与快手页面一致）
STATUS_PAT = re.compile(r"(审核未通过|审核通过|投放中(?:\(部分流量未通过\)|（部分流量未通过）|\(部分流量未投放\)|（部分流量未投放）)?)")

NUMBER_LINE = re.compile(r"^\d+(\.\d+)?$")          # 花费 0.000
METRICS_LINE = re.compile(r"^[\d.%,\s]+$")           # 挤在一起的指标串 0000 / 0.0000.0000.00000.00%0


def is_label_line(s):
    return s in LABELS


def parse(pasted_text):
    lines = [l.strip() for l in pasted_text.split("\n")]
    lines = [l for l in lines if l]  # 去空行
    # 去掉开头表头行
    while lines and (lines[0] in HEADER_JUNK or lines[0] in BUTTON_JUNK):
        lines.pop(0)

    blocks = []
    i = 0
    n = len(lines)
    while i < n:
        # 找一个 4 连标签行的块起点
        if not (is_label_line(lines[i])):
            i += 1
            continue
        # 连续标签行（理论上恰好4个，容错3~5）
        j = i
        while j < n and is_label_line(lines[j]):
            j += 1
        if j - i < 3:          # 不是标签块，跳过
            i = j
            continue
        block_lines = lines[j:]  # 标签之后的块内容
        # 找下一块的起点，截断
        end = len(block_lines)
        for k in range(len(block_lines) - 3):
            if all(is_label_line(block_lines[k + t]) for t in range(4)):
                end = k
                break
        body = block_lines[:end]
        # 解析块体
        name = None
        status = None
        spend = None
        plan = None
        metrics = None
        k = 0
        # 创意名称：第一个非按钮文字、非状态、非数字的行
        while k < len(body) and name is None:
            s = body[k]
            if s in BUTTON_JUNK or s in HEADER_JUNK:
                k += 1
            elif STATUS_PAT.match(s) and (s.startswith("投放中") or s.startswith("审核")):
                k += 1
            elif NUMBER_LINE.match(s) or METRICS_LINE.match(s):
                k += 1
            else:
                name = s
                k += 1
        # 状态：含关键词的行
        for s in body:
            if s.startswith("投放中") or s.startswith("审核"):
                status = s
                break
        try:
            si = body.index(status) if status else -1
        except ValueError:
            si = -1
        # 状态之后：两种模板
        #   v2 有花费行： [花费(0.000), 计划名称, 指标串]
        #   v3 无花费行： [计划名称, 指标串]
        if si >= 0:
            tail = body[si + 1:]
            dec = [s for s in tail if re.fullmatch(r"\d+\.\d+", s)]   # 花费：带小数
            ints = [s for s in tail if re.fullmatch(r"\d+", s)]       # 指标串：纯整数
            if dec:
                spend = dec[0]
            # 计划名称：状态之后第一行非数字
            for s in tail:
                if not re.fullmatch(r"\d+\.?\d*", s) and s not in BUTTON_JUNK:
                    plan = s
                    break
            metrics = ints[0] if ints else None
        blocks.append({
            "创意名称": name,
            "状态": status,
            "花费(元)": spend,
            "计划名称": plan,
            "指标串": metrics,
        })
        i = j + end

    return blocks


def classify(b):
    """按用户定义的 5 种环节归类"""
    status = b.get("状态") or ""
    spend = b.get("花费(元)") or "0"
    try:
        spend_f = float(spend)
    except ValueError:
        spend_f = 0.0
    if status.startswith("审核未通过"):
        return "有消耗后拒审" if spend_f > 0 else "刚投放就拒审"
    if "部分流量未通过" in status:
        return "待复核(部分流量未通过)"
    if "部分流量未投放" in status:
        return "投放后限流"
    if status.startswith("投放中") or status.startswith("审核通过"):
        return "正常投放中"
    return "未知"


if __name__ == "__main__":
    src = sys.argv[1] if len(sys.argv) > 1 else None
    if src:
        text = open(src, encoding="utf-8").read()
    else:
        text = sys.stdin.read()
    blocks = parse(text)
    out = []
    for b in blocks:
        b["归类"] = classify(b)
        out.append(b)
    print(json.dumps(out, ensure_ascii=False, indent=2))
    # 汇总
    from collections import Counter
    print("\n== 归类汇总 ==", json.dumps(dict(Counter(x["归类"] for x in out)), ensure_ascii=False))
