#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
IP老师素材数据分析报告
用法：python3 scripts/generate_ip_report.py MMDD
读取：data/【周报】投后素材看板数据-代理-MMDD.csv（编导侧数据已停更，代理文件已覆盖全部素材）
输出：reports/IP素材分析报告_MMDD.html
"""

import csv, json, sys, os, re
from collections import defaultdict
from datetime import datetime

DATE    = sys.argv[1] if len(sys.argv) > 1 else '0904'
FILE_DL = f'data/【周报】投后素材看板数据-代理-{DATE}.csv'
OUT     = f'reports/IP素材分析报告_{DATE}.html'

IP_NAMES = ['李博', '白琳', '王晶']

AGENT_NORM = {
    '成都发条荔枝文化传媒有限公司': '荔枝',
    '申坤互动（北京）信息技术有限公司': '申坤',
    '十人（北京）传媒广告有限公司': '十人',
    '天津掌视广通信息技术有限公司': '掌视',
    '北京有范儿科技有限公司': '有范',
    '东信': '东信',
}

def norm_agent(a):
    return AGENT_NORM.get(a, a) if a else '自有'

def tag_prod(n):
    n = n or ''
    if '李博' in n or '物理' in n: return '9元李博'
    if '199' in n or '双科' in n or '三科' in n: return '199双科'
    return '其他'
    n = n or ''
    if '李博' in n or '物理' in n: return '9元李博'
    if '199' in n or '双科' in n or '三科' in n: return '199双科'
    return '其他'

def pn(s):
    try: return float(str(s).replace(',','')) if s and str(s).strip() not in ('','--','-') else 0.0
    except: return 0.0

def _order_col(r):
    """成交单量列名兼容：1009 前为「成交单量」，1016 起变成带腾讯渠道说明的长列名"""
    if '成交单量' in r:
        return '成交单量'
    for k in r.keys():
        if k.startswith('成交单量'):
            return k
    return ''

# ── 读取数据（仅代理CSV，编导侧已停更） ─────────────
items = []
for fpath in [FILE_DL]:
    if not os.path.exists(fpath):
        continue
    with open(fpath, encoding='utf-8-sig') as f:
        for r in csv.DictReader(f):
            name = r.get('素材名称','').strip()
            ip = next((x for x in IP_NAMES if x in name), None)
            if not ip:
                continue
            items.append({
                'ip':    ip,
                'name':  name,
                'prod':  tag_prod(r.get('投放产品','')),
                'spend': pn(r.get('消耗',0)),
                'gmv':   pn(r.get('成交GMV',0)),
                'order': pn(r.get(_order_col(r),0)),
                'cpa':   pn(r.get('CPA',0)),
                'roi':   pn(r.get('ROI',0)),
                'cpm':   pn(r.get('CPM（千次曝光成本）',0)),
                'ctr':   pn(r.get('CTR',0)),
                'days':  pn(r.get('已上线投放天数',0)),
                'agent': norm_agent(r.get('代理商','').strip()),
                'url':   r.get('素材预览','').strip(),
            })

# ── 按 IP 汇总
def agg(rows):
    spend = sum(r['spend'] for r in rows)
    gmv   = sum(r['gmv']   for r in rows)
    order = sum(r['order'] for r in rows)
    cpa   = spend / order if order else 0
    roi   = gmv / spend if spend else 0
    return {'spend': round(spend,2), 'gmv': round(gmv,2), 'order': int(order),
            'cpa': round(cpa,2), 'roi': round(roi,3)}

by_ip   = {ip: agg([r for r in items if r['ip']==ip]) for ip in IP_NAMES}
by_prod = {}
for r in items:
    by_prod.setdefault(r['prod'], []).append(r)
by_prod_agg = {p: agg(v) for p,v in by_prod.items()}

# IP × 产品
by_ip_prod = {}
for ip in IP_NAMES:
    for prod in by_prod:
        sub = [r for r in items if r['ip']==ip and r['prod']==prod]
        if sub:
            by_ip_prod[f'{ip}|{prod}'] = agg(sub)

total_spend = sum(r['spend'] for r in items)
total_gmv   = sum(r['gmv']   for r in items)
total_order = sum(r['order'] for r in items)
total_cpa   = total_spend / total_order if total_order else 0
total_roi   = total_gmv / total_spend if total_spend else 0

def fmt_spend(v):
    if v >= 10000: return f'{v/10000:.1f}万'
    return f'{v:,.0f}'

items_json    = json.dumps(items, ensure_ascii=False)
by_ip_json    = json.dumps(by_ip, ensure_ascii=False)
by_prod_json  = json.dumps(by_prod_agg, ensure_ascii=False)
ip_prod_json  = json.dumps(by_ip_prod, ensure_ascii=False)
ip_names_json = json.dumps(IP_NAMES, ensure_ascii=False)
prods_json    = json.dumps(sorted(by_prod_agg.keys()), ensure_ascii=False)

html = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>IP素材分析 · {DATE}</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<style>
:root{{--bg:#F0F4FA;--s1:#FFFFFF;--s2:#F5F7FB;--s3:#E8ECF4;
  --border:rgba(0,0,0,0.07);--border2:rgba(0,0,0,0.11);
  --amber:#D97706;--blue:#2563EB;--sky:#0EA5E9;--teal:#0D9488;
  --rose:#DC2626;--green:#16A34A;--purple:#7C3AED;--orange:#EA580C;
  --ink:#1E2A3B;--ink2:#374151;--muted:#6B7A99;
  --font:'DM Sans',system-ui,sans-serif;--mono:'DM Mono',monospace;
  --r-sm:6px;--r-md:10px;--r-lg:14px}}
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:var(--font);background:var(--bg);color:var(--ink);min-height:100vh}}
.wrap{{max-width:1280px;margin:0 auto;padding:32px 20px 80px}}
.page-head{{display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:12px;
  padding:18px 22px;background:var(--s1);border:1px solid var(--border);border-radius:var(--r-lg);
  margin-bottom:20px;box-shadow:0 1px 4px rgba(0,0,0,0.05)}}
.head-icon{{width:42px;height:42px;border-radius:10px;background:linear-gradient(135deg,#7C3AED,#2563EB);
  display:flex;align-items:center;justify-content:center;color:#fff;font-weight:700;font-size:15px;flex-shrink:0}}
.head-title{{font-size:19px;font-weight:700;letter-spacing:-.3px}}
.head-sub{{font-size:11px;color:var(--muted);letter-spacing:1px;text-transform:uppercase;margin-top:2px}}
.head-badge{{font-family:var(--mono);font-size:11px;color:var(--muted);background:var(--s2);
  border:1px solid var(--border2);padding:4px 12px;border-radius:4px}}
.kpi-row{{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:20px}}
.kpi-card{{background:var(--s1);border:1px solid var(--border);border-radius:var(--r-lg);padding:18px 20px}}
.kpi-label{{font-size:11px;letter-spacing:1px;text-transform:uppercase;color:var(--muted);margin-bottom:8px}}
.kpi-val{{font-size:26px;font-weight:700;line-height:1;font-family:var(--mono)}}
.kpi-sub{{font-size:11px;color:var(--muted);margin-top:4px}}
.sec-label{{font-size:11px;letter-spacing:1.5px;text-transform:uppercase;color:var(--muted);margin-bottom:10px}}
.chart-grid{{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:20px}}
.chart-box{{background:var(--s1);border:1px solid var(--border);border-radius:var(--r-lg);padding:18px 20px}}
.chart-title{{font-size:11px;letter-spacing:1.5px;text-transform:uppercase;color:var(--muted);margin-bottom:14px}}
.chart-canvas{{position:relative;height:220px}}
.ip-grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:12px;margin-bottom:20px}}
.ip-card{{background:var(--s1);border:1px solid var(--border);border-radius:var(--r-lg);padding:18px 20px}}
.ip-name{{font-size:15px;font-weight:700;margin-bottom:12px}}
.ip-metrics{{display:grid;grid-template-columns:1fr 1fr;gap:8px}}
.ip-metric{{background:var(--s2);border-radius:var(--r-sm);padding:10px 12px}}
.ip-metric-label{{font-size:10px;color:var(--muted);margin-bottom:3px}}
.ip-metric-val{{font-family:var(--mono);font-size:14px;font-weight:600}}
.filter-wrap{{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:12px;align-items:center}}
.filter-label{{font-size:10px;color:var(--muted);letter-spacing:1px;text-transform:uppercase}}
.pf-btn{{background:var(--s1);border:1px solid var(--border2);color:var(--muted);
  padding:5px 12px;border-radius:var(--r-sm);font-size:12px;cursor:pointer;transition:all .15s}}
.pf-btn:hover{{border-color:var(--blue);color:var(--ink)}}
.pf-btn.active{{background:var(--blue);border-color:var(--blue);color:#fff;font-weight:600}}
.tbl-wrap{{background:var(--s1);border:1px solid var(--border);border-radius:var(--r-lg);overflow:hidden;margin-bottom:24px}}
.tbl-scroll{{overflow-x:auto}}
table{{width:100%;border-collapse:collapse}}
th{{font-family:var(--mono);font-size:10px;letter-spacing:1px;text-transform:uppercase;color:var(--muted);
  padding:10px 12px;border-bottom:1px solid var(--border);background:var(--s2);white-space:nowrap;text-align:left}}
th.r{{text-align:right}}th.sortable{{cursor:pointer}}th.sortable:hover{{color:var(--ink)}}
th.asc::after{{content:' ↑';color:var(--amber)}}th.desc::after{{content:' ↓';color:var(--amber)}}
td{{padding:9px 12px;border-bottom:1px solid var(--border);font-size:12px;vertical-align:middle}}
td.r{{text-align:right;font-family:var(--mono);font-size:12px}}
tr:last-child td{{border-bottom:none}}tr:hover td{{background:rgba(37,99,235,0.03)}}
.mat-name{{max-width:240px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}}
.pill{{display:inline-block;padding:2px 8px;border-radius:4px;font-size:11px}}
@media(max-width:800px){{.kpi-row{{grid-template-columns:repeat(2,1fr)}}.chart-grid{{grid-template-columns:1fr}}}}
</style>
</head>
<body>
<div class="wrap">

<div class="page-head">
  <div style="display:flex;align-items:center;gap:14px">
    <div class="head-icon">IP</div>
    <div>
      <div class="head-title">IP老师素材投放分析</div>
      <div class="head-sub">IP MATERIAL · PERFORMANCE REPORT · 2026-{DATE[:2]}-{DATE[2:]}</div>
    </div>
  </div>
  <div class="head-badge">数据截至 2026/{DATE[:2]}/{DATE[2:]}</div>
</div>

<div class="kpi-row">
  <div class="kpi-card">
    <div class="kpi-label">总消耗</div>
    <div class="kpi-val" style="color:var(--amber)">¥{fmt_spend(total_spend)}</div>
    <div class="kpi-sub">元</div>
  </div>
  <div class="kpi-card">
    <div class="kpi-label">成交GMV</div>
    <div class="kpi-val" style="color:var(--blue)">¥{fmt_spend(total_gmv)}</div>
    <div class="kpi-sub">元</div>
  </div>
  <div class="kpi-card">
    <div class="kpi-label">成交单量</div>
    <div class="kpi-val" style="color:var(--teal)">{int(total_order)}</div>
    <div class="kpi-sub">单</div>
  </div>
  <div class="kpi-card">
    <div class="kpi-label">CPA</div>
    <div class="kpi-val" style="color:var(--purple)">{"¥"+f"{total_cpa:.1f}" if total_cpa else "—"}</div>
    <div class="kpi-sub">元 / 单</div>
  </div>
</div>

<div class="sec-label">按 IP 老师</div>
<div class="ip-grid" id="ipCardRow"></div>

<div class="chart-grid">
  <div class="chart-box"><div class="chart-title">IP 消耗对比（元）</div><div class="chart-canvas"><canvas id="ipSpendChart"></canvas></div></div>
  <div class="chart-box"><div class="chart-title">IP 成交单量对比</div><div class="chart-canvas"><canvas id="ipOrderChart"></canvas></div></div>
</div>
<div class="chart-grid">
  <div class="chart-box"><div class="chart-title">产品消耗对比（元）</div><div class="chart-canvas"><canvas id="prodSpendChart"></canvas></div></div>
  <div class="chart-box"><div class="chart-title">产品成交单量对比</div><div class="chart-canvas"><canvas id="prodOrderChart"></canvas></div></div>
</div>

<div class="sec-label">素材明细</div>
<div class="filter-wrap">
  <span class="filter-label">IP</span>
  <div id="filterIP">
    <button class="pf-btn active" onclick="filterIP(this,'all')">全部</button>
  </div>
</div>
<div class="filter-wrap" style="margin-top:-8px">
  <span class="filter-label">产品</span>
  <div id="filterProd">
    <button class="pf-btn active" onclick="filterProd(this,'all')">全部</button>
  </div>
</div>
<div class="tbl-wrap"><div class="tbl-scroll">
<table>
  <thead><tr>
    <th>IP</th>
    <th>产品</th>
    <th>素材名称</th>
    <th class="r sortable" data-key="spend" onclick="sortTbl('spend')">消耗</th>
    <th class="r sortable" data-key="gmv" onclick="sortTbl('gmv')">GMV</th>
    <th class="r sortable" data-key="order" onclick="sortTbl('order')">订单</th>
    <th class="r sortable" data-key="cpa" onclick="sortTbl('cpa')">CPA</th>
    <th class="r sortable" data-key="roi" onclick="sortTbl('roi')">ROI</th>
    <th>代理商</th>
    <th>预览</th>
  </tr></thead>
  <tbody id="tblBody"></tbody>
</table>
</div></div>

</div>
<script>
const ITEMS    = {items_json};
const BY_IP    = {by_ip_json};
const BY_PROD  = {by_prod_json};
const IP_PROD  = {ip_prod_json};
const IP_NAMES = {ip_names_json};
const PRODS    = {prods_json};
const COLORS   = ['#2563EB','#D97706','#0D9488','#7C3AED','#EA580C','#0EA5E9','#16A34A','#DC2626'];

const ipColor  = {{}};
IP_NAMES.forEach((ip,i) => ipColor[ip] = COLORS[i % COLORS.length]);

const barOpts = (label, data, labels, color, fmt) => ({{
  type: 'bar',
  data: {{ labels, datasets: [{{ label, data,
    backgroundColor: Array.isArray(color) ? color.map(c=>c+'CC') : labels.map((_,i)=>COLORS[i%COLORS.length]+'CC'),
    borderRadius: 5, borderSkipped: false }}] }},
  options: {{ responsive:true, maintainAspectRatio:false,
    plugins: {{ legend:{{display:false}}, tooltip:{{callbacks:{{label: c => fmt ? fmt(c.raw) : c.raw}}}} }},
    scales: {{ x:{{grid:{{display:false}},ticks:{{font:{{size:11}}}}}},
               y:{{grid:{{color:'rgba(0,0,0,0.04)'}},ticks:{{font:{{size:11}}}}}} }} }}
}});

window.addEventListener('load', () => {{
  // IP cards
  const cardRow = document.getElementById('ipCardRow');
  IP_NAMES.forEach(ip => {{
    const s = BY_IP[ip]; const c = ipColor[ip];
    cardRow.innerHTML += `<div class="ip-card">
      <div class="ip-name" style="color:${{c}}">${{ip}}</div>
      <div class="ip-metrics">
        <div class="ip-metric"><div class="ip-metric-label">消耗</div><div class="ip-metric-val" style="color:var(--amber)">¥${{s.spend>=10000?(s.spend/10000).toFixed(1)+'万':s.spend.toFixed(0)}}</div></div>
        <div class="ip-metric"><div class="ip-metric-label">GMV</div><div class="ip-metric-val" style="color:var(--blue)">¥${{s.gmv>=10000?(s.gmv/10000).toFixed(1)+'万':s.gmv.toFixed(0)}}</div></div>
        <div class="ip-metric"><div class="ip-metric-label">订单</div><div class="ip-metric-val" style="color:var(--teal)">${{s.order}}</div></div>
        <div class="ip-metric"><div class="ip-metric-label">CPA</div><div class="ip-metric-val" style="color:var(--purple)">${{s.cpa>0?'¥'+s.cpa.toFixed(1):'—'}}</div></div>
      </div>
    </div>`;
  }});

  // Charts
  new Chart(document.getElementById('ipSpendChart'),
    barOpts('消耗', IP_NAMES.map(ip=>+(BY_IP[ip].spend.toFixed(0))), IP_NAMES, null, v=>'¥'+v.toLocaleString()));
  new Chart(document.getElementById('ipOrderChart'),
    barOpts('订单', IP_NAMES.map(ip=>BY_IP[ip].order), IP_NAMES, null));
  new Chart(document.getElementById('prodSpendChart'),
    barOpts('消耗', PRODS.map(p=>+(BY_PROD[p].spend.toFixed(0))), PRODS, null, v=>'¥'+v.toLocaleString()));
  new Chart(document.getElementById('prodOrderChart'),
    barOpts('订单', PRODS.map(p=>BY_PROD[p].order), PRODS, null));

  // Filter buttons
  const fIP = document.getElementById('filterIP');
  IP_NAMES.forEach(ip => {{
    const b = document.createElement('button');
    b.className='pf-btn'; b.textContent=ip;
    b.onclick=()=>filterIP(b,ip); fIP.appendChild(b);
  }});
  const fProd = document.getElementById('filterProd');
  PRODS.forEach(p => {{
    const b = document.createElement('button');
    b.className='pf-btn'; b.textContent=p;
    b.onclick=()=>filterProd(b,p); fProd.appendChild(b);
  }});

  renderTbl();
}});

let curIP='all', curProd='all', sortKey='spend', sortDir='desc';

function renderTbl() {{
  const tbody = document.getElementById('tblBody');
  let rows = ITEMS.filter(r =>
    (curIP==='all'||r.ip===curIP) &&
    (curProd==='all'||r.prod===curProd)
  );
  rows.sort((a,b) => sortDir==='asc' ? a[sortKey]-b[sortKey] : b[sortKey]-a[sortKey]);
  tbody.innerHTML = rows.map(r => {{
    const c = ipColor[r.ip]||'#aaa';
    return `<tr>
      <td><span class="pill" style="background:${{c}}22;color:${{c}}">${{r.ip}}</span></td>
      <td><span class="pill" style="background:var(--sky)22;color:var(--sky);font-size:11px">${{r.prod}}</span></td>
      <td><div class="mat-name" style="white-space:normal;word-break:break-all;max-width:300px">${{r.name}}</div></td>
      <td class="r">${{r.spend>0?'¥'+r.spend.toLocaleString(undefined,{{maximumFractionDigits:0}}):'—'}}</td>
      <td class="r">${{r.gmv>0?'¥'+r.gmv.toLocaleString(undefined,{{maximumFractionDigits:0}}):'—'}}</td>
      <td class="r">${{r.order>0?r.order:'—'}}</td>
      <td class="r">${{r.cpa>0?'¥'+r.cpa.toFixed(1):'—'}}</td>
      <td class="r">${{r.roi>0?r.roi.toFixed(3):'—'}}</td>
      <td style="font-size:11px;color:var(--muted)">${{r.agent}}</td>
      <td>${{r.url?`<a style="color:var(--blue);font-size:11px;text-decoration:none" href="${{r.url}}" target="_blank">▶ 预览</a>`:'—'}}</td>
    </tr>`;
  }}).join('');
}}
function filterIP(btn,val){{
  document.querySelectorAll('#filterIP .pf-btn').forEach(b=>b.classList.remove('active'));
  btn.classList.add('active'); curIP=val; renderTbl();
}}
function filterProd(btn,val){{
  document.querySelectorAll('#filterProd .pf-btn').forEach(b=>b.classList.remove('active'));
  btn.classList.add('active'); curProd=val; renderTbl();
}}
function sortTbl(key){{
  if(sortKey===key) sortDir=sortDir==='desc'?'asc':'desc';
  else{{sortKey=key;sortDir='desc';}}
  document.querySelectorAll('th.sortable').forEach(th=>{{
    th.classList.remove('asc','desc');
    if(th.dataset.key===key) th.classList.add(sortDir);
  }});
  renderTbl();
}}
</script>
</body>
</html>'''

with open(OUT, 'w', encoding='utf-8') as f:
    f.write(html)
print(f'✓ 报告已生成: {OUT}')
print(f'  IP素材: {len(items)} 行 | 总消耗 ¥{total_spend:,.0f} | 订单 {int(total_order)}')

