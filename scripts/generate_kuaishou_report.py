# -*- coding: utf-8 -*-
"""快手投放数据报告（2026-10-30 接入真实数据）

数据源（~/Desktop/快手/）：
  - soso-账户 (2).csv      账户/计划/组/素材维度，转化漏斗（GBK 编码）
  - soso-素材表现数据.csv  素材维度，曝光与播放质量（GBK 编码）

口径（与用户逐条确认过）：
  - 主数据源=账户表；素材表现表只提供播放质量列（3秒/5秒/完播/封面点击率等）
  - 合并主键=视频ID（同名多ID，如 AIGC 有 44 个ID，按名称会串）
  - 行为数≈素材点击：行为率=行为÷曝光；转化率=转化÷行为；深转率=深转÷转化
  - 素材分类：名称=AIGC→平台AI；素材内容非空(视频URL)→视频；名称含图文集合_→图文；空内容兜底图文
  - 编导：名称匹配已知编导/剪辑，其余归「其他」
  - 账户表为组级拆分（同素材同日多组多行），所有聚合按行加总后重算比率

用法：python3 scripts/generate_kuaishou_report.py [MMDD]
输出：reports/快手投放报告_MMDD.html
"""

import csv
import json
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
REPORTS_DIR = BASE_DIR / "reports"
CHART_JS_PATH = Path(__file__).parent / "chart.min.js"
KS_DIR = Path.home() / "Desktop" / "快手"
ACC_FILE = KS_DIR / "soso-账户 (2).csv"
MAT_FILE = KS_DIR / "soso-素材表现数据.csv"

TODAY = datetime.now()
TARGET = sys.argv[1] if len(sys.argv) > 1 else TODAY.strftime("%m%d")
TARGET_DT = datetime(TODAY.year, int(TARGET[:2]), int(TARGET[2:]))
if TARGET_DT > TODAY:
    TARGET_DT = TARGET_DT.replace(year=TODAY.year - 1)
REPORT_MMDD = TARGET_DT.strftime("%m%d")

PERSONS = ["小敏", "嘉丽", "浩正", "雅迪", "婷玉", "魏怡", "瑞晨", "国星"]

PERSON_COLORS = {
    "小敏": "#3B82F6", "嘉丽": "#8B5CF6", "瑞晨": "#10B981",
    "浩正": "#F59E0B", "雅迪": "#EC4899", "魏怡": "#EF4444",
    "婷玉": "#14B8A6", "国星": "#0EA5E9", "其他": "#94A3B8",
}
PERSON_BG = {
    "小敏": "#EFF6FF", "嘉丽": "#F5F3FF", "瑞晨": "#ECFDF5",
    "浩正": "#FFFBEB", "雅迪": "#FDF2F8", "魏怡": "#FEF2F2",
    "婷玉": "#F0FDFA", "国星": "#E0F2FE", "其他": "#F8FAFC",
}


def _f(v):
    try:
        x = float(str(v).replace(",", "").replace("¥", "").replace("%", ""))
        return x if abs(x) < 1e300 else 0.0
    except (TypeError, ValueError):
        return 0.0


def read_gbk(path):
    with open(path, encoding="gbk", errors="replace", newline="") as f:
        return list(csv.DictReader(f))


def classify(name, content):
    """素材分类：AIGC=平台AI；内容非空=视频；图文集合_=图文；空内容兜底图文。"""
    n = (name or "").strip()
    if n.upper() == "AIGC":
        return "AI"
    if (content or "").strip():
        return "视频"
    if "图文集合" in n:
        return "图文"
    return "图文"


def extract_person(name):
    for p in PERSONS:
        if p in (name or ""):
            return p
    return "其他"


# ---------------------------------------------------------------- 数据加载

METRIC_KEYS = ["spend", "imp", "act", "conv", "deep", "valid", "open1", "open3", "open5", "open10"]


