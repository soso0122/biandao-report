#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
代理商素材数据分析与HTML报告生成 - 0807 版本
与 /tmp/agent_report_0731_orig.html 设计完全一致

用法：
  python3 scripts/generate_report_agent_0807.py [DATE]
  DATE 默认 '0807'，对应 data/【周报】投后素材看板数据-代理-{DATE}.csv
"""

import csv
import json
import sys
import os
from collections import defaultdict
from datetime import datetime

# ── 配置 ────────────────────────────────────────────────
DATE = sys.argv[1] if len(sys.argv) > 1 else '0807'
WEEK_START = datetime(2026, 8, 1)   # 本周新起量判断起点
WEEK_END   = datetime(2026, 8, 7)   # 本周新起量判断终点

DATA_FILE  = f'data/【周报】投后素材看板数据-代理-{DATE}.csv'
OUT_FILE   = f'reports/代理商数据分析报告_{DATE}.html'

# ── 双周对比：自动推算上一期文件 ─────────────────────────────
_WEEK_MAP = {'0911': '0904', '0904': '0828', '0828': '0821', '0821': '0814', '0814': '0807'}
PREV_DATE  = _WEEK_MAP.get(DATE, '')
PREV_FILE  = f'data/【周报】投后素材看板数据-代理-{PREV_DATE}.csv' if PREV_DATE else ''

AGENT_NORM = {
    '成都发条荔枝文化传媒有限公司': '荔枝',
    '申坤互动（北京）信息技术有限公司': '申坤',
    '十人（北京）传媒广告有限公司': '十人',
}

AVATAR_MAP = {
    '荔枝': 'av-0',
    '自投放': 'av-1',
    '申坤': 'av-2',
    '十人': 'av-3',
    '有范': 'av-4',
    '启航': 'av-5',
    '玄武': 'av-4',
}

AGENT_ORDER = ['荔枝', '自投放', '申坤', '十人', '有范', '启航', '玄武']

# ── 产品标签（供对比图 filter 用）──────────────────────────
PROD_LABELS = {
    '9元高中物理李博': '9元李博',
    '199元高中双科提分课': '199双科',
}

# ── 产品分类 ─────────────────────────────────────────────
def tag_prod(product_name: str) -> str:
    p = product_name or ''
    if '李博' in p or '物理' in p:
        return '9元高中物理李博'
    elif '199' in p or '双科' in p:
        return '199元高中双科提分课'
    return p or '其他'

# ── 读数据 ────────────────────────────────────────────────
def read_data(path: str):
    rows = []
    with open(path, 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)
    return rows


# ── 主分析 ────────────────────────────────────────────────
def analyze(rows):
    """
    Returns:
      agent_stats      : dict[agent_name] -> stats dict
      global_analysis  : lifecycle + new_week + total_with_consume
      agent_prod_stats : dict[agent][prod_tag] -> {consume, gmv, orders, materials}
      material_details : dict[agent] -> sorted list of top-20 by consume
    """
    # Per (agent, material) accumulators
    mat_consume   = defaultdict(float)
    mat_gmv       = defaultdict(float)
    mat_orders    = defaultdict(int)
    mat_link      = {}
    mat_first     = {}
    mat_days      = {}
    mat_prod      = {}   # raw product name (first seen)
    mat_imp       = defaultdict(float)   # for true CTR/CVR per material
    mat_click     = defaultdict(float)
    mat_conv      = defaultdict(float)

    # Per (agent, prod_tag) totals
    ap_consume    = defaultdict(lambda: defaultdict(float))
    ap_gmv        = defaultdict(lambda: defaultdict(float))
    ap_orders     = defaultdict(lambda: defaultdict(int))
    ap_mats       = defaultdict(lambda: defaultdict(set))   # set of mat names with consume

    # Per agent CTR/CVR (weighted by rows with spend)
    ag_ctr_sum    = defaultdict(float)
    ag_cvr_sum    = defaultdict(float)
    ag_ctr_n      = defaultdict(int)

    # Per agent impression/click/conv for true CTR/CVR
    ag_imp        = defaultdict(float)
    ag_click      = defaultdict(float)
    ag_conv       = defaultdict(float)

    for row in rows:
        raw_agent = row.get('代理商', '').strip()
        agent = AGENT_NORM.get(raw_agent, raw_agent)
        if not agent:
            continue

        mat  = row.get('素材名称', '').strip()
        link = row.get('素材预览', '').strip()
        raw_prod = row.get('投放产品', '').strip()
        prod_tag = tag_prod(raw_prod)
        ft   = row.get('首次消耗时间', '').strip()
        days_str = row.get('已上线投放天数', '').strip()

        key = (agent, mat)

        # first-seen fields
        if key not in mat_link and link:
            mat_link[key] = link
        if key not in mat_first and ft and ft != '-':
            mat_first[key] = ft
        if key not in mat_days and days_str and days_str not in ('', '-'):
            try:
                mat_days[key] = int(float(days_str))
            except ValueError:
                pass
        if key not in mat_prod and raw_prod:
            mat_prod[key] = raw_prod

        try:
            consume = float(row.get('消耗', 0) or 0)
            gmv     = float(row.get('成交GMV', 0) or 0)
            orders  = int(float(row.get('成交单量', 0) or 0))
            ctr_val = float(str(row.get('CTR', 0) or 0).replace('%','').replace(',','') or 0)
            cvr_val = float(str(row.get('CVR', 0) or 0).replace('%','').replace(',','') or 0)
        except (ValueError, TypeError):
            continue

        mat_consume[key] += consume
        mat_gmv[key]     += gmv
        mat_orders[key]  += orders

        if consume > 0:
            ag_ctr_sum[agent] += ctr_val
            ag_cvr_sum[agent] += cvr_val
            ag_ctr_n[agent]   += 1
            cpm_val = float(str(row.get('CPM（千次曝光成本）', 0) or 0).replace(',','') or 0)
            if cpm_val > 0:
                imp   = consume / cpm_val * 1000
                click = imp * ctr_val / 100
                conv  = click * cvr_val / 100
                ag_imp[agent]    += imp
                ag_click[agent]  += click
                ag_conv[agent]   += conv
                mat_imp[key]     += imp
                mat_click[key]   += click
                mat_conv[key]    += conv

        ap_consume[agent][prod_tag] += consume
        ap_gmv[agent][prod_tag]     += gmv
        ap_orders[agent][prod_tag]  += orders
        if consume > 0:
            ap_mats[agent][prod_tag].add(mat)

    # ── build per-agent stats ──────────────────────────────
    agent_stats = {}
    all_mats_for_lc = []    # global, deduped by mat name

    for agent in set(k[0] for k in mat_consume.keys()):
        total_consume = 0.0
        total_gmv     = 0.0
        total_orders  = 0
        n_with_consume = 0
        n_with_orders  = 0
        days_list      = []
        details        = []

        seen_globally = set()

        for key, consume in mat_consume.items():
            if key[0] != agent:
                continue
            mat = key[1]
            gmv    = mat_gmv[key]
            orders = mat_orders[key]
            link   = mat_link.get(key, '')
            ft     = mat_first.get(key, '')
            days   = mat_days.get(key)
            raw_prod = mat_prod.get(key, '')

            total_consume += consume
            total_gmv     += gmv
            total_orders  += orders

            if consume > 0:
                n_with_consume += 1
                if days is not None:
                    days_list.append(days)
            if orders > 0:
                n_with_orders += 1

            details.append({
                '素材名称':    mat,
                '总消耗':      round(consume, 2),
                '总GMV':       round(gmv, 2),
                '总订单':      orders,
                '链接':        link,
                '首次消耗时间': ft,
                '投放天数':    days,
                '投放产品':    raw_prod,
                '代理商':      agent,
                'CTR':         round(mat_click[key] / mat_imp[key] * 100, 2) if mat_imp[key] else 0,
                'CVR':         round(mat_conv[key] / mat_click[key] * 100, 2) if mat_click[key] else 0,
            })

            # For global lifecycle – dedup by mat name only
            if mat not in seen_globally and consume > 0:
                seen_globally.add(mat)
                all_mats_for_lc.append({
                    '素材名称':    mat,
                    '代理商':      agent,
                    '总消耗':      round(consume, 2),
                    '总单量':      orders,
                    '首次消耗时间': ft,
                    '投放天数':    days,
                    '链接':        link,
                })

        # sort details by consume desc, keep top-20 for modal
        details_sorted = sorted(details, key=lambda x: -x['总消耗'])

        agent_stats[agent] = {
            '总消耗':          total_consume,
            '总GMV':           total_gmv,
            '总订单':          total_orders,
            '有消耗素材数':    n_with_consume,
            '有成交素材数':    n_with_orders,
            '平均投放天数':    sum(days_list)/len(days_list) if days_list else 0,
            '平均CTR':         ag_click[agent] / ag_imp[agent] * 100 if ag_imp[agent] else 0,
            '平均CVR':         ag_conv[agent] / ag_click[agent] * 100 if ag_click[agent] else 0,
            '总展示':           ag_imp[agent],
            '总点击':           ag_click[agent],
            '总转化':           ag_conv[agent],
            '素材详情':        details_sorted[:20],   # top-20 for modal
        }

    # ── lifecycle buckets (global, deduped) ───────────────
    lc = {'1-7天': [], '8-14天': [], '15-30天': [], '30天以上': []}
    for m in all_mats_for_lc:
        d = m['投放天数']
        if d is None:
            continue
        if d <= 7:
            lc['1-7天'].append(m)
        elif d <= 14:
            lc['8-14天'].append(m)
        elif d <= 30:
            lc['15-30天'].append(m)
        else:
            lc['30天以上'].append(m)

    # sort each bucket by consume desc
    for bk in lc:
        lc[bk].sort(key=lambda x: -x['总消耗'])

    # ── new-week materials ────────────────────────────────
    new_week = []
    for m in all_mats_for_lc:
        ft = m['首次消耗时间']
        if not ft or ft == '-':
            continue
        try:
            dt = datetime.strptime(ft, '%Y/%m/%d')
            if WEEK_START <= dt <= WEEK_END:
                new_week.append(m)
        except ValueError:
            pass
    new_week.sort(key=lambda x: -x['总消耗'])

    global_analysis = {
        'lifecycle_buckets': lc,
        'new_this_week':     new_week,
        'total_with_consume': len(all_mats_for_lc),
    }

    # ── agent_prod_stats serializable ─────────────────────
    ap_stats_out = {}
    for agent in ap_consume:
        ap_stats_out[agent] = {}
        for ptag in ap_consume[agent]:
            ap_stats_out[agent][ptag] = {
                '消耗':  ap_consume[agent][ptag],
                'GMV':   ap_gmv[agent][ptag],
                '订单':  ap_orders[agent][ptag],
                '素材':  len(ap_mats[agent][ptag]),
            }

    return agent_stats, global_analysis, ap_stats_out


# ── Build JS blobs ──────────────────────────────────────────
def build_js_data(agent_stats, global_analysis, ap_stats,
                  prev_agent_stats=None, prev_mat_stats=None):
    if prev_agent_stats is None: prev_agent_stats = {}
    if prev_mat_stats is None:   prev_mat_stats = {}
    """
    Build all JS constants that the HTML template needs.
    Returns a dict of variable_name -> python value (to be json-encoded).
    """
    # Ordered list of agents actually present, sorted by consume desc
    agents_present = sorted(agent_stats.keys(), key=lambda a: -agent_stats[a]['总消耗'])
    # Keep only those in AGENT_ORDER, preserve order, then append extras
    ordered = [a for a in AGENT_ORDER if a in agents_present]
    for a in agents_present:
        if a not in ordered:
            ordered.append(a)
    agents = ordered

    total_consume = sum(agent_stats[a]['总消耗'] for a in agents)

    # ── agentPanelData ────────────────────────────────────
    apd = {}
    for i, agent in enumerate(agents):
        s = agent_stats[agent]
        consume_val = s['总消耗']
        # rank
        rank = f'#{i+1} by 消耗'

        def fmt_wan(v):
            if v >= 10000:
                return f'¥{v/10000:.1f}万'
            return f'¥{v:,.0f}'

        # top10 overall by orders
        top10_all = sorted(s['素材详情'], key=lambda x: -x['总订单'])[:10]
        top10 = [{'name': t['素材名称'],
                  'meta': f'¥{t["总消耗"]:,.0f} · {t["总订单"]}单',
                  'url':  t.get('链接', '')} for t in top10_all]

        # prodTop10: top10 per product tag
        prod_top10 = {}
        for ptag in ['9元高中物理李博', '199元高中双科提分课']:
            short = PROD_LABELS[ptag]
            ptag_mats = [x for x in s['素材详情']
                         if tag_prod(x.get('投放产品', '')) == ptag]
            ptag_mats.sort(key=lambda x: -x['总订单'])
            prod_top10[short] = [
                {'name': t['素材名称'],
                 'meta': f'¥{t["总消耗"]:,.0f} · {t["总订单"]}单',
                 'url':  t.get('链接', '')}
                for t in ptag_mats[:10]
            ]

        pct_val = (consume_val / total_consume * 100) if total_consume > 0 else 0

        # 双周对比
        prev = prev_agent_stats.get(agent, {})
        def _chg(cur, prv):
            if not prv: return None
            return round((cur - prv) / prv * 100, 1) if prv else None

        apd[agent] = {
            'rank':    rank,
            'consume': fmt_wan(consume_val),
            'gmv':     fmt_wan(s['总GMV']),
            'orders':  f'{s["总订单"]:,}',
            'mat':     str(s['有消耗素材数']),
            'pct':     f'{pct_val:.1f}%',
            'pctVal':  round(pct_val, 1),
            'top10':    top10,
            'prodTop10': prod_top10,
            'ctr':     round(s['平均CTR'], 2),
            'cvr':     round(s['平均CVR'], 2),
            'prev': {
                'consume': round(prev.get('总消耗', 0), 2),
                'orders':  prev.get('总订单', 0),
                'ctr':     round(prev.get('平均CTR', 0), 2),
                'cvr':     round(prev.get('平均CVR', 0), 2),
            } if prev else None,
            'chg': {
                'consume': _chg(consume_val, prev.get('总消耗')),
                'orders':  _chg(s['总订单'], prev.get('总订单')),
                'ctr':     round(s['平均CTR'] - prev.get('平均CTR', 0), 2),
                'cvr':     round(s['平均CVR'] - prev.get('平均CVR', 0), 2),
            } if prev else None,
        }

    # ── lifecycleBuckets ──────────────────────────────────
    lc_buckets = {}
    for bk, items in global_analysis['lifecycle_buckets'].items():
        lc_buckets[bk] = [
            {
                '素材名称':     m['素材名称'],
                '代理商':       m['代理商'],
                '总消耗':       m['总消耗'],
                '总单量':       m['总单量'],
                '首次消耗时间':  m['首次消耗时间'],
                '投放天数':     m['投放天数'],
                '链接':         m.get('链接', ''),
            }
            for m in items
        ]

    # ── allProductData (all products combined) ─────────────
    def agent_data(agents, ap_stats, ptag=None):
        consume_list  = []
        gmv_list      = []
        orders_list   = []
        mats_list     = []
        for a in agents:
            if ptag:
                d = ap_stats.get(a, {}).get(ptag, {})
                consume_list.append(round(d.get('消耗', 0), 2))
                gmv_list.append(round(d.get('GMV', 0), 2))
                orders_list.append(d.get('订单', 0))
                mats_list.append(d.get('素材', 0))
            else:
                consume_list.append(round(agent_stats[a]['总消耗'], 2))
                gmv_list.append(round(agent_stats[a]['总GMV'], 2))
                orders_list.append(agent_stats[a]['总订单'])
                mats_list.append(agent_stats[a]['有消耗素材数'])
        return {'consume': consume_list, 'gmv': gmv_list, 'orders': orders_list, 'materials': mats_list}

    all_product_data = agent_data(agents, ap_stats)

    # per-product
    all_ptags = set()
    for a in ap_stats:
        all_ptags.update(ap_stats[a].keys())

    product_data = {}
    for ptag in sorted(all_ptags):
        product_data[ptag] = agent_data(agents, ap_stats, ptag)

    # ── materialDetails ───────────────────────────────────
    mat_details = {}
    for agent in agents:
        mat_details[agent] = agent_stats[agent]['素材详情']

    return {
        'agents':          agents,
        'agentPanelData':  apd,
        'lifecycleBuckets': lc_buckets,
        'allProductData':  all_product_data,
        'productData':     product_data,
        'materialDetails': mat_details,
        'prevMatStats':    prev_mat_stats,
    }


# ── HTML generation helpers ────────────────────────────────
def _fmt_wan(v):
    if v >= 10000:
        return f'¥{v/10000:.1f}万'
    return f'¥{v:,.0f}'


def _fmt_date_label(d: datetime) -> str:
    return f'{d.month}月{d.day}日'


def _render_new_week_items(new_week):
    parts = []
    for m in new_week:
        nm = m['素材名称']
        agent = m['代理商']
        ft = m['首次消耗时间']
        consume = m['总消耗']
        orders = m['总单量']
        link = m.get('链接', '')
        lk_html = f'<a href="{link}" target="_blank" class="nw-link">&#9654;</a>' if link else ''
        parts.append(
            f'<div class="nw-item">'
            f'<span class="nw-name" title="{nm}">{nm}</span>'
            f'<span class="nw-meta">{agent} | 首消 {ft} | ¥{consume:,.0f} | {orders}单</span>'
            f'{lk_html}'
            f'</div>'
        )
    return '\n'.join(parts)


def _render_lc_buckets_html(lc, total_with_consume):
    bk_colors = {'1-7天': '#0D9488', '8-14天': '#3B82F6', '15-30天': '#D97706', '30天以上': '#E11D48'}
    parts = []
    for bk in ['1-7天', '8-14天', '15-30天', '30天以上']:
        items = lc.get(bk, [])
        cnt = len(items)
        pct = cnt / total_with_consume * 100 if total_with_consume > 0 else 0
        color = bk_colors[bk]
        idx = list(bk_colors.keys()).index(bk)
        parts.append(
            f'<div class="bk-pill" onclick="selectBucket({idx})">'
            f'<div class="bk-name">{bk}</div>'
            f'<div class="bk-cnt" style="color:{color}">{cnt}</div>'
            f'<div class="bk-pct">占有消耗素材 {pct:.0f}%</div>'
            f'</div>'
        )
    return '\n'.join(parts)


def _render_sidebar_buttons(agents, agent_stats):
    total_consume = sum(agent_stats[a]['总消耗'] for a in agents)
    parts = []
    # "全部" button
    agent_cnt = len(agents)
    total_wan = _fmt_wan(total_consume)
    parts.append(
        f'<button class="dir-btn active" onclick="selectAgent(\'all\',this)">'
        f'<div class="dir-avatar av-2" style="font-size:11px;letter-spacing:-0.5px">全部</div>'
        f'<div class="dir-info">'
        f'<div class="dir-name">全部代理商</div>'
        f'<div class="dir-stat">{agent_cnt}家 · 总消耗 {total_wan}</div>'
        f'</div></button>'
    )
    for agent in agents:
        av = AVATAR_MAP.get(agent, 'av-4')
        first_char = agent[0]
        s = agent_stats[agent]
        consume_str = _fmt_wan(s['总消耗'])
        orders_str = f'{s["总订单"]:,}'
        parts.append(
            f'<button class="dir-btn" onclick="selectAgent(\'{agent}\',this)" data-agent="{agent}">'
            f'<div class="dir-avatar {av}">{first_char}</div>'
            f'<div class="dir-info">'
            f'<div class="dir-name">{agent}</div>'
            f'<div class="dir-stat">{consume_str} · {orders_str}单</div>'
            f'</div></button>'
        )
    return '\n'.join(parts)


def _render_compare_table_rows(agents, agent_stats):
    rows = []
    for agent in agents:
        s = agent_stats[agent]
        avg_days = s['平均投放天数']
        rows.append(
            f'<tr>'
            f'<td><strong>{agent}</strong></td>'
            f'<td style="text-align:right;font-family:var(--mono)">¥{s["总消耗"]:,.0f}</td>'
            f'<td style="text-align:right;font-family:var(--mono)">¥{s["总GMV"]:,.0f}</td>'
            f'<td style="text-align:right;font-family:var(--mono)">{s["总订单"]}</td>'
            f'<td style="text-align:right;font-family:var(--mono)">{s["有消耗素材数"]}</td>'
            f'<td style="text-align:right;font-family:var(--mono)">{s["有成交素材数"]}</td>'
            f'<td style="text-align:right;font-family:var(--mono)">{avg_days:.1f} 天</td>'
            f'</tr>'
        )
    return '\n'.join(rows)


def _render_prod_filter_buttons(product_data):
    parts = ['<button class="pf-btn pf-all active" onclick="filterByProduct(\'all\',this)">全部</button>']
    for ptag in sorted(product_data.keys()):
        parts.append(
            f'<button class="pf-btn" onclick="filterByProduct(\'{ptag}\',this)">{ptag}</button>'
        )
    return '\n'.join(parts)


CSS = """:root{--bg:#F1F5F9;--surface:#FFFFFF;--surface2:#F8FAFC;--border:#E2E8F0;--border2:#CBD5E1;--ink:#0F172A;--ink2:#334155;--muted:#64748B;--dim:#94A3B8;--blue:#1E40AF;--blue-l:#3B82F6;--sky:#0EA5E9;--amber:#D97706;--amber-l:#F59E0B;--teal:#0D9488;--font:'Plus Jakarta Sans',sans-serif;--mono:'JetBrains Mono',monospace;--r-sm:8px;--r-md:12px;--r-lg:16px}
*{margin:0;padding:0;box-sizing:border-box}html{scroll-behavior:smooth}body{font-family:var(--font);background:var(--bg);color:var(--ink);min-height:100vh}
.wrap{max-width:1440px;margin:0 auto;padding:32px 24px 80px}
.topbar{display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:12px;background:var(--surface);border:1px solid var(--border);border-radius:var(--r-lg);padding:20px 28px;margin-bottom:24px}
.topbar-left{display:flex;align-items:center;gap:16px}
.topbar-logo{width:40px;height:40px;border-radius:10px;background:linear-gradient(135deg,#D97706,#F59E0B);display:flex;align-items:center;justify-content:center;font-family:var(--mono);font-size:14px;font-weight:500;color:#fff;flex-shrink:0}
.topbar-title{font-size:18px;font-weight:800;color:var(--ink);letter-spacing:-0.5px}
.topbar-sub{font-family:var(--mono);font-size:11px;color:var(--muted);margin-top:2px}
.badge{font-family:var(--mono);font-size:10px;letter-spacing:0.5px;padding:5px 12px;border-radius:20px;border:1px solid;white-space:nowrap;background:#FEF3C7;color:#92400E;border-color:#FDE68A}
.kpi-row{display:grid;grid-template-columns:repeat(6,1fr);gap:12px;margin-bottom:24px}
@media(max-width:1024px){.kpi-row{grid-template-columns:repeat(3,1fr)}}
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
.dir-btn:last-child{border-bottom:none}.dir-btn:hover{background:var(--surface2)}.dir-btn.active{background:#FEF9EE}
.dir-btn.active::before{content:'';position:absolute;left:0;top:0;bottom:0;width:3px;background:var(--amber);border-radius:0 2px 2px 0}
.dir-avatar{width:32px;height:32px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:13px;font-weight:700;flex-shrink:0}
.dir-info{flex:1;min-width:0}.dir-name{font-size:14px;font-weight:600;color:var(--ink);line-height:1.2}
.dir-stat{font-family:var(--mono);font-size:10px;color:var(--muted);margin-top:2px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.dir-btn.active .dir-name{color:var(--amber)}
.sec-label{font-family:var(--mono);font-size:10px;letter-spacing:2px;text-transform:uppercase;color:var(--muted);margin:28px 0 14px;display:flex;align-items:center;gap:10px}
.sec-label::after{content:'';flex:1;height:1px;background:var(--border)}
.collapsible{background:var(--surface);border:1px solid var(--border);border-radius:var(--r-lg);overflow:hidden;margin-bottom:16px}
.coll-head{display:flex;align-items:center;justify-content:space-between;padding:16px 20px;cursor:pointer;user-select:none;transition:background .15s}
.coll-head:hover{background:var(--surface2)}.coll-title{font-size:14px;font-weight:700;color:var(--ink);display:flex;align-items:center;gap:8px}
.coll-badge{font-family:var(--mono);font-size:9px;letter-spacing:1px;padding:2px 8px;border-radius:10px}
.coll-arrow{font-size:12px;color:var(--muted);transition:transform .2s}.coll-arrow.open{transform:rotate(180deg)}
.coll-body{padding:0 20px 20px;display:none}.coll-body.open{display:block}
.dir-panel{background:var(--surface);border:1px solid var(--border);border-radius:var(--r-lg);margin-bottom:20px;overflow:hidden}
.dir-panel-head{display:flex;align-items:center;gap:16px;padding:20px 24px;border-bottom:1px solid var(--border);background:linear-gradient(135deg,#FFFBEB,var(--surface))}
.dir-panel-avatar{width:52px;height:52px;border-radius:14px;display:flex;align-items:center;justify-content:center;font-size:20px;font-weight:800;flex-shrink:0;color:#fff}
.dir-panel-name{font-size:22px;font-weight:800;color:var(--ink);letter-spacing:-0.5px}
.dir-panel-sub{font-family:var(--mono);font-size:11px;color:var(--muted);margin-top:3px}
.dir-panel-body{padding:20px 24px}
.panel-metrics{display:grid;grid-template-columns:repeat(6,1fr);gap:10px;margin-bottom:16px}
@media(max-width:900px){.panel-metrics{grid-template-columns:repeat(3,1fr)}}
@media(max-width:700px){.panel-metrics{grid-template-columns:repeat(2,1fr)}}
.pm-card{background:var(--surface2);border:1px solid var(--border);border-radius:var(--r-sm);padding:14px 16px}
.pm-label{font-family:var(--mono);font-size:9px;letter-spacing:1px;text-transform:uppercase;color:var(--muted);margin-bottom:6px}
.pm-val{font-family:var(--mono);font-size:18px;font-weight:500;color:var(--ink)}.pm-val.amber{color:var(--amber)}
.consume-bar-section{margin-bottom:16px}
.consume-bar-label{display:flex;justify-content:space-between;font-family:var(--mono);font-size:10px;color:var(--muted);margin-bottom:5px}
.consume-bar-bg{background:var(--surface2);border-radius:4px;height:8px;overflow:hidden}
.consume-bar-fill{height:100%;background:linear-gradient(90deg,var(--amber),var(--amber-l));border-radius:4px;transition:width .5s ease}
.top-item-row{display:flex;align-items:flex-start;gap:10px;padding:8px 0;border-bottom:1px solid var(--border)}
.top-item-row:last-child{border-bottom:none}
.top-rank-badge{flex-shrink:0;width:22px;height:22px;border-radius:6px;display:flex;align-items:center;justify-content:center;font-family:var(--mono);font-size:11px;font-weight:600}
.r1{background:#FEF3C7;color:#92400E}.r2{background:#F1F5F9;color:#475569}.r3{background:#F1F5F9;color:#475569}
.top-item-body{flex:1;min-width:0}.top-item-name{font-size:11px;font-weight:500;color:var(--ink);overflow:hidden;text-overflow:ellipsis;white-space:nowrap;margin-bottom:2px}
.top-item-meta{font-family:var(--mono);font-size:10px;color:var(--muted)}
.mat-link{color:var(--blue-l);text-decoration:none;font-size:10px;font-family:var(--mono);margin-left:4px}.mat-link:hover{text-decoration:underline}
.detail-btn{display:inline-flex;align-items:center;gap:6px;margin-top:14px;padding:8px 16px;border-radius:8px;border:1px solid var(--border2);background:var(--surface);font-family:var(--font);font-size:12px;font-weight:600;color:var(--amber);cursor:pointer;transition:all .15s}
.detail-btn:hover{background:var(--amber);color:#fff;border-color:var(--amber)}
.lc-buckets{display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin-bottom:16px}
@media(max-width:640px){.lc-buckets{grid-template-columns:repeat(2,1fr)}}
.bk-pill{background:var(--surface2);border:1px solid var(--border);border-radius:var(--r-sm);padding:14px;cursor:pointer;transition:all .15s}
.bk-pill:hover{border-color:var(--border2);box-shadow:0 2px 8px rgba(0,0,0,.06)}.bk-pill.active{border-color:var(--amber-l);background:#FFFBEB}
.bk-name{font-family:var(--mono);font-size:10px;letter-spacing:1px;color:var(--muted);margin-bottom:6px}
.bk-cnt{font-family:var(--mono);font-size:24px;font-weight:500;line-height:1;margin-bottom:3px}.bk-pct{font-size:10px;color:var(--dim);font-family:var(--mono)}
.lc-detail-row{display:flex;gap:16px;align-items:flex-start;margin-top:16px}
@media(max-width:640px){.lc-detail-row{flex-direction:column}}
.lc-chart-wrap{flex:0 0 200px;height:170px;position:relative}.lc-mat-list{flex:1;min-width:0}
.lc-mat-title{font-family:var(--mono);font-size:10px;letter-spacing:1px;color:var(--muted);margin-bottom:8px}
.mat-scroll{max-height:190px;overflow-y:auto}.mat-scroll::-webkit-scrollbar{width:3px}.mat-scroll::-webkit-scrollbar-thumb{background:var(--border2);border-radius:2px}
.mat-row{display:flex;align-items:center;gap:8px;padding:6px 0;border-bottom:1px solid var(--border);font-size:12px}.mat-row:last-child{border-bottom:none}
.mat-rname{flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:var(--ink)}.mat-rmeta{font-family:var(--mono);font-size:10px;color:var(--muted);white-space:nowrap}
.new-week-box{background:var(--surface2);border:1px solid var(--border);border-radius:var(--r-md);padding:16px;margin-top:16px}
.new-week-title-row{display:flex;align-items:center;gap:10px;margin-bottom:6px}.new-week-title-text{font-size:14px;font-weight:700;color:var(--ink)}
.new-week-badge{font-family:var(--mono);font-size:10px;background:#DBEAFE;color:#1E3A8A;padding:2px 8px;border-radius:10px}
.new-week-sub{font-family:var(--mono);font-size:10px;color:var(--muted);margin-bottom:10px}
.new-week-list{max-height:260px;overflow-y:auto}.new-week-list::-webkit-scrollbar{width:3px}.new-week-list::-webkit-scrollbar-thumb{background:var(--border2);border-radius:2px}
.nw-item{display:flex;align-items:center;gap:8px;padding:6px 0;border-bottom:1px solid var(--border);font-size:12px}.nw-item:last-child{border-bottom:none}
.nw-name{flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:var(--ink)}.nw-meta{font-family:var(--mono);font-size:10px;color:var(--muted);white-space:nowrap}
.nw-link{color:var(--blue-l);text-decoration:none;font-size:11px;flex-shrink:0}
.pf-btn{font-family:var(--mono);font-size:11px;letter-spacing:0.5px;background:var(--surface);border:1px solid var(--border2);color:var(--muted);padding:5px 14px;border-radius:20px;cursor:pointer;transition:all .15s;font-weight:500}
.pf-btn:hover{border-color:var(--amber-l);color:var(--amber)}.pf-btn.active{background:var(--ink);color:#fff;border-color:var(--ink)}
.charts-grid{display:grid;grid-template-columns:repeat(2,1fr);gap:14px}
@media(max-width:768px){.charts-grid{grid-template-columns:1fr}}
.chart-box{background:var(--surface);border:1px solid var(--border);border-radius:var(--r-md);padding:18px 20px}
.chart-title{font-family:var(--mono);font-size:10px;letter-spacing:1.5px;text-transform:uppercase;color:var(--muted);margin-bottom:12px}
.chart-canvas{position:relative;height:200px}
.tbl-wrap{border-radius:var(--r-md);overflow:hidden;border:1px solid var(--border)}.tbl-scroll{overflow-x:auto}
table{width:100%;border-collapse:collapse}thead tr{background:var(--surface2)}
th{font-family:var(--mono);font-size:9px;letter-spacing:1.5px;text-transform:uppercase;color:var(--muted);padding:11px 14px;text-align:left;font-weight:500;border-bottom:1px solid var(--border);white-space:nowrap}
td{padding:10px 14px;border-bottom:1px solid var(--border);font-family:var(--mono);font-size:12px;color:var(--muted)}
tbody tr:last-child td{border-bottom:none}tbody tr:hover td{background:var(--surface2)}
.td-name{color:var(--ink);font-family:var(--font);font-size:13px;font-weight:600}.td-num{text-align:right}.td-rank{width:32px;color:var(--dim)}
.modal-bg{display:none;position:fixed;inset:0;background:rgba(15,23,42,.6);backdrop-filter:blur(4px);z-index:999;padding:20px;overflow-y:auto}
.modal-box{background:var(--surface);border:1px solid var(--border);border-radius:var(--r-lg);max-width:920px;margin:60px auto;padding:28px;position:relative;box-shadow:0 24px 64px rgba(0,0,0,.12)}
.modal-title{font-size:20px;font-weight:800;color:var(--ink);margin-bottom:4px}.modal-sub{font-family:var(--mono);font-size:10px;letter-spacing:1px;color:var(--muted);margin-bottom:20px}
.modal-close{position:absolute;top:20px;right:22px;width:28px;height:28px;border-radius:8px;background:var(--surface2);border:1px solid var(--border);font-size:14px;cursor:pointer;color:var(--muted);display:flex;align-items:center;justify-content:center;transition:all .15s}
.modal-close:hover{background:var(--border);color:var(--ink)}.tbl-link{color:var(--blue-l);text-decoration:none;font-size:13px;opacity:.7}.tbl-link:hover{opacity:1}
.footer{text-align:center;margin-top:48px;font-family:var(--mono);font-size:10px;letter-spacing:1px;color:var(--dim)}
.av-0{background:linear-gradient(135deg,#B45309,#FCD34D)}.av-1{background:linear-gradient(135deg,#BE185D,#F472B6)}.av-2{background:linear-gradient(135deg,#1D4ED8,#60A5FA)}.av-3{background:linear-gradient(135deg,#065F46,#34D399)}.av-4{background:linear-gradient(135deg,#7C3AED,#A78BFA)}.av-5{background:linear-gradient(135deg,#0E7490,#22D3EE)}"""

JS_FUNCS = """
let _lcChartInited = false;
function chgBadge(v, isPct) {
  if (v === null || v === undefined) return '';
  const color = v >= 0 ? '#16A34A' : '#DC2626';
  const arrow = v >= 0 ? '↑' : '↓';
  const val = isPct ? Math.abs(v).toFixed(2) + 'pp' : Math.abs(v).toFixed(1) + '%';
  return `<span style="font-size:10px;color:${color};margin-left:5px;font-family:var(--mono)">${arrow}${val}</span>`;
}
function toggleColl(head) {
  const body = head.nextElementSibling;
  const arrow = head.querySelector('.coll-arrow');
  body.classList.toggle('open');
  arrow.classList.toggle('open');
  if (body.classList.contains('open') && !_lcChartInited && document.getElementById('lifecycleChart')) {
    _lcChartInited = true; initLcChart();
  }
  if (body.classList.contains('open') && document.getElementById('trendTotalChart') && !trendTotalChart) {
    buildTrendCharts();
  }
}
function renderAgentPanel(name) {
  const d = agentPanelData[name];
  const av = AVATAR_MAP[name] || 'av-2';
  const rankColors = ['#1E40AF','#0D9488','#D97706','#64748B','#64748B','#64748B','#64748B','#64748B','#64748B','#64748B'];
  const prodOrder = ['9元李博', '199双科'];
  function renderTopItems(items) {
    return items.map((t,i) => {
      const lk = t.url ? `<a href="${t.url}" target="_blank" class="mat-link">▶ 预览</a>` : '';
      const hasPrev = !!prevMatStats[t.name];
      const tBtn = hasPrev ? `<button onclick="toggleOuterTrend(this,this.dataset.mat)" data-mat="${t.name.replace(/"/g,'&quot;')}" style="font-size:10px;padding:2px 8px;border:1px solid var(--border2);border-radius:4px;background:var(--surface);cursor:pointer;color:var(--muted);margin-left:6px">走势</button>` : '';
      return `<div class="top-item-row">
        <span class="top-rank-badge" style="background:${rankColors[i]||'#64748B'};color:#fff;flex-shrink:0;width:22px;height:22px;border-radius:6px;display:flex;align-items:center;justify-content:center;font-family:var(--mono);font-size:11px;font-weight:600">${i+1}</span>
        <div class="top-item-body">
          <div class="top-item-name" title="${t.name}">${t.name}</div>
          <div class="top-item-meta">${t.meta} ${lk}${tBtn}</div>
        </div>
      </div>
      <div class="outer-trend-expand" data-mat="${t.name.replace(/"/g,'&quot;')}" style="display:none;padding:8px 0 4px 32px"></div>`;
    }).join('');
  }
  let top10Section = '';
  if (d.prodTop10) {
    prodOrder.forEach(ptag => {
      const items = d.prodTop10[ptag];
      if (!items || !items.length) return;
      top10Section += `<div style="font-size:13px;font-weight:700;color:var(--ink);margin:14px 0 8px">成交 TOP 10 · ${ptag}</div>`;
      top10Section += `<div class="top-list">${renderTopItems(items)}</div>`;
    });
  }
  if (!top10Section) {
    top10Section = `<div style="font-size:13px;font-weight:700;color:var(--ink);margin-bottom:10px">成交 TOP 10</div><div class="top-list">${renderTopItems(d.top10)}</div>`;
  }
  return `<div class="dir-panel-head">
    <div class="dir-panel-avatar ${av}">${name[0]}</div>
    <div><div class="dir-panel-name">${name}</div><div class="dir-panel-sub">${d.rank}</div></div>
  </div>
  <div class="dir-panel-body">
    <div class="panel-metrics">
      <div class="pm-card"><div class="pm-label">消耗</div><div class="pm-val amber">${d.consume}${d.chg ? chgBadge(d.chg.consume) : ''}</div></div>
      <div class="pm-card"><div class="pm-label">GMV</div><div class="pm-val">${d.gmv}</div></div>
      <div class="pm-card"><div class="pm-label">订单</div><div class="pm-val">${d.orders}${d.chg ? chgBadge(d.chg.orders) : ''}</div></div>
      <div class="pm-card"><div class="pm-label">有消耗素材</div><div class="pm-val">${d.mat}</div></div>
      <div class="pm-card"><div class="pm-label">平均 CTR</div><div class="pm-val">${d.ctr.toFixed(2)}%${d.chg ? chgBadge(d.chg.ctr, true) : ''}</div></div>
      <div class="pm-card"><div class="pm-label">平均 CVR</div><div class="pm-val">${d.cvr.toFixed(2)}%${d.chg ? chgBadge(d.chg.cvr, true) : ''}</div></div>
    </div>
    <div class="consume-bar-section">
      <div class="consume-bar-label"><span>消耗占比</span><span>${d.pct}</span></div>
      <div class="consume-bar-bg"><div class="consume-bar-fill" style="width:${d.pctVal}%"></div></div>
    </div>
    ${top10Section}
    <button class="detail-btn" onclick="showDetails('${name}')">查看消耗 TOP 20 →</button>
  </div>`;
}
function selectAgent(name, btn) {
  document.querySelectorAll('.dir-btn').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  const panel = document.getElementById('agent-panel');
  const overview = document.getElementById('agent-overview');
  if (name === 'all') { panel.style.display='none'; overview.style.display='block'; }
  else { panel.innerHTML = renderAgentPanel(name); panel.style.display='block'; overview.style.display='none'; }
}
const bucketKeys = ['1-7天','8-14天','15-30天','30天以上'];
const bkColors = ['#0D9488','#3B82F6','#D97706','#E11D48'];
let lcChart = null;
function initLcChart() {
  if (lcChart) return;
  lcChart = new Chart(document.getElementById('lifecycleChart'), {
    type: 'bar',
    data: { labels: bucketKeys, datasets: [{ data: bucketKeys.map(k => lifecycleBuckets[k].length), backgroundColor: bkColors, borderRadius: 4, borderSkipped: false }] },
    options: { indexAxis: 'y', responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } }, scales: { x: { grid: { display: false }, ticks: { font: { family: 'JetBrains Mono', size: 10 } } }, y: { grid: { display: false }, ticks: { font: { family: 'JetBrains Mono', size: 10 } } } } }
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
    return `<div class="mat-row"><span class="mat-rname" title="${m.素材名称}">${m.素材名称}</span><span class="mat-rmeta">${m.代理商} · ¥${m.总消耗.toLocaleString('zh-CN',{maximumFractionDigits:0})} · ${m.总单量}单</span>${lk}</div>`;
  }).join('');
}
const chartColors = ['#D97706','#1D4ED8','#7C3AED','#065F46','#0E7490','#BE185D','#B45309'];
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
    data: { labels: agents, datasets: [{ data: allProductData[key], backgroundColor: agents.map((_,j)=>chartColors[j%chartColors.length]), borderRadius: 4, borderSkipped: false }] },
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
    row.cells[1].textContent = '¥' + (d.consume[i]||0).toLocaleString('zh-CN', {maximumFractionDigits:0});
    row.cells[2].textContent = '¥' + (d.gmv[i]||0).toLocaleString('zh-CN', {maximumFractionDigits:0});
    row.cells[3].textContent = d.orders[i]||0;
    row.cells[4].textContent = d.materials[i]||0;
  });
}
function showDetails(agent) {
  const allDetails = materialDetails[agent] || [];
  const prods = [...new Set(allDetails.map(it => it.投放产品 || '').filter(Boolean))].sort();
  function renderRows(items) {
    return items.map((it,i) => {
      const lk = it.链接 ? `<a href="${it.链接}" target="_blank" class="tbl-link">▶</a>` : '—';
      const prev = prevMatStats[it.素材名称];
      const trendBtn = prev
        ? `<button onclick="toggleTrend(this,'${it.素材名称.replace(/'/g,"\\'")}',${it.总消耗},${it.CTR||0},${it.CVR||0})" style="font-size:10px;padding:2px 8px;border:1px solid var(--border2);border-radius:4px;background:var(--surface);cursor:pointer;color:var(--muted)">走势</button>`
        : '—';
      return `<tr>
        <td class="td-rank">${i+1}</td>
        <td style="max-width:240px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:var(--ink);font-family:var(--font);font-size:13px" title="${it.素材名称}">${it.素材名称}</td>
        <td class="td-num">¥${(it.总消耗||0).toLocaleString('zh-CN',{maximumFractionDigits:0})}</td>
        <td class="td-num">¥${(it.总GMV||0).toLocaleString('zh-CN',{maximumFractionDigits:0})}</td>
        <td class="td-num">${it.总订单||0}</td>
        <td class="td-num">${(it.CTR||0).toFixed(2)}%</td>
        <td class="td-num">${(it.CVR||0).toFixed(2)}%</td>
        <td class="td-num">${it.投放天数??'—'}</td>
        <td>${lk}</td>
        <td>${trendBtn}</td>
      </tr>
      <tr class="trend-row" id="trend-${i}" style="display:none"><td colspan="10" style="padding:0"></td></tr>`;
    }).join('');
  }
  let filterBtns = `<div style="display:flex;gap:6px;flex-wrap:wrap;margin-bottom:14px" id="modal-prod-filter"><button class="pf-btn active" onclick="filterModalProd('all',this)">全部 (${allDetails.length})</button>`;
  prods.forEach(p => { const cnt = allDetails.filter(it => it.投放产品 === p).length; filterBtns += `<button class="pf-btn" onclick="filterModalProd('${p}',this)">${p} (${cnt})</button>`; });
  filterBtns += '</div>';
  const html = `<div class="modal-title">${agent}</div><div class="modal-sub">消耗 TOP 20 素材（按消耗降序）</div>${filterBtns}<div class="tbl-wrap"><div class="tbl-scroll"><table><thead><tr><th></th><th>素材名称</th><th class="td-num">消耗</th><th class="td-num">GMV</th><th class="td-num">订单</th><th class="td-num">CTR</th><th class="td-num">CVR</th><th class="td-num">投放天数</th><th>预览</th><th>走势</th></tr></thead><tbody id="modal-tbody">${renderRows(allDetails)}</tbody></table></div></div>`;
  document.getElementById('modalContent').innerHTML = html;
  document.getElementById('modalBg').style.display = 'block';
  window._modalDetails = allDetails; window._renderRows = renderRows;
}
function toggleTrend(btn, matName, curSpend, curCtr, curCvr) {
  const tr = btn.closest('tr');
  const trendTr = tr.nextElementSibling;
  if (trendTr.style.display !== 'none') { trendTr.style.display = 'none'; btn.textContent = '走势'; return; }
  const prev = prevMatStats[matName] || {};
  const prevSpend = prev.spend || 0;
  const prevCtr   = prev.ctr   || 0;
  const prevCvr   = prev.cvr   || 0;
  function chgStr(cur, prv, isPct) {
    if (!prv) return '';
    const color = cur >= prv ? '#16A34A' : '#DC2626';
    const arrow = cur >= prv ? '↑' : '↓';
    if (isPct) {
      const diff = Math.abs(cur - prv);
      return `<span style="color:${color};font-size:11px"> ${arrow}${diff.toFixed(2)}pp</span>`;
    }
    const p = (cur - prv) / prv * 100;
    return `<span style="color:${color};font-size:11px"> ${arrow}${Math.abs(p).toFixed(1)}%</span>`;
  }
  const canvasId = 'trend-canvas-' + Date.now();
  trendTr.querySelector('td').innerHTML = `
    <div style="padding:12px 16px;background:var(--surface2);border-top:1px solid var(--border)">
      <div style="font-size:11px;color:var(--muted);margin-bottom:10px;font-family:var(--mono)">双周走势对比（${prevDateLabel} → ${curDateLabel}）</div>
      <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:8px">
        <div style="background:var(--surface);border:1px solid var(--border);border-radius:6px;padding:12px">
          <div style="font-size:10px;color:var(--muted);margin-bottom:6px">消耗</div>
          <div style="font-family:var(--mono);font-size:14px;font-weight:600">¥${curSpend.toLocaleString('zh-CN',{maximumFractionDigits:0})}${chgStr(curSpend,prevSpend)}</div>
          <div style="font-family:var(--mono);font-size:10px;color:var(--muted);margin-top:4px">上周 ¥${prevSpend.toLocaleString('zh-CN',{maximumFractionDigits:0})}</div>
        </div>
        <div style="background:var(--surface);border:1px solid var(--border);border-radius:6px;padding:12px">
          <div style="font-size:10px;color:var(--muted);margin-bottom:6px">CTR</div>
          <div style="font-family:var(--mono);font-size:14px;font-weight:600">${curCtr.toFixed(2)}%${chgStr(curCtr,prevCtr,true)}</div>
          <div style="font-family:var(--mono);font-size:10px;color:var(--muted);margin-top:4px">上周 ${prevCtr.toFixed(2)}%</div>
        </div>
        <div style="background:var(--surface);border:1px solid var(--border);border-radius:6px;padding:12px">
          <div style="font-size:10px;color:var(--muted);margin-bottom:6px">CVR</div>
          <div style="font-family:var(--mono);font-size:14px;font-weight:600">${curCvr.toFixed(2)}%${chgStr(curCvr,prevCvr,true)}</div>
          <div style="font-family:var(--mono);font-size:10px;color:var(--muted);margin-top:4px">上周 ${prevCvr.toFixed(2)}%</div>
        </div>
      </div>
    </div>`;
  trendTr.style.display = '';
  btn.textContent = '收起';
}
function filterModalProd(prod, btn) {
  document.querySelectorAll('#modal-prod-filter .pf-btn').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  const items = prod === 'all' ? window._modalDetails : window._modalDetails.filter(it => it.投放产品 === prod);
  document.getElementById('modal-tbody').innerHTML = window._renderRows(items);
}
function closeModal() { document.getElementById('modalBg').style.display = 'none'; }
window.addEventListener('click', e => { if (e.target === document.getElementById('modalBg')) closeModal(); });

// ── TOP10 外部走势展开 ────────────────────────────────────────
function toggleOuterTrend(btn, matName) {
  const mat = matName || btn.dataset.mat;
  const row = btn.closest('.top-item-row');
  const expandDiv = row.nextElementSibling;
  if (expandDiv.style.display !== 'none') {
    expandDiv.style.display = 'none'; btn.textContent = '走势'; return;
  }
  const prev = prevMatStats[mat] || {};
  const allDet = Object.values(materialDetails).flat();
  const cur = allDet.find(it => it.素材名称 === mat) || {};
  const curSpend = cur.总消耗||0, curOrders = cur.总订单||0;
  const curCtr = cur.CTR||0, curCvr = cur.CVR||0;
  const prevSpend = prev.spend||0, prevOrders = prev.orders||0;
  const prevCtr = prev.ctr||0, prevCvr = prev.cvr||0;
  function chgS(cur, prv, isPct) {
    if (!prv) return '';
    const color = cur >= prv ? '#16A34A' : '#DC2626';
    const arrow = cur >= prv ? '↑' : '↓';
    const val = isPct ? Math.abs(cur-prv).toFixed(2)+'pp' : Math.abs((cur-prv)/prv*100).toFixed(1)+'%';
    return '<span style="color:'+color+';font-size:10px"> '+arrow+val+'</span>';
  }
  expandDiv.innerHTML =
    '<div style="background:var(--surface2);border:1px solid var(--border);border-radius:6px;padding:10px;margin-bottom:4px">' +
    '<div style="font-size:10px;color:var(--muted);margin-bottom:8px;font-family:var(--mono)">'+prevDateLabel+' → '+curDateLabel+'</div>' +
    '<div style="display:grid;grid-template-columns:repeat(4,1fr);gap:6px">' +
    '<div style="background:var(--surface);border:1px solid var(--border);border-radius:4px;padding:8px"><div style="font-size:9px;color:var(--muted);margin-bottom:3px">消耗</div><div style="font-family:var(--mono);font-size:12px;font-weight:600">¥'+curSpend.toLocaleString('zh-CN',{maximumFractionDigits:0})+chgS(curSpend,prevSpend,false)+'</div><div style="font-family:var(--mono);font-size:9px;color:var(--muted)">上周 ¥'+prevSpend.toLocaleString('zh-CN',{maximumFractionDigits:0})+'</div></div>' +
    '<div style="background:var(--surface);border:1px solid var(--border);border-radius:4px;padding:8px"><div style="font-size:9px;color:var(--muted);margin-bottom:3px">成交</div><div style="font-family:var(--mono);font-size:12px;font-weight:600">'+curOrders+'单'+chgS(curOrders,prevOrders,false)+'</div><div style="font-family:var(--mono);font-size:9px;color:var(--muted)">上周 '+prevOrders+'单</div></div>' +
    '<div style="background:var(--surface);border:1px solid var(--border);border-radius:4px;padding:8px"><div style="font-size:9px;color:var(--muted);margin-bottom:3px">CTR</div><div style="font-family:var(--mono);font-size:12px;font-weight:600">'+curCtr.toFixed(2)+'%'+chgS(curCtr,prevCtr,true)+'</div><div style="font-family:var(--mono);font-size:9px;color:var(--muted)">上周 '+prevCtr.toFixed(2)+'%</div></div>' +
    '<div style="background:var(--surface);border:1px solid var(--border);border-radius:4px;padding:8px"><div style="font-size:9px;color:var(--muted);margin-bottom:3px">CVR</div><div style="font-family:var(--mono);font-size:12px;font-weight:600">'+curCvr.toFixed(2)+'%'+chgS(curCvr,prevCvr,true)+'</div><div style="font-family:var(--mono);font-size:9px;color:var(--muted)">上周 '+prevCvr.toFixed(2)+'%</div></div>' +
    '</div></div>';
  expandDiv.style.display = 'block';
  btn.textContent = '收起';
}

const trendWeeks = Object.keys(histTrend).sort();
const trendColors = ['#D97706','#1D4ED8','#7C3AED','#065F46','#0E7490','#BE185D','#B45309'];
let trendMetric = 'spend';
let trendTotalChart = null, trendAgentChart = null;

const metricLabel = { spend: '消耗（元）', orders: '订单数', ctr: 'CTR %', cvr: 'CVR %' };
const metricFmt = {
  spend:  v => '¥' + v.toLocaleString('zh-CN', {maximumFractionDigits:0}),
  orders: v => v + '单',
  ctr:    v => v.toFixed(2) + '%',
  cvr:    v => v.toFixed(2) + '%',
};

function buildTrendCharts() {
  if (!trendWeeks.length) return;
  const totalData = trendWeeks.map(w => histTrend[w]['__total__']?.[trendMetric] ?? 0);
  const totalOpts = {
    type: 'line',
    data: { labels: trendWeeks, datasets: [{ label: '整体', data: totalData,
      borderColor: '#D97706', backgroundColor: 'rgba(217,119,6,0.08)',
      borderWidth: 2, pointRadius: 4, fill: true, tension: 0.3 }] },
    options: { responsive:true, maintainAspectRatio:false,
      plugins: { legend:{display:false}, tooltip:{callbacks:{label: c => metricFmt[trendMetric](c.raw)}} },
      scales: { x:{grid:{display:false},ticks:{font:{size:10}}}, y:{grid:{color:'rgba(0,0,0,0.04)'},ticks:{font:{size:10}}} } }
  };
  if (trendTotalChart) { trendTotalChart.destroy(); }
  trendTotalChart = new Chart(document.getElementById('trendTotalChart'), totalOpts);

  const agentDatasets = agents.map((a, i) => ({
    label: a,
    data: trendWeeks.map(w => histTrend[w]?.[a]?.[trendMetric] ?? 0),
    borderColor: trendColors[i % trendColors.length],
    backgroundColor: 'transparent',
    borderWidth: 2, pointRadius: 3, tension: 0.3,
  }));
  const agentOpts = {
    type: 'line',
    data: { labels: trendWeeks, datasets: agentDatasets },
    options: { responsive:true, maintainAspectRatio:false,
      plugins: { legend:{position:'bottom',labels:{font:{size:10},boxWidth:10}},
                 tooltip:{callbacks:{label: c => c.dataset.label + ': ' + metricFmt[trendMetric](c.raw)}} },
      scales: { x:{grid:{display:false},ticks:{font:{size:10}}}, y:{grid:{color:'rgba(0,0,0,0.04)'},ticks:{font:{size:10}}} } }
  };
  if (trendAgentChart) { trendAgentChart.destroy(); }
  trendAgentChart = new Chart(document.getElementById('trendAgentChart'), agentOpts);
}

function switchTrendMetric(metric, btn) {
  document.querySelectorAll('#trendMetricFilter .pf-btn').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  trendMetric = metric;
  buildTrendCharts();
}

"""


def generate_html(agent_stats, global_analysis, js_data, date_label,
                  prev_agent_stats=None, prev_date='', hist_trend=None):
    if prev_agent_stats is None: prev_agent_stats = {}
    if hist_trend is None: hist_trend = {}
    agents       = js_data['agents']
    total_consume = sum(agent_stats[a]['总消耗'] for a in agents)
    total_gmv     = sum(agent_stats[a]['总GMV']   for a in agents)
    total_orders  = sum(agent_stats[a]['总订单']  for a in agents)
    total_mats    = sum(agent_stats[a]['有消耗素材数'] for a in agents)

    lc    = global_analysis['lifecycle_buckets']
    nw    = global_analysis['new_this_week']
    total_w_consume = global_analysis['total_with_consume']

    mm = date_label[:2]
    dd = date_label[2:]
    date_display = f'2026/{mm}/{dd}'
    date_sub     = f'AGENT MATERIAL REPORT · 2026.{mm}.{dd}'

    sidebar_html  = _render_sidebar_buttons(agents, agent_stats)
    lc_bk_html    = _render_lc_buckets_html(lc, total_w_consume)
    nw_html       = _render_new_week_items(nw)
    comp_tbl_html = _render_compare_table_rows(agents, agent_stats)
    pf_btns_html  = _render_prod_filter_buttons(js_data['productData'])

    # JS data
    avatar_map_js   = json.dumps(AVATAR_MAP, ensure_ascii=False)
    apd_js          = json.dumps(js_data['agentPanelData'], ensure_ascii=False)
    lc_js           = json.dumps(js_data['lifecycleBuckets'], ensure_ascii=False)
    agents_js       = json.dumps(agents, ensure_ascii=False)
    all_prod_js     = json.dumps(js_data['allProductData'], ensure_ascii=False)
    prod_data_js    = json.dumps(js_data['productData'], ensure_ascii=False)
    mat_details_js  = json.dumps(js_data['materialDetails'], ensure_ascii=False)
    prev_mat_js     = json.dumps(js_data.get('prevMatStats', {}), ensure_ascii=False)
    prev_date_js    = json.dumps(prev_date, ensure_ascii=False)
    hist_trend_js   = json.dumps(hist_trend, ensure_ascii=False)

    # 顶部双周对比 KPI（全局）
    prev_total_consume = sum(prev_agent_stats[a]['总消耗'] for a in prev_agent_stats) if prev_agent_stats else 0
    prev_total_orders  = sum(prev_agent_stats[a]['总订单'] for a in prev_agent_stats) if prev_agent_stats else 0
    prev_total_ctr     = (sum(prev_agent_stats[a]['平均CTR'] for a in prev_agent_stats) / len(prev_agent_stats)) if prev_agent_stats else 0
    prev_total_cvr     = (sum(prev_agent_stats[a]['平均CVR'] for a in prev_agent_stats) / len(prev_agent_stats)) if prev_agent_stats else 0
    total_imp          = sum(agent_stats[a].get('总展示', 0) for a in agents)
    total_click        = sum(agent_stats[a].get('总点击', 0) for a in agents)
    total_conv_click   = sum(agent_stats[a].get('总转化', 0) for a in agents)
    cur_total_ctr      = total_click / total_imp * 100 if total_imp else 0
    cur_total_cvr      = total_conv_click / total_click * 100 if total_click else 0
    prev_imp           = sum(prev_agent_stats[a].get('总展示', 0) for a in prev_agent_stats) if prev_agent_stats else 0
    prev_click         = sum(prev_agent_stats[a].get('总点击', 0) for a in prev_agent_stats) if prev_agent_stats else 0
    prev_conv_click    = sum(prev_agent_stats[a].get('总转化', 0) for a in prev_agent_stats) if prev_agent_stats else 0
    prev_total_ctr     = prev_click / prev_imp * 100 if prev_imp else 0
    prev_total_cvr     = prev_conv_click / prev_click * 100 if prev_click else 0

    def _chg_html(cur, prv):
        if not prv: return ''
        pct = (cur - prv) / prv * 100
        color = '#16A34A' if pct >= 0 else '#DC2626'
        arrow = '↑' if pct >= 0 else '↓'
        return f'<span style="font-size:11px;color:{color};margin-left:6px">{arrow}{abs(pct):.1f}%</span>'

    def _chg_ppt(diff):
        color = '#16A34A' if diff >= 0 else '#DC2626'
        arrow = '↑' if diff >= 0 else '↓'
        return f'<span style="font-size:11px;color:{color};margin-left:6px">{arrow}{abs(diff):.2f}pp</span>'

    kpi_chg_consume = _chg_html(total_consume, prev_total_consume) if prev_agent_stats else ''
    kpi_chg_orders  = _chg_html(total_orders,  prev_total_orders)  if prev_agent_stats else ''
    kpi_chg_ctr     = _chg_ppt(cur_total_ctr - prev_total_ctr)     if prev_agent_stats else ''
    kpi_chg_cvr     = _chg_ppt(cur_total_cvr - prev_total_cvr)     if prev_agent_stats else ''
    prev_label      = f'vs {prev_date}' if prev_date else ''

    compare_thead = '<th>代理商</th><th style="text-align:right">消耗</th><th style="text-align:right">GMV</th><th style="text-align:right">订单</th><th style="text-align:right">有消耗素材</th><th style="text-align:right">有成交素材</th><th style="text-align:right">平均投放天数</th>'

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>代理商数据分析 · {date_display}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<style>{CSS}</style>
</head>
<body>
<div class="wrap">

<div class="topbar">
  <div class="topbar-left">
    <div class="topbar-logo">代</div>
    <div>
      <div class="topbar-title">代理商数据分析</div>
      <div class="topbar-sub">{date_sub}</div>
    </div>
  </div>
  <span class="badge">数据截至 {date_display}</span>
</div>

<div class="kpi-row">
  <div class="kpi-card"><div class="kpi-label">总消耗</div><div class="kpi-val">{_fmt_wan(total_consume)}{kpi_chg_consume}</div>{'<div style="font-size:10px;color:var(--muted);margin-top:4px;font-family:var(--mono)">'+prev_label+'</div>' if prev_label else ''}</div>
  <div class="kpi-card"><div class="kpi-label">总 GMV</div><div class="kpi-val">{_fmt_wan(total_gmv)}</div></div>
  <div class="kpi-card"><div class="kpi-label">总订单</div><div class="kpi-val">{total_orders:,}{kpi_chg_orders}</div></div>
  <div class="kpi-card"><div class="kpi-label">有消耗素材</div><div class="kpi-val">{total_mats:,}</div></div>
  <div class="kpi-card"><div class="kpi-label">平均 CTR</div><div class="kpi-val">{cur_total_ctr:.2f}%{kpi_chg_ctr}</div></div>
  <div class="kpi-card"><div class="kpi-label">平均 CVR</div><div class="kpi-val">{cur_total_cvr:.2f}%{kpi_chg_cvr}</div></div>
</div>

<div class="main-layout">
  <div class="dir-sidebar">
    <div class="dir-sidebar-head">选择代理商</div>
    {sidebar_html}
  </div>
  <div>
    <div class="dir-panel" id="agent-panel" style="display:none"></div>
    <div id="agent-overview">

      <div class="collapsible">
        <div class="coll-head" onclick="toggleColl(this)">
          <div class="coll-title">素材生命周期 <span class="coll-badge" style="background:#DCFCE7;color:#166534">{total_w_consume} 条</span></div>
          <span class="coll-arrow">▼</span>
        </div>
        <div class="coll-body">
          <div class="lc-buckets">{lc_bk_html}</div>
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
              <span class="new-week-badge">{len(nw)} 条</span>
            </div>
            <div class="new-week-sub">首次消耗时间在 {_fmt_date_label(WEEK_START)} - {_fmt_date_label(WEEK_END)}（占有消耗素材 {len(nw)/total_w_consume*100:.0f}%）</div>
            <div class="new-week-list">{nw_html}</div>
          </div>
        </div>
      </div>

      <div class="sec-label">历史趋势</div>
      <div class="collapsible" style="margin-bottom:20px">
        <div class="coll-head" onclick="toggleColl(this)">
          <div class="coll-title">多周趋势 <span class="coll-badge" style="background:#DBEAFE;color:#1E3A8A">{len(hist_trend)} 期</span></div>
          <span class="coll-arrow">▼</span>
        </div>
        <div class="coll-body">
          <div style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:14px" id="trendMetricFilter">
            <button class="pf-btn active" onclick="switchTrendMetric('spend',this)">消耗</button>
            <button class="pf-btn" onclick="switchTrendMetric('orders',this)">订单</button>
            <button class="pf-btn" onclick="switchTrendMetric('ctr',this)">CTR</button>
            <button class="pf-btn" onclick="switchTrendMetric('cvr',this)">CVR</button>
          </div>
          <div class="charts-grid">
            <div class="chart-box">
              <div class="chart-title">整体趋势</div>
              <div class="chart-canvas"><canvas id="trendTotalChart"></canvas></div>
            </div>
            <div class="chart-box">
              <div class="chart-title">分代理商趋势</div>
              <div class="chart-canvas"><canvas id="trendAgentChart"></canvas></div>
            </div>
          </div>
        </div>
      </div>

      <div class="sec-label">对比分析</div>
      <div style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:14px">
        {pf_btns_html}
      </div>
      <div class="charts-grid" style="margin-bottom:20px">
        <div class="chart-box"><div class="chart-title">消耗（元）</div><div class="chart-canvas"><canvas id="consumeChart"></canvas></div></div>
        <div class="chart-box"><div class="chart-title">GMV（元）</div><div class="chart-canvas"><canvas id="gmvChart"></canvas></div></div>
        <div class="chart-box"><div class="chart-title">订单数</div><div class="chart-canvas"><canvas id="ordersChart"></canvas></div></div>
        <div class="chart-box"><div class="chart-title">有消耗素材数</div><div class="chart-canvas"><canvas id="materialsChart"></canvas></div></div>
      </div>

      <div class="sec-label">代理商对比</div>
      <div class="tbl-wrap"><div class="tbl-scroll">
        <table>
          <thead><tr>{compare_thead}</tr></thead>
          <tbody id="compareTableBody">{comp_tbl_html}</tbody>
        </table>
      </div></div>

    </div>
  </div>
</div>

<div class="modal-bg" id="modalBg">
  <div class="modal-box">
    <button class="modal-close" onclick="closeModal()">✕</button>
    <div id="modalContent"></div>
  </div>
</div>

<div class="footer">Generated {datetime.now().strftime('%Y-%m-%d %H:%M')} · 代理商数据分析报告 {date_label}</div>
</div>

<script>
const AVATAR_MAP = {avatar_map_js};
const agentPanelData = {apd_js};
const lifecycleBuckets = {lc_js};
const agents = {agents_js};
const allProductData = {all_prod_js};
const productData = {prod_data_js};
const materialDetails = {mat_details_js};
const prevMatStats = {prev_mat_js};
const prevDateLabel = {prev_date_js};
const curDateLabel = '{date_label}';
const histTrend = {hist_trend_js};
{JS_FUNCS}
</script>
</body>
</html>"""


def main():
    rows = read_data(DATA_FILE)
    print(f'✓ 已读取 {len(rows)} 行数据')
    agent_stats, global_analysis, ap_stats = analyze(rows)

    # ── 上期数据（双周对比）──────────────────────────────────
    prev_agent_stats = {}
    prev_mat_stats = {}
    if PREV_FILE and os.path.exists(PREV_FILE):
        prev_rows = read_data(PREV_FILE)
        prev_agent_stats, _, _ = analyze(prev_rows)
        _ps = defaultdict(lambda: {'spend':0,'ctr_sum':0,'cvr_sum':0,'orders':0,'n':0,'imp':0,'click':0,'conv':0})
        for r in prev_rows:
            mat = r.get('素材名称','').strip()
            if not mat: continue
            def _pn(s):
                try: return float(str(s).replace(',','').replace('%','') or 0)
                except: return 0.0
            sp = _pn(r.get('消耗',0))
            _ps[mat]['spend']  += sp
            _ps[mat]['orders'] += _pn(r.get('成交单量',0))
            if sp > 0:
                cpm = _pn(r.get('CPM（千次曝光成本）',0))
                ctr = _pn(r.get('CTR',0))
                cvr = _pn(r.get('CVR',0))
                if cpm > 0:
                    imp = sp/cpm*1000; click = imp*ctr/100; conv = click*cvr/100
                    _ps[mat]['imp'] += imp; _ps[mat]['click'] += click; _ps[mat]['conv'] += conv
        for mat, s in _ps.items():
            prev_mat_stats[mat] = {
                'spend':  round(s['spend'], 2),
                'orders': int(s['orders']),
                'ctr':    round(s['click']/s['imp']*100, 2) if s['imp'] else 0,
                'cvr':    round(s['conv']/s['click']*100, 2) if s['click'] else 0,
            }
        print(f'✓ 已读取上期数据: {PREV_FILE}')

    # ── 历史趋势：扫描所有历史期 CSV ──────────────────────────
    import glob, re as _re
    hist_files = sorted(glob.glob('data/【周报】投后素材看板数据-代理-????.csv'))
    hist_trend = {}   # week_label -> {agent -> {spend,orders,ctr,cvr}, 'total' -> {...}}
    for fpath in hist_files:
        m = _re.search(r'代理-(\d{4})\.csv', fpath)
        if not m: continue
        wlabel = m.group(1)
        try:
            wrows = read_data(fpath)
            wstats, _, _ = analyze(wrows)
            week_entry = {}
            for a, s in wstats.items():
                week_entry[a] = {
                    'spend':  round(s['总消耗'], 0),
                    'orders': s['总订单'],
                    'ctr':    round(s['平均CTR'], 2),
                    'cvr':    round(s['平均CVR'], 2),
                }
            # 全局合计
            t_imp   = sum(s['总展示'] for s in wstats.values())
            t_click = sum(s['总点击'] for s in wstats.values())
            t_conv  = sum(s['总转化'] for s in wstats.values())
            week_entry['__total__'] = {
                'spend':  round(sum(s['总消耗'] for s in wstats.values()), 0),
                'orders': sum(s['总订单'] for s in wstats.values()),
                'ctr':    round(t_click/t_imp*100, 2) if t_imp else 0,
                'cvr':    round(t_conv/t_click*100, 2) if t_click else 0,
            }
            hist_trend[wlabel] = week_entry
        except Exception as e:
            print(f'  跳过 {fpath}: {e}')
    print(f'✓ 历史趋势: {len(hist_trend)} 期')

    js_data = build_js_data(agent_stats, global_analysis, ap_stats,
                            prev_agent_stats, prev_mat_stats)
    html = generate_html(agent_stats, global_analysis, js_data, DATE,
                         prev_agent_stats, PREV_DATE, hist_trend)
    os.makedirs(os.path.dirname(OUT_FILE), exist_ok=True)
    with open(OUT_FILE, 'w', encoding='utf-8') as f:
        f.write(html)
    total = sum(agent_stats[a]['总消耗'] for a in js_data['agents'])
    print(f'✓ 报告已生成: {OUT_FILE}')
    print(f'  代理商: {len(js_data["agents"])} 家 · 总消耗 ¥{total:,.0f} · 本周新起量 {len(global_analysis["new_this_week"])} 条')


if __name__ == '__main__':
    main()
