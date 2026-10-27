#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import csv, json, sys, re
from collections import defaultdict
from datetime import datetime

DATE_LABEL  = sys.argv[1] if len(sys.argv) > 1 else '0807'
CSV_INVEST  = sys.argv[2] if len(sys.argv) > 2 else f'data/【周报】引导素材投放-{DATE_LABEL}.csv'
OUT_PATH    = sys.argv[3] if len(sys.argv) > 3 else f'reports/引导素材分析报告_{DATE_LABEL}.html'
CSV_AUDIT   = f'data/【周报】引导素材过审-{DATE_LABEL}.csv'

def read_csv(path):
    with open(path, encoding='utf-8-sig') as f:
        return list(csv.DictReader(f))

def extract_editor(name):
    name = name.strip()
    # hash/UUID 文件名 → 外部
    if re.match(r'^[0-9a-f]{32}', name.lower()): return '外部'
    if re.match(r'^[0-9A-F]{8}-[0-9A-F]{4}', name): return '外部'
    if '微信视频' in name: return '外部'
    # 编导优先：只要名称里含编导名，不管有没有剪辑名
    if '婷玉' in name: return '婷玉'
    if '嘉丽' in name: return '嘉丽'
    if '雅迪' in name: return '雅迪'
    if '小敏' in name: return '小敏'
    if '浩正' in name or '杜' in name: return '浩正'
    if '子衿' in name or '子矜' in name: return '子衿'
    # 无编导名 → 剪辑归属
    if '瑞晨' in name or '瑞浩' in name: return '瑞晨'
    if '魏怡' in name: return '魏怡'
    if '国星' in name: return '国星'
    return None

def pn(s):
    try: return float(str(s).replace(',', '')) if s and str(s).strip() not in ('', '--', '-') else 0.0
    except: return 0.0

# ── 读取投放数据
invest_rows = read_csv(CSV_INVEST)

invest_items = []
for r in invest_rows:
    raw_name = r['视频名称'].strip()
    # 科学计数法 → 用素材id替代
    if 'E+' in raw_name or 'e+' in raw_name:
        mat_id = r.get('素材id', '').strip().lstrip()
        display_name = mat_id if mat_id else raw_name
    else:
        display_name = raw_name
    ed = extract_editor(raw_name) or '—'
    url = r.get('视频链接', '').strip()
    # 素材类型：主页优先（名称全数字/科学计数法），再用 CSV 的素材类型列
    _is_numeric = bool(re.match(r'^[\d.]+[Ee][+\-]?\d+$', raw_name)) or raw_name.replace('.','').isdigit()
    if _is_numeric:
        mat_type = '主页'
    else:
        mat_type = r.get('素材类型', '').strip() or ('图文' if (not url or url == '--') else '视频')
    # 账户id：科学计数法转全数字字符串
    raw_acct = r.get('账户id', '').strip()
    try:
        acct_display = str(int(float(raw_acct))) if raw_acct else ''
    except:
        acct_display = raw_acct
    spend    = pn(r['消耗'])
    imp      = int(pn(r['展示数']))
    click    = int(pn(r['点击数']))
    ctr_raw  = pn(r['点击率(%)'])
    cpm      = pn(r['平均千次展现费用(元)'])
    cpc      = pn(r['平均点击单价(元)'])
    conv     = int(pn(r['转化数']))
    cpa_val  = pn(r['转化成本'])
    huifang  = int(pn(r.get('回访-高潜成交(计费时间)', '0')))
    grade    = r.get('素材评估', '').strip()
    invest_items.append({
        'editor': ed, 'name': display_name, 'url': url,
        'acct':   acct_display,
        'mat_type': mat_type,
        'spend': spend, 'imp': imp, 'click': click, 'ctr': ctr_raw,
        'cpm': cpm, 'cpc': cpc, 'conv': conv, 'cpa': cpa_val,
        'huifang': huifang, 'grade': grade,
    })