def load_data():
    acc_rows = read_gbk(ACC_FILE)
    mat_rows = read_gbk(MAT_FILE)

    # 表2：播放质量按 (日,账户,视频ID) 聚合；率按曝光加权
    q_map = {}
    for r in mat_rows:
        d = (r["分日"] or "").strip()
        if not d:
            continue
        key = (d, (r["账户信息ID"] or "").strip(), (r["视频ID"] or "").strip())
        imp = _f(r["曝光数"])
        if key not in q_map:
            q_map[key] = {"imp": 0.0, "cover_exp": 0.0, "cover_click": 0.0,
                          "mat_exp": 0.0,
                          "p3_w": 0.0, "p5_w": 0.0, "fin_w": 0.0}
        q = q_map[key]
        q["imp"] += imp
        q["cover_exp"] += _f(r["封面曝光数"])
        q["cover_click"] += _f(r["封面点击数"])
        q["mat_exp"] += _f(r["素材曝光数"])
        q["p3_w"] += _f(r["3秒播放率"]) * imp
        q["p5_w"] += _f(r["5秒播放率"]) * imp
        q["fin_w"] += _f(r["完播率"]) * imp

    # 表1：按行读取，构建三类聚合（账户/计划/素材）
    accounts, plans, materials = {}, {}, {}
    for r in acc_rows:
        d = (r["分日"] or "").strip()
        if not d:
            continue
        vid = (r["视频ID"] or "").strip()
        name = (r["素材名称"] or "").strip()
        content = (r["素材内容"] or "").strip()
        acct = (r["账户信息ID"] or "").strip() or "未知账户"
        plan = (r["计划名称"] or "").strip() or "未命名计划"
        typ = classify(name, content)
        person = extract_person(name) if typ == "视频" else ("其他" if typ == "图文" else "AI")

        row = {
            "spend": _f(r["花费(元)"]), "imp": _f(r["曝光数"]), "act": _f(r["行为数"]),
            "conv": _f(r["转化数(计费时间)"]), "deep": _f(r["深度转化数(计费时间)"]),
            "valid": _f(r["有效获客数（计费时间）"]),
            "open1": _f(r["企微开口1次数量"]), "open3": _f(r["企微开口3次数量"]),
            "open5": _f(r["企微开口5次数量"]), "open10": _f(r["企微开口10次数量"]),
        }

        def add_day(target, key):
            days = target.setdefault("days", {})
            day = days.setdefault(d, {k: 0.0 for k in METRIC_KEYS})
            for k in METRIC_KEYS:
                day[k] += row[k]

        if acct not in accounts:
            accounts[acct] = {"days": {}}
        add_day(accounts[acct], acct)

        if plan not in plans:
            plans[plan] = {"days": {}, "vids": set()}
        add_day(plans[plan], plan)
        if vid:
            plans[plan]["vids"].add(vid)

        if vid:
            if vid not in materials:
                materials[vid] = {"vid": vid, "name": name, "type": typ, "person": person,
                                  "content": content, "days": {}}
            m = materials[vid]
            add_day(m, vid)
            # 同名同类型不同ID时，名称取带名字的那个
            if not m["name"] and name:
                m["name"] = name
            if not m["content"] and content:
                m["content"] = content

    # 播放质量并入素材 days（主账户与三个账户全用 vid 匹配）
    for (d, acct, vid), q in q_map.items():
        if vid in materials and d in materials[vid]["days"]:
            m = materials[vid]["days"][d]
            m["p3"] = q["p3_w"] / q["imp"] if q["imp"] else 0.0
            m["p5"] = q["p5_w"] / q["imp"] if q["imp"] else 0.0
            m["fin"] = q["fin_w"] / q["imp"] if q["imp"] else 0.0
            m["cover_rate"] = q["cover_click"] / q["cover_exp"] * 100 if q["cover_exp"] else 0.0
        # 播放质量单独存，供「只算有质量数据的账户」场景
        if "qdays" not in materials.get(vid, {}):
            materials.setdefault(vid, {}).setdefault("qdays", {})
        if vid in materials:
            qd = materials[vid].setdefault("qdays", {})
            qd[d] = {
                "p3": q["p3_w"] / q["imp"] if q["imp"] else 0.0,
                "p5": q["p5_w"] / q["imp"] if q["imp"] else 0.0,
                "fin": q["fin_w"] / q["imp"] if q["imp"] else 0.0,
                "cover_rate": q["cover_click"] / q["cover_exp"] * 100 if q["cover_exp"] else 0.0,
            }

    dates = sorted({d for a in accounts.values() for d in a["days"]})

    def summarize(target):
        s = {k: 0.0 for k in METRIC_KEYS}
        for day in target["days"].values():
            for k in METRIC_KEYS:
                s[k] += day[k]
        s["act_rate"] = s["act"] / s["imp"] * 100 if s["imp"] else 0.0
        s["cvr"] = s["conv"] / s["act"] * 100 if s["act"] else 0.0
        s["deep_rate"] = s["deep"] / s["conv"] * 100 if s["conv"] else 0.0
        s["cpa"] = s["spend"] / s["conv"] if s["conv"] else 0.0
        return s

    out = {
        "dates": dates,
        "accounts": [{"id": a, "days": accounts[a]["days"], **summarize(accounts[a])}
                     for a in sorted(accounts)],
        "plans": [{"name": p, "days": plans[p]["days"], "vid_count": len(plans[p]["vids"]),
                   **summarize(plans[p])}
                  for p in sorted(plans, key=lambda x: -summarize(plans[x])["spend"])],
        "materials": [{**summarize(m), "vid": m["vid"], "name": m["name"],
                       "type": m["type"], "person": m["person"],
                       "content": m["content"], "days": m["days"],
                       "qdays": m.get("qdays", {})} for m in materials.values()],
    }
    return out


# ---------------------------------------------------------------- 页面

