#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
引导素材每日分析报告生成器（支持多日对比）
用法:
  python scripts/generate_report_daily_guide.py                # 自动读取 data/ 下所有 引导加微每日数据-*.csv
  python scripts/generate_report_daily_guide.py data/引导加微每日数据-0722.csv   # 指定单个文件
"""
import csv, json, sys, os, re
from pathlib import Path
from collections import defaultdict

PERSONS = ['小敏', '嘉丽', '瑞晨', '浩正', '雅迪', '魏怡', '婷玉']
EDITORS = ['小敏', '嘉丽', '浩正', '雅迪', '婷玉']  # 编导
EDITORS_SET = set(EDITORS)
CUTTERS = ['魏怡', '瑞晨', '国星']  # 剪辑
PERSON_COLORS = {
    '小敏': '#3B82F6', '嘉丽': '#8B5CF6', '瑞晨': '#10B981',
    '浩正': '#F59E0B', '雅迪': '#EC4899', '魏怡': '#EF4444',
    '婷玉': '#14B8A6', '其他': '#94A3B8', '外部': '#F97316', '主页': '#059669',
}
PERSON_BG = {
    '小敏': '#EFF6FF', '嘉丽': '#F5F3FF', '瑞晨': '#ECFDF5',
    '浩正': '#FFFBEB', '雅迪': '#FDF2F8', '魏怡': '#FEF2F2',
    '婷玉': '#F0FDFA', '其他': '#F8FAFC', '外部': '#FFF7ED', '主页': '#ECFDF5',
}

def safe_float(v):
    try:
        return float(str(v).replace(',', '') or 0)
    except:
        return 0.0

def extract_person(name):
    found_editors = [p for p in EDITORS if p in name]
    found_cutters = [p for p in CUTTERS if p in name]
    if found_editors:
        return found_editors[0]
    if found_cutters:
        return found_cutters[0]
    return '其他'

def extract_collab(name):
    found_editors = [p for p in EDITORS if p in name]
    found_cutters = [p for p in CUTTERS if p in name]
    if found_editors and found_cutters:
        return f"{found_editors[0]}×{found_cutters[0]}"
    return ''

def is_external(name):
    return '微信视频' in name

def is_tuwen(name):
    return '图文' in name and not is_homepage(name)

def is_homepage(name):
    n = name.strip()
    return bool(re.fullmatch(r'\d+', n) or re.fullmatch(r'[\d.]+[eE][+\-]?\d+', n))

def clean_name(name):
    return re.sub(r'\.mp4\.mp4$', '.mp4', name)

def load_csv(path):
    with open(path, encoding='utf-8-sig') as f:
        rows = list(csv.DictReader(f))
    valid = [r for r in rows if (r.get('视频名称') or '').strip()]
    for r in valid:
        name = r.get('视频名称', '')
        r['_name']        = clean_name(name)
        r['_id']          = r.get('素材id', '').strip()
        video_url         = r.get('视频链接', '').strip()
        r['_is_homepage'] = is_homepage(name)
        r['_is_tuwen']    = not r['_is_homepage'] and len(video_url) < 10
        r['_is_external'] = is_external(name)
        r['_person']      = '外部' if is_external(name) else ('主页' if r['_is_homepage'] else extract_person(name))
        r['_collab']      = extract_collab(name)
        r['_account']     = r.get('账户名称', '')
        r['_消耗']       = safe_float(r.get('消耗'))
        r['_展示数']     = safe_float(r.get('展示数'))
        r['_点击数']     = safe_float(r.get('点击数'))
        r['_点击率']     = safe_float(r.get('点击率(%)'))
        r['_转化数']     = safe_float(r.get('转化数'))
        r['_转化成本']   = safe_float(r.get('转化成本'))
        r['_高潜成交']   = safe_float(r.get('回访-高潜成交(计费时间)'))
        r['_CPM']        = safe_float(r.get('平均千次展现费用(元)'))
        r['_CPC']        = safe_float(r.get('平均点击单价(元)'))
        r['_视频链接']   = r.get('视频链接', '')
        r['_投放情况']   = r.get('投放情况', '')
    return valid

def compute_stats(rows):
    ts = sum(r['_消耗'] for r in rows)
    ti = sum(r['_展示数'] for r in rows)
    tc = sum(r['_点击数'] for r in rows)
    tz = sum(r['_转化数'] for r in rows)
    tg = sum(r['_高潜成交'] for r in rows)
    by_person = defaultdict(lambda: {'消耗':0,'转化':0,'展示':0,'点击':0,'高潜成交':0,'素材数':0})
    for r in rows:
        p = r['_person']
        by_person[p]['消耗']    += r['_消耗']
        by_person[p]['转化']    += r['_转化数']
        by_person[p]['展示']    += r['_展示数']
        by_person[p]['点击']    += r['_点击数']
        by_person[p]['高潜成交'] += r['_高潜成交']
        by_person[p]['素材数']  += 1
    for p,d in by_person.items():
        d['CPA'] = d['消耗']/d['转化'] if d['转化'] else 0
        d['CTR'] = d['点击']/d['展示']*100 if d['展示'] else 0
    return {
        'total_spend': ts, 'total_imp': ti,
        'total_conv': tz, 'total_gaoquan': tg,
        'avg_cpa': ts/tz if tz else 0,
        'avg_ctr': tc/ti*100 if ti else 0,
        'by_person': dict(by_person)
    }

def rows_to_json(rows):
    out = []
    for r in sorted(rows, key=lambda x: -x['_消耗']):
        out.append({
            'id': r['_id'],
            'name': r['_name'],
            'person': r['_person'],
            'account': r['_account'],
            'is_external': r['_is_external'],
            'is_tuwen': r['_is_tuwen'],
            'is_homepage': r['_is_homepage'],
            'collab': r['_collab'],
            'status': r['_投放情况'],
            'spend': r['_消耗'],
            'impressions': r['_展示数'],
            'clicks': r['_点击数'],
            'ctr': r['_点击率'],
            'conversions': r['_转化数'],
            'cpa': r['_转化成本'],
            'gaoquan': r['_高潜成交'],
            'cpm': r['_CPM'],
            'cpc': r['_CPC'],
            'video_url': r['_视频链接'],
        })
    return out

def build_compare(days_data):
    date_labels = [l for l,_ in days_data]
    trend = []
    for label, rows in days_data:
        s = compute_stats(rows)
        trend.append({
            'date': label,
            'spend': round(s['total_spend'], 2),
            'conv': round(s['total_conv'], 1),
            'gaoquan': round(s['total_gaoquan'], 1),
            'cpa': round(s['avg_cpa'], 2),
            'ctr': round(s['avg_ctr'], 3),
        })

    mat_map = {}
    for label, rows in days_data:
        for r in rows:
            key = r['_id'] if r['_id'] else r['_name']
            if key not in mat_map:
                mat_map[key] = {
                    'name': r['_name'],
                    'person': r['_person'],
                    'is_external': r['_is_external'],
                    'is_homepage': r['_is_homepage'],
                    'video_url': r['_视频链接'],
                    'days': {}
                }
            elif r['_is_homepage'] and not mat_map[key]['is_homepage']:
                # 用科学计数法名称更新（更准确的主页标识）
                mat_map[key]['is_homepage'] = True
                mat_map[key]['person'] = '主页'
                mat_map[key]['name'] = r['_name']
            if label not in mat_map[key]['days']:
                mat_map[key]['days'][label] = {
                    'spend': r['_消耗'], 'conv': r['_转化数'],
                    'gaoquan': r['_高潜成交'], 'cpa': 0,
                }
            else:
                mat_map[key]['days'][label]['spend']   += r['_消耗']
                mat_map[key]['days'][label]['conv']    += r['_转化数']
                mat_map[key]['days'][label]['gaoquan'] += r['_高潜成交']

    mat_rows = []
    for key, m in mat_map.items():
        total = sum(m['days'].get(d, {}).get('spend', 0) for d in date_labels)
        if total == 0:
            continue
        row = {
            'name': m['name'],
            'person': m['person'],
            'is_external': m['is_external'],
            'is_homepage': m['is_homepage'],
            'video_url': m['video_url']
        }
        for d in date_labels:
            day = m['days'].get(d, {})
            row[f's_{d}'] = round(day.get('spend', 0), 2)
            row[f'c_{d}'] = round(day.get('conv', 0), 1)
            row[f'g_{d}'] = round(day.get('gaoquan', 0), 1)
            row[f'p_{d}'] = round(day.get('cpa', 0), 2)
        row['total'] = round(total, 2)
        mat_rows.append(row)
    mat_rows.sort(key=lambda x: -x['total'])

    all_persons = []
    seen = set()
    for _, rows in days_data:
        for r in rows:
            if r['_消耗'] > 0 and r['_person'] not in seen:
                seen.add(r['_person'])
                all_persons.append(r['_person'])
    all_persons.sort(key=lambda p: -sum(
        r['_消耗'] for _, rows in days_data for r in rows if r['_person'] == p
    ))

    person_by_day = {}
    for label, rows in days_data:
        pm = defaultdict(float)
        for r in rows:
            pm[r['_person']] += r['_消耗']
        person_by_day[label] = {p: round(pm.get(p, 0), 2) for p in all_persons}

    return {
        'trend': trend,
        'date_labels': date_labels,
        'mat_rows': mat_rows,
        'persons': all_persons,
        'person_by_day': person_by_day,
    }

# ---------- 完整的 HTML 模板（支持多日对比） ----------
HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>引导素材日报 · {date_str}</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Fira+Sans:wght@300;400;500;600;700&family=Fira+Code:wght@400;500&display=swap" rel="stylesheet">
<style>
*,*::before,*::after{{box-sizing:border-box;margin:0;padding:0}}
:root{{
  --bg:#F8FAFC;--card:#FFFFFF;--border:#DBEAFE;
  --primary:#1E40AF;--primary-light:#3B82F6;
  --accent:#D97706;--accent-bg:#FFFBEB;
  --text:#1E3A8A;--text-secondary:#64748B;--text-muted:#94A3B8;
  --success:#059669;--danger:#DC2626;
  --shadow:0 1px 3px rgba(0,0,0,.08);
  --shadow-md:0 4px 6px rgba(0,0,0,.07);
  --radius:10px;
  font-family:'Fira Sans',system-ui,sans-serif;
}}
body{{background:var(--bg);color:var(--text);font-size:14px;line-height:1.5;min-height:100vh}}

.header{{
  background:linear-gradient(135deg,#1E3A8A 0%,#1E40AF 60%,#2563EB 100%);
  padding:20px 28px 18px;display:flex;align-items:center;justify-content:space-between;
  border-bottom:1px solid rgba(255,255,255,.1);
}}
.header-left h1{{color:#fff;font-size:18px;font-weight:700;letter-spacing:.3px}}
.header-left p{{color:rgba(255,255,255,.65);font-size:12px;margin-top:2px}}
.header-badge{{
  background:rgba(255,255,255,.15);border:1px solid rgba(255,255,255,.25);
  color:#fff;padding:5px 12px;border-radius:20px;font-size:12px;font-weight:500;
  backdrop-filter:blur(4px);
}}

.page{{max-width:1400px;margin:0 auto;padding:20px 24px}}

.kpi-grid{{display:grid;grid-template-columns:repeat(7,1fr);gap:12px;margin-bottom:20px}}
.kpi-card{{
  background:var(--card);border:1px solid var(--border);border-radius:var(--radius);
  padding:14px 16px;box-shadow:var(--shadow);transition:box-shadow .15s;
}}
.kpi-card:hover{{box-shadow:var(--shadow-md)}}
.kpi-card.accent{{background:var(--accent-bg);border-color:#FCD34D}}
.kpi-label{{font-size:11px;color:var(--text-secondary);font-weight:500;text-transform:uppercase;letter-spacing:.5px;margin-bottom:6px}}
.kpi-value{{font-size:24px;font-weight:700;color:var(--primary);font-family:'Fira Code',monospace;line-height:1.1}}
.kpi-card.accent .kpi-value{{color:var(--accent)}}
.kpi-sub{{font-size:11px;color:var(--text-muted);margin-top:3px}}

.section-title{{font-size:13px;font-weight:600;color:var(--text);margin-bottom:12px;
  display:flex;align-items:center;gap:6px}}
.section-title::before{{content:'';display:inline-block;width:3px;height:14px;
  background:var(--primary-light);border-radius:2px}}

.charts-row{{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:20px}}
.chart-card{{background:var(--card);border:1px solid var(--border);border-radius:var(--radius);
  padding:16px;box-shadow:var(--shadow)}}
.chart-wrap{{position:relative;height:220px;width:100%}}

/* 多日切换标签 */
.tabs{{
  display:flex;gap:6px;flex-wrap:wrap;
  background:var(--card);border:1px solid var(--border);border-radius:var(--radius);
  padding:8px 12px;box-shadow:var(--shadow);align-items:center;
}}
.tabs-label{{font-size:12px;color:var(--text-secondary);font-weight:500;margin-right:4px;white-space:nowrap}}
.tab-btn{{
  padding:5px 14px;border-radius:20px;border:none;background:transparent;
  font-weight:500;font-size:13px;color:var(--text-secondary);cursor:pointer;
  transition:all .15s;white-space:nowrap;
}}
.tab-btn:hover{{background:var(--bg);color:var(--primary)}}
.tab-btn.active{{background:var(--primary);color:#fff;box-shadow:var(--shadow-md)}}
.tab-select{{
  padding:6px 12px;border-radius:8px;border:1.5px solid var(--border);
  font-size:13px;font-weight:500;color:var(--text);background:var(--bg);
  cursor:pointer;outline:none;min-width:120px;
}}
.tab-select:focus{{border-color:var(--primary-light)}}
.tabs-sort{{display:flex;gap:4px;margin-left:auto}}
.sort-btn{{
  padding:4px 10px;border-radius:6px;border:1.5px solid var(--border);
  font-size:11px;font-weight:500;color:var(--text-secondary);cursor:pointer;
  background:var(--bg);transition:all .15s;white-space:nowrap;display:flex;align-items:center;gap:3px;
}}
.sort-btn:hover{{border-color:var(--primary-light);color:var(--primary)}}
.sort-btn.active{{border-color:var(--primary);background:var(--primary);color:#fff}}

.filter-bar{{
  display:flex;align-items:center;gap:8px;flex-wrap:wrap;
  background:var(--card);border:1px solid var(--border);
  border-radius:var(--radius);padding:10px 14px;
  margin-bottom:12px;box-shadow:var(--shadow);
}}
.filter-label{{font-size:12px;color:var(--text-secondary);font-weight:500;white-space:nowrap}}
.filter-btn{{
  padding:4px 12px;border-radius:20px;border:1.5px solid var(--border);
  font-size:12px;font-weight:500;cursor:pointer;transition:all .15s;background:var(--bg);
  color:var(--text-secondary);
}}
.filter-btn:hover{{border-color:currentColor;opacity:.9}}
.filter-btn.active{{color:#fff;border-color:transparent;background:var(--primary)}}
.filter-btn-video{{color:#3B82F6}}
.filter-btn-tuwen{{color:#8B5CF6}}
.filter-btn-homepage{{color:#059669}}
.filter-sep{{width:1px;height:18px;background:var(--border);margin:0 4px}}

.table-card{{background:var(--card);border:1px solid var(--border);border-radius:var(--radius);
  box-shadow:var(--shadow);overflow:hidden}}
.table-toolbar{{
  display:flex;align-items:center;justify-content:space-between;
  padding:10px 14px;border-bottom:1px solid var(--border);
}}
.table-info{{font-size:12px;color:var(--text-secondary)}}
.table-info span{{font-weight:600;color:var(--primary)}}
.table-wrap{{overflow-x:auto}}
table{{width:100%;border-collapse:collapse;font-size:13px}}
thead th{{
  padding:9px 12px;text-align:left;font-size:11px;font-weight:600;
  color:var(--text-secondary);text-transform:uppercase;letter-spacing:.4px;
  background:#F1F5F9;border-bottom:1px solid var(--border);white-space:nowrap;
  cursor:pointer;user-select:none;
}}
thead th:hover{{color:var(--primary)}}
thead th.sorted-asc::after{{content:' ↑'}}
thead th.sorted-desc::after{{content:' ↓'}}
tbody tr{{border-bottom:1px solid #F1F5F9;transition:background .1s}}
tbody tr:hover{{background:#F8FAFC}}
tbody td{{padding:9px 12px;vertical-align:middle}}
tbody tr:last-child{{border-bottom:none}}

.person-badge{{
  display:inline-flex;align-items:center;padding:2px 8px;
  border-radius:12px;font-size:11px;font-weight:600;white-space:nowrap;
}}
.ext-badge{{
  display:inline-flex;align-items:center;padding:2px 6px;
  border-radius:4px;font-size:10px;font-weight:600;
  background:#FFF7ED;color:#C2410C;border:1px solid #FED7AA;margin-left:4px;
}}
.status-badge{{
  display:inline-flex;align-items:center;padding:1px 6px;
  border-radius:4px;font-size:10px;font-weight:500;
}}
.status-active{{background:#ECFDF5;color:#059669}}
.status-inactive{{background:#F8FAFC;color:#94A3B8}}
.mat-name{{max-width:220px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;
  font-size:12px;color:var(--text)}}
.num{{font-family:'Fira Code',monospace;font-size:12px}}
.num-zero{{color:var(--text-muted)}}
.num-hi{{color:var(--success);font-weight:600}}
.gaoquan-cell{{font-family:'Fira Code',monospace;font-size:13px;font-weight:700;color:var(--accent)}}
.gaoquan-zero{{color:var(--text-muted);font-weight:400}}

.btn-play{{
  display:inline-flex;align-items:center;gap:4px;
  padding:4px 10px;border-radius:6px;border:1.5px solid var(--border);
  background:var(--bg);color:var(--primary-light);font-size:11px;font-weight:500;
  cursor:pointer;transition:all .15s;white-space:nowrap;
}}
.btn-play:hover{{background:var(--primary);color:#fff;border-color:var(--primary)}}
.btn-play svg{{width:12px;height:12px;flex-shrink:0}}

.modal-overlay{{
  position:fixed;inset:0;background:rgba(15,23,42,.7);
  display:none;align-items:center;justify-content:center;z-index:1000;
  backdrop-filter:blur(4px);
}}
.modal-overlay.open{{display:flex}}
.modal{{
  background:#0F172A;border-radius:14px;overflow:hidden;
  width:min(900px,95vw);box-shadow:0 25px 50px rgba(0,0,0,.5);
  display:flex;flex-direction:column;max-height:90vh;
}}
.modal-header{{
  display:flex;align-items:center;justify-content:space-between;
  padding:12px 16px;border-bottom:1px solid rgba(255,255,255,.1);
}}
.modal-title{{color:#E2E8F0;font-size:13px;font-weight:500;
  max-width:calc(100% - 40px);overflow:hidden;text-overflow:ellipsis;white-space:nowrap}}
.modal-meta{{display:flex;gap:8px;align-items:center;padding:8px 16px;flex-wrap:wrap;background:#0F172A}}
.modal-badge{{
  padding:3px 8px;border-radius:12px;font-size:11px;font-weight:600;
  background:rgba(255,255,255,.1);color:#CBD5E1;
}}
.modal-badge.accent{{background:#92400E;color:#FDE68A}}
.modal-close{{
  width:28px;height:28px;border-radius:6px;border:none;
  background:rgba(255,255,255,.1);color:#94A3B8;cursor:pointer;
  display:flex;align-items:center;justify-content:center;font-size:18px;
  transition:all .15s;flex-shrink:0;
}}
.modal-close:hover{{background:rgba(255,255,255,.2);color:#fff}}
.video-wrap{{background:#000;display:flex;align-items:center;justify-content:center;flex:1}}
video{{max-width:100%;max-height:65vh;display:block}}
.video-error{{color:#94A3B8;font-size:13px;text-align:center;padding:40px 20px}}
.video-error a{{color:#60A5FA;text-decoration:underline}}

.empty-state{{text-align:center;padding:40px 20px;color:var(--text-muted);font-size:13px}}

/* 对比表格 */
.compare-section{{margin-top:20px}}
.compare-section .table-card .section-title{{margin-bottom:4px}}

@media(max-width:900px){{
  .kpi-grid{{grid-template-columns:repeat(4,1fr)}}
  .charts-row{{grid-template-columns:1fr}}
}}
@media(max-width:600px){{
  .kpi-grid{{grid-template-columns:repeat(2,1fr);gap:8px}}
  .kpi-grid .kpi-card:last-child{{grid-column:span 2;max-width:50%;margin:0 auto;width:100%}}
  .kpi-value{{font-size:18px}}
  .kpi-card{{padding:10px 12px}}
  .page{{padding:10px}}
  .header{{padding:14px 16px 12px}}
  .header-left h1{{font-size:15px}}
  .header-badge{{font-size:11px;padding:4px 10px}}
  .chart-wrap{{height:160px}}
  .filter-bar{{gap:5px;padding:8px 10px}}
  .filter-btn{{padding:3px 9px;font-size:11px}}
  .tabs{{padding:6px 10px}}
  .tab-btn{{padding:4px 10px;font-size:12px}}
  .sort-btn{{padding:3px 7px;font-size:10px}}
  thead th:nth-child(4),
  thead th:nth-child(5),
  thead th:nth-child(7){{display:none}}
  tbody td:nth-child(4),
  tbody td:nth-child(5),
  tbody td:nth-child(7){{display:none}}
  .mat-name{{max-width:130px}}
  table{{font-size:12px}}
  tbody td{{padding:7px 8px}}
  thead th{{padding:7px 8px}}
}}
</style>
</head>
<body>

<div class="header">
  <div class="header-left">
    <h1>引导素材日报</h1>
    <p>数据来源：千川素材看板 · 引导加微</p>
  </div>
  <div class="header-badge">{date_str}</div>
</div>

<div class="page">

  <!-- KPI Cards -->
  <div class="kpi-grid">
    <div class="kpi-card">
      <div class="kpi-label">总消耗</div>
      <div class="kpi-value" id="kpi-spend">¥{total_spend}</div>
      <div class="kpi-sub" id="kpi-count">{material_count} 条素材</div>
    </div>
    <div class="kpi-card">
      <div class="kpi-label">总展示</div>
      <div class="kpi-value" id="kpi-imp">{total_imp}</div>
      <div class="kpi-sub">次曝光</div>
    </div>
    <div class="kpi-card">
      <div class="kpi-label">平均点击率</div>
      <div class="kpi-value" id="kpi-ctr">{avg_ctr}</div>
      <div class="kpi-sub">CTR</div>
    </div>
    <div class="kpi-card">
      <div class="kpi-label">总转化数</div>
      <div class="kpi-value" id="kpi-conv">{total_conv}</div>
      <div class="kpi-sub">次转化</div>
    </div>
    <div class="kpi-card">
      <div class="kpi-label">平均 CPA</div>
      <div class="kpi-value" id="kpi-cpa">¥{avg_cpa}</div>
      <div class="kpi-sub">转化成本</div>
    </div>
    <div class="kpi-card accent">
      <div class="kpi-label">高潜成交</div>
      <div class="kpi-value" id="kpi-gaoquan">{total_gaoquan}</div>
      <div class="kpi-sub">深度转化 · 核心指标</div>
    </div>
    <div class="kpi-card accent">
      <div class="kpi-label">深转率</div>
      <div class="kpi-value" id="kpi-deeprate">{deep_rate}</div>
      <div class="kpi-sub">高潜成交 / 总转化</div>
    </div>
  </div>

  <!-- 多日趋势折线图（仅多日时显示） -->
  <div id="trendSection" style="display:none;margin-bottom:20px">
    <div class="chart-card">
      <div class="section-title">每日趋势：转化数 / 高潜成交 / CPA（近7天）</div>
      <div class="chart-wrap" style="height:200px"><canvas id="chartTrend"></canvas></div>
    </div>
  </div>

  <!-- 多日切换标签（仅多日时显示） -->
  <div id="tabsContainer" style="display:none;margin-bottom:16px">
    <div class="tabs" id="tabHeaders">
      <div class="tabs-sort">
        <button class="sort-btn active" id="sortByDate" onclick="setTabSort('date')">日期 ↑</button>
        <button class="sort-btn" id="sortBySpend" onclick="setTabSort('spend')">消耗 ↓</button>
      </div>
    </div>
  </div>

  <!-- 图表行 -->
  <div class="charts-row">
    <div class="chart-card">
      <div class="section-title">消耗分布（按人）</div>
      <div class="chart-wrap"><canvas id="chartSpend"></canvas></div>
    </div>
    <div class="chart-card">
      <div class="section-title">转化成本 CPA（按人）</div>
      <div class="chart-wrap"><canvas id="chartCPA"></canvas></div>
    </div>
    <div class="chart-card">
      <div class="section-title">转化数（按人）</div>
      <div class="chart-wrap"><canvas id="chartConv"></canvas></div>
    </div>
    <div class="chart-card">
      <div class="section-title">高潜成交（按人）</div>
      <div class="chart-wrap"><canvas id="chartGaoquan"></canvas></div>
    </div>
  </div>

  <!-- 筛选栏 -->
  <div class="filter-bar" style="flex-direction:column;align-items:flex-start;gap:10px">
    <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap">
      <span class="filter-label">类型</span>
      <button class="filter-btn active" data-type="all" onclick="filterType('all',this)">全部</button>
      <button class="filter-btn filter-btn-video" data-type="video" onclick="filterType('video',this)">视频</button>
      <button class="filter-btn filter-btn-tuwen" data-type="tuwen" onclick="filterType('tuwen',this)">图文</button>
      <button class="filter-btn filter-btn-homepage" data-type="homepage" onclick="filterType('homepage',this)">主页</button>
    </div>
    <div style="width:100%;height:1px;background:var(--border)"></div>
    <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap">
      <span class="filter-label">人物</span>
      <button class="filter-btn active" data-person="all" onclick="filterBy('all',this)">全部</button>
      <div class="filter-sep"></div>
      <div id="personFilters" style="display:flex;gap:6px;flex-wrap:wrap"></div>
    </div>
    <div style="width:100%;height:1px;background:var(--border)"></div>
    <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap">
      <span class="filter-label">账户</span>
      <button class="filter-btn active" data-account="all" onclick="filterAccount('all',this)">全部</button>
      <div class="filter-sep"></div>
      <div id="accountFilters" style="display:flex;gap:6px;flex-wrap:wrap"></div>
    </div>
  </div>

  <!-- 素材明细表 -->
  <div class="table-card">
    <div class="table-toolbar">
      <div class="section-title" style="margin:0">素材明细</div>
      <div class="table-info">显示 <span id="visibleCount">-</span> / {material_count} 条 · 点击列头排序</div>
    </div>
    <div class="table-wrap">
      <table id="matTable">
        <thead>
          <tr>
            <th data-col="person">人物</th>
            <th data-col="account">账户</th>
            <th data-col="name">素材名称</th>
            <th data-col="spend" class="sorted-desc">消耗</th>
            <th data-col="impressions">展示数</th>
            <th data-col="ctr">点击率%</th>
            <th data-col="conversions">转化数</th>
            <th data-col="cpa">CPA</th>
            <th data-col="gaoquan" title="高潜成交（深度转化核心指标）">高潜成交 ★</th>
            <th>视频</th>
          </tr>
        </thead>
        <tbody id="tableBody"></tbody>
      </table>
    </div>
    <div class="empty-state" id="emptyState" style="display:none">该筛选条件下暂无数据</div>
  </div>

  <!-- 多日对比表（仅多日时显示） -->
  <div id="compareSection" style="display:none;margin-top:20px">
    <div class="table-card">
      <div class="table-toolbar">
        <div class="section-title" style="margin:0">多日趋势对比</div>
        <div style="display:flex;align-items:center;gap:8px">
          <div id="compareColBtns" style="display:flex;gap:4px"></div>
          <button class="sort-btn active" id="compareSortBtn" onclick="toggleCompareSort()" style="margin-left:4px">总消耗 ↓</button>
        </div>
      </div>
      <div class="table-wrap">
        <table class="compare-table">
          <thead id="compareHead"></thead>
          <tbody id="compareBody"></tbody>
        </table>
      </div>
    </div>
  </div>

</div><!-- /page -->

<!-- Video Modal -->
<div class="modal-overlay" id="videoModal" onclick="closeModal(event)">
  <div class="modal" onclick="event.stopPropagation()">
    <div class="modal-header">
      <div class="modal-title" id="modalTitle">素材名称</div>
      <button class="modal-close" onclick="closeModal()">✕</button>
    </div>
    <div class="modal-meta" id="modalMeta"></div>
    <div class="video-wrap" id="videoWrap"></div>
  </div>
</div>

<script>
// ---------- 注入数据 ----------
const PERSON_COLORS = {person_colors_js};
const PERSON_BG = {person_bg_js};
const ALL_ROWS = {rows_js};
const P_LABELS = {person_labels};
const P_SPEND = {person_spend};
const P_CPA = {person_cpa};
const P_COLORS = {person_bg_arr};
const IS_MULTI = {is_multi};
const COMPARE_DATA = {compare_js};
const ALL_DATES = {all_dates_js};
const ALL_ROWS_BY_DATE = {all_rows_by_date_js};

// ---------- 图表 ----------
const chartDefaults = {{
  responsive: true, maintainAspectRatio: false,
  plugins: {{ legend: {{ display: false }}, tooltip: {{ callbacks: {{}} }} }},
  scales: {{ x: {{ grid: {{ color: '#F1F5F9' }} }}, y: {{ grid: {{ color: '#F1F5F9' }}, ticks: {{ font: {{ size: 11 }} }} }} }},
}};

let trendChart;

function initTrendChart() {{
  if (!IS_MULTI) return;
  const trend = COMPARE_DATA.trend || [];
  const labels      = trend.map(t => t.date);
  const convData    = trend.map(t => t.conv);
  const gqData      = trend.map(t => t.gaoquan);
  const cpaData     = trend.map(t => t.cpa);
  const deepRateData= trend.map(t => t.conv > 0 ? parseFloat((t.gaoquan / t.conv * 100).toFixed(1)) : 0);

  if (trendChart) trendChart.destroy();
  trendChart = new Chart(document.getElementById('chartTrend'), {{
    type: 'line',
    data: {{
      labels,
      datasets: [
        {{
          label: '转化数', data: convData, yAxisID: 'y',
          borderColor: '#3B82F6', backgroundColor: '#3B82F620',
          borderWidth: 2, pointRadius: 4, pointHoverRadius: 6,
          fill: true, tension: 0.3,
        }},
        {{
          label: '高潜成交', data: gqData, yAxisID: 'y',
          borderColor: '#D97706', backgroundColor: '#D9770620',
          borderWidth: 2, pointRadius: 4, pointHoverRadius: 6,
          fill: true, tension: 0.3,
        }},
        {{
          label: 'CPA(¥)', data: cpaData, yAxisID: 'yRight',
          borderColor: '#10B981', backgroundColor: 'transparent',
          borderWidth: 2, borderDash: [4, 3],
          pointRadius: 4, pointHoverRadius: 6,
          fill: false, tension: 0.3,
        }},
        {{
          label: '深转率(%)', data: deepRateData, yAxisID: 'yRight',
          borderColor: '#8B5CF6', backgroundColor: 'transparent',
          borderWidth: 2, borderDash: [2, 4],
          pointRadius: 4, pointHoverRadius: 6,
          fill: false, tension: 0.3,
        }},
      ]
    }},
    options: {{
      responsive: true, maintainAspectRatio: false,
      interaction: {{ mode: 'index', intersect: false }},
      plugins: {{
        legend: {{ display: true, position: 'top',
          labels: {{ font: {{ size: 11 }}, boxWidth: 12, padding: 12 }} }},
        tooltip: {{ callbacks: {{
          label: ctx => {{
            if (ctx.dataset.label === 'CPA(¥)') return ' CPA: ¥' + ctx.parsed.y.toFixed(2);
            if (ctx.dataset.label === '深转率(%)') return ' 深转率: ' + ctx.parsed.y.toFixed(1) + '%';
            return ' ' + ctx.dataset.label + ': ' + ctx.parsed.y.toFixed(0);
          }}
        }} }}
      }},
      scales: {{
        x: {{ grid: {{ color: '#F1F5F9' }}, ticks: {{ font: {{ size: 11 }} }} }},
        y: {{
          position: 'left', grid: {{ color: '#F1F5F9' }},
          ticks: {{ font: {{ size: 11 }}, stepSize: 1 }},
          title: {{ display: true, text: '次数', font: {{ size: 10 }}, color: '#94A3B8' }}
        }},
        yRight: {{
          position: 'right', grid: {{ drawOnChartArea: false }},
          ticks: {{ font: {{ size: 11 }}, callback: v => v }},
          title: {{ display: true, text: 'CPA(¥) / 深转率(%)', font: {{ size: 10 }}, color: '#94A3B8' }}
        }}
      }}
    }}
  }});
}}

let spendChart, cpaChart, convChart, gaoquanChart;

function initCharts(labels, spendData, cpaData, convData, gaoquanData) {{
  const colors = labels.map(p => PERSON_COLORS[p] || '#94A3B8');
  if (spendChart) spendChart.destroy();
  if (cpaChart) cpaChart.destroy();
  if (convChart) convChart.destroy();
  if (gaoquanChart) gaoquanChart.destroy();

  const makeBar = (id, label, data, prefix, color) => new Chart(document.getElementById(id), {{
    type: 'bar',
    data: {{ labels, datasets: [{{ label, data, backgroundColor: color || colors, borderRadius: 4 }}] }},
    options: {{
      ...chartDefaults,
      plugins: {{ ...chartDefaults.plugins, tooltip: {{ callbacks: {{ label: ctx => ' ' + prefix + ctx.parsed.y.toFixed(prefix === '¥' ? 2 : 0) }} }} }},
      scales: {{ ...chartDefaults.scales, y: {{ ...chartDefaults.scales.y,
        ticks: {{ font: {{size:11}}, callback: v => prefix + v }} }} }}
    }}
  }});

  spendChart   = makeBar('chartSpend',   '消耗(元)',   spendData,   '¥', null);
  cpaChart     = makeBar('chartCPA',     'CPA(元)',    cpaData,     '¥', null);
  convChart    = makeBar('chartConv',    '转化数',     convData,    '',  null);
  gaoquanChart = makeBar('chartGaoquan', '高潜成交',   gaoquanData, '',  colors.map((c,i) => labels[i] === '高潜成交' ? '#D97706' : c));
}}

// ---------- 渲染单日 ----------
function renderDay(rows, dateLabel) {{
  // 计算当日汇总
  let ts=0, ti=0, tc=0, tz=0, tg=0;
  rows.forEach(r => {{ ts+=r.spend; ti+=r.impressions; tc+=r.clicks; tz+=r.conversions; tg+=r.gaoquan; }});
  const cpa = tz ? ts/tz : 0;
  const ctr = ti ? tc/ti*100 : 0;
  document.getElementById('kpi-spend').textContent  = '¥' + ts.toLocaleString('zh',{{minimumFractionDigits:2,maximumFractionDigits:2}});
  document.getElementById('kpi-count').textContent  = rows.length + ' 条素材';
  document.getElementById('kpi-imp').textContent    = ti.toLocaleString('zh',{{maximumFractionDigits:0}});
  document.getElementById('kpi-ctr').textContent    = ctr.toFixed(2) + '%';
  document.getElementById('kpi-conv').textContent   = tz.toFixed(0);
  document.getElementById('kpi-cpa').textContent    = '¥' + cpa.toFixed(2);
  document.getElementById('kpi-gaoquan').textContent= tg.toFixed(0);
  document.getElementById('kpi-deeprate').textContent= (tz ? (tg/tz*100).toFixed(1)+'%' : '—');
  // 更新筛选器（基于当前行）
  const persons = [...new Set(rows.map(r => r.person))];
  const container = document.getElementById('personFilters');
  container.innerHTML = '';
  persons.forEach(p => {{
    const btn = document.createElement('button');
    btn.className = 'filter-btn';
    btn.dataset.person = p;
    btn.textContent = p;
    btn.style.color = PERSON_COLORS[p] || '#64748B';
    btn.onclick = function(){{ filterBy(p, this); }};
    container.appendChild(btn);
  }});
  // 重置人物筛选为全部
  document.querySelectorAll('.filter-btn[data-person]').forEach(b => {{
    b.classList.remove('active');
    b.style.background = '';
    if (b.dataset.person !== 'all') b.style.color = PERSON_COLORS[b.dataset.person] || '#64748B';
    else b.style.color = 'var(--text-secondary)';
  }});
  const allBtn = document.querySelector('.filter-btn[data-person="all"]');
  if (allBtn) {{ allBtn.classList.add('active'); allBtn.style.background = 'var(--primary)'; allBtn.style.color = '#fff'; }}
  currentFilter = 'all';
  // 更新账户筛选器
  const accounts = [...new Set(rows.map(r => r.account).filter(Boolean))];
  const acContainer = document.getElementById('accountFilters');
  acContainer.innerHTML = '';
  accounts.forEach(a => {{
    const btn = document.createElement('button');
    btn.className = 'filter-btn';
    btn.dataset.account = a;
    btn.textContent = a.replace('高中---猿起武汉-', '').replace('猿辅导', '辅导');
    btn.title = a;
    btn.onclick = function(){{ filterAccount(a, this); }};
    acContainer.appendChild(btn);
  }});
  // 重置账户筛选为全部
  document.querySelectorAll('.filter-btn[data-account]').forEach(b => {{
    b.classList.remove('active');
    b.style.background = '';
    b.style.color = 'var(--text-secondary)';
  }});
  const allAccBtn = document.querySelector('.filter-btn[data-account="all"]');
  if (allAccBtn) {{ allAccBtn.classList.add('active'); allAccBtn.style.background = 'var(--primary)'; allAccBtn.style.color = '#fff'; }}
  currentAccountFilter = 'all';
  // 更新表格数据源
  window.currentRows = rows;
  renderTable();

  // 更新图表
  const agg = {{}};
  rows.forEach(r => {{
    const p = r.person;
    if (!agg[p]) agg[p] = {{ spend:0, conv:0, gaoquan:0 }};
    agg[p].spend   += r.spend;
    agg[p].conv    += r.conversions;
    agg[p].gaoquan += r.gaoquan;
  }});
  const labels = Object.keys(agg).sort((a,b) => agg[b].spend - agg[a].spend);
  const spendData   = labels.map(p => agg[p].spend);
  const cpaData     = labels.map(p => (agg[p].conv ? agg[p].spend / agg[p].conv : 0));
  const convData    = labels.map(p => agg[p].conv);
  const gaoquanData = labels.map(p => agg[p].gaoquan);
  initCharts(labels, spendData, cpaData, convData, gaoquanData);
}}

// ---------- 表格排序 ----------
let currentFilter = 'all';
let currentType = 'all';
let currentAccountFilter = 'all';
let sortCol = 'spend';
let sortAsc = false;

function filterType(type, btn) {{
  currentType = type;
  const colors = {{ video:'#3B82F6', tuwen:'#8B5CF6', homepage:'#059669' }};
  document.querySelectorAll('.filter-btn[data-type]').forEach(b => {{
    b.classList.remove('active');
    b.style.background = '';
    b.style.color = b.dataset.type === 'all' ? 'var(--text-secondary)' : (colors[b.dataset.type] || '#64748B');
  }});
  btn.classList.add('active');
  if (type !== 'all') {{
    btn.style.background = colors[type];
    btn.style.color = '#fff';
  }} else {{
    btn.style.background = 'var(--primary)';
    btn.style.color = '#fff';
  }}
  renderTable();
}}

function filterBy(person, btn) {{
  currentFilter = person;
  document.querySelectorAll('.filter-btn[data-person]').forEach(b => {{
    b.classList.remove('active');
    b.style.background = '';
    b.style.color = b.dataset.person === 'all' ? 'var(--text-secondary)' : (PERSON_COLORS[b.dataset.person] || '#64748B');
  }});
  btn.classList.add('active');
  if (person !== 'all') {{
    btn.style.background = PERSON_COLORS[person] || '#1E40AF';
    btn.style.color = '#fff';
  }} else {{
    btn.style.background = 'var(--primary)';
    btn.style.color = '#fff';
  }}
  renderTable();
}}

function filterAccount(account, btn) {{
  currentAccountFilter = account;
  document.querySelectorAll('.filter-btn[data-account]').forEach(b => {{
    b.classList.remove('active');
    b.style.background = '';
    b.style.color = 'var(--text-secondary)';
  }});
  btn.classList.add('active');
  btn.style.background = account === 'all' ? 'var(--primary)' : '#475569';
  btn.style.color = '#fff';
  renderTable();
}}

document.querySelectorAll('thead th[data-col]').forEach(th => {{
  th.onclick = function() {{
    const col = this.dataset.col;
    if (sortCol === col) sortAsc = !sortAsc;
    else {{ sortCol = col; sortAsc = col === 'name' || col === 'person'; }}
    document.querySelectorAll('thead th').forEach(t => t.classList.remove('sorted-asc','sorted-desc'));
    this.classList.add(sortAsc ? 'sorted-asc' : 'sorted-desc');
    renderTable();
  }};
}});

function sortRows(rows) {{
  return [...rows].sort((a, b) => {{
    let va = a[sortCol], vb = b[sortCol];
    if (typeof va === 'string') return sortAsc ? va.localeCompare(vb,'zh') : vb.localeCompare(va,'zh');
    return sortAsc ? va - vb : vb - va;
  }});
}}

function fmt(n) {{
  if (n === 0 || n === null || n === undefined) return '<span class="num num-zero">—</span>';
  return '<span class="num">' + n.toFixed(2) + '</span>';
}}
function fmtInt(n) {{
  if (!n) return '<span class="num num-zero">—</span>';
  return '<span class="num">' + n.toLocaleString() + '</span>';
}}

function renderTable() {{
  const rows = window.currentRows || ALL_ROWS;
  const filtered = (currentFilter === 'all' ? rows : rows.filter(r => r.person === currentFilter))
    .filter(r => r.spend > 0)
    .filter(r => currentAccountFilter === 'all' ? true : r.account === currentAccountFilter)
    .filter(r => currentType === 'all' ? true :
      currentType === 'tuwen' ? (r.is_tuwen && !r.is_homepage) :
      currentType === 'homepage' ? r.is_homepage :
      (!r.is_tuwen && !r.is_homepage));
  const sorted = sortRows(filtered);
  const tbody = document.getElementById('tableBody');
  const empty = document.getElementById('emptyState');
  document.getElementById('visibleCount').textContent = sorted.length;

  if (!sorted.length) {{ tbody.innerHTML = ''; empty.style.display = 'block'; return; }}
  empty.style.display = 'none';

  tbody.innerHTML = sorted.map((r, i) => {{
    const pc = PERSON_COLORS[r.person] || '#94A3B8';
    const bg = PERSON_BG[r.person]  || '#F8FAFC';
    const extBadge = r.is_external ? '<span class="ext-badge">外部</span>' : '';
    const tuwenBadge = r.is_tuwen ? '<span class="ext-badge" style="background:#F5F3FF;color:#7C3AED;border-color:#DDD6FE">图文</span>' : '';
    const homepageBadge = r.is_homepage ? '<span class="ext-badge" style="background:#ECFDF5;color:#059669;border-color:#A7F3D0">主页</span>' : '';
    const collabBadge = r.collab ? `<span class="ext-badge" style="background:#F0F9FF;color:#0369A1;border-color:#BAE6FD">${{r.collab}}</span>` : '';
    const statusCls = r.status === '已使用' ? 'status-active' : 'status-inactive';
    const cpaDisp = r.cpa > 0 ? fmt(r.cpa) : '<span class="num num-zero">—</span>';
    const gaoquanDisp = r.gaoquan > 0
      ? '<span class="gaoquan-cell">' + r.gaoquan + '</span>'
      : '<span class="gaoquan-zero num-zero">—</span>';
    const hasVideo = r.video_url && r.video_url.length > 10 && !r.is_tuwen && !r.is_homepage;
    const playBtn = hasVideo
      ? `<button class="btn-play" onclick="openVideoByName('${{encodeURIComponent(r.name)}}')">
           <svg viewBox="0 0 16 16" fill="currentColor"><path d="M4 3l10 5-10 5V3z"/></svg>播放
         </button>`
      : '<span style="color:var(--text-muted);font-size:11px">无链接</span>';
    return `<tr>
      <td><span class="person-badge" style="background:${{bg}};color:${{pc}}">${{r.person}}</span></td>
      <td><span style="font-size:11px;color:var(--text-secondary);white-space:nowrap" title="${{r.account}}">${{(r.account||'').replace('高中---猿起武汉-','').replace('猿辅导','辅导')}}</span></td>
      <td><div style="display:flex;align-items:center;gap:4px">
        <span class="mat-name" title="${{r.name}}">${{r.name}}</span>${{extBadge}}${{tuwenBadge}}${{homepageBadge}}${{collabBadge}}</div></td>
      <td>${{fmt(r.spend)}}</td>
      <td>${{fmtInt(r.impressions)}}</td>
      <td><span class="num">${{r.ctr > 0 ? r.ctr.toFixed(2)+'%' : '—'}}</span></td>
      <td>${{r.conversions > 0 ? '<span class="num num-hi">'+r.conversions+'</span>' : '<span class="num num-zero">—</span>'}}</td>
      <td>${{cpaDisp}}</td>
      <td>${{gaoquanDisp}}</td>
      <td>${{playBtn}}</td>
    </tr>`;
  }}).join('');
}}

// ---------- 视频弹窗 ----------
function openVideoByName(encodedName) {{
  const name = decodeURIComponent(encodedName);
  const rows = window.currentRows || ALL_ROWS;
  const r = rows.find(x => x.name === name);
  if (!r) return;
  document.getElementById('modalTitle').textContent = name;
  const meta = document.getElementById('modalMeta');
  const pc = PERSON_COLORS[r.person] || '#64748B';
  meta.innerHTML = `
    <span class="modal-badge" style="background:${{pc}}22;color:${{pc}}">${{r.person}}</span>
    ${{r.is_external ? '<span class="modal-badge" style="background:#92400E44;color:#FDE68A">外部素材</span>' : ''}}
    <span class="modal-badge">消耗 ¥${{r.spend.toFixed(2)}}</span>
    <span class="modal-badge">转化 ${{r.conversions}}</span>
    <span class="modal-badge">CPA ¥${{r.cpa > 0 ? r.cpa.toFixed(2) : '—'}}</span>
    ${{r.gaoquan > 0 ? '<span class="modal-badge accent">高潜成交 ' + r.gaoquan + '</span>' : ''}}
  `;
  const wrap = document.getElementById('videoWrap');
  if (r.video_url) {{
    wrap.innerHTML = `<video controls autoplay preload="metadata" style="max-width:100%;max-height:65vh">
      <source src="${{r.video_url}}" type="video/mp4">
      <div class="video-error">浏览器不支持内嵌播放。<br><a href="${{r.video_url}}" target="_blank">点击在新窗口打开视频</a></div>
    </video>`;
  }} else {{
    wrap.innerHTML = '<div class="video-error">暂无视频链接</div>';
  }}
  document.getElementById('videoModal').classList.add('open');
  document.body.style.overflow = 'hidden';
}}

function closeModal(e) {{
  if (e && e.target !== document.getElementById('videoModal') && !e.currentTarget?.classList?.contains('modal-close')) return;
  document.getElementById('videoModal').classList.remove('open');
  document.getElementById('videoWrap').innerHTML = '';
  document.body.style.overflow = '';
}}

document.addEventListener('keydown', e => {{ if (e.key === 'Escape') closeModal({{target:document.getElementById('videoModal')}}); }});

// ---------- 多日 Tab ----------
function initTabs() {{
  if (!IS_MULTI) return;

  // 预计算每日消耗（用于按消耗排序）
  const daySpend = {{}};
  ALL_DATES.forEach(d => {{
    const rows = ALL_ROWS_BY_DATE[d] || [];
    daySpend[d] = rows.reduce((s, r) => s + r.spend, 0);
  }});

  let tabSortMode = 'date';   // 'date' | 'spend'
  let tabSortAsc  = true;
  let activeDate  = ALL_DATES[ALL_DATES.length - 1];

  function getSortedDates() {{
    return [...ALL_DATES].sort((a, b) => {{
      if (tabSortMode === 'spend') {{
        return tabSortAsc ? daySpend[a] - daySpend[b] : daySpend[b] - daySpend[a];
      }}
      return tabSortAsc ? a.localeCompare(b) : b.localeCompare(a);
    }});
  }}

  function switchDay(date) {{
    activeDate = date;
    renderDay(ALL_ROWS_BY_DATE[date] || [], date);
    renderCompare();
  }}

  function renderTabButtons() {{
    const sorted = getSortedDates();
    const container = document.getElementById('tabHeaders');
    // 清除旧的 tab 按钮（保留排序按钮）
    container.querySelectorAll('.tab-btn, .tab-select, .tabs-label').forEach(el => el.remove());

    const sortDiv = container.querySelector('.tabs-sort');

    if (sorted.length <= 7) {{
      sorted.forEach((d) => {{
        const btn = document.createElement('button');
        btn.className = 'tab-btn' + (d === activeDate ? ' active' : '');
        btn.textContent = d + ' ¥' + daySpend[d].toFixed(0);
        btn.onclick = () => {{
          container.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
          btn.classList.add('active');
          switchDay(d);
        }};
        container.insertBefore(btn, sortDiv);
      }});
    }} else {{
      const label = document.createElement('span');
      label.className = 'tabs-label';
      label.textContent = '选择日期';
      container.insertBefore(label, sortDiv);
      const sel = document.createElement('select');
      sel.className = 'tab-select';
      sorted.forEach(d => {{
        const opt = document.createElement('option');
        opt.value = d;
        opt.textContent = d + ' ¥' + daySpend[d].toFixed(0);
        if (d === activeDate) opt.selected = true;
        sel.appendChild(opt);
      }});
      sel.addEventListener('change', () => switchDay(sel.value));
      container.insertBefore(sel, sortDiv);
    }}
  }}

  window.setTabSort = function(mode) {{
    if (tabSortMode === mode) {{
      tabSortAsc = !tabSortAsc;
    }} else {{
      tabSortMode = mode;
      tabSortAsc = mode === 'date';   // 日期默认升序，消耗默认降序
    }}
    const dateBtn  = document.getElementById('sortByDate');
    const spendBtn = document.getElementById('sortBySpend');
    dateBtn.classList.toggle('active', mode === 'date');
    spendBtn.classList.toggle('active', mode === 'spend');
    dateBtn.textContent  = '日期 ' + (tabSortMode === 'date'  ? (tabSortAsc ? '↑' : '↓') : '↑');
    spendBtn.textContent = '消耗 ' + (tabSortMode === 'spend' ? (tabSortAsc ? '↑' : '↓') : '↓');
    renderTabButtons();
  }};

  renderTabButtons();
  switchDay(activeDate);
}}

// ---------- 对比表 ----------
let compareSortAsc = false;
let compareActiveDates = null;  // null = 全部日期

function toggleCompareSort() {{
  compareSortAsc = !compareSortAsc;
  document.getElementById('compareSortBtn').textContent = '总消耗 ' + (compareSortAsc ? '↑' : '↓');
  renderCompare();
}}

function initCompareCols() {{
  const dates = ALL_DATES;
  // 默认只展示最近7天
  compareActiveDates = dates.slice(-7);
  const container = document.getElementById('compareColBtns');

  function rebuild() {{
    container.innerHTML = '';
    if (dates.length <= 7) {{
      dates.forEach(d => {{
        const btn = document.createElement('button');
        const isActive = compareActiveDates.includes(d);
        btn.className = 'sort-btn' + (isActive ? ' active' : '');
        btn.textContent = d;
        btn.onclick = () => {{
          if (compareActiveDates.includes(d)) {{
            if (compareActiveDates.length === 1) return;
            compareActiveDates = compareActiveDates.filter(x => x !== d);
          }} else {{
            compareActiveDates = dates.filter(x => compareActiveDates.includes(x) || x === d);
          }}
          rebuild();
          renderCompare();
        }};
        container.appendChild(btn);
      }});
    }} else {{
      // 超过7天：显示最近7天的胶囊按钮 + "更多"展开其余
      const recentDates = dates.slice(-7);
      const olderDates  = dates.slice(0, -7);

      // 先渲染最近7天按钮
      recentDates.forEach(d => {{
        const btn = document.createElement('button');
        const isActive = compareActiveDates.includes(d);
        btn.className = 'sort-btn' + (isActive ? ' active' : '');
        btn.textContent = d;
        btn.onclick = () => {{
          if (compareActiveDates.includes(d)) {{
            if (compareActiveDates.length === 1) return;
            compareActiveDates = compareActiveDates.filter(x => x !== d);
          }} else {{
            compareActiveDates = dates.filter(x => compareActiveDates.includes(x) || x === d);
          }}
          rebuild();
          renderCompare();
        }};
        container.appendChild(btn);
      }});

      // 历史日期用下拉
      if (olderDates.length > 0) {{
        const sep = document.createElement('span');
        sep.style.cssText = 'width:1px;height:18px;background:var(--border);margin:0 4px;display:inline-block';
        container.appendChild(sep);

        const sel = document.createElement('select');
        sel.className = 'tab-select';
        sel.style.cssText = 'padding:3px 8px;font-size:11px;min-width:90px';
        const placeholder = document.createElement('option');
        placeholder.value = ''; placeholder.textContent = '历史日期...';
        placeholder.disabled = true; placeholder.selected = true;
        sel.appendChild(placeholder);
        olderDates.forEach(d => {{
          const opt = document.createElement('option');
          opt.value = d;
          opt.textContent = d + (compareActiveDates.includes(d) ? ' ✓' : '');
          sel.appendChild(opt);
        }});
        sel.onchange = () => {{
          const d = sel.value;
          if (!d) return;
          if (compareActiveDates.includes(d)) {{
            if (compareActiveDates.length === 1) return;
            compareActiveDates = compareActiveDates.filter(x => x !== d);
          }} else {{
            compareActiveDates = dates.filter(x => compareActiveDates.includes(x) || x === d);
          }}
          sel.value = '';
          rebuild();
          renderCompare();
        }};
        container.appendChild(sel);
      }}
    }}
  }}
  rebuild();
}}

function renderCompare() {{
  if (!IS_MULTI) return;
  const head = document.getElementById('compareHead');
  const body = document.getElementById('compareBody');
  const dates = compareActiveDates || ALL_DATES;
  head.innerHTML = `<tr><th>素材名称</th>${{dates.map(d => `<th>${{d}}</th>`).join('')}}<th style="cursor:pointer" onclick="toggleCompareSort()">总消耗 ${{compareSortAsc?'↑':'↓'}}</th></tr>`;
  let matRows = (COMPARE_DATA.mat_rows || []).filter(m =>
    ALL_DATES.some(d => (m['s_'+d] || 0) > 0)
  );
  // 按当前可见日期重算总消耗再排序
  matRows = matRows.map(m => ({{
    ...m,
    _visTotal: dates.reduce((s, d) => s + (m['s_'+d] || 0), 0)
  }})).sort((a, b) => compareSortAsc ? a._visTotal - b._visTotal : b._visTotal - a._visTotal);

  body.innerHTML = matRows.map(m => `
    <tr>
      <td style="font-weight:500;max-width:200px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="${{m.name}}">${{m.name}}</td>
      ${{dates.map(d => `<td><span class="num">${{(m['s_'+d]||0)>0 ? '¥'+(m['s_'+d]).toFixed(2) : '<span class=\\"num-zero\\">—</span>'}}</span></td>`).join('')}}
      <td><strong>¥${{m._visTotal.toFixed(2)}}</strong></td>
    </tr>
  `).join('') || '<tr><td colspan="' + (dates.length+2) + '" class="empty-state">暂无数据</td></tr>';
}}

// ---------- 初始化 ----------
document.addEventListener('DOMContentLoaded', function() {{
  if (!IS_MULTI) {{
    renderDay(ALL_ROWS, '');
  }} else {{
    document.getElementById('tabsContainer').style.display = '';
    document.getElementById('compareSection').style.display = '';
    document.getElementById('trendSection').style.display = '';
    initTrendChart();
    initCompareCols();
    initTabs();
  }}
}});
</script>
</body>
</html>
"""