# ── 读取过审数据
import os as _os
audit_stats = defaultdict(lambda: {'pass': 0, 'fail': 0})
if _os.path.exists(CSV_AUDIT):
    for r in read_csv(CSV_AUDIT):
        result = r.get('审核建议', '').strip()
        if result in ('--', '', '生态风险判定不通过'):
            continue
        name = r.get('视频名称', '').strip()
        ed = extract_editor(name) or '外部'
        if '通过' in result and '不通过' not in result:
            audit_stats[ed]['pass'] += 1
        else:
            audit_stats[ed]['fail'] += 1

total_audit_pass  = sum(v['pass'] for v in audit_stats.values())
total_audit_total = sum(v['pass'] + v['fail'] for v in audit_stats.values())
total_audit_rate  = total_audit_pass / total_audit_total * 100 if total_audit_total else 0

# ── 按编导聚合（仅统计有编导的行，主页单独一组）
by_ed_invest = defaultdict(list)
for it in invest_items:
    if it['editor'] != '—':
        by_ed_invest[it['editor']].append(it)
    elif it['mat_type'] == '主页':
        by_ed_invest['主页'].append(it)

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
        'hf_rate': huifang / conv * 100 if conv else 0,
        'audit_pass':  audit_stats[ed]['pass'],
        'audit_total': audit_stats[ed]['pass'] + audit_stats[ed]['fail'],
        'audit_rate':  audit_stats[ed]['pass'] / (audit_stats[ed]['pass'] + audit_stats[ed]['fail']) * 100
                       if (audit_stats[ed]['pass'] + audit_stats[ed]['fail']) > 0 else None,
    }

# ── 全局 KPI
all_eds_invest = sorted(ed_invest_stats, key=lambda e: -ed_invest_stats[e]['spend'])
total_spend    = sum(s['spend']   for s in ed_invest_stats.values())
total_huifang  = sum(s['huifang'] for s in ed_invest_stats.values())
total_conv     = sum(s['conv']    for s in ed_invest_stats.values())
total_cpa      = total_spend / total_conv if total_conv else 0
total_hf_rate  = total_huifang / total_conv * 100 if total_conv else 0
total_has_cost = sum(s['has_cost'] for s in ed_invest_stats.values())

all_eds_review   = []
total_review     = 0
total_passed     = 0
total_failed     = 0
global_pass_rate = 0

all_accts = sorted(set(it['acct'] for it in invest_items if it['acct']))
all_accts_js = json.dumps(all_accts, ensure_ascii=False)
invest_json   = json.dumps(invest_items,  ensure_ascii=False)
review_json   = json.dumps([],  ensure_ascii=False)
ed_invest_js  = json.dumps({ed: {'spend': round(s['spend'],2), 'huifang': s['huifang'],
    'conv': s['conv'], 'cpa': round(s['cpa'],2),
    'avg_ctr': round(s['avg_ctr'],2), 'has_cost': s['has_cost'], 'total': s['total'],
    'hf_rate': round(s['hf_rate'],1),
    'audit_pass': s['audit_pass'], 'audit_total': s['audit_total'],
    'audit_rate': round(s['audit_rate'],1) if s['audit_rate'] is not None else None}
    for ed, s in ed_invest_stats.items()}, ensure_ascii=False)
ed_review_js  = json.dumps({}, ensure_ascii=False)

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
.tab-pane{{display:none}}.tab-pane.active{{display:block}}
.kpi-row{{display:grid;grid-template-columns:repeat(5,1fr);gap:12px;margin-bottom:20px}}
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
@media(max-width:800px){{.kpi-row{{grid-template-columns:repeat(3,1fr)}}.chart-grid{{grid-template-columns:1fr}}}}
</style>
</head>
<body>
<div class="wrap">

<div class="page-head">
  <div style="display:flex;align-items:center;gap:14px">
    <div class="head-icon">引</div>
    <div>
      <div class="head-title">引导素材投放分析</div>
      <div class="head-sub">GUIDE MATERIAL · PERFORMANCE REPORT · 2026-{DATE_LABEL[:2]}-{DATE_LABEL[2:]}</div>
    </div>
  </div>
  <div class="head-badge">数据截至 2026/{DATE_LABEL[:2]}/{DATE_LABEL[2:]}</div>
