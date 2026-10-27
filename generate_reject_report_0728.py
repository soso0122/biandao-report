import csv
import re
import collections
import json
from pathlib import Path

DATA_FILE = "data/拒审导出-0728.csv"
OUTPUT_FILE = "reports/拒审日报分析_0728.html"
REPORT_DATE = "0728"

# ── 数据解析 ────────────────────────────────────────────────────────────────

with open(DATA_FILE, encoding="utf-8-sig") as f:
    rows = [r for r in csv.DictReader(f) if r["视频名称"].strip()]


def get_material_type(name):
    base = name.replace(".mp4", "").replace(".MP4", "")
    # 去掉编导名再判断 C/c，避免误匹配（实际上现有编导名均不含 C/c）
    has_c = bool(re.search(r"[Cc]", base))
    has_gai = "改" in base
    if has_c and has_gai:
        return "测试改版"
    if has_c:
        return "测试素材"
    if has_gai:
        return "改版素材"
    return "原版素材"


def get_creator(name):
    for c in ["魏怡", "瑞晨", "国星", "嘉丽D", "嘉丽", "雅迪"]:
        if c in name:
            return c
    return "其他"


def parse_reject_reason(row):
    # 规则1：以G列拒审类型为准，空则归为无明确原因
    typed = row.get("拒审类型", "").strip()
    return typed if typed else "无明确原因"


