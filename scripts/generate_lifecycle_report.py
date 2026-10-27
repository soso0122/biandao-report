#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
素材生命周期分析 HTML 报告生成器
用法:
  python3 scripts/generate_lifecycle_report.py
读 reports/素材生命周期_总结.csv + 每日明细 + data/ 原始日数据，输出 reports/素材生命周期分析.html
"""
import csv, json, re, sys
from pathlib import Path
from collections import defaultdict

ROOT = Path(__file__).parent.parent
DATA = ROOT / 'data'
OUT = ROOT / 'reports'


def f(v):
    v = str(v or '0').replace(',', '')
    try:
        return float(v)
    except:
        return 0.0


def main():
    # ---------- 1. 素材总结 ----------
    life = list(csv.DictReader(open(OUT / '素材生命周期_总结.csv', encoding='utf-8-sig')))
    for r in life:
        r['_spend'] = f(r['总消耗'])

    # ---------- 2. 逐日轨迹：每素材每天的 {spend, gq} ----------
    files = [x for x in sorted(DATA.glob('引导加微每日数据-*.csv'))
             if re.fullmatch(r'引导加微每日数据-\d{4}', x.stem)]

    # 第一遍：建立 名字→主素材id 映射（0827 缺素材id列，按名字归并到主id）
    name_to_id = {}
    id_spend = defaultdict(float)
    for fp in files:
        with open(fp, encoding='utf-8-sig') as fh:
            for r in csv.DictReader(fh):
                name = (r.get('视频名称') or '').strip()
                sid = (r.get('素材id') or '').strip()
                if not sid:
                    continue
                id_spend[sid] += f(r.get('消耗'))
                for n in {name, name[5:] if name.startswith('推送视频_') else name}:
                    if not n:
                        continue
                    if n not in name_to_id:
                        name_to_id[n] = sid
                    elif id_spend[name_to_id[n]] < id_spend[sid]:
                        name_to_id[n] = sid

    def norm_key(name, sid):
        if name in name_to_id:
            return name_to_id[name]
        if sid:
            return sid
        return name

    dates = []
    traj = defaultdict(dict)  # key -> {date_label: [spend, gq]}
    for fp in files:
        mmdd = re.search(r'(\d{4})', fp.stem).group(1)
        label = f"{mmdd[:2]}/{mmdd[2:]}"
        dates.append(label)
        with open(fp, encoding='utf-8-sig') as fh:
            for r in csv.DictReader(fh):
                name = (r.get('视频名称') or '').strip()
                if not name:
                    continue
                link = (r.get('视频链接') or '').strip()
                is_home = bool(re.fullmatch(r'\d+', name) or re.fullmatch(r'[\d.]+[eE][+\-]?\d+', name))
                if is_home:
                    continue
                sid = (r.get('素材id') or '').strip()
                key = norm_key(name, sid)
                sp = f(r.get('消耗'))
                gq = f(r.get('回访-高潜成交(计费时间)'))
                if label not in traj[key]:
                    traj[key][label] = [0.0, 0.0]
                traj[key][label][0] += sp
                traj[key][label][1] += gq

    # ---------- 3. 挂计划零消耗视频（最近一天） ----------
    latest = files[-1]
    plan_only = []
    seen_plan = set()
    with open(latest, encoding='utf-8-sig') as fh:
        for r in csv.DictReader(fh):
            name = (r.get('视频名称') or '').strip()
            link = (r.get('视频链接') or '').strip()
            spend = f(r.get('消耗'))
            units = f(r.get('关联在投单元数'))
            is_home = bool(re.fullmatch(r'\d+', name) or re.fullmatch(r'[\d.]+[eE][+\-]?\d+', name))
            is_video = len(link) >= 10 and '图文' not in name and not is_home and not name.upper().startswith('AI')
            if is_video and spend == 0 and units > 0 and name not in seen_plan:
                seen_plan.add(name)
                plan_only.append({'name': name, 'units': int(units)})
    plan_only.sort(key=lambda x: -x['units'])

    # ---------- 4. 汇总统计 ----------
    n_life = len(life)
    n_now = sum(1 for r in life if int(r['已停天数']) == 0)
    tot_spend = sum(r['_spend'] for r in life)
    tot_gq = sum(int(r['总高潜']) for r in life)
    top30_spend = sum(r['_spend'] for r in sorted(life, key=lambda x: -x['_spend'])[:30])
    top30_gq = sum(int(r.get('总高潜') or 0) for r in sorted(life, key=lambda x: -int(x.get('总高潜') or 0))[:30])
    one_day = [r for r in life if r['投放模式'] == '试投一天即停']
    one_day_med = sorted(r['_spend'] for r in one_day)
    one_day_med = one_day_med[len(one_day_med) // 2] if one_day_med else 0
    one_day_n = len(one_day)
    low_budget = sum(1 for r in life if r['_spend'] <= 100)
    cont = [r for r in life if r['投放模式'] == '持续在跑']

    # ---------- 5. 看片清单 ----------
    watch = list(csv.DictReader(open(OUT / '看片清单_视频素材.csv', encoding='utf-8-sig')))
    for w in watch:
        w['_spend'] = f(w['总消耗'])

    # ---------- 6. 逐日活跃/消耗 ----------
    daily_active = []
    for label in dates:
        day = traj
        act = sum(1 for k in day if day[k].get(label, [0, 0])[0] > 0)
        sp = sum(day[k].get(label, [0, 0])[0] for k in day)
        daily_active.append({'d': label, 'act': act, 'spend': round(sp, 0)})

    # ---------- 7. 输出 JSON 供 HTML ----------
    life_js = []
    for r in life:
        key = r['素材id'] or r['素材名称']
        t = traj.get(r['素材id']) or {}
        # 若 key 用名称也能命中
        if not t:
            for k, v in traj.items():
                if k.endswith(r['素材名称']):
                    t = v
                    break
        seq = [{'d': d, 's': round(t.get(d, [0, 0])[0], 2), 'g': int(t.get(d, [0, 0])[1])} for d in dates]
        life_js.append({
            'id': r['素材id'], 'name': r['素材名称'], 'person': r['人'], 'type': r['类型'],
            'tag': r['标签'], 'account': r['账户'],
            'first': r['首投日期'], 'last': r['末投日期'],
            'activeDays': int(r['在投天数']), 'span': int(r['时间跨度']),
            'stops': int(r['停投次数(≥2天)']), 'oneDayGaps': int(r['停1天次数']),
            'maxGap': int(r['最长连续停投']), 'idle': int(r['已停天数']),
            'spend': round(r['_spend'], 2), 'conv': int(r['总转化']), 'gq': int(r['总高潜']),
            'gqMode': r['深转模式'], 'gqLost': r.get('深转消失信号') == '是',
            'runMode': r['投放模式'], 'traj': seq,
        })

    # ---------- 8. HTML ----------
    html = HTML_TEMPLATE.format(
        n_life=n_life, n_now=n_now,
        tot_spend=f"{tot_spend:,.0f}", tot_gq=tot_gq,
        top30_pct=f"{top30_spend/tot_spend*100:.1f}" if tot_spend else '0',
        top30_gq_pct=f"{top30_gq/tot_gq*100:.0f}" if tot_gq else '0',
        low_budget_pct=f"{low_budget/n_life*100:.0f}" if n_life else '0',
        one_day_med=f"{one_day_med:.2f}",
        one_day_n=one_day_n,
        n_plan_only=len(plan_only),
        n_cont=len(cont),
        life_js=json.dumps(life_js, ensure_ascii=False),
        daily_js=json.dumps(daily_active, ensure_ascii=False),
        watch_js=json.dumps(watch, ensure_ascii=False),
        plan_only_js=json.dumps(plan_only, ensure_ascii=False),
    )

    # 内嵌 Chart.js
    chart_js = (Path(__file__).parent / 'chart.min.js').read_text(encoding='utf-8')
    html = html.replace('<script src="CHART_JS_PLACEHOLDER"></script>', f'<script>{chart_js}</script>', 1)

    out_path = OUT / '素材生命周期分析.html'
    out_path.write_text(html, encoding='utf-8')
    print(f'报告已生成: {out_path} ({out_path.stat().st_size/1e6:.1f} MB)')


HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>素材生命周期分析 · 千川信息流</title>
<script src="CHART_JS_PLACEHOLDER"></script>
<style>
*,*::before,*::after{{box-sizing:border-box;margin:0;padding:0}}
:root{{
  --bg:#F8FAFC;--card:#FFFFFF;--border:#DBEAFE;
  --primary:#1E40AF;--primary-light:#3B82F6;
  --accent:#D97706;--accent-bg:#FFFBEB;
  --text:#1E3A8A;--text-secondary:#64748B;--text-muted:#94A3B8;
  --success:#059669;--danger:#DC2626;
  --shadow:0 1px 3px rgba(0,0,0,.08);--shadow-md:0 4px 6px rgba(0,0,0,.07);
  --radius:10px;
  font-family:'Fira Sans',system-ui,'PingFang SC','Microsoft YaHei',sans-serif;
}}
body{{background:var(--bg);color:var(--text);font-size:14px;line-height:1.5;min-height:100vh}}
.header{{background:linear-gradient(135deg,#1E3A8A 0%,#1E40AF 60%,#2563EB 100%);padding:20px 28px 18px;color:#fff}}
.header h1{{font-size:20px;font-weight:700}}
.header p{{color:rgba(255,255,255,.7);font-size:12px;margin-top:4px}}
.wrap{{max-width:1400px;margin:0 auto;padding:20px}}
.kpi-grid{{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:20px}}
.kpi{{background:var(--card);border:1px solid var(--border);border-radius:var(--radius);padding:14px 16px;box-shadow:var(--shadow)}}
.kpi .lbl{{font-size:11px;color:var(--text-secondary)}}
.kpi .val{{font-size:22px;font-weight:700;color:var(--primary);font-family:monospace;margin-top:2px}}
.kpi .sub{{font-size:11px;color:var(--text-muted);margin-top:2px}}
.card{{background:var(--card);border:1px solid var(--border);border-radius:var(--radius);padding:16px 18px;box-shadow:var(--shadow);margin-bottom:16px}}
.card h2{{font-size:15px;font-weight:700;color:var(--primary);margin-bottom:10px}}
.conclusion{{background:var(--accent-bg);border:1.5px solid #FDE68A;border-radius:var(--radius);padding:16px 18px;margin-bottom:16px}}
.conclusion h2{{font-size:15px;font-weight:700;color:var(--accent);margin-bottom:8px}}
.conclusion p{{font-size:13px;color:#78350F;margin-bottom:6px}}
.charts{{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:16px}}
.chart-box{{background:var(--card);border:1px solid var(--border);border-radius:var(--radius);padding:14px;box-shadow:var(--shadow)}}
.chart-box h3{{font-size:13px;font-weight:700;color:var(--text);margin-bottom:8px}}
.filter-bar{{display:flex;gap:8px;flex-wrap:wrap;align-items:center;margin-bottom:10px}}
.filter-bar label{{font-size:12px;color:var(--text-secondary);font-weight:500}}
.filter-btn,.tab-btn{{padding:5px 13px;border-radius:16px;border:1.5px solid var(--border);background:var(--card);font-size:12px;font-weight:500;color:var(--text-secondary);cursor:pointer;transition:all .15s;white-space:nowrap}}
.filter-btn:hover,.tab-btn:hover{{border-color:var(--primary-light);color:var(--primary)}}
.filter-btn.active,.tab-btn.active{{background:var(--primary);border-color:var(--primary);color:#fff}}
input[type=search]{{padding:6px 12px;border-radius:8px;border:1.5px solid var(--border);font-size:13px;outline:none;min-width:220px}}
input[type=search]:focus{{border-color:var(--primary-light)}}
table{{width:100%;border-collapse:collapse;font-size:12.5px}}
thead th{{position:sticky;top:0;background:#EFF6FF;color:var(--text);font-weight:600;padding:8px 10px;text-align:left;border-bottom:2px solid var(--border);white-space:nowrap;z-index:2}}
tbody td{{padding:7px 10px;border-bottom:1px solid #E8F0FE;vertical-align:middle}}
tbody tr{{cursor:pointer}}
tbody tr:hover{{background:#F5F9FF}}
tbody tr.active-row{{background:#EFF6FF}}
.num{{font-family:monospace;font-weight:600}}
.pos{{color:var(--success)}}.warn{{color:var(--accent)}}.zero{{color:var(--text-muted)}}
.badge{{display:inline-block;padding:1px 8px;border-radius:10px;font-size:11px;font-weight:500}}
.b-p0{{background:#FEE2E2;color:#DC2626}}.b-p1{{background:#FFEDD5;color:#EA580C}}
.b-p2{{background:#FEF9C3;color:#A16207}}.b-p3{{background:#DBEAFE;color:#1D4ED8}}
.b-skip{{background:#F1F5F9;color:#64748B}}.b-plan{{background:#EDE9FE;color:#6D28D9}}
.b-video{{background:#DBEAFE;color:#1D4ED8}}.b-tuwen{{background:#F3E8FF;color:#7C3AED}}.b-ai{{background:#EEF2FF;color:#6366F1}}
.traj-detail{{display:none;background:#F8FAFC;border-top:1px solid var(--border);padding:12px 16px}}
.traj-detail.show{{display:table-row}}
.traj-wrap{{display:flex;gap:2px;align-items:flex-end;height:70px;padding:6px 0}}
.traj-bar{{flex:1;min-width:6px;border-radius:2px 2px 0 0;background:#DBEAFE;position:relative}}
.traj-bar.has{{background:var(--primary-light)}}
.traj-dot{{position:absolute;top:-4px;left:50%;transform:translateX(-50%);width:8px;height:8px;border-radius:50%;background:var(--accent)}}
.traj-labels{{display:flex;justify-content:space-between;font-size:10px;color:var(--text-muted);margin-top:4px}}
.legend{{display:flex;gap:14px;font-size:11px;color:var(--text-secondary);margin:8px 0 4px;flex-wrap:wrap}}
.legend span{{display:inline-flex;align-items:center;gap:5px}}
.legend i{{display:inline-block;width:10px;height:10px;border-radius:2px}}
.count-info{{font-size:12px;color:var(--text-secondary);margin-bottom:8px}}
@media(max-width:900px){{.kpi-grid{{grid-template-columns:repeat(2,1fr)}}.charts{{grid-template-columns:1fr}}}}
</style>
</head>
<body>
<div class="header">
  <h1>素材生命周期分析</h1>
  <p>千川信息流 · 引导加微项目 · 07/21–10/08 共 78 天 · 口径：消耗>0=在投 · 深转=高潜成交>0 · 停投间隔≥2天才算真停</p>
</div>
<div class="wrap">

  <div class="kpi-grid">
    <div class="kpi"><div class="lbl">曾投放素材</div><div class="val">{n_life}</div><div class="sub">当前在投 {n_now} 个</div></div>
    <div class="kpi"><div class="lbl">总消耗</div><div class="val">¥{tot_spend}</div><div class="sub">Top30 素材占 {top30_pct}%</div></div>
    <div class="kpi"><div class="lbl">总高潜成交</div><div class="val">{tot_gq}</div><div class="sub">深转是核心验证指标</div></div>
    <div class="kpi"><div class="lbl">浅投素材（≤¥100）</div><div class="val">{low_budget_pct}%</div><div class="sub">试投一天即停的中位消耗 ¥{one_day_med}</div></div>
  </div>

  <div class="conclusion">
    <h2>核心结论：跑出率低，不全是素材的锅</h2>
    <p>① 验证预算太薄：{low_budget_pct}% 的素材一生总消耗 ≤ ¥100，{one_day_n} 个「试投一天即停」的素材中位消耗仅 ¥{one_day_med} —— 一天的投放预算还不如一杯水，转化不了不是素材差，是根本没给验证机会。</p>
    <p>② 流量高度集中：Top 30 素材吃掉 {top30_pct}% 的消耗和 {top30_gq_pct}% 的高潜，平台自己已经把量集中在少数素材上，长尾素材被浅试后就晾着。</p>
    <p>③ 计划给了量没到：最近一天有 <b>{n_plan_only}</b> 个视频素材挂着计划但消耗为 0 —— 这批是「给了计划没给量」的，素材质量嫌疑最小，优先排查出价/预算/账户。</p>
    <p>④ 能持续跑的素材只有 <b>{n_cont}</b> 个，其中图文占绝大多数；视频侧缺乏「稳定长跑」的样本，反而说明视频该收窄数量、集中预算打爆款。</p>
  </div>

  <div class="charts">
    <div class="chart-box"><h3>投放模式分布（{n_life} 个曾投素材）</h3><div style="height:260px"><canvas id="chRunMode"></canvas></div></div>
    <div class="chart-box"><h3>深转模式分布</h3><div style="height:260px"><canvas id="chGqMode"></canvas></div></div>
  </div>
  <div class="card"><h2>逐日活跃素材数 vs 总消耗</h2><div style="height:220px"><canvas id="chDaily"></canvas></div></div>

  <div class="card">
    <h2>看片清单（视频素材 · 哪些值得翻原视频）</h2>
    <div class="count-info">P0 深转消失/疑似停错（最值得逐条看片）→ P1 深转波动 → P2 花大钱零深转 → P3 浅投即停；「跳过」验证量太小看了也说明不了问题；「挂计划零消耗」是计划/出价问题，素材嫌疑最小，抽查对比即可。</div>
    <div class="filter-bar" id="watchTabs">
      <button class="tab-btn active" data-p="P0">P0 深转消失/疑似停错</button>
      <button class="tab-btn" data-p="P1">P1 深转波动</button>
      <button class="tab-btn" data-p="P2">P2 花钱多零深转</button>
      <button class="tab-btn" data-p="P3">P3 浅投即停</button>
      <button class="tab-btn" data-p="跳过">跳过（验证量不足）</button>
      <button class="tab-btn" data-p="plan">挂计划零消耗</button>
    </div>
    <input type="search" id="watchSearch" placeholder="搜索素材名 / 人 / 标签…">
    <div class="count-info" id="watchCount" style="margin-top:8px"></div>
    <div style="overflow-x:auto"><table id="watchTable">
      <thead><tr>
        <th>优先级</th><th>素材名称</th><th>人</th><th>标签</th><th>首投</th><th>末投</th><th>在投天数</th><th>总消耗</th><th>总转化</th><th>总高潜</th><th>深转模式</th><th>投放模式</th>
      </tr></thead>
      <tbody id="watchBody"></tbody>
    </table></div>
  </div>

  <div class="card">
    <h2>全部素材 · 生命周期明细</h2>
    <div class="filter-bar">
      <button class="filter-btn active" data-f="all">全部</button>
      <button class="filter-btn" data-f="持续在跑">持续在跑</button>
      <button class="filter-btn" data-f="波动投放中">波动投放中</button>
      <button class="filter-btn" data-f="停投后复投又停">停投复投</button>
      <button class="filter-btn" data-f="试投一天即停">试投一天</button>
      <button class="filter-btn" data-f="连续投放后停投">连投后停</button>
      <button class="filter-btn" data-f="近期刚停">近期刚停</button>
      <span style="flex:1"></span>
      <input type="search" id="lifeSearch" placeholder="搜索素材名…">
    </div>
    <div class="count-info" id="lifeCount"></div>
    <div style="overflow-x:auto"><table id="lifeTable">
      <thead><tr>
        <th>素材名称</th><th>类型</th><th>人</th><th>标签</th><th>首投</th><th>末投</th><th>在投</th><th>停投≥2天</th><th>总消耗</th><th>总转化</th><th>高潜</th><th>深转模式</th><th>投放模式</th>
      </tr></thead>
      <tbody id="lifeBody"></tbody>
    </table></div>
  </div>

</div>
<script>
const LIFE = {life_js};
const DAILY = {daily_js};
const WATCH = {watch_js};
const PLAN_ONLY = {plan_only_js};
const ALL_DATES = DAILY.map(x => x.d);

const MODE_COLORS = {{'P0':'#DC2626','P1':'#EA580C','P2':'#A16207','P3':'#1D4ED8','跳过':'#64748B','plan':'#6D28D9'}};
const TYPE_BADGE = m => m === '图文' ? 'b-tuwen' : (m === 'Ai' ? 'b-ai' : 'b-video');
const esc = s => String(s || '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
const fmtMoney = v => '¥' + Number(v).toLocaleString('zh', {{minimumFractionDigits:2, maximumFractionDigits:2}});

// ---------- 图表 ----------
const countBy = (arr, key) => {{
  const c = {{}}; arr.forEach(x => c[x[key]] = (c[x[key]] || 0) + 1); return c;
}};
const runModeCnt = countBy(LIFE, 'runMode');
const gqModeCnt = countBy(LIFE, 'gqMode');
const RUN_ORDER = ['持续在跑','波动投放中','近期刚停','连续投放后停投','停投后复投又停','试投一天即停'];
const GQ_ORDER = ['持续有深转','后来才有深转','深转时有时无','以前有深转现在没有','仅投一天(有深转)','从未有深转'];

new Chart(document.getElementById('chRunMode'), {{
  type: 'bar',
  data: {{ labels: RUN_ORDER,
    datasets: [{{ label: '素材数', data: RUN_ORDER.map(m => runModeCnt[m] || 0), backgroundColor: '#3B82F6', borderRadius: 4 }}] }},
  options: {{ indexAxis: 'y', plugins: {{ legend: {{ display: false }} }}, scales: {{ x: {{ beginAtZero: true }} }} }}
}});
new Chart(document.getElementById('chGqMode'), {{
  type: 'bar',
  data: {{ labels: GQ_ORDER,
    datasets: [{{ label: '素材数', data: GQ_ORDER.map(m => gqModeCnt[m] || 0), backgroundColor: '#D97706', borderRadius: 4 }}] }},
  options: {{ indexAxis: 'y', plugins: {{ legend: {{ display: false }} }}, scales: {{ x: {{ beginAtZero: true }} }} }}
}});
new Chart(document.getElementById('chDaily'), {{
  type: 'bar',
  data: {{
    labels: ALL_DATES,
    datasets: [
      {{ label: '活跃素材数', data: DAILY.map(d => d.act), yAxisID: 'y', backgroundColor: 'rgba(59,130,246,.5)', borderRadius: 1 }},
      {{ label: '总消耗(¥)', data: DAILY.map(d => d.spend), yAxisID: 'y1', type: 'line', borderColor: '#D97706', backgroundColor: 'rgba(217,119,6,.1)', fill: true, tension: .3, pointRadius: 0 }}
    ]
  }},
  options: {{ scales: {{ x: {{ ticks: {{ maxTicksLimit: 20, font: {{ size: 10 }} }} }}, y: {{ beginAtZero: true, title: {{ display: true, text: '活跃素材数', font: {{ size: 10 }} }} }}, y1: {{ beginAtZero: true, position: 'right', grid: {{ drawOnChartArea: false }}, title: {{ display: true, text: '消耗(¥)', font: {{ size: 10 }} }} }} }} }}
}});

// ---------- 看片清单 ----------
let watchPri = 'P0', watchKw = '';
function renderWatch() {{
  const rows = watchPri === 'plan' ? PLAN_ONLY
    : WATCH.filter(w => w['看片优先级'] === watchPri);
  const kw = watchKw.trim();
  const filtered = rows.filter(w => {{
    if (!kw) return true;
    const blob = ((w.name || w['素材名称'] || '') + ' ' + (w['人'] || '') + ' ' + (w['标签'] || '')).toLowerCase();
    return blob.includes(kw.toLowerCase());
  }});
  document.getElementById('watchCount').textContent = watchPri === 'plan'
    ? `挂计划但消耗为 0 的视频：${{filtered.length}} 个（素材嫌疑最小，抽查与爆款对比）`
    : `共 ${{filtered.length}} 个（按总消耗降序）`;
  const body = document.getElementById('watchBody');
  if (!filtered.length) {{ body.innerHTML = '<tr><td colspan="12" style="text-align:center;color:#94A3B8;padding:16px">无数据</td></tr>'; return; }}
  body.innerHTML = filtered.map(w => {{
    if (watchPri === 'plan') {{
      return `<tr><td><span class="badge b-plan">挂计划</span></td>
        <td>${{esc(w.name)}}</td><td>—</td><td>—</td><td>—</td><td>—</td>
        <td>—</td><td>¥0</td><td>0</td><td>0</td>
        <td><span class="zero">零消耗</span></td>
        <td>${{w.units}} 个计划</td></tr>`;
    }}
    return `<tr>
      <td><span class="badge b-${{watchPri.toLowerCase()}}">${{watchPri}}</span></td>
      <td style="max-width:260px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="${{esc(w['素材名称'])}}">${{esc(w['素材名称'])}}</td>
      <td>${{esc(w['人'])}}</td><td>${{esc(w['标签'] || '—')}}</td>
      <td>${{w['首投']}}</td><td>${{w['末投']}}</td><td>${{w['在投天数']}}</td>
      <td class="num">${{fmtMoney(w['总消耗'])}}</td>
      <td class="num ${{Number(w['总转化'])>0?'pos':'zero'}}">${{w['总转化']}}</td>
      <td class="num ${{Number(w['总高潜'])>0?'warn':'zero'}}">${{w['总高潜']}}</td>
      <td>${{esc(w['深转模式'])}}</td><td>${{esc(w['投放模式'])}}</td>
    </tr>`;
  }}).join('');
}}
document.getElementById('watchTabs').addEventListener('click', e => {{
  const btn = e.target.closest('.tab-btn'); if (!btn) return;
  document.querySelectorAll('#watchTabs .tab-btn').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  watchPri = btn.dataset.p;
  renderWatch();
}});
document.getElementById('watchSearch').addEventListener('input', e => {{ watchKw = e.target.value; renderWatch(); }});
renderWatch();

// ---------- 全部素材 ----------
let lifeMode = 'all', lifeKw = '';
function renderLife() {{
  const filtered = LIFE.filter(m => {{
    if (lifeMode !== 'all' && m.runMode !== lifeMode) return false;
    if (lifeKw && !m.name.toLowerCase().includes(lifeKw.toLowerCase()) && !(m.person||'').toLowerCase().includes(lifeKw.toLowerCase())) return false;
    return true;
  }}).sort((a,b) => b.spend - a.spend);
  document.getElementById('lifeCount').textContent = `显示 ${{filtered.length}} / ${{LIFE.length}} 个素材（点击行展开每日轨迹）`;
  const body = document.getElementById('lifeBody');
  if (!filtered.length) {{ body.innerHTML = '<tr><td colspan="13" style="text-align:center;color:#94A3B8;padding:16px">无数据</td></tr>'; return; }}
  body.innerHTML = filtered.map((m, i) => {{
    const gqCls = m.gq > 0 ? 'warn' : 'zero';
    const gqBadge = m.gqLost ? ' <span class="badge b-p0">深转消失</span>' : '';
    const bars = m.traj.map((t, j) => {{
      const active = t.s > 0;
      const hasGq = t.g > 0;
      return `<div class="traj-bar ${{active?'has':''}}" title="${{t.d}} ¥${{t.s}}${{hasGq?' · 深转'+t.g:''}}" style="height:${{active ? Math.max(8, Math.min(100, t.s/50)) : 3}}%">${{hasGq?'<span class="traj-dot"></span>':''}}</div>`;
    }}).join('');
    const lbls = m.traj.length > 40
      ? `<span>${{m.traj[0].d}}</span><span>${{m.traj[Math.floor(m.traj.length/2)].d}}</span><span>${{m.traj[m.traj.length-1].d}}</span>`
      : m.traj.map(t => `<span>${{t.d.slice(3)}}</span>`).join('');
    return `<tr class="life-row" data-i="${{i}}">
      <td style="max-width:240px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="${{esc(m.name)}}">${{esc(m.name)}}</td>
      <td><span class="badge ${{TYPE_BADGE(m.type)}}">${{m.type}}</span></td>
      <td>${{esc(m.person)}}</td><td>${{esc(m.tag || '—')}}</td>
      <td>${{m.first}}</td><td>${{m.last}}</td><td>${{m.activeDays}}</td>
      <td class="num ${{m.stops>0?'warn':''}}">${{m.stops}}</td>
      <td class="num">${{fmtMoney(m.spend)}}</td>
      <td class="num ${{m.conv>0?'pos':'zero'}}">${{m.conv}}</td>
      <td class="num ${{gqCls}}">${{m.gq}}${{gqBadge}}</td>
      <td>${{esc(m.gqMode)}}</td><td>${{esc(m.runMode)}}</td>
    </tr>
    <tr class="traj-detail" id="traj-${{i}}"><td colspan="13">
      <div class="legend"><span><i style="background:#DBEAFE"></i>未投</span><span><i style="background:#3B82F6"></i>在投（消耗&gt;0）</span><span><i style="background:#D97706"></i>深转日（高潜&gt;0）</span></div>
      <div class="traj-wrap">${{bars}}</div>
      <div class="traj-labels">${{lbls}}</div>
    </td></tr>`;
  }}).join('');
  body.querySelectorAll('.life-row').forEach(tr => {{
    tr.onclick = () => {{
      const det = document.getElementById('traj-' + tr.dataset.i);
      const wasOpen = det.classList.contains('show');
      body.querySelectorAll('.traj-detail').forEach(d => d.classList.remove('show'));
      body.querySelectorAll('.life-row').forEach(r => r.classList.remove('active-row'));
      if (!wasOpen) {{ det.classList.add('show'); tr.classList.add('active-row'); }}
    }};
  }});
}}
document.querySelectorAll('.filter-bar .filter-btn').forEach(btn => {{
  btn.onclick = () => {{
    document.querySelectorAll('.filter-bar .filter-btn').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    lifeMode = btn.dataset.f;
    renderLife();
  }};
}});
document.getElementById('lifeSearch').addEventListener('input', e => {{ lifeKw = e.target.value; renderLife(); }});
renderLife();
</script>
</body>
</html>
"""


if __name__ == '__main__':
    main()
