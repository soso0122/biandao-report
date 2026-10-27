#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import csv, json, sys
from collections import defaultdict
from datetime import datetime

DATE_LABEL = sys.argv[1] if len(sys.argv) > 1 else '0731'
CSV_INVEST = sys.argv[2] if len(sys.argv) > 2 else f'data/【周报】引导素材-{DATE_LABEL}.csv'
CSV_REVIEW = sys.argv[3] if len(sys.argv) > 3 else f'data/【周报】引导素材过审数据-{DATE_LABEL}.csv'
OUT_PATH   = sys.argv[4] if len(sys.argv) > 4 else f'reports/引导素材分析报告_{DATE_LABEL}.html'

def read_csv(path):
    with open(path, encoding='utf-8-sig') as f:
        return list(csv.DictReader(f))

def extract_editor(name):
    name = name.strip()
    if '微信视频' in name: return '外部'
    if '国星' in name: return '国星'
    if ('瑞晨' in name and '浩正' in name) or '瑞浩' in name: return '瑞晨'
    if '浩正' in name: return '浩正'
    if '瑞晨' in name: return '瑞晨'
    if '嘉丽' in name: return '嘉丽'
    if '小敏' in name: return '小敏'
    if '魏怡' in name: return '魏怡'
    if '雅迪' in name: return '雅迪'
    if '婷玉' in name: return '婷玉'
    if '子矜' in name or '子衿' in name: return '子衿'
    return None

def pn(s):
    try: return float(str(s).replace(',', '')) if s and str(s).strip() not in ('', '--', '-') else 0.0
    except: return 0.0

# ── 读取投放数据
invest_rows = read_csv(CSV_INVEST)

invest_items = []
for r in invest_rows:
    ed = extract_editor(r['视频名称'])
    if not ed: continue
    spend    = pn(r['消耗'])
    imp      = int(pn(r['展示数']))
    click    = int(pn(r['点击数']))
    ctr_raw  = pn(r['点击率(%)'])
    cpm      = pn(r['平均千次展现费用(元)'])
    cpc      = pn(r['平均点击单价(元)'])
    conv     = int(pn(r['转化数']))
    cpa_val  = pn(r['转化成本'])
    huifang  = int(pn(r.get('回访-高潜成交(计费时间)', '0')))
    url      = r.get('视频链接', '').strip()
    grade    = r.get('素材评估', '').strip()
    invest_items.append({
        'editor': ed, 'name': r['视频名称'].strip(), 'url': url,
        'spend': spend, 'imp': imp, 'click': click, 'ctr': ctr_raw,
        'cpm': cpm, 'cpc': cpc, 'conv': conv, 'cpa': cpa_val,
        'huifang': huifang, 'grade': grade,
    })

# ── 读取过审数据
review_rows = read_csv(CSV_REVIEW)

review_items = []
for r in review_rows:
    ed = extract_editor(r['视频名称'])
    if not ed: continue
    review_items.append({
        'editor': ed, 'name': r['视频名称'].strip(),
        'result': r.get('审核建议', '').strip(),
        'url': r.get('视频链接', '').strip(),
    })

# ── 按编导聚合投放
by_ed_invest = defaultdict(list)
for it in invest_items:
    by_ed_invest[it['editor']].append(it)

ed_invest_stats = {}
for ed, items in by_ed_invest.items():
    has_cost = [x for x in items if x['spend'] > 0]
    cost = sum(x['spend'] for x in items)
    huifang = sum(x['huifang'] for x in items)
    conv = sum(x['conv'] for x in items)
    cpa = cost / conv if conv else 0
    ctrs = [x['ctr'] for x in has_cost if x['ctr'] > 0]
    avg_ctr = sum(ctrs) / len(ctrs) if ctrs else 0
    top_spend = sorted(items, key=lambda x: -x['spend'])[:10]
    ed_invest_stats[ed] = {
        'total': len(items), 'has_cost': len(has_cost),
        'spend': cost, 'huifang': huifang, 'conv': conv, 'cpa': cpa,
        'avg_ctr': avg_ctr, 'top10': top_spend,
    }