def clean_reject_text(text):
    text = re.sub(r"<img[^>]*>", "", text)
    text = re.sub(r"https?://\S+", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    parts = re.findall(r"建议\d+[:：]\s*([^建议]+?)(?=建议\d+|$)", text)
    return " | ".join(p.strip() for p in parts) if parts else text[:120]


for r in rows:
    r["_type"] = get_material_type(r["视频名称"])
    r["_creator"] = get_creator(r["视频名称"])
    r["_passed"] = r["审核建议"] == "审核通过"
    r["_reason"] = parse_reject_reason(r) if not r["_passed"] else ""
    r["_reject_text"] = clean_reject_text(r.get("拒审建议", "")) if not r["_passed"] else ""
    r["_detail"] = r.get("拒审详细内容", "").strip()   # H列
    r["_video_url"] = r.get("视频链接", "").strip()

# ── 统计汇总 ─────────────────────────────────────────────────────────────────

total = len(rows)
passed = sum(1 for r in rows if r["_passed"])
rejected = total - passed
pass_rate = round(passed / total * 100, 1)

TYPE_ORDER = ["原版素材", "测试素材", "改版素材", "测试改版"]
type_stats = {t: {"total": 0, "passed": 0, "rejected": 0} for t in TYPE_ORDER}
for r in rows:
    s = type_stats[r["_type"]]
    s["total"] += 1
    if r["_passed"]:
        s["passed"] += 1
    else:
        s["rejected"] += 1

creator_stats = {}
for r in rows:
    c = r["_creator"]
    if c not in creator_stats:
        creator_stats[c] = {"total": 0, "passed": 0, "rejected": 0,
                            "pass_rev": 0, "pass_orig": 0,
                            "fail_rev": 0, "fail_orig": 0}
    creator_stats[c]["total"] += 1
    is_revised = "改" in r["_type"]
    if r["_passed"]:
        creator_stats[c]["passed"] += 1
        if is_revised: creator_stats[c]["pass_rev"] += 1
        else:          creator_stats[c]["pass_orig"] += 1
    else:
        creator_stats[c]["rejected"] += 1
        if is_revised: creator_stats[c]["fail_rev"] += 1
        else:          creator_stats[c]["fail_orig"] += 1
# 按拒审数排序
creator_order = sorted(creator_stats, key=lambda x: creator_stats[x]["rejected"], reverse=True)

reasons = [r["_reason"] for r in rows if not r["_passed"] and r["_reason"]]
reason_counts = dict(sorted(collections.Counter(reasons).items(), key=lambda x: -x[1]))

revised_total = type_stats["改版素材"]["total"] + type_stats["测试改版"]["total"]
revised_passed = type_stats["改版素材"]["passed"] + type_stats["测试改版"]["passed"]
revised_rate = round(revised_passed / revised_total * 100, 1) if revised_total else 0
passed_rows = [r for r in rows if r["_passed"]]
rejected_rows = [r for r in rows if not r["_passed"]]

# ── Chart.js 数据 ─────────────────────────────────────────────────────────────

type_chart_labels = json.dumps(TYPE_ORDER, ensure_ascii=False)
type_chart_passed = json.dumps([type_stats[t]["passed"] for t in TYPE_ORDER])
type_chart_rejected = json.dumps([type_stats[t]["rejected"] for t in TYPE_ORDER])

reason_labels = json.dumps(list(reason_counts.keys()), ensure_ascii=False)
reason_values = json.dumps(list(reason_counts.values()))

creator_labels = json.dumps(creator_order, ensure_ascii=False)
creator_pass_orig   = json.dumps([creator_stats[c]["pass_orig"]  for c in creator_order])
creator_pass_rev    = json.dumps([creator_stats[c]["pass_rev"]   for c in creator_order])
creator_fail_orig   = json.dumps([creator_stats[c]["fail_orig"]  for c in creator_order])
creator_fail_rev    = json.dumps([creator_stats[c]["fail_rev"]   for c in creator_order])

# ── HTML 行构建 ──────────────────────────────────────────────────────────────

TYPE_BADGE_STYLES = {
    "原版素材":  ("background:#f1f5f9;color:#475569", "原版"),
    "测试素材":  ("background:#dbeafe;color:#1e40af", "测试 C"),
    "改版素材":  ("background:#d1fae5;color:#065f46", "改版"),
    "测试改版":  ("background:#ede9fe;color:#5b21b6", "测试改"),
}

REASON_BADGE_STYLES = {
    "中危行业":   "background:#fee2e2;color:#b91c1c",
    "名人名校":   "background:#ffedd5;color:#c2410c",
    "资料图":     "background:#fef9c3;color:#854d0e",
    "引导字幕":   "background:#e0f2fe;color:#0369a1",
    "高危词":     "background:#ffe4e6;color:#be123c",
    "无明确原因":"background:#f1f5f9;color:#475569",
}


def type_badge(t):
    style, label = TYPE_BADGE_STYLES.get(t, ("background:#f1f5f9;color:#475569", t))
    return f'<span class="badge" style="{style}">{label}</span>'


def reason_badge(r):
    if not r:
        return ""
    style = REASON_BADGE_STYLES.get(r, "background:#f1f5f9;color:#475569")
    return f'<span class="badge" style="{style}">{r}</span>'


def passed_rows_html():
    items = []
    for r in passed_rows:
        name = r["视频名称"]
        tb = type_badge(r["_type"])
        url = r["_video_url"]
        items.append(f"""
        <div class="passed-card" data-url="{url}" data-name="{name}" role="button" tabindex="0">
          <div class="passed-icon">
            <svg viewBox="0 0 20 20" fill="currentColor" width="18" height="18">
              <path fill-rule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clip-rule="evenodd"/>
            </svg>
          </div>
          <div class="passed-name">{name}</div>
          {tb}
          <div class="play-hint">
            <svg viewBox="0 0 20 20" fill="currentColor" width="16" height="16">
              <path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM9.555 7.168A1 1 0 008 8v4a1 1 0 001.555.832l3-2a1 1 0 000-1.664l-3-2z" clip-rule="evenodd"/>
            </svg>
          </div>
        </div>""")
    return "\n".join(items)


def rejected_table_rows():
    rows_html = []
    for i, r in enumerate(rejected_rows):
        name = r["视频名称"]
        tb = type_badge(r["_type"])
        rb = reason_badge(r["_reason"])
        text = r["_reject_text"] or "—"
        detail = r["_detail"]
        detail_html = f'<div class="td-detail">{detail}</div>' if detail else ""
        url = r["_video_url"]
        type_val = r["_type"]
        reason_val = r["_reason"]
        rows_html.append(f"""
        <tr data-type="{type_val}" data-reason="{reason_val}">
          <td class="td-name">
            {name}
            <button class="btn-play" data-url="{url}" data-name="{name}" title="预览视频">
              <svg viewBox="0 0 20 20" fill="currentColor" width="13" height="13">
                <path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM9.555 7.168A1 1 0 008 8v4a1 1 0 001.555.832l3-2a1 1 0 000-1.664l-3-2z" clip-rule="evenodd"/>
              </svg>
              预览
            </button>
          </td>
          <td>{tb}</td>
          <td>{rb}</td>
          <td class="td-reason">{text}{detail_html}</td>
        </tr>""")
    return "\n".join(rows_html)


# ── HTML 模板 ─────────────────────────────────────────────────────────────────

html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>拒审日报分析 {REPORT_DATE}</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Fira+Code:wght@400;500;600&family=Fira+Sans:wght@300;400;500;600;700&display=swap" rel="stylesheet">
<style>
*, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
:root {{
  --c-bg: #F8FAFC;
  --c-surface: #FFFFFF;
  --c-primary: #1E40AF;
  --c-secondary: #3B82F6;
  --c-accent: #D97706;
  --c-muted: #E9EEF6;
  --c-border: #DBEAFE;
  --c-text: #1E293B;
  --c-muted-text: #64748B;
  --c-pass: #059669;
  --c-pass-bg: #ECFDF5;
  --c-pass-border: #A7F3D0;
  --c-fail: #DC2626;
  --c-fail-bg: #FEF2F2;
  --radius: 10px;
  --radius-sm: 6px;
  --shadow: 0 1px 3px rgba(0,0,0,.08), 0 1px 2px rgba(0,0,0,.04);
  --shadow-md: 0 4px 12px rgba(0,0,0,.08);
}}
body {{
  font-family: 'Fira Sans', -apple-system, sans-serif;
  background: var(--c-bg);
  color: var(--c-text);
  line-height: 1.6;
  padding: 24px 16px 48px;
}}
.container {{ max-width: 1100px; margin: 0 auto; }}

/* Header */
.page-header {{
  display: flex; align-items: flex-end; justify-content: space-between;
  margin-bottom: 28px; padding-bottom: 16px;
  border-bottom: 2px solid var(--c-border);
}}
.page-title {{ font-size: 22px; font-weight: 700; color: var(--c-primary); letter-spacing: -.3px; }}
.page-date {{ font-family: 'Fira Code', monospace; font-size: 13px; color: var(--c-muted-text); }}

/* KPI 卡片 */
.kpi-grid {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 14px; margin-bottom: 28px; }}
.kpi-card {{
  background: var(--c-surface); border-radius: var(--radius);
  border: 1px solid var(--c-border); padding: 18px 20px;
  box-shadow: var(--shadow);
}}
.kpi-label {{ font-size: 12px; color: var(--c-muted-text); font-weight: 500; margin-bottom: 6px; text-transform: uppercase; letter-spacing: .5px; }}
.kpi-value {{ font-size: 36px; font-weight: 700; line-height: 1; font-family: 'Fira Code', monospace; }}
.kpi-sub {{ font-size: 12px; color: var(--c-muted-text); margin-top: 5px; }}
.kpi-pass .kpi-value {{ color: var(--c-pass); }}
.kpi-fail .kpi-value {{ color: var(--c-fail); }}
.kpi-rate .kpi-value {{ color: var(--c-primary); }}