def generate_html(days_data):
    latest_label, latest_rows = days_data[-1]
    ls = compute_stats(latest_rows)
    is_multi = len(days_data) > 1

    # 最新日的人名数据用于图表
    sorted_persons = sorted(
        [(p, d) for p, d in ls['by_person'].items() if d['消耗'] > 0],
        key=lambda x: -x[1]['消耗']
    )
    person_labels = json.dumps([p for p, _ in sorted_persons], ensure_ascii=False)
    person_spend = json.dumps([round(d['消耗'], 2) for _, d in sorted_persons])
    person_cpa = json.dumps([round(d['CPA'], 2) for _, d in sorted_persons])
    person_bg_arr = json.dumps([PERSON_COLORS.get(p, '#94A3B8') for p, _ in sorted_persons])

    # 多日对比数据
    compare_data = build_compare(days_data) if is_multi else {}

    return HTML_TEMPLATE.format(
        date_str=latest_label,
        total_spend=f"{ls['total_spend']:,.2f}",
        total_imp=f"{ls['total_imp']:,.0f}",
        total_conv=f"{ls['total_conv']:.0f}",
        avg_cpa=f"{ls['avg_cpa']:.2f}",
        avg_ctr=f"{ls['avg_ctr']:.2f}%",
        total_gaoquan=f"{ls['total_gaoquan']:.0f}",
        deep_rate=f"{ls['total_gaoquan']/ls['total_conv']*100:.1f}%" if ls['total_conv'] else '—',
        material_count=str(len(latest_rows)),
        person_colors_js=json.dumps(PERSON_COLORS, ensure_ascii=False),
        person_bg_js=json.dumps(PERSON_BG, ensure_ascii=False),
        rows_js=json.dumps(rows_to_json(latest_rows), ensure_ascii=False),
        person_labels=person_labels,
        person_spend=person_spend,
        person_cpa=person_cpa,
        person_bg_arr=person_bg_arr,
        is_multi='true' if is_multi else 'false',
        compare_js=json.dumps(compare_data, ensure_ascii=False) if is_multi else '{}',
        all_dates_js=json.dumps([l for l, _ in days_data], ensure_ascii=False),
        all_rows_by_date_js=json.dumps(
            {l: rows_to_json(r) for l, r in days_data}, ensure_ascii=False
        ),
    )