# ── 按编导聚合过审
by_ed_review = defaultdict(list)
for it in review_items:
    by_ed_review[it['editor']].append(it)

ed_review_stats = {}
for ed, items in by_ed_review.items():
    passed = sum(1 for x in items if x['result'] == '审核通过')
    failed = sum(1 for x in items if x['result'] == '审核不通过')
    ed_review_stats[ed] = {
        'total': len(items), 'passed': passed, 'failed': failed,
        'rate': passed / len(items) * 100 if items else 0,
        'items': items,
    }

# ── 全局 KPI
all_eds_invest = sorted(ed_invest_stats, key=lambda e: -ed_invest_stats[e]['spend'])
total_spend    = sum(s['spend']   for s in ed_invest_stats.values())
total_huifang  = sum(s['huifang'] for s in ed_invest_stats.values())
total_conv     = sum(s['conv']    for s in ed_invest_stats.values())
total_cpa      = total_spend / total_conv if total_conv else 0
total_has_cost = sum(s['has_cost'] for s in ed_invest_stats.values())

all_eds_review   = sorted(ed_review_stats, key=lambda e: -ed_review_stats[e]['total'])
total_review     = sum(s['total']  for s in ed_review_stats.values())
total_passed     = sum(s['passed'] for s in ed_review_stats.values())
total_failed     = sum(s['failed'] for s in ed_review_stats.values())
global_pass_rate = total_passed / total_review * 100 if total_review else 0

# ── JSON for JS
invest_json   = json.dumps(invest_items,  ensure_ascii=False)
review_json   = json.dumps(review_items,  ensure_ascii=False)
ed_invest_js  = json.dumps({ed: {'spend': round(s['spend'],2), 'huifang': s['huifang'],
    'conv': s['conv'], 'cpa': round(s['cpa'],2),
    'avg_ctr': round(s['avg_ctr'],2), 'has_cost': s['has_cost'], 'total': s['total']}
    for ed, s in ed_invest_stats.items()}, ensure_ascii=False)
ed_review_js  = json.dumps({ed: {'passed': s['passed'], 'failed': s['failed'], 'total': s['total']}
    for ed, s in ed_review_stats.items()}, ensure_ascii=False)

def fmt_spend(v):
    if v >= 10000: return f'{v/10000:.1f}万'
    return f'{v:,.0f}'

html = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>引导素材分析 · {DATE_LABEL}</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<style>
:root{{--bg:#F0F4FA;--s1:#FFFFFF;--s2:#F5F7FB;--s3:#E8ECF4;
  --border:rgba(0,0,0,0.07);--border2:rgba(0,0,0,0.11);
  --amber:#D97706;--blue:#2563EB;--sky:#0EA5E9;--teal:#0D9488;
  --rose:#DC2626;--green:#16A34A;--purple:#7C3AED;
  --ink:#1E2A3B;--ink2:#374151;--muted:#6B7A99;
  --font:'DM Sans',system-ui,sans-serif;--mono:'DM Mono',monospace;
  --r-sm:6px;--r-md:10px;--r-lg:14px}}
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:var(--font);background:var(--bg);color:var(--ink);min-height:100vh}}
.wrap{{max-width:1280px;margin:0 auto;padding:32px 20px 80px}}
.page-head{{display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:12px;
  padding:18px 22px;background:var(--s1);border:1px solid var(--border);border-radius:var(--r-lg);
  margin-bottom:20px;box-shadow:0 1px 4px rgba(0,0,0,0.05)}}
