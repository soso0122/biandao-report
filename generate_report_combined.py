#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
编导数据分析 — 历史汇总 + 近7天周报 合并版
"""

import csv, json
from collections import defaultdict
from datetime import datetime

WEEK_START = '2026/8/29'   # 近7天起始日期
HIST_START = '2026/5/1'   # 历史数据起始（首次消耗时间 >= 此日期）

def tag_prod(prod_name):
    n = prod_name or ''
    if '李博' in n or '物理' in n:
        return '9元李博'
    if '199' in n or '双科' in n:
        return '199双科'
    return n or '其他'


NAME_MAP = {
    '子矜': '子衿', '贾子矜': '子衿',
    '魏嘉丽': '嘉丽', '杜浩正': '浩正',
    '王雅迪': '雅迪', '曲敏': '小敏', '吴婷玉': '婷玉'
}


def norm(name):
    return NAME_MAP.get(name.strip(), name.strip())


def read_upload(path):
    rows = []
    with open(path, encoding='utf-8-sig') as f:
        for r in csv.DictReader(f):
            rows.append(r)
    return rows


def read_delivery(path, week_only=False, since=None):
    rows = []
    with open(path, encoding='utf-8-sig') as f:
        for r in csv.DictReader(f):
            if not (r.get('编导确认', '').strip()
                    and r.get('是否自产自投', '').strip() == '是'
                    and r.get('是否混剪', '').strip() == '否'):
                continue
            ft = r.get('首次消耗时间', '').strip()
            if week_only:
                if not ft or ft == '-' or ft < WEEK_START:
                    continue
            if since:
                if not ft or ft == '-' or ft < since:
                    continue
            rows.append(r)
    return rows


def analyze(upload_rows, delivery_rows, week_start=None):
    # ── 上传统计
    upload_stats = defaultdict(lambda: {
        '唯一素材数': 0, '总上传数': 0,
        '新素材数': 0, '拒审后二次上传数': 0,
        '未同步': 0, '已同步': 0, '已投放': 0,
    })
    umat = defaultdict(set)
    for r in upload_rows:
        d = norm(r.get('编导', ''))
        if not d:
            continue
        umat[d].add(r.get('文件命名', ''))
        s = upload_stats[d]
        s['总上传数'] += 1
        ut = r.get('上传类型', '')
        if ut == '新素材':
            s['新素材数'] += 1
        elif ut == '拒审后二次上传':
            s['拒审后二次上传数'] += 1
        st = r.get('状态', '')
        if st == '未同步': s['未同步'] += 1
        elif st == '已同步': s['已同步'] += 1
        elif st == '已投放': s['已投放'] += 1
    for d in umat:
        upload_stats[d]['唯一素材数'] = len(umat[d])

    # ── 投放统计
    d_stats = defaultdict(lambda: {
        '总消耗': 0.0, '总GMV': 0.0, '总单量': 0,
        '有消耗': 0, '有成交': 0, '均投放天数': 0.0,
        '素材详情': [],
    })
    d_product = defaultdict(lambda: defaultdict(int))
    mat_records = defaultdict(list)
    mat_first = {}
    mat_days = {}

    for r in delivery_rows:
        d = norm(r.get('编导确认', ''))
        if not d:
            continue
        mname = r.get('素材名称', '')
        mlink = r.get('素材预览', '')
        prod = r.get('投放产品', '')
        ft = r.get('首次消耗时间', '').strip()
        ds = r.get('已上线投放天数', '').strip()
        key = d + '###' + mname

        if key not in mat_first and ft and ft != '-':
            mat_first[key] = ft
        if key not in mat_days and ds and ds != '-':
            try: mat_days[key] = int(ds)
            except ValueError: pass

        try:
            c = float(r.get('消耗', 0) or 0)
            g = float(r.get('成交GMV', 0) or 0)
            o = int(float(r.get('成交单量', 0) or 0))
            d_stats[d]['总消耗'] += c
            d_stats[d]['总GMV'] += g
            d_stats[d]['总单量'] += o
            if o > 0 and prod:
                d_product[d][prod] += o
            mat_records[key].append({'消耗': c, 'GMV': g, '单量': o, '链接': mlink, '产品': prod})
        except (ValueError, TypeError):
            pass

    for d in d_stats:
        w_c, w_o, days_l = set(), set(), []
        for key, recs in mat_records.items():
            if not key.startswith(d + '###'):
                continue
            mn = key.split('###', 1)[1]
            tc = sum(x['消耗'] for x in recs)
            to = sum(x['单量'] for x in recs)
            tg = sum(x['GMV'] for x in recs)
            if tc > 0:
                w_c.add(mn)
                if key in mat_days: days_l.append(mat_days[key])
            if to > 0: w_o.add(mn)
            lnk = recs[0].get('链接', '')
            prod_list = [x['产品'] for x in recs if x.get('产品')]
            dom_prod = max(set(prod_list), key=prod_list.count) if prod_list else ''
            d_stats[d]['素材详情'].append({
                '素材名称': mn, '总消耗': tc, '总GMV': tg, '总单量': to,
                '链接': lnk, '首消': mat_first.get(key, ''),
                '天数': mat_days.get(key), '产品': dom_prod,
            })
        d_stats[d]['有消耗'] = len(w_c)
        d_stats[d]['有成交'] = len(w_o)
        d_stats[d]['均投放天数'] = sum(days_l) / len(days_l) if days_l else 0

    for d in d_stats:
        # 全局 top3（按单量，不分产品）
        d_stats[d]['Top3'] = sorted(d_stats[d]['素材详情'], key=lambda x: x['总单量'], reverse=True)[:3]
        d_stats[d]['产品成单'] = dict(d_product[d])
        # 按产品分别 top3
        prod_top3 = {}
        for prod_tag in ['9元李博', '199双科']:
            items = [m for m in d_stats[d]['素材详情'] if tag_prod(m.get('产品','')) == prod_tag and m['总单量'] > 0]
            prod_top3[prod_tag] = sorted(items, key=lambda x: x['总单量'], reverse=True)[:3]
        d_stats[d]['产品Top3'] = prod_top3

    # ── 全局素材
    gmat = {}
    for key, recs in mat_records.items():
        d, mn = key.split('###', 1)
        tc = sum(x['消耗'] for x in recs)
        if tc <= 0: continue
        if mn not in gmat:
            prod_list = [x['产品'] for x in recs if x.get('产品')]
            dom_prod = max(set(prod_list), key=prod_list.count) if prod_list else ''
            gmat[mn] = {
                '素材名称': mn, '编导': d, '总消耗': tc,
                '总GMV': sum(x['GMV'] for x in recs),
                '总单量': sum(x['单量'] for x in recs),
                '链接': recs[0].get('链接', ''),
                '首消': mat_first.get(key, ''),
                '天数': mat_days.get(key),
                '产品': dom_prod,
            }
        else:
            gmat[mn]['总消耗'] += tc
            gmat[mn]['总GMV'] += sum(x['GMV'] for x in recs)
            gmat[mn]['总单量'] += sum(x['单量'] for x in recs)

    all_mat = list(gmat.values())

    # 生命周期
    buckets = {'≤7天': [], '8-14天': [], '15-30天': [], '>30天': []}
    for m in all_mat:
        d = m['天数']
        if d is None: continue
        if d <= 7: buckets['≤7天'].append(m)
        elif d <= 14: buckets['8-14天'].append(m)
        elif d <= 30: buckets['15-30天'].append(m)
        else: buckets['>30天'].append(m)

    top20 = sorted(all_mat, key=lambda x: x['总消耗'], reverse=True)[:20]

    return upload_stats, d_stats, {
        'buckets': buckets,
        'top20': top20,
        'total_mat': len(all_mat),
    }


def _fmt(n, prefix='¥'):
    if n >= 10000:
        return f'{prefix}{n/10000:.1f}万'
    return f'{prefix}{n:,.0f}'


def generate_html(
    upload_stats,
    hist_stats, hist_global,
    week_stats, week_global,
    hist_date_range=('', ''),
    output='编导数据分析报告_合并版.html'
):
    all_dirs = sorted(set(list(hist_stats.keys()) + list(week_stats.keys())))
    week_dirs = sorted(week_stats.keys())
    ht_c = sum(s['总消耗'] for s in hist_stats.values())
    ht_g = sum(s['总GMV'] for s in hist_stats.values())
    ht_o = sum(s['总单量'] for s in hist_stats.values())
    ht_m = sum(s['有消耗'] for s in hist_stats.values())
    wk_c = sum(s['总消耗'] for s in week_stats.values())
    wk_g = sum(s['总GMV'] for s in week_stats.values())
    wk_o = sum(s['总单量'] for s in week_stats.values())
    wk_m = sum(s['有消耗'] for s in week_stats.values())

    def build_panel(dirs, stats, tag):
        result = {}
        for d in dirs:
            s = stats.get(d, {})
            us = upload_stats.get(d, {})
            tc = s.get('总消耗', 0)
            tg = s.get('总GMV', 0)
            to_cnt = s.get('总单量', 0)
            prod = s.get('产品成单', {})
            top3 = s.get('Top3', [])
            products = [{'name': pn, 'cnt': f'{pc}单'}
                        for pn, pc in sorted(prod.items(), key=lambda x: -x[1])]
            top3_data = []
            for m in top3:
                top3_data.append({
                    'name': m['素材名称'],
                    'meta': (f'{m["总单量"]}单 · GMV ¥{m["总GMV"]:,.0f}' +
                             (f' · 首消 {m["首消"]}' if m.get('首消') else '')),
                    'url': m.get('链接', '')
                })
            prod_top3_data = {}
            for ptag, items in s.get('产品Top3', {}).items():
                prod_top3_data[ptag] = [
                    {'name': m['素材名称'],
                     'meta': (f'{m["总单量"]}单 · GMV ¥{m["总GMV"]:,.0f}' +
                              (f' · 首消 {m["首消"]}' if m.get('首消') else '')),
                     'url': m.get('链接', '')}
                    for m in items
                ]
            result[d] = {
                'consume': _fmt(tc), 'gmv': _fmt(tg), 'orders': str(to_cnt),
                'mat': f'{s.get("有消耗",0)}/{s.get("有成交",0)}',
                'days': f'{s.get("均投放天数",0):.1f}',
                'upload': f'上传 {us.get("唯一素材数",0)}件' if us else '',
                'newmat': f'新素材 {us.get("新素材数",0)}' if us else '',
                'rejected': f'拒审二传 {us.get("拒审后二次上传数",0)}' if us else '',
                'products': products, 'top3': top3_data, 'prodTop3': prod_top3_data,
                'detailKey': f'{d}___{tag}',
            }
        return result

    hist_panel_data = build_panel(all_dirs, hist_stats, 'hist')
    week_panel_data = build_panel(week_dirs, week_stats, 'week')
    # __AFTER_BUILD_PANEL__

    bk_keys = ['≤7天', '8-14天', '15-30天', '>30天']
    bk_colors_css = ['#0D9488', '#3B82F6', '#D97706', '#E11D48']
    total_mat = hist_global['total_mat']

    lc_buckets_html = ''
    for i, bk in enumerate(bk_keys):
        cnt = len(hist_global['buckets'][bk])
        pct = cnt / total_mat * 100 if total_mat else 0
        lc_buckets_html += (f'<div class="bk-pill" data-idx="{i}" onclick="selectBucket({i})">'
                            f'<div class="bk-label">{bk}</div>'
                            f'<div class="bk-cnt" style="color:{bk_colors_css[i]}">{cnt}</div>'
                            f'<div class="bk-sub">{pct:.0f}% of total</div></div>')

    top20_rows = ''
    for i, m in enumerate(hist_global['top20'], 1):
        lnk = f'<a href="{m["链接"]}" target="_blank" class="tbl-link">▶</a>' if m.get('链接') else '—'
        top20_rows += (f'<tr><td class="rank-cell">{i}</td>'
                       f'<td class="name-cell">{m["素材名称"]}</td>'
                       f'<td class="dir-cell">{m["编导"]}</td>'
                       f'<td class="num-cell">¥{m["总消耗"]:,.0f}</td>'
                       f'<td class="num-cell">¥{m["总GMV"]:,.0f}</td>'
                       f'<td class="num-cell">{m["总单量"]}</td>'
                       f'<td class="num-cell">{m.get("首消","—") or "—"}</td>'
                       f'<td class="num-cell">{str(m["天数"])+"天" if m.get("天数") is not None else "—"}</td>'
                       f'<td>{lnk}</td></tr>')

    week_top20 = sorted(
        [m for s in week_stats.values() for m in s.get('素材详情', [])],
        key=lambda x: x['总消耗'], reverse=True
    )[:20]
    week_top20_rows = ''
    for i, m in enumerate(week_top20, 1):
        lnk = f'<a href="{m["链接"]}" target="_blank" class="tbl-link">▶</a>' if m.get('链接') else '—'
        ptag = tag_prod(m.get('产品', ''))
        pbadge = f'<span class="prod-tag prod-{ptag}">{ptag}</span>'
        week_top20_rows += (f'<tr data-prod="{ptag}">'
                            f'<td class="rank-cell">{i}</td>'
                            f'<td class="name-cell">{m["素材名称"]}</td>'
                            f'<td>{pbadge}</td>'
                            f'<td class="num-cell">¥{m["总消耗"]:,.0f}</td>'
                            f'<td class="num-cell">¥{m["总GMV"]:,.0f}</td>'
                            f'<td class="num-cell">{m["总单量"]}</td>'
                            f'<td class="num-cell">{m.get("首消","—") or "—"}</td>'
                            f'<td class="num-cell">{str(m["天数"])+"天" if m.get("天数") is not None else "—"}</td>'
                            f'<td>{lnk}</td></tr>')

    modal_data = {}
    for d in all_dirs:
        for tag_k, stats_k in [('hist', hist_stats), ('week', week_stats)]:
            key = f'{d}___{tag_k}'
            modal_data[key] = sorted(
                stats_k.get(d, {}).get('素材详情', []),
                key=lambda x: x['总消耗'], reverse=True
            )[:20]

    def mk_si(d, i, tag, stats):
        s = stats.get(d, {})
        tc = s.get('总消耗', 0)
        to_cnt = s.get('总单量', 0)
        av = f'av-{i % 6}'
        ch = d[0] if d else '?'
        safe = d.replace("'", "\\'")
        return (f'<div class="si-item" id="si-{tag}-{safe}" onclick="selectDir(\'{tag}\',\'{safe}\',this)">'
                f'<div class="av {av}">{ch}</div>'
                f'<div class="si-body"><div class="si-name">{d}</div>'
                f'<div class="si-meta">{_fmt(tc)} · {to_cnt}单</div>'
                f'</div></div>')

    hist_sidebar = ''.join(mk_si(d, i, 'hist', hist_stats) for i, d in enumerate(all_dirs))
    week_sidebar = ''.join(mk_si(d, i, 'week', week_stats) for i, d in enumerate(week_dirs))
    # __START_HTML__

    html = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>编导数据分析 · 历史 + 周报</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<style>
:root {{
  --bg:#F1F5F9;--surface:#FFFFFF;--surface2:#F8FAFC;
  --border:#E2E8F0;--border2:#CBD5E1;
  --ink:#0F172A;--ink2:#334155;--muted:#64748B;--dim:#94A3B8;
  --blue:#1E40AF;--blue-l:#3B82F6;--sky:#0EA5E9;
  --amber:#D97706;--amber-l:#F59E0B;--teal:#0D9488;
  --rose:#E11D48;--green:#059669;
  --font:'Plus Jakarta Sans',sans-serif;
  --mono:'JetBrains Mono',monospace;
  --r-sm:8px;--r-md:12px;--r-lg:16px;
}}
*{{margin:0;padding:0;box-sizing:border-box}}
html{{scroll-behavior:smooth}}
body{{font-family:var(--font);background:var(--bg);color:var(--ink);min-height:100vh}}
.wrap{{max-width:1440px;margin:0 auto;padding:32px 24px 80px}}
/* ── TOPBAR ── */
.topbar{{
  background:var(--surface);border:1px solid var(--border);
  border-radius:var(--r-lg);padding:20px 28px;
  display:flex;align-items:center;gap:20px;
  margin-bottom:28px;flex-wrap:wrap;
}}
.logo{{
  width:44px;height:44px;border-radius:var(--r-md);
  background:linear-gradient(135deg,var(--blue),var(--blue-l));
  display:flex;align-items:center;justify-content:center;
  font-family:var(--mono);font-size:18px;font-weight:500;
  color:#fff;flex-shrink:0;
}}
.topbar-info{{flex:1}}
.topbar-title{{font-size:18px;font-weight:700;color:var(--ink)}}
.topbar-sub{{font-family:var(--mono);font-size:10px;letter-spacing:2px;color:var(--muted);margin-top:2px}}
.topbar-badges{{display:flex;gap:8px;flex-wrap:wrap}}
.tb-badge{{
  font-family:var(--mono);font-size:10px;letter-spacing:0.5px;
  padding:4px 10px;border-radius:6px;border:1px solid var(--border2);
  color:var(--muted);background:var(--surface2);
}}
.tb-badge.sky{{color:var(--sky);border-color:#BAE6FD;background:#F0F9FF}}
/* ── KPI ROW ── */
.kpi-row{{display:grid;grid-template-columns:repeat(4,1fr);gap:16px;margin-bottom:28px}}
.kpi-card{{
  background:var(--surface);border:1px solid var(--border);
  border-radius:var(--r-md);padding:24px 20px;
  border-top:3px solid transparent;
}}
.kpi-card.kh{{border-top-color:var(--amber)}}
.kpi-card.kw{{border-top-color:var(--sky)}}
.kpi-tag{{font-family:var(--mono);font-size:10px;letter-spacing:1.5px;color:var(--muted);text-transform:uppercase;margin-bottom:10px}}
.kpi-val{{font-family:var(--mono);font-size:28px;font-weight:600;color:var(--ink);line-height:1;margin-bottom:6px}}
.kpi-lbl{{font-size:12px;color:var(--muted)}}
.kpi-card.kh .kpi-val{{color:var(--amber)}}
.kpi-card.kw .kpi-val{{color:var(--sky)}}
/* __ CSS2__ */
/* ── PANE LAYOUT ── */
.pane-layout{{display:grid;grid-template-columns:220px 1fr;gap:20px;align-items:start}}
/* ── SIDEBAR ── */
.sidebar{{
  background:var(--surface);border:1px solid var(--border);
  border-radius:var(--r-lg);padding:12px;
  position:sticky;top:20px;
}}
.sb-all{{
  display:flex;align-items:center;gap:10px;
  padding:10px 12px;border-radius:var(--r-md);
  cursor:pointer;font-size:13px;font-weight:600;
  color:var(--ink2);border:none;background:none;
  width:100%;text-align:left;transition:background 0.15s;
  margin-bottom:6px;
}}
.sb-all:hover,.sb-all.active{{background:var(--surface2)}}
.sb-all.active{{color:var(--blue);font-weight:700}}
.si-item{{
  display:flex;align-items:center;gap:10px;
  padding:9px 10px;border-radius:var(--r-md);
  cursor:pointer;transition:background 0.15s;
}}
.si-item:hover{{background:var(--surface2)}}
.si-item.active{{background:#EFF6FF}}
.av{{
  width:34px;height:34px;border-radius:50%;
  flex-shrink:0;display:flex;align-items:center;
  justify-content:center;color:#fff;
  font-family:var(--mono);font-size:13px;font-weight:500;
}}
.av-0{{background:linear-gradient(135deg,#7C3AED,#A78BFA)}}
.av-1{{background:linear-gradient(135deg,#BE185D,#F472B6)}}
.av-2{{background:linear-gradient(135deg,#1D4ED8,#60A5FA)}}
.av-3{{background:linear-gradient(135deg,#065F46,#34D399)}}
.av-4{{background:linear-gradient(135deg,#B45309,#FCD34D)}}
.av-5{{background:linear-gradient(135deg,#0E7490,#22D3EE)}}
.si-body{{min-width:0}}
.si-name{{font-size:13px;font-weight:600;color:var(--ink);overflow:hidden;text-overflow:ellipsis;white-space:nowrap}}
.si-meta{{font-family:var(--mono);font-size:10px;color:var(--muted)}}
/* __ CSS3__ */
/* ── CONTENT AREA ── */
.content-area{{min-width:0}}
/* ── COLLAPSIBLE ── */
.coll-wrap{{
  background:var(--surface);border:1px solid var(--border);
  border-radius:var(--r-lg);margin-bottom:16px;overflow:hidden;
}}
.coll-head{{
  display:flex;align-items:center;justify-content:space-between;
  padding:16px 20px;cursor:pointer;
  font-size:14px;font-weight:600;color:var(--ink);
  background:none;border:none;width:100%;text-align:left;
}}
.coll-head:hover{{background:var(--surface2)}}
.coll-arrow{{font-size:12px;color:var(--muted);transition:transform 0.2s}}
.coll-wrap.open .coll-arrow{{transform:rotate(180deg)}}
.coll-body{{display:none;padding:0 20px 20px}}
.coll-wrap.open .coll-body{{display:block}}
/* ── LIFECYCLE ── */
.lc-buckets{{display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin-bottom:16px}}
.bk-pill{{
  background:var(--surface2);border:1px solid var(--border);
  border-radius:var(--r-md);padding:14px 16px;cursor:pointer;
  transition:all 0.15s;
}}
.bk-pill:hover,.bk-pill.active{{border-color:var(--border2);background:#EFF6FF}}
.bk-label{{font-family:var(--mono);font-size:10px;color:var(--muted);margin-bottom:6px}}
.bk-cnt{{font-family:var(--mono);font-size:24px;font-weight:500;line-height:1;margin-bottom:3px}}
.bk-sub{{font-size:10px;color:var(--dim);font-family:var(--mono)}}
.lc-detail-row{{display:flex;gap:20px;align-items:flex-start;margin-top:16px}}
.lc-chart-wrap{{flex:0 0 200px;height:170px;position:relative}}
.lc-mat-list{{flex:1;min-width:0}}
.lc-mat-title{{font-family:var(--mono);font-size:10px;letter-spacing:1px;color:var(--muted);margin-bottom:8px}}
.mat-scroll{{max-height:180px;overflow-y:auto}}
.mat-scroll::-webkit-scrollbar{{width:4px}}
.mat-scroll::-webkit-scrollbar-track{{background:var(--surface2)}}
.mat-scroll::-webkit-scrollbar-thumb{{background:var(--border2);border-radius:2px}}
.mat-row{{display:flex;align-items:center;gap:8px;padding:7px 0;border-bottom:1px solid var(--border);font-size:12px}}
.mat-row:last-child{{border-bottom:none}}
.mat-rname{{flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:var(--ink2)}}
.mat-rmeta{{font-family:var(--mono);font-size:10px;color:var(--muted);white-space:nowrap}}
.mat-link{{color:var(--blue-l);text-decoration:none;font-family:var(--mono);font-size:10px;white-space:nowrap}}
.mat-link:hover{{color:var(--blue)}}
/* __ CSS4__ */
/* ── TABLE ── */
.tbl-wrap{{background:var(--surface);border:1px solid var(--border);border-radius:var(--r-lg);overflow:hidden;}}
.tbl-scroll{{overflow-x:auto}}
table{{width:100%;border-collapse:collapse}}
thead tr{{background:var(--surface2)}}
th{{font-family:var(--mono);font-size:9px;letter-spacing:1.5px;text-transform:uppercase;color:var(--muted);padding:12px 14px;text-align:left;font-weight:400;border-bottom:1px solid var(--border);white-space:nowrap}}
td{{padding:10px 14px;border-bottom:1px solid var(--border);font-family:var(--mono);font-size:12px;color:var(--ink2)}}
tbody tr:hover td{{background:var(--surface2)}}
tbody tr:last-child td{{border-bottom:none}}
.rank-cell{{color:var(--dim);width:32px}}
.name-cell{{color:var(--ink);font-family:var(--font);font-size:12px;max-width:280px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}}
.dir-cell{{color:var(--amber)}}
.num-cell{{text-align:right}}
.tbl-link{{color:var(--teal);text-decoration:none}}
.tbl-link:hover{{color:var(--blue)}}
/* ── PROD FILTER ── */
.prod-filter{{display:flex;gap:6px;margin-bottom:14px}}
.pf-btn{{font-family:var(--mono);font-size:10px;letter-spacing:1px;background:var(--surface);border:1px solid var(--border2);color:var(--muted);padding:5px 14px;border-radius:6px;cursor:pointer;transition:all 0.15s}}
.pf-btn:hover{{color:var(--ink)}}
.pf-btn.active.pf-all{{background:var(--ink);color:#fff;border-color:var(--ink)}}
.pf-btn.active.pf-libo{{background:#FEF3C7;color:var(--amber);border-color:#FDE68A}}
.pf-btn.active.pf-sk{{background:#E0F2FE;color:var(--sky);border-color:#BAE6FD}}
/* ── PROD TAGS ── */
.prod-tag{{display:inline-block;padding:2px 7px;border-radius:4px;font-family:var(--mono);font-size:9px;letter-spacing:1px;white-space:nowrap}}
.prod-9元李博{{background:#FEF3C7;color:var(--amber)}}
.prod-199双科{{background:#E0F2FE;color:var(--sky)}}
.prod-其他{{background:var(--surface2);color:var(--muted)}}
/* ── DIRECTOR PANEL ── */
.dir-panel{{display:none}}
.dir-panel.active{{display:block}}
.dp-header{{
  background:var(--surface);border:1px solid var(--border);
  border-radius:var(--r-lg);padding:20px 24px;margin-bottom:16px;
  display:flex;align-items:center;gap:16px;
}}
.dp-av{{width:52px;height:52px;border-radius:50%;flex-shrink:0;display:flex;align-items:center;justify-content:center;color:#fff;font-family:var(--mono);font-size:20px;font-weight:500}}
.dp-info{{flex:1}}
.dp-name{{font-size:20px;font-weight:700;color:var(--ink);margin-bottom:4px}}
.dp-tag{{font-family:var(--mono);font-size:10px;letter-spacing:1px;color:var(--muted)}}
.dp-metrics{{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin-bottom:16px}}
.dp-metric{{background:var(--surface);border:1px solid var(--border);border-radius:var(--r-md);padding:14px 16px}}
.dp-metric-val{{font-family:var(--mono);font-size:18px;font-weight:500;color:var(--blue);line-height:1;margin-bottom:4px}}
.dp-metric-lbl{{font-size:11px;color:var(--muted)}}
.dp-upload{{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:16px}}
.dp-pill{{font-family:var(--mono);font-size:11px;background:var(--surface2);border:1px solid var(--border);color:var(--ink2);padding:5px 12px;border-radius:20px}}
.dp-section-title{{font-family:var(--mono);font-size:10px;letter-spacing:1.5px;text-transform:uppercase;color:var(--muted);margin-bottom:10px}}
.dp-products{{background:var(--surface);border:1px solid var(--border);border-radius:var(--r-md);overflow:hidden;margin-bottom:16px}}
.dp-prod-row{{display:flex;justify-content:space-between;align-items:center;padding:10px 14px;border-bottom:1px solid var(--border)}}
.dp-prod-row:last-child{{border-bottom:none}}
.dp-prod-name{{font-size:13px;color:var(--ink2)}}
.dp-prod-cnt{{font-family:var(--mono);font-size:12px;font-weight:500;color:var(--amber)}}
.dp-top3{{display:flex;flex-direction:column;gap:8px;margin-bottom:16px}}
.dp-top-item{{background:var(--surface);border:1px solid var(--border);border-radius:var(--r-md);padding:12px 14px;display:flex;align-items:flex-start;gap:12px}}
.dp-top-rank{{width:24px;height:24px;border-radius:6px;background:var(--blue-l);color:#fff;font-family:var(--mono);font-size:11px;font-weight:500;display:flex;align-items:center;justify-content:center;flex-shrink:0}}
.dp-top-body{{flex:1;min-width:0}}
.dp-top-name{{font-size:13px;color:var(--ink);margin-bottom:4px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}}
.dp-top-meta{{font-family:var(--mono);font-size:11px;color:var(--muted)}}
.dp-detail-btn{{background:var(--blue);color:#fff;border:none;padding:10px 20px;border-radius:var(--r-md);font-family:var(--mono);font-size:12px;font-weight:500;cursor:pointer;transition:background 0.15s}}
.dp-detail-btn:hover{{background:var(--blue-l)}}
/* ── CHARTS ── */
.charts-grid{{display:grid;grid-template-columns:repeat(2,1fr);gap:14px;margin-top:16px}}
.chart-box{{background:var(--surface);border:1px solid var(--border);border-radius:var(--r-lg);padding:20px}}
.chart-title{{font-family:var(--mono);font-size:10px;letter-spacing:1.5px;text-transform:uppercase;color:var(--muted);margin-bottom:14px}}
.chart-canvas{{position:relative;height:220px}}
/* ── MODAL ── */
.modal-bg{{display:none;position:fixed;inset:0;background:rgba(15,23,42,0.5);backdrop-filter:blur(4px);z-index:999;padding:20px;overflow-y:auto}}
.modal-box{{background:var(--surface);border:1px solid var(--border2);border-radius:var(--r-lg);max-width:900px;margin:60px auto;padding:28px;position:relative;box-shadow:0 20px 60px rgba(0,0,0,0.15)}}
.modal-title{{font-size:20px;font-weight:700;color:var(--ink);margin-bottom:6px}}
.modal-sub{{font-family:var(--mono);font-size:10px;letter-spacing:1px;color:var(--muted);margin-bottom:20px}}
.modal-close{{position:absolute;top:18px;right:20px;font-size:22px;cursor:pointer;color:var(--muted);background:none;border:none;line-height:1}}
.modal-close:hover{{color:var(--ink)}}
/* ── TAB NAV ── */
.tab-nav{{
  display:flex;gap:4px;margin-bottom:20px;
  background:var(--surface);border:1px solid var(--border);
  border-radius:var(--r-md);padding:4px;width:fit-content;
}}
.tab-btn{{
  font-family:var(--font);font-size:13px;font-weight:600;
  background:none;border:none;cursor:pointer;
  padding:8px 20px;border-radius:8px;
  color:var(--muted);transition:all 0.18s;white-space:nowrap;
}}
.tab-btn:hover{{color:var(--ink)}}
.tab-btn.active{{background:var(--blue);color:#fff;box-shadow:0 2px 8px rgba(30,64,175,0.25)}}
.tab-btn.tab-week.active{{background:var(--sky)}}
.tab-pane{{display:none;animation:fadeIn 0.2s ease}}
.tab-pane.active{{display:block}}
@keyframes fadeIn{{from{{opacity:0;transform:translateY(6px)}}to{{opacity:1;transform:translateY(0)}}}}
/* ── FOOTER ── */
.footer{{text-align:center;margin-top:60px;font-family:var(--mono);font-size:10px;letter-spacing:1px;color:var(--dim)}}
@media(max-width:900px){{
  .pane-layout{{grid-template-columns:1fr}}
  .sidebar{{position:static}}
  .kpi-row{{grid-template-columns:repeat(4,1fr)}}
  .lc-buckets{{grid-template-columns:repeat(2,1fr)}}
  .charts-grid{{grid-template-columns:1fr}}
}}
@media(max-width:600px){{
  .kpi-row{{grid-template-columns:repeat(2,1fr)}}
  .dp-metrics{{grid-template-columns:repeat(2,1fr)}}
}}
</style>
</head>
<body>
<div class="wrap">

<!-- TOPBAR -->
<div class="topbar">
  <div class="logo">编</div>
  <div class="topbar-info">
    <div class="topbar-title">编导数据分析</div>
    <div class="topbar-sub">DIRECTOR · MATERIAL · PERFORMANCE</div>
  </div>
  <div class="topbar-badges">
    <span class="tb-badge sky">本周周报 {WEEK_START} 起</span>
  </div>
</div>

<!-- KPI ROW -->
<div class="kpi-row">
  <div class="kpi-card kw"><div class="kpi-tag">本周</div><div class="kpi-val">¥{wk_c:,.0f}</div><div class="kpi-lbl">总消耗</div></div>
  <div class="kpi-card kw"><div class="kpi-tag">本周</div><div class="kpi-val">¥{wk_g:,.0f}</div><div class="kpi-lbl">总GMV</div></div>
  <div class="kpi-card kw"><div class="kpi-tag">本周</div><div class="kpi-val">{wk_o}</div><div class="kpi-lbl">总订单</div></div>
  <div class="kpi-card kw"><div class="kpi-tag">本周</div><div class="kpi-val">{wk_m}</div><div class="kpi-lbl">有消耗素材</div></div>
</div>

<!-- TABS -->
<div class="tab-nav">
  <button class="tab-btn tab-week active" onclick="switchTab('week')">
    本周周报 <span class="tab-count">{len(week_dirs)} 人</span>
  </button>
</div>

<!-- ═══ TAB: HIST ═══ -->
<div class="tab-pane" id="tab-hist">
<div class="pane-layout">
  <!-- Sidebar -->
  <div class="sidebar">
    <button class="sb-all active" id="sb-all-hist" onclick="selectDir('hist','__all__',this)">全部编导</button>
    {hist_sidebar}
  </div>
  <!-- Content -->
  <div class="content-area">
    <!-- Overview (all selected) -->
    <div id="overview-hist">
      <!-- Lifecycle -->
      <div class="coll-wrap open" id="coll-lc">
        <button class="coll-head" onclick="toggleColl(this)">
          <span>素材生命周期</span><span class="coll-arrow">▾</span>
        </button>
        <div class="coll-body">
          <div class="lc-buckets">{lc_buckets_html}</div>
          <div class="lc-detail-row">
            <div class="lc-chart-wrap"><canvas id="lcChart"></canvas></div>
            <div class="lc-mat-list">
              <div class="lc-mat-title" id="bkTitle">← 点击分桶查看素材列表</div>
              <div class="mat-scroll" id="bkList"></div>
            </div>
          </div>
        </div>
      </div>
      <!-- Top 20 -->
      <div class="coll-wrap open" id="coll-top20">
        <button class="coll-head" onclick="toggleColl(this)">
          <span>历史消耗 TOP 20 素材</span><span class="coll-arrow">▾</span>
        </button>
        <div class="coll-body" style="padding:0 0 0">
          <div class="tbl-wrap" style="border-radius:0;border:none">
            <div class="tbl-scroll">
              <table>
                <thead><tr><th>#</th><th>素材名称</th><th>编导</th><th style="text-align:right">消耗</th><th style="text-align:right">GMV</th><th style="text-align:right">订单</th><th style="text-align:right">首消</th><th style="text-align:right">天数</th><th></th></tr></thead>
                <tbody>{top20_rows}</tbody>
              </table>
            </div>
          </div>
        </div>
      </div>
      <!-- Charts -->
      <div class="charts-grid">
        <div class="chart-box"><div class="chart-title">历史消耗对比</div><div class="chart-canvas"><canvas id="hConsumeChart"></canvas></div></div>
        <div class="chart-box"><div class="chart-title">历史 GMV 对比</div><div class="chart-canvas"><canvas id="hGmvChart"></canvas></div></div>
        <div class="chart-box"><div class="chart-title">历史订单对比</div><div class="chart-canvas"><canvas id="hOrderChart"></canvas></div></div>
        <div class="chart-box"><div class="chart-title">有消耗素材数</div><div class="chart-canvas"><canvas id="hMatChart"></canvas></div></div>
      </div>
    </div>
    <!-- Director Panel -->
    <div class="dir-panel" id="dir-panel-hist"></div>
  </div>
</div>
</div>

<!-- ═══ TAB: WEEK ═══ -->
<div class="tab-pane active" id="tab-week">
<div class="pane-layout">
  <!-- Sidebar -->
  <div class="sidebar">
    <button class="sb-all active" id="sb-all-week" onclick="selectDir('week','__all__',this)">全部编导</button>
    {week_sidebar}
  </div>
  <!-- Content -->
  <div class="content-area">
    <div id="overview-week">
      <!-- Top 20 -->
      <div class="coll-wrap open">
        <button class="coll-head" onclick="toggleColl(this)">
          <span>本周 TOP 20 素材（按消耗）</span><span class="coll-arrow">▾</span>
        </button>
        <div class="coll-body" style="padding:12px 0 0">
          <div class="prod-filter">
            <button class="pf-btn pf-all active" onclick="filterProd(this,'all')">全部</button>
            <button class="pf-btn pf-libo" onclick="filterProd(this,'9元李博')">9元李博</button>
            <button class="pf-btn pf-sk" onclick="filterProd(this,'199双科')">199双科</button>
          </div>
          <div class="tbl-wrap" style="border-radius:var(--r-md)">
            <div class="tbl-scroll">
              <table id="weekTop20">
                <thead><tr><th>#</th><th>素材名称</th><th>产品</th><th style="text-align:right">消耗</th><th style="text-align:right">GMV</th><th style="text-align:right">订单</th><th style="text-align:right">首消</th><th style="text-align:right">天数</th><th></th></tr></thead>
                <tbody>{week_top20_rows}</tbody>
              </table>
            </div>
          </div>
        </div>
      </div>
      <!-- Charts -->
      <div class="charts-grid">
        <div class="chart-box"><div class="chart-title">本周消耗对比</div><div class="chart-canvas"><canvas id="wConsumeChart"></canvas></div></div>
        <div class="chart-box"><div class="chart-title">本周 GMV 对比</div><div class="chart-canvas"><canvas id="wGmvChart"></canvas></div></div>
        <div class="chart-box"><div class="chart-title">本周订单对比</div><div class="chart-canvas"><canvas id="wOrderChart"></canvas></div></div>
        <div class="chart-box"><div class="chart-title">本周有消耗素材</div><div class="chart-canvas"><canvas id="wMatChart"></canvas></div></div>
      </div>
    </div>
    <div class="dir-panel" id="dir-panel-week"></div>
  </div>
</div>
</div>

<div class="footer">Generated {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</div>
</div><!-- /wrap -->

<!-- MODAL -->
<div class="modal-bg" id="modalBg">
  <div class="modal-box">
    <button class="modal-close" onclick="closeModal()">✕</button>
    <div id="modalContent"></div>
  </div>
</div>

<!-- __ SCRIPT_START__ -->
<script>
Chart.defaults.color = '#64748B';
Chart.defaults.borderColor = '#E2E8F0';

// ── Tab switching
function switchTab(t) {{
  document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
  document.querySelectorAll('.tab-pane').forEach(p => p.classList.remove('active'));
  document.querySelector('.tab-btn.tab-' + t).classList.add('active');
  document.getElementById('tab-' + t).classList.add('active');
  if (t === 'week') initWeekCharts();
}}

// ── Collapsible
function toggleColl(head) {{
  const wrap = head.closest('.coll-wrap');
  wrap.classList.toggle('open');
}}

// ── Product filter
function filterProd(btn, prod) {{
  document.querySelectorAll('.pf-btn').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  document.querySelectorAll('#weekTop20 tbody tr').forEach(row => {{
    row.style.display = (prod === 'all' || row.dataset.prod === prod) ? '' : 'none';
  }});
}}

// ── Director selector
function selectDir(tabId, dir, btn) {{
  // Update sidebar active
  document.querySelectorAll('#tab-' + tabId + ' .si-item, #sb-all-' + tabId).forEach(el => el.classList.remove('active'));
  btn.classList.add('active');
  const overview = document.getElementById('overview-' + tabId);
  const panel = document.getElementById('dir-panel-' + tabId);
  if (dir === '__all__') {{
    overview.style.display = '';
    panel.classList.remove('active');
  }} else {{
    overview.style.display = 'none';
    panel.classList.add('active');
    renderDirPanel(tabId, dir);
  }}
}}

// ── Panel data
const histPanelData = {json.dumps(hist_panel_data)};
const weekPanelData = {json.dumps(week_panel_data)};

const avColors = ['av-0','av-1','av-2','av-3','av-4','av-5'];
const hDirList = {json.dumps(all_dirs)};
const wDirList = {json.dumps(week_dirs)};

function getDirAv(tabId, dir) {{
  const list = tabId === 'hist' ? hDirList : wDirList;
  const idx = list.indexOf(dir);
  return idx >= 0 ? avColors[idx % 6] : 'av-0';
}}

function renderDirPanel(tabId, dirName) {{
  const data = (tabId === 'hist' ? histPanelData : weekPanelData)[dirName];
  if (!data) return;
  const avCls = getDirAv(tabId, dirName);
  const accentColor = tabId === 'hist' ? 'var(--amber)' : 'var(--sky)';
  let html = '<div class="dp-header">';
  html += '<div class="dp-av ' + avCls + '">' + dirName[0] + '</div>';
  html += '<div class="dp-info"><div class="dp-name">' + dirName + '</div>';
  html += '<div class="dp-tag">' + (tabId === 'hist' ? '历史汇总' : '本周周报') + '</div></div></div>';
  // Metrics
  html += '<div class="dp-metrics">';
  html += '<div class="dp-metric"><div class="dp-metric-val" style="color:' + accentColor + '">' + data.consume + '</div><div class="dp-metric-lbl">消耗</div></div>';
  html += '<div class="dp-metric"><div class="dp-metric-val">' + data.gmv + '</div><div class="dp-metric-lbl">GMV</div></div>';
  html += '<div class="dp-metric"><div class="dp-metric-val">' + data.orders + '</div><div class="dp-metric-lbl">订单</div></div>';
  html += '<div class="dp-metric"><div class="dp-metric-val">' + data.mat + '</div><div class="dp-metric-lbl">消耗/成交</div></div>';
  html += '</div>';
  // Upload pills
  if (data.upload) {{
    html += '<div class="dp-upload">';
    if (data.upload) html += '<span class="dp-pill">' + data.upload + '</span>';
    if (data.newmat) html += '<span class="dp-pill">' + data.newmat + '</span>';
    if (data.rejected) html += '<span class="dp-pill">' + data.rejected + '</span>';
    html += '</div>';
  }}
  // Products
  if (data.products && data.products.length) {{
    html += '<div class="dp-section-title">产品成单</div>';
    html += '<div class="dp-products">';
    data.products.forEach(p => {{
      html += '<div class="dp-prod-row"><span class="dp-prod-name">' + p.name + '</span><span class="dp-prod-cnt">' + p.cnt + '</span></div>';
    }});
    html += '</div>';
  }}
  // Top 3 by product
  const rankColors = ['#1E40AF','#0D9488','#D97706'];
  const prodLabels = {{'9元李博': '9元李博', '199双科': '199双科'}};
  if (data.prodTop3) {{
    const prodOrder = ['9元李博', '199双科'];
    prodOrder.forEach(ptag => {{
      const items = data.prodTop3[ptag];
      if (!items || !items.length) return;
      html += '<div class="dp-section-title">成交 TOP 3 · ' + prodLabels[ptag] + '</div>';
      html += '<div class="dp-top3">';
      items.forEach((m, i) => {{
        const lk = m.url ? '<a href="' + m.url + '" target="_blank" class="mat-link" style="margin-left:8px">▶ 预览</a>' : '';
        html += '<div class="dp-top-item">';
        html += '<div class="dp-top-rank" style="background:' + rankColors[i] + '">' + (i+1) + '</div>';
        html += '<div class="dp-top-body"><div class="dp-top-name" title="' + m.name + '">' + m.name + '</div>';
        html += '<div class="dp-top-meta">' + m.meta + lk + '</div></div></div>';
      }});
      html += '</div>';
    }});
  }}
  // Detail button
  html += '<button class="dp-detail-btn" onclick="showModal(&quot;' + dirName + '&quot;,&quot;' + tabId + '&quot;)">消耗 Top 20 →</button>';
  document.getElementById('dir-panel-' + tabId).innerHTML = html;
}}

// ── Lifecycle
const lcData = {json.dumps({
    bk: [
        {'素材名称': m['素材名称'], '编导': m['编导'],
         '总消耗': m['总消耗'], '总单量': m['总单量'],
         '首消': m['首消'], '天数': m['天数'], '链接': m['链接']}
        for m in sorted(hist_global['buckets'][bk], key=lambda x: x['总消耗'], reverse=True)
    ]
    for bk in ['≤7天', '8-14天', '15-30天', '>30天']
})};
const bkColors = ['#0D9488','#3B82F6','#D97706','#E11D48'];
const bkKeys = ['≤7天','8-14天','15-30天','>30天'];

// ── Chart data (declared before window.load so they're in scope)
const hDirs = {json.dumps(all_dirs)};
const wDirs = {json.dumps(week_dirs)};
const hStats = {json.dumps({d: {'c': hist_stats.get(d,{}).get('总消耗',0), 'g': hist_stats.get(d,{}).get('总GMV',0), 'o': hist_stats.get(d,{}).get('总单量',0), 'm': hist_stats.get(d,{}).get('有消耗',0)} for d in all_dirs})};
const wStats = {json.dumps({d: {'c': week_stats.get(d,{}).get('总消耗',0), 'g': week_stats.get(d,{}).get('总GMV',0), 'o': week_stats.get(d,{}).get('总单量',0), 'm': week_stats.get(d,{}).get('有消耗',0)} for d in week_dirs})};

let lcChart;
window.addEventListener('load', function() {{
  lcChart = new Chart(document.getElementById('lcChart'), {{
    type: 'bar',
    data: {{
      labels: bkKeys,
      datasets: [{{ data: bkKeys.map(k => lcData[k].length), backgroundColor: bkColors, borderRadius: 4, borderSkipped: false }}]
    }},
    options: {{
      indexAxis: 'y', responsive: true, maintainAspectRatio: false,
      plugins: {{ legend: {{ display: false }}, title: {{ display: true, text: '生命周期分布', color: '#64748B', font: {{ size: 10 }} }} }},
      scales: {{
        x: {{ grid: {{ color: '#F1F5F9' }}, ticks: {{ font: {{ size: 10 }} }} }},
        y: {{ grid: {{ display: false }}, ticks: {{ font: {{ size: 10 }} }} }}
      }}
    }}
  }});
  makeBar('hConsumeChart', hDirs, hDirs.map(d => hStats[d].c), '#D97706', '历史消耗');
  makeBar('hGmvChart',     hDirs, hDirs.map(d => hStats[d].g), '#D97706', '历史GMV');
  makeBar('hOrderChart',   hDirs, hDirs.map(d => hStats[d].o), '#0D9488', '历史订单');
  makeBar('hMatChart',     hDirs, hDirs.map(d => hStats[d].m), '#0D9488', '有消耗素材');
  initWeekCharts();
}});

function selectBucket(idx) {{
  document.querySelectorAll('.bk-pill').forEach((el,i) => el.classList.toggle('active', i===idx));
  const bk = bkKeys[idx];
  const items = lcData[bk];
  document.getElementById('bkTitle').textContent = bk + ' · ' + items.length + ' 条（按消耗排序）';
  document.getElementById('bkList').innerHTML = items.map(m => {{
    const lk = m.链接 ? '<a href="'+m.链接+'" target="_blank" class="mat-link">▶</a>' : '';
    return '<div class="mat-row"><span class="mat-rname" title="'+m.素材名称+'">'+m.素材名称+'</span>'
      + '<span class="mat-rmeta">'+m.编导+' · ¥'+m.总消耗.toFixed(0)+' · '+m.总单量+'单</span>'
      + lk + '</div>';
  }}).join('');
}}

// ── Charts
function makeBar(id, labels, data, color, title) {{
  return new Chart(document.getElementById(id), {{
    type: 'bar',
    data: {{ labels, datasets: [{{ data, backgroundColor: color + 'CC', borderRadius: 4, borderSkipped: false }}] }},
    options: {{
      responsive: true, maintainAspectRatio: false,
      plugins: {{ legend: {{ display: false }} }},
      scales: {{
        x: {{ grid: {{ display: false }}, ticks: {{ font: {{ size: 10 }} }} }},
        y: {{ grid: {{ color: '#F1F5F9' }}, ticks: {{ font: {{ size: 10 }} }} }}
      }}
    }}
  }});
}}

let weekChartsInited = false;
function initWeekCharts() {{
  if (weekChartsInited) return;
  weekChartsInited = true;
  makeBar('wConsumeChart', wDirs, wDirs.map(d => wStats[d].c), '#0EA5E9', '本周消耗');
  makeBar('wGmvChart',     wDirs, wDirs.map(d => wStats[d].g), '#0EA5E9', '本周GMV');
  makeBar('wOrderChart',   wDirs, wDirs.map(d => wStats[d].o), '#0D9488', '本周订单');
  makeBar('wMatChart',     wDirs, wDirs.map(d => wStats[d].m), '#0D9488', '有消耗素材');
}}

// ── Modal
const modalData = {json.dumps(modal_data)};

function showModal(d, tag) {{
  const key = d + '___' + tag;
  const items = modalData[key] || [];
  const color = tag === 'hist' ? '#D97706' : '#0EA5E9';
  const label = tag === 'hist' ? '历史' : '本周';
  let html = '<div class="modal-title">' + d + '</div>';
  html += '<div class="modal-sub">' + label + ' · 消耗 TOP 20（按消耗降序）</div>';
  html += '<div style="overflow-x:auto"><table><thead><tr>';
  html += '<th>#</th><th>素材名称</th><th style="text-align:right">消耗</th><th style="text-align:right">GMV</th><th style="text-align:right">订单</th><th style="text-align:right">首消</th><th style="text-align:right">天数</th><th></th>';
  html += '</tr></thead><tbody>';
  items.forEach((it, i) => {{
    const lk = it.链接 ? '<a href="'+it.链接+'" target="_blank" class="tbl-link">▶</a>' : '—';
    html += '<tr>';
    html += '<td class="rank-cell">'+(i+1)+'</td>';
    html += '<td class="name-cell">'+it.素材名称+'</td>';
    html += '<td class="num-cell" style="color:'+color+'">¥'+it.总消耗.toFixed(0)+'</td>';
    html += '<td class="num-cell">¥'+it.总GMV.toFixed(0)+'</td>';
    html += '<td class="num-cell">'+it.总单量+'</td>';
    html += '<td class="num-cell">'+(it.首消||'—')+'</td>';
    html += '<td class="num-cell">'+(it.天数!=null?it.天数+'天':'—')+'</td>';
    html += '<td>'+lk+'</td></tr>';
  }});
  html += '</tbody></table></div>';
  document.getElementById('modalContent').innerHTML = html;
  document.getElementById('modalBg').style.display = 'block';
}}

function closeModal() {{
  document.getElementById('modalBg').style.display = 'none';
}}

window.addEventListener('click', e => {{
  if (e.target === document.getElementById('modalBg')) closeModal();
}});
</script>
</body>
</html>'''

    with open(output, 'w', encoding='utf-8') as f:
        f.write(html)
    print(f'✓ 报告已生成: {output}')
    return output


if __name__ == '__main__':
    import os
    BASE = os.path.dirname(os.path.abspath(__file__))
    DATA = os.path.join(BASE, 'data')
    REPORTS = os.path.join(BASE, 'reports')
    os.makedirs(REPORTS, exist_ok=True)

    upload_rows = read_upload(os.path.join(DATA, '上传数据_增强版_0904.csv'))
    hist_rows   = read_delivery(os.path.join(DATA, '投后数据-编导-历史.csv'), week_only=False)
    week_rows   = read_delivery(os.path.join(DATA, '【周报】投后素材看板数据-编导-0904.csv'), week_only=False)

    print(f'上传数据: {len(upload_rows)} 条')
    print(f'历史投放: {len(hist_rows)} 条（筛选后）')
    print(f'近7天投放: {len(week_rows)} 条（筛选后）')

    upload_stats, hist_stats, hist_global = analyze(upload_rows, hist_rows)
    _,            week_stats, week_global = analyze(upload_rows, week_rows)

    print('\n历史编导汇总:')
    for d in sorted(hist_stats, key=lambda x: -hist_stats[x]['总消耗']):
        s = hist_stats[d]
        print(f'  {d}: ¥{s["总消耗"]:,.0f} 消耗 | {s["总单量"]}单 | {s["有消耗"]}条有消耗')

    print('\n近7天编导汇总:')
    for d in sorted(week_stats, key=lambda x: -week_stats[x]['总消耗']):
        s = week_stats[d]
        print(f'  {d}: ¥{s["总消耗"]:,.0f} 消耗 | {s["总单量"]}单 | {s["有消耗"]}条有消耗')

    out = os.path.join(REPORTS, '编导数据分析报告_合并版.html')
    generate_html(upload_stats, hist_stats, hist_global, week_stats, week_global, output=out)