CSS = """
:root{--bg:#F8FAFC;--card:#FFFFFF;--border:#DBEAFE;--primary:#1E40AF;--primary-light:#3B82F6;
--accent:#D97706;--accent-bg:#FFFBEB;--text:#1E3A8A;--text-secondary:#64748B;--text-muted:#94A3B8;
--success:#059669;--danger:#DC2626;--shadow:0 1px 3px rgba(0,0,0,.08);--shadow-md:0 4px 6px rgba(0,0,0,.07);
--radius:10px;font-family:'Fira Sans',system-ui,sans-serif}
*{box-sizing:border-box;margin:0;padding:0}
body{background:var(--bg);color:var(--text);font-size:14px;line-height:1.5;min-height:100vh}

.topbar{position:sticky;top:0;z-index:1000;background:#fff;border-bottom:1.5px solid var(--border);
box-shadow:0 2px 6px rgba(0,0,0,.06);padding:8px 24px 10px}
.topbar-row1{display:flex;align-items:center;gap:16px;flex-wrap:wrap;margin-bottom:6px}
.brand{font-size:13px;font-weight:700;color:var(--primary);white-space:nowrap}
.topbar-row2{display:flex;align-items:center;gap:8px;flex-wrap:wrap}
.topbar-row2 .label{font-size:12px;color:var(--text-secondary);font-weight:500}
.date-chip{font-size:11px;padding:3px 9px;border-radius:12px;background:#EFF6FF;color:var(--primary);
border:1px solid #BFDBFE;cursor:pointer}
.date-chip.sel{background:var(--primary);color:#fff;border-color:var(--primary)}
.range-btn{font-size:11px;padding:3px 9px;border-radius:12px;border:1px solid var(--border);
background:#fff;color:var(--text-secondary);cursor:pointer}
.range-btn:hover{border-color:var(--primary-light);color:var(--primary)}
.range-btn.active{background:var(--primary);color:#fff;border-color:var(--primary)}

.page{max-width:1500px;margin:0 auto;padding:20px 24px}
.section-title{font-size:13px;font-weight:600;color:var(--text);margin-bottom:12px;
display:flex;align-items:center;gap:6px}
.section-title::before{content:'';display:inline-block;width:3px;height:14px;
background:var(--primary-light);border-radius:2px}

/* 口径说明卡 */
.caliber-card{background:var(--card);border:1.5px solid var(--border);border-radius:var(--radius);
box-shadow:var(--shadow);margin-bottom:16px;overflow:hidden}
.caliber-head{display:flex;align-items:center;justify-content:space-between;
padding:10px 14px;background:#F0F6FF;border-bottom:1px solid var(--border);cursor:pointer;
font-size:13px;font-weight:600;color:var(--primary)}
.caliber-head .arrow{transition:transform .2s;font-size:11px;color:var(--text-secondary)}
.caliber-body{padding:12px 16px;display:grid;grid-template-columns:repeat(auto-fill,minmax(330px,1fr));gap:8px 20px}
.caliber-item{font-size:12px;color:#475569;line-height:1.7}
.caliber-item b{color:var(--primary);font-weight:600}
.caliber-card.collapsed .caliber-body{display:none}
.caliber-card.collapsed .arrow{transform:rotate(-90deg)}

.kpi-grid{display:grid;grid-template-columns:repeat(5,1fr);gap:12px;margin-bottom:20px}
.kpi-card{background:var(--card);border:1px solid var(--border);border-radius:var(--radius);
padding:14px 16px;box-shadow:var(--shadow);transition:box-shadow .15s}
.kpi-card:hover{box-shadow:var(--shadow-md)}
.kpi-card.accent{background:var(--accent-bg);border-color:#FCD34D}
.kpi-label{font-size:11px;color:var(--text-secondary);font-weight:500;text-transform:uppercase;
letter-spacing:.5px;margin-bottom:6px}
.kpi-value{font-size:22px;font-weight:700;color:var(--primary);font-family:'Fira Code',monospace;line-height:1.1}
.kpi-card.accent .kpi-value{color:var(--accent)}
.kpi-sub{font-size:11px;color:var(--text-muted);margin-top:3px}
.tc-diff{font-weight:600;display:inline-block;font-size:10.5px}
.tc-diff.inc{color:var(--success)}
.tc-diff.dec{color:var(--danger)}
.help-tip{display:inline-flex;align-items:center;justify-content:center;width:11px;height:11px;
border-radius:50%;background:#DBEAFE;color:var(--primary);font-size:9px;font-weight:700;line-height:1;
margin-left:3px;flex-shrink:0;position:relative;vertical-align:middle;text-align:center}
.help-tip::before{content:'?'}
.help-tip:hover::after{content:attr(data-tip);position:fixed;z-index:99999;pointer-events:none;
background:#1E3A8A;color:#fff;border-radius:8px;padding:8px 10px;font-size:11px;font-weight:400;
line-height:1.5;white-space:normal;word-break:break-all;max-width:380px;box-shadow:0 4px 12px rgba(0,0,0,.3)}

.charts-row{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:20px}
.chart-card{background:var(--card);border:1px solid var(--border);border-radius:var(--radius);
padding:16px;box-shadow:var(--shadow)}
.chart-wrap{position:relative;height:230px;width:100%}

.filter-bar{display:flex;align-items:center;gap:8px;flex-wrap:wrap;background:var(--card);
border:1px solid var(--border);border-radius:var(--radius);padding:10px 14px;margin-bottom:12px;
box-shadow:var(--shadow)}
.filter-label{font-size:12px;color:var(--text-secondary);font-weight:500;white-space:nowrap}
.filter-btn{padding:4px 12px;border-radius:20px;border:1.5px solid var(--border);font-size:12px;
font-weight:500;cursor:pointer;transition:all .15s;background:var(--bg);color:var(--text-secondary)}
.filter-btn:hover{border-color:currentColor;opacity:.9}
.filter-btn.active{color:#fff;border-color:transparent;background:var(--primary)}
.filter-btn-video{color:#3B82F6}
.filter-btn-tuwen{color:#8B5CF6}
.filter-btn-ai{color:#6366F1}
.filter-sep{width:1px;height:18px;background:var(--border);margin:0 4px}
.search-box{padding:5px 10px;border-radius:8px;border:1.5px solid var(--border);font-size:12px;
outline:none;width:180px;background:var(--bg);color:var(--text)}
.search-box:focus{border-color:var(--primary-light)}

.table-card{background:var(--card);border:1px solid var(--border);border-radius:var(--radius);
box-shadow:var(--shadow);overflow:hidden}
.table-toolbar{display:flex;align-items:center;justify-content:space-between;
padding:10px 14px;border-bottom:1px solid var(--border)}
.table-info{font-size:12px;color:var(--text-secondary)}
.table-info span{font-weight:600;color:var(--primary)}
.table-wrap{overflow-x:auto}
table{width:100%;border-collapse:collapse;font-size:13px}
thead th{padding:9px 12px;text-align:left;font-size:11px;font-weight:600;color:var(--text-secondary);
text-transform:uppercase;letter-spacing:.4px;background:#F1F5F9;border-bottom:1px solid var(--border);
white-space:nowrap;cursor:pointer;user-select:none;position:sticky;top:0;z-index:5}
thead th:hover{color:var(--primary)}
thead th.sorted-asc::after{content:' ↑'}
thead th.sorted-desc::after{content:' ↓'}
tbody tr{border-bottom:1px solid #F1F5F9;transition:background .1s}
tbody tr:hover{background:var(--bg)}
tbody td{padding:9px 12px;vertical-align:middle}
tbody tr:last-child{border-bottom:none}

.person-badge{display:inline-flex;align-items:center;padding:2px 8px;border-radius:12px;
font-size:11px;font-weight:600;white-space:nowrap}
.type-video{background:#EFF6FF;color:#3B82F6}
.type-tuwen{background:#F5F3FF;color:#8B5CF6}
.type-ai{background:#EEF2FF;color:#6366F1}
.mat-name{max-width:300px;white-space:normal;word-break:break-all;font-size:12px;
color:var(--text);line-height:1.45}
.num{font-family:'Fira Code',monospace;font-size:12px}
.num-zero{color:var(--text-muted)}
.gaoquan-cell{font-family:'Fira Code',monospace;font-size:13px;font-weight:700;color:var(--accent)}
.gaoquan-zero{color:var(--text-muted);font-weight:400}
.btn-play{display:inline-flex;align-items:center;gap:4px;padding:4px 10px;border-radius:6px;
border:1.5px solid var(--border);background:var(--bg);color:var(--primary-light);font-size:11px;
font-weight:500;cursor:pointer;transition:all .15s;white-space:nowrap}
.btn-play:hover{background:var(--primary);color:#fff;border-color:var(--primary)}

.modal-overlay{position:fixed;inset:0;background:rgba(15,23,42,.7);display:none;
align-items:center;justify-content:center;z-index:1000;backdrop-filter:blur(4px)}
.modal-overlay.open{display:flex}
.modal{background:#0F172A;border-radius:14px;overflow:hidden;width:min(900px,95vw);
box-shadow:0 25px 50px rgba(0,0,0,.5);display:flex;flex-direction:column;max-height:90vh}
.modal-header{display:flex;align-items:center;justify-content:space-between;
padding:12px 16px;border-bottom:1px solid rgba(255,255,255,.1)}
.modal-title{color:#E2E8F0;font-size:13px;font-weight:500;max-width:calc(100% - 40px);
overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.modal-close{width:28px;height:28px;border-radius:6px;border:none;background:rgba(255,255,255,.1);
color:#94A3B8;cursor:pointer;display:flex;align-items:center;justify-content:center;font-size:18px}
.modal-close:hover{background:rgba(255,255,255,.2);color:#fff}
.video-wrap{background:#000;display:flex;align-items:center;justify-content:center;flex:1}
video{max-width:100%;max-height:65vh;display:block}
.video-error{color:#94A3B8;font-size:13px;text-align:center;padding:40px 20px}
.empty-state{text-align:center;padding:40px 20px;color:var(--text-muted);font-size:13px}
@media(max-width:900px){.kpi-grid{grid-template-columns:repeat(2,1fr)}.charts-row{grid-template-columns:1fr}}
"""