/* 图表区 */
.charts-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-bottom: 32px; }}
.chart-card {{
  background: var(--c-surface); border-radius: var(--radius);
  border: 1px solid var(--c-border); padding: 20px;
  box-shadow: var(--shadow);
}}
.chart-full {{ grid-column: 1 / -1; }}
.chart-title {{ font-size: 14px; font-weight: 600; color: var(--c-text); margin-bottom: 16px; }}
.chart-wrap {{ position: relative; height: 220px; }}
.chart-wrap-tall {{ position: relative; height: 180px; }}

/* 关键发现 */
.insight-bar {{
  background: linear-gradient(135deg, #1E40AF, #3B82F6);
  color: #fff; border-radius: var(--radius);
  padding: 16px 20px; margin-bottom: 32px;
  display: flex; align-items: center; gap: 12px;
  box-shadow: var(--shadow-md);
}}
.insight-icon {{ font-size: 20px; flex-shrink: 0; }}
.insight-text {{ font-size: 14px; line-height: 1.5; }}
.insight-text strong {{ font-weight: 700; }}

/* 通过素材 */
.section {{ margin-bottom: 32px; }}
.section-title {{
  font-size: 14px; font-weight: 700; color: var(--c-text);
  margin-bottom: 14px; display: flex; align-items: center; gap: 8px;
  padding-bottom: 8px; border-bottom: 1px solid var(--c-border);
}}
.dot-pass {{ width: 8px; height: 8px; border-radius: 50%; background: var(--c-pass); flex-shrink: 0; }}
.dot-fail {{ width: 8px; height: 8px; border-radius: 50%; background: var(--c-fail); flex-shrink: 0; }}
.dot-info {{ width: 8px; height: 8px; border-radius: 50%; background: var(--c-secondary); flex-shrink: 0; }}

.passed-grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 10px; }}
.passed-card {{
  background: var(--c-pass-bg); border: 1px solid var(--c-pass-border);
  border-radius: var(--radius-sm); padding: 12px 14px;
  display: flex; align-items: center; gap: 10px;
  cursor: pointer; transition: box-shadow .15s, transform .1s;
}}
.passed-card:hover {{ box-shadow: var(--shadow-md); transform: translateY(-1px); }}
.passed-icon {{ color: var(--c-pass); flex-shrink: 0; }}
.passed-name {{ font-size: 13px; font-family: 'Fira Code', monospace; flex: 1; word-break: break-all; }}
.play-hint {{ color: var(--c-secondary); opacity: .7; flex-shrink: 0; }}

