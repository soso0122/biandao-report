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
SHEET_DAILY_RECORD = "当日数据记录"   # 天级汇总，含「销售反馈-出单」=深转真实回传
SHEET_LEDGER = "拒审台账-子账户"       # 子账户素材台账：全量素材池+审核状态（近3周模块分母）

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
        # 「当日数据记录」：天级汇总（用户留存），取「销售反馈-出单」=深转真实回传
        header_rec, rows_rec = read_sheet(client, SHEET_DAILY_RECORD)
        header_ledger, rows_ledger = read_sheet(client, SHEET_LEDGER)
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

        # 解析「当日数据记录」：两行表头，第2行列名=日期(0)…出单(9)
        # 出单=深转真实回传（销售反馈），天级口径
        deep_real = {}   # {date: 出单数}
        if header_rec is not None and rows_rec:
            for r in rows_rec:
                if not r or len(r) < 10:
                    continue
                v0 = r[0]
                if v0 is None or isinstance(v0, str):   # 跳过「日期」「总计」行
                    continue
                d = excel_dt(v0)
                if d is None:
                    continue
                try:
                    n = float(r[9] or 0)
                except (TypeError, ValueError):
                    n = 0.0
                deep_real[d.strftime("%Y-%m-%d")] = n
        print(f"[石墨] 当日数据记录-出单(深转回传): {deep_real}")

        # 解析「拒审台账-子账户」：全量素材池 + 审核状态（近3周模块分母/过审率）
        # 列：0上传日期 1视频名称 2审核状态 3创建时间 4时长 5视频来源 6视频素材评价
        #     7关联创意 8上传卡审 9投放卡审 10卡审详情 11视频ID 12视频标识 13视频名称
        # 三分类（用户 2026-11-11 定，与台账 I/J 列一致）：
        #   上传卡审=审核状态「审核未通过」；投放卡审=关联创意含「未通过」且状态非未通过；其余=过审
        ledger = []   # [{name, upload, audit(过审/上传卡审/投放卡审), status, creative}]
        if header_ledger is not None and rows_ledger:
            for r in rows_ledger:
                if not r:
                    continue
                name = str(r[13] or r[1] or "").strip()
                if not name:
                    continue
                d0 = excel_dt(r[0])
                upload = d0.strftime("%Y-%m-%d") if d0 else ""
                status = str(r[2] or "").strip()
                creative = str(r[7] or "").strip()
                if status == "审核未通过":
                    audit = "上传卡审"
                elif "未通过" in creative:
                    audit = "投放卡审"
                else:
                    audit = "过审"
                ledger.append({"name": name, "upload": upload,
                               "audit": audit, "status": status,
                               "creative": creative})
        print(f"[石墨] 拒审台账: {len(ledger)} 行, "
              f"过审 {sum(1 for x in ledger if x['audit'] == '过审')}, "
              f"上传卡审 {sum(1 for x in ledger if x['audit'] == '上传卡审')}, "
              f"投放卡审 {sum(1 for x in ledger if x['audit'] == '投放卡审')}")

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

        # ---------- 聚合：账户 / 计划 / 组（账户表，保持原有粒度，不拆AI） ----------
        accounts, plans, groups = {}, {}, {}
        # 账户表组级行：只存深转/有效获客（素材表没有的两列），
        # 后续按 (日,账户,组名称,素材名称) 映射到素材表行
        acc_va_dp = {}
        for r in acc_recs:
            d = r.get("分日", "")[:10]
            if not d:
                continue
            acct = str(r.get("账户信息ID") or "").strip() or "未知账户"
            plan = str(r.get("计划名称") or "").strip() or "未命名计划"
            grp = str(r.get("组名称") or "").strip() or "未命名组"
            name = str(r.get("素材名称") or "").strip()
            if not name:
                continue

            add_m(accounts.setdefault(acct, {}).setdefault(d, zero_m()), r)

            pl = plans.setdefault(plan, {"days": {}, "names": set()})
            add_m(pl["days"].setdefault(d, {}).setdefault(acct, zero_m()), r)
            pl["names"].add(name)

            gr = groups.setdefault(grp, {"days": {}})
            add_m(gr["days"].setdefault(d, {}).setdefault(acct, zero_m()), r)

            key = (d, acct, grp, name, "系统自动" in grp)
            va = fnum(r.get("有效获客数（计费时间）"))
            dp = fnum(r.get("深度转化数(计费时间)"))
            if va or dp:
                entry = acc_va_dp.setdefault(key, {"va": 0.0, "dp": 0.0})
                entry["va"] += va
                entry["dp"] += dp

        # ---------- 素材聚合（以素材表为准，按「创意名称」精确拆分系统自动） ----------
        # 用户 2026-11-09 规则：创意名称含「系统自动」→ 平台AI；人工创意按原规则分析。
        # 同名素材拆两条：正常（人工创意）+ 平台AI（系统自动创意）。
        # 注意：有效获客/深转从账户表映射时，素材表同日同素材多创意行会重复累加，
        # 因此这里只加素材表指标，va/dp 在聚合完成后统一补充（按 素材+日+账户+is_auto）。
        materials = {}
        for r in mat_recs:
            d = r.get("分日", "")[:10]
            if not d:
                continue
            name = str(r.get("素材名称") or "").strip()
            acct = str(r.get("账户信息ID") or "").strip() or "未知账户"
            creative = str(r.get("创意名称") or "").strip()
            if not name:
                continue
            is_auto = "系统自动" in creative
            mkey = (name, is_auto)
            mt = materials.setdefault(mkey, {"name": name, "is_auto": is_auto,
                                             "type": None, "person": None, "content": "",
                                             "days": {}})
            mc = mt["days"].setdefault(d, {}).setdefault(acct, {"m": zero_m(), "q": zero_q()})
            # 素材指标（素材表含这些列，按创意名称拆分精确）
            for col, k in (("花费(元)", "sp"), ("行为数", "ac"), ("曝光数", "im"),
                           ("转化数(计费时间)", "cv"),
                           ("企微开口1次数量", "o1"), ("企微开口3次数量", "o3"),
                           ("企微开口5次数量", "o5"), ("企微开口10次数量", "o10")):
                if col in r:
                    mc["m"][k] += fnum(r[col])
            # 播放质量
            imp = fnum(r.get("曝光数"))
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

        # 有效获客/深转补充：账户表无创意名称，按（素材名, 日, 账户）聚合 va/dp。
        # 若同名素材同日有人工+AI两条行，按各自转化数占比拆分 va/dp（总量守恒、不重复）；
        # 两条转化都为 0 时全给人工行。单条行则直接赋值。
        va_dp_by_mat = {}
        for (d, acct, grp, name, grp_auto), vd in acc_va_dp.items():
            key = (name, d, acct)
            e = va_dp_by_mat.setdefault(key, {"va": 0.0, "dp": 0.0})
            e["va"] += vd["va"]
            e["dp"] += vd["dp"]
        # 找出同日同素材双行的情况
        row_cv = {}
        for (name, is_auto), mt in materials.items():
            for d, accts in mt["days"].items():
                for acct, mc in accts.items():
                    row_cv[(name, d, acct, is_auto)] = mc["m"]["cv"]
        for (name, is_auto), mt in materials.items():
            for d, accts in mt["days"].items():
                for acct, mc in accts.items():
                    vd = va_dp_by_mat.get((name, d, acct))
                    if not vd:
                        continue
                    cv_this = mc["m"]["cv"]
                    cv_other = row_cv.get((name, d, acct, not is_auto), 0.0)
                    if cv_other <= 0 and cv_this <= 0:
                        # 都没有转化：全给人工行
                        if is_auto:
                            continue
                        mc["m"]["dp"] = vd["dp"]
                        mc["m"]["va"] = vd["va"]
                    else:
                        total = cv_this + cv_other
                        share = cv_this / total if total else 0.0
                        mc["m"]["dp"] = vd["dp"] * share
                        mc["m"]["va"] = vd["va"] * share

        # ---------- 分类：类型 / 编导 ----------
        # 类型互斥优先级（2026-11-10 定）：名称含「花火」→ 花火AI（最高）
        # → 系统自动创意/AIGC → 平台AI → 内容非空 → 视频 → 否则图文
        PERSONS = ["嘉丽", "小敏", "雅迪", "瑞晨"]
        for (name, is_auto), mt in materials.items():
            n = name.strip()
            if "花火" in n:
                mt["type"] = "花火AI"
            elif is_auto or n.upper() == "AIGC":
                mt["type"] = "AI"
            elif mt["content"]:
                mt["type"] = "视频"
            else:
                mt["type"] = "图文"
            if mt["type"] in ("AI", "花火AI"):
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
            "materials": [{"name": mt["name"], "type": mt["type"], "person": mt["person"],
                           "is_auto": mt["is_auto"], "content": mt["content"], "days": mt["days"]}
                          for mt in materials.values()],
            "hourly": hourly_acc,
            "deep_real": deep_real,
            "ledger": ledger,
        }
        OUT_JSON.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        print(f"[OK] {OUT_JSON} ({OUT_JSON.stat().st_size/1024:.0f} KB): "
              f"账户{len(payload['accounts'])} 计划{len(payload['plans'])} "
              f"组{len(payload['groups'])} 素材{len(payload['materials'])} 日期{dates[0]}~{dates[-1]}")
    finally:
        client.stop()


if __name__ == "__main__":
    main()