</div>

<!-- 投放表现 -->
<div id="tab-invest">

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
  <div class="kpi-card">
    <div class="kpi-label">高潜转化率</div>
    <div class="kpi-val" style="color:var(--rose)">{total_hf_rate:.1f}%</div>
    <div class="kpi-sub">高潜回访 / 转化数</div>
  </div>
  <div class="kpi-card">
    <div class="kpi-label">视频过审率</div>
    <div class="kpi-val" style="color:var(--green)">{total_audit_rate:.1f}%</div>
    <div class="kpi-sub">{total_audit_pass} / {total_audit_total} 条</div>
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
<div class="filter-wrap" style="margin-top:-8px">
  <span class="filter-label">账户</span>
  <div id="filterAcct">
    <button class="pf-btn active" onclick="filterAcctFn(this,'all')">全部</button>
  </div>
</div>
<div class="filter-wrap" style="margin-top:-8px">
  <span class="filter-label">类型</span>
  <div id="filterType">
    <button class="pf-btn active" onclick="filterTypeFn(this,'all')">全部</button>
    <button class="pf-btn" onclick="filterTypeFn(this,'视频')">视频</button>
    <button class="pf-btn" onclick="filterTypeFn(this,'图文')">图文</button>
    <button class="pf-btn" onclick="filterTypeFn(this,'主页')">主页</button>
  </div>
</div>
<div class="tbl-wrap"><div class="tbl-scroll">
<table>
  <thead><tr>
    <th>类型</th>
    <th>账户</th>
    <th>编导</th>
    <th>素材名称</th>
    <th class="r sortable" data-key="spend" onclick="sortInvest('spend')">消耗</th>
    <th class="r sortable" data-key="ctr" onclick="sortInvest('ctr')">CTR %</th>
    <th class="r sortable" data-key="huifang" onclick="sortInvest('huifang')">高潜回访</th>
    <th class="r">高潜转化率</th>
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

<div style="text-align:center;font-size:11px;color:var(--muted);margin-top:32px;padding-top:20px;border-top:1px solid var(--border)">
  Generated {datetime.now().strftime('%Y-%m-%d %H:%M')} · 引导素材投放分析报告 {DATE_LABEL}
</div>
</div><!-- /wrap -->

<script>
const INVEST = {invest_json};
const ED_INVEST = {ed_invest_js};
const ALL_ACCTS = {all_accts_js};
const COLORS = ['#D97706','#2563EB','#0D9488','#7C3AED','#EA580C','#0EA5E9','#16A34A','#DC2626'];

