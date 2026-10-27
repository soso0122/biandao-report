#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
代理商数据分析报告生成 - 0716版（新格式，与0710 HTML一致）
用法：python3 scripts/generate_agent_0716_new.py
"""

import csv
import json
from collections import defaultdict
from datetime import datetime

def tag_prod(prod_name):
    n = prod_name or ''
    if '李博' in n or '物理' in n:
        return '9元李博'
    if '199' in n or '双科' in n:
        return '199双科'
    return n or '其他'

PROD_ORDER = ['9元李博', '199双科']

INPUT_FILE = 'data/【周报】代理素材报告0724.csv'
OUTPUT_FILE = 'reports/代理商数据分析_0724.html'
REPORT_DATE = '2026.07.24'
DATA_DATE = '2026/07/24'
NEW_WEEK_START = datetime(2026, 7, 17)
NEW_WEEK_END = datetime(2026, 7, 23)
NEW_WEEK_LABEL = '7月17日 - 7月23日'

AVATAR_MAP = {'荔枝': 'av-0', '申坤': 'av-2', '玄武': 'av-4', '十人': 'av-3', '启航': 'av-5', '自投放': 'av-1'}
CHART_COLORS = ['#D97706', '#1D4ED8', '#7C3AED', '#065F46', '#0E7490']
EXCLUDE_AGENTS = set()  # 不排除任何代理商，自投放与其他代理商并列
AGENT_EXCLUDE_FROM_MAIN = set()  # 不分离


def fmt_consume(v):
    if v >= 10000:
        return f'¥{v/10000:.1f}万'
    return f'¥{v:,.0f}'


def read_and_aggregate(file_path):
    rows = []
    with open(file_path, encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)

    # aggregate by (代理商, 签名) → unique material per agent
    mat_key_stats = defaultdict(lambda: {
        '素材名称': '', '代理商': '', '签名': '', '链接': '',
        '投放产品': '', '首次消耗时间': '', '已上线投放天数': 0,
        '消耗': 0.0, 'GMV': 0.0, '订单': 0,
    })

    for row in rows:
        agent = row.get('代理商', '').strip()
        if not agent:
            continue

        sig = row.get('签名', '').strip()
        mat_name = row.get('素材名称', '').strip()
        key = (agent, sig or mat_name)

        s = mat_key_stats[key]
        s['素材名称'] = mat_name
        s['代理商'] = agent
        s['签名'] = sig
        if not s['链接']:
            s['链接'] = row.get('素材预览', '').strip()
        if not s['投放产品']:
            s['投放产品'] = row.get('投放产品', '').strip()

        first_time = row.get('首次消耗时间', '').strip()
        if first_time and first_time != '-' and not s['首次消耗时间']:
            s['首次消耗时间'] = first_time

        days_str = row.get('已上线投放天数', '').strip()
        if days_str and days_str not in ('', '-') and not s['已上线投放天数']:
            try:
                s['已上线投放天数'] = int(float(days_str))
            except ValueError:
                pass

        try:
            s['消耗'] += float(row.get('消耗', 0) or 0)
            s['GMV'] += float(row.get('成交GMV', 0) or 0)
            s['订单'] += int(float(row.get('成交单量', 0) or 0))
        except (ValueError, TypeError):
            pass

    return list(mat_key_stats.values())


def build_agent_stats(materials):
    agent_stats = defaultdict(lambda: {
        '总消耗': 0.0, '总GMV': 0.0, '总订单': 0,
        '有消耗素材数': 0, '有成交素材数': 0,
        '总投放天数': 0, '有天数素材数': 0,
        '素材列表': [],
    })
    agent_product_stats = defaultdict(lambda: defaultdict(lambda: {
        '消耗': 0.0, 'GMV': 0.0, '订单': 0, '素材': set()
    }))

    for m in materials:
        agent = m['代理商']
        s = agent_stats[agent]
        s['总消耗'] += m['消耗']
        s['总GMV'] += m['GMV']
        s['总订单'] += m['订单']
        if m['消耗'] > 0:
            s['有消耗素材数'] += 1
        if m['GMV'] > 0:
            s['有成交素材数'] += 1
        if m['已上线投放天数'] > 0:
            s['总投放天数'] += m['已上线投放天数']
            s['有天数素材数'] += 1
        s['素材列表'].append(m)

        prod = m['投放产品']
        if prod:
            ps = agent_product_stats[agent][prod]
            ps['消耗'] += m['消耗']
            ps['GMV'] += m['GMV']
            ps['订单'] += m['订单']
            if m['消耗'] > 0:
                ps['素材'].add(m['素材名称'])

    return agent_stats, agent_product_stats


def lifecycle_bucket(days):
    if days <= 7:
        return '1-7天'
    elif days <= 14:
        return '8-14天'
    elif days <= 30:
        return '15-30天'
    else:
        return '30天以上'


def build_lifecycle(materials):
    buckets = {'1-7天': [], '8-14天': [], '15-30天': [], '30天以上': []}
    for m in materials:
        if m['消耗'] <= 0:
            continue
        days = m['已上线投放天数']
        if days <= 0:
            continue
        bk = lifecycle_bucket(days)
        buckets[bk].append({
            '素材名称': m['素材名称'],
            '代理商': m['代理商'],
            '总消耗': round(m['消耗'], 2),
            '总单量': m['订单'],
            '首次消耗时间': m['首次消耗时间'],
            '投放天数': days,
            '链接': m['链接'],
        })
    for bk in buckets:
        buckets[bk].sort(key=lambda x: -x['总消耗'])
    return buckets


def build_new_week(materials):
    result = []
    for m in materials:
        ft = m['首次消耗时间']
        if not ft or ft == '-':
            continue
        try:
            dt = datetime.strptime(ft.strip(), '%Y/%m/%d')
        except ValueError:
            try:
                dt = datetime.strptime(ft.strip(), '%Y-%m-%d')
            except ValueError:
                continue
        if NEW_WEEK_START <= dt <= NEW_WEEK_END and m['消耗'] > 0:
            result.append({
                '素材名称': m['素材名称'],
                '代理商': m['代理商'],
                '首消': ft,
                '消耗': m['消耗'],
                '订单': m['订单'],
                '链接': m['链接'],
            })
    result.sort(key=lambda x: -x['消耗'])
    return result


def generate_html(materials, agent_stats, agent_product_stats):
    agents_sorted = sorted(agent_stats.keys(), key=lambda a: -agent_stats[a]['总消耗'])
    total_consume = sum(s['总消耗'] for s in agent_stats.values())
    total_gmv = sum(s['总GMV'] for s in agent_stats.values())
    total_orders = sum(s['总订单'] for s in agent_stats.values())
    total_with_consume = sum(s['有消耗素材数'] for s in agent_stats.values())

    lifecycle_buckets = build_lifecycle(materials)
    new_week = build_new_week(materials)
    total_lifecycle = sum(len(v) for v in lifecycle_buckets.values())

    all_products = sorted(set(
        p for a in agents_sorted for p in agent_product_stats[a].keys()
    ))

    # ── Sidebar HTML
    sidebar_btns = ''
    for i, agent in enumerate(agents_sorted):
        s = agent_stats[agent]
        av = AVATAR_MAP.get(agent, f'av-{i%6}')
        sidebar_btns += f'''    <button class="dir-btn" onclick="selectAgent('{agent}',this)" data-agent="{agent}">
      <div class="dir-avatar {av}">{agent[0]}</div>
      <div class="dir-info">
        <div class="dir-name">{agent}</div>
        <div class="dir-stat">{fmt_consume(s["总消耗"])} · {s["总订单"]}单</div>
      </div>
    </button>\n'''

    # ── Lifecycle buckets HTML
    bk_colors = ['#0D9488', '#3B82F6', '#D97706', '#E11D48']
    bk_keys = ['1-7天', '8-14天', '15-30天', '30天以上']
    bk_html = ''
    for j, bk in enumerate(bk_keys):
        cnt = len(lifecycle_buckets[bk])
        pct = round(cnt / total_lifecycle * 100) if total_lifecycle else 0
        bk_html += f'            <div class="bk-pill" onclick="selectBucket({j})"><div class="bk-name">{bk}</div><div class="bk-cnt" style="color:{bk_colors[j]}">{cnt}</div><div class="bk-pct">占有消耗素材 {pct}%</div></div>\n'

    # ── New week HTML
    new_week_html = ''
    for item in new_week:
        lk = f'<a href="{item["链接"]}" target="_blank" class="nw-link">▶</a>' if item['链接'] else ''
        new_week_html += f'<div class="nw-item"><span class="nw-name" title="{item["素材名称"]}">{item["素材名称"]}</span><span class="nw-meta">{item["代理商"]} | 首消 {item["首消"]} | ¥{item["消耗"]:,.0f} | {item["订单"]}单</span>{lk}</div>\n'

    # ── Product filter bar HTML
    prod_filter_html = f'  <button class="pf-btn pf-all active" onclick="filterByProduct(\'all\',this)">全部</button>\n'
    for p in all_products:
        prod_filter_html += f'  <button class="pf-btn" onclick="filterByProduct(\'{p}\',this)">{p}</button>\n'

    # ── Compare table body HTML
    compare_rows = ''
    for agent in agents_sorted:
        s = agent_stats[agent]
        avg_days = round(s['总投放天数'] / s['有天数素材数'], 1) if s['有天数素材数'] else 0
        compare_rows += f'''                    <tr>
                        <td><strong>{agent}</strong></td>
                        <td style="text-align:right">¥{s["总消耗"]:,.2f}</td>
                        <td style="text-align:right">¥{s["总GMV"]:,.2f}</td>
                        <td style="text-align:right">{s["总订单"]}</td>
                        <td style="text-align:right">{s["有消耗素材数"]}</td>
                        <td style="text-align:right">{s["有成交素材数"]}</td>
                        <td style="text-align:right">{avg_days} 天</td>
                    </tr>\n'''

    # ── JS: agentPanelData
    panel_data_lines = []
    for i, agent in enumerate(agents_sorted):
        s = agent_stats[agent]
        pct_val = round(s['总消耗'] / total_consume * 100, 1) if total_consume else 0
        rank = f'#{i+1} by 消耗'
        top3 = sorted(s['素材列表'], key=lambda m: -m['GMV'])[:3]
        top3_js = []
        for t in top3:
            url = t['链接'].replace("'", "\\'")
            name_t = t['素材名称'].replace("'", "\\'")
            t_cost = t['消耗']
            t_order = t['订单']
            top3_js.append(
                f"      {{name:'{name_t}',meta:'¥{t_cost:,.0f} · {t_order}单',url:'{url}'}}"
            )
        top3_str = ',\n'.join(top3_js)
        # 按产品分组 top3
        prod_top3_parts = []
        for ptag in PROD_ORDER:
            items = [m for m in s['素材列表'] if tag_prod(m.get('投放产品','')) == ptag and m['GMV'] > 0]
            items_sorted = sorted(items, key=lambda m: -m['GMV'])[:3]
            items_js = json.dumps([
                {'name': m['素材名称'], 'meta': '¥{:,.0f} · {}单'.format(m['消耗'], m['订单']), 'url': m['链接']}
                for m in items_sorted
            ], ensure_ascii=False)
            prod_top3_parts.append(f'"{ptag}":{items_js}')
        prod_top3_str = '{' + ','.join(prod_top3_parts) + '}'
        tc = round(s['总消耗'], 0)
        tg = round(s['总GMV'], 0)
        to = s['总订单']
        tm = s['有消耗素材数']
        panel_data_lines.append(
            f"  '{agent}': {{rank:'{rank}',consume:'¥{tc:,.0f}',gmv:'¥{tg:,.0f}',"
            f"orders:'{to}',mat:'{tm}',pct:'{pct_val}%',pctVal:{pct_val},\n"
            f"    top3:[\n{top3_str}\n    ],prodTop3:{prod_top3_str}}}"
        )
    agent_panel_data_js = 'const agentPanelData = {\n' + ',\n'.join(panel_data_lines) + '\n};\n'

    # ── JS: lifecycleBuckets
    lc_js = 'const lifecycleBuckets = ' + json.dumps(
        lifecycle_buckets, ensure_ascii=False
    ) + ';\n'

    # ── JS: chart data
    agents_js = 'const agents = ' + json.dumps(agents_sorted, ensure_ascii=False) + ';\n'
    all_product_data_js = 'const allProductData = {\n'
    all_product_data_js += f'consume:   {json.dumps([round(agent_stats[a]["总消耗"],2) for a in agents_sorted])},\n'
    all_product_data_js += f'gmv:       {json.dumps([round(agent_stats[a]["总GMV"],2) for a in agents_sorted])},\n'
    all_product_data_js += f'orders:    {json.dumps([agent_stats[a]["总订单"] for a in agents_sorted])},\n'
    all_product_data_js += f'materials: {json.dumps([agent_stats[a]["有消耗素材数"] for a in agents_sorted])}\n'
    all_product_data_js += '};\n'

    prod_data_dict = {}
    for p in all_products:
        prod_data_dict[p] = {
            'consume': [round(agent_product_stats[a][p]['消耗'], 2) for a in agents_sorted],
            'gmv': [round(agent_product_stats[a][p]['GMV'], 2) for a in agents_sorted],
            'orders': [agent_product_stats[a][p]['订单'] for a in agents_sorted],
            'materials': [len(agent_product_stats[a][p]['素材']) for a in agents_sorted],
        }
    prod_data_js = 'const productData = ' + json.dumps(prod_data_dict, ensure_ascii=False) + ';\n'

    # ── JS: materialDetails (top 20 per agent)
    mat_details = {}
    for agent in agents_sorted:
        top20 = sorted(agent_stats[agent]['素材列表'], key=lambda m: -m['消耗'])[:20]
        mat_details[agent] = [{
            '素材名称': m['素材名称'],
            '总消耗': round(m['消耗'], 2),
            '总GMV': round(m['GMV'], 2),
            '总订单': m['订单'],
            '投放产品': m['投放产品'],
            '链接': m['链接'],
        } for m in top20]
    mat_details_js = 'const materialDetails = ' + json.dumps(mat_details, ensure_ascii=False) + ';\n'

    avatar_map_js = "const AVATAR_MAP = {" + ",".join(f"'{k}':'{v}'" for k, v in AVATAR_MAP.items()) + "};\n"

    # ── Assemble HTML
    css = get_css()
    html_body = get_html_body(
        total_consume, total_gmv, total_orders, total_with_consume,
        len(agents_sorted), sidebar_btns,
        total_lifecycle, bk_html, new_week, new_week_html,
        prod_filter_html, compare_rows
    )
    js_static = get_js_static()

    return f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>代理商数据分析 · {REPORT_DATE}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<style>
{css}
</style>
</head>
<body>
<div class="wrap">
{html_body}
</div>
<div class="modal-bg" id="modalBg">
  <div class="modal-box">
    <button class="modal-close" onclick="closeModal()">✕</button>
    <div id="modalContent"></div>
  </div>
</div>
<script>
Chart.defaults.color = '#64748B';
Chart.defaults.borderColor = 'rgba(0,0,0,0.06)';
{avatar_map_js}
{agent_panel_data_js}
{lc_js}
{agents_js}
{all_product_data_js}
{prod_data_js}
{mat_details_js}
{js_static}
</script>
</body>
</html>'''


def build_self_tab_html(total_consume, total_gmv, total_orders, total_mat,
                        total_lc, bk_html,
                        new_week, new_week_html, new_week_pct,
                        prod_filter_html, compare_rows,
                        top3):
    new_week_pct_label = new_week_pct
    top3_html = ''
    for i, m in enumerate(top3):
        rc = ['r1','r2','r3'][i]
        lk = f'<a href="{m["链接"]}" target="_blank" class="mat-link">▶ 预览</a>' if m['链接'] else ''
        top3_html += f'<div class="top-item-row"><span class="top-rank-badge {rc}">{i+1}</span><div class="top-item-body"><div class="top-item-name" title="{m["素材名称"]}">{m["素材名称"]}</div><div class="top-item-meta">¥{m["消耗"]:,.0f} · {m["订单"]}单 {lk}</div></div></div>\n'

    return f'''<div class="topbar">
  <div class="topbar-left">
    <div class="topbar-logo" style="background:linear-gradient(135deg,#0E7490,#22D3EE)">自</div>
    <div>
      <div class="topbar-title">自投放数据分析</div>
      <div class="topbar-sub">SELF DELIVERY REPORT · {REPORT_DATE}</div>
    </div>
  </div>
  <span class="badge">数据截至 {DATA_DATE}</span>
</div>

<div class="kpi-row">
  <div class="kpi-card"><div class="kpi-label">总消耗</div><div class="kpi-val">¥{total_consume:,.0f}</div></div>
  <div class="kpi-card"><div class="kpi-label">总 GMV</div><div class="kpi-val">¥{total_gmv:,.0f}</div></div>
  <div class="kpi-card"><div class="kpi-label">总订单</div><div class="kpi-val">{total_orders}</div></div>
  <div class="kpi-card"><div class="kpi-label">有消耗素材</div><div class="kpi-val">{total_mat}</div></div>
</div>

<div class="collapsible">
  <div class="coll-head" onclick="toggleColl(this)">
    <div class="coll-title">素材生命周期 <span class="coll-badge" style="background:#DCFCE7;color:#166534">{total_lc} 条</span></div>
    <span class="coll-arrow">▼</span>
  </div>
  <div class="coll-body">
    <div class="lc-buckets">
{bk_html}    </div>
    <div class="lc-detail-row">
      <div class="lc-chart-wrap"><canvas id="selfLifecycleChart"></canvas></div>
      <div class="lc-mat-list">
        <div class="lc-mat-title" id="selfBucketDetailTitle">← 点击分桶查看素材明细</div>
        <div class="mat-scroll" id="selfBucketMaterialList"></div>
      </div>
    </div>
    <div class="new-week-box">
      <div class="new-week-title-row">
        <span class="new-week-title-text">本周新起量素材</span>
        <span class="new-week-badge">{len(new_week)} 条</span>
      </div>
      <div class="new-week-sub">首次消耗时间在 {NEW_WEEK_LABEL}（占有消耗素材 {new_week_pct_label}%）</div>
      <div class="new-week-list">{new_week_html}</div>
    </div>
  </div>
</div>

<div class="sec-label" style="margin-top:28px">产品分布</div>
<div id="selfProdFilterBar" style="display:flex;gap:6px;flex-wrap:wrap;margin-bottom:16px">
{prod_filter_html}</div>

<div class="sec-label">成交 TOP 3</div>
<div class="collapsible" style="margin-bottom:20px">
  <div class="coll-head" onclick="toggleColl(this)">
    <div class="coll-title">TOP 3 素材</div>
    <span class="coll-arrow">▼</span>
  </div>
  <div class="coll-body">
    <div class="top-list">{top3_html}</div>
    <button class="detail-btn" onclick="showSelfDetails()">查看消耗 TOP 20 →</button>
  </div>
</div>

<div class="sec-label">详细数据</div>
<div class="tbl-wrap"><div class="tbl-scroll">
  <table style="table-layout:fixed;width:100%">
    <colgroup>
      <col style="width:100px"><col style="width:130px"><col style="width:120px">
      <col style="width:90px"><col style="width:110px"><col style="width:110px"><col style="width:120px">
    </colgroup>
    <thead><tr>
      <th>账户</th><th style="text-align:right">总消耗</th><th style="text-align:right">总GMV</th>
      <th style="text-align:right">总订单</th><th style="text-align:right">有消耗素材</th>
      <th style="text-align:right">有成交素材</th><th style="text-align:right">平均投放天数</th>
    </tr></thead>
    <tbody id="selfCompareTableBody">{compare_rows}</tbody>
  </table>
</div></div>
<div class="footer">Generated {datetime.now().strftime("%Y-%m-%d")}</div>'''


def get_css():
    return """:root{--bg:#F1F5F9;--surface:#FFFFFF;--surface2:#F8FAFC;--border:#E2E8F0;--border2:#CBD5E1;--ink:#0F172A;--ink2:#334155;--muted:#64748B;--dim:#94A3B8;--blue:#1E40AF;--blue-l:#3B82F6;--sky:#0EA5E9;--amber:#D97706;--amber-l:#F59E0B;--teal:#0D9488;--font:'Plus Jakarta Sans',sans-serif;--mono:'JetBrains Mono',monospace;--r-sm:8px;--r-md:12px;--r-lg:16px}
*{margin:0;padding:0;box-sizing:border-box}html{scroll-behavior:smooth}body{font-family:var(--font);background:var(--bg);color:var(--ink);min-height:100vh}
.wrap{max-width:1440px;margin:0 auto;padding:32px 24px 80px}
.topbar{display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:12px;background:var(--surface);border:1px solid var(--border);border-radius:var(--r-lg);padding:20px 28px;margin-bottom:24px}
.topbar-left{display:flex;align-items:center;gap:16px}
.topbar-logo{width:40px;height:40px;border-radius:10px;background:linear-gradient(135deg,#D97706,#F59E0B);display:flex;align-items:center;justify-content:center;font-family:var(--mono);font-size:14px;font-weight:500;color:#fff;flex-shrink:0}
.topbar-title{font-size:18px;font-weight:800;color:var(--ink);letter-spacing:-0.5px}
.topbar-sub{font-family:var(--mono);font-size:11px;color:var(--muted);margin-top:2px}
.badge{font-family:var(--mono);font-size:10px;letter-spacing:0.5px;padding:5px 12px;border-radius:20px;border:1px solid;white-space:nowrap;background:#FEF3C7;color:#92400E;border-color:#FDE68A}
.kpi-row{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:24px}
@media(max-width:768px){.kpi-row{grid-template-columns:repeat(2,1fr)}}
.kpi-card{background:var(--surface);border:1px solid var(--border);border-radius:var(--r-md);padding:16px 18px;position:relative;overflow:hidden;transition:box-shadow .15s,transform .15s}
.kpi-card:hover{box-shadow:0 4px 16px rgba(0,0,0,.07);transform:translateY(-1px)}
.kpi-card::before{content:'';position:absolute;top:0;left:0;right:0;height:3px;background:linear-gradient(90deg,var(--amber),var(--amber-l))}
.kpi-label{font-family:var(--mono);font-size:9px;letter-spacing:1px;text-transform:uppercase;color:var(--muted);margin-bottom:6px}
.kpi-val{font-family:var(--mono);font-size:20px;font-weight:500;line-height:1;color:var(--amber)}
.main-layout{display:grid;grid-template-columns:220px 1fr;gap:20px;align-items:start}
@media(max-width:900px){.main-layout{grid-template-columns:1fr}}
.dir-sidebar{background:var(--surface);border:1px solid var(--border);border-radius:var(--r-lg);overflow:hidden;position:sticky;top:24px}
.dir-sidebar-head{padding:16px 18px 12px;border-bottom:1px solid var(--border);font-family:var(--mono);font-size:10px;letter-spacing:2px;text-transform:uppercase;color:var(--muted)}
.dir-btn{display:flex;align-items:center;gap:10px;width:100%;padding:13px 18px;border:none;background:none;cursor:pointer;text-align:left;transition:background .15s;border-bottom:1px solid var(--border);position:relative}
.dir-btn:last-child{border-bottom:none}
.dir-btn:hover{background:var(--surface2)}
.dir-btn.active{background:#FEF9EE}
.dir-btn.active::before{content:'';position:absolute;left:0;top:0;bottom:0;width:3px;background:var(--amber);border-radius:0 2px 2px 0}
.dir-avatar{width:32px;height:32px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:13px;font-weight:700;flex-shrink:0}
.dir-info{flex:1;min-width:0}
.dir-name{font-size:14px;font-weight:600;color:var(--ink);line-height:1.2}
.dir-stat{font-family:var(--mono);font-size:10px;color:var(--muted);margin-top:2px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.dir-btn.active .dir-name{color:var(--amber)}
.sec-label{font-family:var(--mono);font-size:10px;letter-spacing:2px;text-transform:uppercase;color:var(--muted);margin:28px 0 14px;display:flex;align-items:center;gap:10px}
.sec-label::after{content:'';flex:1;height:1px;background:var(--border)}
.collapsible{background:var(--surface);border:1px solid var(--border);border-radius:var(--r-lg);overflow:hidden;margin-bottom:16px}
.coll-head{display:flex;align-items:center;justify-content:space-between;padding:16px 20px;cursor:pointer;user-select:none;transition:background .15s}
.coll-head:hover{background:var(--surface2)}
.coll-title{font-size:14px;font-weight:700;color:var(--ink);display:flex;align-items:center;gap:8px}
.coll-badge{font-family:var(--mono);font-size:9px;letter-spacing:1px;padding:2px 8px;border-radius:10px}
.coll-arrow{font-size:12px;color:var(--muted);transition:transform .2s}
.coll-arrow.open{transform:rotate(180deg)}
.coll-body{padding:0 20px 20px;display:none}
.coll-body.open{display:block}
.dir-panel{background:var(--surface);border:1px solid var(--border);border-radius:var(--r-lg);margin-bottom:20px;overflow:hidden}
.dir-panel-head{display:flex;align-items:center;gap:16px;padding:20px 24px;border-bottom:1px solid var(--border);background:linear-gradient(135deg,#FFFBEB,var(--surface))}
.dir-panel-avatar{width:52px;height:52px;border-radius:14px;display:flex;align-items:center;justify-content:center;font-size:20px;font-weight:800;flex-shrink:0;color:#fff}
.dir-panel-name{font-size:22px;font-weight:800;color:var(--ink);letter-spacing:-0.5px}
.dir-panel-sub{font-family:var(--mono);font-size:11px;color:var(--muted);margin-top:3px}
.dir-panel-body{padding:20px 24px}
.panel-metrics{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin-bottom:16px}
@media(max-width:700px){.panel-metrics{grid-template-columns:repeat(2,1fr)}}
.pm-card{background:var(--surface2);border:1px solid var(--border);border-radius:var(--r-sm);padding:14px 16px}
.pm-label{font-family:var(--mono);font-size:9px;letter-spacing:1px;text-transform:uppercase;color:var(--muted);margin-bottom:6px}
.pm-val{font-family:var(--mono);font-size:18px;font-weight:500;color:var(--ink)}
.pm-val.amber{color:var(--amber)}
.consume-bar-section{margin-bottom:16px}
.consume-bar-label{display:flex;justify-content:space-between;font-family:var(--mono);font-size:10px;color:var(--muted);margin-bottom:5px}
.consume-bar-bg{background:var(--surface2);border-radius:4px;height:8px;overflow:hidden}
.consume-bar-fill{height:100%;background:linear-gradient(90deg,var(--amber),var(--amber-l));border-radius:4px;transition:width .5s ease}
.top-list{}
.top-item-row{display:flex;align-items:flex-start;gap:10px;padding:8px 0;border-bottom:1px solid var(--border)}
.top-item-row:last-child{border-bottom:none}
.top-rank-badge{flex-shrink:0;width:22px;height:22px;border-radius:6px;display:flex;align-items:center;justify-content:center;font-family:var(--mono);font-size:11px;font-weight:600}
.r1{background:#FEF3C7;color:#92400E}.r2{background:#F1F5F9;color:#475569}.r3{background:#F1F5F9;color:#475569}
.top-item-body{flex:1;min-width:0}
.top-item-name{font-size:11px;font-weight:500;color:var(--ink);overflow:hidden;text-overflow:ellipsis;white-space:nowrap;margin-bottom:2px}
.top-item-meta{font-family:var(--mono);font-size:10px;color:var(--muted)}
.mat-link{color:var(--blue-l);text-decoration:none;font-size:10px;font-family:var(--mono);margin-left:4px}
.mat-link:hover{text-decoration:underline}
.detail-btn{display:inline-flex;align-items:center;gap:6px;margin-top:14px;padding:8px 16px;border-radius:8px;border:1px solid var(--border2);background:var(--surface);font-family:var(--font);font-size:12px;font-weight:600;color:var(--amber);cursor:pointer;transition:all .15s}
.detail-btn:hover{background:var(--amber);color:#fff;border-color:var(--amber)}
.lc-buckets{display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin-bottom:16px}
@media(max-width:640px){.lc-buckets{grid-template-columns:repeat(2,1fr)}}
.bk-pill{background:var(--surface2);border:1px solid var(--border);border-radius:var(--r-sm);padding:14px;cursor:pointer;transition:all .15s}
.bk-pill:hover{border-color:var(--border2);box-shadow:0 2px 8px rgba(0,0,0,.06)}
.bk-pill.active{border-color:var(--amber-l);background:#FFFBEB}
.bk-name{font-family:var(--mono);font-size:10px;letter-spacing:1px;color:var(--muted);margin-bottom:6px}
.bk-cnt{font-family:var(--mono);font-size:24px;font-weight:500;line-height:1;margin-bottom:3px}
.bk-pct{font-size:10px;color:var(--dim);font-family:var(--mono)}
.lc-detail-row{display:flex;gap:16px;align-items:flex-start;margin-top:16px}
@media(max-width:640px){.lc-detail-row{flex-direction:column}}
.lc-chart-wrap{flex:0 0 200px;height:170px;position:relative}
.lc-mat-list{flex:1;min-width:0}
.lc-mat-title{font-family:var(--mono);font-size:10px;letter-spacing:1px;color:var(--muted);margin-bottom:8px}
.mat-scroll{max-height:190px;overflow-y:auto}
.mat-scroll::-webkit-scrollbar{width:3px}
.mat-scroll::-webkit-scrollbar-thumb{background:var(--border2);border-radius:2px}
.mat-row{display:flex;align-items:center;gap:8px;padding:6px 0;border-bottom:1px solid var(--border);font-size:12px}
.mat-row:last-child{border-bottom:none}
.mat-rname{flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:var(--ink)}
.mat-rmeta{font-family:var(--mono);font-size:10px;color:var(--muted);white-space:nowrap}
.new-week-box{background:var(--surface2);border:1px solid var(--border);border-radius:var(--r-md);padding:16px;margin-top:16px}
.new-week-title-row{display:flex;align-items:center;gap:10px;margin-bottom:6px}
.new-week-title-text{font-size:14px;font-weight:700;color:var(--ink)}
.new-week-badge{font-family:var(--mono);font-size:10px;background:#DBEAFE;color:#1E3A8A;padding:2px 8px;border-radius:10px}
.new-week-sub{font-family:var(--mono);font-size:10px;color:var(--muted);margin-bottom:10px}
.new-week-list{max-height:260px;overflow-y:auto}
.new-week-list::-webkit-scrollbar{width:3px}
.new-week-list::-webkit-scrollbar-thumb{background:var(--border2);border-radius:2px}
.nw-item{display:flex;align-items:center;gap:8px;padding:6px 0;border-bottom:1px solid var(--border);font-size:12px}
.nw-item:last-child{border-bottom:none}
.nw-name{flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:var(--ink)}
.nw-meta{font-family:var(--mono);font-size:10px;color:var(--muted);white-space:nowrap}
.nw-link{color:var(--blue-l);text-decoration:none;font-size:11px;flex-shrink:0}
.pf-btn{font-family:var(--mono);font-size:11px;letter-spacing:0.5px;background:var(--surface);border:1px solid var(--border2);color:var(--muted);padding:5px 14px;border-radius:20px;cursor:pointer;transition:all .15s;font-weight:500}
.pf-btn:hover{border-color:var(--amber-l);color:var(--amber)}
.pf-btn.active{background:var(--ink);color:#fff;border-color:var(--ink)}
.charts-grid{display:grid;grid-template-columns:repeat(2,1fr);gap:14px}
@media(max-width:768px){.charts-grid{grid-template-columns:1fr}}
.chart-box{background:var(--surface);border:1px solid var(--border);border-radius:var(--r-md);padding:18px 20px}
.chart-title{font-family:var(--mono);font-size:10px;letter-spacing:1.5px;text-transform:uppercase;color:var(--muted);margin-bottom:12px}
.chart-canvas{position:relative;height:200px}
.tbl-wrap{border-radius:var(--r-md);overflow:hidden;border:1px solid var(--border)}
.tbl-scroll{overflow-x:auto}
table{width:100%;border-collapse:collapse}
thead tr{background:var(--surface2)}
th{font-family:var(--mono);font-size:9px;letter-spacing:1.5px;text-transform:uppercase;color:var(--muted);padding:11px 14px;text-align:left;font-weight:500;border-bottom:1px solid var(--border);white-space:nowrap}
td{padding:10px 14px;border-bottom:1px solid var(--border);font-family:var(--mono);font-size:12px;color:var(--muted)}
tbody tr:last-child td{border-bottom:none}
tbody tr:hover td{background:var(--surface2)}
.td-name{color:var(--ink);font-family:var(--font);font-size:13px;font-weight:600}
.td-num{text-align:right}
.td-rank{width:32px;color:var(--dim)}
.modal-bg{display:none;position:fixed;inset:0;background:rgba(15,23,42,.6);backdrop-filter:blur(4px);z-index:999;padding:20px;overflow-y:auto}
.modal-box{background:var(--surface);border:1px solid var(--border);border-radius:var(--r-lg);max-width:920px;margin:60px auto;padding:28px;position:relative;box-shadow:0 24px 64px rgba(0,0,0,.12)}
.modal-title{font-size:20px;font-weight:800;color:var(--ink);margin-bottom:4px}
.modal-sub{font-family:var(--mono);font-size:10px;letter-spacing:1px;color:var(--muted);margin-bottom:20px}
.modal-close{position:absolute;top:20px;right:22px;width:28px;height:28px;border-radius:8px;background:var(--surface2);border:1px solid var(--border);font-size:14px;cursor:pointer;color:var(--muted);display:flex;align-items:center;justify-content:center;transition:all .15s}
.modal-close:hover{background:var(--border);color:var(--ink)}
.tbl-link{color:var(--blue-l);text-decoration:none;font-size:13px;opacity:.7}
.tbl-link:hover{opacity:1}
.footer{text-align:center;margin-top:48px;font-family:var(--mono);font-size:10px;letter-spacing:1px;color:var(--dim)}
.av-0{background:linear-gradient(135deg,#B45309,#FCD34D)}.av-1{background:linear-gradient(135deg,#BE185D,#F472B6)}.av-2{background:linear-gradient(135deg,#1D4ED8,#60A5FA)}.av-3{background:linear-gradient(135deg,#065F46,#34D399)}.av-4{background:linear-gradient(135deg,#7C3AED,#A78BFA)}.av-5{background:linear-gradient(135deg,#0E7490,#22D3EE)}
.page-tabs{display:flex;gap:4px;margin-bottom:20px;background:var(--surface);border:1px solid var(--border);border-radius:var(--r-md);padding:4px;width:fit-content}
.page-tab{padding:8px 20px;border-radius:8px;border:none;background:none;font-family:var(--font);font-size:13px;font-weight:600;color:var(--muted);cursor:pointer;transition:all .15s}
.page-tab:hover{color:var(--ink)}
.page-tab.active{background:var(--ink);color:#fff}"""


def get_html_body(total_consume, total_gmv, total_orders, total_with_consume,
                  n_agents, sidebar_btns,
                  total_lifecycle, bk_html, new_week, new_week_html,
                  prod_filter_html, compare_rows):
    new_week_pct = round(len(new_week) / total_with_consume * 100) if total_with_consume else 0
    return f'''<div class="topbar">
  <div class="topbar-left">
    <div class="topbar-logo">代</div>
    <div>
      <div class="topbar-title">代理商数据分析</div>
      <div class="topbar-sub">AGENT MATERIAL REPORT · {REPORT_DATE}</div>
    </div>
  </div>
  <span class="badge">数据截至 {DATA_DATE}</span>
</div>

<div class="kpi-row">
  <div class="kpi-card"><div class="kpi-label">总消耗</div><div class="kpi-val">¥{total_consume:,.0f}</div></div>
  <div class="kpi-card"><div class="kpi-label">总 GMV</div><div class="kpi-val">¥{total_gmv:,.0f}</div></div>
  <div class="kpi-card"><div class="kpi-label">总订单</div><div class="kpi-val">{total_orders}</div></div>
  <div class="kpi-card"><div class="kpi-label">有消耗素材</div><div class="kpi-val">{total_with_consume}</div></div>
</div>

<div class="main-layout">
  <div class="dir-sidebar">
    <div class="dir-sidebar-head">选择代理商</div>
    <button class="dir-btn active" onclick="selectAgent('all',this)">
      <div class="dir-avatar av-2" style="font-size:11px;letter-spacing:-0.5px">全部</div>
      <div class="dir-info">
        <div class="dir-name">全部代理商</div>
        <div class="dir-stat">{n_agents}家 · 总消耗 {fmt_consume(total_consume)}</div>
      </div>
    </button>
{sidebar_btns}  </div>

  <div>
    <div class="dir-panel" id="agent-panel" style="display:none"></div>

    <div id="agent-overview">

      <div class="collapsible">
        <div class="coll-head" onclick="toggleColl(this)">
          <div class="coll-title">素材生命周期 <span class="coll-badge" style="background:#DCFCE7;color:#166534">{total_lifecycle} 条</span></div>
          <span class="coll-arrow">▼</span>
        </div>
        <div class="coll-body">
          <div class="lc-buckets">
{bk_html}          </div>
          <div class="lc-detail-row">
            <div class="lc-chart-wrap"><canvas id="lifecycleChart"></canvas></div>
            <div class="lc-mat-list">
              <div class="lc-mat-title" id="bucketDetailTitle">← 点击分桶查看素材明细</div>
              <div class="mat-scroll" id="bucketMaterialList"></div>
            </div>
          </div>
          <div class="new-week-box">
            <div class="new-week-title-row">
              <span class="new-week-title-text">本周新起量素材</span>
              <span class="new-week-badge">{len(new_week)} 条</span>
            </div>
            <div class="new-week-sub">首次消耗时间在 {NEW_WEEK_LABEL}（占有消耗素材 {new_week_pct}%）</div>
            <div class="new-week-list">{new_week_html}</div>
          </div>
        </div>
      </div>

      <div class="sec-label">代理商对比</div>
      <div id="prodFilterBar" style="display:flex;gap:6px;flex-wrap:wrap;margin-bottom:16px">
{prod_filter_html}      </div>
      <div class="charts-grid" style="margin-bottom:20px">
        <div class="chart-box"><div class="chart-title">总消耗对比</div><div class="chart-canvas"><canvas id="consumeChart"></canvas></div></div>
        <div class="chart-box"><div class="chart-title">GMV 对比</div><div class="chart-canvas"><canvas id="gmvChart"></canvas></div></div>
        <div class="chart-box"><div class="chart-title">订单数对比</div><div class="chart-canvas"><canvas id="ordersChart"></canvas></div></div>
        <div class="chart-box"><div class="chart-title">有消耗素材数</div><div class="chart-canvas"><canvas id="materialsChart"></canvas></div></div>
      </div>

      <div class="sec-label">详细对比</div>
      <div class="tbl-wrap"><div class="tbl-scroll">
        <table style="table-layout:fixed;width:100%">
          <colgroup>
            <col style="width:100px"><col style="width:130px"><col style="width:120px">
            <col style="width:90px"><col style="width:110px"><col style="width:110px"><col style="width:120px">
          </colgroup>
          <thead><tr>
            <th>代理商</th><th style="text-align:right">总消耗</th><th style="text-align:right">总GMV</th>
            <th style="text-align:right">总订单</th><th style="text-align:right">有消耗素材</th>
            <th style="text-align:right">有成交素材</th><th style="text-align:right">平均投放天数</th>
          </tr></thead>
          <tbody id="compareTableBody">{compare_rows}</tbody>
        </table>
      </div></div>
    </div>
  </div>
</div>

<div class="footer">Generated {datetime.now().strftime("%Y-%m-%d")}</div>'''


def get_js_static():
    return """// ── Collapsible
let _lcChartInited = false;
function toggleColl(head) {
  const body = head.nextElementSibling;
  const arrow = head.querySelector('.coll-arrow');
  body.classList.toggle('open');
  arrow.classList.toggle('open');
  if (body.classList.contains('open') && !_lcChartInited && document.getElementById('lifecycleChart')) {
    _lcChartInited = true;
    initLcChart();
  }
}

// ── Agent selector
function renderAgentPanel(name) {
  const d = agentPanelData[name];
  const av = AVATAR_MAP[name] || 'av-2';
  const rankColors = ['#1E40AF','#0D9488','#D97706'];
  const prodOrder = ['9元李博', '199双科'];
  const prodLabels = {'9元李博':'9元李博','199双科':'199双科'};
  function renderTop3Items(items) {
    return items.map((t,i) => {
      const lk = t.url ? `<a href="${t.url}" target="_blank" class="mat-link">▶ 预览</a>` : '';
      return `<div class="top-item-row"><span class="top-rank-badge" style="background:${rankColors[i]}">${i+1}</span><div class="top-item-body"><div class="top-item-name" title="${t.name}">${t.name}</div><div class="top-item-meta">${t.meta} ${lk}</div></div></div>`;
    }).join('');
  }
  let top3Section = '';
  if (d.prodTop3) {
    prodOrder.forEach(ptag => {
      const items = d.prodTop3[ptag];
      if (!items || !items.length) return;
      top3Section += `<div style="font-size:13px;font-weight:700;color:var(--ink);margin:14px 0 8px">成交 TOP 3 · ${prodLabels[ptag]}</div>`;
      top3Section += `<div class="top-list">${renderTop3Items(items)}</div>`;
    });
  }
  if (!top3Section) {
    const top3html = d.top3.map((t,i) => {
      const lk = t.url ? `<a href="${t.url}" target="_blank" class="mat-link">▶ 预览</a>` : '';
      return `<div class="top-item-row"><span class="top-rank-badge" style="background:${rankColors[i]}">${i+1}</span><div class="top-item-body"><div class="top-item-name" title="${t.name}">${t.name}</div><div class="top-item-meta">${t.meta} ${lk}</div></div></div>`;
    }).join('');
    top3Section = `<div style="font-size:13px;font-weight:700;color:var(--ink);margin-bottom:10px">成交 TOP 3</div><div class="top-list">${top3html}</div>`;
  }
  return `<div class="dir-panel-head">
    <div class="dir-panel-avatar ${av}">${name[0]}</div>
    <div><div class="dir-panel-name">${name}</div><div class="dir-panel-sub">${d.rank}</div></div>
  </div>
  <div class="dir-panel-body">
    <div class="panel-metrics">
      <div class="pm-card"><div class="pm-label">消耗</div><div class="pm-val amber">${d.consume}</div></div>
      <div class="pm-card"><div class="pm-label">GMV</div><div class="pm-val">${d.gmv}</div></div>
      <div class="pm-card"><div class="pm-label">订单</div><div class="pm-val">${d.orders}</div></div>
      <div class="pm-card"><div class="pm-label">有消耗素材</div><div class="pm-val">${d.mat}</div></div>
    </div>
    <div class="consume-bar-section">
      <div class="consume-bar-label"><span>消耗占比</span><span>${d.pct}</span></div>
      <div class="consume-bar-bg"><div class="consume-bar-fill" style="width:${d.pctVal}%"></div></div>
    </div>
    ${top3Section}
    <button class="detail-btn" onclick="showDetails('${name}')">查看消耗 TOP 20 →</button>
  </div>`;
}

function selectAgent(name, btn) {
  document.querySelectorAll('.dir-btn').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  const panel = document.getElementById('agent-panel');
  const overview = document.getElementById('agent-overview');
  if (name === 'all') {
    panel.style.display = 'none';
    overview.style.display = 'block';
  } else {
    panel.innerHTML = renderAgentPanel(name);
    panel.style.display = 'block';
    overview.style.display = 'none';
  }
}

// ── Lifecycle
const bucketKeys = ['1-7天', '8-14天', '15-30天', '30天以上'];
const bkColors = ['#0D9488','#3B82F6','#D97706','#E11D48'];
let lcChart = null;

function initLcChart() {
  if (lcChart) return;
  lcChart = new Chart(document.getElementById('lifecycleChart'), {
    type: 'bar',
    data: { labels: bucketKeys, datasets: [{ data: bucketKeys.map(k => lifecycleBuckets[k].length), backgroundColor: bkColors, borderRadius: 4, borderSkipped: false }] },
    options: { indexAxis: 'y', responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } }, scales: { x: { grid: { color: 'rgba(0,0,0,0.04)' }, ticks: { font: { family: 'JetBrains Mono', size: 10 } } }, y: { grid: { display: false }, ticks: { font: { family: 'JetBrains Mono', size: 10 } } } } }
  });
}

function selectBucket(idx) {
  document.querySelectorAll('.bk-pill').forEach((el,i) => el.classList.toggle('active', i===idx));
  initLcChart();
  const bk = bucketKeys[idx];
  const items = lifecycleBuckets[bk];
  document.getElementById('bucketDetailTitle').textContent = bk + ' · ' + items.length + ' 条（按消耗排序）';
  document.getElementById('bucketMaterialList').innerHTML = items.map(m => {
    const lk = m.链接 ? `<a href="${m.链接}" target="_blank" class="mat-link">▶</a>` : '';
    return `<div class="mat-row"><span class="mat-rname" title="${m.素材名称}">${m.素材名称}</span><span class="mat-rmeta">${m.代理商} · ¥${m.总消耗.toFixed(0)} · ${m.总单量}单</span>${lk}</div>`;
  }).join('');
}

// ── Charts
const chartColors = """ + json.dumps(CHART_COLORS) + """;
const barOpts = () => ({
  responsive: true, maintainAspectRatio: false,
  plugins: { legend: { display: false } },
  scales: {
    x: { grid: { display: false }, ticks: { font: { family: 'JetBrains Mono', size: 10 } } },
    y: { grid: { color: 'rgba(0,0,0,0.04)' }, ticks: { font: { family: 'JetBrains Mono', size: 10 } } }
  }
});
const chartKeys = ['consume','gmv','orders','materials'];
const charts = {};
chartKeys.forEach((key, i) => {
  charts[key] = new Chart(document.getElementById(['consumeChart','gmvChart','ordersChart','materialsChart'][i]), {
    type: 'bar',
    data: { labels: agents, datasets: [{ data: allProductData[key], backgroundColor: chartColors, borderRadius: 4, borderSkipped: false }] },
    options: barOpts()
  });
});

function filterByProduct(prod, btn) {
  document.querySelectorAll('.pf-btn').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  const d = prod === 'all' ? allProductData : (productData[prod] || allProductData);
  chartKeys.forEach(key => { charts[key].data.datasets[0].data = d[key]; charts[key].update(); });
  updateCompareTable(prod);
}

function updateCompareTable(prod) {
  const tbody = document.getElementById('compareTableBody');
  if (!tbody) return;
  const d = prod === 'all' ? allProductData : (productData[prod] || allProductData);
  agents.forEach((a, i) => {
    const row = tbody.rows[i];
    if (!row) return;
    row.cells[1].textContent = '¥' + d.consume[i].toLocaleString('zh-CN', {maximumFractionDigits:0});
    row.cells[2].textContent = '¥' + d.gmv[i].toLocaleString('zh-CN', {maximumFractionDigits:0});
    row.cells[3].textContent = d.orders[i];
    row.cells[4].textContent = d.materials[i];
  });
}

// ── Modal
function showDetails(agent) {
  const allDetails = materialDetails[agent] || [];
  const prods = [...new Set(allDetails.map(it => it.投放产品 || '').filter(Boolean))].sort();
  function renderRows(items) {
    return items.map((it,i) => {
      const lk = it.链接 ? `<a href="${it.链接}" target="_blank" class="tbl-link">▶</a>` : '—';
      return `<tr><td class="td-rank">${i+1}</td><td style="max-width:240px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:var(--ink);font-family:var(--font);font-size:12px">${it.素材名称}</td><td class="td-num" style="color:var(--amber)">¥${it.总消耗.toFixed(0)}</td><td class="td-num">¥${it.总GMV.toFixed(0)}</td><td class="td-num">${it.总订单}</td><td style="text-align:center">${lk}</td></tr>`;
    }).join('');
  }
  let filterBtns = `<div style="display:flex;gap:6px;flex-wrap:wrap;margin-bottom:14px" id="modal-prod-filter">
    <button class="pf-btn active" onclick="filterModalProd('all',this)">全部 (${allDetails.length})</button>`;
  prods.forEach(p => {
    const cnt = allDetails.filter(it => it.投放产品 === p).length;
    filterBtns += `<button class="pf-btn" onclick="filterModalProd('${p}',this)">${p} (${cnt})</button>`;
  });
  filterBtns += '</div>';
  const html = `<div class="modal-title">${agent}</div><div class="modal-sub">消耗 TOP 20 素材（按消耗降序）</div>${filterBtns}<div style="overflow-x:auto"><table><thead><tr><th>#</th><th>素材名称</th><th style="text-align:right">消耗</th><th style="text-align:right">GMV</th><th style="text-align:right">订单</th><th>预览</th></tr></thead><tbody id="modal-tbody">${renderRows(allDetails)}</tbody></table></div>`;
  document.getElementById('modalContent').innerHTML = html;
  document.getElementById('modalBg').style.display = 'block';
  window._modalDetails = allDetails;
  window._renderRows = renderRows;
}

function filterModalProd(prod, btn) {
  document.querySelectorAll('#modal-prod-filter .pf-btn').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  const items = prod === 'all' ? window._modalDetails : window._modalDetails.filter(it => it.投放产品 === prod);
  document.getElementById('modal-tbody').innerHTML = window._renderRows(items);
}

function closeModal() { document.getElementById('modalBg').style.display = 'none'; }
window.addEventListener('click', e => { if (e.target === document.getElementById('modalBg')) closeModal(); });"""


def main():
    print(f'读取数据: {INPUT_FILE}')
    all_materials = read_and_aggregate(INPUT_FILE)
    print(f'聚合后素材数: {len(all_materials)}（含自投放）')

    agent_stats, agent_product_stats = build_agent_stats(all_materials)

    for a in sorted(agent_stats, key=lambda x: -agent_stats[x]['总消耗']):
        s = agent_stats[a]
        print(f'  {a}: 消耗¥{s["总消耗"]:,.0f} | {s["总订单"]}单 | {s["有消耗素材数"]}条有消耗')

    html = generate_html(all_materials, agent_stats, agent_product_stats)
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        f.write(html)
    print(f'✓ 报告已生成: {OUTPUT_FILE}')


if __name__ == '__main__':
    main()
