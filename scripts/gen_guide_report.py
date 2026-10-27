import csv, json, sys

def extract_editor(name):
    if '嘉丽' in name: return '嘉丽'
    if '小敏' in name: return '小敏'
    if ('瑞晨' in name and '浩正' in name) or '瑞浩' in name: return '瑞晨浩正'
    if '浩正' in name: return '浩正'
    if '瑞晨' in name: return '瑞晨'
    if '雅迪' in name: return '雅迪'
    if '婷玉' in name: return '婷玉'
    if '魏怡' in name: return '魏怡'
    if '子矜' in name or '子衿' in name: return '子衿'
    return None

def parse_num(s):
    return float(s.replace(',', '')) if s and s.strip() not in ('', '-', '--') else 0.0

csv_v1 = sys.argv[1] if len(sys.argv) > 1 else 'data/【周报】引导-0716.csv'
csv_v2 = sys.argv[2] if len(sys.argv) > 2 else 'data/【周报】引导第2版-0716.csv'
date_label = sys.argv[3] if len(sys.argv) > 3 else '0716'
out_path = sys.argv[4] if len(sys.argv) > 4 else f'reports/引导素材分析报告_{date_label}.html'

# v1: ad preview URL + spend data
with open(csv_v1, 'r') as f:
    v1_map = {}
    for r in csv.DictReader(f):
        name = r['素材名称'].strip()
        if name and name != '-':
            v1_map[name] = r

# v2: status fields + all submitted materials
with open(csv_v2, 'r') as f:
    v2_rows = list(csv.DictReader(f))

items = []
for r in v2_rows:
    name = r['视频名称'].strip()
    if not name or name == '-':
        continue
    ed = extract_editor(name)
    if not ed:
        continue

    v1 = v1_map.get(name, {})
    # Prefer ad preview URL from v1; fallback to direct link from v2
    url = v1.get('素材内容', '').strip() or r.get('视频链接', '').strip()
    mat_type = v1.get('素材类型', '').strip() or '竖版视频'

    spend = parse_num(r['消耗'])
    imp = int(parse_num(r['展示数']))
    cpm = parse_num(r['平均千次展现费用(元)'])
    click = int(parse_num(r['点击数']))
    ctr_raw = parse_num(r['点击率(%)'])
    ctr = f'{ctr_raw:.2f}%'
    cpc = parse_num(r['平均点击单价(元)'])
    conv = int(parse_num(r['转化数']))
    cpa_val = parse_num(r['转化成本'])
    cvr_raw = parse_num(r['转化率(%)'])
    cvr = f'{cvr_raw:.2f}%'
    units = r['关联在投单元数'].strip()
    units = int(units) if units.isdigit() else 0

    status = r['投放情况'].strip()      # 已使用 / 未使用
    review = r['审核建议'].strip()      # 审核通过 / 审核不通过 / --
    grade  = r['素材评估'].strip()      # 首发 / 优质 / --

    items.append({
        'editor': ed, 'name': name, 'url': url, 'type': mat_type,
        'spend': spend, 'imp': imp, 'cpm': cpm, 'click': click,
        'ctr': ctr, 'cpc': cpc, 'conv': conv, 'cpa': cpa_val, 'cvr': cvr,
        'units': units, 'status': status, 'review': review, 'grade': grade
    })

items.sort(key=lambda x: (-x['spend'], x['editor']))

# Performance KPIs (items with spend > 0)
perf_items = [x for x in items if x['spend'] > 0]
total_spend = sum(x['spend'] for x in perf_items)
total_conv  = sum(x['conv']  for x in perf_items)
avg_cpa     = total_spend / total_conv if total_conv else 0
mat_count   = len(perf_items)

# Library KPIs
total_submit  = len(items)
review_pass   = sum(1 for x in items if x['review'] == '审核通过')
review_fail   = sum(1 for x in items if x['review'] == '审核不通过')
in_use        = sum(1 for x in items if x['status'] == '已使用')
pass_rate     = review_pass / (review_pass + review_fail) * 100 if (review_pass + review_fail) else 0

