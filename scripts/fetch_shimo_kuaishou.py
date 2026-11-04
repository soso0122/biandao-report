#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从石墨文档拉取快手投放数据 → data/kuaishou_shimo_data.json

石墨文档：【快手】引流加微数据 (guid=3O8pG2xayV1rhLnp)
MCP：https://shimo-mcp.zhenguanyu.com/sse，认证必须 Authorization: Bearer <Token>。

Sheet 结构（命名规则由用户 2026-11-02 定，后续新账户沿用）：
  - 账户表现-分日（跨账户）        所有账户按天，账户/计划/组级，转化漏斗
  - 素材表现-分日（跨账户）        所有账户按天，素材级，转化+播放质量
  - 账户表现-分时-{账户ID}        单账户按小时（从分日表里发现账户ID，自动读取）
  - 素材表现-分时-{账户ID}        单账户按小时（暂存，报告未展示）

去重防护（历史踩坑）：
  - 分日/分时表都是组级拆分（同素材同日多组多行），按行求和是正确的、不算重复
  - 但导出偶发「完全相同的重复行」，写库前用整行签名去重
  - 石墨存的是 Excel 序列日期（整数=分日，小数=分时），需转换
"""
import json
import re
import subprocess
import sys
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
OUT_JSON = DATA_DIR / "kuaishou_shimo_data.json"

FILE_GUID = "3O8pG2xayV1rhLnp"
SHEET_ACC_DAILY = "账户表现-分日（跨账户）"
SHEET_MAT_DAILY = "素材表现-分日（跨账户）"
SHEET_ACC_HOURLY = "账户表现-分时-{}"
SHEET_MAT_HOURLY = "素材表现-分时-{}"

PAGE_ROWS = 150          # 32 列 × 150 行 = 4800 单元格 < 5000 上限
COL_END = "AF"           # 覆盖到 32 列


def load_token():
    cfg = json.load(open(Path.home() / ".zcode" / "cli" / "config.json"))
    shimo = cfg.get("mcp", {}).get("servers", {}).get("shimo", {})
    tok = (shimo.get("env") or {}).get("SHIMO_TOKEN", "")
    if not tok:
        m = re.search(r"[?&]t=([0-9a-fA-F]{32,})", shimo.get("url", ""))
        tok = m.group(1) if m else ""
    if not tok:
        raise SystemExit("未找到石墨 Token")
    return tok


TOKEN = load_token()
MCP_BASE = "https://shimo-mcp.zhenguanyu.com"
EXCEL_EPOCH = datetime(1899, 12, 30)


def excel_dt(v):
    """Excel 序列 → datetime（整数=分日，小数=分时）"""
    if isinstance(v, (int, float)):
        return EXCEL_EPOCH + timedelta(days=float(v))
    s = str(v).strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


def hour_of(dt):
    """四舍五入取小时：石墨时间戳经 Excel 序列浮点换算后，
    整点值会偏差成 16:59:59.9997 之类，截断会把 X:00 归进上一小时。
    四舍五入到最近整点（2026-11-04 修复）。"""
    total_sec = dt.hour * 3600 + dt.minute * 60 + dt.second
    return int(round(total_sec / 3600)) % 24


def fnum(v):
    try:
        x = float(str(v).replace(",", "").replace("%", ""))
        return x if abs(x) < 1e300 else 0.0
    except (TypeError, ValueError):
        return 0.0


class ShimoClient:
    def __init__(self):
        self.token = TOKEN
        self.results = []
        self.proc = None
        self.sid = None

    def post(self, body):
        subprocess.run(
            ["curl", "-s", "-m", "60", "-X", "POST",
             f"{MCP_BASE}/message?sessionId={self.sid}",
             "-H", f"Authorization: Bearer {self.token}",
             "-H", "Content-Type: application/json",
             "-d", json.dumps(body)],
            capture_output=True, text=True, timeout=65)

    def start(self):
        self.proc = subprocess.Popen(
            ["curl", "-s", "-m", "900", "-N",
             "-H", f"Authorization: Bearer {self.token}", f"{MCP_BASE}/sse"],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, bufsize=1)
        for _ in range(10):
            line = self.proc.stdout.readline().strip()
            if "sessionId=" in line:
                m = re.search(r"sessionId=([a-f0-9-]+)", line)
                self.sid = m.group(1)
                break
        if not self.sid:
            raise SystemExit("无法建立 MCP 会话")

        def reader():
            for line in self.proc.stdout:
                line = line.strip()
                if line.startswith("data:"):
                    p = line[5:].strip()
                    if p and p != "[DONE]":
                        try:
                            d = json.loads(p)
                            if d.get("method") == "ping":
                                self.post({"jsonrpc": "2.0", "id": d.get("id"), "result": {}})
                            self.results.append(d)
                        except Exception:
                            pass

        threading.Thread(target=reader, daemon=True).start()
        time.sleep(1)
        self.post({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                   "params": {"protocolVersion": "2024-11-05", "capabilities": {},
                              "clientInfo": {"name": "zcode", "version": "1.0"}}})
        time.sleep(2)
        self.post({"jsonrpc": "2.0", "method": "notifications/initialized"})
        time.sleep(1)

    def stop(self):
        if self.proc:
            self.proc.kill()

    def call(self, name, args, timeout=90):
        msg_id = int(time.time() * 1000) % 100000
        self.post({"jsonrpc": "2.0", "id": msg_id, "method": "tools/call",
                   "params": {"name": name, "arguments": args}})
        deadline = time.time() + timeout
        while time.time() < deadline:
            for r in list(self.results):
                if isinstance(r, dict) and r.get("id") == msg_id:
                    return r
            time.sleep(0.4)
        return None

    def read_range(self, sheet, rng):
        r = self.call("shimo_get_spreadsheet_content",
                      {"file_guid": FILE_GUID, "range": f"{sheet}!{rng}"})
        if not r:
            return None, "无响应"
        content = r.get("result", {})
        texts = [c.get("text", "") for c in (content.get("content") or []) if c.get("type") == "text"]
        txt = "\n".join(texts)
        if "failed" in txt:
            return None, txt[:300]
        try:
            d = json.loads(txt)
            return d.get("values"), None
        except Exception:
            return None, txt[:300]


def read_sheet(client, sheet):
    """整表读取，返回 (header, rows)。表不存在返回 (None, None)。"""
    vals, err = client.read_range(sheet, f"A1:{COL_END}1")
    if err:
        return None, err
    if not vals:
        return None, "空表"
    header = [str(h) if h is not None else "" for h in vals[0]]
    header = [h for h in header if h]

    rows = []
    seen = set()
    start = 2
    while True:
        vals, err = client.read_range(sheet, f"A{start}:{COL_END}{start + PAGE_ROWS - 1}")
        if err:
            return None, err
        if not vals:
            break
        page_rows = [v for v in vals if any(x is not None for x in v)]
        for v in page_rows:
            sig = tuple("" if x is None else str(x)[:80] for x in v)
            if sig in seen:      # 完全相同的重复行 → 丢弃
                continue
            seen.add(sig)
            rows.append(v)
        if len(page_rows) < PAGE_ROWS:
            break
        start += PAGE_ROWS
    return header, rows


def parse_rows(header, rows):
    """行 → dict（按表头名取值）。分日/分时 列转字符串日期。"""
    out = []
    for r in rows:
        rec = {}
        for i, h in enumerate(header):
            if not h:
                continue
            v = r[i] if i < len(r) else None
            if v is None:
                continue
            if h in ("分日", "分时"):
                dt = excel_dt(v)
                if dt:
                    rec[h] = dt.strftime("%Y-%m-%d %H:%M:%S")
                continue
            if isinstance(v, str):
                v = v.strip()
            rec[h] = v
        out.append(rec)
    return out


FUNNEL = {
    "花费(元)": "sp", "曝光数": "im", "行为数": "ac",
    "转化数(计费时间)": "cv", "深度转化数(计费时间)": "dp",
    "有效获客数（计费时间）": "va",
    "企微开口1次数量": "o1", "企微开口3次数量": "o3",
    "企微开口5次数量": "o5", "企微开口10次数量": "o10",
}
METRIC_FIELDS = ["sp", "im", "ac", "cv", "dp", "va", "o1", "o3", "o5", "o10"]


def zero_m():
    return {k: 0.0 for k in METRIC_FIELDS}


def zero_q():
    return {"qi": 0.0, "qmi": 0.0, "cc": 0.0, "ce": 0.0, "p3": 0.0, "p5": 0.0, "fn": 0.0}


def add_m(target, rec):
    for col, k in FUNNEL.items():
        if col in rec:
            target[k] += fnum(rec[col])


def main():
    client = ShimoClient()
    client.start()
    try:
        header_acc, rows_acc = read_sheet(client, SHEET_ACC_DAILY)
        header_mat, rows_mat = read_sheet(client, SHEET_MAT_DAILY)
        if header_acc is None:
            raise SystemExit(f"读账户分日表失败: {rows_acc}")
        if header_mat is None:
            raise SystemExit(f"读素材分日表失败: {rows_mat}")
        acc_recs = parse_rows(header_acc, rows_acc)
        mat_recs = parse_rows(header_mat, rows_mat)
        print(f"[石墨] 账户分日: {len(acc_recs)} 行; 素材分日: {len(mat_recs)} 行")

        # 从分日表发现账户
        acct_ids = sorted({str(r["账户信息ID"]).strip()
                           for r in acc_recs if r.get("账户信息ID") not in (None, "")} |
                          {str(r["账户信息ID"]).strip()
                           for r in mat_recs if r.get("账户信息ID") not in (None, "")})
        print(f"[石墨] 账户: {acct_ids}")

        # 分时表：按账户读
        hourly_acc = {}   # {acct: {date: {hour: metrics}}}
        hourly_mat = {}   # {acct: {date: {hour: quality sums}}}（暂存）
        for aid in acct_ids:
            h_header, h_rows = read_sheet(client, SHEET_ACC_HOURLY.format(aid))
            if h_header is None:
                print(f"[石墨] 账户{aid} 无分时账户表，跳过（{h_rows[:80]}）")
            else:
                h_recs = parse_rows(h_header, h_rows)
                for r in h_recs:
                    dt_str = r.get("分时", "")
                    dt = datetime.strptime(dt_str, "%Y-%m-%d %H:%M:%S")
                    d, h = dt.strftime("%Y-%m-%d"), hour_of(dt)
                    m = hourly_acc.setdefault(aid, {}).setdefault(d, {}).setdefault(h, zero_m())
                    add_m(m, r)
                print(f"[石墨] 账户{aid} 分时: {len(h_recs)} 行")

            m_header, m_rows = read_sheet(client, SHEET_MAT_HOURLY.format(aid))
            if m_header is None:
                print(f"[石墨] 账户{aid} 无分时素材表，跳过")
            else:
                m_recs = parse_rows(m_header, m_rows)
                for r in m_recs:
                    dt_str = r.get("分时", "")
                    dt = datetime.strptime(dt_str, "%Y-%m-%d %H:%M:%S")
                    d, h = dt.strftime("%Y-%m-%d"), hour_of(dt)
                    q = hourly_mat.setdefault(aid, {}).setdefault(d, {}).setdefault(h, zero_q())
                    imp = fnum(r.get("曝光数"))
                    q["qi"] += imp
                    q["qmi"] += fnum(r.get("素材曝光数"))
                    q["cc"] += fnum(r.get("封面点击数"))
                    q["ce"] += fnum(r.get("封面曝光数"))
                    q["p3"] += fnum(r.get("3秒播放率")) * imp
                    q["p5"] += fnum(r.get("5秒播放率")) * imp
                    q["fn"] += fnum(r.get("完播率")) * imp
                print(f"[石墨] 账户{aid} 分时素材: {len(m_recs)} 行")

        # ---------- 聚合：账户 / 计划 / 组 / 素材（分日，账户表为主，按账户拆分） ----------
        accounts, plans, groups, materials = {}, {}, {}, {}
        for r in acc_recs:
            d = r.get("分日", "")[:10]
            if not d:
                continue
            acct = str(r.get("账户信息ID") or "").strip() or "未知账户"
            plan = str(r.get("计划名称") or "").strip() or "未命名计划"
            grp = str(r.get("组名称") or "").strip() or "未命名组"
            name = str(r.get("素材名称") or "").strip()
            content = str(r.get("素材内容") or "").strip()
            if not name:
                continue

            add_m(accounts.setdefault(acct, {}).setdefault(d, zero_m()), r)

            pl = plans.setdefault(plan, {"days": {}, "names": set()})
            add_m(pl["days"].setdefault(d, {}).setdefault(acct, zero_m()), r)
            pl["names"].add(name)

            gr = groups.setdefault(grp, {"days": {}})
            add_m(gr["days"].setdefault(d, {}).setdefault(acct, zero_m()), r)

            mt = materials.setdefault(name, {"type": None, "person": None, "content": "",
                                             "days": {}})
            md = mt["days"].setdefault(d, {})
            mc = md.setdefault(acct, {"m": zero_m(), "q": zero_q()})
            add_m(mc["m"], r)
            if content:
                mt["content"] = content

        # 素材表：播放质量并入素材 days（按素材名+账户，与账户表对齐）
        for r in mat_recs:
            d = r.get("分日", "")[:10]
            if not d:
                continue
            name = str(r.get("素材名称") or "").strip()
            acct = str(r.get("账户信息ID") or "").strip() or "未知账户"
            if not name:
                continue
            imp = fnum(r.get("曝光数"))
            mt = materials.setdefault(name, {"type": None, "person": None, "content": "",
                                             "days": {}})
            mc = mt["days"].setdefault(d, {}).setdefault(acct, {"m": zero_m(), "q": zero_q()})
            q = mc["q"]
            q["qi"] += imp
            q["qmi"] += fnum(r.get("素材曝光数"))
            q["cc"] += fnum(r.get("封面点击数"))
            q["ce"] += fnum(r.get("封面曝光数"))
            q["p3"] += fnum(r.get("3秒播放率")) * imp
            q["p5"] += fnum(r.get("5秒播放率")) * imp
            q["fn"] += fnum(r.get("完播率")) * imp
            if not mt["content"]:
                mt["content"] = str(r.get("素材内容") or "").strip()

        # ---------- 分类：类型 / 编导（2026-11-02 定：只认 4 人，其余全部归「其他」） ----------
        PERSONS = ["嘉丽", "小敏", "雅迪", "瑞晨"]
        for name, mt in materials.items():
            n = name.strip()
            if n.upper() == "AIGC":
                mt["type"] = "AI"
            elif mt["content"]:
                mt["type"] = "视频"
            else:
                mt["type"] = "图文"
            if mt["type"] == "AI":
                mt["person"] = "其他"
            else:
                # 视频与图文都按名称匹配编导（图文不能一律归其他）
                mt["person"] = next((p for p in PERSONS if p in n), "其他")

        dates = sorted({d for a in accounts.values() for d in a})

        payload = {
            "source": "shimo",
            "file_guid": FILE_GUID,
            "fetched_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "dates": dates,
            "accounts": [{"id": a, "days": accounts[a]} for a in sorted(accounts)],
            "plans": [{"name": p, "days": plans[p]["days"], "names": sorted(plans[p]["names"])}
                      for p in sorted(plans)],
            "groups": [{"name": g, "days": groups[g]["days"]} for g in sorted(groups)],
            "materials": [{"name": n, "type": mt["type"], "person": mt["person"],
                           "content": mt["content"], "days": mt["days"]}
                          for n, mt in materials.items()],
            "hourly": hourly_acc,
        }
        OUT_JSON.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        print(f"[OK] {OUT_JSON} ({OUT_JSON.stat().st_size/1024:.0f} KB): "
              f"账户{len(payload['accounts'])} 计划{len(payload['plans'])} "
              f"组{len(payload['groups'])} 素材{len(payload['materials'])} 日期{dates[0]}~{dates[-1]}")
    finally:
        client.stop()


if __name__ == "__main__":
    main()