const investEditors = Object.keys(ED_INVEST).sort((a,b) => ED_INVEST[b].spend - ED_INVEST[a].spend);
const colorMap = {{}};
investEditors.forEach((e,i) => colorMap[e] = COLORS[i % COLORS.length]);

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
        <div class="ed-metric" style="grid-column:1/-1"><div class="ed-metric-label">高潜转化率</div><div class="ed-metric-val" style="color:var(--rose)">${{s.conv > 0 ? s.hf_rate.toFixed(1)+'%' : '—'}}</div></div>
        <div class="ed-metric" style="grid-column:1/-1"><div class="ed-metric-label">视频过审率</div><div class="ed-metric-val" style="color:var(--green)">${{s.audit_rate !== null ? s.audit_rate.toFixed(1)+'% ('+s.audit_pass+'/'+s.audit_total+')' : '—'}}</div></div>      </div>
    </div>`;
  }});

  // Filter buttons — editors
  const filterRow = document.getElementById('filterRow');
  investEditors.forEach(ed => {{
    const btn = document.createElement('button');
    btn.className = 'pf-btn'; btn.textContent = ed;
    btn.onclick = () => filterInvest(btn, ed);
    filterRow.appendChild(btn);
  }});

  // Filter buttons — accounts (dynamic from data)
  const filterAcct = document.getElementById('filterAcct');
  ALL_ACCTS.forEach(acct => {{
    const btn = document.createElement('button');
    btn.className = 'pf-btn'; btn.textContent = acct;
    btn.onclick = () => filterAcctFn(btn, acct);
    filterAcct.appendChild(btn);
  }});

  renderInvest();
}});

// ── Invest table
let investFilter = 'all', acctFilter = 'all', typeFilter = 'all', investSort = 'spend', investDir = 'desc';
function renderInvest() {{
  const tbody = document.getElementById('investTbody');
  let rows = INVEST.filter(r =>
    (investFilter === 'all' || r.editor === investFilter) &&
    (acctFilter === 'all' || r.acct === acctFilter) &&
    (typeFilter === 'all' || r.mat_type === typeFilter)
  );
  rows.sort((a,b) => investDir === 'asc' ? a[investSort] - b[investSort] : b[investSort] - a[investSort]);
  const gradeColor = {{'首发': 'var(--amber)', '优质': 'var(--blue)'}};
  const typeColor  = {{'视频':'var(--blue)','图文':'var(--teal)','主页':'var(--purple)'}};
  tbody.innerHTML = rows.map(r => {{
    const c = colorMap[r.editor] || '#aaa';
    const lk = r.url ? `<a class="mat-link" href="${{r.url}}" target="_blank">▶ 预览</a>` : '—';
    const grade = r.grade && r.grade !== '--' ? `<span class="pill" style="background:${{(gradeColor[r.grade]||'#999')}}22;color:${{gradeColor[r.grade]||'var(--muted)'}}">${{r.grade}}</span>` : '—';
    const acctColor = 'var(--sky)';
    const tc = typeColor[r.mat_type] || 'var(--muted)';
    const edPill = r.editor !== '—' ? `<span class="pill" style="background:${{c}}22;color:${{c}}">${{r.editor}}</span>` : '<span style="color:var(--muted)">—</span>';
    return `<tr>
      <td><span class="pill" style="background:${{tc}}22;color:${{tc}};font-size:11px">${{r.mat_type}}</span></td>
      <td><span class="pill" style="background:${{acctColor}}22;color:${{acctColor}};font-size:11px">${{r.acct||'—'}}</span></td>
      <td>${{edPill}}</td>
      <td><div class="mat-name" title="${{r.name}}">${{r.name}}</div></td>
      <td class="r">${{r.spend > 0 ? '¥' + r.spend.toLocaleString(undefined,{{maximumFractionDigits:0}}) : '—'}}</td>
      <td class="r">${{r.ctr > 0 ? r.ctr.toFixed(2) + '%' : '—'}}</td>
      <td class="r" style="color:${{r.huifang > 0 ? 'var(--blue)' : 'inherit'}};font-weight:${{r.huifang > 0 ? '600' : '400'}}">${{r.huifang > 0 ? r.huifang : '—'}}</td>
      <td class="r">${{r.conv > 0 ? (r.huifang/r.conv*100).toFixed(1)+'%' : '—'}}</td>
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
function filterAcctFn(btn, val) {{
  document.querySelectorAll('#filterAcct .pf-btn').forEach(b => b.classList.remove('active'));
  btn.classList.add('active'); acctFilter = val; renderInvest();
}}
function filterTypeFn(btn, val) {{
  document.querySelectorAll('#filterType .pf-btn').forEach(b => b.classList.remove('active'));
  btn.classList.add('active'); typeFilter = val; renderInvest();
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
</script>
</body>
</html>'''

with open(OUT_PATH, 'w', encoding='utf-8') as f:
    f.write(html)
print(f'✓ 报告已生成: {OUT_PATH}')
print(f'  投放数据: {len(invest_items)} 条 | 总消耗 ¥{total_spend:,.0f} | 高潜回访 {total_huifang}')