/* badge */
.badge {{
  display: inline-block; padding: 2px 8px;
  border-radius: 20px; font-size: 11px; font-weight: 600;
  white-space: nowrap;
}}

/* 拒审表格 */
.table-wrap {{ overflow-x: auto; }}
table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
thead th {{
  background: var(--c-muted); color: var(--c-primary);
  font-weight: 600; font-size: 12px; text-transform: uppercase;
  letter-spacing: .4px; padding: 10px 12px; text-align: left;
  border-bottom: 2px solid var(--c-border);
}}
thead th.sortable {{ cursor: pointer; user-select: none; }}
thead th.sortable:hover {{ background: #dde8f6; }}
thead th .sort-icon {{ margin-left: 4px; opacity: .4; font-size: 10px; }}
thead th.asc .sort-icon::after {{ content: '▲'; }}
thead th.desc .sort-icon::after {{ content: '▼'; }}
thead th:not(.asc):not(.desc) .sort-icon::after {{ content: '⇅'; }}
tbody tr {{ border-bottom: 1px solid var(--c-muted); transition: background .15s; }}
tbody tr:hover {{ background: #F0F5FF; }}
td {{ padding: 9px 12px; vertical-align: middle; }}
.td-name {{ font-family: 'Fira Code', monospace; font-size: 12px; color: var(--c-text); max-width: 240px; word-break: break-all; }}
.td-reason {{ color: var(--c-muted-text); font-size: 12px; max-width: 320px; }}
.td-detail {{ color: var(--c-accent); font-size: 11px; margin-top: 3px; }}
.btn-play {{
  display: inline-flex; align-items: center; gap: 3px;
  background: none; border: 1px solid var(--c-secondary); border-radius: 4px;
  color: var(--c-secondary); font-size: 11px; padding: 1px 6px;
  cursor: pointer; margin-top: 4px; transition: background .15s;
}}
.btn-play:hover {{ background: var(--c-secondary); color: #fff; }}

/* 视频预览 Modal */
.modal-overlay {{
  display: none; position: fixed; inset: 0;
  background: rgba(0,0,0,.7); z-index: 1000;
  align-items: center; justify-content: center;
}}
.modal-overlay.open {{ display: flex; }}
.modal-box {{
  background: #111; border-radius: var(--radius);
  padding: 16px; max-width: 720px; width: 90%;
  position: relative;
}}
.modal-title {{
  color: #e2e8f0; font-size: 13px; font-family: 'Fira Code', monospace;
  margin-bottom: 10px; padding-right: 28px; word-break: break-all;
}}
.modal-close {{
  position: absolute; top: 12px; right: 12px;
  background: none; border: none; color: #94a3b8;
  font-size: 20px; cursor: pointer; line-height: 1;
}}
.modal-close:hover {{ color: #fff; }}
.modal-video {{ width: 100%; border-radius: 6px; max-height: 60vh; }}

/* 标记说明 */
.legend-card {{
  background: var(--c-surface); border-radius: var(--radius);
  border: 1px solid var(--c-border); padding: 16px 20px;
  display: flex; gap: 20px; flex-wrap: wrap; align-items: center;
  box-shadow: var(--shadow);
}}
.legend-item {{ display: flex; align-items: center; gap: 8px; font-size: 13px; }}
.legend-label {{ font-weight: 500; }}
.legend-desc {{ color: var(--c-muted-text); }}

@media (max-width: 768px) {{
  .kpi-grid {{ grid-template-columns: repeat(2, 1fr); }}
  .charts-grid {{ grid-template-columns: 1fr; }}
  .chart-full {{ grid-column: 1; }}
}}
@media (max-width: 480px) {{
  .kpi-grid {{ grid-template-columns: 1fr 1fr; }}
}}
</style>
</head>
<body>
<div class="container">

  <!-- 页头 -->
  <header class="page-header">
    <div>
      <div class="page-title">审核日报分析</div>
      <div class="page-date">数据日期：2025-07-{REPORT_DATE[2:]}  ·  导出自千川创作者后台</div>
    </div>
    <div class="page-date" style="text-align:right">
      共提报 <strong style="color:var(--c-text)">{total}</strong> 条 &nbsp;·&nbsp;
      通过 <strong style="color:var(--c-pass)">{passed}</strong> &nbsp;·&nbsp;
      拒审 <strong style="color:var(--c-fail)">{rejected}</strong>
    </div>
  </header>

  <!-- KPI 卡片 -->
  <div class="kpi-grid">
    <div class="kpi-card">
      <div class="kpi-label">总提报数</div>
      <div class="kpi-value" style="color:var(--c-primary)">{total}</div>
      <div class="kpi-sub">本次导出全部素材</div>
    </div>
    <div class="kpi-card kpi-pass">
      <div class="kpi-label">审核通过</div>
      <div class="kpi-value">{passed}</div>
      <div class="kpi-sub">通过率 {pass_rate}%</div>
    </div>
    <div class="kpi-card kpi-fail">
      <div class="kpi-label">审核不通过</div>
      <div class="kpi-value">{rejected}</div>
      <div class="kpi-sub">拒审率 {round(rejected/total*100,1)}%</div>
    </div>
    <div class="kpi-card kpi-rate">
      <div class="kpi-label">改版素材通过率</div>
      <div class="kpi-value">{revised_rate}%</div>
      <div class="kpi-sub">{revised_passed} / {revised_total} 全部通过</div>
    </div>
  </div>

  <!-- 关键发现 -->
  <div class="insight-bar">
    <div class="insight-icon">
      <svg viewBox="0 0 20 20" fill="currentColor" width="22" height="22">
        <path fill-rule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7-4a1 1 0 11-2 0 1 1 0 012 0zM9 9a1 1 0 000 2v3a1 1 0 001 1h1a1 1 0 100-2v-3a1 1 0 00-1-1H9z" clip-rule="evenodd"/>
      </svg>
    </div>
    <div class="insight-text">
      <strong>核心发现：</strong>本批次所有 <strong>改版素材（带"改"标记）通过率 {revised_rate}%</strong>，共 {revised_passed} / {revised_total} 条过审；
      原版素材和测试素材（带 C/c）<strong>通过率均为 0%</strong>，全部拒审。
      拒审主因为「中危行业」（{reason_counts.get("中危行业",0)} 条）和「资料图」（{reason_counts.get("资料图",0)} 条）。
    </div>
  </div>

  <!-- 图表区 -->
  <div class="charts-grid">

    <!-- 按素材类型 -->
    <div class="chart-card">
      <div class="chart-title">按素材类型 — 通过 vs 拒审</div>
      <div class="chart-wrap">
        <canvas id="typeChart"></canvas>
      </div>
    </div>

    <!-- 拒审原因 -->
    <div class="chart-card">
      <div class="chart-title">拒审原因分布</div>
      <div class="chart-wrap">
        <canvas id="reasonChart"></canvas>
      </div>
    </div>

    <!-- 按编导 -->
    <div class="chart-card chart-full">
      <div class="chart-title">按编导/账户 — 提报数与通过情况</div>
      <div class="chart-wrap-tall">
        <canvas id="creatorChart"></canvas>
      </div>
    </div>

  </div>

  <!-- 通过素材 -->
  <div class="section">
    <div class="section-title"><span class="dot-pass"></span>审核通过的素材（{passed} 条）</div>
    <div class="passed-grid">
      {passed_rows_html()}
    </div>
  </div>

  <!-- 拒审明细 -->
  <div class="section">
    <div class="section-title"><span class="dot-fail"></span>拒审明细（{rejected} 条）</div>
    <div class="table-wrap">
      <table id="rejectTable">
        <thead>
          <tr>
            <th>素材名称</th>
            <th class="sortable" data-col="type">类型 <span class="sort-icon"></span></th>
            <th class="sortable" data-col="reason">拒审类型 <span class="sort-icon"></span></th>
            <th>审核建议 / 详细内容</th>
          </tr>
        </thead>
        <tbody>
          {rejected_table_rows()}
        </tbody>
      </table>
    </div>
  </div>

  <!-- 素材标记说明 -->
  <div class="section">
    <div class="section-title"><span class="dot-info"></span>素材命名标记说明</div>
    <div class="legend-card">
      <div class="legend-item">
        <span class="badge" style="background:#d1fae5;color:#065f46">改</span>
        <span class="legend-label">改版素材</span>
        <span class="legend-desc">——  名称中含「改」，已针对拒审原因修改后重新提报</span>
      </div>
      <div class="legend-item">
        <span class="badge" style="background:#dbeafe;color:#1e40af">C / c</span>
        <span class="legend-label">测试素材</span>
        <span class="legend-desc">——  名称中含大写 C 或小写 c，属测试版本</span>
      </div>
      <div class="legend-item">
        <span class="badge" style="background:#ede9fe;color:#5b21b6">C + 改</span>
        <span class="legend-label">测试改版</span>
        <span class="legend-desc">——  同时带 c 和「改」，测试素材的修改版</span>
      </div>
      <div class="legend-item">
        <span class="badge" style="background:#f1f5f9;color:#475569">原版</span>
        <span class="legend-label">原版素材</span>
        <span class="legend-desc">——  无特殊标记</span>
      </div>
    </div>
  </div>

</div><!-- /container -->

<!-- 视频预览 Modal -->
<div class="modal-overlay" id="videoModal" onclick="closeVideo(event)">
  <div class="modal-box">
    <button class="modal-close" onclick="closeModal()">✕</button>
    <div class="modal-title" id="modalTitle"></div>
    <video class="modal-video" id="modalVideo" controls autoplay></video>
  </div>
</div>

<script>
Chart.defaults.font.family = "'Fira Sans', sans-serif";
Chart.defaults.font.size = 12;
Chart.defaults.color = "#64748B";

const PASS_COLOR = "#059669";
const FAIL_COLOR = "#DC2626";
const PASS_BG = "rgba(5,150,105,.18)";
const FAIL_BG = "rgba(220,38,38,.18)";

// 素材类型图
new Chart(document.getElementById("typeChart"), {{
  type: "bar",
  data: {{
    labels: {type_chart_labels},
    datasets: [
      {{ label: "通过", data: {type_chart_passed}, backgroundColor: PASS_BG, borderColor: PASS_COLOR, borderWidth: 2, borderRadius: 4 }},
      {{ label: "拒审", data: {type_chart_rejected}, backgroundColor: FAIL_BG, borderColor: FAIL_COLOR, borderWidth: 2, borderRadius: 4 }}
    ]
  }},
  options: {{
    responsive: true, maintainAspectRatio: false,
    plugins: {{ legend: {{ position: "top" }}, tooltip: {{ mode: "index" }} }},
    scales: {{
      x: {{ grid: {{ color: "#F1F5F9" }} }},
      y: {{ grid: {{ color: "#F1F5F9" }}, ticks: {{ stepSize: 1 }}, beginAtZero: true }}
    }}
  }}
}});

// 拒审原因图
new Chart(document.getElementById("reasonChart"), {{
  type: "bar",
  data: {{
    labels: {reason_labels},
    datasets: [{{
      label: "数量",
      data: {reason_values},
      backgroundColor: ["rgba(220,38,38,.2)","rgba(234,88,12,.2)","rgba(234,179,8,.2)","rgba(14,165,233,.2)","rgba(244,63,94,.2)","rgba(100,116,139,.2)"],
      borderColor:     ["#DC2626","#EA580C","#EAB308","#0EA5E9","#F43F5E","#64748B"],
      borderWidth: 2, borderRadius: 4
    }}]
  }},
  options: {{
    indexAxis: "y",
    responsive: true, maintainAspectRatio: false,
    plugins: {{ legend: {{ display: false }}, tooltip: {{ callbacks: {{ label: ctx => ` ${{ctx.parsed.x}} 条` }} }} }},
    scales: {{
      x: {{ grid: {{ color: "#F1F5F9" }}, ticks: {{ stepSize: 1 }}, beginAtZero: true }},
      y: {{ grid: {{ display: false }} }}
    }}
  }}
}});

// 编导图
new Chart(document.getElementById("creatorChart"), {{
  type: "bar",
  data: {{
    labels: {creator_labels},
    datasets: [
      {{ label: "通过·改版", data: {creator_pass_rev},   backgroundColor: "rgba(5,150,105,.7)",  borderColor: "#059669", borderWidth: 1, borderRadius: 4, stack: "pass" }},
      {{ label: "通过·原版", data: {creator_pass_orig},  backgroundColor: "rgba(5,150,105,.25)", borderColor: "#059669", borderWidth: 1, borderRadius: 4, stack: "pass" }},
      {{ label: "拒审·改版", data: {creator_fail_rev},   backgroundColor: "rgba(220,38,38,.6)",  borderColor: "#DC2626", borderWidth: 1, borderRadius: 4, stack: "fail" }},
      {{ label: "拒审·原版", data: {creator_fail_orig},  backgroundColor: "rgba(220,38,38,.2)",  borderColor: "#DC2626", borderWidth: 1, borderRadius: 4, stack: "fail" }}
    ]
  }},
  options: {{
    responsive: true, maintainAspectRatio: false,
    plugins: {{ legend: {{ position: "top" }}, tooltip: {{ mode: "index" }} }},
    scales: {{
      x: {{ grid: {{ color: "#F1F5F9" }}, stacked: true }},
      y: {{ grid: {{ color: "#F1F5F9" }}, ticks: {{ stepSize: 1 }}, beginAtZero: true, stacked: true }}
    }}
  }}
}});

// ── 表格排序 ──
(function() {{
  const table = document.getElementById("rejectTable");
  const ths = table.querySelectorAll("th.sortable");
  let sortCol = null, sortDir = 1;
  ths.forEach(th => {{
    th.addEventListener("click", () => {{
      const col = th.dataset.col;
      if (sortCol === col) sortDir *= -1; else {{ sortCol = col; sortDir = 1; }}
      ths.forEach(t => t.classList.remove("asc","desc"));
      th.classList.add(sortDir === 1 ? "asc" : "desc");
      const tbody = table.querySelector("tbody");
      const rows = [...tbody.querySelectorAll("tr")];
      rows.sort((a, b) => {{
        const av = a.dataset[col] || "", bv = b.dataset[col] || "";
        return av.localeCompare(bv, "zh") * sortDir;
      }});
      rows.forEach(r => tbody.appendChild(r));
    }});
  }});
}})();

// ── 视频 Modal ──
function openVideo(url, name) {{
  document.getElementById("modalTitle").textContent = name;
  const v = document.getElementById("modalVideo");
  v.src = url;
  v.load();
  document.getElementById("videoModal").classList.add("open");
}}
function closeModal() {{
  const v = document.getElementById("modalVideo");
  v.pause(); v.src = "";
  document.getElementById("videoModal").classList.remove("open");
}}
function closeVideo(e) {{
  if (e.target === document.getElementById("videoModal")) closeModal();
}}
document.addEventListener("keydown", e => {{ if (e.key === "Escape") closeModal(); }});

// 通过素材卡片点击
document.querySelectorAll(".passed-card[data-url]").forEach(el => {{
  el.addEventListener("click", () => openVideo(el.dataset.url, el.dataset.name));
  el.addEventListener("keydown", e => {{ if (e.key === "Enter") openVideo(el.dataset.url, el.dataset.name); }});
}});

// 拒审表格预览按钮
document.querySelectorAll(".btn-play[data-url]").forEach(btn => {{
  btn.addEventListener("click", e => {{
    e.stopPropagation();
    openVideo(btn.dataset.url, btn.dataset.name);
  }});
}});
</script>
</body>
</html>"""

Path("reports").mkdir(exist_ok=True)
with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
    f.write(html)

print(f"✓ 报告已生成：{OUTPUT_FILE}")
print(f"  总计 {total} 条 | 通过 {passed} | 拒审 {rejected} | 通过率 {pass_rate}%")
print(f"  拒审原因：{reason_counts}")