CALIBER_HTML = """
<div class="caliber-card" id="caliberCard">
  <div class="caliber-head" onclick="document.getElementById('caliberCard').classList.toggle('collapsed')">
    <span>📌 指标口径说明（点击收起）</span><span class="arrow">▼</span>
  </div>
  <div class="caliber-body">
    <div class="caliber-item"><b>数据源</b>：账户维度表（快手后台「账户」导出）+ 素材表现表（补充播放质量）。两表花费一致，KPI 以账户表为准。</div>
    <div class="caliber-item"><b>行为数</b>：快手里的「行为」约等于素材点击（行为率 = 行为数 ÷ 曝光数）。</div>
    <div class="caliber-item"><b>转化率</b> = 转化数(计费时间) ÷ 行为数；<b>深转率</b> = 深度转化数 ÷ 转化数。</div>
    <div class="caliber-item"><b>CPA</b> = 花费 ÷ 转化数（计费时间口径）。</div>
    <div class="caliber-item"><b>漏斗</b>：曝光 → 行为 → 转化 → 深转 → 有效获客 → 企微开口 1 次（3/5/10 次为后续开口阶段）。</div>
    <div class="caliber-item"><b>素材分类</b>：素材内容有视频链接 = 视频；名称 = AIGC = 平台 AI 素材；名称含「图文集合_」= 图文。</div>
    <div class="caliber-item"><b>编导归属</b>：按素材名称匹配已知编导/剪辑（小敏、嘉丽、浩正、雅迪、婷玉、魏怡、瑞晨、国星），匹配不到归「其他」。</div>
    <div class="caliber-item"><b>3秒/5秒/完播率、封面点击率</b>：来自素材表现表，按曝光加权；仅主账户有数据。</div>
    <div class="caliber-item"><b>明细粒度</b>：账户表为广告组级拆分（同一素材同一天可能在多个组投放），本页所有数字都按行加总后重算比率，无重复计算。</div>
  </div>
</div>
"""


def build_html(data):
    chart_js = CHART_JS_PATH.read_text(encoding="utf-8") if CHART_JS_PATH.exists() else ""
    data_json = json.dumps(data, ensure_ascii=False)
    colors_js = json.dumps(PERSON_COLORS, ensure_ascii=False)
    bg_js = json.dumps(PERSON_BG, ensure_ascii=False)

    html = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>快手投放日报 · __MMDD__</title>
<style>__CSS__</style>
</head>
<body>
<div class="topbar">
  <div class="topbar-row1">
    <span class="brand">🟠 快手投放日报 · __MMDD__</span>
  </div>
  <div class="topbar-row2">
    <span class="label">日期</span>
    <span id="dateChips" style="display:flex;gap:4px;flex-wrap:wrap"></span>
    <span class="range-btn" id="btnLatest">最新</span>
    <span class="range-btn" id="btnAll">全部</span>
    <span class="range-btn" id="btn7d">近7天</span>
  </div>
</div>
<div class="page">

__CALIBER__

  <div class="kpi-grid" id="kpiGrid"></div>

  <div class="charts-row">
    <div class="chart-card">
      <div class="section-title">转化漏斗趋势（所选日期范围）</div>
      <div class="chart-wrap"><canvas id="chartFunnel"></canvas></div>
    </div>
    <div class="chart-card">
      <div class="section-title">花费与 CPA 趋势</div>
      <div class="chart-wrap"><canvas id="chartCpa"></canvas></div>
    </div>
  </div>

  <div class="chart-card" style="margin-bottom:20px">
    <div class="section-title">编导表现</div>
    <div id="personRow" style="display:grid;grid-template-columns:repeat(4,1fr);gap:12px"></div>
  </div>

  <div class="table-card" style="margin-bottom:20px">
    <div class="table-toolbar">
      <div class="section-title" style="margin:0">📊 账户表现</div>
      <div class="table-info">3 个账户 · 全漏斗对比</div>
    </div>
    <div class="table-wrap"><table id="acctTable"><thead></thead><tbody id="acctBody"></tbody></table></div>
  </div>

  <div class="table-card" style="margin-bottom:20px">
    <div class="table-toolbar">
      <div class="section-title" style="margin:0">🗂 计划表现</div>
      <div class="table-info">按计划名称聚合</div>
    </div>
    <div class="table-wrap"><table id="planTable"><thead></thead><tbody id="planBody"></tbody></table></div>
  </div>

  <div class="filter-bar">
    <span class="filter-label">类型</span>
    <button class="filter-btn active" data-t="all">全部</button>
    <button class="filter-btn filter-btn-video" data-t="视频">视频</button>
    <button class="filter-btn filter-btn-tuwen" data-t="图文">图文</button>
    <button class="filter-btn filter-btn-ai" data-t="AI">平台AI</button>
    <span class="filter-sep"></span>
    <span class="filter-label">编导</span>
    <span id="personBtns" style="display:flex;gap:6px;flex-wrap:wrap"></span>
    <span class="filter-sep"></span>
    <input class="search-box" id="searchBox" placeholder="🔍 搜索素材名称 / ID">
  </div>

  <div class="table-card">
    <div class="table-toolbar">
      <div class="section-title" style="margin:0">🎬 素材明细</div>
      <div class="table-info">共 <span id="matCount">0</span> 条素材（所选日期累计）</div>
    </div>
    <div class="table-wrap"><table id="matTable"><thead></thead><tbody id="matBody"></tbody></table></div>
  </div>