def main():
    data_dir = Path(__file__).parent.parent / 'data'
    files = sorted(f for f in data_dir.glob('引导加微每日数据-*.csv')
                   if re.fullmatch(r'引导加微每日数据-\d{4}', f.stem))
    if sys.argv[1:]:
        files = [Path(sys.argv[1])]

    if not files:
        print('找不到数据文件')
        sys.exit(1)

    days_data = []
    for f in files:
        m = re.search(r'(\d{4})', f.stem)
        mmdd = m.group(1) if m else f.stem[-4:]
        label = f"{mmdd[:2]}/{mmdd[2:]}"
        rows = load_csv(f)
        days_data.append((label, rows))
        s = compute_stats(rows)
        print(f"{label}: {len(rows)}条  消耗¥{s['total_spend']:.2f}  转化{s['total_conv']:.0f}  高潜{s['total_gaoquan']:.0f}")

    html = generate_html(days_data)

    out_dir = Path(__file__).parent.parent / 'reports'
    out_dir.mkdir(exist_ok=True)
    latest_mmdd = re.search(r'(\d{4})', files[-1].stem).group(1)
    out_path = out_dir / f'引导素材每日分析_{latest_mmdd}.html'
    with open(out_path, 'w', encoding='utf-8') as f:
        f.write(html)
    print(f'报告已生成: {out_path}')

if __name__ == '__main__':
    main()