.head-icon{{width:42px;height:42px;border-radius:10px;background:linear-gradient(135deg,var(--sky),var(--blue));
  display:flex;align-items:center;justify-content:center;color:#fff;font-weight:700;font-size:15px;flex-shrink:0}}
.head-title{{font-size:19px;font-weight:700;letter-spacing:-.3px}}
.head-sub{{font-size:11px;color:var(--muted);letter-spacing:1px;text-transform:uppercase;margin-top:2px}}
.head-badge{{font-family:var(--mono);font-size:11px;color:var(--muted);background:var(--s2);
  border:1px solid var(--border2);padding:4px 12px;border-radius:4px;white-space:nowrap}}
.tab-nav{{display:flex;gap:4px;background:var(--s1);border:1px solid var(--border);border-radius:var(--r-lg);
  padding:4px;margin-bottom:20px}}
.tab-btn{{flex:1;padding:9px 0;border:none;background:none;border-radius:var(--r-md);font-size:13px;
  font-weight:600;color:var(--muted);cursor:pointer;transition:all .2s}}
.tab-btn.active{{background:var(--blue);color:#fff;box-shadow:0 2px 8px rgba(37,99,235,0.25)}}
.tab-btn.tab-review.active{{background:var(--teal)}}
.tab-pane{{display:none}}.tab-pane.active{{display:block}}
.kpi-row{{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:20px}}
.kpi-card{{background:var(--s1);border:1px solid var(--border);border-radius:var(--r-lg);padding:18px 20px}}
.kpi-label{{font-size:11px;letter-spacing:1px;text-transform:uppercase;color:var(--muted);margin-bottom:8px}}
.kpi-val{{font-size:26px;font-weight:700;line-height:1;font-family:var(--mono)}}
.kpi-sub{{font-size:11px;color:var(--muted);margin-top:4px}}
.chart-grid{{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:20px}}
.chart-box{{background:var(--s1);border:1px solid var(--border);border-radius:var(--r-lg);padding:18px 20px}}
.chart-title{{font-size:11px;letter-spacing:1.5px;text-transform:uppercase;color:var(--muted);margin-bottom:14px}}
.chart-canvas{{position:relative;height:220px}}
.ed-grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(270px,1fr));gap:12px;margin-bottom:20px}}
.ed-card{{background:var(--s1);border:1px solid var(--border);border-radius:var(--r-lg);padding:18px 20px}}
.ed-name{{font-size:15px;font-weight:700;margin-bottom:12px}}
.ed-metrics{{display:grid;grid-template-columns:1fr 1fr;gap:8px}}
.ed-metric{{background:var(--s2);border-radius:var(--r-sm);padding:10px 12px}}
.ed-metric-label{{font-size:10px;color:var(--muted);margin-bottom:3px}}
.ed-metric-val{{font-family:var(--mono);font-size:14px;font-weight:600}}
.sec-label{{font-size:11px;letter-spacing:1.5px;text-transform:uppercase;color:var(--muted);margin-bottom:10px}}
.filter-wrap{{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:12px;align-items:center}}
.filter-label{{font-size:10px;color:var(--muted);letter-spacing:1px;text-transform:uppercase}}
.pf-btn{{background:var(--s1);border:1px solid var(--border2);color:var(--muted);
  padding:5px 12px;border-radius:var(--r-sm);font-size:12px;cursor:pointer;transition:all .15s}}
.pf-btn:hover{{border-color:var(--blue);color:var(--ink)}}
.pf-btn.active{{background:var(--blue);border-color:var(--blue);color:#fff;font-weight:600}}
.tbl-wrap{{background:var(--s1);border:1px solid var(--border);border-radius:var(--r-lg);
  overflow:hidden;box-shadow:0 1px 3px rgba(0,0,0,0.04);margin-bottom:24px}}
.tbl-scroll{{overflow-x:auto}}
table{{width:100%;border-collapse:collapse}}
th{{font-family:var(--mono);font-size:10px;letter-spacing:1px;text-transform:uppercase;color:var(--muted);
  padding:10px 12px;border-bottom:1px solid var(--border);background:var(--s2);white-space:nowrap;text-align:left}}
th.r{{text-align:right}}th.sortable{{cursor:pointer}}th.sortable:hover{{color:var(--ink)}}
th.asc::after{{content:' ↑';color:var(--amber)}}th.desc::after{{content:' ↓';color:var(--amber)}}
td{{padding:9px 12px;border-bottom:1px solid var(--border);font-size:12px;vertical-align:middle}}
td.r{{text-align:right;font-family:var(--mono);font-size:12px}}
tr:last-child td{{border-bottom:none}}tr:hover td{{background:rgba(37,99,235,0.03)}}
.mat-name{{max-width:200px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}}
.pill{{display:inline-block;padding:2px 8px;border-radius:4px;font-size:11px}}
.rv-pass{{background:rgba(22,163,74,0.1);color:var(--green)}}
.rv-fail{{background:rgba(220,38,38,0.1);color:var(--rose)}}
.mat-link{{color:var(--blue);font-size:11px;text-decoration:none}}
.mat-link:hover{{text-decoration:underline}}
.rv-card{{background:var(--s1);border:1px solid var(--border);border-radius:var(--r-lg);padding:18px 20px}}
.rv-name{{font-size:14px;font-weight:700;margin-bottom:4px}}
.rv-counts{{font-size:12px;color:var(--muted);margin-bottom:10px}}
.rate-bar-bg{{background:var(--s3);border-radius:4px;height:7px;overflow:hidden;margin-bottom:5px}}
.rate-bar-fill{{height:7px;border-radius:4px}}
.rate-val{{font-family:var(--mono);font-size:14px;font-weight:700}}
.rv-grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(240px,1fr));gap:12px;margin-bottom:20px}}
@media(max-width:800px){{.kpi-row{{grid-template-columns:1fr 1fr}}.chart-grid{{grid-template-columns:1fr}}}}
</style>
</head>
<body>
<div class="wrap">