raw_json = json.dumps(items, ensure_ascii=False)

def fmt_n(v):
    return f'{v:,.0f}'

fmt_spend = fmt_n

html = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>引导素材分析 · {date_label}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Syne:wght@700;800&family=DM+Sans:wght@300;400;500&family=DM+Mono:wght@400;500&display=swap" rel="stylesheet" media="print" onload="this.media='all'">
<noscript><link href="https://fonts.googleapis.com/css2?family=Syne:wght@700;800&family=DM+Sans:wght@300;400;500&family=DM+Mono:wght@400;500&display=swap" rel="stylesheet"></noscript>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<style>
:root{{
  --ink:#F4F6FA;--s1:#FFFFFF;--s2:#EEF1F7;--s3:#E2E7F0;
  --border:rgba(0,0,0,0.08);--border2:rgba(0,0,0,0.12);
  --amber:#D97706;--azure:#2563EB;--teal:#0D9488;--rose:#DC2626;
  --green:#16A34A;--purple:#7C3AED;
  --text:#1E2A3B;--muted:#6B7A99;--dim:#D1D9E6;
  --font-d:'Syne',sans-serif;--font-b:'DM Sans',sans-serif;--font-m:'DM Mono',monospace;
}}
*{{margin:0;padding:0;box-sizing:border-box}}
html{{scroll-behavior:smooth}}
body{{
  font-family:var(--font-b);background:var(--ink);color:var(--text);min-height:100vh;
  background-image:linear-gradient(rgba(37,99,235,0.04) 1px,transparent 1px),
    linear-gradient(90deg,rgba(37,99,235,0.04) 1px,transparent 1px);
  background-size:40px 40px;
}}
.wrap{{max-width:1400px;margin:0 auto;padding:40px 24px 80px}}
.page-head{{display:flex;align-items:flex-end;justify-content:space-between;flex-wrap:wrap;gap:16px;
  padding-bottom:28px;margin-bottom:36px;border-bottom:1px solid var(--border)}}
.head-left h1{{font-family:var(--font-d);font-size:clamp(26px,3.5vw,44px);font-weight:800;
  letter-spacing:-1.5px;line-height:1}}
.head-left h1 em{{font-style:normal;color:var(--amber)}}
.head-meta{{font-family:var(--font-m);font-size:11px;letter-spacing:1.5px;color:var(--muted);
  margin-top:8px;text-transform:uppercase}}
.date-badge{{font-family:var(--font-m);font-size:11px;letter-spacing:1px;
  background:var(--s2);border:1px solid var(--border2);color:var(--muted);padding:5px 12px;border-radius:4px}}
.kpi-bar{{display:grid;grid-template-columns:repeat(4,1fr);gap:1px;
  background:var(--border);border:1px solid var(--border);border-radius:12px;overflow:hidden;margin-bottom:36px}}
.kpi-cell{{background:var(--s1);padding:20px 24px}}
.kpi-label{{font-size:11px;letter-spacing:1px;text-transform:uppercase;color:var(--muted);margin-bottom:8px}}
.kpi-val{{font-family:var(--font-d);font-size:32px;font-weight:800;color:var(--amber);line-height:1}}
.kpi-sub{{font-size:12px;color:var(--muted);margin-top:4px}}
.chart-row{{display:grid;grid-template-columns:repeat(3,1fr);gap:16px;margin-bottom:36px}}
.chart-box{{background:var(--s1);border:1px solid var(--border);border-radius:12px;padding:20px;
  box-shadow:0 1px 4px rgba(0,0,0,0.06)}}
.chart-title{{font-size:12px;letter-spacing:1px;text-transform:uppercase;color:var(--muted);margin-bottom:16px}}
.chart-canvas{{position:relative;height:220px}}
.sec-label{{font-family:var(--font-m);font-size:11px;letter-spacing:2px;text-transform:uppercase;
  color:var(--muted);margin-bottom:16px;padding-left:2px}}
.funnel-row{{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:36px}}
.funnel-card{{background:var(--s1);border:1px solid var(--border);border-radius:12px;padding:18px 16px;
  box-shadow:0 1px 4px rgba(0,0,0,0.06)}}