</div>

<div class="modal-overlay" id="videoModal">
  <div class="modal">
    <div class="modal-header">
      <span class="modal-title" id="modalTitle"></span>
      <button class="modal-close" onclick="closeModal()">✕</button>
    </div>
    <div class="video-wrap"><video id="modalVideo" controls></video></div>
  </div>
</div>

<script>__CHARTJS__</script>
<script>
const DATA = __DATA_JSON__;
const PERSON_COLORS = __COLORS_JS__;
const PERSON_BG = __BG_JS__;

const fmtM = v => '¥' + v.toLocaleString('zh-CN', {minimumFractionDigits:2, maximumFractionDigits:2});
const fmtI = v => Math.round(v).toLocaleString('zh-CN');
const fmtP = v => v.toFixed(2) + '%';
const fmtP1 = v => v.toFixed(1) + '%';

const state = { dates: [...DATA.dates], type: 'all', person: 'all', search: '' };
const selDays = () => new Set(state.dates);

function aggDayRows(target, sel) {
  // target: {days:{date:{...}}} → 求和
  const s = {spend:0,imp:0,act:0,conv:0,deep:0,valid:0,open1:0,open3:0,open5:0,open10:0};
  for (const d of sel) {
    const day = target.days[d];
    if (!day) continue;
    for (const k in s) s[k] += day[k] || 0;
  }
  return s;
}
function aggMetrics(target, sel) {
  const s = aggDayRows(target, sel);
  s.act_rate = s.imp ? s.act / s.imp * 100 : 0;
  s.cvr = s.act ? s.conv / s.act * 100 : 0;
  s.deep_rate = s.conv ? s.deep / s.conv * 100 : 0;
  s.cpa = s.conv ? s.spend / s.conv : 0;
  return s;
}

/* ---------- KPI ---------- */
const KPI_DEFS = [
  ['总消耗', 'spend', 'fmtM', '花费（计费时间）', false],
  ['曝光数', 'imp', 'fmtI', '素材总曝光', false],
  ['行为数', 'act', 'fmtI', '约等于素材点击', false],
  ['行为率', 'act_rate', 'fmtP', '行为数 ÷ 曝光数', false],
  ['转化数', 'conv', 'fmtI', '转化数（计费时间）', false],
  ['转化率', 'cvr', 'fmtP', '转化数 ÷ 行为数', false],
  ['平均CPA', 'cpa', 'fmtM', '花费 ÷ 转化数', false],
  ['深转数', 'deep', 'fmtI', '深度转化数（计费时间）', false],
  ['深转率', 'deep_rate', 'fmtP', '深转 ÷ 转化', false],
  ['有效获客', 'valid', 'fmtI', '有效获客数（计费时间）', false],
  ['企微开口1次', 'open1', 'fmtI', '开口 1 次数量', true],
  ['开口3次', 'open3', 'fmtI', '开口 3 次数量', false],
  ['开口5次', 'open5', 'fmtI', '开口 5 次数量', false],
  ['开口10次', 'open10', 'fmtI', '开口 10 次数量', false],
];
function renderKpi() {
  const sel = selDays();
  const acc = DATA.accounts.map(a => ({id:a.id, ...aggMetrics(a, sel)}));
  const t = {};
  for (const a of acc) for (const k in a) {
    if (typeof a[k] === 'number') t[k] = (t[k] || 0) + a[k];
  }
  t.act_rate = t.imp ? t.act / t.imp * 100 : 0;
  t.cvr = t.act ? t.conv / t.act * 100 : 0;
  t.deep_rate = t.conv ? t.deep / t.conv * 100 : 0;
  t.cpa = t.conv ? t.spend / t.conv : 0;
  const prevD = DATA.dates[DATA.dates.indexOf(state.dates[0]) - 1];
  const prevSel = prevD ? new Set([prevD]) : new Set();
  const pt = {};
  if (prevD) {
    for (const a of DATA.accounts) {
      const s = aggMetrics(a, prevSel);
      for (const k in s) if (typeof s[k] === 'number') pt[k] = (pt[k] || 0) + s[k];
    }
  }
  const diff = (cur, prev) => {
    if (!prevD || Math.abs(cur - prev) < 1e-9) return '';
    const cls = cur >= prev ? 'inc' : 'dec';
    const sign = cur > prev ? '+' : '';
    return '<span class="tc-diff ' + cls + '">' + sign + (cur - prev).toLocaleString('zh-CN') + '</span>';
  };
  const grid = document.getElementById('kpiGrid');
  grid.innerHTML = KPI_DEFS.map(([label, key, fmt, sub, accent]) => {
    const val = t[key] || 0;
    const cls = accent ? 'kpi-card accent' : 'kpi-card';
    const dhtml = ['spend','conv','deep','open1'].includes(key) ? diff(val, pt[key] || 0) : '';
    return '<div class="' + cls + '"><div class="kpi-label">' + label +
      '<span class="help-tip" data-tip="' + sub + '"></span></div>' +
      '<div class="kpi-value">' + (fmt === 'fmtM' ? fmtM(val) : fmt === 'fmtP' ? fmtP(val) : fmtI(val)) + '</div>' +
      '<div class="kpi-sub">' + dhtml + sub + '</div></div>';
  }).join('');
}

