#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
编导数据分析 — 历史汇总 + 近7天周报 合并版
"""

import csv, json
from collections import defaultdict
from datetime import datetime

WEEK_START = '2026/7/3'  # 近7天起始日期

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


def read_delivery(path, week_only=False):
    rows = []
    with open(path, encoding='utf-8-sig') as f:
        for r in csv.DictReader(f):
            if not (r.get('编导确认', '').strip()
                    and r.get('是否自产自投', '').strip() == '是'
                    and r.get('是否混剪', '').strip() == '否'):
                continue
            if week_only:
                ft = r.get('首次消耗时间', '').strip()
                if not ft or ft == '-' or ft < WEEK_START:
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
        prod = r.get('素材投放产品', '')
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
            mat_records[key].append({'消耗': c, 'GMV': g, '单量': o, '链接': mlink})
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
            d_stats[d]['素材详情'].append({
                '素材名称': mn, '总消耗': tc, '总GMV': tg, '总单量': to,
                '链接': lnk, '首消': mat_first.get(key, ''),
                '天数': mat_days.get(key),
            })
        d_stats[d]['有消耗'] = len(w_c)
        d_stats[d]['有成交'] = len(w_o)
        d_stats[d]['均投放天数'] = sum(days_l) / len(days_l) if days_l else 0

    for d in d_stats:
        d_stats[d]['Top3'] = sorted(d_stats[d]['素材详情'], key=lambda x: x['总单量'], reverse=True)[:3]
        d_stats[d]['产品成单'] = dict(d_product[d])

    # ── 全局素材
    gmat = {}
    for key, recs in mat_records.items():
        d, mn = key.split('###', 1)
        tc = sum(x['消耗'] for x in recs)
        if tc <= 0: continue
        if mn not in gmat:
            gmat[mn] = {
                '素材名称': mn, '编导': d, '总消耗': tc,
                '总GMV': sum(x['GMV'] for x in recs),
                '总单量': sum(x['单量'] for x in recs),
                '链接': recs[0].get('链接', ''),
                '首消': mat_first.get(key, ''),
                '天数': mat_days.get(key),
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

    def director_card(d, stats, tag='hist'):
        s = stats.get(d, {})
        us = upload_stats.get(d, {})
        if not s and not us:
            return ''
        color = 'var(--amber)' if tag == 'hist' else 'var(--azure)'
        tc = s.get('总消耗', 0)
        tg = s.get('总GMV', 0)
        to = s.get('总单量', 0)
        top3 = s.get('Top3', [])
        prod = s.get('产品成单', {})
        details = sorted(s.get('素材详情', []), key=lambda x: x['总消耗'], reverse=True)[:20]
        safe_d = d.replace("'", "\\'")

        top3_html = ''
        for i, m in enumerate(top3, 1):
            lnk = f'<a href="{m["链接"]}" target="_blank" class="mat-link">▶ 预览</a>' if m.get('链接') else ''
            top3_html += f'''
              <div class="top-item">
                <span class="top-rank" style="background:{color}22;color:{color}">{i}</span>
                <div class="top-body">
                  <div class="top-name">{m["素材名称"]}</div>
                  <div class="top-meta">{m["总单量"]}单 · GMV ¥{m["总GMV"]:,.0f} {("· 首消 "+m["首消"]) if m.get("首消") else ""}</div>
                  {lnk}
                </div>
              </div>'''

        prod_html = ''
        if prod:
            items = sorted(prod.items(), key=lambda x: -x[1])
            prod_html = '<div class="prod-box"><div class="prod-title">产品成单</div>'
            for pname, pcnt in items:
                prod_html += f'<div class="prod-row"><span class="prod-name">{pname}</span><span class="prod-cnt" style="color:{color}">{pcnt}单</span></div>'
            prod_html += '</div>'

        return f'''
        <div class="dcard" id="dc-{tag}-{d}">
          <div class="dcard-head" style="border-color:{color}">
            <span class="dcard-name">{d}</span>
            <span class="dcard-badge" style="background:{color}22;color:{color}">{"历史" if tag=="hist" else "本周"}</span>
          </div>
          <div class="dcard-body">
            <div class="metrics-row">
              <div class="metric"><div class="metric-val" style="color:{color}">{_fmt(tc)}</div><div class="metric-lbl">消耗</div></div>
              <div class="metric"><div class="metric-val">{_fmt(tg)}</div><div class="metric-lbl">GMV</div></div>
              <div class="metric"><div class="metric-val">{to}</div><div class="metric-lbl">订单</div></div>
              <div class="metric"><div class="metric-val">{s.get("有消耗",0)}/{s.get("有成交",0)}</div><div class="metric-lbl">有消耗/成交</div></div>
            </div>
            {'<div class="upload-strip"><span>上传 '+str(us.get("唯一素材数",0))+'件</span><span>新素材 '+str(us.get("新素材数",0))+'</span><span>拒审二传 '+str(us.get("拒审后二次上传数",0))+'</span></div>' if us else ''}
            {prod_html}
            {'<div class="top3-label">成交 TOP 3</div>' + top3_html if top3 else ''}
          </div>
          <button class="detail-btn" onclick="showModal(\'{safe_d}\',\'{tag}\')" style="border-color:{color}22;color:{color}">消耗 Top 20 →</button>
        </div>'''

    hist_cards = ''.join(director_card(d, hist_stats, 'hist') for d in all_dirs)
    week_cards = ''.join(director_card(d, week_stats, 'week') for d in week_dirs)

    # 生命周期 HTML
    bk_keys = ['≤7天', '8-14天', '15-30天', '>30天']
    bk_colors = ['#2DD4BF', '#60A5FA', '#F5A524', '#F87171']
    total_mat = hist_global['total_mat']

    lc_buckets_html = ''
    for i, bk in enumerate(bk_keys):
        cnt = len(hist_global['buckets'][bk])
        pct = cnt / total_mat * 100 if total_mat else 0
        lc_buckets_html += f'''
            <div class="bk-pill" data-idx="{i}" onclick="selectBucket({i})">
              <div class="bk-name">{bk}</div>
              <div class="bk-cnt" style="color:{bk_colors[i]}">{cnt}</div>
              <div class="bk-pct">{pct:.0f}% of total</div>
            </div>'''

    # Top 20 table rows
    top20_rows = ''
    for i, m in enumerate(hist_global['top20'], 1):
        lnk = f'<a href="{m["链接"]}" target="_blank" class="tbl-link">▶</a>' if m.get('链接') else '—'
        top20_rows += f'''
              <tr>
                <td class="rank-cell">{i}</td>
                <td class="name-cell">{m["素材名称"]}</td>
                <td class="dir-cell">{m["编导"]}</td>
                <td class="num-cell">¥{m["总消耗"]:,.0f}</td>
                <td class="num-cell">¥{m["总GMV"]:,.0f}</td>
                <td class="num-cell">{m["总单量"]}</td>
                <td class="num-cell">{m.get("首消","—") or "—"}</td>
                <td class="num-cell">{str(m["天数"])+"天" if m.get("天数") is not None else "—"}</td>
                <td>{lnk}</td>
              </tr>'''

    # Week top 20
    week_top20 = sorted(
        [m for s in week_stats.values() for m in s.get('素材详情', [])],
        key=lambda x: x['总消耗'], reverse=True
    )[:20]
    week_top20_rows = ''
    for i, m in enumerate(week_top20, 1):
        lnk = f'<a href="{m["链接"]}" target="_blank" class="tbl-link">▶</a>' if m.get('链接') else '—'
        week_top20_rows += f'''
              <tr>
                <td class="rank-cell">{i}</td>
                <td class="name-cell">{m["素材名称"]}</td>
                <td class="num-cell">¥{m["总消耗"]:,.0f}</td>
                <td class="num-cell">¥{m["总GMV"]:,.0f}</td>
                <td class="num-cell">{m["总单量"]}</td>
                <td class="num-cell">{m.get("首消","—") or "—"}</td>
                <td class="num-cell">{str(m["天数"])+"天" if m.get("天数") is not None else "—"}</td>
                <td>{lnk}</td>
              </tr>'''

    # modal data
    modal_data = {}
    for d in all_dirs:
        for tag, stats in [('hist', hist_stats), ('week', week_stats)]:
            key = f'{d}___{tag}'
            details = sorted(
                stats.get(d, {}).get('素材详情', []),
                key=lambda x: x['总消耗'], reverse=True
            )[:20]
            modal_data[key] = details

    html = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>编导数据分析 · 历史 + 周报</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Syne:wght@700;800&family=DM+Sans:wght@300;400;500&family=DM+Mono:wght@400;500&display=swap" rel="stylesheet">
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<style>
:root {{
  --ink:      #06090F;
  --s1:       #0C1120;
  --s2:       #111828;
  --s3:       #19233A;
  --border:   rgba(255,255,255,0.055);
  --border2:  rgba(255,255,255,0.10);
  --amber:    #F5A524;
  --amber-d:  #C07D0E;
  --azure:    #4B8FED;
  --azure-d:  #2D64B5;
  --teal:     #2DD4BF;
  --rose:     #F87171;
  --text:     #DDE4F0;
  --muted:    #5E6E8A;
  --dim:      #2A3550;
  --font-d:   'Syne', sans-serif;
  --font-b:   'DM Sans', sans-serif;
  --font-m:   'DM Mono', monospace;
}}
*{{margin:0;padding:0;box-sizing:border-box}}
html{{scroll-behavior:smooth}}
body{{
  font-family:var(--font-b);
  background:var(--ink);
  color:var(--text);
  min-height:100vh;
  background-image:
    linear-gradient(rgba(75,143,237,0.03) 1px, transparent 1px),
    linear-gradient(90deg, rgba(75,143,237,0.03) 1px, transparent 1px);
  background-size:40px 40px;
}}

/* ── LAYOUT ─────────────────────── */
.wrap{{max-width:1440px;margin:0 auto;padding:40px 24px 80px}}

/* ── HEADER ─────────────────────── */
.page-head{{
  display:flex;align-items:flex-end;justify-content:space-between;
  flex-wrap:wrap;gap:16px;
  padding-bottom:32px;margin-bottom:40px;
  border-bottom:1px solid var(--border);
}}
.head-left h1{{
  font-family:var(--font-d);font-size:clamp(28px,4vw,48px);
  font-weight:800;letter-spacing:-1.5px;line-height:1;
  color:var(--text);
}}
.head-left h1 em{{font-style:normal;color:var(--amber)}}
.head-meta{{
  font-family:var(--font-m);font-size:11px;letter-spacing:1.5px;
  color:var(--muted);margin-top:8px;text-transform:uppercase;
}}
.head-right{{display:flex;flex-direction:column;align-items:flex-end;gap:6px}}
.date-badge{{
  font-family:var(--font-m);font-size:11px;letter-spacing:1px;
  background:var(--s2);border:1px solid var(--border2);
  color:var(--muted);padding:5px 12px;border-radius:4px;
}}

/* ── DUAL KPI BAR ────────────────── */
.kpi-bar{{
  display:grid;grid-template-columns:1fr 1fr;gap:2px;
  background:var(--border);border:1px solid var(--border);
  border-radius:12px;overflow:hidden;margin-bottom:40px;
}}
.kpi-half{{
  display:grid;grid-template-columns:repeat(4,1fr);gap:1px;
  background:var(--border);
}}
.kpi-cell{{
  background:var(--s1);padding:20px 18px;
  position:relative;overflow:hidden;
  transition:background 0.2s;
}}
.kpi-cell:hover{{background:var(--s2)}}
.kpi-label{{
  font-family:var(--font-m);font-size:9px;letter-spacing:2px;
  text-transform:uppercase;color:var(--muted);margin-bottom:10px;
}}
.kpi-val{{
  font-family:var(--font-m);font-size:22px;font-weight:500;
  line-height:1;margin-bottom:4px;
}}
.kpi-sub{{font-size:11px;color:var(--dim)}}
.kpi-cell.hist .kpi-val{{color:var(--amber)}}
.kpi-cell.week .kpi-val{{color:var(--azure)}}
.kpi-half-head{{
  grid-column:1/-1;background:var(--s2);
  padding:10px 18px;display:flex;align-items:center;gap:8px;
}}
.kpi-half-title{{
  font-family:var(--font-m);font-size:10px;letter-spacing:2px;
  text-transform:uppercase;
}}
.kpi-half-title.t-amber{{color:var(--amber)}}
.kpi-half-title.t-azure{{color:var(--azure)}}
.kpi-dot{{width:6px;height:6px;border-radius:50%}}

/* ── TABS ────────────────────────── */
.tab-nav{{
  display:flex;gap:0;margin-bottom:40px;
  border-bottom:1px solid var(--border);
  position:relative;
}}
.tab-btn{{
  font-family:var(--font-d);font-size:15px;font-weight:700;
  letter-spacing:0.5px;
  background:none;border:none;cursor:pointer;
  padding:14px 32px 14px 0;
  color:var(--muted);
  transition:color 0.2s;
  position:relative;
  white-space:nowrap;
}}
.tab-btn::after{{
  content:'';position:absolute;bottom:-1px;left:0;right:0;
  height:2px;background:var(--amber);
  transform:scaleX(0);transform-origin:left;
  transition:transform 0.25s cubic-bezier(0.4,0,0.2,1);
}}
.tab-btn.active{{color:var(--text)}}
.tab-btn.active::after{{transform:scaleX(1)}}
.tab-btn.tab-week.active::after{{background:var(--azure)}}
.tab-count{{
  display:inline-flex;align-items:center;justify-content:center;
  font-family:var(--font-m);font-size:9px;
  padding:2px 6px;border-radius:3px;margin-left:8px;
  vertical-align:middle;
}}
.tab-hist .tab-count{{background:rgba(245,165,36,0.15);color:var(--amber)}}
.tab-week .tab-count{{background:rgba(75,143,237,0.15);color:var(--azure)}}

.tab-pane{{display:none;animation:fadeTab 0.3s ease}}
.tab-pane.active{{display:block}}
@keyframes fadeTab{{from{{opacity:0;transform:translateY(8px)}}to{{opacity:1;transform:translateY(0)}}}}

/* ── SECTION LABEL ───────────────── */
.sec-label{{
  font-family:var(--font-m);font-size:10px;letter-spacing:2.5px;
  text-transform:uppercase;color:var(--muted);
  margin:44px 0 18px;display:flex;align-items:center;gap:12px;
}}
.sec-label::after{{content:'';flex:1;height:1px;background:var(--border)}}

/* ── LIFECYCLE ───────────────────── */
.lc-wrap{{
  background:var(--s1);border:1px solid var(--border);
  border-radius:12px;padding:24px;
}}
.lc-buckets{{display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin-bottom:20px}}
.bk-pill{{
  background:var(--ink);border:1px solid var(--border);
  border-radius:8px;padding:14px 16px;cursor:pointer;
  transition:all 0.18s;
}}
.bk-pill:hover,.bk-pill.active{{border-color:var(--border2);background:var(--s2)}}
.bk-name{{font-family:var(--font-m);font-size:10px;letter-spacing:1px;color:var(--muted);margin-bottom:6px}}
.bk-cnt{{font-family:var(--font-m);font-size:26px;font-weight:500;line-height:1;margin-bottom:4px}}
.bk-pct{{font-size:10px;color:var(--dim);font-family:var(--font-m)}}

.lc-detail-row{{display:flex;gap:20px;align-items:flex-start}}
.lc-chart-wrap{{flex:0 0 220px;height:180px;position:relative}}
.lc-mat-list{{flex:1;min-width:0}}
.lc-mat-title{{font-family:var(--font-m);font-size:10px;letter-spacing:1px;color:var(--muted);margin-bottom:10px}}
.mat-scroll{{max-height:200px;overflow-y:auto}}
.mat-scroll::-webkit-scrollbar{{width:3px}}
.mat-scroll::-webkit-scrollbar-track{{background:transparent}}
.mat-scroll::-webkit-scrollbar-thumb{{background:var(--dim);border-radius:2px}}
.mat-row{{
  display:flex;align-items:center;gap:8px;
  padding:7px 0;border-bottom:1px solid var(--border);
  font-size:12px;
}}
.mat-row:last-child{{border-bottom:none}}
.mat-rname{{flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:var(--text)}}
.mat-rmeta{{font-family:var(--font-m);font-size:10px;color:var(--muted);white-space:nowrap}}
.mat-link{{color:var(--amber);text-decoration:none;font-family:var(--font-m);font-size:10px;white-space:nowrap;opacity:0.7}}
.mat-link:hover{{opacity:1}}
.mat-link.wk{{color:var(--azure)}}

/* ── TABLE ───────────────────────── */
.tbl-wrap{{
  background:var(--s1);border:1px solid var(--border);
  border-radius:12px;overflow:hidden;
}}
.tbl-scroll{{overflow-x:auto}}
table{{width:100%;border-collapse:collapse}}
thead tr{{background:var(--s2)}}
th{{
  font-family:var(--font-m);font-size:9px;letter-spacing:1.5px;
  text-transform:uppercase;color:var(--muted);
  padding:12px 14px;text-align:left;font-weight:400;
  border-bottom:1px solid var(--border);white-space:nowrap;
}}
td{{
  padding:11px 14px;border-bottom:1px solid rgba(255,255,255,0.025);
  font-family:var(--font-m);font-size:12px;color:var(--muted);
}}
tbody tr:hover td{{background:rgba(255,255,255,0.015)}}
tbody tr:last-child td{{border-bottom:none}}
.rank-cell{{color:var(--dim);width:32px}}
.name-cell{{color:var(--text);font-family:var(--font-b);font-size:12px;max-width:280px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}}
.dir-cell{{color:var(--amber)}}
.num-cell{{text-align:right}}
.tbl-link{{color:var(--teal);text-decoration:none;opacity:0.7}}
.tbl-link:hover{{opacity:1}}

/* ── DIRECTOR CARDS ──────────────── */
.dcards{{display:grid;grid-template-columns:repeat(auto-fill,minmax(320px,1fr));gap:14px}}
.dcard{{
  background:var(--s1);border:1px solid var(--border);
  border-radius:12px;overflow:hidden;
  transition:border-color 0.2s;display:flex;flex-direction:column;
}}
.dcard:hover{{border-color:var(--border2)}}
.dcard-head{{
  display:flex;align-items:center;justify-content:space-between;
  padding:16px 18px 14px;border-bottom:2px solid var(--amber);
}}
.dcard-name{{font-family:var(--font-d);font-size:20px;font-weight:800;color:var(--text)}}
.dcard-badge{{
  font-family:var(--font-m);font-size:9px;letter-spacing:1.5px;
  text-transform:uppercase;padding:3px 8px;border-radius:4px;
}}
.dcard-body{{padding:16px 18px;flex:1}}

.metrics-row{{
  display:grid;grid-template-columns:repeat(4,1fr);gap:6px;
  margin-bottom:14px;
}}
.metric{{background:var(--ink);border-radius:6px;padding:10px 8px;text-align:center}}
.metric-val{{font-family:var(--font-m);font-size:14px;font-weight:500;line-height:1;margin-bottom:3px}}
.metric-lbl{{font-size:9px;color:var(--muted);font-family:var(--font-m);letter-spacing:0.5px}}

.upload-strip{{
  display:flex;gap:12px;padding:8px 10px;
  background:var(--s2);border-radius:6px;margin-bottom:12px;
  font-family:var(--font-m);font-size:10px;color:var(--muted);
  flex-wrap:wrap;
}}

.prod-box{{
  background:var(--ink);border-radius:6px;padding:10px;margin-bottom:12px;
}}
.prod-title{{
  font-family:var(--font-m);font-size:9px;letter-spacing:1.5px;
  text-transform:uppercase;color:var(--muted);margin-bottom:8px;
}}
.prod-row{{
  display:flex;justify-content:space-between;align-items:center;
  padding:3px 0;font-size:11px;
  border-bottom:1px solid var(--border);
}}
.prod-row:last-child{{border-bottom:none}}
.prod-name{{color:var(--muted);flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-family:var(--font-b)}}
.prod-cnt{{font-family:var(--font-m);font-size:11px;font-weight:500;margin-left:8px;flex-shrink:0}}

.top3-label{{
  font-family:var(--font-m);font-size:9px;letter-spacing:2px;
  text-transform:uppercase;color:var(--muted);margin:12px 0 8px;
}}
.top-item{{display:flex;gap:10px;margin-bottom:8px}}
.top-rank{{
  flex-shrink:0;width:20px;height:20px;border-radius:4px;
  display:flex;align-items:center;justify-content:center;
  font-family:var(--font-m);font-size:10px;font-weight:500;
}}
.top-body{{flex:1;min-width:0}}
.top-name{{font-size:11px;color:var(--text);margin-bottom:2px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}}
.top-meta{{font-family:var(--font-m);font-size:10px;color:var(--muted)}}

.detail-btn{{
  margin:0 18px 18px;background:transparent;
  border:1px solid;padding:8px 14px;border-radius:6px;
  font-family:var(--font-m);font-size:11px;letter-spacing:0.5px;
  cursor:pointer;transition:all 0.18s;text-align:left;
}}
.detail-btn:hover{{background:rgba(255,255,255,0.04)}}

/* ── CHARTS ──────────────────────── */
.charts-grid{{display:grid;grid-template-columns:repeat(2,1fr);gap:14px}}
.chart-box{{
  background:var(--s1);border:1px solid var(--border);
  border-radius:12px;padding:20px;
}}
.chart-title{{
  font-family:var(--font-m);font-size:10px;letter-spacing:1.5px;
  text-transform:uppercase;color:var(--muted);margin-bottom:14px;
}}
.chart-canvas{{position:relative;height:240px}}

/* ── MODAL ───────────────────────── */
.modal-bg{{
  display:none;position:fixed;inset:0;
  background:rgba(0,0,0,0.75);backdrop-filter:blur(6px);
  z-index:999;padding:20px;overflow-y:auto;
}}
.modal-box{{
  background:var(--s1);border:1px solid var(--border2);
  border-radius:14px;max-width:900px;
  margin:60px auto;padding:28px;position:relative;
}}
.modal-title{{
  font-family:var(--font-d);font-size:20px;font-weight:800;
  color:var(--text);margin-bottom:6px;
}}
.modal-sub{{font-family:var(--font-m);font-size:10px;letter-spacing:1px;color:var(--muted);margin-bottom:20px}}
.modal-close{{
  position:absolute;top:18px;right:20px;
  font-size:22px;cursor:pointer;color:var(--muted);
  background:none;border:none;line-height:1;
}}
.modal-close:hover{{color:var(--text)}}

/* ── FOOTER ──────────────────────── */
.footer{{
  text-align:center;margin-top:60px;
  font-family:var(--font-m);font-size:10px;letter-spacing:1px;
  color:var(--dim);
}}

@media(max-width:768px){{
  .kpi-bar{{grid-template-columns:1fr}}
  .kpi-half{{grid-template-columns:repeat(2,1fr)}}
  .lc-buckets{{grid-template-columns:repeat(2,1fr)}}
  .charts-grid{{grid-template-columns:1fr}}
  .lc-detail-row{{flex-direction:column}}
  .lc-chart-wrap{{flex:none;width:100%;height:160px}}
}}
</style>
</head>
<body>
<div class="wrap">

<!-- HEADER -->
<div class="page-head">
  <div class="head-left">
    <h1>编导<em>数据</em>分析</h1>
    <div class="head-meta">DIRECTOR · MATERIAL · PERFORMANCE</div>
  </div>
  <div class="head-right">
    <div class="date-badge">历史 2026/3/17 – 7/9</div>
    <div class="date-badge" style="color:var(--azure);border-color:rgba(75,143,237,0.3)">本周 {WEEK_START} – 7/9</div>
  </div>
</div>

<!-- DUAL KPI BAR -->
<div class="kpi-bar">
  <div class="kpi-half" style="grid-template-rows:auto auto">
    <div class="kpi-half-head" style="grid-column:1/-1">
      <div class="kpi-dot" style="background:var(--amber)"></div>
      <span class="kpi-half-title t-amber">历史汇总</span>
    </div>
    <div class="kpi-cell hist"><div class="kpi-label">总消耗</div><div class="kpi-val">¥{ht_c:,.0f}</div><div class="kpi-sub">元</div></div>
    <div class="kpi-cell hist"><div class="kpi-label">总 GMV</div><div class="kpi-val">¥{ht_g:,.0f}</div><div class="kpi-sub">元</div></div>
    <div class="kpi-cell hist"><div class="kpi-label">总订单</div><div class="kpi-val">{ht_o}</div><div class="kpi-sub">单</div></div>
    <div class="kpi-cell hist"><div class="kpi-label">有消耗素材</div><div class="kpi-val">{ht_m}</div><div class="kpi-sub">条</div></div>
  </div>
  <div class="kpi-half" style="grid-template-rows:auto auto">
    <div class="kpi-half-head" style="grid-column:1/-1">
      <div class="kpi-dot" style="background:var(--azure)"></div>
      <span class="kpi-half-title t-azure">近 7 天新起量</span>
    </div>
    <div class="kpi-cell week"><div class="kpi-label">总消耗</div><div class="kpi-val">¥{wk_c:,.0f}</div><div class="kpi-sub">元</div></div>
    <div class="kpi-cell week"><div class="kpi-label">总 GMV</div><div class="kpi-val">¥{wk_g:,.0f}</div><div class="kpi-sub">元</div></div>
    <div class="kpi-cell week"><div class="kpi-label">总订单</div><div class="kpi-val">{wk_o}</div><div class="kpi-sub">单</div></div>
    <div class="kpi-cell week"><div class="kpi-label">有消耗素材</div><div class="kpi-val">{wk_m}</div><div class="kpi-sub">条</div></div>
  </div>
</div>

<!-- TABS -->
<div class="tab-nav">
  <button class="tab-btn tab-hist active" onclick="switchTab('hist')">
    历史汇总 <span class="tab-count">{len(all_dirs)} 人</span>
  </button>
  <button class="tab-btn tab-week" onclick="switchTab('week')">
    近 7 天周报 <span class="tab-count">{len(week_dirs)} 人</span>
  </button>
</div>

<!-- ═══ TAB: HIST ═══ -->
<div class="tab-pane active" id="tab-hist">

  <div class="sec-label">素材生命周期</div>
  <div class="lc-wrap">
    <div class="lc-buckets">{lc_buckets_html}</div>
    <div class="lc-detail-row">
      <div class="lc-chart-wrap"><canvas id="lcChart"></canvas></div>
      <div class="lc-mat-list">
        <div class="lc-mat-title" id="bkTitle">← 点击分桶查看素材列表</div>
        <div class="mat-scroll" id="bkList"></div>
      </div>
    </div>
  </div>

  <div class="sec-label">历史消耗 TOP 20 素材</div>
  <div class="tbl-wrap">
    <div class="tbl-scroll">
      <table>
        <thead><tr>
          <th>#</th><th>素材名称</th><th>编导</th>
          <th style="text-align:right">消耗</th>
          <th style="text-align:right">GMV</th>
          <th style="text-align:right">订单</th>
          <th style="text-align:right">首消时间</th>
          <th style="text-align:right">投放天数</th>
          <th></th>
        </tr></thead>
        <tbody>{top20_rows}</tbody>
      </table>
    </div>
  </div>

  <div class="sec-label">各编导历史数据</div>
  <div class="dcards">{hist_cards}</div>

  <div class="sec-label">对比图表</div>
  <div class="charts-grid">
    <div class="chart-box"><div class="chart-title">历史消耗对比</div><div class="chart-canvas"><canvas id="hConsumeChart"></canvas></div></div>
    <div class="chart-box"><div class="chart-title">历史 GMV 对比</div><div class="chart-canvas"><canvas id="hGmvChart"></canvas></div></div>
    <div class="chart-box"><div class="chart-title">历史订单对比</div><div class="chart-canvas"><canvas id="hOrderChart"></canvas></div></div>
    <div class="chart-box"><div class="chart-title">有消耗素材数对比</div><div class="chart-canvas"><canvas id="hMatChart"></canvas></div></div>
  </div>

</div>

<!-- ═══ TAB: WEEK ═══ -->
<div class="tab-pane" id="tab-week">

  <div class="sec-label">近 7 天新起量素材 TOP 20</div>
  <div class="tbl-wrap">
    <div class="tbl-scroll">
      <table>
        <thead><tr>
          <th>#</th><th>素材名称</th>
          <th style="text-align:right">消耗</th>
          <th style="text-align:right">GMV</th>
          <th style="text-align:right">订单</th>
          <th style="text-align:right">首消时间</th>
          <th style="text-align:right">投放天数</th>
          <th></th>
        </tr></thead>
        <tbody>{week_top20_rows}</tbody>
      </table>
    </div>
  </div>

  <div class="sec-label">各编导本周数据</div>
  <div class="dcards">{week_cards}</div>

  <div class="sec-label">对比图表</div>
  <div class="charts-grid">
    <div class="chart-box"><div class="chart-title">本周消耗对比</div><div class="chart-canvas"><canvas id="wConsumeChart"></canvas></div></div>
    <div class="chart-box"><div class="chart-title">本周 GMV 对比</div><div class="chart-canvas"><canvas id="wGmvChart"></canvas></div></div>
    <div class="chart-box"><div class="chart-title">本周订单对比</div><div class="chart-canvas"><canvas id="wOrderChart"></canvas></div></div>
    <div class="chart-box"><div class="chart-title">本周有消耗素材</div><div class="chart-canvas"><canvas id="wMatChart"></canvas></div></div>
  </div>

</div>

<div class="footer">Generated {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</div>
</div>

<!-- MODAL -->
<div class="modal-bg" id="modalBg">
  <div class="modal-box">
    <button class="modal-close" onclick="closeModal()">✕</button>
    <div id="modalContent"></div>
  </div>
</div>

<script>
Chart.defaults.color = '#5E6E8A';
Chart.defaults.borderColor = 'rgba(255,255,255,0.05)';

// ── Tab switching
function switchTab(t) {{
  document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
  document.querySelectorAll('.tab-pane').forEach(p => p.classList.remove('active'));
  document.querySelector('.tab-btn.tab-' + t).classList.add('active');
  document.getElementById('tab-' + t).classList.add('active');
}}

// ── Lifecycle buckets
const lcData = {json.dumps({
    bk: [
        {'素材名称': m['素材名称'], '编导': m['编导'],
         '总消耗': m['总消耗'], '总单量': m['总单量'],
         '首消': m['首消'], '天数': m['天数'], '链接': m['链接']}
        for m in sorted(hist_global['buckets'][bk], key=lambda x: x['总消耗'], reverse=True)
    ]
    for bk in ['≤7天', '8-14天', '15-30天', '>30天']
})};
const bkColors = ['#2DD4BF','#60A5FA','#F5A524','#F87171'];
const bkKeys = ['≤7天','8-14天','15-30天','>30天'];

const lcChart = new Chart(document.getElementById('lcChart'), {{
  type: 'bar',
  data: {{
    labels: bkKeys,
    datasets: [{{
      data: bkKeys.map(k => lcData[k].length),
      backgroundColor: bkColors,
      borderRadius: 4, borderSkipped: false,
    }}]
  }},
  options: {{
    indexAxis: 'y', responsive: true, maintainAspectRatio: false,
    plugins: {{ legend: {{ display: false }},
      title: {{ display: true, text: '生命周期分布', color: '#5E6E8A', font: {{ size: 10, family: 'DM Mono' }} }}
    }},
    scales: {{
      x: {{ grid: {{ color: 'rgba(255,255,255,0.03)' }}, ticks: {{ font: {{ family: 'DM Mono', size: 10 }} }} }},
      y: {{ grid: {{ display: false }}, ticks: {{ font: {{ family: 'DM Mono', size: 10 }} }} }}
    }}
  }}
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

// ── Charts util
const makeBar = (id, labels, data, color, title) => new Chart(document.getElementById(id), {{
  type: 'bar',
  data: {{ labels, datasets: [{{ data, backgroundColor: color + 'CC', borderRadius: 4, borderSkipped: false }}] }},
  options: {{
    responsive: true, maintainAspectRatio: false,
    plugins: {{ legend: {{ display: false }},
      title: {{ display: false }}
    }},
    scales: {{
      x: {{ grid: {{ display: false }}, ticks: {{ font: {{ family: 'DM Mono', size: 10 }} }} }},
      y: {{ grid: {{ color: 'rgba(255,255,255,0.03)' }}, ticks: {{ font: {{ family: 'DM Mono', size: 10 }} }} }}
    }}
  }}
}});

const hDirs = {json.dumps(all_dirs)};
const wDirs = {json.dumps(week_dirs)};
const hStats = {json.dumps({d: {'c': hist_stats.get(d,{}).get('总消耗',0), 'g': hist_stats.get(d,{}).get('总GMV',0), 'o': hist_stats.get(d,{}).get('总单量',0), 'm': hist_stats.get(d,{}).get('有消耗',0)} for d in all_dirs})};
const wStats = {json.dumps({d: {'c': week_stats.get(d,{}).get('总消耗',0), 'g': week_stats.get(d,{}).get('总GMV',0), 'o': week_stats.get(d,{}).get('总单量',0), 'm': week_stats.get(d,{}).get('有消耗',0)} for d in week_dirs})};

makeBar('hConsumeChart', hDirs, hDirs.map(d => hStats[d].c), '#F5A524', '历史消耗');
makeBar('hGmvChart',     hDirs, hDirs.map(d => hStats[d].g), '#F5A524', '历史GMV');
makeBar('hOrderChart',   hDirs, hDirs.map(d => hStats[d].o), '#2DD4BF', '历史订单');
makeBar('hMatChart',     hDirs, hDirs.map(d => hStats[d].m), '#2DD4BF', '有消耗素材');
makeBar('wConsumeChart', wDirs, wDirs.map(d => wStats[d].c), '#4B8FED', '本周消耗');
makeBar('wGmvChart',     wDirs, wDirs.map(d => wStats[d].g), '#4B8FED', '本周GMV');
makeBar('wOrderChart',   wDirs, wDirs.map(d => wStats[d].o), '#2DD4BF', '本周订单');
makeBar('wMatChart',     wDirs, wDirs.map(d => wStats[d].m), '#2DD4BF', '有消耗素材');

// ── Modal
const modalData = {json.dumps(modal_data)};

function showModal(d, tag) {{
  const key = d + '___' + tag;
  const items = modalData[key] || [];
  const color = tag === 'hist' ? '#F5A524' : '#4B8FED';
  const label = tag === 'hist' ? '历史' : '本周';
  let html = '<div class="modal-title">' + d + '</div>';
  html += '<div class="modal-sub">' + label + ' · 消耗 TOP 20 素材（按消耗降序）</div>';
  html += '<div style="overflow-x:auto"><table><thead><tr>';
  html += '<th>#</th><th>素材名称</th><th style="text-align:right">消耗</th><th style="text-align:right">GMV</th><th style="text-align:right">订单</th><th style="text-align:right">首消</th><th style="text-align:right">天数</th><th></th>';
  html += '</tr></thead><tbody>';
  const maxC = items.length ? Math.max(...items.map(x=>x.总消耗)) : 1;
  items.forEach((it, i) => {{
    const pct = (it.总消耗 / maxC * 100).toFixed(1);
    const lk = it.链接 ? '<a href="'+it.链接+'" target="_blank" class="tbl-link">▶</a>' : '—';
    html += '<tr>';
    html += '<td class="rank-cell">'+(i+1)+'</td>';
    html += '<td class="name-cell" style="max-width:260px">'+it.素材名称+'</td>';
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

    upload_rows = read_upload(os.path.join(DATA, '上传数据_增强版_0710.csv'))
    hist_rows   = read_delivery(os.path.join(DATA, '投后数据-编导-历史.csv'), week_only=False)
    week_rows   = read_delivery(os.path.join(DATA, '投后数据-编导-历史.csv'), week_only=True)

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