<div class="page-head">
  <div style="display:flex;align-items:center;gap:14px">
    <div class="head-icon">引</div>
    <div>
      <div class="head-title">引导素材投放分析</div>
      <div class="head-sub">GUIDE MATERIAL · PERFORMANCE REPORT · 2026-07-{DATE_LABEL[2:]}</div>
    </div>
  </div>
  <div class="head-badge">数据截至 2026/07/{DATE_LABEL[2:]}</div>
</div>

<div class="tab-nav">
  <button class="tab-btn active" onclick="switchTab('invest')">投放表现</button>
  <button class="tab-btn tab-review" onclick="switchTab('review')">过审情况</button>
</div>

<!-- ═══ TAB: 投放表现 ═══ -->
<div class="tab-pane active" id="tab-invest">

<div class="kpi-row">
  <div class="kpi-card">
    <div class="kpi-label">总消耗</div>
    <div class="kpi-val" style="color:var(--amber)">¥{fmt_spend(total_spend)}</div>
    <div class="kpi-sub">元</div>
  </div>
  <div class="kpi-card">
    <div class="kpi-label">高潜成交回访</div>
    <div class="kpi-val" style="color:var(--blue)">{total_huifang}</div>
    <div class="kpi-sub">次</div>
  </div>
  <div class="kpi-card">
    <div class="kpi-label">CPA</div>
    <div class="kpi-val" style="color:var(--teal)">¥{total_cpa:.1f}</div>
    <div class="kpi-sub">元 / 转化</div>
  </div>
  <div class="kpi-card">
    <div class="kpi-label">总转化数</div>
    <div class="kpi-val" style="color:var(--purple)">{total_conv}</div>
    <div class="kpi-sub">次</div>
  </div>
</div>

<div class="chart-grid">
  <div class="chart-box"><div class="chart-title">消耗对比（元）</div><div class="chart-canvas"><canvas id="spendChart"></canvas></div></div>
  <div class="chart-box"><div class="chart-title">高潜成交回访次数</div><div class="chart-canvas"><canvas id="huifangChart"></canvas></div></div>
</div>
<div class="chart-grid">
  <div class="chart-box"><div class="chart-title">CPA（元/转化）</div><div class="chart-canvas"><canvas id="cpaChart"></canvas></div></div>
  <div class="chart-box"><div class="chart-title">转化数</div><div class="chart-canvas"><canvas id="convChart"></canvas></div></div>
</div>

<div class="sec-label">按编导</div>
<div class="ed-grid" id="edCardRow"></div>