/* ---------- 趋势图 ---------- */
let chartFunnel = null, chartCpa = null;
function renderCharts() {
  const sel = selDays();
  const ds = DATA.dates.filter(d => sel.has(d));
  const spend = [], conv = [], deep = [], open1 = [], cpa = [];
  for (const d of ds) {
    let s = {spend:0,conv:0,deep:0,open1:0};
    for (const a of DATA.accounts) {
      const day = a.days[d];
      if (day) { s.spend += day.spend||0; s.conv += day.conv||0; s.deep += day.deep||0; s.open1 += day.open1||0; }
    }
    spend.push(+s.spend.toFixed(2)); conv.push(+s.conv.toFixed(1)); deep.push(+s.deep.toFixed(1));
    open1.push(+s.open1.toFixed(1)); cpa.push(s.conv ? +(s.spend / s.conv).toFixed(2) : 0);
  }
  const base = {responsive:true, maintainAspectRatio:false,
    plugins:{legend:{labels:{boxWidth:12, font:{size:11}}}},
    scales:{y:{beginAtZero:true, ticks:{font:{size:10}}}, x:{ticks:{font:{size:10}}}}};
  if (chartFunnel) chartFunnel.destroy();
  chartFunnel = new Chart(document.getElementById('chartFunnel'), {
    type:'line', data:{labels:ds, datasets:[
      {label:'转化', data:conv, borderColor:'#3B82F6', backgroundColor:'rgba(59,130,246,.10)', fill:true, tension:.3, pointRadius:2},
      {label:'深转', data:deep, borderColor:'#F59E0B', backgroundColor:'rgba(245,158,11,.10)', fill:true, tension:.3, pointRadius:2},
      {label:'企微开口1次', data:open1, borderColor:'#10B981', backgroundColor:'rgba(16,185,129,.10)', fill:true, tension:.3, pointRadius:2}
    ]}, options:base
  });
  if (chartCpa) chartCpa.destroy();
  chartCpa = new Chart(document.getElementById('chartCpa'), {
    type:'bar', data:{labels:ds, datasets:[
      {label:'花费', data:spend, backgroundColor:'#3B82F6', borderRadius:3, yAxisID:'y'},
      {label:'CPA', data:cpa, borderColor:'#8B5CF6', backgroundColor:'#8B5CF6', type:'line', tension:.3, pointRadius:2, yAxisID:'y1'}
    ]},
    options:Object.assign({}, base, {scales:{
      y:Object.assign({}, base.scales.y, {position:'left', grid:{drawOnChartArea:false}}),
      y1:Object.assign({}, base.scales.y, {position:'right', grid:{drawOnChartArea:false}})
    }})
  });
}

/* ---------- 编导卡 ---------- */
function renderPersons() {
  const sel = selDays();
  const map = {};
  for (const m of DATA.materials) {
    const s = aggMetrics(m, sel);
    const p = m.person || '其他';
    if (!map[p]) map[p] = {spend:0,imp:0,act:0,conv:0,deep:0,valid:0,open1:0,cnt:0};
    for (const k of ['spend','imp','act','conv','deep','valid','open1']) map[p][k] += s[k];
    map[p].cnt += 1;
  }
  const wrap = document.getElementById('personRow');
  const list = Object.entries(map).sort((a,b) => b[1].spend - a[1].spend);
  wrap.innerHTML = list.map(([p, m]) => {
    const c = PERSON_COLORS[p] || '#64748B', bg = PERSON_BG[p] || '#F8FAFC';
    const deepRate = m.conv ? m.deep / m.conv * 100 : 0;
    const cpa = m.conv ? m.spend / m.conv : 0;
    return '<div class="kpi-card" style="margin:0;cursor:pointer" data-person="' + p + '">' +
      '<div class="kpi-label"><span class="person-badge" style="background:' + bg + ';color:' + c + '">' + p + '</span></div>' +
      '<div class="kpi-value" style="font-size:18px;color:' + c + '">' + fmtM(m.spend) + '</div>' +
      '<div class="kpi-sub">素材 ' + m.cnt + ' 条 · 转化 ' + fmtI(m.conv) + ' · 深转 ' + fmtI(m.deep) + '</div>' +
      '<div class="kpi-sub">CPA ' + fmtM(cpa) + ' · 深转率 ' + fmtP(deepRate) + ' · 开口1次 ' + fmtI(m.open1) + '</div>' +
    '</div>';
  }).join('') || '<div class="empty-state">暂无数据</div>';
}