.funnel-name{{font-family:var(--font-d);font-size:15px;font-weight:700;margin-bottom:14px}}
.funnel-step{{margin-bottom:10px}}
.funnel-step-label{{font-size:11px;color:var(--muted);margin-bottom:4px;display:flex;justify-content:space-between}}
.funnel-bar-wrap{{background:var(--dim);border-radius:3px;height:6px;overflow:hidden}}
.funnel-bar{{height:6px;border-radius:3px;transition:width .4s}}
.funnel-pct{{font-family:var(--font-m);font-size:13px;font-weight:500;margin-top:6px}}
.filter-row{{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:14px}}
.pf-btn{{background:var(--s1);border:1px solid var(--border2);color:var(--muted);
  padding:6px 14px;border-radius:6px;font-size:12px;cursor:pointer;transition:all .2s}}
.pf-btn:hover{{border-color:var(--amber);color:var(--text)}}
.pf-btn.active{{background:var(--amber);border-color:var(--amber);color:#fff;font-weight:600}}
.tbl-wrap{{overflow-x:auto;margin-bottom:40px;background:var(--s1);border:1px solid var(--border);
  border-radius:12px;box-shadow:0 1px 4px rgba(0,0,0,0.06)}}
table{{width:100%;border-collapse:collapse}}
th{{font-family:var(--font-m);font-size:10px;letter-spacing:1px;text-transform:uppercase;
  color:var(--muted);padding:10px 12px;border-bottom:1px solid var(--border);
  white-space:nowrap;text-align:left;background:var(--s2)}}
th.num{{text-align:right}}
td{{padding:10px 12px;border-bottom:1px solid var(--border);font-size:13px;vertical-align:middle}}
td.num{{text-align:right;font-family:var(--font-m);font-size:12px}}
tr:last-child td{{border-bottom:none}}
tr:hover td{{background:rgba(37,99,235,0.04)}}
.mat-name{{max-width:220px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:12px}}
.type-badge{{display:inline-block;padding:2px 8px;border-radius:4px;font-size:10px;font-family:var(--font-m)}}
.type-v{{background:rgba(13,148,136,0.12);color:var(--teal)}}
.type-h{{background:rgba(217,119,6,0.12);color:var(--amber)}}
.preview-link{{color:var(--azure);font-size:11px;text-decoration:none;opacity:.8}}
.preview-link:hover{{opacity:1}}
.pill{{display:inline-block;padding:2px 8px;border-radius:4px;font-size:11px;font-family:var(--font-m);background:var(--s3);color:var(--muted)}}
.sortable{{cursor:pointer;user-select:none}}
.sortable:hover{{color:var(--text)}}
.sort-icon{{font-size:10px;opacity:.4;margin-left:3px}}
.sortable.asc .sort-icon::after{{content:'↑';opacity:1;color:var(--amber)}}
.sortable.desc .sort-icon::after{{content:'↓';opacity:1;color:var(--amber)}}
.footer{{text-align:center;font-family:var(--font-m);font-size:11px;color:var(--muted);
  margin-top:40px;padding-top:24px;border-top:1px solid var(--border)}}
@media(max-width:900px){{
  .chart-row{{grid-template-columns:1fr}}
  .funnel-row{{grid-template-columns:repeat(2,1fr)}}
  .kpi-bar{{grid-template-columns:repeat(2,1fr)}}
}}
</style>
</head>
<body>
<div class="wrap">
<div class="page-head">
  <div class="head-left">
    <h1>引导素材 <em>投放分析</em></h1>
    <div class="head-meta">Guide Material · Performance Report · 2026-07-{date_label[2:]}</div>
  </div>
  <div class="date-badge">数据截止 2026-07-{date_label[2:]}</div>
</div>
<div class="sec-label">投放效果</div>
<div class="kpi-bar">
  <div class="kpi-cell"><div class="kpi-label">总消耗</div><div class="kpi-val">{fmt_spend(total_spend)}</div><div class="kpi-sub">元</div></div>
  <div class="kpi-cell"><div class="kpi-label">总转化</div><div class="kpi-val">{total_conv}</div><div class="kpi-sub">单</div></div>
  <div class="kpi-cell"><div class="kpi-label">平均 CPA</div><div class="kpi-val">{avg_cpa:.2f}</div><div class="kpi-sub">元 / 单</div></div>
  <div class="kpi-cell"><div class="kpi-label">有消耗素材</div><div class="kpi-val">{mat_count}</div><div class="kpi-sub">条</div></div>
</div>
<div class="sec-label" style="margin-top:28px">素材库总览</div>
<div class="kpi-bar" style="grid-template-columns:repeat(5,1fr)">
  <div class="kpi-cell"><div class="kpi-label">提交总数</div><div class="kpi-val" style="color:var(--azure)">{total_submit}</div><div class="kpi-sub">条</div></div>
  <div class="kpi-cell"><div class="kpi-label">审核通过</div><div class="kpi-val" style="color:var(--green)">{review_pass}</div><div class="kpi-sub">条</div></div>
  <div class="kpi-cell"><div class="kpi-label">审核不通过</div><div class="kpi-val" style="color:var(--rose)">{review_fail}</div><div class="kpi-sub">条</div></div>
  <div class="kpi-cell"><div class="kpi-label">在投数</div><div class="kpi-val" style="color:var(--teal)">{in_use}</div><div class="kpi-sub">条</div></div>
  <div class="kpi-cell"><div class="kpi-label">审核通过率</div><div class="kpi-val" style="color:var(--purple)">{pass_rate:.0f}%</div><div class="kpi-sub">通过 / (通过+不通过)</div></div>
</div>
<div class="sec-label" style="margin-top:28px">投放数据对比（按编导）</div>
<div class="chart-row" style="grid-template-columns:repeat(2,1fr)">
  <div class="chart-box"><div class="chart-title">消耗对比（元）</div><div class="chart-canvas" style="height:240px"><canvas id="spendChart"></canvas></div></div>
  <div class="chart-box"><div class="chart-title">CTR 对比（%）</div><div class="chart-canvas" style="height:240px"><canvas id="ctrChart"></canvas></div></div>
</div>
<div class="chart-row" style="grid-template-columns:repeat(2,1fr);margin-bottom:36px">
  <div class="chart-box"><div class="chart-title">CPA 对比（元）</div><div class="chart-canvas" style="height:240px"><canvas id="cpaChart"></canvas></div></div>
  <div class="chart-box"><div class="chart-title">审核通过 / 不通过（按编导）</div><div class="chart-canvas" style="height:240px"><canvas id="reviewChart"></canvas></div></div>
</div>
<div class="sec-label">点击 → 转化漏斗（按编导）</div>
<div class="funnel-row" id="funnelRow"></div>
<div class="sec-label">素材明细</div>
<div style="display:flex;gap:16px;flex-wrap:wrap;margin-bottom:10px;align-items:center">
  <span style="font-family:var(--font-m);font-size:10px;letter-spacing:1px;color:var(--muted);text-transform:uppercase">审核</span>
  <div class="filter-row" id="statusFilterRow" style="margin:0">
    <button class="pf-btn active" onclick="setStatusFilter(this,'all')">全部</button>
    <button class="pf-btn" onclick="setStatusFilter(this,'审核通过')">审核通过</button>
    <button class="pf-btn" onclick="setStatusFilter(this,'审核不通过')">审核不通过</button>
  </div>
</div>
<div style="display:flex;gap:16px;flex-wrap:wrap;margin-bottom:14px;align-items:center">
  <span style="font-family:var(--font-m);font-size:10px;letter-spacing:1px;color:var(--muted);text-transform:uppercase">编导</span>
  <div class="filter-row" id="filterRow" style="margin:0">
    <button class="pf-btn active" onclick="filterTable(this,'all')">全部</button>
  </div>
</div>
<div class="tbl-wrap">
<table>
  <thead><tr>
    <th>编导</th><th>素材名称</th><th>类型</th>
    <th class="num sortable" data-key="spend" onclick="sortTable('spend')">消耗 <span class="sort-icon" id="si-spend"></span></th>
    <th class="num sortable" data-key="imp" onclick="sortTable('imp')">展示数 <span class="sort-icon" id="si-imp"></span></th>
    <th class="num sortable" data-key="cpm" onclick="sortTable('cpm')">CPM <span class="sort-icon" id="si-cpm"></span></th>
    <th class="num sortable" data-key="click" onclick="sortTable('click')">点击数 <span class="sort-icon" id="si-click"></span></th>
    <th class="num sortable" data-key="ctr_n" onclick="sortTable('ctr_n')">CTR <span class="sort-icon" id="si-ctr_n"></span></th>
    <th class="num sortable" data-key="conv" onclick="sortTable('conv')">转化数 <span class="sort-icon" id="si-conv"></span></th>
    <th class="num sortable" data-key="cpa" onclick="sortTable('cpa')">CPA <span class="sort-icon" id="si-cpa"></span></th>
    <th class="num sortable" data-key="cvr_n" onclick="sortTable('cvr_n')">CVR <span class="sort-icon" id="si-cvr_n"></span></th>
    <th class="num sortable" data-key="units" onclick="sortTable('units')">关联单元 <span class="sort-icon" id="si-units"></span></th>
    <th>投放情况</th><th>审核建议</th><th>素材评估</th>
    <th>预览</th>
  </tr></thead>
  <tbody id="tableBody"></tbody>
</table>
</div>
<div class="footer">Generated 2026-07-18 · 引导素材投放分析报告 {date_label}</div>
</div>
<script>
Chart.defaults.color='#6B7A99';
Chart.defaults.borderColor='rgba(0,0,0,0.06)';
const COLORS=['#D97706','#2563EB','#0D9488','#7C3AED','#DC2626','#16A34A','#EA580C'];
const RAW={raw_json};
const editorMap={{}};
RAW.forEach(r=>{{
  if(!editorMap[r.editor]) editorMap[r.editor]={{spend:0,imp:0,click:0,conv:0,count:0,color:''}};
  const e=editorMap[r.editor];
  e.spend+=r.spend;e.imp+=r.imp;e.click+=r.click;e.conv+=r.conv;e.count++;
}});
const editors=Object.keys(editorMap).sort((a,b)=>editorMap[b].spend-editorMap[a].spend);
editors.forEach((e,i)=>{{editorMap[e].color=COLORS[i%COLORS.length];}});
const bgColors=editors.map(e=>editorMap[e].color);
const barOpts=(label,data,fmt)=>({{
  type:'bar',
  data:{{labels:editors,datasets:[{{label,data,backgroundColor:bgColors,borderRadius:6,borderSkipped:false}}]}},
  options:{{responsive:true,maintainAspectRatio:false,
    plugins:{{legend:{{display:false}},tooltip:{{callbacks:{{label:c=>fmt?fmt(c.raw):c.raw}}}}}},
    scales:{{x:{{grid:{{display:false}},ticks:{{color:'#6B7A99',font:{{size:11}}}}}},
      y:{{grid:{{color:'rgba(0,0,0,0.04)'}},ticks:{{color:'#6B7A99',font:{{size:11}}}}}}}}}}
}});
new Chart(document.getElementById('spendChart'),barOpts('消耗',editors.map(e=>+editorMap[e].spend.toFixed(0)),v=>'¥'+v.toLocaleString()));
new Chart(document.getElementById('ctrChart'),barOpts('CTR',editors.map(e=>editorMap[e].imp?+(editorMap[e].click/editorMap[e].imp*100).toFixed(2):0),v=>v+'%'));
new Chart(document.getElementById('cpaChart'),barOpts('CPA',editors.map(e=>editorMap[e].conv?+(editorMap[e].spend/editorMap[e].conv).toFixed(2):0),v=>v?'¥'+v:'—'));
// Review pass rate stacked bar by editor
const reviewByEd={{}};
RAW.forEach(r=>{{
  if(!reviewByEd[r.editor]) reviewByEd[r.editor]={{pass:0,fail:0,other:0}};
  if(r.review==='审核通过') reviewByEd[r.editor].pass++;
  else if(r.review==='审核不通过') reviewByEd[r.editor].fail++;
  else reviewByEd[r.editor].other++;
}});
new Chart(document.getElementById('reviewChart'),{{
  type:'bar',
  data:{{labels:editors,
    datasets:[
      {{label:'通过',data:editors.map(e=>reviewByEd[e]?.pass||0),backgroundColor:'rgba(22,163,74,0.8)',borderRadius:0}},
      {{label:'不通过',data:editors.map(e=>reviewByEd[e]?.fail||0),backgroundColor:'rgba(220,38,38,0.7)',borderRadius:0}},
      {{label:'待定',data:editors.map(e=>reviewByEd[e]?.other||0),backgroundColor:'rgba(107,122,153,0.3)',borderRadius:6}}
    ]}},
  options:{{responsive:true,maintainAspectRatio:false,
    plugins:{{legend:{{display:true,position:'bottom',labels:{{font:{{size:10}},boxWidth:10,padding:8}}}},
      tooltip:{{callbacks:{{label:c=>c.dataset.label+': '+c.raw}}}}}},
    scales:{{x:{{stacked:true,grid:{{display:false}},ticks:{{color:'#6B7A99',font:{{size:11}}}}}},
      y:{{stacked:true,grid:{{color:'rgba(0,0,0,0.04)'}},ticks:{{color:'#6B7A99',font:{{size:11}}}}}}}}}}
}});
const funnelRow=document.getElementById('funnelRow');
editors.forEach((e,i)=>{{
  const d=editorMap[e];
  const ctr=d.imp?(d.click/d.imp*100).toFixed(2):0;
  const cvr=d.click?(d.conv/d.click*100).toFixed(2):0;
  const ctrPct=d.imp?Math.min(100,d.click/d.imp*100):0;
  const cvrPct=d.click?Math.min(100,d.conv/d.click*100):0;
  funnelRow.innerHTML+=`<div class="funnel-card">
    <div class="funnel-name" style="color:${{d.color}}">${{e}}</div>
    <div class="funnel-step">
      <div class="funnel-step-label"><span>展示</span><span>${{d.imp.toLocaleString()}}</span></div>
      <div class="funnel-bar-wrap"><div class="funnel-bar" style="width:100%;background:${{d.color}}33"></div></div>
    </div>
    <div class="funnel-step">
      <div class="funnel-step-label"><span>点击</span><span>${{d.click.toLocaleString()}}</span></div>
      <div class="funnel-bar-wrap"><div class="funnel-bar" style="width:${{ctrPct}}%;background:${{d.color}}88"></div></div>
      <div class="funnel-pct" style="color:${{d.color}}">CTR ${{ctr}}%</div>
    </div>
    <div class="funnel-step">
      <div class="funnel-step-label"><span>转化</span><span>${{d.conv}}</span></div>
      <div class="funnel-bar-wrap"><div class="funnel-bar" style="width:${{cvrPct}}%;background:${{d.color}}"></div></div>
      <div class="funnel-pct" style="color:${{d.color}}">CVR ${{cvr}}%</div>
    </div>
    <div style="margin-top:12px;font-family:var(--font-m);font-size:11px;color:var(--muted)">
      消耗 <span style="color:var(--text)">¥${{d.spend.toFixed(0)}}</span>
      &nbsp;·&nbsp; CPA <span style="color:var(--text)">${{d.conv?'¥'+(d.spend/d.conv).toFixed(1):'—'}}</span>
    </div>
  </div>`;
}});
const filterRow=document.getElementById('filterRow');
editors.forEach(e=>{{
  const btn=document.createElement('button');
  btn.className='pf-btn';btn.textContent=e;
  btn.onclick=()=>filterTable(btn,e);
  filterRow.appendChild(btn);
}});
let sortKey='spend',sortDir='desc',activeFilter='all',activeStatusFilter='all';
function sortVal(r,key){{
  if(key==='ctr_n') return r.imp?r.click/r.imp:0;
  if(key==='cvr_n') return r.click?r.conv/r.click:0;
  return r[key]||0;
}}
function renderTable(){{
  const tbody=document.getElementById('tableBody');
  let rows=RAW.filter(r=>
    (activeFilter==='all'||r.editor===activeFilter)&&
    (activeStatusFilter==='all'||r.review===activeStatusFilter)
  );
  if(sortKey) rows.sort((a,b)=>sortDir==='asc'?sortVal(a,sortKey)-sortVal(b,sortKey):sortVal(b,sortKey)-sortVal(a,sortKey));
  const statusColor={{'已使用':'var(--teal)','未使用':'var(--muted)'}};
  const reviewColor={{'审核通过':'var(--green)','审核不通过':'var(--rose)'}};
  const gradeColor={{'首发':'var(--amber)','优质':'var(--azure)'}};
  tbody.innerHTML=rows.map(r=>{{
    const typeClass=r.type.includes('竖')?'type-v':'type-h';
    const preview=r.url?`<a class="preview-link" href="${{r.url}}" target="_blank">▶ 预览</a>`:'—';
    const cpaD=r.conv?`¥${{r.cpa.toFixed(2)}}`:'—';
    const statusHtml=r.status?`<span style="font-size:11px;color:${{statusColor[r.status]||'var(--muted)'}}">${{r.status}}</span>`:'—';
    const reviewHtml=r.review&&r.review!=='--'?`<span style="font-size:11px;color:${{reviewColor[r.review]||'var(--muted)'}}">${{r.review}}</span>`:'—';
    const gradeHtml=r.grade&&r.grade!=='--'?`<span class="pill" style="background:${{gradeColor[r.grade]||'var(--s3)'}}22;color:${{gradeColor[r.grade]||'var(--muted)'}}">${{r.grade}}</span>`:'—';
    return`<tr><td><span class="pill" style="background:${{editorMap[r.editor].color}}22;color:${{editorMap[r.editor].color}}">${{r.editor}}</span></td>
      <td><div class="mat-name" title="${{r.name}}">${{r.name}}</div></td>
      <td><span class="type-badge ${{typeClass}}">${{r.type}}</span></td>
      <td class="num">¥${{r.spend.toLocaleString()}}</td>
      <td class="num">${{r.imp.toLocaleString()}}</td>
      <td class="num">${{r.cpm.toFixed(2)}}</td>
      <td class="num">${{r.click.toLocaleString()}}</td>
      <td class="num">${{r.ctr}}</td>
      <td class="num">${{r.conv}}</td>
      <td class="num">${{cpaD}}</td>
      <td class="num">${{r.cvr}}</td>
      <td class="num">${{r.units||'—'}}</td>
      <td>${{statusHtml}}</td>
      <td>${{reviewHtml}}</td>
      <td>${{gradeHtml}}</td>
      <td>${{preview}}</td></tr>`;
  }}).join('');
}}
renderTable();
document.querySelector('th[data-key="spend"]').classList.add('desc');
function sortTable(key){{
  if(sortKey===key) sortDir=sortDir==='desc'?'asc':'desc';
  else{{sortKey=key;sortDir='desc';}}
  document.querySelectorAll('th.sortable').forEach(th=>{{th.classList.remove('asc','desc');if(th.dataset.key===sortKey)th.classList.add(sortDir);}});
  renderTable();
}}
function filterTable(btn,val){{
  document.querySelectorAll('#filterRow .pf-btn').forEach(b=>b.classList.remove('active'));
  btn.classList.add('active');activeFilter=val;renderTable();
}}
function setStatusFilter(btn,val){{
  document.querySelectorAll('#statusFilterRow .pf-btn').forEach(b=>b.classList.remove('active'));
  btn.classList.add('active');activeStatusFilter=val;renderTable();
}}
</script>
</body>
</html>'''

with open(out_path, 'w') as f:
    f.write(html)
print(f'Written to {out_path}')
print(f'Total spend: {total_spend:,.2f}, Conv: {total_conv}, CPA: {avg_cpa:.2f}, Items: {mat_count}')