<div class="sec-label">素材明细</div>
<div class="filter-wrap">
  <span class="filter-label">编导</span>
  <div id="filterRow">
    <button class="pf-btn active" onclick="filterInvest(this,'all')">全部</button>
  </div>
</div>
<div class="tbl-wrap"><div class="tbl-scroll">
<table>
  <thead><tr>
    <th>编导</th>
    <th>素材名称</th>
    <th class="r sortable" data-key="spend" onclick="sortInvest('spend')">消耗</th>
    <th class="r sortable" data-key="ctr" onclick="sortInvest('ctr')">CTR %</th>
    <th class="r sortable" data-key="huifang" onclick="sortInvest('huifang')">高潜回访</th>
    <th class="r sortable" data-key="imp" onclick="sortInvest('imp')">展示数</th>
    <th class="r sortable" data-key="click" onclick="sortInvest('click')">点击数</th>
    <th class="r sortable" data-key="cpm" onclick="sortInvest('cpm')">CPM</th>
    <th class="r sortable" data-key="conv" onclick="sortInvest('conv')">转化数</th>
    <th>素材评估</th>
    <th>预览</th>
  </tr></thead>
  <tbody id="investTbody"></tbody>
</table>
</div></div>

</div><!-- /tab-invest -->

<!-- ═══ TAB: 过审情况 ═══ -->
<div class="tab-pane" id="tab-review">

<div class="kpi-row">
  <div class="kpi-card">
    <div class="kpi-label">提交总数</div>
    <div class="kpi-val" style="color:var(--blue)">{total_review}</div>
    <div class="kpi-sub">条</div>
  </div>
  <div class="kpi-card">
    <div class="kpi-label">审核通过</div>
    <div class="kpi-val" style="color:var(--green)">{total_passed}</div>
    <div class="kpi-sub">条</div>
  </div>
  <div class="kpi-card">
    <div class="kpi-label">审核不通过</div>
    <div class="kpi-val" style="color:var(--rose)">{total_failed}</div>
    <div class="kpi-sub">条</div>
  </div>
  <div class="kpi-card">
    <div class="kpi-label">整体过审率</div>
    <div class="kpi-val" style="color:var(--teal)">{global_pass_rate:.0f}%</div>
    <div class="kpi-sub">通过 / 总提交</div>
  </div>
</div>

<div class="chart-grid" style="grid-template-columns:1fr">
  <div class="chart-box"><div class="chart-title">各编导过审情况（通过 / 不通过）</div><div class="chart-canvas" style="height:240px"><canvas id="reviewChart"></canvas></div></div>
</div>

<div class="sec-label">各编导过审率</div>
<div class="rv-grid" id="rvCardRow"></div>

<div class="sec-label">素材明细</div>
<div class="filter-wrap">
  <span class="filter-label">编导</span>
  <div id="rvFilterRow">
    <button class="pf-btn active" onclick="filterReview(this,'all')">全部</button>
  </div>
  <span class="filter-label" style="margin-left:8px">结果</span>
  <div id="rvResultRow">
    <button class="pf-btn active" onclick="filterReviewResult(this,'all')">全部</button>
    <button class="pf-btn" onclick="filterReviewResult(this,'审核通过')">通过</button>
    <button class="pf-btn" onclick="filterReviewResult(this,'审核不通过')">不通过</button>
  </div>
</div>
<div class="tbl-wrap"><div class="tbl-scroll">
<table>
  <thead><tr>
    <th>编导</th>
    <th>素材名称</th>
    <th>审核结果</th>
    <th>预览</th>
  </tr></thead>
  <tbody id="reviewTbody"></tbody>
</table>
</div></div>

</div><!-- /tab-review -->

<div style="text-align:center;font-size:11px;color:var(--muted);margin-top:32px;padding-top:20px;border-top:1px solid var(--border)">
  Generated {datetime.now().strftime('%Y-%m-%d %H:%M')} · 引导素材投放分析报告 {DATE_LABEL}
</div>
</div><!-- /wrap -->