/* ---------- 表格通用 ---------- */
const ACCT_COLS = [
  ['账户', 'id', 'txt'], ['花费', 'spend', 'fmtM'], ['曝光', 'imp', 'fmtI'],
  ['行为数', 'act', 'fmtI'], ['行为率', 'act_rate', 'fmtP'], ['转化', 'conv', 'fmtI'],
  ['转化率', 'cvr', 'fmtP'], ['CPA', 'cpa', 'fmtM'], ['深转', 'deep', 'fmtI'],
  ['深转率', 'deep_rate', 'fmtP'], ['有效获客', 'valid', 'fmtI'], ['开口1次', 'open1', 'fmtI'],
  ['开口3次', 'open3', 'fmtI'], ['开口5次', 'open5', 'fmtI'], ['开口10次', 'open10', 'fmtI'],
];
const PLAN_COLS = [
  ['计划名称', 'name', 'txt'], ['素材数', 'vid_count', 'fmtI'], ['花费', 'spend', 'fmtM'],
  ['曝光', 'imp', 'fmtI'], ['行为数', 'act', 'fmtI'], ['行为率', 'act_rate', 'fmtP'],
  ['转化', 'conv', 'fmtI'], ['转化率', 'cvr', 'fmtP'], ['CPA', 'cpa', 'fmtM'],
  ['深转', 'deep', 'fmtI'], ['深转率', 'deep_rate', 'fmtP'], ['有效获客', 'valid', 'fmtI'],
  ['开口1次', 'open1', 'fmtI'], ['开口3次', 'open3', 'fmtI'], ['开口5次', 'open5', 'fmtI'], ['开口10次', 'open10', 'fmtI'],
];
const MAT_COLS = [
  ['素材名称', 'name', 'name'], ['类型', 'type', 'type'], ['编导', 'person', 'person'],
  ['花费', 'spend', 'fmtM'], ['曝光', 'imp', 'fmtI'], ['行为数', 'act', 'fmtI'],
  ['行为率', 'act_rate', 'fmtP'], ['转化', 'conv', 'fmtI'], ['转化率', 'cvr', 'fmtP'],
  ['CPA', 'cpa', 'fmtM'], ['深转', 'deep', 'fmtI'], ['深转率', 'deep_rate', 'fmtP'],
  ['有效获客', 'valid', 'fmtI'], ['开口1', 'open1', 'fmtI'], ['开口3', 'open3', 'fmtI'],
  ['开口5', 'open5', 'fmtI'], ['开口10', 'open10', 'fmtI'], ['3秒播放率', 'p3', 'fmtP'],
  ['5秒播放率', 'p5', 'fmtP'], ['完播率', 'fin', 'fmtP'], ['封面点击率', 'cover_rate', 'fmtP'],
  ['播放', '', 'play'],
];

function buildHead(tableId, cols) {
  const thead = document.querySelector('#' + tableId + ' thead');
  thead.innerHTML = '<tr>' + cols.map(([label, key]) =>
    '<th data-k="' + key + '">' + label + '</th>').join('') + '</tr>';
}

let sortKey = {acct:null, plan:null, mat:null};
let sortDir = {acct:-1, plan:-1, mat:-1};
const TABLE_SHORT = {acctTable:'acct', planTable:'plan', matTable:'mat'};

function fmtCell(v, kind) {
  if (kind === 'fmtM') return fmtM(v);
  if (kind === 'fmtP') return fmtP(v);
  return fmtI(v);
}
function renderRowHtml(row, cols, tableId) {
  return '<tr>' + cols.map(([label, key, kind]) => {
    if (kind === 'name') return '<td class="mat-name">' + (row.name || '—') + '</td>';
    if (kind === 'type') {
      const t = row.type || '视频';
      const cls = t === '图文' ? 'type-tuwen' : t === 'AI' ? 'type-ai' : 'type-video';
      const txt = t === 'AI' ? '平台AI' : t;
      return '<td><span class="person-badge ' + cls + '">' + txt + '</span></td>';
    }
    if (kind === 'person') {
      const p = row.person || '其他';
      const c = PERSON_COLORS[p] || '#64748B', bg = PERSON_BG[p] || '#F8FAFC';
      return '<td><span class="person-badge" style="background:' + bg + ';color:' + c + '">' + p + '</span></td>';
    }
    if (kind === 'play') {
      if (!row.content) return '<td><span class="num-zero">—</span></td>';
      return '<td><button class="btn-play" onclick="openVideo(\\'' + row.vid + '\\')">▶ 播放</button></td>';
    }
    if (kind === 'txt') return '<td>' + row[key] + '</td>';
    const v = row[key] || 0;
    if (kind === 'fmtI' && v === 0) return '<td class="num num-zero">0</td>';
    if (key === 'deep' && v > 0) return '<td class="gaoquan-cell">' + fmtI(v) + '</td>';
    return '<td class="num">' + fmtCell(v, kind) + '</td>';
  }).join('') + '</tr>';
}

function renderAccounts() {
  const sel = selDays();
  const rows = DATA.accounts.map(a => ({id:a.id, ...aggMetrics(a, sel)}));
  const k = sortKey.acct || 'spend', dir = sortKey.acct ? sortDir.acct : -1;
  rows.sort((a,b) => ((a[k]||0) - (b[k]||0)) * dir);
  document.getElementById('acctBody').innerHTML =
    rows.map(r => renderRowHtml(r, ACCT_COLS, 'acct')).join('') ||
    '<tr><td colspan="15" class="empty-state">暂无数据</td></tr>';
}
function renderPlans() {
  const sel = selDays();
  const rows = DATA.plans.map(p => ({...p, ...aggMetrics(p, sel), vid_count: p.vid_count}));
  const k = sortKey.plan || 'spend', dir = sortKey.plan ? sortDir.plan : -1;
  rows.sort((a,b) => ((a[k]||0) - (b[k]||0)) * dir);
  document.getElementById('planBody').innerHTML =
    rows.map(r => renderRowHtml(r, PLAN_COLS, 'plan')).join('') ||
    '<tr><td colspan="16" class="empty-state">暂无数据</td></tr>';
}

/* ---------- 素材明细 ---------- */
function qAgg(m, sel) {
  let p3w=0, p5w=0, finw=0, qimp=0, coverc=0, covere=0;
  for (const d of sel) {
    const q = (m.qdays && m.qdays[d]) ? m.qdays[d] : null;
    if (!q) continue;
    const day = m.days[d];
    const imp = day ? (day.imp||0) : 0;
    p3w += (q.p3||0) * imp; p5w += (q.p5||0) * imp; finw += (q.fin||0) * imp; qimp += imp;
    coverc += (q.cover_rate||0); covere += 1;
  }
  return {
    p3: qimp ? p3w/qimp : 0, p5: qimp ? p5w/qimp : 0, fin: qimp ? finw/qimp : 0,
    cover_rate: covere ? coverc/covere : 0,
  };
}
function renderMaterials() {
  const sel = selDays();
  let list = [];
  for (const m of DATA.materials) {
    const s = aggMetrics(m, sel);
    if (s.spend <= 0 && s.imp <= 0 && s.act <= 0 && s.conv <= 0 && s.deep <= 0) continue;
    if (state.type !== 'all' && m.type !== state.type) continue;
    if (state.person !== 'all' && (m.person || '其他') !== state.person) continue;
    if (state.search) {
      const q = state.search.toLowerCase();
      if (!(m.name || '').toLowerCase().includes(q) && !String(m.vid).includes(q)) continue;
    }
    list.push({...m, ...s, ...qAgg(m, sel)});
  }
  const k = sortKey.mat || 'spend', dir = sortKey.mat ? sortDir.mat : -1;
  list.sort((a,b) => ((a[k]||0) - (b[k]||0)) * dir);
  document.getElementById('matCount').textContent = list.length;
  document.getElementById('matBody').innerHTML =
    list.map(r => renderRowHtml(r, MAT_COLS, 'mat')).join('') ||
    '<tr><td colspan="22" class="empty-state">暂无数据</td></tr>';
}

