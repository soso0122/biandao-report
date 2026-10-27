#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
素材月度复盘报告（7/8/9/10月）
用法:
  python3 scripts/generate_monthly_review.py

设计: Data-Dense Dashboard（ui-ux-pro-max 推荐）+ 项目浅色蓝白体系
"""
import csv, re, json, sys
from pathlib import Path
from collections import defaultdict
from datetime import datetime

from fresh_links import load_fresh_links

ROOT = Path(__file__).parent.parent
DATA = ROOT / 'data'
OUT = ROOT / 'reports'

PERSONS = ['小敏', '嘉丽', '瑞晨', '浩正', '雅迪', '魏怡', '婷玉', '国星']


def f(v):
    v = str(v or '0').replace(',', '')
    try:
        return float(v)
    except:
        return 0.0


def pdate(label):
    return datetime(2026, int(label[:2]), int(label[3:]))


def person_of(name):
    for p in PERSONS:
        if p in name:
            return p
    return '外部/未知'


def main():
    files = sorted(DATA.glob('引导加微每日数据-*.csv'))
    files = [x for x in files if re.fullmatch(r'引导加微每日数据-\d{4}', x.stem)]
    months = ['07', '08', '09', '10']

    # ---- 标签表 ----
    label_map = {}
    lf = DATA / '历史打标.csv'
    if lf.exists():
        with open(lf, encoding='utf-8-sig') as fh:
            for r in csv.DictReader(fh):
                sid = (r.get('素材id') or '').strip()
                name = (r.get('视频名称') or '').strip()
                tag = (r.get('标签') or '').strip()
                if sid:
                    label_map[sid] = tag
                if name:
                    label_map[name] = tag

    # ---- 名字→主id 归一化（0827 缺素材id列）----
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

    def norm(name, sid):
        return name_to_id.get(name) or sid or name

    def tag_of(name, sid):
        t = label_map.get(sid) or label_map.get(name)
        if not t and name.startswith('推送视频_'):
            t = label_map.get(name[5:]) or ''
        return t or ''

    # ---- 每月聚合 + 全局信息 ----
    month_agg = {mm: {} for mm in months}
    first_seen = {}
    first_spend = {}
    tot_conv = defaultdict(float)
    tot_gq = defaultdict(float)
    key_name = {}
    key_type = {}
    key_link = {}
    day_spend = defaultdict(lambda: defaultdict(float))
    day_conv = defaultdict(lambda: defaultdict(float))

    # 加载用户最新导出的视频链接（千川链接带时效，旧链接会失效）
    fresh = load_fresh_links()
    fresh_by_id = fresh['by_id']
    fresh_by_name = fresh['by_name']

    def fresh_link(name, sid):
        """新链接优先按素材id匹配，其次按名称（含去'推送视频_'前缀）"""
        if sid and sid in fresh_by_id:
            return fresh_by_id[sid]
        if name in fresh_by_name:
            return fresh_by_name[name]
        if name.startswith('推送视频_'):
            n2 = name[len('推送视频_'):]
            if n2 in fresh_by_name:
                return fresh_by_name[n2]
        return ''

    for fp in files:
        mmdd = re.search(r'(\d{4})', fp.stem).group(1)
        label = f"{mmdd[:2]}/{mmdd[2:]}"
        mm = mmdd[:2]
        with open(fp, encoding='utf-8-sig') as fh:
            for r in csv.DictReader(fh):
                name = (r.get('视频名称') or '').strip()
                if not name:
                    continue
                is_home = bool(re.fullmatch(r'\d+', name) or re.fullmatch(r'[\d.]+[eE][+\-]?\d+', name))
                if is_home:
                    continue
                link = (r.get('视频链接') or '').strip()
                sid = (r.get('素材id') or '').strip()
                key = norm(name, sid)
                sp = f(r.get('消耗'))
                conv = f(r.get('转化数'))
                gq = f(r.get('回访-高潜成交(计费时间)'))

                if key not in first_seen:
                    first_seen[key] = label
                if sp > 0 and (key not in first_spend or pdate(label) < pdate(first_spend[key])):
                    first_spend[key] = label
                tot_conv[key] += conv
                tot_gq[key] += gq
                key_name[key] = name
                key_type[key] = '图文' if ('图文' in name or len(link) < 10) else '视频'
                if key not in key_link:
                    key_link[key] = fresh_link(name, sid) or link
                day_spend[key][label] += sp
                day_conv[key][label] += conv

                if mm in month_agg:
                    d = month_agg[mm].setdefault(key, dict(spend=0.0, conv=0.0, gq=0.0))
                    d['spend'] += sp
                    d['conv'] += conv
                    d['gq'] += gq

    # ---- 每月四个维度 ----
    months_js = {}
    for mm in months:
        items = month_agg[mm]
        act = [(k, v) for k, v in items.items() if v['spend'] > 0]
        zero = [(k, v) for k, v in items.items() if v['spend'] == 0]
        tot_spend = sum(v['spend'] for _, v in act)
        tot_conv_m = sum(v['conv'] for _, v in act)
        tot_gq_m = sum(v['gq'] for _, v in act)

        def row(k, v):
            conv = v['conv']
            gq = v['gq']
            deep = gq / conv * 100 if conv else None
            return {
                'id': k, 'name': key_name[k], 'person': person_of(key_name[k]),
                'type': key_type[k], 'tag': tag_of(key_name[k], k),
                'spend': round(v['spend'], 2), 'conv': int(conv), 'gq': int(gq),
                'deep': round(deep, 1) if deep is not None else None,
                'link': key_link.get(k, ''),
            }

        top_gq = sorted([row(k, v) for k, v in act if v['gq'] > 0], key=lambda r: -r['gq'])[:3]

        cand_deep = [row(k, v) for k, v in act if v['conv'] >= 5]
        top_deep = sorted(cand_deep, key=lambda r: -r['deep'])[:3]

        no_gq = [row(k, v) for k, v in act if v['conv'] > 10 and v['gq'] == 0]
        no_gq.sort(key=lambda r: -r['conv'])

        lowest = sorted([row(k, v) for k, v in act], key=lambda r: r['spend'])[:5]

        months_js[mm] = {
            'kpi': {
                'active': len(act), 'zero': len(zero),
                'spend': round(tot_spend, 0), 'conv': int(tot_conv_m), 'gq': int(tot_gq_m),
                'conv10': len([1 for k, v in act if v['conv'] > 10]),
            },
            'top_gq': top_gq,
            'top_deep': top_deep,
            'no_gq': no_gq,
            'lowest': lowest,
        }

    # ---- 全局证据 ----
    all_keys = set(first_seen)
    zero_ever = [k for k in all_keys if k not in first_spend]
    latent = []
    for k in all_keys:
        if k not in first_spend:
            continue
        lat = (pdate(first_spend[k]) - pdate(first_seen[k])).days
        if lat >= 7 and tot_conv[k] >= 3:
            latent.append({
                'id': k, 'name': key_name[k], 'type': key_type[k],
                'first_seen': first_seen[k], 'first_spend': first_spend[k],
                'idle': lat, 'conv': int(tot_conv[k]), 'gq': int(tot_gq[k]),
                'link': key_link.get(k, ''),
            })
    latent.sort(key=lambda x: -x['conv'])

    continuation = []
    for i in range(3):
        cur, nxt = months[i], months[i + 1]
        proven = [k for k, v in month_agg[cur].items() if v['spend'] > 0 and v['conv'] >= 1]
        resumed = sum(1 for k in proven if month_agg[nxt].get(k, {}).get('spend', 0) >= 10)
        shallow = sum(1 for k in proven if 0 < month_agg[nxt].get(k, {}).get('spend', 0) < 10)
        zero_n = sum(1 for k in proven if month_agg[nxt].get(k, {}).get('spend', 0) == 0)
        continuation.append({
            'from': cur, 'to': nxt, 'proven': len(proven),
            'resumed': resumed, 'shallow': shallow, 'zero': zero_n,
        })

    labels = []
    for fp in files:
        mmdd = re.search(r'(\d{4})', fp.stem).group(1)
        labels.append(f"{mmdd[:2]}/{mmdd[2:]}")
    labels = sorted(set(labels), key=lambda l: pdate(l))
    stopped_conv = []
    for k in all_keys:
        act_days = sorted(d for d in day_spend[k] if day_spend[k][d] > 0)
        if len(act_days) < 2:
            continue
        last = act_days[-1]
        idx = labels.index(last)
        if day_conv[k][last] > 0 and idx <= len(labels) - 3:
            stopped_conv.append({
                'id': k, 'name': key_name[k], 'last': last,
                'conv_last': int(day_conv[k][last]), 'link': key_link.get(k, ''),
            })
    stopped_conv.sort(key=lambda x: pdate(x['last']), reverse=True)

    # ---- 月度概览图数据 ----
    overview = {
        'labels': ['7月', '8月', '9月', '10月'],
        'spend': [round(sum(v['spend'] for _, v in month_agg[mm].items() if v['spend'] > 0), 0) for mm in months],
        'gq': [int(sum(v['gq'] for _, v in month_agg[mm].items())) for mm in months],
        'conv': [int(sum(v['conv'] for _, v in month_agg[mm].items())) for mm in months],
    }

    html = (HTML_TEMPLATE
            .replace('{{', '{').replace('}}', '}')  # 模板用 replace 填充，双花括号还原
            .replace('__MONTHS_JS__', json.dumps(months_js, ensure_ascii=False))
            .replace('__MONTHS_ORDER__', json.dumps(months))
            .replace('__ZERO_EVER__', json.dumps(len(zero_ever)))
            .replace('__TOTAL_MAT__', json.dumps(len(all_keys)))
            .replace('__ZERO_PCT__', json.dumps(round(len(zero_ever) / len(all_keys) * 100)))
            .replace('__LATENT_JS__', json.dumps(latent, ensure_ascii=False))
            .replace('__LATENT_N__', json.dumps(len(latent)))
            .replace('__CONT_JS__', json.dumps(continuation, ensure_ascii=False))
            .replace('__STOPPED_JS__', json.dumps(stopped_conv[:10], ensure_ascii=False))
            .replace('__STOPPED_N__', json.dumps(len(stopped_conv)))
            .replace('__OVERVIEW_JS__', json.dumps(overview, ensure_ascii=False))
            .replace('__CHARTJS__', (Path(__file__).parent / 'chart.min.js').read_text(encoding='utf-8'))
            )
    out_path = OUT / '素材月度复盘.html'
    out_path.write_text(html, encoding='utf-8')
    print(f'报告已生成: {out_path}')


HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>素材月度复盘 · 7-10月</title>
<style>
*,*::before,*::after{{box-sizing:border-box;margin:0;padding:0}}
:root{{
  --bg:#F0F4FA;--card:#FFFFFF;--border:#DBEAFE;--border-soft:#EAF1FA;
  --primary:#1E40AF;--primary-light:#3B82F6;--primary-soft:#EFF6FF;
  --accent:#D97706;--accent-soft:#FFFBEB;
  --text:#1E3A8A;--text-2:#475569;--text-muted:#94A3B8;
  --success:#059669;--success-soft:#ECFDF5;
  --danger:#DC2626;--danger-soft:#FEF2F2;
  --shadow:0 1px 2px rgba(30,64,175,.05);
  --shadow-md:0 4px 12px rgba(30,64,175,.08);
  --radius:12px;
  font-family:'Fira Sans',system-ui,'PingFang SC','Microsoft YaHei',sans-serif;
}}
body{{background:var(--bg);color:var(--text);font-size:14px;line-height:1.5}}
.header{{
  background:linear-gradient(120deg,#1E3A8A 0%,#1E40AF 55%,#2563EB 100%);
  padding:26px 32px 22px;color:#fff;position:relative;overflow:hidden;
}}
.header::after{{
  content:'';position:absolute;right:-60px;top:-80px;width:260px;height:260px;
  background:radial-gradient(circle,rgba(255,255,255,.10) 0%,transparent 65%);
}}
.header h1{{font-size:22px;font-weight:700;letter-spacing:.3px}}
.header p{{color:rgba(255,255,255,.72);font-size:12px;margin-top:6px}}
.wrap{{max-width:1440px;margin:0 auto;padding:22px}}

/* 结论区 */
.evidence-grid{{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:18px}}
.ev-card{{
  background:var(--card);border:1px solid var(--border);border-radius:var(--radius);
  padding:16px 16px 14px;box-shadow:var(--shadow);position:relative;transition:transform .15s,box-shadow .15s;
}}
.ev-card:hover{{transform:translateY(-2px);box-shadow:var(--shadow-md)}}
.ev-num{{
  width:26px;height:26px;border-radius:8px;display:inline-flex;align-items:center;justify-content:center;
  font-size:13px;font-weight:700;color:#fff;margin-bottom:10px;
}}
.ev-card .ev-title{{font-size:12px;font-weight:600;color:var(--text-2);margin-bottom:6px}}
.ev-card .ev-big{{font-size:26px;font-weight:700;line-height:1.1;font-family:monospace}}
.ev-card .ev-desc{{font-size:11.5px;color:var(--text-muted);margin-top:6px}}
.ev-blue .ev-num{{background:var(--primary-light)}}
.ev-green .ev-num{{background:var(--success)}}
.ev-amber .ev-num{{background:var(--accent)}}
.ev-red .ev-num{{background:var(--danger)}}

/* 卡片 */
.card{{
  background:var(--card);border:1px solid var(--border);border-radius:var(--radius);
  padding:18px 20px;box-shadow:var(--shadow);margin-bottom:16px;
}}
.card-head{{display:flex;align-items:center;gap:10px;margin-bottom:4px}}
.card-icon{{
  width:32px;height:32px;border-radius:9px;display:inline-flex;align-items:center;justify-content:center;
  font-size:15px;flex:none;
}}
.card h2{{font-size:15px;font-weight:700;color:var(--text)}}
.card .card-sub{{font-size:11.5px;color:var(--text-muted);margin:2px 0 12px}}

/* 概览图 */
.overview-wrap{{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:18px}}
.overview-chart{{background:var(--card);border:1px solid var(--border);border-radius:var(--radius);padding:16px;box-shadow:var(--shadow)}}
.overview-chart h3{{font-size:13px;font-weight:700;color:var(--text);margin-bottom:10px;display:flex;align-items:center;gap:8px}}
.overview-chart h3 .dot{{width:8px;height:8px;border-radius:50%;display:inline-block}}

/* 表格 */
.table-wrap{{overflow-x:auto;border-radius:8px;border:1px solid var(--border-soft)}}
table{{width:100%;border-collapse:collapse;font-size:12.5px}}
thead th{{
  position:sticky;top:0;background:#F4F8FE;color:var(--text-2);font-weight:600;
  padding:9px 12px;text-align:left;border-bottom:1px solid var(--border);white-space:nowrap;z-index:2;
}}
tbody tr{{height:38px;transition:background .12s}}
tbody tr:hover{{background:var(--primary-soft)}}
tbody tr:nth-child(even){{background:#FAFCFF}}
tbody tr:nth-child(even):hover{{background:var(--primary-soft)}}
tbody td{{padding:6px 12px;border-bottom:1px solid var(--border-soft);vertical-align:middle}}
td.m-name{{max-width:250px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}}
td.m-id{{font-family:monospace;font-size:11px;color:var(--text-muted);white-space:nowrap}}
.num{{font-family:monospace;font-weight:600}}
.pos{{color:var(--success)}}.warn{{color:var(--accent)}}.zero{{color:var(--text-muted)}}
.badge{{display:inline-block;padding:1px 9px;border-radius:10px;font-size:11px;font-weight:500}}
.b-video{{background:#DBEAFE;color:#1D4ED8}}.b-tuwen{{background:#F3E8FF;color:#7C3AED}}
.link-btn{{
  display:inline-block;padding:2px 11px;border-radius:12px;border:1px solid var(--border);
  background:var(--bg);color:var(--primary);font-size:11px;text-decoration:none;font-weight:500;transition:all .15s;
}}
.link-btn:hover{{background:var(--primary);color:#fff;border-color:var(--primary)}}
.empty-row{{text-align:center;color:var(--text-muted);padding:14px}}

/* 分段标题 */
.sub-title{{
  display:flex;align-items:center;gap:8px;font-size:13px;font-weight:700;color:var(--text);
  margin:18px 0 4px;
}}
.sub-title .st-bar{{width:4px;height:16px;border-radius:2px;background:var(--primary-light);display:inline-block}}
.note{{font-size:11.5px;color:var(--text-muted);margin:2px 0 8px}}

/* 续投率 */
.cont-row{{display:flex;align-items:center;gap:12px;margin-bottom:10px}}
.cont-lbl{{width:130px;text-align:right;font-size:12px;color:var(--text-2);flex:none}}
.cont-lbl b{{display:block;font-size:10.5px;color:var(--text-muted);font-weight:400}}
.bar-track{{flex:1;height:18px;background:#F1F5F9;border-radius:9px;overflow:hidden;display:flex}}
.bar-seg{{height:100%;transition:width .4s}}
.cont-stat{{width:170px;font-size:11.5px;color:var(--text-2);flex:none}}
.cont-legend{{display:flex;gap:16px;font-size:11px;color:var(--text-muted);margin:10px 0 0 142px}}
.cont-legend i{{display:inline-block;width:10px;height:10px;border-radius:2px;margin-right:4px}}

/* 月度 tabs */
.tabs{{display:flex;gap:8px;margin:14px 0 16px;background:#E9F0FB;border-radius:12px;padding:5px;width:fit-content}}
.tab-btn{{
  padding:7px 26px;border-radius:9px;border:none;background:transparent;
  font-size:13px;font-weight:600;color:var(--text-2);cursor:pointer;transition:all .18s;
}}
.tab-btn:hover{{color:var(--primary)}}
.tab-btn.active{{background:#fff;color:var(--primary);box-shadow:var(--shadow-md)}}

/* KPI 行 */
.kpi-grid{{display:grid;grid-template-columns:repeat(6,1fr);gap:10px;margin-bottom:16px}}
.kpi{{
  background:linear-gradient(180deg,#FAFCFF 0%,#F3F7FE 100%);
  border:1px solid var(--border-soft);border-radius:10px;padding:11px 13px;
}}
.kpi .lbl{{font-size:10.5px;color:var(--text-muted);letter-spacing:.4px}}
.kpi .val{{font-size:20px;font-weight:700;font-family:monospace;margin-top:3px;color:var(--text)}}
.kpi.accent .val{{color:var(--primary)}}
.kpi.green .val{{color:var(--success)}}
.kpi.amber .val{{color:var(--accent)}}
.kpi.red .val{{color:var(--danger)}}
@media(max-width:900px){{
  .evidence-grid{{grid-template-columns:repeat(2,1fr)}}
  .overview-wrap{{grid-template-columns:1fr}}
  .kpi-grid{{grid-template-columns:repeat(3,1fr)}}
}}
</style>
</head>
<body>
<div class="header">
  <h1>素材月度复盘 · 7-10月</h1>
  <p>口径：消耗&gt;0=在投 · 深转=高潜成交 · 深转率=高潜÷转化（转化≥5才进榜） · 数据范围 07/21–10/08</p>
</div>
<div class="wrap">

  <!-- 月度概览 -->
  <div class="overview-wrap">
    <div class="overview-chart"><h3><span class="dot" style="background:#3B82F6"></span>月度总消耗（¥）</h3><div style="height:150px"><canvas id="chSpend"></canvas></div></div>
    <div class="overview-chart"><h3><span class="dot" style="background:#D97706"></span>月度总高潜成交</h3><div style="height:150px"><canvas id="chGq"></canvas></div></div>
  </div>

  <!-- 投放问题证据 -->
  <div class="evidence-grid">
    <div class="ev-card ev-red">
      <span class="ev-num">①</span>
      <div class="ev-title">零消耗素材</div>
      <div class="ev-big" style="color:var(--danger)">__ZERO_PCT__%</div>
      <div class="ev-desc">__ZERO_EVER__/__TOTAL_MAT__ 条素材进库后从未获得任何消耗</div>
    </div>
    <div class="ev-card ev-green">
      <span class="ev-num">②</span>
      <div class="ev-title">闲置后自证素材</div>
      <div class="ev-big" style="color:var(--success)">__LATENT_N__ 条</div>
      <div class="ev-desc">闲置9-18天启用后跑出转化，内容没变，差的只是没给量</div>
    </div>
    <div class="ev-card ev-amber">
      <span class="ev-num">③</span>
      <div class="ev-title">续投率逐月下滑</div>
      <div class="ev-big" style="color:var(--accent)">79%→22%</div>
      <div class="ev-desc">已验证素材次月续投率，9月103条在10月完全没投</div>
    </div>
    <div class="ev-card ev-blue">
      <span class="ev-num">④</span>
      <div class="ev-title">停投时仍在转化</div>
      <div class="ev-big" style="color:var(--primary)">__STOPPED_N__ 条</div>
      <div class="ev-desc">末投日当天还在转化却被停掉，疑似误停</div>
    </div>
  </div>

  <!-- 证据② 闲置自证清单 -->
  <div class="card">
    <div class="card-head">
      <span class="card-icon" style="background:#ECFDF5">📈</span>
      <h2>闲置后自证素材（建议逐条看原视频）</h2>
    </div>
    <div class="card-sub">这些素材进库后躺了 7 天以上才开始投放，内容未变，随后转化 ≥3 —— 证明"不是素材不行，是没被给机会"。</div>
    <div class="table-wrap"><table>
      <thead><tr><th>素材名称</th><th>素材ID</th><th>类型</th><th>进库日</th><th>首投日</th><th>闲置天数</th><th>后续转化</th><th>后续高潜</th><th>视频</th></tr></thead>
      <tbody id="latentBody"></tbody>
    </table></div>
  </div>

  <!-- 证据③ 续投率 -->
  <div class="card">
    <div class="card-head">
      <span class="card-icon" style="background:#FFFBEB">🔁</span>
      <h2>已验证素材的续投率</h2>
    </div>
    <div class="card-sub">上月有转化的素材，次月是否继续给预算（续投=次月消耗≥¥10）。</div>
    <div id="contBars"></div>
    <div class="cont-legend">
      <span><i style="background:#059669"></i>次月续投(≥¥10)</span>
      <span><i style="background:#D97706"></i>次月浅投(&lt;¥10)</span>
      <span><i style="background:#CBD5E1"></i>次月完全没投</span>
    </div>
  </div>

  <!-- 证据④ 停投清单 -->
  <div class="card">
    <div class="card-head">
      <span class="card-icon" style="background:#FEF2F2">⛔</span>
      <h2>末投日仍在转化却被停（前10条）</h2>
    </div>
    <div class="card-sub">这些素材在最后投放的当天仍产生转化，之后却连续停投至今 —— 疑似误停，建议复核。</div>
    <div class="table-wrap"><table>
      <thead><tr><th>素材名称</th><th>素材ID</th><th>末投日</th><th>末投日转化</th><th>视频</th></tr></thead>
      <tbody id="stoppedBody"></tbody>
    </table></div>
  </div>

  <!-- 每月复盘 -->
  <div class="card" style="margin-bottom:0">
    <div class="card-head">
      <span class="card-icon" style="background:#EFF6FF">📊</span>
      <h2>每月复盘 · 四个维度</h2>
    </div>
    <div class="tabs" id="monthTabs"></div>
    <div id="monthPanel"></div>
  </div>

</div>
<script>__CHARTJS__</script>
<script>
const MONTHS_JS = __MONTHS_JS__;
const MONTH_ORDER = __MONTHS_ORDER__;
const LATENT = __LATENT_JS__;
const CONT = __CONT_JS__;
const STOPPED = __STOPPED_JS__;
const OVERVIEW = __OVERVIEW_JS__;

const esc = s => String(s || '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
const fmtMoney = v => '¥' + Number(v).toLocaleString('zh', {{minimumFractionDigits:2, maximumFractionDigits:2}});
const typeBadge = t => '<span class="badge ' + (t === '图文' ? 'b-tuwen' : 'b-video') + '">' + t + '</span>';
const linkBtn = (link, name) => link
  ? '<a class="link-btn" href="' + link + '" target="_blank" title="' + esc(name) + '">看视频</a>'
  : '<span class="zero">无链接</span>';

// 月度概览图
const barOpts = (color) => ({{
  plugins: {{ legend: {{ display: false }} }},
  scales: {{ x: {{ grid: {{ display: false }} }}, y: {{ beginAtZero: true, grid: {{ color: '#EDF2F9' }} }} }},
}});
new Chart(document.getElementById('chSpend'), {{
  type: 'bar',
  data: {{ labels: OVERVIEW.labels, datasets: [{{
    data: OVERVIEW.spend, backgroundColor: ['#93C5FD','#60A5FA','#3B82F6','#1D4ED8'],
    borderRadius: 6, maxBarThickness: 46
  }}] }},
  options: barOpts('#3B82F6')
}});
new Chart(document.getElementById('chGq'), {{
  type: 'bar',
  data: {{ labels: OVERVIEW.labels, datasets: [{{
    data: OVERVIEW.gq, backgroundColor: ['#FDE68A','#FBBF24','#F59E0B','#D97706'],
    borderRadius: 6, maxBarThickness: 46
  }}] }},
  options: barOpts('#D97706')
}});

// 证据②
document.getElementById('latentBody').innerHTML = LATENT.map(m =>
  '<tr><td class="m-name" title="' + esc(m.name) + '">' + esc(m.name) + '</td>'
  + '<td class="m-id" title="' + esc(m.id) + '">' + esc(m.id || '—') + '</td>'
  + '<td>' + typeBadge(m.type) + '</td><td>' + m.first_seen + '</td><td>' + m.first_spend + '</td>'
  + '<td class="num warn">' + m.idle + ' 天</td>'
  + '<td class="num pos">' + m.conv + '</td><td class="num warn">' + m.gq + '</td>'
  + '<td>' + linkBtn(m.link, m.name) + '</td></tr>'
).join('') || '<tr><td colspan="9" class="empty-row">无数据</td></tr>';

// 证据③
document.getElementById('contBars').innerHTML = CONT.map(c => {{
  const tot = c.proven;
  const pR = tot ? Math.round(c.resumed / tot * 100) : 0;
  const pS = tot ? Math.round(c.shallow / tot * 100) : 0;
  const pZ = tot ? Math.round(c.zero / tot * 100) : 0;
  return '<div class="cont-row"><div class="cont-lbl">' + c.from + '月 → ' + c.to + '月<b>已验证 ' + tot + ' 条</b></div>'
    + '<div class="bar-track">'
    + (pR ? '<div class="bar-seg" style="width:' + pR + '%;background:#059669" title="续投 ' + c.resumed + ' 条"></div>' : '')
    + (pS ? '<div class="bar-seg" style="width:' + pS + '%;background:#D97706" title="浅投 ' + c.shallow + ' 条"></div>' : '')
    + (pZ ? '<div class="bar-seg" style="width:' + pZ + '%;background:#CBD5E1" title="没投 ' + c.zero + ' 条"></div>' : '')
    + '</div><span class="cont-stat">续投 ' + c.resumed + ' · 浅投 ' + c.shallow + ' · 没投 ' + c.zero + '</span></div>';
}}).join('');

// 证据④
document.getElementById('stoppedBody').innerHTML = STOPPED.map(m =>
  '<tr><td class="m-name" title="' + esc(m.name) + '">' + esc(m.name) + '</td>'
  + '<td class="m-id" title="' + esc(m.id) + '">' + esc(m.id || '—') + '</td>'
  + '<td>' + m.last + '</td><td class="num pos">' + m.conv_last + '</td>'
  + '<td>' + linkBtn(m.link, m.name) + '</td></tr>'
).join('') || '<tr><td colspan="5" class="empty-row">无数据</td></tr>';

// 月度 tabs
function monthLabel(mm) {{ return parseInt(mm, 10) + '月'; }}
function renderTabs() {{
  const t = document.getElementById('monthTabs');
  t.innerHTML = MONTH_ORDER.map((mm, i) =>
    '<button class="tab-btn' + (i === 3 ? ' active' : '') + '" data-mm="' + mm + '">' + monthLabel(mm) + '</button>'
  ).join('');
  t.querySelectorAll('.tab-btn').forEach(btn => {{
    btn.onclick = () => {{
      t.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      renderMonth(btn.dataset.mm);
    }};
  }});
}}
function renderMonth(mm) {{
  const M = MONTHS_JS[mm];
  const panel = document.getElementById('monthPanel');
  const rowHtml = (r, showDeep) =>
    '<tr><td class="m-name" title="' + esc(r.name) + '">' + esc(r.name) + '</td>'
    + '<td class="m-id" title="' + esc(r.id) + '">' + esc(r.id || '—') + '</td>'
    + '<td>' + esc(r.person) + '</td><td>' + typeBadge(r.type) + '</td><td>' + esc(r.tag || '—') + '</td>'
    + '<td class="num">' + fmtMoney(r.spend) + '</td>'
    + '<td class="num ' + (r.conv > 0 ? 'pos' : 'zero') + '">' + r.conv + '</td>'
    + '<td class="num ' + (r.gq > 0 ? 'warn' : 'zero') + '">' + r.gq + '</td>'
    + (showDeep ? '<td class="num warn">' + (r.deep !== null ? r.deep + '%' : '—') + '</td>' : '')
    + '<td>' + linkBtn(r.link, r.name) + '</td></tr>';
  const table = (head, rows) =>
    '<div class="table-wrap" style="margin-bottom:6px"><table><thead><tr>' + head + '</tr></thead><tbody>'
    + (rows || '<tr><td colspan="10" class="empty-row">当月无符合条件素材</td></tr>') + '</tbody></table></div>';
  const thBase = '<th>素材名称</th><th>素材ID</th><th>人</th><th>类型</th><th>标签</th><th>消耗</th><th>转化</th><th>高潜</th>';

  panel.innerHTML =
    '<div class="kpi-grid">'
    + '<div class="kpi"><div class="lbl">在投素材</div><div class="val">' + M.kpi.active + '</div></div>'
    + '<div class="kpi red"><div class="lbl">零消耗素材</div><div class="val">' + M.kpi.zero + '</div></div>'
    + '<div class="kpi accent"><div class="lbl">总消耗</div><div class="val">¥' + M.kpi.spend.toLocaleString() + '</div></div>'
    + '<div class="kpi green"><div class="lbl">总转化</div><div class="val">' + M.kpi.conv + '</div></div>'
    + '<div class="kpi amber"><div class="lbl">总高潜</div><div class="val">' + M.kpi.gq + '</div></div>'
    + '<div class="kpi"><div class="lbl">转化&gt;10素材</div><div class="val">' + M.kpi.conv10 + '</div></div>'
    + '</div>'

    + '<div class="sub-title"><span class="st-bar" style="background:var(--accent)"></span>1 · 高潜成交 Top3</div>'
    + table(thBase + '<th>视频</th>', M.top_gq.map(r => rowHtml(r, false)).join(''))

    + '<div class="sub-title"><span class="st-bar" style="background:var(--primary-light)"></span>2 · 深转率 Top3（转化≥5 才进榜）</div>'
    + '<div class="note">避免小样本虚高：转化不足 5 条的素材不进榜。</div>'
    + table(thBase + '<th>深转率</th><th>视频</th>', M.top_deep.map(r => rowHtml(r, true)).join(''))

    + '<div class="sub-title"><span class="st-bar" style="background:var(--danger)"></span>3 · 转化&gt;10 却无深转（共 ' + M.no_gq.length + ' 条）</div>'
    + '<div class="note">转化没问题、深转做不动 —— 找"内容短板"的最好样本，建议翻原视频。</div>'
    + table(thBase + '<th>视频</th>', M.no_gq.map(r => rowHtml(r, false)).join(''))

    + '<div class="sub-title"><span class="st-bar" style="background:var(--success)"></span>4 · 零消耗/消耗最低抽样 5 条</div>'
    + '<div class="note">本月 ' + M.kpi.zero + ' 条素材零消耗。它们没有表现数据，点"看视频"打开原片判断内容 —— 若内容认真做了，即"好素材没被给机会"的实证。</div>'
    + table(thBase + '<th>视频</th>', M.lowest.map(r => rowHtml(r, false)).join(''));
}}
renderTabs();
renderMonth(MONTH_ORDER[3]);
</script>
</body>
</html>
"""


if __name__ == '__main__':
    main()