<script>
const INVEST = {invest_json};
const REVIEW = {review_json};
const ED_INVEST = {ed_invest_js};
const ED_REVIEW = {ed_review_js};
const COLORS = ['#D97706','#2563EB','#0D9488','#7C3AED','#EA580C','#0EA5E9','#16A34A','#DC2626'];

const investEditors = Object.keys(ED_INVEST).sort((a,b) => ED_INVEST[b].spend - ED_INVEST[a].spend);
const reviewEditors = Object.keys(ED_REVIEW).sort((a,b) => ED_REVIEW[b].total - ED_REVIEW[a].total);
const colorMap = {{}};
investEditors.forEach((e,i) => colorMap[e] = COLORS[i % COLORS.length]);
reviewEditors.forEach((e,i) => {{ if (!colorMap[e]) colorMap[e] = COLORS[i % COLORS.length]; }});

// ── Charts
const barOpts = (label, data, labels, fmt) => ({{
  type: 'bar',
  data: {{ labels, datasets: [{{ label, data, backgroundColor: labels.map(e => (colorMap[e]||'#ccc') + 'CC'), borderRadius: 5, borderSkipped: false }}] }},
  options: {{ responsive: true, maintainAspectRatio: false,
    plugins: {{ legend: {{ display: false }}, tooltip: {{ callbacks: {{ label: c => fmt ? fmt(c.raw) : c.raw }} }} }},
    scales: {{ x: {{ grid: {{ display: false }}, ticks: {{ font: {{ size: 11 }} }} }},
               y: {{ grid: {{ color: 'rgba(0,0,0,0.04)' }}, ticks: {{ font: {{ size: 11 }} }} }} }} }}
}});

