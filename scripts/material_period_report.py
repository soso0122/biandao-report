#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
素材周期表现看板（独立脚本，不影响任何日报）

读 data/引导加微每日数据-*.csv 全部日期，把数据按期次切分（固定 N 天一期，
从最新日期往前回切），页面可切换期次查看每期素材表现，并支持素材名称搜索定位、
按人/类型/标签/状态筛选、列排序、行展开看逐日/逐周轨迹。

用法:
  python3 scripts/material_period_report.py            # 期次长度 7 天（默认）
  python3 scripts/material_period_report.py --days 14  # 期次长度 14 天

口径（沿用日报/生命周期分析既有规则）:
  - 在投 = 当天消耗 > 0；深转 = 回访-高潜成交(计费时间)
  - 主页素材（纯数字/科学计数法名称）排除
  - 素材身份：名字 → 主素材id（同名取累计消耗最大的id）→ 自带id → 名字+账户
  - CTR = 点击/展示；CVR = 转化/点击；深转率 = 高潜/转化（期次内汇总后重算）
  - 环比 = 选中期次 vs 上一期（等长固定天数）
"""
import csv, json, re, sys
from pathlib import Path
from collections import defaultdict

ROOT = Path(__file__).parent.parent
DATA = ROOT / 'data'
OUT  = ROOT / 'reports'

# 渠道账户：不进明细（会拉低深转率）
CHANNEL_ACCOUNTS = {'1873204791217159', '1873204789662083', '1872584956721257', '1869499299085324'}  # jl01-jl04

EDITORS = ['小敏', '嘉丽', '浩正', '雅迪', '婷玉']          # 编导（优先）
CUTTERS = ['魏怡', '瑞晨', '国星']                          # 剪辑

PERSON_COLORS = {
    '小敏': '#3B82F6', '嘉丽': '#8B5CF6', '瑞晨': '#10B981',
    '浩正': '#F59E0B', '雅迪': '#EC4899', '魏怡': '#EF4444',
    '婷玉': '#14B8A6', 'AI': '#6366F1', '外部': '#F97316', '其他': '#94A3B8',
}
PERSON_BG = {
    '小敏': '#EFF6FF', '嘉丽': '#F5F3FF', '瑞晨': '#ECFDF5',
    '浩正': '#FFFBEB', '雅迪': '#FDF2F8', '魏怡': '#FEF2F2',
    '婷玉': '#F0FDFA', 'AI': '#EEF2FF', '外部': '#FFF7ED', '其他': '#F8FAFC',
}


def fnum(v):
    try:
        return float(str(v or '0').replace(',', ''))
    except Exception:
        return 0.0


def is_homepage(name):
    n = name.strip()
    return bool(re.fullmatch(r'\d+', n) or re.fullmatch(r'[\d.]+[eE][+\-]?\d+', n))


def is_ai(name):
    return name.strip().upper().startswith('AI')


def has_known_person(name):
    return any(p in name for p in EDITORS + CUTTERS)


def extract_person(name):
    for p in EDITORS:
        if p in name:
            return p
    for p in CUTTERS:
        if p in name:
            return p
    return '其他'


def clean_name(name):
    return re.sub(r'\.mp4\.mp4$', '.mp4', name.strip())


def load_label_map():
    """历史打标：素材id 优先，名称兜底（含去 推送视频_ 前缀）"""
    label_map = {}
    lf = DATA / '历史打标.csv'
    if lf.exists():
        with open(lf, encoding='utf-8-sig') as f:
            for r in csv.DictReader(f):
                sid = (r.get('素材id') or '').strip()
                name = (r.get('视频名称') or '').strip()
                tag = (r.get('标签') or '').strip()
                if sid:
                    label_map[sid] = tag
                if name:
                    label_map[name] = tag
    return label_map


def get_tag(name, sid, label_map):
    tag = label_map.get(sid) or label_map.get(name)
    if not tag and name.startswith('推送视频_'):
        tag = label_map.get(name[len('推送视频_'):]) or ''
    if not tag:
        tags = re.findall(r'A[1-4]', name)
        tag = ','.join(sorted(set(tags)))
    return tag


def main():
    args = sys.argv[1:]
    period_len = 7
    if '--days' in args:
        period_len = max(1, int(args[args.index('--days') + 1]))

    files = [x for x in sorted(DATA.glob('引导加微每日数据-*.csv'))
             if re.fullmatch(r'引导加微每日数据-\d{4}', x.stem)]
    if not files:
        print('找不到 data/引导加微每日数据-*.csv')
        sys.exit(1)

    label_map = load_label_map()

    # ---------- 第一遍：名字 → 主素材id（同名多个 id 取累计消耗最大者） ----------
    name_to_id = {}
    id_spend = defaultdict(float)
    for fp in files:
        with open(fp, encoding='utf-8-sig') as fh:
            for r in csv.DictReader(fh):
                name = clean_name((r.get('视频名称') or '').strip())
                sid = (r.get('素材id') or '').strip()
                if not sid or not name:
                    continue
                sp = fnum(r.get('消耗'))
                id_spend[sid] += sp
                for n in {name, name[5:] if name.startswith('推送视频_') else name}:
                    if not n:
                        continue
                    if n not in name_to_id or id_spend[name_to_id[n]] < id_spend[sid]:
                        name_to_id[n] = sid

    # ---------- 第二遍：逐日聚合 ----------
    dates = []            # 日期标签 '10/13'
    day_maps = []         # [{key: {spend,conv,gq,imp,click}}]
    info = {}             # key -> 素材固定信息（含全部名称别名）
    alias_spend = defaultdict(lambda: defaultdict(float))  # key -> {名称: 累计消耗}
    for fp in files:
        mmdd = re.search(r'(\d{4})', fp.stem).group(1)
        label = f"{mmdd[:2]}/{mmdd[2:]}"
        dates.append(label)
        day_map = defaultdict(lambda: {'spend': 0.0, 'conv': 0.0, 'gq': 0.0, 'imp': 0.0, 'click': 0.0,
                                       # 播放质量加权分子（率×展示数）+ 时长加权分子（时长×展示数）
                                       'q_w3': 0.0, 'q_w5': 0.0, 'q_wf': 0.0, 'q_wd': 0.0})
        with open(fp, encoding='utf-8-sig') as fh:
            for r in csv.DictReader(fh):
                name = clean_name((r.get('视频名称') or '').strip())
                if not name:
                    continue
                sid = (r.get('素材id') or '').strip()
                account = (r.get('账户id') or '').strip() or (r.get('账户名称') or '').strip()
                # 渠道账户不进明细（会拉低深转率），跳过
                if account in CHANNEL_ACCOUNTS:
                    continue
                # 素材ID优先：同名多个ID/科学计数法通用名的行，有真实ID就按ID归（防错归）
                key = sid or name_to_id.get(name) or f"{name}|{account}"
                d = day_map[key]
                row_spend = fnum(r.get('消耗'))
                d['spend'] += row_spend
                d['conv'] += fnum(r.get('转化数'))
                d['gq'] += fnum(r.get('回访-高潜成交(计费时间)'))
                d['imp'] += fnum(r.get('展示数'))
                d['click'] += fnum(r.get('点击数'))
                # 播放质量：按展示数加权（3秒率/5秒率口径为÷展示；完播率/时长用展示近似）
                row_imp = fnum(r.get('展示数'))
                d['q_w3'] += fnum(r.get('3秒播放率')) * row_imp
                d['q_w5'] += fnum(r.get('5秒播放率')) * row_imp
                _wf_val = r.get('完播率(%)') if r.get('完播率(%)') not in (None, '') else r.get('完播率')
                d['q_wf'] += fnum(_wf_val) * row_imp
                d['q_wd'] += fnum(r.get('平均单次播放时长')) * row_imp
                alias_spend[key][name] += row_spend
                if key not in info:
                    mat_type = (r.get('素材类型') or '').strip()
                    is_tuwen = (mat_type == '图文') if mat_type else (len((r.get('视频链接') or '').strip()) < 10)
                    is_ai_ = is_ai(name)
                    person = ('AI' if is_ai_ else
                              '外部' if not has_known_person(name) else
                              extract_person(name))
                    info[key] = {
                        'id': sid, 'name': name, 'aliases': [name], 'person': person,
                        'type': 'Ai' if is_ai_ else ('图文' if is_tuwen else '视频'),
                        'tag': get_tag(name, sid, label_map),
                        'account': account,
                    }
                elif name not in info[key]['aliases']:
                    info[key]['aliases'].append(name)
        day_maps.append(dict(day_map))

    # 同一素材id多名称时：优先显示正常名（非纯数字/非科学计数法，消耗最大者）；
    # 没有正常名才用消耗最大的名称；其余保留为别名（供搜索）
    def _is_plain_name(n):
        return not (re.fullmatch(r'\d+', n) or re.fullmatch(r'[\d.]+[eE][+\-]?\d+', n))
    for key, m in info.items():
        cand = alias_spend.get(key)
        if cand:
            normal = {n: s for n, s in cand.items() if _is_plain_name(n)}
            main_name = max(normal, key=lambda n: normal[n]) if normal else max(cand, key=lambda n: cand[n])
            m['name'] = main_name
            m['aliases'] = [n for n in m['aliases'] if n != main_name]
            m['tag'] = get_tag(main_name, m['id'], label_map)

    print(f"加载 {len(files)} 天：{dates[0]} ~ {dates[-1]}，素材 {len(info)} 个")

    # ---------- 期次切分：固定 N 天一期，从最新日期往前回切 ----------
    periods = []
    p_end = len(dates)
    p_idx = 0
    while p_end > 0:
        p_start = max(0, p_end - period_len)
        periods.append({
            'idx': p_idx,
            'start': p_start,
            'end': p_end,
            'label': f"{dates[p_start]}~{dates[p_end - 1]}",
            'days': p_end - p_start,
            'is_latest': p_idx == 0,
        })
        p_idx += 1
        p_end = p_start
    print(f"期次切分：{len(periods)} 期，每期 {period_len} 天（最老一期 {periods[-1]['days']} 天）")

    # ---------- 每期 × 每素材聚合 ----------
    period_data = []  # [{key: {spend,conv,gq,imp,click,days_active,first,last,stopped_at_end,q3,q5,qf,qd}}]
    for p in periods:
        agg = defaultdict(lambda: {'spend': 0.0, 'conv': 0.0, 'gq': 0.0,
                                   'imp': 0.0, 'click': 0.0, 'active': set(),
                                   'q_w3': 0.0, 'q_w5': 0.0, 'q_wf': 0.0, 'q_wd': 0.0})
        for i in range(p['start'], p['end']):
            for k, x in day_maps[i].items():
                a = agg[k]
                a['spend'] += x['spend']; a['conv'] += x['conv']; a['gq'] += x['gq']
                a['imp'] += x['imp']; a['click'] += x['click']
                a['q_w3'] += x['q_w3']; a['q_w5'] += x['q_w5']
                a['q_wf'] += x['q_wf']; a['q_wd'] += x['q_wd']
                if x['spend'] > 0:
                    a['active'].add(i)
        out = {}
        for k, a in agg.items():
            active = sorted(a['active'])
            # 播放质量：加权平均（分母=展示数）；无展示则空
            out[k] = {
                'spend': round(a['spend'], 2), 'conv': int(a['conv']), 'gq': int(a['gq']),
                'imp': int(a['imp']), 'click': int(a['click']),
                'q3': round(a['q_w3']/a['imp'], 2) if a['imp'] else None,
                'q5': round(a['q_w5']/a['imp'], 2) if a['imp'] else None,
                'qf': round(a['q_wf']/a['imp'], 2) if a['imp'] else None,
                'qd': round(a['q_wd']/a['imp'], 2) if a['imp'] else None,
                'days_active': len(active),
                'first': dates[active[0]] if active else None,
                'last': dates[active[-1]] if active else None,
                'stopped_at_end': (p['end'] - 1 - active[-1]) if active else None,
            }
        period_data.append(out)

    # ---------- 每期 KPI ----------
    period_kpis = []
    for pi, p in enumerate(periods):
        cur = period_data[pi]
        prev = period_data[pi + 1] if pi + 1 < len(period_data) else None
        spend = sum(x['spend'] for x in cur.values())
        conv = sum(x['conv'] for x in cur.values())
        gq = sum(x['gq'] for x in cur.values())
        active = sum(1 for x in cur.values() if x['days_active'] > 0)
        new = sum(1 for k, x in cur.items()
                  if x['spend'] > 0 and (prev is None or prev.get(k, {}).get('spend', 0) <= 0))
        if prev is not None:
            pv_spend = round(sum(x['spend'] for x in prev.values()), 2)
            pv_conv = int(sum(x['conv'] for x in prev.values()))
            pv_gq = int(sum(x['gq'] for x in prev.values()))
            pv_active = sum(1 for x in prev.values() if x['days_active'] > 0)
        else:
            pv_spend = pv_conv = pv_gq = pv_active = None
        period_kpis.append({
            'spend': round(spend, 2), 'conv': int(conv), 'gq': int(gq),
            'active': active, 'mats': len(cur), 'new': new,
            'prev_spend': pv_spend, 'prev_conv': pv_conv,
            'prev_gq': pv_gq, 'prev_active': pv_active,
        })

    # ---------- 素材静态信息 + 生命周期累计 + 近30天轨迹 ----------
    rows = []
    last_idx = len(dates) - 1
    for key, m in info.items():
        life_spend = life_conv = life_gq = 0.0
        active = []
        for i, d in enumerate(day_maps):
            x = d.get(key)
            if not x:
                continue
            life_spend += x['spend']; life_conv += x['conv']; life_gq += x['gq']
            if x['spend'] > 0:
                active.append(i)
        if not active and life_spend <= 0:
            continue  # 从未有消耗的素材不进看板，避免噪音行
        # 全周期逐日轨迹（前端按选中期次切片显示当期）
        bars = []
        for i in range(len(dates)):
            x = day_maps[i].get(key)
            bars.append({
                'd': dates[i],
                'spend': round(x['spend'], 2) if x else 0.0,
                'conv': int(x['conv']) if x else 0,
                'gq': int(x['gq']) if x else 0,
                'clk': int(x['click']) if x else 0,
            })
        # 近8周周汇总（全周期视角）
        weeks = []
        wk_end = len(dates)
        while wk_end > 0 and len(weeks) < 8:
            wk_start = max(0, wk_end - 7)
            w_spend = w_conv = w_gq = w_clk = 0.0
            for d in day_maps[wk_start:wk_end]:
                x = d.get(key)
                if x:
                    w_spend += x['spend']; w_conv += x['conv']
                    w_gq += x['gq']; w_clk += x['click']
            weeks.append({'d': dates[wk_start], 'spend': round(w_spend, 2),
                          'conv': int(w_conv), 'gq': int(w_gq), 'clk': int(w_clk)})
            wk_end = wk_start
        weeks.reverse()

        rows.append({
            'key': key, 'id': m['id'], 'name': m['name'], 'aliases': m['aliases'],
            'person': m['person'],
            'type': m['type'], 'tag': m['tag'] or '—', 'account': m['account'],
            'life_spend': round(life_spend, 2), 'life_conv': int(life_conv),
            'life_gq': int(life_gq),
            'life_first': dates[active[0]] if active else '—',
            'life_last': dates[active[-1]] if active else '—',
            'life_days': len(active),
            'bars': bars, 'weeks': weeks,
        })
    rows.sort(key=lambda x: -x['life_spend'])

    payload = {
        'period_len': period_len,
        'all_range': f"{dates[0]}~{dates[-1]}",
        'n_total': len(rows),
        'periods': [{
            'idx': p['idx'], 'label': p['label'], 'days': p['days'],
            'is_latest': p['is_latest'], 'date_list': dates[p['start']:p['end']],
        } for p in periods],
        'period_data': period_data,
        'period_kpis': period_kpis,
    }

    html = HTML_TEMPLATE.format(
        rows_js=json.dumps(rows, ensure_ascii=False),
        cfg_js=json.dumps(payload, ensure_ascii=False),
    )

    OUT.mkdir(exist_ok=True)
    out_path = OUT / '素材周期表现.html'
    out_path.write_text(html, encoding='utf-8')
    k0 = period_kpis[0]
    print(f"最新一期（{periods[0]['label']}）：消耗 ¥{k0['spend']:,.0f} · "
          f"转化 {k0['conv']} · 高潜 {k0['gq']} · 活跃素材 {k0['active']}")
    print(f"报告已生成: {out_path} ({out_path.stat().st_size / 1e6:.1f} MB)")


HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>素材周期表现 · 引导加微</title>
<style>
*,*::before,*::after{{box-sizing:border-box;margin:0;padding:0}}
:root{{
  --bg:#F0F4FA;--card:#FFFFFF;--border:#DBEAFE;
  --primary:#1E40AF;--primary-light:#3B82F6;
  --accent:#D97706;--accent-bg:#FFFBEB;
  --text:#1E3A8A;--text-secondary:#64748B;--text-muted:#94A3B8;
  --success:#059669;--danger:#DC2626;
  --shadow:0 1px 3px rgba(0,0,0,.08);
  --radius:10px;
  font-family:system-ui,-apple-system,'PingFang SC','Microsoft YaHei',sans-serif;
}}
body{{background:var(--bg);color:var(--text);font-size:14px;line-height:1.5;min-height:100vh}}
.header{{background:linear-gradient(135deg,#1E3A8A 0%,#1E40AF 60%,#2563EB 100%);padding:18px 28px 16px;color:#fff}}
.header h1{{font-size:19px;font-weight:700}}
.header p{{color:rgba(255,255,255,.72);font-size:12px;margin-top:3px}}
.wrap{{max-width:1460px;margin:0 auto;padding:18px}}
.kpi-grid{{display:grid;grid-template-columns:repeat(5,1fr);gap:12px;margin-bottom:16px}}
.kpi{{background:var(--card);border:1px solid var(--border);border-radius:var(--radius);padding:12px 15px;box-shadow:var(--shadow)}}
.kpi .lbl{{font-size:11px;color:var(--text-secondary);font-weight:600}}
.kpi .val{{font-size:21px;font-weight:700;color:var(--primary);font-family:monospace;margin-top:2px}}
.kpi .sub{{font-size:11px;color:var(--text-muted);margin-top:2px}}
.card{{background:var(--card);border:1px solid var(--border);border-radius:var(--radius);padding:14px 16px;box-shadow:var(--shadow);margin-bottom:16px}}
.card h2{{font-size:15px;font-weight:700;color:var(--primary);margin-bottom:10px}}
.period-bar{{display:flex;gap:8px;flex-wrap:wrap;align-items:center;margin-bottom:12px;padding:10px 12px;background:#F8FAFC;border:1px solid var(--border);border-radius:8px}}
.period-bar .flabel{{font-size:11px;color:var(--text-secondary);font-weight:600;margin-right:2px}}
.pbtn{{padding:4px 12px;border-radius:14px;border:1.5px solid var(--border);background:var(--card);font-size:12px;font-weight:500;color:var(--text-secondary);cursor:pointer;transition:all .15s;white-space:nowrap}}
.pbtn:hover{{border-color:var(--primary-light);color:var(--primary)}}
.pbtn.active{{background:var(--primary);border-color:var(--primary);color:#fff}}
.period-hint{{font-size:11px;color:var(--text-muted);margin-left:auto}}
.filter-bar{{display:flex;flex-direction:column;gap:8px;margin-bottom:8px}}
.fgroup{{display:flex;gap:4px;flex-wrap:wrap;align-items:center}}
.flabel{{flex:0 0 40px;font-size:11px;color:var(--text-secondary);font-weight:600}}
.fbtn{{padding:4px 12px;border-radius:14px;border:1.5px solid var(--border);background:var(--card);font-size:12px;font-weight:500;color:var(--text-secondary);cursor:pointer;transition:all .15s;white-space:nowrap}}
.fbtn:hover{{border-color:var(--primary-light);color:var(--primary)}}
.fbtn.active{{background:var(--primary);border-color:var(--primary);color:#fff}}
.search-wrap{{display:flex;gap:6px;align-items:center}}
.search-wrap input{{padding:6px 12px;border-radius:8px;border:1.5px solid var(--border);font-size:13px;outline:none;width:300px}}
.search-wrap input:focus{{border-color:var(--primary-light)}}
.count-info{{font-size:12px;color:var(--text-secondary);margin-bottom:8px}}
table{{width:100%;border-collapse:collapse;font-size:12.5px}}
thead th{{position:sticky;top:0;background:#EFF6FF;color:var(--text);font-weight:600;padding:8px 10px;text-align:left;border-bottom:2px solid var(--border);white-space:nowrap;z-index:2}}
thead th.sortable{{cursor:pointer;user-select:none}}
thead th.sortable:hover{{color:var(--primary)}}
thead th.sorted-asc::after{{content:' ↑'}}
thead th.sorted-desc::after{{content:' ↓'}}
tbody td{{padding:7px 10px;border-bottom:1px solid #E8F0FE;vertical-align:middle}}
tbody tr{{cursor:pointer}}
tbody tr:hover{{background:#F5F9FF}}
tbody tr.row-active{{background:#EFF6FF}}
tbody tr.row-hit{{background:#FEF3C7}}
.num{{font-family:monospace;font-weight:600}}
.pos{{color:var(--success)}}.warn{{color:var(--accent)}}.zero{{color:var(--text-muted)}}
.badge{{display:inline-block;padding:1px 8px;border-radius:10px;font-size:11px;font-weight:500}}
.b-video{{background:#DBEAFE;color:#1D4ED8}}.b-tuwen{{background:#F3E8FF;color:#7C3AED}}.b-ai{{background:#EEF2FF;color:#6366F1}}
.st-active{{background:#ECFDF5;color:#059669}}
.st-recent{{background:#DBEAFE;color:#1D4ED8}}
.st-stopped{{background:#FEE2E2;color:#DC2626}}
.st-none{{background:#F1F5F9;color:#64748B}}
.trend-up{{color:var(--danger);font-weight:600}}
.trend-down{{color:var(--success);font-weight:600}}
.trend-new{{color:var(--primary);font-weight:600}}
.detail{{display:none;background:#F8FAFC;border-top:1px solid var(--border);padding:12px 16px}}
.detail.show{{display:table-row}}
.legend{{display:flex;gap:14px;font-size:11px;color:var(--text-secondary);margin:6px 0 4px;flex-wrap:wrap}}
.legend span{{display:inline-flex;align-items:center;gap:5px}}
.legend i{{display:inline-block;width:10px;height:10px;border-radius:2px}}
.bars{{display:flex;gap:2px;align-items:flex-end;height:72px;padding:6px 0}}
.bar{{flex:1;min-width:5px;border-radius:2px 2px 0 0;background:#E2E8F0;position:relative}}
.bar.has{{background:var(--primary-light)}}
.bar-dot{{position:absolute;top:-5px;left:50%;transform:translateX(-50%);width:8px;height:8px;border-radius:50%;background:var(--accent)}}
.bars-labels{{display:flex;justify-content:space-between;font-size:10px;color:var(--text-muted);margin-top:4px}}
.tip{{position:fixed;z-index:300;background:#1E3A8A;color:#fff;border-radius:8px;padding:8px 10px;font-size:11px;line-height:1.7;box-shadow:0 4px 12px rgba(0,0,0,.3);pointer-events:none;white-space:nowrap}}
.tip b{{color:#93C5FD}}
.tip .tg{{color:#FCD34D}}
.two-col{{display:grid;grid-template-columns:1fr 1fr;gap:20px;margin-top:10px}}
.traj-modes{{display:flex;gap:4px;margin-bottom:8px}}
.mbtn{{padding:2px 10px;border-radius:12px;border:1.5px solid var(--border);background:var(--card);font-size:11px;font-weight:500;color:var(--text-secondary);cursor:pointer;transition:all .15s}}
.mbtn:hover{{border-color:var(--primary-light);color:var(--primary)}}
.mbtn.active{{background:var(--primary);border-color:var(--primary);color:#fff}}
.traj-unit{{font-size:11px;color:var(--text-muted);margin-top:6px}}
.detail-stats{{display:flex;gap:18px;flex-wrap:wrap;font-size:12px;color:var(--text-secondary);margin-bottom:10px}}
.detail-stats b{{color:var(--text);font-family:monospace}}
@media(max-width:900px){{.kpi-grid{{grid-template-columns:repeat(2,1fr)}}.two-col{{grid-template-columns:1fr}}.search-wrap{{margin-left:0}}}}
</style>
</head>
<body>
<div class="header">
  <h1>素材周期表现 · 引导加微</h1>
  <p id="headerSub"></p>
  <a href="https://soso0122.github.io/daily-guide-report/" style="color:rgba(255,255,255,.9);font-size:12px;text-decoration:underline">← 返回日报</a>
</div>
<div class="wrap">
  <div class="kpi-grid" id="kpiGrid"></div>

  <div class="card">
    <h2>素材明细（点击行展开逐日/逐周轨迹）</h2>
    <div class="period-bar">
      <span class="flabel">期次</span>
      <span id="fPeriod"></span>
      <span class="period-hint" id="periodHint"></span>
    </div>
    <div class="filter-bar">
      <div class="search-wrap">
        <span class="flabel">搜索</span>
        <input type="search" id="search" placeholder="多关键词：空格/逗号分隔，命中任一即显示，回车定位">
      </div>
      <div class="fgroup"><span class="flabel">类型</span><span id="fType"></span></div>
      <div class="fgroup"><span class="flabel">标签</span><span id="fTag"></span></div>
      <div class="fgroup"><span class="flabel">状态</span><span id="fStatus"></span></div>
    </div>
    <div class="count-info" id="countInfo"></div>
    <div style="overflow-x:auto"><table id="mainTable">
      <thead><tr>
        <th>素材名称</th>
        <th>人</th><th>类型</th><th>标签</th>
        <th class="sortable" data-k="spend">周期消耗</th>
        <th class="sortable" data-k="conv">转化</th>
        <th class="sortable" data-k="gq">高潜</th>
        <th class="sortable" data-k="cpa">CPA</th>
        <th class="sortable" data-k="ctr">CTR</th>
        <th class="sortable" data-k="cvr">CVR</th>
        <th class="sortable" data-k="deep">深转率</th>
        <th class="sortable" data-k="q3" title="3秒播放率（展示加权）">3秒播放率</th>
        <th class="sortable" data-k="q5" title="5秒播放率（展示加权）">5秒播放率</th>
        <th class="sortable" data-k="qf" title="完播率（展示加权）">完播率</th>
        <th class="sortable" data-k="qd" title="平均单次播放时长·秒（展示加权）">播放时长</th>
        <th>首投</th><th>末投</th>
        <th class="sortable" data-k="days_active">在投天数</th>
        <th>环比上期</th><th>状态</th>
        <th class="sortable" data-k="life_spend">累计消耗</th>
        <th class="sortable" data-k="life_conv">累计转化</th>
        <th class="sortable" data-k="life_gq">累计高潜</th>
      </tr></thead>
      <tbody id="tbody"></tbody>
    </table></div>
  </div>
</div>
<div class="tip" id="tip" style="display:none"></div>
<script>
const ROWS = {rows_js};
const CFG = {cfg_js};
const PERIODS = CFG.periods;                 // 期次（idx 0 = 最新一期）
const PDATA = CFG.period_data;                // 每期 × 每素材
const KPI = CFG.period_kpis;

document.getElementById('headerSub').textContent =
  '数据范围 ' + CFG.all_range + ' · 期次固定 ' + CFG.period_len + ' 天一期' +
  ' · 口径：消耗>0=在投 · 深转率=高潜/转化 · 活跃素材=期内任一天消耗>0（去重）· 新起量=本期有消耗且上期无 · 环比=本期vs上一期（按消耗）· 主页素材已排除';

const esc = s => String(s == null ? '' : s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
const fmtM = v => '¥' + Number(v).toLocaleString('zh', {{minimumFractionDigits: 2, maximumFractionDigits: 2}});
const fmt0 = v => '¥' + Number(v).toLocaleString('zh', {{maximumFractionDigits: 0}});

const PERSONC = {{'小敏':'#3B82F6','嘉丽':'#8B5CF6','瑞晨':'#10B981','浩正':'#F59E0B','雅迪':'#EC4899','魏怡':'#EF4444','婷玉':'#14B8A6','AI':'#6366F1','外部':'#F97316','其他':'#94A3B8'}};
const PERSONBG = {{'小敏':'#EFF6FF','嘉丽':'#F5F3FF','瑞晨':'#ECFDF5','浩正':'#FFFBEB','雅迪':'#FDF2F8','魏怡':'#FEF2F2','婷玉':'#F0FDFA','AI':'#EEF2FF','外部':'#FFF7ED','其他':'#F8FAFC'}};
const TAG_BADGE = t => t === '图文' ? 'b-tuwen' : (t === 'Ai' ? 'b-ai' : 'b-video');
const STATUS_CLS = s => s === '在投' ? 'st-active' : (s === '近3天在投' ? 'st-recent' : (s === '本期未投' ? 'st-none' : 'st-stopped'));

const state = {{ periodIdx: 0, type: '全部', tag: '全部', status: '全部', kw: '', sortKey: 'spend', sortAsc: false }};

// ---------- 期次按钮 ----------
function renderPeriods() {{
  const box = document.getElementById('fPeriod');
  box.innerHTML = '';
  PERIODS.forEach(p => {{
    const b = document.createElement('button');
    b.className = 'pbtn' + (p.idx === state.periodIdx ? ' active' : '') + (p.is_latest ? ' latest' : '');
    b.textContent = p.label + (p.is_latest ? '（最新·近' + p.days + '天）' : '');
    b.title = p.is_latest ? '最新一期（最近 ' + p.days + ' 天）' : '第 ' + (PERIODS.length - p.idx) + ' 期 · ' + p.days + ' 天';
    b.onclick = () => {{ state.periodIdx = p.idx; renderPeriods(); renderKpi(); render(); }};
    box.appendChild(b);
  }});
  document.getElementById('periodHint').textContent =
    '当前：' + PERIODS[state.periodIdx].label + '（' + PERIODS[state.periodIdx].days + ' 天）· 环比上一期';
}}

// ---------- 当前期次数据 ----------
function curOf(r) {{ return PDATA[state.periodIdx][r.key] || null; }}
function prevOf(r) {{ return PDATA[state.periodIdx + 1] ? (PDATA[state.periodIdx + 1][r.key] || null) : null; }}

function calcDerived(x) {{
  if (!x) return {{ cpa: 0, ctr: 0, cvr: 0, deep: 0 }};
  return {{
    cpa: x.conv ? x.spend / x.conv : 0,
    ctr: x.imp ? x.click / x.imp * 100 : 0,
    cvr: x.click ? x.conv / x.click * 100 : 0,
    deep: x.conv ? x.gq / x.conv * 100 : 0,
  }};
}}

function statusOf(x) {{
  if (!x || x.days_active === 0) return '本期未投';
  if (x.stopped_at_end === 0) return '在投';
  if (x.stopped_at_end <= 3) return '近3天在投';
  return '已停' + x.stopped_at_end + '天';
}}

function trendOf(x, pv) {{
  const curSp = x ? x.spend : 0;
  const prevSp = pv ? pv.spend : 0;
  if (curSp > 0 && prevSp === 0) return {{ t: 'new', label: '新起量' }};
  if (prevSp === 0) return {{ t: 'none', label: '—' }};
  const pct = (curSp - prevSp) / prevSp * 100;
  if (Math.abs(pct) < 0.05) return {{ t: 'flat', label: '持平' }};
  return {{ t: pct > 0 ? 'up' : 'down', label: (pct > 0 ? '+' : '') + pct.toFixed(1) + '%' }};
}}

// ---------- KPI ----------
function renderKpi() {{
  const k = KPI[state.periodIdx];
  const avgCpa = k.conv ? k.spend / k.conv : 0;
  const deep = k.conv ? k.gq / k.conv * 100 : 0;
  const prevDeep = (k.prev_conv != null && k.prev_conv) ? k.prev_gq / k.prev_conv * 100 : null;
  // 环比增幅子行：上期值 + 变化百分比（涨红跌绿）
  const dSub = (cur, prev, fmtVal, unit) => {{
    if (prev == null) return '上期 —';
    const base = '上期 ' + fmtVal(prev) + unit;
    if (prev === 0) return cur > 0 ? base + ' · 新' : base + ' · 持平';
    const pct = (cur - prev) / prev * 100;
    if (Math.abs(pct) < 0.05) return base + ' · 持平';
    return base + ' · ' + (pct > 0 ? '+' : '') + pct.toFixed(1) + '%';
  }};
  const kpi = (lbl, val, sub) => '<div class="kpi"><div class="lbl">' + lbl + '</div><div class="val">' + val + '</div><div class="sub">' + sub + '</div></div>';
  document.getElementById('kpiGrid').innerHTML =
    kpi('本期总消耗', fmt0(k.spend), dSub(k.spend, k.prev_spend, v => fmt0(v), '')) +
    kpi('本期总转化', k.conv.toLocaleString(), '平均 CPA ' + fmt0(avgCpa) + ' · ' + dSub(k.conv, k.prev_conv, v => v.toLocaleString(), '')) +
    kpi('本期高潜成交', k.gq.toLocaleString(), dSub(k.gq, k.prev_gq, v => v.toLocaleString(), '')) +
    kpi('深转率', deep.toFixed(1) + '%', dSub(deep, prevDeep, v => v.toFixed(1), '%')) +
    kpi('活跃素材', k.active + ' / ' + k.mats, '新起量 ' + k.new + ' 个 · ' + dSub(k.active, k.prev_active, v => v.toLocaleString(), ''));
}}

// ---------- 筛选按钮 ----------
const TYPES = ['全部','视频','图文','Ai'];
const TAGS = ['全部','A1','A2','A3','A4'];
const STATUS = ['全部','在投','近3天在投','已停','本期未投'];
function makeButtons(container, list, key) {{
  container.innerHTML = '';
  list.forEach(v => {{
    const b = document.createElement('button');
    b.className = 'fbtn' + (state[key] === v ? ' active' : '');
    b.textContent = v;
    b.onclick = () => {{
      state[key] = v;
      container.querySelectorAll('.fbtn').forEach(x => x.classList.remove('active'));
      b.classList.add('active');
      render();
    }};
    container.appendChild(b);
  }});
}}
makeButtons(document.getElementById('fType'), TYPES, 'type');
makeButtons(document.getElementById('fTag'), TAGS, 'tag');
makeButtons(document.getElementById('fStatus'), STATUS, 'status');

// ---------- 匹配 ----------
function kwTerms() {{
  return state.kw.split(/[\\s,，、]+/).map(s => s.toLowerCase()).filter(Boolean);
}}
function kwMatch(r) {{
  const terms = kwTerms();
  if (!terms.length) return false;
  const blob = String(r.name).toLowerCase() + ' ' + String(r.id).toLowerCase() + ' '
    + (r.aliases || []).join(' ').toLowerCase();
  return terms.some(t => blob.includes(t));  // 多关键词 OR：命中任意一个即显示
}}
function matchRow(r, x) {{
  if (state.type !== '全部' && r.type !== state.type) return false;
  if (state.tag !== '全部' && (r.tag || '').split(',')[0] !== state.tag) return false;
  const st = statusOf(x);
  if (state.status === '在投' && st !== '在投') return false;
  if (state.status === '近3天在投' && st !== '近3天在投') return false;
  if (state.status === '已停' && !/^已停/.test(st)) return false;
  if (state.status === '本期未投' && st !== '本期未投') return false;
  if (state.kw && !kwMatch(r)) return false;
  return true;
}}

// ---------- 渲染 ----------
function sortRows(list) {{
  const k = state.sortKey;
  list.sort((a, b) => {{
    const va = a._v[k], vb = b._v[k];
    const na = typeof va === 'number' ? va : parseFloat(va), nb = typeof vb === 'number' ? vb : parseFloat(vb);
    const cmp = (isNaN(na) || isNaN(nb)) ? String(va).localeCompare(String(vb), 'zh') : na - nb;
    return state.sortAsc ? cmp : -cmp;
  }});
  return list;
}}

function render() {{
  // 候选：当前期次有记录，或搜索词命中（保证搜索永远能定位到素材）
  const items = [];
  ROWS.forEach(r => {{
    const x = curOf(r);
    if (x || (state.kw && kwMatch(r))) {{
      const d = calcDerived(x);
      items.push({{ r: r, x: x, _v: {{
        spend: x ? x.spend : 0, conv: x ? x.conv : 0, gq: x ? x.gq : 0,
        cpa: d.cpa, ctr: d.ctr, cvr: d.cvr, deep: d.deep,
        q3: x && x.q3 != null ? x.q3 : -1, q5: x && x.q5 != null ? x.q5 : -1,
        qf: x && x.qf != null ? x.qf : -1, qd: x && x.qd != null ? x.qd : -1,
        days_active: x ? x.days_active : 0,
        life_spend: r.life_spend, life_conv: r.life_conv, life_gq: r.life_gq,
      }} }});
    }}
  }});
  const shown = sortRows(items.filter(it => matchRow(it.r, it.x)));
  const terms = kwTerms();
  document.getElementById('countInfo').textContent =
    '期次 ' + PERIODS[state.periodIdx].label + ' · 显示 ' + shown.length + ' / ' + items.length +
    ' 个素材（周期消耗降序，可点列头排序）' +
    (terms.length > 1 ? ' · 命中关键词 ' + terms.length + ' 个（任一即显示）' : '');
  const body = document.getElementById('tbody');
  if (!shown.length) {{
    body.innerHTML = '<tr><td colspan="23" style="text-align:center;color:#94A3B8;padding:18px">没有匹配的素材</td></tr>';
    return;
  }}
  body.innerHTML = shown.map((it, i) => {{
    const r = it.r, x = it.x, v = it._v, d = calcDerived(x);
    const st = statusOf(x);
    const personBadge = '<span style="display:inline-block;padding:1px 8px;border-radius:10px;font-size:11px;font-weight:500;background:' + (PERSONBG[r.person] || '#F8FAFC') + ';color:' + (PERSONC[r.person] || '#64748B') + '">' + esc(r.person) + '</span>';
    const gqCls = v.gq > 0 ? 'warn' : 'zero';
    const convCls = v.conv > 0 ? 'pos' : 'zero';
    const spendCls = v.spend > 0 ? '' : 'zero';
    const tr = trendOf(x, prevOf(r));
    const trCls = tr.t === 'up' ? 'trend-up' : (tr.t === 'down' ? 'trend-down' : (tr.t === 'new' ? 'trend-new' : 'zero'));
    return '<tr class="row" data-i="' + i + '">'
      + '<td style="max-width:230px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="' + esc(r.name) + (r.aliases && r.aliases.length ? '\\n别名：' + r.aliases.join('、') : '') + '">' + esc(r.name) + '</td>'
      + '<td>' + personBadge + '</td>'
      + '<td><span class="badge ' + TAG_BADGE(r.type) + '">' + esc(r.type) + '</span></td>'
      + '<td>' + esc(r.tag) + '</td>'
      + '<td class="num ' + spendCls + '">' + fmtM(v.spend) + '</td>'
      + '<td class="num ' + convCls + '">' + v.conv + '</td>'
      + '<td class="num ' + gqCls + '">' + v.gq + '</td>'
      + '<td class="num">' + (v.conv ? '¥' + d.cpa.toFixed(0) : '—') + '</td>'
      + '<td class="num">' + d.ctr.toFixed(2) + '%</td>'
      + '<td class="num">' + d.cvr.toFixed(2) + '%</td>'
      + '<td class="num ' + (d.deep >= 15 ? 'warn' : '') + '">' + d.deep.toFixed(1) + '%</td>'
      + '<td class="num">' + (v.q3 >= 0 ? v.q3.toFixed(2) + '%' : '—') + '</td>'
      + '<td class="num">' + (v.q5 >= 0 ? v.q5.toFixed(2) + '%' : '—') + '</td>'
      + '<td class="num">' + (v.qf >= 0 ? v.qf.toFixed(2) + '%' : '—') + '</td>'
      + '<td class="num">' + (v.qd >= 0 ? v.qd.toFixed(1) + 's' : '—') + '</td>'
      + '<td>' + (x && x.first ? x.first : '—') + '</td>'
      + '<td>' + (x && x.last ? x.last : '—') + '</td>'
      + '<td class="num">' + v.days_active + '</td>'
      + '<td><span class="' + trCls + '">' + tr.label + '</span></td>'
      + '<td><span class="badge ' + STATUS_CLS(st) + '">' + esc(st) + '</span></td>'
      + '<td class="num">' + fmtM(r.life_spend) + '</td>'
      + '<td class="num">' + r.life_conv + '</td>'
      + '<td class="num">' + r.life_gq + '</td>'
      + '</tr>'
      + '<tr class="detail" id="det-' + i + '"><td colspan="23">' + detailHtml(r, x, d) + '</td></tr>';
  }}).join('');
  body.querySelectorAll('.row').forEach(tr => {{
    tr.onclick = () => {{
      const det = document.getElementById('det-' + tr.dataset.i);
      const wasOpen = det.classList.contains('show');
      body.querySelectorAll('.detail').forEach(xx => xx.classList.remove('show'));
      body.querySelectorAll('.row').forEach(xx => xx.classList.remove('row-active'));
      if (!wasOpen) {{ det.classList.add('show'); tr.classList.add('row-active'); }}
    }};
  }});
}}

// ---------- 展开面板（轨迹可切换 消耗/转化/高潜/深转率 维度） ----------
let TRAJ_MODE = 'spend';  // 全局轨迹维度：spend | conv | gq | deep（深转率=高潜/转化）
const MODE_LABEL = {{ spend: '消耗', conv: '转化', gq: '高潜', deep: '深转率' }};
const MODE_UNIT = {{ spend: '柱高按本素材日峰值等比', conv: '柱高按本素材日峰值等比', gq: '柱高按本素材日峰值等比', deep: '深转率 = 当日高潜/转化，柱高按 100% 等比' }};

function modeVal(b, mode) {{
  if (mode === 'deep') return b.conv > 0 ? (b.gq / b.conv) * 100 : 0;
  return b[mode] || 0;
}}
function modeBar(b, mode, maxVal) {{
  const v = modeVal(b, mode);
  const has = v > 0;
  const h = mode === 'deep' ? Math.max(6, Math.min(100, v)) : (has ? Math.max(10, Math.min(100, v / maxVal * 100)) : 4);
  return '<div class="bar ' + (has ? 'has' : '') + '" data-t="' + b.d + '|' + b.spend + '|' + b.conv + '|' + b.gq + '|' + b.clk + '" style="height:' + h + '%"></div>';
}}

function detailHtml(r, x, d) {{
  // 逐日图 = 选中期次内（固定期长，比如7天）
  const winDates = PERIODS[state.periodIdx].date_list;
  const dayBarsFull = r.bars.filter(b => winDates.includes(b.d));
  const dayMax = Math.max(1, ...dayBarsFull.map(b => modeVal(b, TRAJ_MODE)));
  const wkMax = Math.max(1, ...r.weeks.map(w => modeVal(w, TRAJ_MODE)));
  const trd = trendOf(x, prevOf(r));
  const trdCls = trd.t === 'up' ? 'trend-up' : (trd.t === 'down' ? 'trend-down' : (trd.t === 'new' ? 'trend-new' : 'zero'));
  const modeBtns = Object.keys(MODE_LABEL).map(k =>
    '<button class="mbtn' + (TRAJ_MODE === k ? ' active' : '') + '" data-m="' + k + '">' + MODE_LABEL[k] + '</button>').join('');
  const dayBars = dayBarsFull.map(b => {{
    const dot = b.gq > 0 ? '<span class="bar-dot"></span>' : '';
    return modeBar(b, TRAJ_MODE, dayMax).replace('</div>', dot + '</div>');
  }}).join('');
  const wkBars = r.weeks.map(w => {{
    const v = modeVal(w, TRAJ_MODE);
    const has = v > 0;
    const dot = w.gq > 0 ? '<span class="bar-dot"></span>' : '';
    const h = TRAJ_MODE === 'deep' ? Math.max(6, Math.min(100, v)) : (has ? Math.max(10, Math.min(100, v / wkMax * 100)) : 4);
    return '<div class="bar ' + (has ? 'has' : '') + '" data-t="' + w.d + '起7天|' + w.spend + '|' + w.conv + '|' + w.gq + '|' + w.clk + '" style="height:' + h + '%">' + dot + '</div>';
  }}).join('');
  const dLbls = dayBarsFull.length > 20
    ? '<span>' + dayBarsFull[0].d + '</span><span>' + dayBarsFull[Math.floor(dayBarsFull.length/2)].d + '</span><span>' + dayBarsFull[dayBarsFull.length-1].d + '</span>'
    : dayBarsFull.map(b => '<span>' + b.d.slice(3) + '</span>').join('');
  const wLbls = '<span>' + r.weeks[0].d + '</span><span>' + r.weeks[Math.floor(r.weeks.length/2)].d + '</span><span>' + r.weeks[r.weeks.length-1].d + '</span>';
  return '<div class="detail-stats">'
    + '<span>本期消耗 <b>' + fmt0(v_of(x, 'spend')) + '</b></span>'
    + '<span>环比上期 <b class="' + trdCls + '">' + trd.label + '</b></span>'
    + '<span>转化 <b>' + (x ? x.conv : 0) + '</b></span>'
    + '<span>高潜 <b>' + (x ? x.gq : 0) + '</b></span>'
    + '<span>CTR <b>' + d.ctr.toFixed(2) + '%</b></span>'
    + '<span>CVR <b>' + d.cvr.toFixed(2) + '%</b></span>'
    + '<span>深转率 <b>' + d.deep.toFixed(1) + '%</b></span>'
    + '<span>累计消耗 <b>' + fmt0(r.life_spend) + '</b></span>'
    + '<span>累计转化 <b>' + r.life_conv + '</b></span>'
    + '<span>累计高潜 <b>' + r.life_gq + '</b></span>'
    + '<span>全周期 ' + r.life_first + ' ~ ' + r.life_last + '（在投 ' + r.life_days + ' 天）</span>'
    + '</div>'
    + '<div class="traj-modes">维度：' + modeBtns + '</div>'
    + '<div class="two-col">'
    + '<div><div class="legend"><span><i style="background:#3B82F6"></i>' + MODE_LABEL[TRAJ_MODE] + '</span><span><i style="background:#D97706"></i>高潜日</span><span><i style="background:#E2E8F0"></i>未投</span></div>'
    +   '<div class="bars">' + dayBars + '</div><div class="bars-labels">' + dLbls + '</div>'
    +   '<div class="traj-unit">选中期次逐日（' + dayBarsFull.length + ' 天）· ' + MODE_UNIT[TRAJ_MODE] + '</div></div>'
    + '<div><div class="legend"><span><i style="background:#3B82F6"></i>周' + MODE_LABEL[TRAJ_MODE] + '</span><span><i style="background:#D97706"></i>高潜周</span></div>'
    +   '<div class="bars">' + wkBars + '</div><div class="bars-labels">' + wLbls + '</div>'
    +   '<div class="traj-unit">近8周全周期（周起日标签）· ' + MODE_UNIT[TRAJ_MODE] + '</div></div>'
    + '</div>';
}}

// 轨迹维度切换（事件委托：展开面板里点 mbtn）
document.getElementById('tbody').addEventListener('click', e => {{
  const btn = e.target.closest('.mbtn');
  if (!btn) return;
  TRAJ_MODE = btn.dataset.m;
  // 重新渲染当前展开的面板
  const open = document.querySelector('#tbody .detail.show');
  if (!open) return;
  const row = open.previousElementSibling;
  const i = row ? row.dataset.i : null;
  if (i == null) return;
  // 复用当前渲染数据：重新走一遍 render 再展开同一条
  render();
  const again = document.querySelectorAll('#tbody .row');
  let hit = null;
  again.forEach(tr => {{ if (tr.dataset.i === i) hit = tr; }});
  if (hit) {{
    const det = document.getElementById('det-' + i);
    det.classList.add('show');
    hit.classList.add('row-active');
  }}
}});

function v_of(x, k) {{ return x ? x[k] : 0; }}

// ---------- 排序 ----------
document.querySelectorAll('thead th.sortable').forEach(th => {{
  th.onclick = () => {{
    const k = th.dataset.k;
    if (state.sortKey === k) state.sortAsc = !state.sortAsc;
    else {{ state.sortKey = k; state.sortAsc = false; }}
    document.querySelectorAll('thead th.sortable').forEach(x => x.classList.remove('sorted-asc','sorted-desc'));
    th.classList.add(state.sortAsc ? 'sorted-asc' : 'sorted-desc');
    render();
  }};
}});

// ---------- 搜索 ----------
const searchInput = document.getElementById('search');
searchInput.addEventListener('input', e => {{ state.kw = e.target.value.trim(); render(); }});
searchInput.addEventListener('keydown', e => {{
  if (e.key === 'Enter') {{
    const first = document.querySelector('#tbody .row');
    if (first) {{
      first.scrollIntoView({{ block: 'center', behavior: 'smooth' }});
      first.classList.add('row-hit');
      setTimeout(() => first.classList.remove('row-hit'), 1200);
    }}
  }}
  if (e.key === 'Escape') {{ searchInput.value = ''; state.kw = ''; render(); }}
}});

// ---------- 悬停提示（消耗/转化/高潜/深转率 全显示） ----------
const tip = document.getElementById('tip');
document.addEventListener('mouseover', e => {{
  const bar = e.target.closest('.bar');
  if (!bar) {{ tip.style.display = 'none'; return; }}
  const [d, s, c, g, clk] = bar.dataset.t.split('|');
  const deep = Number(c) > 0 ? (Number(g) / Number(c) * 100).toFixed(1) : '—';
  tip.innerHTML = '<b>' + d + '</b>'
    + '<br>消耗 ' + fmt0(s)
    + '<br>转化 ' + c
    + '<br>高潜 <span class="tg">' + g + '</span>'
    + '<br>深转率 ' + deep + '%';
  tip.style.display = 'block';
}});
document.addEventListener('mousemove', e => {{
  if (tip.style.display !== 'block') return;
  // 先放鼠标右下，测量后越界则翻转到鼠标左上，保证始终完整可见
  let x = e.clientX + 14;
  let y = e.clientY + 14;
  tip.style.left = x + 'px';
  tip.style.top = y + 'px';
  const r = tip.getBoundingClientRect();
  const vw = window.innerWidth, vh = window.innerHeight;
  if (r.right > vw - 4) x = e.clientX - r.width - 14;
  if (r.bottom > vh - 4) y = e.clientY - r.height - 14;
  if (x < 4) x = 4;
  if (y < 4) y = 4;
  tip.style.left = x + 'px';
  tip.style.top = y + 'px';
}});

renderPeriods();
renderKpi();
render();</script>
</body>
</html>
"""


if __name__ == '__main__':
    main()