/* ---------- 日期 chips ---------- */
function renderChips() {
  const wrap = document.getElementById('dateChips');
  wrap.innerHTML = DATA.dates.map(d =>
    '<span class="date-chip' + (state.dates.includes(d) ? ' sel' : '') + '" data-d="' + d + '">' +
    d.slice(5) + '</span>').join('');
  wrap.querySelectorAll('.date-chip').forEach(el => {
    el.addEventListener('click', () => {
      const d = el.dataset.d;
      state.dates = state.dates.includes(d)
        ? (state.dates.length > 1 ? state.dates.filter(x => x !== d) : state.dates)
        : [...state.dates, d].sort();
      renderAll();
    });
  });
  document.getElementById('btnLatest').onclick = () => { state.dates = [DATA.dates[DATA.dates.length-1]]; renderAll(); };
  document.getElementById('btnAll').onclick = () => { state.dates = [...DATA.dates]; renderAll(); };
  document.getElementById('btn7d').onclick = () => { state.dates = DATA.dates.slice(-7); renderAll(); };
}

/* ---------- 筛选与搜索 ---------- */
function renderPersonBtns() {
  const persons = ['all', ...new Set(DATA.materials.map(m => m.person || '其他'))];
  const wrap = document.getElementById('personBtns');
  wrap.innerHTML = persons.map(p =>
    '<button class="filter-btn' + (state.person === p ? ' active' : '') + '" data-p="' + p + '">' +
    (p === 'all' ? '全部' : p) + '</button>').join('');
  wrap.querySelectorAll('.filter-btn').forEach(b => {
    b.addEventListener('click', () => {
      state.person = b.dataset.p; renderMaterials(); renderPersonBtns();
    });
  });
}
function initFilters() {
  document.querySelectorAll('.filter-bar .filter-btn[data-t]').forEach(b => {
    b.addEventListener('click', () => {
      document.querySelectorAll('.filter-bar .filter-btn[data-t]').forEach(x => x.classList.remove('active'));
      b.classList.add('active'); state.type = b.dataset.t; renderMaterials();
    });
  });
  document.getElementById('searchBox').addEventListener('input', e => {
    state.search = e.target.value.trim(); renderMaterials();
  });
}
// 点编导卡切换筛选
document.getElementById('personRow').addEventListener('click', e => {
  const card = e.target.closest('[data-person]');
  if (!card) return;
  const p = card.dataset.person;
  state.person = (state.person === p) ? 'all' : p;
  renderMaterials(); renderPersonBtns();
});

/* ---------- 排序 ---------- */
function bindSort(tableId, keyHolder, dirHolder, rerender) {
  const short = TABLE_SHORT[tableId];
  document.querySelectorAll('#' + tableId + ' thead th').forEach(th => {
    th.addEventListener('click', () => {
      const k = th.dataset.k;
      if (!k) return;
      if (keyHolder[short] === k) dirHolder[short] *= -1;
      else { keyHolder[short] = k; dirHolder[short] = -1; }
      document.querySelectorAll('#' + tableId + ' thead th').forEach(x => x.classList.remove('sorted-asc','sorted-desc'));
      th.classList.add(dirHolder[short] === -1 ? 'sorted-desc' : 'sorted-asc');
      rerender();
    });
  });
}

/* ---------- 视频弹窗 ---------- */
function openVideo(vid) {
  const m = DATA.materials.find(x => x.vid === vid);
  if (!m || !m.content) return;
  document.getElementById('modalTitle').textContent = m.name || m.vid;
  document.getElementById('modalVideo').src = m.content;
  document.getElementById('videoModal').classList.add('open');
}
function closeModal() {
  document.getElementById('videoModal').classList.remove('open');
  document.getElementById('modalVideo').pause();
  document.getElementById('modalVideo').src = '';
}
document.getElementById('videoModal').addEventListener('click', e => {
  if (e.target.id === 'videoModal') closeModal();
});

function renderAll() {
  renderKpi(); renderCharts(); renderPersons(); renderChips();
  renderAccounts(); renderPlans(); renderMaterials(); renderPersonBtns();
}

buildHead('acctTable', ACCT_COLS);
buildHead('planTable', PLAN_COLS);
buildHead('matTable', MAT_COLS);
bindSort('acctTable', sortKey, sortDir, renderAccounts);
bindSort('planTable', sortKey, sortDir, renderPlans);
bindSort('matTable', sortKey, sortDir, renderMaterials);
initFilters();
renderAll();
</script>
</body>
</html>"""

    html = (html.replace("__MMDD__", REPORT_MMDD)
                .replace("__CSS__", CSS)
                .replace("__CALIBER__", CALIBER_HTML)
                .replace("__CHARTJS__", chart_js)
                .replace("__DATA_JSON__", data_json)
                .replace("__COLORS_JS__", colors_js)
                .replace("__BG_JS__", bg_js))
    return html


def main():
    data = load_data()
    print(f"[数据] 账户 {len(data['accounts'])} 个, 计划 {len(data['plans'])} 个, 素材 {len(data['materials'])} 条, 日期 {data['dates'][0]}~{data['dates'][-1]}")
    html = build_html(data)
    out = REPORTS_DIR / f"快手投放报告_{REPORT_MMDD}.html"
    out.write_text(html, encoding="utf-8")
    print(f"[OK] {out} ({out.stat().st_size/1024:.0f} KB)")


if __name__ == "__main__":
    main()