window.addEventListener('load', () => {{
  new Chart(document.getElementById('spendChart'),
    barOpts('消耗', investEditors.map(e => +(ED_INVEST[e].spend.toFixed(0))), investEditors, v => '¥' + v.toLocaleString()));
  new Chart(document.getElementById('huifangChart'),
    barOpts('高潜回访', investEditors.map(e => ED_INVEST[e].huifang), investEditors));
  new Chart(document.getElementById('cpaChart'),
    barOpts('CPA', investEditors.map(e => +(ED_INVEST[e].cpa.toFixed(2))), investEditors, v => v > 0 ? '¥' + v : '—'));
  new Chart(document.getElementById('convChart'),
    barOpts('转化数', investEditors.map(e => ED_INVEST[e].conv), investEditors));

  // Review stacked bar
  new Chart(document.getElementById('reviewChart'), {{
    type: 'bar',
    data: {{ labels: reviewEditors, datasets: [
      {{ label: '通过', data: reviewEditors.map(e => ED_REVIEW[e].passed), backgroundColor: 'rgba(22,163,74,0.75)', borderRadius: 0 }},
      {{ label: '不通过', data: reviewEditors.map(e => ED_REVIEW[e].failed), backgroundColor: 'rgba(220,38,38,0.65)', borderRadius: 5 }}
    ]}},
    options: {{ responsive: true, maintainAspectRatio: false,
      plugins: {{ legend: {{ display: true, position: 'bottom', labels: {{ font: {{ size: 10 }}, boxWidth: 10, padding: 8 }} }},
                  tooltip: {{ callbacks: {{ label: c => c.dataset.label + ': ' + c.raw }} }} }},
      scales: {{ x: {{ stacked: true, grid: {{ display: false }}, ticks: {{ font: {{ size: 11 }} }} }},
                 y: {{ stacked: true, grid: {{ color: 'rgba(0,0,0,0.04)' }}, ticks: {{ font: {{ size: 11 }} }} }} }} }}
  }});

  // Editor invest cards
  const edCardRow = document.getElementById('edCardRow');
  investEditors.forEach(ed => {{
    const s = ED_INVEST[ed];
    const c = colorMap[ed];
    edCardRow.innerHTML += `<div class="ed-card">
      <div class="ed-name" style="color:${{c}}">${{ed}}</div>
      <div class="ed-metrics">
        <div class="ed-metric"><div class="ed-metric-label">总消耗</div><div class="ed-metric-val" style="color:var(--amber)">¥${{s.spend >= 10000 ? (s.spend/10000).toFixed(1)+'万' : s.spend.toFixed(0)}}</div></div>
        <div class="ed-metric"><div class="ed-metric-label">高潜回访</div><div class="ed-metric-val" style="color:var(--blue)">${{s.huifang}}</div></div>
        <div class="ed-metric"><div class="ed-metric-label">CPA</div><div class="ed-metric-val" style="color:var(--teal)">${{s.cpa > 0 ? '¥'+s.cpa.toFixed(1) : '—'}}</div></div>
        <div class="ed-metric"><div class="ed-metric-label">转化数</div><div class="ed-metric-val" style="color:var(--purple)">${{s.conv}}</div></div>
      </div>
    </div>`;
  }});

  // Review cards
  const rvCardRow = document.getElementById('rvCardRow');
  reviewEditors.forEach(ed => {{
    const s = ED_REVIEW[ed];
    const rate = s.total ? (s.passed / s.total * 100).toFixed(0) : 0;
    const c = colorMap[ed] || '#6B7A99';
    const barColor = +rate >= 60 ? 'var(--green)' : +rate >= 30 ? 'var(--amber)' : 'var(--rose)';
    rvCardRow.innerHTML += `<div class="rv-card">
      <div class="rv-name" style="color:${{c}}">${{ed}}</div>
      <div class="rv-counts">通过 ${{s.passed}} · 不通过 ${{s.failed}} · 共 ${{s.total}} 条</div>
      <div class="rate-bar-bg"><div class="rate-bar-fill" style="width:${{rate}}%;background:${{barColor}}"></div></div>
      <div class="rate-val" style="color:${{barColor}}">${{rate}}%</div>
    </div>`;
  }});

  // Filter buttons
  const filterRow = document.getElementById('filterRow');
  investEditors.forEach(ed => {{
    const btn = document.createElement('button');
    btn.className = 'pf-btn'; btn.textContent = ed;
    btn.onclick = () => filterInvest(btn, ed);
    filterRow.appendChild(btn);
  }});
  const rvFilterRow = document.getElementById('rvFilterRow');
  reviewEditors.forEach(ed => {{
    const btn = document.createElement('button');
    btn.className = 'pf-btn'; btn.textContent = ed;
    btn.onclick = () => filterReview(btn, ed);
    rvFilterRow.appendChild(btn);
  }});

  renderInvest(); renderReview();
}});

// ── Invest table
let investFilter = 'all', investSort = 'spend', investDir = 'desc';
function renderInvest() {{
  const tbody = document.getElementById('investTbody');
  let rows = INVEST.filter(r => investFilter === 'all' || r.editor === investFilter);
  rows.sort((a,b) => investDir === 'asc' ? a[investSort] - b[investSort] : b[investSort] - a[investSort]);
  const gradeColor = {{'首发': 'var(--amber)', '优质': 'var(--blue)'}};
  tbody.innerHTML = rows.map(r => {{
    const c = colorMap[r.editor] || '#ccc';
    const lk = r.url ? `<a class="mat-link" href="${{r.url}}" target="_blank">▶ 预览</a>` : '—';
    const grade = r.grade && r.grade !== '--' ? `<span class="pill" style="background:${{(gradeColor[r.grade]||'#999')}}22;color:${{gradeColor[r.grade]||'var(--muted)'}}">${{r.grade}}</span>` : '—';
    return `<tr>
      <td><span class="pill" style="background:${{c}}22;color:${{c}}">${{r.editor}}</span></td>
      <td><div class="mat-name" title="${{r.name}}">${{r.name}}</div></td>
      <td class="r">${{r.spend > 0 ? '¥' + r.spend.toLocaleString(undefined,{{maximumFractionDigits:0}}) : '—'}}</td>
      <td class="r">${{r.ctr > 0 ? r.ctr.toFixed(2) + '%' : '—'}}</td>
      <td class="r" style="color:${{r.huifang > 0 ? 'var(--blue)' : 'inherit'}};font-weight:${{r.huifang > 0 ? '600' : '400'}}">${{r.huifang > 0 ? r.huifang : '—'}}</td>
      <td class="r">${{r.imp > 0 ? r.imp.toLocaleString() : '—'}}</td>
      <td class="r">${{r.click > 0 ? r.click.toLocaleString() : '—'}}</td>
      <td class="r">${{r.cpm > 0 ? r.cpm.toFixed(2) : '—'}}</td>
      <td class="r">${{r.conv > 0 ? r.conv : '—'}}</td>
      <td>${{grade}}</td>
      <td>${{lk}}</td>
    </tr>`;
  }}).join('');
}}
function filterInvest(btn, val) {{
  document.querySelectorAll('#filterRow .pf-btn').forEach(b => b.classList.remove('active'));
  btn.classList.add('active'); investFilter = val; renderInvest();
}}
function sortInvest(key) {{
  if (investSort === key) investDir = investDir === 'desc' ? 'asc' : 'desc';
  else {{ investSort = key; investDir = 'desc'; }}
  document.querySelectorAll('#tab-invest th.sortable').forEach(th => {{
    th.classList.remove('asc','desc');
    if (th.dataset.key === key) th.classList.add(investDir);
  }});
  renderInvest();
}}

// ── Review table
let rvFilter = 'all', rvResultFilter = 'all';
function renderReview() {{
  const tbody = document.getElementById('reviewTbody');
  let rows = REVIEW.filter(r =>
    (rvFilter === 'all' || r.editor === rvFilter) &&
    (rvResultFilter === 'all' || r.result === rvResultFilter)
  );
  tbody.innerHTML = rows.map(r => {{
    const c = colorMap[r.editor] || '#ccc';
    const resultClass = r.result === '审核通过' ? 'rv-pass' : r.result === '审核不通过' ? 'rv-fail' : '';
    const lk = r.url ? `<a class="mat-link" href="${{r.url}}" target="_blank">▶ 预览</a>` : '—';
    return `<tr>
      <td><span class="pill" style="background:${{c}}22;color:${{c}}">${{r.editor}}</span></td>
      <td><div class="mat-name" title="${{r.name}}">${{r.name}}</div></td>
      <td><span class="pill ${{resultClass}}">${{r.result || '—'}}</span></td>
      <td>${{lk}}</td>
    </tr>`;
  }}).join('');
}}
function filterReview(btn, val) {{
  document.querySelectorAll('#rvFilterRow .pf-btn').forEach(b => b.classList.remove('active'));
  btn.classList.add('active'); rvFilter = val; renderReview();
}}
function filterReviewResult(btn, val) {{
  document.querySelectorAll('#rvResultRow .pf-btn').forEach(b => b.classList.remove('active'));
  btn.classList.add('active'); rvResultFilter = val; renderReview();
}}

function switchTab(t) {{
  document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
  document.querySelectorAll('.tab-pane').forEach(p => p.classList.remove('active'));
  document.querySelector('.tab-btn.tab-' + t) || document.querySelectorAll('.tab-btn')[t === 'invest' ? 0 : 1];
  if (t === 'invest') {{
    document.querySelectorAll('.tab-btn')[0].classList.add('active');
    document.getElementById('tab-invest').classList.add('active');
  }} else {{
    document.querySelectorAll('.tab-btn')[1].classList.add('active');
    document.getElementById('tab-review').classList.add('active');
  }}
}}
</script>
</body>
</html>'''

with open(OUT_PATH, 'w', encoding='utf-8') as f:
    f.write(html)
print(f'✓ 报告已生成: {OUT_PATH}')
print(f'  投放数据: {len(invest_items)} 条 | 总消耗 ¥{total_spend:,.0f} | 高潜回访 {total_huifang}')
print(f'  过审数据: {total_review} 条 | 通过 {total_passed} | 过审率 {global_pass_rate:.0f}%')
