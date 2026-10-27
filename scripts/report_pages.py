# -*- coding: utf-8 -*-
"""
日报页面拆分与「内容素材转化时效」模块。

由 generate_report_daily_guide.py 的 main() 调用：一个脚本一次生成全部页面，
口径函数复用 generate_report_daily_guide 里的实现（不重复定义，防口径漂移）。

生成：
  reports/引导素材每日分析_MMDD.html   总览（KPI/渠道/趋势/标签/类型卡）
  reports/卡审分析_MMDD.html          卡审分析（投放账户+测试账户）
  reports/跑出与时效_MMDD.html        近3周跑出 + 内容素材转化时效
  reports/编导明细_MMDD.html          编导表现 + 素材明细
（素材周期表现.html 由 material_period_report.py 生成，本模块不动）

所有页面顶部统一 sticky 顶栏：tab 导航 + 日期多选筛选；
选中日期写入 URL 参数 ?d=MM/DD,...，跨页同步。
时效子模块不随全局日期变化，使用自己的产出日期筛选。
"""
import csv
import json
import re
import datetime
import statistics
from pathlib import Path
from collections import defaultdict

CORE_EDITORS = ['小敏', '瑞晨', '嘉丽', '雅迪']  # 编导只统计4人（2026-10-23 用户定）
ALL_PERSONS = ['小敏', '嘉丽', '浩正', '雅迪', '婷玉', '魏怡', '瑞晨', '国星']

PAGES = [
    ('index', '总览', '引导素材每日分析_{mmdd}.html'),
    ('detail', '编导&素材明细', '编导&素材明细.html'),
    ('kajian', '卡审分析', '卡审分析.html'),
    ('pass3w', '近3周跑出', '近3周跑出.html'),
    ('timing', '内容素材转化时效', '内容素材转化时效.html'),
]

TOOLTIPS = {
    'conv_rate': '转化成交率 = 转化>0素材数 ÷ 产出投放素材数（按基础名去重）。转化口径阶段性目标不同（加粉/三次开口）。',
    'gq_conv_rate': '高潜成交率（转化） = 深转>0素材数 ÷ 转化>0素材数（按基础名去重）。',
    'gq_rate': '高潜成交率 = 深转>0素材数 ÷ 产出投放素材数（按基础名去重）。',
    'run_rate': '高潜跑出率 = 深转≥5单素材数 ÷ 产出投放素材数（按基础名去重）。',
    'conv_run_rate': '高潜跑出率（转化） = 深转≥5单素材数 ÷ 转化>0素材数（按基础名去重）。',
    'conv_days': '首转天数 = 首次有转化日期 − 产出日期（均值 / 中位数）。',
    'gq_days': '首高潜天数 = 首次有高潜日期 − 产出日期（均值 / 中位数）。',
    'gap_pc': '产出→首转 = 首次有转化日期 − 产出日期。',
    'gap_pe': '产出→起量 = 首次有效投放日期（单日消耗首次>¥25）− 产出日期。',
    'gap_ec': '起量→首转 = 首次有转化日期 − 首次有效投放日期（可能为负：有效投放前就出转化）。',
    'p25p75': '把素材按间隔天数从小到大排队：25%的素材 ≤ X天 = 有 1/4 素材在这个天数内完成；75%的素材 ≤ X天 = 只有 1/4 素材比这个更慢。',
    'eff_day': '首次有效投放日 = 单日消耗首次超过 ¥25 的那天。',
    'first_day': '首次投放日 = 该素材在投放数据中首次出现（有消耗）的日期。',
    'conv_day': '首次转化日 = 转化数>0 的第一天。',
    'gq_day': '首次高潜日 = 高潜成交>0 的第一天。',
    'pd': '产出日期 = 素材名称开头的 MMDD 日期前缀；名称无日期时取投放数据首次出现日。',
}


def _sf(v):
    try:
        return float(str(v).replace(',', '') or 0)
    except Exception:
        return 0.0


def _produce_day(name):
    name = (name or '').strip()
    m = re.match(r'^(\d{2})(\d{2})[-—－]', name)
    if not m and name.startswith('推送视频_'):
        m = re.match(r'^(\d{2})(\d{2})[-—－]', name[len('推送视频_'):])
    if not m:
        return ''
    mm, dd = int(m.group(1)), int(m.group(2))
    if not (1 <= mm <= 12 and 1 <= dd <= 31):
        return ''
    return f'{mm:02d}{dd:02d}'


def _base_name(name):
    n = re.sub(r'\.mp4$', '', (name or '').strip())
    n = re.sub(r'-(\d)改$', '', n)
    n = re.sub(r'-改$', '', n)
    return n


def _days_between(a, b):
    a, b = str(a or ''), str(b or '')
    if not (re.fullmatch(r'\d{4}', a) and re.fullmatch(r'\d{4}', b)):
        return None
    try:
        da = datetime.date(2026, int(a[:2]), int(a[2:]))
        db = datetime.date(2026, int(b[:2]), int(b[2:]))
    except ValueError:
        return None
    return (db - da).days


def _person_of(name):
    for p in CORE_EDITORS:
        if p in name:
            return p
    return '其他'


def _json_stats(vals):
    vals = [v for v in vals if v is not None]
    if not vals:
        return None
    vals.sort()
    n = len(vals)

    def q(p):
        idx = (n - 1) * p
        lo = int(idx)
        hi = min(lo + 1, n - 1)
        return vals[lo] + (vals[hi] - vals[lo]) * (idx - lo)

    return {
        'n': n,
        'mean': round(statistics.mean(vals), 1),
        'median': round(statistics.median(vals), 1),
        'p25': round(q(0.25), 1),
        'p75': round(q(0.75), 1),
    }


def _histogram(vals, bin_edges):
    counts = [0] * len(bin_edges)
    for v in vals:
        if v is None:
            continue
        placed = False
        for i in range(len(bin_edges) - 1):
            if bin_edges[i] <= v < bin_edges[i + 1]:
                counts[i] += 1
                placed = True
                break
        if not placed:
            counts[-1] += 1
    return counts


def _tag_of(sid, name):
    from generate_report_daily_guide import _LABEL_MAP
    tag = _LABEL_MAP.get(sid) or _LABEL_MAP.get(name)
    if not tag and name.startswith('推送视频_'):
        tag = _LABEL_MAP.get(name[len('推送视频_'):])
    if not tag:
        tags = re.findall(r'A[1-4]', name)
        tag = ','.join(sorted(set(tags)))
    return tag or ''


def build_timing_data():
    """⏱️ 内容素材转化时效：仅自投、有转化素材、按素材id聚合、全历史。"""
    from generate_report_daily_guide import CHANNEL_ACCOUNTS
    data_dir = Path(__file__).parent.parent / 'data'

    mats = {}
    daily_spend = defaultdict(dict)
    for fp in sorted(data_dir.glob('引导加微每日数据-*.csv')):
        mmdd = fp.stem[-4:]
        with open(fp, encoding='utf-8-sig', newline='') as f:
            for r in csv.DictReader(f):
                acc = (r.get('账户id') or '').strip().lstrip('\t')
                if acc in CHANNEL_ACCOUNTS:
                    continue
                sid = (r.get('素材id') or '').strip().lstrip('\t')
                if not sid:
                    continue
                name = (r.get('视频名称') or '').strip()
                if not name:
                    continue
                d = mats.setdefault(sid, {
                    'name': name, 'type': (r.get('素材类型') or '').strip(),
                    'pd': _produce_day(name), 'first': mmdd,
                    'conv': 0.0, 'gq': 0.0, 'spend': 0.0,
                    'conv_day': None, 'gq_day': None,
                    'imp': 0.0, 'click': 0.0,
                    'w3n': 0.0, 'w3w': 0.0, 'wfn': 0.0, 'wfw': 0.0,
                    'wdn': 0.0, 'wdw': 0.0,
                    'rejected': False,
                    'url': (r.get('视频链接') or '').strip(),
                })
                d['first'] = min(d['first'], mmdd)
                if '不通过' in (r.get('审核建议') or ''):
                    d['rejected'] = True
                if (r.get('视频链接') or '').strip():
                    d['url'] = (r.get('视频链接') or '').strip()
                spend = _sf(r.get('消耗'))
                conv = _sf(r.get('转化数'))
                gq = _sf(r.get('回访-高潜成交(计费时间)'))
                d['spend'] += spend
                d['conv'] += conv
                d['gq'] += gq
                d['imp'] += _sf(r.get('展示数'))
                d['click'] += _sf(r.get('点击数'))
                _imp = _sf(r.get('展示数'))
                _w3 = _sf(r.get('3秒播放率'))
                _wf = _sf(r.get('完播率(%)') if r.get('完播率(%)') not in (None, '') else r.get('完播率'))
                _wd = _sf(r.get('平均单次播放时长'))
                if _w3 > 0 and _imp > 0:
                    d['w3n'] += _w3 * _imp; d['w3w'] += _imp
                if _wf > 0 and _imp > 0:
                    d['wfn'] += _wf * _imp; d['wfw'] += _imp
                if _wd > 0 and _imp > 0:
                    d['wdn'] += _wd * _imp; d['wdw'] += _imp
                if conv > 0:
                    d['conv_day'] = min(d['conv_day'] or '9999', mmdd)
                if gq > 0:
                    d['gq_day'] = min(d['gq_day'] or '9999', mmdd)
                daily_spend[sid][mmdd] = daily_spend[sid].get(mmdd, 0.0) + spend

    for sid, byday in daily_spend.items():
        for mmdd in sorted(byday):
            if byday[mmdd] > 25:
                mats[sid]['eff_day'] = mmdd
                break
        else:
            mats[sid]['eff_day'] = ''

    # 池内判定：视频=推送池未卡审；图文=名称有日期前缀
    def _in_pool(d):
        # 图文=名称有日期前缀；视频=推送池且未卡审
        if d['type'] == '图文':
            return bool(_produce_day(d['name']))
        return d['name'].startswith('推送视频_') and not d.get('rejected', False)

    # 明细行：与转化成交率分母同集合（按 编导+基础名 去重，含无ID老数据，池内）
    # 数据源：open_rate_data（_ord 已有池判定字段），数值从 mats 聚合
    _ord_rows = build_open_rate_data()
    _ord_map = {(x['p'], x['b']): x for x in _ord_rows}
    _base_rows = {}
    for x in _ord_rows:
        p = x['p']; bn = x['b']
        # 池判定（与分母一致）
        if x['type'] == '图文':
            if not x.get('pd_prefix'):
                continue
        else:
            if not x.get('pushed') or x.get('rejected'):
                continue
        key = (p, bn)
        pd = x['pd'] or x['mn']
        # 数值从 mats 聚合：找该基础名的所有素材 id 合并
        base_ids = [sid for sid, d in mats.items()
                    if _person_of(d['name']) == p and _base_name(d['name']) == bn]
        agg = {'spend': 0.0, 'imp': 0.0, 'click': 0.0, 'conv': 0.0, 'gq': 0.0,
               'w3n': 0.0, 'w3w': 0.0, 'wfn': 0.0, 'wfw': 0.0, 'wdn': 0.0, 'wdw': 0.0,
               'first': '9999', 'conv_day': '', 'gq_day': '', 'eff_day': '',
               'name': bn, 'url': ''}
        for sid in base_ids:
            d = mats[sid]
            agg['spend'] += d['spend']; agg['imp'] += d['imp']; agg['click'] += d['click']
            agg['conv'] += d['conv']; agg['gq'] += d['gq']
            agg['w3n'] += d['w3n']; agg['w3w'] += d['w3w']; agg['wfn'] += d['wfn']
            agg['wfw'] += d['wfw']; agg['wdn'] += d['wdn']; agg['wdw'] += d['wdw']
            agg['first'] = min(agg['first'], d['first'])
            if d.get('conv_day'):
                agg['conv_day'] = min(agg['conv_day'] or '9999', d['conv_day'])
            if d.get('gq_day'):
                agg['gq_day'] = min(agg['gq_day'] or '9999', d['gq_day'])
            if d.get('eff_day'):
                agg['eff_day'] = min(agg['eff_day'] or '9999', d['eff_day'])
            if d.get('url'):
                agg['url'] = d['url']
            if d['name']:
                agg['name'] = d['name']
        _base_rows[key] = agg
    # 保存 基础名->首个真实素材id 映射（供明细 ID 列与链接）
    _base_first_id = {}
    for sid, d in mats.items():
        key = (_person_of(d['name']), _base_name(d['name']))
        if key not in _base_first_id:
            _base_first_id[key] = sid

    rows = []
    for (p, bn), d in _base_rows.items():
        _ox = _ord_map.get((p, bn), {})
        pd = _ox.get('pd') or _ox.get('mn') or d['first']
        rows.append({
            'id': _base_first_id.get((p, bn), bn), 'name': d['name'] or bn,
            'type': '图文' if _ox.get('type') == '图文' else '视频',
            'person': p,
            'tag': _tag_of('', d['name'] or bn),
            'pd': pd, 'first': d['first'],
            'eff': d['eff_day'],
            'conv_day': d['conv_day'], 'gq_day': d['gq_day'],
            'gap_pc': _days_between(pd, d['conv_day']),
            'gap_pe': _days_between(pd, d['eff_day']),
            'gap_ec': _days_between(d['eff_day'], d['conv_day']),
            'gap_gq': _days_between(pd, d['gq_day']),
            'spend': round(d['spend'], 2), 'conv': int(d['conv']), 'gq': int(d['gq']),
            'imp': int(d['imp']), 'click': int(d['click']),
            'ctr': round(d['click'] / d['imp'] * 100, 2) if d['imp'] else None,
            'cvr': round(d['conv'] / d['click'] * 100, 2) if d['click'] else None,
            'deep_rate': round(d['gq'] / d['conv'] * 100, 1) if d['conv'] else None,
            'w3': round(d['w3n'] / d['w3w'], 2) if d['w3w'] else None,
            'wf': round(d['wfn'] / d['wfw'], 2) if d['wfw'] else None,
            'wd': round(d['wdn'] / d['wdw'], 2) if d['wdw'] else None,
            'url': (d['url'].split('\n')[0].strip() if d['conv'] > 0 else ''),
        })
    rows.sort(key=lambda x: (x['conv_day'] or '0000'), reverse=True)

    # 编导指标（基础名去重；全历史固定口径）
    conv_groups = defaultdict(dict)
    for r in rows:
        p, bn = r['person'], _base_name(r['name'])
        g = conv_groups.setdefault((p, bn), {
            'pd': r['pd'], 'conv_day': '', 'gq_day': '',
        })
        g['conv_day'] = min(g['conv_day'] or '9999', r['conv_day'] or '9999')
        if r['gq_day']:
            g['gq_day'] = min(g['gq_day'] or '9999', r['gq_day'])

    all_groups = defaultdict(dict)
    for sid, d in mats.items():
        p, bn = _person_of(d['name']), _base_name(d['name'])
        g = all_groups.setdefault((p, bn), {'conv': False, 'gq': False})
        if d['conv'] > 0:
            g['conv'] = True
        if d['gq'] > 0:
            g['gq'] = True

    director = {}
    for p in CORE_EDITORS + ['其他']:
        own = {bn: g for (pp, bn), g in all_groups.items() if pp == p}
        total, conv_n, gq_n = len(own), 0, 0
        for g in own.values():
            conv_n += 1 if g['conv'] else 0
            gq_n += 1 if g['gq'] else 0
        cg = {bn: g for (pp, bn), g in conv_groups.items() if pp == p}
        conv_days = [_days_between(g['pd'], g['conv_day']) for g in cg.values() if g['conv_day']]
        gq_days = [_days_between(g['pd'], g['gq_day']) for g in cg.values() if g['gq_day']]
        # 三个间隔按素材行算（间隔②③需要有效投放日，仅对有有效投放的素材）
        prs = [r for r in rows if r['person'] == p]
        gap_pc = [r['gap_pc'] for r in prs if r['gap_pc'] is not None]
        gap_pe = [r['gap_pe'] for r in prs if r['gap_pe'] is not None]
        gap_ec = [r['gap_ec'] for r in prs if r['gap_ec'] is not None]
        director[p] = {
            'total': total, 'conv': conv_n, 'gq': gq_n,
            'open_rate': round(conv_n / total * 100, 1) if total else None,
            'order_rate': round(gq_n / conv_n * 100, 1) if conv_n else None,
            'conv_days': _json_stats(conv_days),
            'gq_days': _json_stats(gq_days),
            'gap_pe': _json_stats(gap_pe),
            'gap_ec': _json_stats(gap_ec),
        }

    def gap_vals(key):
        return [r[key] for r in rows if r[key] is not None]

    bins_pc = [0, 3, 7, 14, 21, 30, 45, 60, 90]
    bins_ec = [-15, -7, -1, 0, 3, 7, 14, 30, 60]
    summary = {
        'gap_pc': _json_stats(gap_vals('gap_pc')),
        'gap_pe': _json_stats(gap_vals('gap_pe')),
        'gap_ec': _json_stats(gap_vals('gap_ec')),
        'hist_pc': _histogram(gap_vals('gap_pc'), bins_pc),
        'hist_ec': _histogram(gap_vals('gap_ec'), bins_ec),
        'bins_pc': bins_pc, 'bins_ec': bins_ec,
    }

    # 编导卡按产出日期联动：per_pd[p][pd] = 该产出日该编导（有转化素材行）聚合
    # 分母 total：该产出日该编导的全部素材数（基础名去重，含无转化）——由 all_groups 里的 pd 推导
    # 先建 (person, base) -> pd 映射（无日期前缀的用首现日）
    base_pd = {}
    for (p, bn), g in all_groups.items():
        base_pd[(p, bn)] = g.get('pd', '')
    # 给 all_groups 补 pd
    for (p, bn), g in all_groups.items():
        if 'pd' not in g:
            # 从 mats 找该基础名的产出日
            g['pd'] = ''
    # 分母直接复用 build_open_rate_data()（与近3周/明细页同一数据源，绝对一致）
    _ord = build_open_rate_data()
    base_pd_all = {(x['p'], x['b']): (x['pd'] or x['mn']) for x in _ord}
    per_pd = defaultdict(dict)
    # 分母 + 分子都从 open_rate_data（_ord）来：与近3周/明细页完全一致
    # 时效页口径：产出日筛选决定分母，分子 = 历史上有过转化（用户 2026-10-26 确认）
    # 过审文件也计入「素材产出数量」（工作量口径）：按 (编导, 基础名) 去重，
    # 产出日 = 名称 MMDD 前缀（无前缀跳过）；转化成交率等指标分母不变（仍只走投放数据）
    audit_keys = {}
    for fp in sorted(data_dir.glob('*投放过审.csv')):
        with open(fp, encoding='utf-8-sig', newline='') as f:
            for r in csv.DictReader(f):
                name = (r.get('视频名称') or '').strip()
                if not name or '图文' in name:
                    continue
                pd = _produce_day(name)
                if not pd:
                    continue
                key = (_person_of(name), _base_name(name))
                if key not in audit_keys or pd < audit_keys[key]:
                    audit_keys[key] = pd

    for x in _ord:
        p = x['p']; pd = x['pd'] or x['mn']
        k = per_pd.setdefault(p, {})
        b = k.setdefault(pd, {'gaps': defaultdict(list), 'open_n': 0, 'order_n': 0, 'run_n': 0,
                              'total': 0, 'produce_n': 0, 'tuwen_n': 0, 'video_n': 0})
        # 素材产出数量：图文数 + 视频数（视频含未过审；0改/1改/2改/3改按基础名算1次）——全量
        if x['type'] == '图文':
            b['tuwen_n'] += 1
            b['produce_n'] += 1
        else:
            b['video_n'] += 1
            b['produce_n'] += 1
        # 指标池（与近3周页对齐）：视频=推送池未卡审；图文=名称有日期前缀
        in_pool = False
        if x['type'] == '图文':
            in_pool = bool(x.get('pd_prefix'))
        else:
            in_pool = bool(x.get('pushed')) and not x.get('rejected')
        if not in_pool:
            continue
        b['total'] += 1
        if x['cd']:
            b['open_n'] += 1
        if x['gd']:
            b['order_n'] += 1
        if (x['gq_total'] or 0) >= 5:
            b['run_n'] += 1
    # 过审文件里的素材（投放数据未出现的）也计入产出数量
    for (p, bn), pd in audit_keys.items():
        if (p, bn) in {(x['p'], x['b']) for x in _ord}:
            continue  # 已计入
        k = per_pd.setdefault(p, {})
        b = k.setdefault(pd, {'gaps': defaultdict(list), 'open_n': 0, 'order_n': 0, 'run_n': 0,
                              'total': 0, 'produce_n': 0, 'tuwen_n': 0, 'video_n': 0})
        b['video_n'] += 1
        b['produce_n'] += 1

    # 间隔：有转化素材行（rows，按素材 id）
    for r in rows:
        k = per_pd.setdefault(r['person'], {})
        b = k.setdefault(r['pd'], {'gaps': defaultdict(list), 'open_n': 0, 'order_n': 0, 'run_n': 0, 'total': 0})
        if r['gap_pc'] is not None:
            b['gaps']['gap_pc'].append(r['gap_pc'])
        if r['gap_pe'] is not None:
            b['gaps']['gap_pe'].append(r['gap_pe'])
        if r['gap_ec'] is not None:
            b['gaps']['gap_ec'].append(r['gap_ec'])
        if r['gap_gq'] is not None:
            b['gaps']['gq_gap'].append(r['gap_gq'])
    per_pd_out = {}
    for p, by_pd in per_pd.items():
        out = {}
        for pd, b in by_pd.items():
            out[pd] = {
                'gap_pc': sorted(b['gaps'].get('gap_pc', [])),
                'gap_pe': sorted(b['gaps'].get('gap_pe', [])),
                'gap_ec': sorted(b['gaps'].get('gap_ec', [])),
                'gq_gap': sorted(b['gaps'].get('gq_gap', [])),
                'open_n': b.get('open_n', 0), 'order_n': b.get('order_n', 0), 'total': b.get('total', 0),
                'run_n': b.get('run_n', 0), 'tuwen_n': b.get('tuwen_n', 0), 'video_n': b.get('video_n', 0),
                'produce_n': b.get('produce_n', 0),
            }
        per_pd_out[p] = out

    firsts = [d['first'] for d in mats.values()]
    all_pds = sorted({d['pd'] for d in mats.values() if d['pd']})
    # 在测且未转化素材（累计消耗>0 且 转化=0），用于测试消耗预警
    testing = sorted(
        [{'name': d['name'], 'person': _person_of(d['name']),
          'spend': round(d['spend'], 2), 'first': d['first'],
          'url': d['url'].split('\n')[0].strip()}
         for d in mats.values() if d['spend'] > 0 and d['conv'] <= 0],
        key=lambda x: -x['spend'])
    return {
        'rows': rows, 'director': director, 'summary': summary, 'n': len(rows),
        'range': [min(firsts) if firsts else '', max(firsts) if firsts else ''],
        'all_pds': all_pds, 'testing': testing, 'per_pd': per_pd_out,
    }


def build_open_rate_data():
    """五率数据（跟随日期筛选）：每 (编导, 基础名) 的 min/max 出现日 + 首个转化日。

    供近3周页与编导明细页的编导卡使用：选中日期窗口内，
    转化成交率 = 窗口内有转化的素材数 ÷ 窗口内出现的全部素材数（按基础名去重）。
    """
    from generate_report_daily_guide import CHANNEL_ACCOUNTS
    data_dir = Path(__file__).parent.parent / 'data'
    g = defaultdict(dict)   # (person, base) -> {mn, mx, cd, gd, gq_total, type}
    for fp in sorted(data_dir.glob('引导加微每日数据-*.csv')):
        mmdd = fp.stem[-4:]
        with open(fp, encoding='utf-8-sig', newline='') as f:
            for r in csv.DictReader(f):
                acc = (r.get('账户id') or '').strip().lstrip('\t')
                if acc in CHANNEL_ACCOUNTS:
                    continue
                name = (r.get('视频名称') or '').strip()
                if not name:
                    continue
                typ = (r.get('素材类型') or '').strip()
                key = (_person_of(name), _base_name(name))
                d = g.setdefault(key, {'mn': '9999', 'mx': '0000', 'cd': None, 'ld': None,
                                       'gd': None, 'lg': None, 'gq_total': 0.0, 'pd': '',
                                       'pd_prefix': False, 'type': '', 'pushed': False, 'rejected': False})
                d['mn'] = min(d['mn'], mmdd)
                d['mx'] = max(d['mx'], mmdd)
                if not d['type'] and typ:
                    d['type'] = typ
                # 产出日（用户 2026-10-26 定）：先取名称日期前缀；找不到再用推送日（首现日）兜底
                pdp = _produce_day(name)
                if pdp and not d['pd']:
                    d['pd'] = pdp
                    d['pd_prefix'] = True
                elif not d['pd']:
                    d['pd'] = mmdd
                if name.startswith('推送视频_'):
                    d['pushed'] = True
                if '不通过' in (r.get('审核建议') or ''):
                    d['rejected'] = True
                if _sf(r.get('转化数')) > 0:
                    d['cd'] = min(d['cd'] or '9999', mmdd)
                    d['ld'] = max(d['ld'] or '0000', mmdd)
                gq = _sf(r.get('回访-高潜成交(计费时间)'))
                if gq > 0:
                    d['gd'] = min(d['gd'] or '9999', mmdd)
                    d['lg'] = max(d['lg'] or '0000', mmdd)
                    d['gq_total'] += gq
    return [{'p': k[0], 'b': k[1], 'mn': v['mn'], 'mx': v['mx'], 'cd': v['cd'] or '',
             'ld': v['ld'] or '', 'gd': v['gd'] or '', 'lg': v['lg'] or '',
             'gq_total': round(v['gq_total'], 1),
             'pd': v['pd'] or v['mn'], 'pd_prefix': v['pd_prefix'],
             'type': v['type'], 'pushed': v['pushed'], 'rejected': v['rejected']}
            for k, v in g.items()]


# ---------------- 共享资源提取 ----------------

def _legacy_assets():
    """从旧模板提取共享 CSS 和 JS（运行时锚点切割，防行号漂移）。"""
    import generate_report_daily_guide as gdg
    t = gdg.HTML_TEMPLATE
    # 去掉 <style></style> 标签本身，只留 CSS 文本（避免嵌套 style 标签提前闭合）
    css = t[t.index('<style>') + len('<style>'):t.index('</style>')]
    i1 = t.index('<script>')
    i2 = t.index('let trendChart;')
    i3 = t.index('</script>\n</body>')
    inject = t[i1:i2]
    shared = t[i2:i3]
    return css, inject, shared


# ---------------- 顶栏与 DateBar ----------------

DATEBAR_JS = r"""
// ============ 顶部日期栏（所有页面共享）============
const DateBar = (function(){
  let dates = [];        // 全部日期 'MM/DD'
  let daySpend = {};     // 每天消耗
  let selected = [];     // 选中日期
  const dkey = l => l.replace('/','');
  function parseQuery(){
    const m = location.search.match(/[?&]d=([^&]*)/);
    if (!m) return [];
    return decodeURIComponent(m[1]).split(',').map(s=>s.trim()).filter(l => dates.includes(l));
  }
  // 面板保持打开：点击面板内部不触发 document 关闭监听
  document.addEventListener('click', function(e){
    const dd = document.getElementById('dateDropdown');
    if (!dd || dd.style.display === 'none') return;
    if (dd.contains(e.target)) return;
    const opener = document.querySelector('button[onclick^="DateBar.open"]');
    if (opener && opener.contains(e.target)) return;
    dd.style.display = 'none';
  });
  function persist(){
    // 更新所有 tab 链接的 ?d= 参数（跨页同步）
    const q = selected.length ? '?d=' + encodeURIComponent(selected.join(',')) : '';
    document.querySelectorAll('.nav a.tab').forEach(a => {
      a.href = a.getAttribute('data-base') + q;
    });
  }
  function renderChips(){
    const box = document.getElementById('dateChips');
    if (!box) return;
    box.innerHTML = [...selected].sort().reverse().map(d =>
      `<span class="date-chip">${d}<span style="cursor:pointer;margin-left:4px" onclick="DateBar.toggle('${d}')">✕</span></span>`).join('');
    document.querySelectorAll('.range-btn').forEach(b => {
      b.classList.toggle('active', b.dataset.key === deriveRange());
    });
  }
  function deriveRange(){
    const sel = new Set(selected);
    if (dates.every(d => sel.has(d))) return 'all';
    const months = [...new Set(dates.map(d => d.slice(0,2)))];
    return months.find(mm => {
      const md = dates.filter(d => d.startsWith(mm));
      return md.length > 0 && md.every(d => sel.has(d));
    }) || null;
  }
  function renderRanges(){
    const box = document.getElementById('rangeBtns');
    if (!box) return;
    const months = [...new Set(dates.map(d => d.slice(0,2)))];
    const ranges = [...months.map(mm => ({label: mm.replace(/^0/,'')+'月', key:mm})), {label:'全年', key:'all'}];
    box.innerHTML = ranges.map(r =>
      `<button class="range-btn" data-key="${r.key}" onclick="DateBar.setRange('${r.key}')">${r.label}</button>`).join('');
  }
  function renderDropdown(){
    const dd = document.getElementById('dateDropdown');
    if (!dd) return;
    // 面板保持打开：toggle 后不关面板，只更新勾选态；日期按顺序展示
    dd.innerHTML = [...dates].sort().reverse().map(d => {
      const sel = selected.includes(d);
      return `<div class="date-item${sel?' sel':''}" onclick="event.stopPropagation();DateBar.toggle('${d}')">
        <span>${sel?'✓ ':''}${d}</span>
        <span style="color:#94A3B8;font-size:11px">¥${(daySpend[d]||0).toFixed(0)}</span>
      </div>`;
    }).join('');
  }
  function notify(){
    renderChips(); renderDropdown();
    persist();
    try { sessionStorage.setItem('guideDateSel', JSON.stringify(selected)); } catch (e) {}
    if (window._onDates) window._onDates([...selected].sort());
  }
  return {
    init(allDates, spend, defaultDates){
      dates = allDates; daySpend = spend;
      selected = parseQuery();
      if (!selected.length) {
        try {
          const sv = sessionStorage.getItem('guideDateSel');
          if (sv) {
            const arr = JSON.parse(sv).filter(l => dates.includes(l));
            if (arr.length) selected = arr;
          }
        } catch (e) {}
      }
      if (!selected.length) selected = defaultDates && defaultDates.length ? defaultDates : [dates[dates.length-1]];
      document.querySelectorAll('.nav a.tab').forEach(a => a.setAttribute('data-base', a.href));
      renderRanges(); renderChips(); notify();
    },
    toggle(d){
      this.userTouched = true;
      if (selected.includes(d)) {
        if (selected.length === 1) return;
        selected = selected.filter(x => x !== d);
      } else selected = [...selected, d];
      notify();
    },
    setRange(key){
      this.userTouched = true;
      const cur = deriveRange();
      if (cur === key) { selected = [dates[dates.length-1]]; }
      else selected = key === 'all' ? [...dates] : dates.filter(d => d.startsWith(key));
      notify();
    },
    open(){
      const dd = document.getElementById('dateDropdown');
      if (!dd) return;
      const show = dd.style.display === 'none';
      dd.style.display = show ? 'block' : 'none';
      if (show) renderDropdown();
      if (!show) dd.style.display = 'none';
    },
    setDates(list, userTouched){
      const arr = (list || []).filter(l => dates.includes(l));
      if (arr.length) {
        selected = arr;
        if (userTouched) this.userTouched = true;
        notify();
      }
    },
    get touched(){ return !!this.userTouched; },
    get selected(){ return [...selected]; },
  };
})();

// ============ 编导/总览五率统一计算（基础名去重，分母含无消耗） ============
// 口径（2026-10-26 改名）：
//   转化成交率 = 转化>0素材数 ÷ 产出投放素材数
//   高潜成交率（转化） = 深转>0素材数 ÷ 转化>0素材数
//   高潜成交率 = 深转>0素材数 ÷ 产出投放素材数
//   高潜跑出率 = 深转≥5素材数 ÷ 产出投放素材数
//   高潜跑出率（转化） = 深转≥5素材数 ÷ 转化>0素材数
function _dateRange(dates){
  const keys = dates.map(d => d.replace('/',''));
  return {s: keys.reduce((a,b) => a < b ? a : b), e: keys.reduce((a,b) => a > b ? a : b)};
}
// 通用四率统计
//   p: 编导名 或 '__ALL__'
//   dates: 全局投放日期（近3周页=窗口；明细页=顶部选中日期）
//   pdRange: {mode:'window'|'set'|'all'} 产出日期筛选（近3周=window；明细页=produceDaySet；时效页按需）
//   pdSet: 产出日期集合（mode='set' 时生效）
//   type: 'all'|'video'|'tuwen'
function computeFourRates(p, dates, pdRange, pdSet, type, win, mode){
  // win: {s,e} 显式窗口（近3周页=最后选中日往前21天）；未传则用 dates 推导
  // mode: 'any'（默认，窗口内任意一天有转化/高潜）| 'first'（首次转化/高潜在窗口内）
  const dr = win || _dateRange(dates);
  const m = mode || 'any';
  let total=0, conv=0, gq=0, runout=0;
  (OPEN_RATE_DATA || []).forEach(x => {
    if (p !== '__ALL__' && x.p !== p) return;
    // 类型过滤（type 为空按视频处理）
    const isTw = x.type === '图文';
    if (type === 'video' && isTw) return;
    if (type === 'tuwen' && !isTw) return;
    // 产出日期过滤
    if (pdRange === 'window') {
      if (!(x.pd >= dr.s && x.pd <= dr.e)) return;
    } else if (pdRange === 'set') {
      if (pdSet && pdSet.size && !pdSet.has(x.pd)) return;
    }
    // 素材池过滤（与近3周页一致）：图文=名称日期前缀；视频=推送池未卡审
    if (isTw) {
      if (!x.pd_prefix) return;
    } else {
      if (!x.pushed || x.rejected) return;
    }
    // 分母：
    //  pdRange='window'（近3周页）：产出日期在窗口内的素材即入分母（含无消耗）
    //  pdRange='set'（明细页产出日期筛选）：还需在投放窗口内出现过
    if (pdRange !== 'window') {
      if (!(x.mn <= dr.e && x.mx >= dr.s)) return;
    }
    total++;
    if (m === 'first') {
      if (x.cd && x.cd >= dr.s && x.cd <= dr.e) conv++;
      if (x.gd && x.gd >= dr.s && x.gd <= dr.e) gq++;
    } else if (m === 'hist') {
      // 历史口径：只要有过转化/高潜（不限窗口）
      if (x.cd) conv++;
      if (x.gd) gq++;
    } else {
      // 窗口内任一转化/高潜：首日<=窗口末 且 末日>=窗口首
      if (x.cd && x.ld && x.cd <= dr.e && x.ld >= dr.s) conv++;
      if (x.gd && x.lg && x.gd <= dr.e && x.lg >= dr.s) gq++;
    }
    if ((x.gq_total || 0) >= 5) runout++;
  });
  const pct = (a,b) => b > 0 ? Math.round(a/b*1000)/10 : null;
  return {
    total, conv, gq, runout,
    open_rate: pct(conv, total),           // 转化成交率（内部键沿用旧名）
    order_rate: pct(gq, Math.max(conv, gq)),  // 高潜成交率（转化）
    chulv_rate: pct(gq, total),            // 高潜成交率
    run_rate: pct(runout, total),          // 高潜跑出率
    conv_run_rate: pct(runout, conv),      // 高潜跑出率（转化）
  };
}

// ---------- 问号 tooltip 跟随定位（旧模板恢复：按问号实际位置显示，不居中） ----------
document.addEventListener('mouseover', e => {
  const tip = e.target.closest && e.target.closest('.help-tip');
  if (!tip) return;
  const rect = tip.getBoundingClientRect();
  const text = tip.getAttribute('data-tip') || '';
  const tipW = Math.min(380, text.length * 12 + 20);
  let left = rect.left + rect.width/2 - tipW/2;
  left = Math.max(8, Math.min(left, window.innerWidth - tipW - 8));
  let top = rect.top - 8;
  if (top < 8) top = rect.bottom + 8;
  const style = document.createElement('style');
  style.id = 'helpTipPos';
  style.textContent = `.help-tip:hover::after{left:${left}px !important;top:${top}px !important;transform:none !important}`;
  const oldStyle = document.getElementById('helpTipPos');
  if (oldStyle) oldStyle.remove();
  document.head.appendChild(style);
}, true);

"""

TOPBAR_CSS = """
.topbar{position:sticky;top:0;z-index:1000;background:#FFFFFF;border-bottom:1.5px solid #DBEAFE;
  box-shadow:0 2px 6px rgba(0,0,0,.06);padding:8px 24px 10px}
.topbar-row1{display:flex;align-items:center;gap:16px;flex-wrap:wrap;margin-bottom:6px}
.brand{font-size:13px;font-weight:700;color:#1E40AF;white-space:nowrap}
.nav{display:flex;gap:6px;flex-wrap:wrap}
.tab{font-size:12px;padding:5px 12px;border-radius:8px;border:1px solid #DBEAFE;color:#64748B;
  text-decoration:none;background:#F8FAFC;font-weight:500}
.tab:hover{border-color:#3B82F6;color:#1E40AF}
.tab.active{background:#1E40AF;color:#fff;border-color:#1E40AF}
.topbar-row2{display:flex;align-items:center;gap:8px;flex-wrap:wrap;position:relative}
#dateDropdown{position:absolute;top:100%;left:0;z-index:1100;background:#fff;border:1.5px solid #DBEAFE;
  border-radius:10px;box-shadow:0 6px 16px rgba(0,0,0,.12);padding:10px;max-height:360px;overflow-y:auto;min-width:240px}
.date-item{display:flex;justify-content:space-between;gap:12px;padding:6px 10px;cursor:pointer;font-size:12px;border-radius:6px}
.date-item:hover{background:#EFF6FF}
.date-item.sel{background:#EFF6FF;font-weight:600;color:#1E40AF}
.date-chip{font-size:11px;padding:3px 9px;border-radius:12px;background:#EFF6FF;color:#1E40AF;border:1px solid #BFDBFE}
.range-btn{font-size:11px;padding:3px 9px;border-radius:12px;border:1px solid #DBEAFE;background:#fff;color:#64748B;cursor:pointer}
.range-btn.active{background:#1E40AF;color:#fff;border-color:#1E40AF}
/* 表头问号 tooltip：确保悬停时在列头之上显示 */
.table-wrap thead th .help-tip{position:relative;z-index:9991}
"""

LEGEND_CSS = """
.legend{background:#F8FAFC;border:1.5px solid #DBEAFE;border-radius:10px;padding:10px 14px;
  font-size:12px;color:#475569;line-height:1.8;margin-bottom:12px}
.legend b{color:#1E3A8A}
.t-filter-row{display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin-bottom:8px}
.t-filter-col{display:flex;flex-direction:column;gap:6px;margin-bottom:10px}
.t-filter-col .t-filter-row{margin-bottom:0}
"""


def _topbar_html(active, mmdd, hide_dates=False):
    """sticky 顶栏：tab 导航 + 日期栏（DateBar 渲染）。时效页的日期行换成产出日期筛选器。"""
    tabs = ''.join(
        f'<a class="tab{" active" if key == active else ""}" href="{"index.html" if key == "index" else name.format(mmdd=mmdd).replace("&", "&amp;")}">{label}</a>'
        for key, label, name in PAGES
    )
    if active == 'timing':
        row2 = '''  <div class="topbar-row2">
    <span class="filter-label">产出日期</span>
    <button class="sort-btn" onclick="clearTPd()">全部</button>
    <span id="timingPdChips" style="display:flex;gap:4px;flex-wrap:wrap"></span>
    <div style="position:relative;display:inline-block">
      <button class="sort-btn" onclick="TimingPd.open()">选择日期 ▾</button>
      <div id="timingPdPicker" style="display:none;position:absolute;top:100%;left:0;z-index:500;background:#fff;border:1.5px solid var(--border);border-radius:8px;box-shadow:var(--shadow-md);padding:10px;max-height:320px;overflow-y:auto;min-width:280px"></div>
    </div>
    <span style="font-size:11px;color:#94A3B8">⚠️ 此处按「产出日期」筛选时效素材，与总览页的「投放日期」筛选不同</span>
  </div>
'''
    elif hide_dates:
        row2 = ''
    else:
        row2 = f'''  <div class="topbar-row2">
    <button class="sort-btn" onclick="DateBar.open()">选择日期 ▾</button>
    <span style="font-size:12px;color:#64748B;font-weight:500">日期</span>
    <span id="rangeBtns" style="display:flex;gap:4px;flex-wrap:wrap"></span>
    <span id="dateChips" style="display:flex;gap:4px;flex-wrap:wrap"></span>
    <div id="dateDropdown" style="display:none"></div>
  </div>
'''
    return f'''<div class="topbar">
  <div class="topbar-row1">
    <span class="brand">引导素材日报 · {mmdd[:2]}/{mmdd[2:]}</span>
    <nav class="nav">{tabs}</nav>
  </div>
{row2}</div>'''


def _html_head(title, active, mmdd, css, hide_dates=False):
    return f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>
<style>{css}{TOPBAR_CSS}{LEGEND_CSS}</style>
</head>
<body>
{_topbar_html(active, mmdd, hide_dates)}
'''


def _html_tail(data_js, page_js, pre_js=''):
    return f'''<script>
{pre_js}
{data_js}
{DATEBAR_JS}
{page_js}
</script>
</body>
</html>'''


# ---------------- 旧 JS 函数切片（从旧模板提取，保持 {{}} 字面量） ----------------

def _js_slices():
    """返回关键 JS 函数文本（原样保留 {{}} 转义，拼接时不再 format）。"""
    import generate_report_daily_guide as gdg
    t = gdg.HTML_TEMPLATE
    out = {}

    def cut(start_anchor, end_anchor):
        i = t.index(start_anchor)
        j = t.index(end_anchor)
        return t[i:j]

    # 卡审分析块（含 fmtDate、openRejectVideo、REJ 全局）
    out['kajian'] = cut('// ---------- 卡审分析 & 近3周跑出 ----------',
                        'function passWindowForDates()')
    # 近3周跑出块
    out['pass'] = cut('function passWindowForDates()',
                      'function bindRejectSorts()')
    # bindRejectSorts ~ renderRejectModules 结束（卡审初始化 + 标签卡）
    out['rej_init'] = cut('function bindRejectSorts()',
                          'function initCharts(labels')
    # 表格排序 ~ 明细相关（filter/sort/renderTable/高潜成交率/弹窗/modal 在 HTML 侧）
    out['table'] = cut('// ---------- 表格排序 ----------',
                       '// ---------- 对比表 ----------')
    # updatePersonCards（编导卡）独立
    out['person_cards'] = cut('function updatePersonCards(rows, auditData)',
                              'function updateTypeCards(rows)')
    # mergeAuditData + mergedRows（多日合并）
    out['merge_audit'] = cut('function mergeAuditData(dates)',
                             'function initTabs()')
    out['merged_rows'] = cut('function mergedRows(dates)',
                             'function switchDays(dates)')
    # initTrendChart（趋势图）
    out['trend'] = cut('function initTrendChart()',
                       'function updateTagCards(rows)')
    # renderChannel
    out['channel'] = cut('function renderChannel(dates)',
                         'function renderPager(totalPages)')
    # openVideoByName（明细播放）+ closeModal + modal HTML
    out['open_video'] = cut('function openVideoByName(encodedName, encodedId)',
                            'function closeModal(e)')
    out['close_modal'] = cut('function closeModal(e)',
                             "document.addEventListener('keydown'")
    return out


# ---------------- 汇总页 JS（预聚合，不再背 52MB 明细） ----------------

OVERVIEW_JS = r"""
// ============ 总览页渲染 ============
let _curDateLabel = '';

function renderKpi(dates){
  let ts=0, ti=0, tc=0, tz=0, tg=0, n=0;
  dates.forEach(d => {
    const s = DAY_STATS[d]; if (!s) return;
    ts += s.spend; ti += s.imp; tc += s.click; tz += s.conv; tg += s.gq; n += s.materials;
  });
  const cpa = tz ? ts/tz : 0, ctr = ti ? tc/ti*100 : 0, cvr = tc ? tz/tc*100 : 0;
  document.getElementById('kpi-spend').textContent = '¥' + ts.toLocaleString('zh',{minimumFractionDigits:2,maximumFractionDigits:2});
  document.getElementById('kpi-count').textContent = n + ' 条素材';
  document.getElementById('kpi-imp').textContent = ti.toLocaleString('zh',{maximumFractionDigits:0});
  document.getElementById('kpi-ctr').textContent = ctr.toFixed(2) + '%';
  document.getElementById('kpi-cvr').textContent = cvr.toFixed(2) + '%';
  document.getElementById('kpi-conv').textContent = tz.toFixed(0);
  document.getElementById('kpi-cpa').textContent = '¥' + cpa.toFixed(2);
  document.getElementById('kpi-gaoquan').textContent = tg.toFixed(0);
  document.getElementById('kpi-deeprate').textContent = tz ? (tg/tz*100).toFixed(1)+'%' : '—';
  _curDateLabel = dates.length === 1 ? dates[0] : '';
  renderKpiDiffs(dates);
}

function renderKpiDiffs(dates){
  const dEls = ['spend','imp','ctr','cvr','conv','cpa','gaoquan','deeprate'];
  dEls.forEach(k => { const el = document.getElementById('kpi-'+k+'-diff'); if (el) { el.textContent=''; el.className='kpi-diff'; } });
  if (dates.length !== 1) return;
  const label = dates[0];
  const idx = ALL_DATES.indexOf(label);
  if (idx <= 0) return;
  const p = DAY_STATS[ALL_DATES[idx-1]];
  if (!p) return;
  const c = DAY_STATS[label];
  const fmtSign = (v, digits, prefix, suffix) => {
    if (v === 0) return { text: '±0', cls: '' };
    const sign = v > 0 ? '+' : '-';
    const abs = Math.abs(v).toFixed(digits);
    return { text: sign + prefix + abs + suffix, cls: v > 0 ? 'up' : 'down' };
  };
  const set = (key, build) => {
    const el = document.getElementById('kpi-'+key+'-diff');
    if (!el) return;
    const r = build(c, p);
    if (r) { el.textContent = r.text; if (r.cls) el.className = 'kpi-diff ' + r.cls; }
  };
  set('spend', (c,p) => fmtSign(c.spend - p.spend, 2, '¥', ''));
  set('imp',   (c,p) => fmtSign(c.imp - p.imp, 0, '', ''));
  set('ctr',   (c,p) => fmtSign((c.click/c.imp*100) - (p.click/p.imp*100), 2, '', '%'));
  set('cvr',   (c,p) => fmtSign((c.conv/c.click*100) - (p.conv/p.click*100), 2, '', '%'));
  set('conv',  (c,p) => fmtSign(c.conv - p.conv, 0, '', ''));
  set('cpa',   (c,p) => fmtSign((c.spend/c.conv) - (p.spend/p.conv), 2, '¥', ''));
  set('gaoquan', (c,p) => fmtSign(c.gq - p.gq, 0, '', ''));
  set('deeprate', (c,p) => fmtSign((c.gq/c.conv*100) - (p.gq/p.conv*100), 1, '', '%'));
}

function renderTagCards(dates){
  const container = document.getElementById('tagCardsRow');
  if (!container) return;
  const TAG_FULL = {'A1':'A1 技巧','A2':'A2 经历','A3':'A3 结果','A4':'A4 情绪'};
  const ORDER = ['A1','A2','A3','A4'];
  const COLORS = {'A1':'#3B82F6','A2':'#8B5CF6','A3':'#10B981','A4':'#F59E0B'};
  const stats = {};
  ORDER.forEach(t => stats[t] = {spend:0,conv:0,gq:0,click:0,imp:0});
  dates.forEach(d => {
    const s = TAG_STATS_BY_DAY[d]; if (!s) return;
    ORDER.forEach(t => { const x = s[t]; if (!x) return;
      stats[t].spend += x.spend; stats[t].conv += x.conv; stats[t].gq += x.gq;
      stats[t].click += x.click; stats[t].imp += x.imp; });
  });
  container.innerHTML = ORDER.map(t => {
    const s = stats[t], color = COLORS[t];
    const cpa = s.conv > 0 ? (s.spend/s.conv).toFixed(2) : '—';
    const deepRate = s.conv > 0 ? (s.gq/s.conv*100).toFixed(1)+'%' : '—';
    const ctr = s.imp > 0 ? (s.click/s.imp*100).toFixed(2)+'%' : '—';
    const cvr = s.click > 0 ? (s.conv/s.click*100).toFixed(2)+'%' : '—';
    const hasData = s.spend > 0;
    return `<div style="background:#fff;border:1.5px solid ${color}33;border-radius:10px;padding:14px 16px;box-shadow:0 1px 3px rgba(0,0,0,.06);">
      <div style="display:flex;align-items:center;gap:6px;margin-bottom:10px">
        <span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:${color}"></span>
        <span style="font-size:13px;font-weight:700;color:${color}">${TAG_FULL[t]}</span>
      </div>
      ${hasData ? `
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:6px">
        <div style="background:#F8FAFC;border-radius:6px;padding:8px 10px">
          <div style="font-size:10px;color:#94A3B8;margin-bottom:2px">消耗</div>
          <div style="font-size:15px;font-weight:700;color:#1E40AF;font-family:monospace">¥${s.spend.toLocaleString('zh',{maximumFractionDigits:0})}</div>
        </div>
        <div style="background:#F8FAFC;border-radius:6px;padding:8px 10px">
          <div style="font-size:10px;color:#94A3B8;margin-bottom:2px">转化数</div>
          <div style="font-size:15px;font-weight:700;color:#059669;font-family:monospace">${s.conv}</div>
        </div>
        <div style="background:#F8FAFC;border-radius:6px;padding:8px 10px">
          <div style="font-size:10px;color:#94A3B8;margin-bottom:2px">点击率</div>
          <div style="font-size:15px;font-weight:700;color:#3B82F6;font-family:monospace">${ctr}</div>
          <div style="font-size:10px;color:#94A3B8;margin-top:2px">点击 ${s.click.toLocaleString('zh',{maximumFractionDigits:0})}</div>
        </div>
        <div style="background:#F8FAFC;border-radius:6px;padding:8px 10px">
          <div style="font-size:10px;color:#94A3B8;margin-bottom:2px">转化率</div>
          <div style="font-size:15px;font-weight:700;color:#8B5CF6;font-family:monospace">${cvr}</div>
          <div style="font-size:10px;color:#94A3B8;margin-top:2px">转化 ${s.conv} / 点击 ${s.click.toLocaleString('zh',{maximumFractionDigits:0})}</div>
        </div>
        <div style="background:#F8FAFC;border-radius:6px;padding:8px 10px">
          <div style="font-size:10px;color:#94A3B8;margin-bottom:2px">高潜成交</div>
          <div style="font-size:15px;font-weight:700;color:#D97706;font-family:monospace">${s.gq}</div>
        </div>
        <div style="background:#F8FAFC;border-radius:6px;padding:8px 10px">
          <div style="font-size:10px;color:#94A3B8;margin-bottom:2px">CPA</div>
          <div style="font-size:15px;font-weight:700;color:#64748B;font-family:monospace">¥${cpa}</div>
        </div>
        <div style="background:#FFFBEB;border-radius:6px;padding:8px 10px;grid-column:span 2">
          <div style="font-size:10px;color:#94A3B8;margin-bottom:2px">深转率（高潜/转化）</div>
          <div style="font-size:15px;font-weight:700;color:#D97706;font-family:monospace">${deepRate}</div>
        </div>
      </div>` : `<div style="color:#94A3B8;font-size:12px;text-align:center;padding:20px 0">暂无数据</div>`}
    </div>`;
  }).join('');
}

function renderTypeCards(dates){
  const container = document.getElementById('typeCardsRow');
  if (!container) return;
  let totSpend=0, totConv=0, totGq=0;
  const agg = { video:{spend:0,conv:0,gq:0,click:0,imp:0,n:0}, tuwen:{spend:0,conv:0,gq:0,click:0,imp:0,n:0}, ai:{spend:0,conv:0,gq:0,click:0,imp:0,n:0} };
  dates.forEach(d => {
    const s = TYPE_STATS_BY_DAY[d]; if (!s) return;
    ['video','tuwen','ai'].forEach(k => { const x = s[k]; if (!x) return;
      agg[k].spend += x.spend; agg[k].conv += x.conv; agg[k].gq += x.gq;
      agg[k].click += x.click; agg[k].imp += x.imp; agg[k].n += x.n; });
  });
  Object.values(agg).forEach(a => { totSpend += a.spend; totConv += a.conv; totGq += a.gq; });
  const types = [
    { key:'video', label:'视频', color:'#3B82F6' },
    { key:'tuwen', label:'图文', color:'#8B5CF6' },
    { key:'ai',    label:'Ai',   color:'#6366F1' },
  ];
  container.innerHTML = types.map(t => {
    const s = agg[t.key], color = t.color;
    const cpa = s.conv > 0 ? (s.spend/s.conv).toFixed(2) : '—';
    const deepRate = s.conv > 0 ? (s.gq/s.conv*100).toFixed(1)+'%' : '—';
    const ctr = s.imp > 0 ? (s.click/s.imp*100).toFixed(2)+'%' : '—';
    const cvr = s.click > 0 ? (s.conv/s.click*100).toFixed(2)+'%' : '—';
    const spendPct = totSpend > 0 ? (s.spend/totSpend*100).toFixed(1) : '0';
    const convPct = totConv > 0 ? (s.conv/totConv*100).toFixed(1) : '0';
    const gqPct = totGq > 0 ? (s.gq/totGq*100).toFixed(1) : '0';
    return `<div style="background:#fff;border:1.5px solid ${color}33;border-radius:10px;padding:14px 16px;box-shadow:0 1px 3px rgba(0,0,0,.06)">
      <div style="display:flex;align-items:center;gap:6px;margin-bottom:10px">
        <span style="width:8px;height:8px;border-radius:50%;background:${color};display:inline-block"></span>
        <span style="font-size:13px;font-weight:700;color:${color}">${t.label}</span>
        <span style="font-size:11px;color:#94A3B8;margin-left:auto">${s.n} 条素材${t.key==='ai' ? '（已含于视频/图文）' : ''}</span>
      </div>
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:6px">
        <div style="background:#F8FAFC;border-radius:6px;padding:8px 10px">
          <div style="font-size:10px;color:#94A3B8;margin-bottom:2px">消耗</div>
          <div style="font-size:15px;font-weight:700;color:#1E40AF;font-family:monospace">¥${s.spend.toLocaleString('zh',{minimumFractionDigits:2,maximumFractionDigits:2})}</div>
          <div style="font-size:10px;color:${color};margin-top:2px">占比 ${spendPct}%</div>
        </div>
        <div style="background:#F8FAFC;border-radius:6px;padding:8px 10px">
          <div style="font-size:10px;color:#94A3B8;margin-bottom:2px">转化数</div>
          <div style="font-size:15px;font-weight:700;color:#059669;font-family:monospace">${s.conv}</div>
          <div style="font-size:10px;color:${color};margin-top:2px">占比 ${convPct}%</div>
        </div>
        <div style="background:#F8FAFC;border-radius:6px;padding:8px 10px">
          <div style="font-size:10px;color:#94A3B8;margin-bottom:2px">点击率</div>
          <div style="font-size:15px;font-weight:700;color:#3B82F6;font-family:monospace">${ctr}</div>
          <div style="font-size:10px;color:${color};margin-top:2px">点击 ${s.click.toLocaleString('zh',{maximumFractionDigits:0})}</div>
        </div>
        <div style="background:#F8FAFC;border-radius:6px;padding:8px 10px">
          <div style="font-size:10px;color:#94A3B8;margin-bottom:2px">转化率</div>
          <div style="font-size:15px;font-weight:700;color:#8B5CF6;font-family:monospace">${cvr}</div>
          <div style="font-size:10px;color:${color};margin-top:2px">转化 ${s.conv} / 点击 ${s.click.toLocaleString('zh',{maximumFractionDigits:0})}</div>
        </div>
        <div style="background:#F8FAFC;border-radius:6px;padding:8px 10px">
          <div style="font-size:10px;color:#94A3B8;margin-bottom:2px">高潜成交</div>
          <div style="font-size:15px;font-weight:700;color:#D97706;font-family:monospace">${s.gq}</div>
          <div style="font-size:10px;color:${color};margin-top:2px">占比 ${gqPct}%</div>
        </div>
        <div style="background:#F8FAFC;border-radius:6px;padding:8px 10px">
          <div style="font-size:10px;color:#94A3B8;margin-bottom:2px">CPA</div>
          <div style="font-size:15px;font-weight:700;color:#64748B;font-family:monospace">¥${cpa}</div>
        </div>
        <div style="background:#FFFBEB;border-radius:6px;padding:8px 10px;grid-column:span 2">
          <div style="font-size:10px;color:#94A3B8;margin-bottom:2px">深转率（高潜/转化）</div>
          <div style="font-size:15px;font-weight:700;color:#D97706;font-family:monospace">${deepRate}</div>
        </div>
      </div>
    </div>`;
  }).join('');
}

// 总览页日期联动
window._onDates = function(dates){
  renderKpi(dates);
  renderChannel(dates);
  renderTagCards(dates);
  renderTypeCards(dates);
};
"""

# ---------------- 明细页 JS（编导表现 + 素材明细） ----------------

DETAIL_JS = r"""
// ============ 编导明细页 ============
// 全部编导总卡：personStats 聚合 + 四率（由 updatePersonCards 里的补丁调用）
function renderAllDirectorCard(){
  const _el = document.getElementById('personAllCard');
  if (!_el) return;
  const _all4 = computeFourRates('__ALL__', _selDates4, 'set', produceDaySet, _personType, null, 'any');
  let vS=0, tS=0, cV=0, cK=0, iM=0, gQ=0;
  _personRows.forEach(r => {
    if (r.spend === 0 || r.is_ai) return;
    const isTw = r.is_tuwen;
    if (isTw) tS += r.spend; else vS += r.spend;
    if (_personType === 'all' || (_personType === 'video' && !isTw) || (_personType === 'tuwen' && isTw)) {
      cV += r.conversions; cK += r.clicks; iM += r.impressions; gQ += r.gaoquan;
    }
  });
  const totS = _personType === 'video' ? vS : _personType === 'tuwen' ? tS : vS + tS;
  const cpa = cV > 0 ? '¥' + (totS/cV).toFixed(2) : '—';
  const ctr = iM > 0 ? (cK/iM*100).toFixed(2)+'%' : '—';
  const cvr = cK > 0 ? (cV/cK*100).toFixed(2)+'%' : '—';
  const deep = cV > 0 ? (gQ/cV*100).toFixed(1)+'%' : '—';
  const cells = [
    ['视频消耗', '¥' + vS.toFixed(2), '', '#1E40AF'],
    ['图文消耗', '¥' + tS.toFixed(2), '', '#8B5CF6'],
    ['转化数', String(cV), '', '#059669'],
    ['点击率', ctr, '', '#3B82F6'],
    ['转化率', cvr, '', '#8B5CF6'],
    ['高潜成交', String(gQ), '', '#D97706'],
    ['CPA', cpa, '', '#64748B'],
    ['深转率', deep, '', '#D97706'],
    ['转化成交率', _all4.open_rate != null ? _all4.open_rate+'%' : '—', _all4.conv+'/'+_all4.total+' 条', '#1E40AF'],
    ['高潜成交率（转化）', _all4.order_rate != null ? _all4.order_rate+'%' : '—', _all4.gq+'/'+Math.max(_all4.gq,_all4.conv)+' 条', '#8B5CF6'],
    ['高潜成交率', _all4.chulv_rate != null ? _all4.chulv_rate+'%' : '—', _all4.gq+'/'+_all4.total+' 条', '#D97706'],
    ['高潜跑出率', _all4.run_rate != null ? _all4.run_rate+'%' : '—', _all4.runout+'/'+_all4.total+' 条', '#D97706'],
    ['高潜跑出率（转化）', _all4.conv_run_rate != null ? _all4.conv_run_rate+'%' : '—', _all4.runout+'/'+_all4.conv+' 条', '#9A3412']
  ];
  const cellHtml = cells.map(c =>
    '<div style="background:#F8FAFC;border-radius:6px;padding:6px 8px;text-align:center"><div style="font-size:10px;color:#94A3B8">' + c[0] + '</div><div style="font-size:13px;font-weight:700;font-family:monospace;color:' + c[3] + '">' + c[1] + '</div>' + (c[2] ? '<div style="font-size:9px;color:#64748B">' + c[2] + '</div>' : '') + '</div>'
  ).join('');
  _el.innerHTML = '<div style="background:#fff;border:1.5px solid #1E40AF44;border-radius:10px;padding:12px 14px;box-shadow:0 1px 3px rgba(0,0,0,.06)">' +
    '<div style="display:flex;align-items:center;gap:6px;margin-bottom:8px"><span style="width:8px;height:8px;border-radius:50%;background:#1E40AF;display:inline-block"></span><span style="font-size:13px;font-weight:700;color:#1E40AF">全部编导</span></div>' +
    '<div style="display:grid;grid-template-columns:repeat(4,1fr);gap:6px">' + cellHtml + '</div></div>';
}
// 排序/筛选/分页状态变量由旧 table 块声明（currentFilter/currentType/currentTag/
// currentVersion/currentAccountFilter/sortCol/sortAsc/pageNum/PAGE_SIZE/produceDaySet/pdPickerMonth），
// 此处只声明编导卡状态（旧 person_cards 块未含此段声明）
let _personType = 'all';
let _personRows = [];
let _personAudit = null;

function fmtDate(mmdd) {
  if (!mmdd) return '<span style="color:var(--text-muted)">—</span>';
  return mmdd.slice(0,2) + '/' + mmdd.slice(2);
}

window.setPersonType = function(type, btn){
  _personType = type;
  document.querySelectorAll('#personTypeAll,#personTypeVideo,#personTypeTuwen').forEach(b => { b.classList.remove('active'); b.style.background=''; });
  btn.classList.add('active');
  updatePersonCards(_personRows, _personAudit);
};

function renderDetail(rows){
  window.currentRows = rows;
  const persons = [...new Set(rows.map(r => r.person))];
  const pc = document.getElementById('personFilters');
  if (pc) {
    pc.innerHTML = '';
    persons.forEach(p => {
      const btn = document.createElement('button');
      btn.className = 'filter-btn'; btn.dataset.person = p; btn.textContent = p;
      btn.style.color = PERSON_COLORS[p] || '#64748B';
      btn.onclick = function(){ filterBy(p, this); };
      pc.appendChild(btn);
    });
  }
  document.querySelectorAll('.filter-btn[data-person]').forEach(b => {
    b.classList.remove('active'); b.style.background='';
    if (b.dataset.person !== 'all') b.style.color = PERSON_COLORS[b.dataset.person] || '#64748B';
    else b.style.color = 'var(--text-secondary)';
  });
  const allBtn = document.querySelector('.filter-btn[data-person="all"]');
  if (allBtn) { allBtn.classList.add('active'); allBtn.style.background='var(--primary)'; allBtn.style.color='#fff'; }
  currentFilter = 'all';
  const accounts = [...new Set(rows.flatMap(r => (r.account || '').split(' / ')).filter(Boolean))];
  const ac = document.getElementById('accountFilters');
  if (ac) {
    ac.innerHTML = '';
    accounts.forEach(a => {
      const btn = document.createElement('button');
      btn.className = 'filter-btn'; btn.dataset.account = a;
      btn.textContent = a.replace('高中-猿起武汉-','').replace('【agent测试】','').replace('【agent智擎】','').replace('高中-渠道-','渠道-');
      btn.title = a;
      btn.onclick = function(){ filterAccount(a, this); };
      ac.appendChild(btn);
    });
  }
  document.querySelectorAll('.filter-btn[data-account]').forEach(b => {
    b.classList.remove('active'); b.style.background=''; b.style.color='var(--text-secondary)';
  });
  const allAcc = document.querySelector('.filter-btn[data-account="all"]');
  if (allAcc) { allAcc.classList.add('active'); allAcc.style.background='var(--primary)'; allAcc.style.color='#fff'; }
  currentAccountFilter = 'all';
  renderProduceDayFilters();
  pageNum = 1;
  renderTable();
}

function updatePersonOrderRates(sortedRows){
  const container = document.getElementById('personOrderRates');
  if (!container) return;
  const CORE = ['小敏','瑞晨','嘉丽','雅迪'];
  const _selDates4 = (window.DateBar && DateBar.selected && DateBar.selected.length) ? DateBar.selected : [ALL_DATES[ALL_DATES.length-1]];
  const colors = PERSON_COLORS;
  container.innerHTML = CORE.map(p => {
    // 与编导卡同源：computeFourRates（基础名去重、含无消耗、跟随当前类型/产出日筛选）
    const f = computeFourRates(p, _selDates4, 'set', produceDaySet, _personType, null, 'any');
    if (!f || !f.total) return '';
    const rate = f.open_rate != null ? f.open_rate.toFixed(0)+'%' : '—';
    const tipText = '有转化素材 ' + f.conv + ' 条 / 总素材 ' + f.total + ' 条（基础名去重，含无消耗）';
    return `<span class="order-rate-badge" data-tip="${tipText}" style="display:inline-flex;align-items:center;gap:4px;background:${colors[p]||'#F8FAFC'}18;border:1px solid ${colors[p]}44;border-radius:14px;padding:3px 10px;font-size:11px;font-weight:600;color:${colors[p]}">
      ${p} 转化成交率 ${rate}<span style="opacity:.6;font-weight:400">（${f.conv}/${f.total}）</span>
    </span>`;
  }).filter(Boolean).join('') || '<span style="font-size:11px;color:var(--text-muted)">该筛选下无编导数据</span>';
}

// 明细页日期联动：多日合并 + 编导卡 + 明细表
window._onDates = function(dates){
  const rows = mergedRows(dates);
  renderDetail(rows);
  updatePersonCards(rows, mergeAuditData(dates));
};
// 产出日期筛选单向联动：更新顶部日期 + 重算编导卡（frOf 用 produceDaySet）
window._switchDays = function(dates){
  if (window.DateBar && DateBar.setDates) DateBar.setDates(dates);
  window._onDates(dates);
};
"""

# ---------------- 时效页 JS（内容素材转化时效） ----------------

TIMING_JS = r"""
// ============ 内容素材转化时效 ============
let T = {timing_js};
let tFilterType = 'all';
let tFilterPerson = 'all';
let tFilterTag = 'all';
let tPdSet = new Set();   // 产出日期筛选
let tSortCol = 'conv_day';
let tSortAsc = false;
let tView = 'detail';     // detail | month

function fmtD(mmdd){
  if (!mmdd) return '<span style="color:var(--text-muted)">—</span>';
  return mmdd.slice(0,2) + '/' + mmdd.slice(2);
}
function fmtGap(v){
  if (v === null || v === undefined) return '<span style="color:var(--text-muted)">—</span>';
  const cls = v < 0 ? 'style="color:#DC2626;font-weight:700"' : 'style="color:#059669"';
  return `<span ${cls}>${v}</span>`;
}

function tStats(key){
  const vals = T.rows.filter(r => tFiltered(r)).map(r => r[key]).filter(v => v !== null && v !== undefined);
  if (!vals.length) return null;
  vals.sort((a,b)=>a-b);
  const n = vals.length;
  const q = p => { const idx=(n-1)*p; const lo=Math.floor(idx); const hi=Math.min(lo+1,n-1); return Math.round((vals[lo]+(vals[hi]-vals[lo])*(idx-lo))*10)/10; };
  const mean = vals.reduce((s,v)=>s+v,0)/n;
  return {n, mean:Math.round(mean*10)/10, median:q(0.5), p25:q(0.25), p75:q(0.75)};
}

function tFiltered(r){
  if (tFilterType !== 'all' && r.type !== tFilterType) return false;
  if (tFilterPerson !== 'all' && r.person !== tFilterPerson) return false;
  if (tFilterTag !== 'all') {
    if (tFilterTag === 'none' && r.tag) return false;
    if (tFilterTag !== 'none' && !(r.tag && r.tag.split(',').some(x => x.split('-')[0].trim() === tFilterTag))) return false;
  }
  if (tPdSet.size && !tPdSet.has(r.pd)) return false;
  return true;
}

function renderTimingSummary(){
  const el = document.getElementById('timingSummary');
  if (!el) return;
  const cards = [
    {key:'gap_pc', label:'产出→首转', tip:'{tooltip_gap_pc}'},
    {key:'gap_pe', label:'产出→起量', tip:'{tooltip_gap_pe}'},
    {key:'gap_ec', label:'起量→首转', tip:'{tooltip_gap_ec}'},
  ];
  el.innerHTML = cards.map(c => {
    const s = tStats(c.key);
    const body = s
      ? `<div style="display:grid;grid-template-columns:repeat(4,1fr);gap:6px;margin-top:8px">
          <div style="background:#F8FAFC;border-radius:6px;padding:6px 8px;text-align:center\"><div style="font-size:10px;color:#94A3B8">均值</div><div style="font-size:16px;font-weight:700;color:#1E40AF;font-family:monospace">${s.mean}</div></div>
          <div style="background:#F8FAFC;border-radius:6px;padding:6px 8px;text-align:center\"><div style="font-size:10px;color:#94A3B8">中位</div><div style="font-size:16px;font-weight:700;color:#1E40AF;font-family:monospace">${s.median}</div></div>
          <div style="background:#F8FAFC;border-radius:6px;padding:6px 8px;text-align:center\"><div style="font-size:10px;color:#94A3B8">25%的素材 ≤ X天 <span class="help-tip" data-tip="{tooltip_p25p75}"></span></div><div style="font-size:16px;font-weight:700;color:#64748B;font-family:monospace">${s.p25}</div></div>
          <div style="background:#F8FAFC;border-radius:6px;padding:6px 8px;text-align:center\"><div style="font-size:10px;color:#94A3B8">75%的素材 ≤ X天 <span class="help-tip" data-tip="{tooltip_p25p75}"></span></div><div style="font-size:16px;font-weight:700;color:#64748B;font-family:monospace">${s.p75}</div></div>
        </div>`
      : '<div style="color:#94A3B8;font-size:12px;padding:12px 0">暂无数据</div>';
    return `<div style="background:#fff;border:1.5px solid #DBEAFE;border-radius:10px;padding:14px 16px">
      <div style="display:flex;align-items:center;gap:6px">
        <span style="font-size:12px;font-weight:700;color:#1E3A8A">${c.label}</span>
        <span class="help-tip" data-tip="${c.tip}"></span>
      </div>${body}
      <div style="font-size:10px;color:#94A3B8;margin-top:6px">样本 ${s ? s.n : 0} 条</div>
    </div>`;
  }).join('');
}

function renderTimingHist(){
  const el = document.getElementById('timingHist');
  if (!el) return;
  const mk = (title, key, bins, tipText, note) => {
    const vals = T.rows.filter(r => tFiltered(r)).map(r => r[key]).filter(v => v !== null && v !== undefined);
    const counts = [];
    for (let i = 0; i < bins.length; i++) {
      const lo = bins[i], hi = bins[i+1];
      counts.push(i === bins.length-1
        ? vals.filter(v => v >= lo).length
        : vals.filter(v => v >= lo && v < hi).length);
    }
    const max = Math.max(1, ...counts);
    const total = vals.length || 1;
    const rangeLabel = (i) => {
      if (i === bins.length-1) return '\u2265' + bins[i] + ' \u5929';
      const lo = bins[i], hi = bins[i+1];
      return lo + '\u2013' + hi + ' \u5929';
    };
    const rows = counts.map((c, i) => {
      const pct = (c / total * 100).toFixed(1);
      const isNeg = bins[i] < 0 && (bins[i+1] === undefined || bins[i+1] < 0);
      const barColor = isNeg ? '#F87171' : '#3B82F6';
      return `<div style="display:grid;grid-template-columns:110px 1fr 130px;align-items:center;gap:10px;margin-bottom:7px">
        <span style="font-size:11px;color:#64748B;text-align:right;white-space:nowrap">${rangeLabel(i)}</span>
        <div style="background:#F1F5F9;border-radius:6px;height:20px;overflow:hidden;position:relative">
          <div style="height:100%;width:${Math.max(1.5, c/max*100)}%;background:${barColor};border-radius:6px;transition:width .2s"></div>
        </div>
        <span style="font-size:11px;color:#1E3A8A;white-space:nowrap"><b>${c}</b> \u6761 \u00b7 ${pct}%</span>
      </div>`;
    }).join('');
    return `<div style="margin-top:16px;padding:14px 16px;border:1px solid #E2E8F0;border-radius:10px;background:#fff">
      <div style="font-size:12px;font-weight:700;color:#1E3A8A;margin-bottom:10px">${title} <span class="help-tip" data-tip="${tipText}"></span></div>
      ${rows}
      <div style="margin-top:10px;padding-top:8px;border-top:1px dashed #E2E8F0;font-size:11px;color:#64748B;line-height:1.7">${note}</div>
    </div>`;
  };
  // 解读跟随当前筛选实时计算
  const statsFor = (key) => {
    const v = T.rows.filter(r => tFiltered(r)).map(r => r[key]).filter(x => x !== null && x !== undefined);
    if (!v.length) return null;
    v.sort((a,b)=>a-b);
    const n = v.length;
    const qq = pp => { const idx=(n-1)*pp; const lo=Math.floor(idx); const hi=Math.min(lo+1,n-1); return v[lo]+(v[hi]-v[lo])*(idx-lo); };
    return {n, mean: Math.round(v.reduce((a,b)=>a+b,0)/n*10)/10, median: Math.round(qq(.5)*10)/10,
            p25: Math.round(qq(.25)*10)/10, p75: Math.round(qq(.75)*10)/10};
  };
  const pcS = statsFor('gap_pc'), ecS = statsFor('gap_ec');
  const note1 = pcS
    ? `\u89e3\u8bfb\uff1a\u5171 ${pcS.n} \u6761\u7d20\u6750\u3002\u4e00\u534a\u5728 <b>${pcS.median} \u5929</b>\u5185\u9996\u8f6c\uff1b<b>${pcS.p25} \u5929</b>\u5185\u5b8c\u6210 25%\uff1b<b>${pcS.p75} \u5929</b>\u5185\u5b8c\u6210 75%\uff1b\u5e73\u5747 <b>${pcS.mean} \u5929</b>\u3002`
    : '\u89e3\u8bfb\uff1a\u6682\u65e0\u6570\u636e';
  const note2 = ecS
    ? `\u89e3\u8bfb\uff1a\u5171 ${ecS.n} \u6761\u7d20\u6750\u3002\u4e00\u534a\u5728 <b>${ecS.median} \u5929</b>\u5185\uff1b<b>${ecS.p25} \u5929</b>\u5185\u5b8c\u6210 25%\uff1b<b>${ecS.p75} \u5929</b>\u5185\u5b8c\u6210 75%\uff1b\u5e73\u5747 <b>${ecS.mean} \u5929</b>\u3002<span style="color:#DC2626">\u7ea2\u8272 = \u8d1f\u503c</span>\uff0c\u8868\u793a\u6709\u6548\u6295\u653e\uff08\u5355\u65e5\u6d88\u8017>\u00a525\uff09\u4e4b\u524d\u5c31\u51fa\u4e86\u8f6c\u5316\u3002`
    : '\u89e3\u8bfb\uff1a\u6682\u65e0\u6570\u636e';
  el.innerHTML = '<div style="display:grid;grid-template-columns:1fr 1fr;gap:20px">' +
    mk('\u4ea7\u51fa\u2192\u9996\u8f6c \u5206\u5e03\uff08\u5929\uff09', 'gap_pc', T.summary.bins_pc, '{tooltip_gap_pc}', note1) +
    mk('\u8d77\u91cf\u2192\u9996\u8f6c \u5206\u5e03\uff08\u5929\uff0c\u53ef\u4e3a\u8d1f\uff09', 'gap_ec', T.summary.bins_ec, '{tooltip_gap_ec}', note2) +
    '</div>';
}

function renderTimingDirector(){
  const el = document.getElementById('timingDirector');
  if (!el) return;
  // 全部编导总览卡（按当前产出日期筛选聚合）
  const _allEl = document.getElementById('timingAllCard');
  if (_allEl) {
    const _allA = aggFor('__ALL__');
    const _c4 = (label, val, frac, color) => '<div style="background:#F8FAFC;border-radius:6px;padding:7px 9px;text-align:center"><div style="font-size:10px;color:#94A3B8">' + label + '</div><div style="font-size:14px;font-weight:700;color:' + color + ';font-family:monospace">' + val + '</div><div style="font-size:10px;color:#64748B">' + frac + ' \u6761</div></div>';
    _allEl.innerHTML = '<div style="background:#fff;border:1.5px solid #1E40AF44;border-radius:10px;padding:12px 14px;box-shadow:0 1px 3px rgba(0,0,0,.06)\">' +
      '<div style="display:flex;align-items:center;gap:6px;margin-bottom:8px\"><span style="width:8px;height:8px;border-radius:50%;background:#1E40AF;display:inline-block"></span><span style="font-size:13px;font-weight:700;color:#1E40AF\">\u5168\u90e8\u7f16\u5bfc</span></div>' +
      '<div style="display:grid;grid-template-columns:repeat(4,1fr);gap:6px\">' +
      _c4('\u7d20\u6750\u4ea7\u51fa', String(_allA.produce_n), '\u56fe\u6587' + _allA.tuwen_n + ' / \u89c6\u9891' + _allA.video_n, '#1E40AF') +
      _c4('\u8f6c\u5316\u6210\u4ea4\u7387', _allA.open_rate != null ? _allA.open_rate+'%' : '\u2014', _allA.open_n + '/' + _allA.total, '#1E40AF') +
      _c4('\u9ad8\u6f5c\u6210\u4ea4\u7387\uff08\u8f6c\u5316\uff09', _allA.order_rate != null ? _allA.order_rate+'%' : '\u2014', _allA.order_n + '/' + _allA.open_n, '#8B5CF6') +
      _c4('\u9ad8\u6f5c\u6210\u4ea4\u7387', _allA.total ? (Math.round(_allA.order_n/_allA.total*1000)/10)+'%' : '\u2014', _allA.order_n + '/' + _allA.total, '#D97706') +
      _c4('\u9ad8\u6f5c\u8dd1\u51fa\u7387', _allA.run_rate != null ? _allA.run_rate+'%' : '\u2014', _allA.runout + '/' + _allA.total, '#D97706') +
      _c4('\u9ad8\u6f5c\u8dd1\u51fa\u7387\uff08\u8f6c\u5316\uff09', _allA.conv_run_rate != null ? _allA.conv_run_rate+'%' : '\u2014', _allA.runout + '/' + _allA.open_n, '#9A3412') +
      _c4('\u4ea7\u51fa\u2192\u9996\u8f6c', _allA.gap_pc ? _allA.gap_pc.mean + '<span style="opacity:.55;font-size:10px"> / ' + _allA.gap_pc.median + '</span>' : '\u2014', '\u5747 / \u4e2d', '#D97706') +
      _c4('\u4ea7\u51fa\u2192\u8d77\u91cf', _allA.gap_pe ? _allA.gap_pe.mean + '<span style="opacity:.55;font-size:10px"> / ' + _allA.gap_pe.median + '</span>' : '\u2014', '\u5747 / \u4e2d', '#D97706') +
      _c4('\u8d77\u91cf\u2192\u9996\u8f6c', _allA.gap_ec ? _allA.gap_ec.mean + '<span style="opacity:.55;font-size:10px"> / ' + _allA.gap_ec.median + '</span>' : '\u2014', '\u5747 / \u4e2d', '#D97706') +
      _c4('\u9996\u9ad8\u6f5c\u5929\u6570', _allA.gq_days ? _allA.gq_days.mean + '<span style="opacity:.55;font-size:10px"> / ' + _allA.gq_days.median + '</span>' : '\u2014', '\u5747 / \u4e2d', '#D97706') +
      '</div></div>';
  }
  const colors = {person_colors_js};
  const rows = T.director;
  // 按当前产出日期筛选聚合编导指标（tPdSet 为空=全部产出日）
  function aggFor(p){
    const per = p === '__ALL__'
      ? (() => { const merged = {}; Object.values(T.per_pd || {}).forEach(byPd => {
            Object.entries(byPd).forEach(([pd, b]) => {
              if (!merged[pd]) merged[pd] = {gap_pc:[], gap_pe:[], gap_ec:[], gq_gap:[], open_n:0, order_n:0, total:0, run_n:0, tuwen_n:0, video_n:0, produce_n:0};
              ['gap_pc','gap_pe','gap_ec','gq_gap'].forEach(k => {
                merged[pd][k] = merged[pd][k].concat(b[k] || []);
              });
              merged[pd].open_n += b.open_n || 0; merged[pd].order_n += b.order_n || 0;
              merged[pd].total += b.total || 0; merged[pd].run_n += b.run_n || 0;
              merged[pd].tuwen_n += b.tuwen_n || 0; merged[pd].video_n += b.video_n || 0;
              merged[pd].produce_n += b.produce_n || 0;
            });
          }); return merged; })()
      : (T.per_pd && T.per_pd[p] ? T.per_pd[p] : {});
    const sel = tPdSet.size ? [...tPdSet] : Object.keys(per);
    const gaps = {gap_pc: [], gap_pe: [], gap_ec: [], gq_gap: []};
    let openN = 0, orderN = 0, total = 0, runN = 0, tuwenN = 0, videoN = 0, produceN = 0;
    sel.forEach(pd => {
      const b = per[pd];
      if (!b) return;
      ['gap_pc','gap_pe','gap_ec','gq_gap'].forEach(k => {
        if (b[k] && b[k].length) gaps[k].push(...b[k]);
      });
      openN += b.open_n || 0; orderN += b.order_n || 0; total += b.total || 0; runN += b.run_n || 0;
      tuwenN += b.tuwen_n || 0; videoN += b.video_n || 0; produceN += b.produce_n || 0;
    });
    const st = k => {
      const v = gaps[k];
      if (!v.length) return null;
      v.sort((a,b)=>a-b);
      const n = v.length;
      const qq = pp => { const idx=(n-1)*pp; const lo=Math.floor(idx); const hi=Math.min(lo+1,n-1); return v[lo]+(v[hi]-v[lo])*(idx-lo); };
      return {n, mean: Math.round(v.reduce((a,b)=>a+b,0)/n*10)/10, median: Math.round(qq(.5)*10)/10};
    };
    return {gap_pc: st('gap_pc'), gap_pe: st('gap_pe'), gap_ec: st('gap_ec'), gq_days: st('gq_gap'),
            open_n: openN, order_n: orderN, total: total, runout: runN,
            tuwen_n: tuwenN, video_n: videoN, produce_n: produceN,
            open_rate: total ? Math.round(openN/total*1000)/10 : null,
            order_rate: openN ? Math.round(orderN/openN*1000)/10 : null,
            run_rate: total ? Math.round(runN/total*1000)/10 : null,
            conv_run_rate: openN ? Math.round(runN/openN*1000)/10 : null};
  }
  const html = Object.keys(rows).map(p => {
    const d = aggFor(p);
    if (!d || d.total === 0) return '';
    const color = colors[p] || '#94A3B8';
    const fmtDays = s => s ? `${s.mean}<span style="opacity:.55;font-size:10px"> / ${s.median}</span>` : '—';
    return `<div style="background:#fff;border:1.5px solid ${color}44;border-radius:10px;padding:12px 14px;box-shadow:0 1px 3px rgba(0,0,0,.06)">
      <div style="display:flex;align-items:center;gap:6px;margin-bottom:8px">
        <span style="width:8px;height:8px;border-radius:50%;background:${color};display:inline-block"></span>
        <span style="font-size:13px;font-weight:700;color:${color}">${p}</span>
      </div>
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:6px">
        <div style="background:#F8FAFC;border-radius:6px;padding:7px 9px">
          <div style="font-size:10px;color:#94A3B8;margin-bottom:1px">素材产出 <span class="help-tip" data-tip="素材产出数量 = 图文数 + 视频数；视频含未过审，0改/1改/2改/3改按基础名算1次"></span></div>
          <div style="font-size:14px;font-weight:700;color:#1E40AF;font-family:monospace">${d.produce_n}</div>
          <div style="font-size:10px;color:#64748B;margin-top:1px">图文${d.tuwen_n} / 视频${d.video_n}</div>
        </div>
        <div style="background:#F8FAFC;border-radius:6px;padding:7px 9px">
          <div style="font-size:10px;color:#94A3B8;margin-bottom:1px">转化成交率 <span class="help-tip" data-tip="{tooltip_conv_rate}"></span></div>
          <div style="font-size:14px;font-weight:700;color:#1E40AF;font-family:monospace">${d.open_rate != null ? d.open_rate+'%' : '—'}</div>
          <div style="font-size:10px;color:#64748B;margin-top:1px">${d.open_n}/${d.total} 条</div>
        </div>
        <div style="background:#F8FAFC;border-radius:6px;padding:7px 9px">
          <div style="font-size:10px;color:#94A3B8;margin-bottom:1px">高潜成交率（转化） <span class="help-tip" data-tip="{tooltip_gq_conv_rate}"></span></div>
          <div style="font-size:14px;font-weight:700;color:#8B5CF6;font-family:monospace">${d.order_rate != null ? d.order_rate+'%' : '—'}</div>
          <div style="font-size:10px;color:#64748B;margin-top:1px">${d.order_n}/${d.open_n} 条</div>
        </div>
        <div style="background:#FFF7ED;border-radius:6px;padding:7px 9px">
          <div style="font-size:10px;color:#94A3B8;margin-bottom:1px">高潜跑出率 <span class="help-tip" data-tip="{tooltip_run_rate}"></span></div>
          <div style="font-size:14px;font-weight:700;color:#D97706;font-family:monospace">${d.run_rate != null ? d.run_rate+'%' : '—'}</div>
          <div style="font-size:10px;color:#64748B;margin-top:1px">${d.runout}/${d.total} 条</div>
        </div>
        <div style="background:#F8FAFC;border-radius:6px;padding:7px 9px">
          <div style="font-size:10px;color:#94A3B8;margin-bottom:1px">高潜成交率 <span class="help-tip" data-tip="{tooltip_gq_rate}"></span></div>
          <div style="font-size:14px;font-weight:700;color:#D97706;font-family:monospace">${d.total ? (Math.round(d.order_n/d.total*1000)/10)+'%' : '—'}</div>
          <div style="font-size:10px;color:#64748B;margin-top:1px">${d.order_n}/${d.total} 条</div>
        </div>
        <div style="background:#F8FAFC;border-radius:6px;padding:7px 9px">
          <div style="font-size:10px;color:#94A3B8;margin-bottom:1px">高潜跑出率（转化） <span class="help-tip" data-tip="{tooltip_conv_run_rate}"></span></div>
          <div style="font-size:14px;font-weight:700;color:#9A3412;font-family:monospace">${d.open_n ? (Math.round(d.runout/d.open_n*1000)/10)+'%' : '—'}</div>
          <div style="font-size:10px;color:#64748B;margin-top:1px">${d.runout}/${d.open_n} 条</div>
        </div>
        <div style="background:#FFFBEB;border-radius:6px;padding:7px 9px">
          <div style="font-size:10px;color:#94A3B8;margin-bottom:1px">产出→首转 <span class="help-tip" data-tip="{tooltip_gap_pc}"></span></div>
          <div style="font-size:14px;font-weight:700;color:#D97706;font-family:monospace">${fmtDays(d.gap_pc)}</div>
        </div>
        <div style="background:#FFFBEB;border-radius:6px;padding:7px 9px">
          <div style="font-size:10px;color:#94A3B8;margin-bottom:1px">产出→起量 <span class="help-tip" data-tip="{tooltip_gap_pe}"></span></div>
          <div style="font-size:14px;font-weight:700;color:#D97706;font-family:monospace">${fmtDays(d.gap_pe)}</div>
        </div>
        <div style="background:#FFFBEB;border-radius:6px;padding:7px 9px">
          <div style="font-size:10px;color:#94A3B8;margin-bottom:1px">起量→首转 <span class="help-tip" data-tip="{tooltip_gap_ec}"></span></div>
          <div style="font-size:14px;font-weight:700;color:#D97706;font-family:monospace">${fmtDays(d.gap_ec)}</div>
        </div>
        <div style="background:#FFFBEB;border-radius:6px;padding:7px 9px">
          <div style="font-size:10px;color:#94A3B8;margin-bottom:1px">首高潜天数(均/中) <span class="help-tip" data-tip="{tooltip_gq_days}"></span></div>
          <div style="font-size:14px;font-weight:700;color:#D97706;font-family:monospace">${fmtDays(d.gq_days)}</div>
        </div>
      </div>
    </div>`;
  }).join('');
  el.innerHTML = html;
}

function renderTimingTable(){
  const tbody = document.getElementById('timingBody');
  const countEl = document.getElementById('timingCount');
  if (!tbody) return;
  const filtered = T.rows.filter(tFiltered);
  const sorted = [...filtered].sort((a,b) => {
    let va = a[tSortCol], vb = b[tSortCol];
    if (va === '' || va === null || va === undefined) va = tSortCol === 'name' ? '' : -9999;
    if (vb === '' || vb === null || vb === undefined) vb = tSortCol === 'name' ? '' : -9999;
    if (typeof va === 'string') return tSortAsc ? va.localeCompare(vb,'zh') : vb.localeCompare(va,'zh');
    return tSortAsc ? va - vb : vb - va;
  });
  if (countEl) countEl.textContent = filtered.length
    ? '共 ' + filtered.length + ' 条（有转化 ' + filtered.filter(r => r.conv > 0).length + ' / 无转化 ' + filtered.filter(r => r.conv <= 0).length + '）'
    : '当前筛选下暂无素材';
  tbody.innerHTML = sorted.map(r => {
    const pc = {person_colors_js}[r.person] || '#94A3B8';
    const playBtn = (r.url && r.url.length > 10 && r.type === '视频')
      ? `<button class="btn-play" onclick="openTimingVideo('${encodeURIComponent(r.id)}')">▶</button>`
      : '<span style="color:var(--text-muted);font-size:11px">—</span>';
    return `<tr>
      <td><div class="mat-name" style="max-width:340px" title="${r.name}">${r.name}</div></td>
      <td><span class="mat-id" style="font-family:monospace;font-size:11px;color:var(--text-muted);white-space:nowrap" title="${r.id}">${r.id || '—'}</span></td>
      <td>${r.type === '图文' ? '<span style="color:#8B5CF6;font-size:10px;font-weight:600">图文</span>' : '<span style="color:#3B82F6;font-size:10px;font-weight:600">视频</span>'}</td>
      <td><span class="person-badge" style="background:${pc}18;color:${pc}">${r.person}</span></td>
      <td>${r.tag ? r.tag : '<span class="num-zero">—</span>'}</td>
      <td>${fmtD(r.pd)}</td>
      <td>${fmtD(r.first)}</td>
      <td>${fmtD(r.eff)}</td>
      <td style="color:#059669">${fmtD(r.conv_day)}</td>
      <td style="color:#D97706">${fmtD(r.gq_day)}</td>
      <td>${fmtGap(r.gap_pc)}</td>
      <td>${fmtGap(r.gap_pe)}</td>
      <td>${fmtGap(r.gap_ec)}</td>
      <td class="num">¥${r.spend.toLocaleString('zh',{maximumFractionDigits:0})}</td>
      <td class="num">${r.conv}</td>
      <td class="num">${r.gq}</td>
      <td class="num">${r.ctr != null ? r.ctr.toFixed(2)+'%' : '<span class="num-zero">—</span>'}</td>
      <td class="num" style="color:#8B5CF6">${r.cvr != null ? r.cvr.toFixed(2)+'%' : '<span class="num-zero">—</span>'}</td>
      <td class="num" style="color:#D97706">${r.deep_rate != null ? r.deep_rate.toFixed(1)+'%' : '<span class="num-zero">—</span>'}</td>
      <td class="num">${r.wf != null ? r.wf.toFixed(2)+'%' : '<span class="num-zero">—</span>'}</td>
      <td class="num">${r.w3 != null ? r.w3.toFixed(2)+'%' : '<span class="num-zero">—</span>'}</td>
      <td class="num">${r.wd != null ? r.wd.toFixed(1)+'s' : '<span class="num-zero">—</span>'}</td>
      <td>${playBtn}</td>
    </tr>`;
  }).join('');
}

function openTimingVideo(encodedId){
  const id = decodeURIComponent(encodedId);
  const r = T.rows.find(x => x.id === id);
  if (!r || !r.url) return;
  document.getElementById('modalTitle').textContent = r.name;
  document.getElementById('modalMeta').innerHTML =
    '<span class="modal-badge">产出 ' + fmtD(r.pd).replace(/<[^>]+>/g,'') + '</span>' +
    '<span class="modal-badge">首转 ' + fmtD(r.conv_day).replace(/<[^>]+>/g,'') + '</span>';
  document.getElementById('videoWrap').innerHTML =
    `<video controls autoplay preload="metadata" style="max-width:100%;max-height:65vh"><source src="${r.url}" type="video/mp4"></video>`;
  document.getElementById('videoModal').classList.add('open');
  document.body.style.overflow = 'hidden';
}

function setTFilterType(t, btn){
  tFilterType = t;
  document.querySelectorAll('#timingTypeBtns .sort-btn').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  renderTimingAll();
}
function setTFilterPerson(p, btn){
  tFilterPerson = p;
  document.querySelectorAll('#timingPersonBtns .sort-btn').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  renderTimingAll();
}
function setTFilterTag(t, btn){
  tFilterTag = t;
  document.querySelectorAll('#timingTagBtns .sort-btn').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  renderTimingAll();
}
function toggleTPd(d){
  if (tPdSet.has(d)) tPdSet.delete(d); else tPdSet.add(d);
  renderTPdChips();
  renderTimingAll();
}
function clearTPd(){
  tPdSet.clear();
  renderTPdChips();
  renderTimingAll();
}
function renderTPdChips(){
  const box = document.getElementById('timingPdChips');
  if (!box) return;
  const sel = [...tPdSet].sort().reverse();
  box.innerHTML = sel.map(d => `<span class="date-chip">${d.slice(0,2)}/${d.slice(2)}<span style="cursor:pointer;margin-left:4px" onclick="toggleTPd('${d}')">✕</span></span>`).join('')
    || '<span style="font-size:11px;color:var(--text-muted)">全部产出日期</span>';
}
function setTView(v, btn){
  tView = v;
  document.querySelectorAll('#timingViewBtns .sort-btn').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  document.getElementById('timingDetailView').style.display = v === 'detail' ? '' : 'none';
  document.getElementById('timingMonthView').style.display = v === 'month' ? '' : 'none';
  if (v === 'month') renderTimingMonth();
  const target = v === 'detail' ? document.getElementById('timingDetailView') : document.getElementById('timingMonthView');
  if (target) target.scrollIntoView({behavior:'smooth', block:'start'});
}
function renderTimingMonth(){
  const box = document.getElementById('timingMonthBody');
  if (!box) return;
  const months = {};
  T.rows.forEach(r => {
    if (!tFiltered(r)) return;
    const m = r.pd.slice(0,2);
    if (!months[m]) months[m] = {rows:[]};
    months[m].rows.push(r);
  });
  const mm = Object.keys(months).sort();
  const stat = rows => {
    const pc = rows.map(r => r.gap_pc).filter(v => v !== null);
    const pe = rows.map(r => r.gap_pe).filter(v => v !== null);
    const ec = rows.map(r => r.gap_ec).filter(v => v !== null);
    const avg = a => a.length ? Math.round(a.reduce((s,v)=>s+v,0)/a.length*10)/10 : '—';
    return {pc:avg(pc), pe:avg(pe), ec:avg(ec)};
  };
  box.innerHTML = mm.map(m => {
    const s = stat(months[m].rows);
    const withGq = months[m].rows.filter(r => r.gq > 0).length;
    return `<tr>
      <td style="font-weight:600;color:#1E40AF">${parseInt(m)}月</td>
      <td class="num">${months[m].rows.length}</td>
      <td class="num">${withGq}</td>
      <td class="num">${s.pc}</td>
      <td class="num">${s.pe}</td>
      <td class="num">${s.ec}</td>
    </tr>`;
  }).join('') || '<tr><td colspan="6" style="text-align:center;color:#94A3B8">该筛选下无数据</td></tr>';
}
function renderTimingAll(){
  renderTimingSummary();
  renderTimingHist();
  renderTimingDirector();
  renderTimingTable();
  if (tView === 'month') renderTimingMonth();
}

window._onDates = function(){ /* 时效模块不随全局日期变化 */ };
document.addEventListener('DOMContentLoaded', function(){
  renderTPdChips();
  renderTimingAll();
});
"""


# ---------------- 近3周跑出页（全自绘：竖排4区块 + 环比对比表） ----------------

PASS3W_JS = r"""
// ============ 近3周跑出页 ============
let REJ_DATES = [];
// 数据：RECENT_PASS_ANALYSIS = {latest, rows, audit_week}
//   rows: 每行 = (编导, 基础名) 一条，含 {id, name, names, type, version, person,
//         push_day, first, daily:{mmdd:{spend,conv,gq,imp,click,w3,w5,wf,wd}}, url}
// 窗口规则（2026-10-26 定稿）：
//   显示窗口 = 最近3个完整自然周；锚点 = 未筛选用最新投放日 / 已筛选用所选最后一天。
//   锚点所在自然周的周日已出现在投放数据里 → 以该周为末周；没有 → 锁上一完整自然周。
// 指标窗口：从有数据第1天到锚点日（历史累计，不按窗口截断）。
const P3 = {
  dkey: mmdd => new Date(2026, parseInt(mmdd.slice(0,2))-1, parseInt(mmdd.slice(2))).getTime(),
  f: d => ('0'+(d.getMonth()+1)).slice(-2) + '/' + ('0'+d.getDate()).slice(-2),
  // 锚点（投放日）
  anchor(){
    const R = RECENT_PASS_ANALYSIS;
    const touched = typeof DateBar !== 'undefined' && DateBar.touched;
    if (touched && REJ_DATES.length) {
      const last = REJ_DATES.slice().sort().pop();
      return new Date(2026, parseInt(last.slice(0,2))-1, parseInt(last.slice(3)));
    }
    if (R.latest) {
      return new Date(2026, parseInt(R.latest.slice(0,2))-1, parseInt(R.latest.slice(2)));
    }
    const all = R.rows.flatMap(r => Object.keys(r.daily || {})).map(this.dkey);
    return all.length ? new Date(Math.max(...all)) : new Date();
  },
  // 全部投放日集合（用于判断某天是否有数据）
  dataDays(){
    const s = new Set();
    RECENT_PASS_ANALYSIS.rows.forEach(r => Object.keys(r.daily || {}).forEach(k => s.add(k)));
    ALL_DATES.forEach(l => s.add(l.replace('/','')));
    return s;
  },
  // 显示窗口：[w3s, w3e, w2s, w2e, w1s, w1e]，周一到周日（第1周=末周）
  weeks(){
    const a = this.anchor();
    let end = a;
    let sun = new Date(end.getTime() + ((7 - end.getDay()) % 7) * 86400000);
    const has = this.dataDays();
    const sunKey = this.f(sun).replace('/','');
    if (!has.has(sunKey)) {
      // 锚点所在周周日无数据 → 锁上一完整自然周
      sun = new Date(sun.getTime() - 7*86400000);
    }
    const out = [];
    for (let i = 2; i >= 0; i--) {
      const e = new Date(sun.getTime() - i*7*86400000);
      const s = new Date(e.getTime() - 6*86400000);
      out.push(s, e);
    }
    return out;
  },
  // 指标累计窗口：有数据第1天 → 锚点
  metricRange(){
    const all = [];
    RECENT_PASS_ANALYSIS.rows.forEach(r => Object.keys(r.daily || {}).forEach(k => all.push(this.dkey(k))));
    const s = all.length ? Math.min(...all) : this.dkey(ALL_DATES[0].replace('/',''));
    const e = this.anchor().getTime();
    return {s, e};
  },
  // 聚合一行（daily 累计到 [ms, me]；无ID老素材按名称行）
  compute(r, ms, me){
    let spend=0, conv=0, gq=0, imp=0, click=0, w3n=0, w5n=0, wfn=0, wdn=0, impQ=0, actDays=0;
    Object.keys(r.daily || {}).forEach(mm => {
      const t = this.dkey(mm);
      if (t < ms || t > me) return;
      const x = r.daily[mm];
      spend += x.spend || 0; conv += x.conv || 0; gq += x.gq || 0;
      imp += x.imp || 0; click += x.click || 0;
      if ((x.spend || 0) > 0) actDays++;
      if ((x.imp || 0) > 0) {
        if ((x.w3 || 0) > 0) { w3n += x.w3 * x.imp; impQ += x.imp; }
        if ((x.w5 || 0) > 0) { w5n += x.w5 * x.imp; if (impQ === 0) impQ += x.imp; }
        if ((x.wf || 0) > 0) wfn += x.wf * x.imp;
        if ((x.wd || 0) > 0) wdn += x.wd * x.imp;
      }
    });
    return {
      r, spend, conv, gq, imp, click,
      ctr: imp > 0 ? click/imp*100 : -1,
      cpa: conv > 0 ? spend/conv : -1,
      deep_rate: conv > 0 ? gq/conv*100 : -1,
      qf: imp > 0 && wfn > 0 ? wfn/imp : -1,
      q3: imp > 0 && w3n > 0 ? w3n/imp : -1,
      q5: imp > 0 && w5n > 0 ? w5n/imp : -1,
      qd: imp > 0 && wdn > 0 ? wdn/imp : -1,
      active_days: actDays,
    };
  },
  fmtPct(v){ return v >= 0 ? v.toFixed(2) + '%' : '<span style="color:var(--text-muted)">—</span>'; },
  fmtSec(v){ return v >= 0 ? v.toFixed(1) + 's' : '<span style="color:var(--text-muted)">—</span>'; },
  cellHtml(c){
    return `<tr>
      <td><div class="mat-name" style="max-width:280px" title="${c.r.name}">${c.r.name}</div></td>
      <td>${c.r.id ? '<span class="num" style="font-family:monospace">' + c.r.id + '</span>' : '<span style="color:var(--text-muted)">—</span>'}</td>
      <td>${c.r.type === 'tuwen' ? '<span style="color:#8B5CF6;font-size:10px;font-weight:600">图文</span>' : '<span style="color:#3B82F6;font-size:10px;font-weight:600">视频</span>'}</td>
      <td><span class="num">${c.r.version}</span></td>
      <td>${this.fmtDateStr(c.r.push_day)}</td>
      <td><span class="num num-hi">¥${c.spend.toFixed(2)}</span></td>
      <td><span class="num">${this.fmtPct(c.ctr)}</span></td>
      <td>${c.conv > 0 ? '<span class="num num-hi">' + c.conv + '</span>' : '<span class="num num-zero">—</span>'}</td>
      <td><span class="num">${c.cpa >= 0 ? '¥' + c.cpa.toFixed(0) : '—'}</span></td>
      <td>${c.gq > 0 ? '<span class="gaoquan-cell">' + c.gq + '</span>' : '<span class="gaoquan-zero num-zero">—</span>'}</td>
      <td><span class="num" style="color:${c.deep_rate >= 15 ? '#D97706' : '#94A3B8'}">${c.deep_rate >= 0 ? c.deep_rate.toFixed(1) + '%' : '—'}</span></td>
      <td><span class="num">${this.fmtPct(c.qf)}</span></td>
      <td><span class="num">${this.fmtPct(c.q3)}</span></td>
      <td><span class="num">${this.fmtPct(c.q5)}</span></td>
      <td><span class="num">${this.fmtSec(c.qd)}</span></td>
      <td><span class="num">${c.active_days}</span></td>
      <td>${c.r.url && c.r.url.length > 10 ? `<button class="btn-play" onclick="P3.play('${encodeURIComponent(c.r.url)}')"><svg viewBox="0 0 16 16" fill="currentColor"><path d="M4 3l10 5-10 5V3z"/></svg>播放</button>` : '<span style="color:var(--text-muted);font-size:11px">无链接</span>'}</td>
    </tr>`;
  },
  fmtDateStr(mmdd){
    return mmdd ? mmdd.slice(0,2) + '/' + mmdd.slice(2) : '—';
  },
  play(url){
    url = decodeURIComponent(url);
    document.getElementById('modalTitle').textContent = '素材预览';
    document.getElementById('modalMeta').innerHTML = '';
    document.getElementById('videoWrap').innerHTML =
      `<video controls autoplay preload="metadata" style="max-width:100%;max-height:65vh"><source src="${url}" type="video/mp4"></video>`;
    document.getElementById('videoModal').classList.add('open');
    document.body.style.overflow = 'hidden';
  },
  // 渲染全部3周 / 第3周 / 第2周 / 第1周 四个区块
  renderAll(){
    this.renderCompare();
    const w = this.weeks();
    const m = this.metricRange();
    const blocks = [
      {id:'wAll', label:'全部3周', s: w[0], e: w[5]},
      {id:'w3', label:'第3周', s: w[0], e: w[1]},
      {id:'w2', label:'第2周', s: w[2], e: w[3]},
      {id:'w1', label:'第1周', s: w[4], e: w[5]},
    ];
    const box = document.getElementById('passWeekBlocks');
    box.innerHTML = blocks.map(b => {
      // 产出日落在该显示周内的素材行；指标按第1天→锚点累计（不截断）
      const rows = (RECENT_PASS_ANALYSIS.rows || []).filter(r => {
        const t = this.dkey(r.push_day);
        return t >= this.dkey(this.f(b.s).replace('/','')) && t <= this.dkey(this.f(b.e).replace('/',''));
      });
      const computed = rows.map(r => this.compute(r, m.s, m.e));
      // 产出数量（全量工作量口径）：produce 里产出日落在该周的素材（含未过审/未推送/过审文件，基础名去重）
      const prod = (RECENT_PASS_ANALYSIS.produce || []).filter(x => {
        const t = this.dkey(x.pd);
        return t >= this.dkey(this.f(b.s).replace('/','')) && t <= this.dkey(this.f(b.e).replace('/',''));
      });
      return this.blockHtml(b.label, this.f(b.s), this.f(b.e), computed, prod);
    }).join('');
  },
  blockHtml(label, s, e, computed, prod){
    const tSpend = computed.reduce((s,c) => s+c.spend, 0);
    const tConv = computed.reduce((s,c) => s+c.conv, 0);
    const tGq = computed.reduce((s,c) => s+c.gq, 0);
    const tImp = computed.reduce((s,c) => s+c.imp, 0);
    const tClick = computed.reduce((s,c) => s+c.click, 0);
    const ctr = tImp > 0 ? tClick/tImp*100 : -1;
    const cpa = tConv > 0 ? tSpend/tConv : -1;
    const deep = tConv > 0 ? tGq/tConv*100 : -1;
    // 五率（基础名行集合，指标累计窗口内判断）
    const convN = computed.filter(c => c.conv > 0).length;
    const gqN = computed.filter(c => c.gq > 0).length;
    const runN = computed.filter(c => c.gq >= 5).length;
    const total = computed.length;
    // 产出数量（全量工作量口径，含过审/未过审，0-3改按基础名算1条）
    const prodN = prod.length;
    const prodTw = prod.filter(x => x.t === 'tuwen').length;
    const prodVd = prodN - prodTw;
    // 过审率：归属周日落在该区块内的提交素材（通过归通过日、未通过归首次提交日）
    const as = this.auditStatsFor(s, e);
    const passRate = as.submitted ? (as.passed/as.submitted*100).toFixed(1)+'%' : '—';
    const passFrac = as.submitted ? as.passed+'/'+as.submitted : '—';
    const cell = (l, v, tip) => `<div style="background:#F8FAFC;border-radius:6px;padding:6px 8px;text-align:center"${tip ? ' title="'+tip+'"' : ''}><div style="font-size:10px;color:#94A3B8">${l}</div><div style="font-size:14px;font-weight:700;font-family:monospace;color:#1E40AF">${v}</div></div>`;
    const pct1 = v => v != null ? v + '%' : '—';
    const summary = `<div style="display:grid;grid-template-columns:repeat(13,1fr);gap:6px;margin-bottom:10px">
      ${cell('点击率', ctr >= 0 ? ctr.toFixed(2)+'%' : '—')}
      ${cell('CPA', cpa >= 0 ? '¥'+cpa.toFixed(0) : '—')}
      ${cell('转化', tConv)}
      ${cell('高潜', tGq)}
      ${cell('深转率', deep >= 0 ? deep.toFixed(1)+'%' : '—')}
      ${cell('过审率', passRate, '过审 ' + passFrac + ' 条（通过归通过日/未通过归首次提交日）')}
      ${cell('转化成交率', total > 0 ? pct1(Math.round(convN/total*1000)/10) : '—')}
      ${cell('高潜成交率（转化）', (convN || gqN) > 0 ? pct1(Math.round(gqN/Math.max(convN,gqN)*1000)/10) : '—')}
      ${cell('高潜成交率', total > 0 ? pct1(Math.round(gqN/total*1000)/10) : '—')}
      ${cell('高潜跑出率', total > 0 ? pct1(Math.round(runN/total*1000)/10) : '—')}
      ${cell('高潜跑出率（转化）', convN > 0 ? pct1(Math.round(runN/convN*1000)/10) : '—')}
      ${cell('产出素材数', prodN)}
      ${cell('图文/视频', prodTw + ' / ' + prodVd)}
    </div>`;
    const table = `<div class="table-wrap" style="max-height:460px;overflow-y:auto">
      <table style="font-size:12px">
        <thead><tr>
          <th>素材名称</th><th>素材ID</th><th>类型</th><th>改版</th><th>产出日</th><th>消耗</th><th>点击率</th><th>转化</th><th>CPA</th><th>深转</th><th>深转率</th><th>完播率</th><th>3秒播放率</th><th>5秒播放率</th><th>播放时长</th><th>在投天数</th><th>视频</th>
        </tr></thead>
        <tbody>${computed.map(c => this.cellHtml(c)).join('') || '<tr><td colspan="17" style="text-align:center;color:#94A3B8">该周无素材</td></tr>'}</tbody>
      </table>
    </div>`;
    return `<div class="chart-card" style="margin-bottom:16px">
      <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:10px">
        <div class="section-title" style="margin:0">${label} <span style="color:var(--text-muted);font-weight:400;font-size:11px">（${s} ~ ${e} 产出 · 指标=第1天~锚点累计）</span></div>
        <div style="font-size:11px;color:var(--text-muted)">${computed.length} 条</div>
      </div>
      ${summary}
      ${this.directorCards(computed, prod, s, e)}
      ${table}
    </div>`;
  },
  // 过审统计聚合：归属周日落在 [s, e] 内的提交素材（s/e 为 'MM/DD' 字符串）
  auditStatsFor(s, e){
    const audit = RECENT_PASS_ANALYSIS.audit_week || {};
    const out = {submitted:0, passed:0, by_person:{}};
    const ks = this.dkey(String(s).replace('/',''));
    const ke = this.dkey(String(e).replace('/',''));
    Object.entries(audit).forEach(([wk, v]) => {
      const k = this.dkey(wk);
      if (k < ks || k > ke) return;
      out.submitted += v.submitted || 0;
      out.passed += v.passed || 0;
      Object.entries(v.by_person || {}).forEach(([p, b]) => {
        const bp = out.by_person[p] || (out.by_person[p] = {submitted:0, passed:0});
        bp.submitted += b.submitted || 0;
        bp.passed += b.passed || 0;
      });
    });
    return out;
  },
  // 各编导表现卡（每区块内，五率+过审率+素材数）
  directorCards(computed, prod, s, e){
    const CORE = ['小敏', '瑞晨', '嘉丽', '雅迪'];
    const colors = PERSON_COLORS;
    const pct1 = v => v != null ? v + '%' : '—';
    const cards = CORE.map(p => {
      const sub = computed.filter(c => c.r.person === p);
      if (!sub.length) return '';
      const total = sub.length;
      const convN = sub.filter(c => c.conv > 0).length;
      const gqN = sub.filter(c => c.gq > 0).length;
      const runN = sub.filter(c => c.gq >= 5).length;
      // 编导产出数量（全量工作量口径）
      const ps = (prod || []).filter(x => x.p === p);
      const tw = ps.filter(x => x.t === 'tuwen').length;
      const vd = ps.length - tw;
      // 编导过审率：该区块归属周内、该编导的提交素材（通过归通过日/未通过归首次提交日）
      const as = this.auditStatsFor(s, e);
      const bp = (as.by_person || {})[p] || {submitted:0, passed:0};
      const pRate = bp.submitted ? (bp.passed/bp.submitted*100).toFixed(1)+'%' : '—';
      const pFrac = bp.submitted ? bp.passed+'/'+bp.submitted : '—';
      const cell = (label, tip, val, frac, color) => `<div style="background:#F8FAFC;border-radius:6px;padding:6px 8px;text-align:center"><div style="font-size:10px;color:#94A3B8">${label} <span class="help-tip" data-tip="${tip}"></span></div><div style="font-size:13px;font-weight:700;color:${color};font-family:monospace">${val}</div><div style="font-size:9px;color:#64748B;font-family:monospace">${frac} 条</div></div>`;
      return `<div style="background:#fff;border:1.5px solid ${colors[p]||'#64748B'}44;border-radius:10px;padding:10px 12px">
        <div style="display:flex;align-items:center;gap:6px;margin-bottom:6px">
          <span style="width:8px;height:8px;border-radius:50%;background:${colors[p]||'#64748B'};display:inline-block"></span>
          <span style="font-size:12px;font-weight:700;color:${colors[p]||'#64748B'}">${p}</span>
          <span style="font-size:10px;color:#94A3B8;margin-left:auto">图文${tw} / 视频${vd}</span>
        </div>
        <div style="display:grid;grid-template-columns:repeat(6,1fr);gap:5px">
          ${cell('过审率', '过审率 = 过审数÷提交数（多次修改按基础名算1次；通过归通过日/未通过归首次提交日）', pRate, pFrac, '#059669')}
          ${cell('转化成交率', '转化成交率 = 转化>0素材数 ÷ 产出投放素材数', total>0 ? pct1(Math.round(convN/total*1000)/10) : '—', convN+'/'+total, '#1E40AF')}
          ${cell('高潜成交率（转化）', '高潜成交率（转化） = 深转>0素材数 ÷ 转化>0素材数', (convN||gqN)>0 ? pct1(Math.round(gqN/Math.max(convN,gqN)*1000)/10) : '—', gqN+'/'+Math.max(convN,gqN), '#8B5CF6')}
          ${cell('高潜成交率', '高潜成交率 = 深转>0素材数 ÷ 产出投放素材数', total>0 ? pct1(Math.round(gqN/total*1000)/10) : '—', gqN+'/'+total, '#D97706')}
          ${cell('高潜跑出率', '高潜跑出率 = 深转≥5素材数 ÷ 产出投放素材数', total>0 ? pct1(Math.round(runN/total*1000)/10) : '—', runN+'/'+total, '#D97706')}
          ${cell('高潜跑出率（转化）', '高潜跑出率（转化） = 深转≥5素材数 ÷ 转化>0素材数', convN>0 ? pct1(Math.round(runN/convN*1000)/10) : '—', runN+'/'+convN, '#9A3412')}
        </div>
      </div>`;
    }).filter(Boolean);
    return cards.length
      ? `<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(520px,1fr));gap:10px;margin-bottom:12px">${cards.join('')}</div>`
      : '';
  },
  // 环比对比表：周位配对（第3 vs 第3、第2 vs 第2、第1 vs 第1）
  // 素材：每格只算该格子区间内产出；指标：上周列→上周窗口周日，本周列→锁定窗口周日
  renderCompare(){
    const el = document.getElementById('passCompare');
    if (!el) return;
    const w = this.weeks();   // [w3s,w3e,w2s,w2e,w1s,w1e]，自然周
    const m = this.metricRange();
    const f = this.f;
    const curWinEnd = this.dkey(f(w[5]).replace('/',''));     // 本周列终点=窗口第1周周日
    const prevWinEnd = this.dkey(f(w[3]).replace('/',''));   // 上周列终点=窗口第2周周日
    const rows = [];
    for (let i = 2; i >= 0; i--) {
      const curS = w[i*2], curE = w[i*2+1];
      const prevS = new Date(curS.getTime() - 7*86400000), prevE = new Date(curE.getTime() - 7*86400000);
      const mk = (s, e, endTime) => {
        const ks = this.dkey(f(s).replace('/','')), ke = this.dkey(f(e).replace('/',''));
        // 素材：产出日在该格子区间内；指标累计到 endTime
        const computed = (RECENT_PASS_ANALYSIS.rows || [])
          .filter(r => this.dkey(r.push_day) >= ks && this.dkey(r.push_day) <= ke)
          .map(r => this.compute(r, m.s, endTime));
        const convN = computed.filter(c => c.conv > 0).length;
        const gqN = computed.filter(c => c.gq > 0).length;
        const runN = computed.filter(c => c.gq >= 5).length;
        const total = computed.length;
        return {convN, gqN, runN, total,
                cr: total>0 ? (convN/total*100).toFixed(1) : '—',
                crFrac: convN+'/'+total,
                gqcr: (convN||gqN)>0 ? (gqN/Math.max(convN,gqN)*100).toFixed(1) : '—',
                gqcrFrac: gqN+'/'+Math.max(convN,gqN),
                gqr: total>0 ? (gqN/total*100).toFixed(1) : '—',
                gqrFrac: gqN+'/'+total,
                runr: total>0 ? (runN/total*100).toFixed(1) : '—',
                runrFrac: runN+'/'+total,
                crrun: convN>0 ? (runN/convN*100).toFixed(1) : '—',
                crrunFrac: runN+'/'+convN};
      };
      const cur = mk(curS, curE, curWinEnd);
      const prev = mk(prevS, prevE, prevWinEnd);
      rows.push({label:'第'+(3-i)+'周', cs:f(curS), ce:f(curE), ps:f(prevS), pe:f(prevE), cur, prev});
    }
    const diff = (a, b) => {
      const va = parseFloat(a), vb = parseFloat(b);
      if (isNaN(va) || isNaN(vb)) return '<span style="color:#94A3B8">—</span>';
      const d = va - vb;
      const cls = d > 0 ? '#059669' : d < 0 ? '#DC2626' : '#94A3B8';
      const arrow = d > 0 ? '▲' : d < 0 ? '▼' : '＝';
      return `<span style="color:${cls};font-size:11px">${arrow} ${Math.abs(d).toFixed(1)}%</span>`;
    };
    el.innerHTML = `<div class="chart-card" style="margin-bottom:16px">
      <div class="section-title" style="margin-bottom:8px">周环比对比（相邻自然周配对 · 上周列指标到${f(new Date(prevWinEnd))} · 本周列指标到${f(new Date(curWinEnd))}）</div>
      <div class="table-wrap" style="overflow-x:auto">
        <table style="font-size:12px;min-width:960px">
          <thead><tr>
            <th>周位</th><th>上周区间</th><th>本周区间</th>
            <th>转化成交率</th><th>高潜成交率（转化）</th><th>高潜成交率</th><th>高潜跑出率</th><th>高潜跑出率（转化）</th>
          </tr></thead>
          <tbody>${rows.map(r => `<tr>
            <td><b>${r.label}</b></td>
            <td style="color:#64748B">${r.ps} ~ ${r.pe}</td>
            <td style="color:#1E40AF;font-weight:600">${r.cs} ~ ${r.ce}</td>
            <td title="上周 ${r.prev.crFrac} → 本周 ${r.cur.crFrac}">${r.prev.cr} → ${r.cur.cr} ${diff(r.cur.cr, r.prev.cr)}</td>
            <td title="上周 ${r.prev.gqcrFrac} → 本周 ${r.cur.gqcrFrac}">${r.prev.gqcr} → ${r.cur.gqcr} ${diff(r.cur.gqcr, r.prev.gqcr)}</td>
            <td title="上周 ${r.prev.gqrFrac} → 本周 ${r.cur.gqrFrac}">${r.prev.gqr} → ${r.cur.gqr} ${diff(r.cur.gqr, r.prev.gqr)}</td>
            <td title="上周 ${r.prev.runrFrac} → 本周 ${r.cur.runrFrac}">${r.prev.runr} → ${r.cur.runr} ${diff(r.cur.runr, r.prev.runr)}</td>
            <td title="上周 ${r.prev.crrunFrac} → 本周 ${r.cur.crrunFrac}">${r.prev.crrun} → ${r.cur.crrun} ${diff(r.cur.crrun, r.prev.crrun)}</td>
          </tr>`).join('')}</tbody>
        </table>
      </div>
      <div class="legend" style="margin-top:6px">五率口径：每格素材=该格区间内产出（基础名去重），指标从有数据第1天累计——上周列到上周窗口周日、本周列到锁定窗口周日。</div>
    </div>`;
  }
};

window._onDates = function(dates){
  REJ_DATES = dates;
  P3.renderAll();
};
document.addEventListener('DOMContentLoaded', function(){
  DateBar.init(ALL_DATES, DAY_SPEND, [ALL_DATES[ALL_DATES.length-1]]);
  P3.renderAll();
});
"""

PASS3W_BODY = """
  <!-- 近3周跑出表现（视频+图文）：环比对比表 + 竖排4区块 -->
  <div id="passCompare"></div>
  <div id="passWeekBlocks"></div>
"""


# ---------------- 主入口：生成四个页面 ----------------

def _cut_html(start_anchor, end_anchor):
    import generate_report_daily_guide as gdg
    t = gdg.HTML_TEMPLATE
    i = t.index(start_anchor)
    j = t.index(end_anchor)
    return t[i:j]


def generate_pages(days_data, latest_label, latest_mmdd, out_dir):
    """生成四个页面。days_data: [(label, rows)]（含渠道行）。"""
    import generate_report_daily_guide as gdg
    out_dir = Path(out_dir)

    # ---- 1. 拆渠道、每日聚合 ----
    detail_days = []
    channel_stats = defaultdict(lambda: defaultdict(lambda: {'spend': 0.0, 'imp': 0.0, 'click': 0.0, 'conv': 0.0, 'gq': 0.0}))
    for label, rows in days_data:
        dr = []
        for r in rows:
            if r.get('_is_channel'):
                c = channel_stats[r['_account']][label]
                c['spend'] += r['_消耗']; c['imp'] += r['_展示数']; c['click'] += r['_点击数']
                c['conv'] += r['_转化数']; c['gq'] += r['_高潜成交']
            else:
                dr.append(r)
        detail_days.append((label, dr))

    all_dates = [l for l, _ in detail_days]
    all_rows_by_date = {}
    day_stats = {}
    tag_stats_by_day = {}
    type_stats_by_day = {}
    day_spend = {}
    for label, rows in detail_days:
        jrows = gdg.rows_to_json(rows, include_video_url=(label == latest_label))
        all_rows_by_date[label] = jrows
        s = gdg.compute_stats(rows)
        day_stats[label] = {'spend': round(s['total_spend'], 2), 'imp': round(s['total_imp']),
                            'click': round(s['total_clicks']), 'conv': round(s['total_conv']),
                            'gq': round(s['total_gaoquan']), 'materials': len(rows)}
        day_spend[label] = round(s['total_spend'], 2)
        # 标签聚合（仅视频、非图文、消耗>0）
        ts = {'A1': {'spend': 0, 'conv': 0, 'gq': 0, 'click': 0, 'imp': 0},
              'A2': {'spend': 0, 'conv': 0, 'gq': 0, 'click': 0, 'imp': 0},
              'A3': {'spend': 0, 'conv': 0, 'gq': 0, 'click': 0, 'imp': 0},
              'A4': {'spend': 0, 'conv': 0, 'gq': 0, 'click': 0, 'imp': 0}}
        for r in rows:
            if r['_is_tuwen'] or r['_消耗'] == 0:
                continue
            tag = r['_tag']
            if not tag:
                continue
            for t in tag.split(','):
                base = t.split('-')[0].strip()
                if base in ts:
                    ts[base]['spend'] += r['_消耗']; ts[base]['conv'] += r['_转化数']
                    ts[base]['gq'] += r['_高潜成交']; ts[base]['click'] += r['_点击数']
                    ts[base]['imp'] += r['_展示数']
        tag_stats_by_day[label] = ts
        # 类型聚合
        ty = {'video': {'spend': 0, 'conv': 0, 'gq': 0, 'click': 0, 'imp': 0, 'n': 0},
              'tuwen': {'spend': 0, 'conv': 0, 'gq': 0, 'click': 0, 'imp': 0, 'n': 0},
              'ai': {'spend': 0, 'conv': 0, 'gq': 0, 'click': 0, 'imp': 0, 'n': 0}}
        for r in rows:
            if r['_消耗'] == 0:
                continue
            if r['_is_ai']:
                k = 'ai'
            elif r['_is_tuwen']:
                k = 'tuwen'
            else:
                k = 'video'
            ty[k]['spend'] += r['_消耗']; ty[k]['conv'] += r['_转化数']; ty[k]['gq'] += r['_高潜成交']
            ty[k]['click'] += r['_点击数']; ty[k]['imp'] += r['_展示数']; ty[k]['n'] += 1
        type_stats_by_day[label] = ty

    channel_by_date = {acc: {l: {'spend': round(d['spend'], 2), 'imp': int(d['imp']),
                                 'click': int(d['click']), 'conv': int(d['conv']), 'gq': int(d['gq'])}
                             for l, d in by_date.items()}
                       for acc, by_date in channel_stats.items()}

    # ---- 2. 卡审 / 近3周 / 时效 ----
    reject_analysis = gdg.build_reject_analysis()
    test_audit_analysis = gdg.build_test_audit_analysis()
    recent_pass_analysis = gdg.build_recent_pass_analysis()
    compare_data = gdg.build_compare(detail_days)
    timing = build_timing_data()

    # ---- 3. 旧 JS 切片 + 旧 HTML 块 ----
    js = _js_slices()
    # 旧模板用 {{ }} 做 format 转义，直接嵌入页面时还原为单花括号
    for k in js:
        js[k] = js[k].replace('{{', '{').replace('}}', '}')
    css, inject_legacy, shared_legacy = _legacy_assets()
    # CSS 同样带 {{}} 转义，必须还原（否则浏览器丢弃整段样式，页面变裸文字）
    css = css.replace('{{', '{').replace('}}', '}')
    modal_html = _cut_html('<div class="modal-overlay"', '<script>')
    kajian_html = _cut_html('<!-- 卡审分析：投放账户推送素材池（仅视频，图文过审数据导不出） -->',
                            '<!-- 近3周过审素材跑出表现（视频+图文） -->')
    person_html = _cut_html('<!-- 编导卡片 -->', '<!-- 筛选栏 -->')
    person_html = person_html.replace(
        '<div id="personCardsRow"',
        '<div id="personAllCard" style="margin-bottom:12px"></div><div id="personCardsRow"'
    )
    filter_html = _cut_html('<!-- 筛选栏 -->', '<!-- 素材明细表 -->')
    table_html = _cut_html('<!-- 素材明细表 -->', '<!-- 素材生命周期（独立网页嵌入，随日报一并发布） -->')
    table_html = table_html.replace(
        '<th data-col="name">素材名称</th>',
        '<th data-col="name" style="min-width:320px">素材名称</th>'
    )
    # 行模板里的名称宽度同步放宽
    js['table'] = js['table'].replace(
        'class="mat-name" title="${r.name}"',
        'class="mat-name" style="max-width:420px" title="${r.name}"'
    )
    # CSS 上限也提高
    css = css.replace('.mat-name{{max-width:260px;', '.mat-name{{max-width:420px;')

    table_html = table_html.replace(
        '编导高潜成交率<span class="help-tip" data-tip="高潜成交率 = 深转>0 的素材数 ÷ 该编导总素材数（按名称基础名去重：同名多版本算一条，任一版本深转>0 即高潜成交）；跟随顶部日期、产出日期、标签/类型筛选联动"></span>',
        '编导转化成交率<span class="help-tip" data-tip="转化成交率 = 转化>0 的素材数 ÷ 该编导总素材数（按名称基础名去重：同名多版本算一条）；跟随顶部日期、产出日期、标签/类型筛选联动"></span>'
    )

    chart_js_code = ''
    chart_path = Path(__file__).parent / 'chart.min.js'
    if chart_path.exists():
        chart_js_code = chart_path.read_text(encoding='utf-8')

    person_colors_json = json.dumps(gdg.PERSON_COLORS, ensure_ascii=False)

    # ---- 编导卡四率补丁（明细页 updatePersonCards）：开口/成单/出单/跑出 + 全部编导总卡 ----
    js['person_cards'] = js['person_cards'].replace(
        "function updatePersonCards(rows, auditData) {",
        "function updatePersonCards(rows, auditData) {\n"
        "  const _selDates4 = (window.DateBar && DateBar.selected && DateBar.selected.length) ? DateBar.selected : [ALL_DATES[ALL_DATES.length-1]];\n"
        "  var _frCache = {};\n"
        "  function frOf(p){\n"
        "    if (_frCache[p]) return _frCache[p];\n"
        "    _frCache[p] = computeFourRates(p, _selDates4, 'set', produceDaySet, _personType, null, 'any');\n"
        "    return _frCache[p];\n"
        "  }\n"
        "  function frRate(p, kind){\n"
        "    const f = frOf(p);\n"
        "    const v = kind === 'order' ? f.order_rate : kind === 'run' ? f.run_rate : kind === 'chulv' ? f.chulv_rate : kind === 'conv_run' ? f.conv_run_rate : f.open_rate;\n"
        "    return v != null ? v + '%' : '\\u2014';\n"
        "  }\n"
        "  function frFrac(p, kind){\n"
        "    const f = frOf(p);\n"
        "    if (kind === 'order') return f.gq + ' / ' + Math.max(f.gq, f.conv) + ' \\u6761';\n"
        "    if (kind === 'run') return f.runout + ' / ' + f.total + ' \\u6761';\n"
        "    if (kind === 'chulv') return f.gq + ' / ' + f.total + ' \\u6761';\n"
        "    if (kind === 'conv_run') return f.runout + ' / ' + f.conv + ' \\u6761';\n"
        "    return f.conv + ' / ' + f.total + ' \\u6761';\n"
        "  }\n"
        "  function frTip(p, kind){\n"
        "    const f = frOf(p);\n"
        "    if (kind === 'order') return '\\u6df1\\u8f6c>0\\u7d20\\u6750 ' + f.gq + ' \\u6761 \\u00f7 \\u8f6c\\u5316>0\\u7d20\\u6750 ' + Math.max(f.gq, f.conv) + ' \\u6761';\n"
        "    if (kind === 'run') return '\\u6df1\\u8f6c\\u22655\\u5355\\u7d20\\u6750 ' + f.runout + ' \\u6761 \\u00f7 \\u4ea7\\u51fa\\u6295\\u653e\\u7d20\\u6750 ' + f.total + ' \\u6761';\n"
        "    if (kind === 'chulv') return '\\u6df1\\u8f6c>0\\u7d20\\u6750 ' + f.gq + ' \\u6761 \\u00f7 \\u4ea7\\u51fa\\u6295\\u653e\\u7d20\\u6750 ' + f.total + ' \\u6761';\n"
        "    if (kind === 'conv_run') return '\\u6df1\\u8f6c\\u22655\\u5355\\u7d20\\u6750 ' + f.runout + ' \\u6761 \\u00f7 \\u8f6c\\u5316>0\\u7d20\\u6750 ' + f.conv + ' \\u6761';\n"
        "    return '\\u8f6c\\u5316>0\\u7d20\\u6750 ' + f.conv + ' \\u6761 \\u00f7 \\u4ea7\\u51fa\\u6295\\u653e\\u7d20\\u6750 ' + f.total + ' \\u6761';\n"
        "  }\n"
        "  renderAllDirectorCard();"
    )

    js['person_cards'] = js['person_cards'].replace(
        "  // 按总消耗排序，过滤无数据的人",
        "  renderAllDirectorCard();\n"
        "  // 按总消耗排序，过滤无数据的人"
    )
    js['person_cards'] = js['person_cards'].replace(
        "  const _selDates4 = (window.DateBar",
        "  function renderAllDirectorCard() {\n"
        "    const _el = document.getElementById('personAllCard');\n"
        "    if (!_el) return;\n"
        "    const _all4 = computeFourRates('__ALL__', _selDates4, 'set', produceDaySet, _personType, null, 'any');\n"
        "    let vS=0, tS=0, cV=0, cK=0, iM=0, gQ=0;\n"
        "    _personRows.forEach(r => {\n"
        "      if (r.spend === 0 || r.is_ai) return;\n"
        "      const isTw = r.is_tuwen;\n"
        "      if (isTw) tS += r.spend; else vS += r.spend;\n"
        "      if (_personType === 'all' || (_personType === 'video' && !isTw) || (_personType === 'tuwen' && isTw)) {\n"
        "        cV += r.conversions; cK += r.clicks; iM += r.impressions; gQ += r.gaoquan;\n"
        "      }\n"
        "    });\n"
        "    const totS = _personType === 'video' ? vS : _personType === 'tuwen' ? tS : vS + tS;\n"
        "    const cpa = cV > 0 ? '\\u00a5' + (totS/cV).toFixed(2) : '\\u2014';\n"
        "    const ctr = iM > 0 ? (cK/iM*100).toFixed(2)+'%' : '\\u2014';\n"
        "    const cvr = cK > 0 ? (cV/cK*100).toFixed(2)+'%' : '\\u2014';\n"
        "    const deep = cV > 0 ? (gQ/cV*100).toFixed(1)+'%' : '\\u2014';\n"
        "    const cells = [\n"
        "      ['\\u89c6\\u9891\\u6d88\\u8017', '\\u00a5' + vS.toFixed(2), '', '#1E40AF'],\n"
        "      ['\\u56fe\\u6587\\u6d88\\u8017', '\\u00a5' + tS.toFixed(2), '', '#8B5CF6'],\n"
        "      ['\\u8f6c\\u5316\\u6570', String(cV), '', '#059669'],\n"
        "      ['\\u70b9\\u51fb\\u7387', ctr, '', '#3B82F6'],\n"
        "      ['\\u8f6c\\u5316\\u7387', cvr, '', '#8B5CF6'],\n"
        "      ['\\u9ad8\\u6f5c\\u6210\\u4ea4', String(gQ), '', '#D97706'],\n"
        "      ['CPA', cpa, '', '#64748B'],\n"
        "      ['\\u6df1\\u8f6c\\u7387', deep, '', '#D97706'],\n"
        "      ['\\u8f6c\\u5316\\u6210\\u4ea4\\u7387', _all4.open_rate != null ? _all4.open_rate+'%' : '\\u2014', _all4.conv+'/'+_all4.total+' \\u6761', '#1E40AF'],\n"
        "      ['\\u9ad8\\u6f5c\\u6210\\u4ea4\\u7387\\uff08\\u8f6c\\u5316\\uff09', _all4.order_rate != null ? _all4.order_rate+'%' : '\\u2014', _all4.gq+'/'+Math.max(_all4.gq,_all4.conv)+' \\u6761', '#8B5CF6'],\n"
        "      ['\\u9ad8\\u6f5c\\u6210\\u4ea4\\u7387', _all4.chulv_rate != null ? _all4.chulv_rate+'%' : '\\u2014', _all4.gq+'/'+_all4.total+' \\u6761', '#D97706'],\n"
        "      ['\\u9ad8\\u6f5c\\u8dd1\\u51fa\\u7387', _all4.run_rate != null ? _all4.run_rate+'%' : '\\u2014', _all4.runout+'/'+_all4.total+' \\u6761', '#D97706'],\n"
        "      ['\\u9ad8\\u6f5c\\u8dd1\\u51fa\\u7387\\uff08\\u8f6c\\u5316\\uff09', _all4.conv_run_rate != null ? _all4.conv_run_rate+'%' : '\\u2014', _all4.runout+'/'+_all4.conv+' \\u6761', '#9A3412']\n"
        "    ];\n"
        "    const cellHtml = cells.map(c => '<div style=\"background:#F8FAFC;border-radius:6px;padding:6px 8px;text-align:center\"><div style=\"font-size:10px;color:#94A3B8\">' + c[0] + '</div><div style=\"font-size:13px;font-weight:700;font-family:monospace;color:' + c[3] + '\">' + c[1] + '</div>' + (c[2] ? '<div style=\"font-size:9px;color:#64748B\">' + c[2] + '</div>' : '') + '</div>').join('');\n"
        "    _el.innerHTML = '<div style=\"background:#fff;border:1.5px solid #1E40AF44;border-radius:10px;padding:12px 14px;box-shadow:0 1px 3px rgba(0,0,0,.06)\">' +\n"
        "      '<div style=\"display:flex;align-items:center;gap:6px;margin-bottom:8px\"><span style=\"width:8px;height:8px;border-radius:50%;background:#1E40AF;display:inline-block\"></span><span style=\"font-size:13px;font-weight:700;color:#1E40AF\">\\u5168\\u90e8\\u7f16\\u5bfc</span></div>' +\n"
        "      '<div style=\"display:grid;grid-template-columns:repeat(4,1fr);gap:6px\">' + cellHtml + '</div></div>';\n"
        "  }\n"
        "  const _selDates4 = (window.DateBar"
    )

    # 五率卡片：整卡替换（旧模板只剩一张高潜成交率卡，扩成五张）
    js['person_cards'] = js['person_cards'].replace(
        '''        <div style="background:#EFF6FF;border-radius:6px;padding:7px 9px">\n          <div style="font-size:10px;color:#94A3B8;margin-bottom:1px">高潜成交率<span class="help-tip" data-tip="高潜成交率 = 深转>0 的素材数 ÷ 该编导总素材数；按名称基础名去重；跟随顶部日期筛选"></span></div>\n          <div class="order-rate-value" style="font-size:13px;font-weight:700;color:#1E40AF;font-family:monospace" data-tip="${orderTipOf(p)}">${orderRateOf(p)}</div>\n          <div style="font-size:10px;color:#64748B;margin-top:1px;font-family:monospace">${orderFractionOf(p)}</div>\n        </div>''',
        '''        <div style="background:#F8FAFC;border-radius:6px;padding:7px 9px">\n          <div style="font-size:10px;color:#94A3B8;margin-bottom:1px">转化成交率<span class="help-tip" data-tip="转化成交率 = 转化>0素材数 ÷ 产出投放素材数（基础名去重）"></span></div>\n          <div class="order-rate-value" style="font-size:13px;font-weight:700;color:#1E40AF;font-family:monospace" data-tip="${frTip(p,'open')}">${frRate(p,'open')}</div>\n          <div style="font-size:10px;color:#64748B;margin-top:1px;font-family:monospace">${frFrac(p,'open')}</div>\n        </div>\n        <div style="background:#F5F3FF;border-radius:6px;padding:7px 9px">\n          <div style="font-size:10px;color:#94A3B8;margin-bottom:1px">高潜成交率（转化）<span class="help-tip" data-tip="高潜成交率（转化） = 深转>0素材数 ÷ 转化>0素材数（基础名去重）"></span></div>\n          <div class="order-rate-value" style="font-size:13px;font-weight:700;color:#8B5CF6;font-family:monospace" data-tip="${frTip(p,'order')}">${frRate(p,'order')}</div>\n          <div style="font-size:10px;color:#64748B;margin-top:1px;font-family:monospace">${frFrac(p,'order')}</div>\n        </div>\n        <div style="background:#EFF6FF;border-radius:6px;padding:7px 9px">\n          <div style="font-size:10px;color:#94A3B8;margin-bottom:1px">高潜成交率<span class="help-tip" data-tip="高潜成交率 = 深转>0素材数 ÷ 产出投放素材数（基础名去重）"></span></div>\n          <div class="order-rate-value" style="font-size:13px;font-weight:700;color:#D97706;font-family:monospace" data-tip="${frTip(p,'chulv')}">${frRate(p,'chulv')}</div>\n          <div style="font-size:10px;color:#64748B;margin-top:1px;font-family:monospace">${frFrac(p,'chulv')}</div>\n        </div>\n        <div style="background:#FFF7ED;border-radius:6px;padding:7px 9px">\n          <div style="font-size:10px;color:#94A3B8;margin-bottom:1px">高潜跑出率<span class="help-tip" data-tip="高潜跑出率 = 深转≥5单素材数 ÷ 产出投放素材数（基础名去重）"></span></div>\n          <div class="order-rate-value" style="font-size:13px;font-weight:700;color:#D97706;font-family:monospace" data-tip="${frTip(p,'run')}">${frRate(p,'run')}</div>\n          <div style="font-size:10px;color:#64748B;margin-top:1px;font-family:monospace">${frFrac(p,'run')}</div>\n        </div>\n        <div style="background:#FFFBEB;border-radius:6px;padding:7px 9px">\n          <div style="font-size:10px;color:#94A3B8;margin-bottom:1px">高潜跑出率（转化）<span class="help-tip" data-tip="高潜跑出率（转化） = 深转≥5单素材数 ÷ 转化>0素材数（基础名去重）"></span></div>\n          <div class="order-rate-value" style="font-size:13px;font-weight:700;color:#9A3412;font-family:monospace" data-tip="${frTip(p,'conv_run')}">${frRate(p,'conv_run')}</div>\n          <div style="font-size:10px;color:#64748B;margin-top:1px;font-family:monospace">${frFrac(p,'conv_run')}</div>\n        </div>'''
    )
    js['person_cards'] = js['person_cards'].replace(
        "if (!orderRateStats[p]) orderRateStats[p] = {total:0, order:0, seen:new Set(), orderNames:[]};",
        "if (!orderRateStats[p]) orderRateStats[p] = {total:0, order:0, open:0, seen:new Set(), orderNames:[]};"
    ).replace(
        """    if (!orderRateStats[p].seen.has(bn)) {
      orderRateStats[p].seen.add(bn);
      orderRateStats[p].total += 1;""",
        """    if (!orderRateStats[p].seen.has(bn)) {
      orderRateStats[p].seen.add(bn);
      orderRateStats[p].total += 1;
      if ((r.conversions || 0) > 0) orderRateStats[p].open += 1;"""
    )
    # ---- 明细表渲染补丁：转化成交率分母含无消耗素材（跟随全部子筛选，不筛消耗） ----
    js['table'] = js['table'].replace(
        '''  const filtered = (currentFilter === 'all' ? rows : rows.filter(r => r.person === currentFilter))
    .filter(r => r.spend > 0)
    .filter(r => currentAccountFilter === 'all' ? true : r.account === currentAccountFilter)
    .filter(r => currentType === 'all' ? true :
      currentType === 'tuwen' ? (r.is_tuwen && !r.is_ai) :
      currentType === 'ai' ? r.is_ai :
      (!r.is_tuwen && !r.is_ai))
    .filter(r => currentTag === 'all' ? true :
      currentTag === 'none' ? !r.tag :
      currentTag === 'keytest' ? r.is_key_test :
      (r.tag && r.tag.split(',').some(t => t.split('-')[0].trim() === currentTag)))
    .filter(r => currentVersion === 'all' ? true : r.version === currentVersion)
    .filter(r => produceDaySet.size === 0 ? true : produceDaySet.has(r.produce_day));''',
        '''  const filteredAll = (currentFilter === 'all' ? rows : rows.filter(r => r.person === currentFilter))
    .filter(r => currentAccountFilter === 'all' ? true : (r.account || '').split(' / ').includes(currentAccountFilter))
    .filter(r => currentType === 'all' ? true :
      currentType === 'tuwen' ? (r.is_tuwen && !r.is_ai) :
      currentType === 'ai' ? r.is_ai :
      (!r.is_tuwen && !r.is_ai))
    .filter(r => currentTag === 'all' ? true :
      currentTag === 'none' ? !r.tag :
      currentTag === 'keytest' ? r.is_key_test :
      (r.tag && r.tag.split(',').some(t => t.split('-')[0].trim() === currentTag)))
    .filter(r => currentVersion === 'all' ? true : r.version === currentVersion)
    .filter(r => produceDaySet.size === 0 ? true : produceDaySet.has(r.produce_day));
  const filtered = filteredAll.filter(r => r.spend > 0);'''
    )
    js['table'] = js['table'].replace(
        '  updatePersonOrderRates(sorted);',
        '  updatePersonOrderRates(filteredAll);'
    )

    # ---- 明细编导卡补丁：五率分母含无消耗素材（去掉 spend===0 早退） ----
    js['person_cards'] = js['person_cards'].replace(
        '''    if (r.spend === 0) return;
    if (r.is_ai) return;  // AI素材不计入编导''',
        '''    if (r.is_ai) return;  // AI素材不计入编导'''
    )

    # ---- 近3周页已改为自绘（PASS3W_JS），旧 js['pass'] 不再使用 ----

    # 旧 JS 里带 {{}} 占位符：替换 person_order
    person_cards_js = js['person_cards'].replace('{person_order_js}',
                                                  json.dumps(gdg.EDITORS + gdg.CUTTERS + ['外部', '其他'], ensure_ascii=False))

    # openVideoByName：优先按素材 ID 从 ID_URL_MAP 取链接
    js['open_video'] = js['open_video'].replace(
        '  const r = rows.find(x => id && x.id === id) || rows.find(x => x.name === name);',
        '  const r = rows.find(x => id && x.id === id) || rows.find(x => x.name === name);\n'
        '  if (r && ID_URL_MAP && ID_URL_MAP[r.id]) r.video_url = ID_URL_MAP[r.id];'
    )
    # mergedRows 多日合并：收集多个名称/账户（同 id 多名时全部显示，不只看一个）
    js['merged_rows'] = js['merged_rows'].replace(
        '        const key = r.id || r.name;',
        '        const key = r.id || r.name;'
    ).replace(
        '          map[key] = Object.assign({}, r);',
        '          map[key] = Object.assign({}, r);\n'
        '          map[key]._names = [r.name];\n'
        '          map[key]._accounts = r.account ? [r.account] : [];'
    ).replace(
        '        } else {\n'
        '          // 累加数值字段',
        '        } else {\n'
        '          if (!map[key]._names) map[key]._names = [map[key].name];\n'
        '          if (!map[key]._names.includes(r.name)) map[key]._names.push(r.name);\n'
        '          if (!map[key]._accounts) map[key]._accounts = map[key].account ? [map[key].account] : [];\n'
        '          if (r.account && !map[key]._accounts.includes(r.account)) map[key]._accounts.push(r.account);\n'
        '          // 累加数值字段'
    ).replace(
        '    return Object.values(map);',
        '    return Object.values(map).map(function(m) {\n'
        '      if (m._names && m._names.length > 1) m.name = m._names.join(" / ");\n'
        '      if (m._accounts && m._accounts.length > 1) m.account = m._accounts.join(" / ");\n'
        '      delete m._names; delete m._accounts;\n'
        '      if (ID_URL_MAP && ID_URL_MAP[m.id]) m.video_url = ID_URL_MAP[m.id];\n'
        '      return m;\n'
        '    });'
    )

    # ---- 公共注入 ----
    common = (
        f"const ALL_DATES = {json.dumps(all_dates, ensure_ascii=False)};\n"
        f"const DAY_SPEND = {json.dumps(day_spend, ensure_ascii=False)};\n"
        f"const PERSON_COLORS = {person_colors_json};\n"
        f"const PERSON_BG = {json.dumps(gdg.PERSON_BG, ensure_ascii=False)};\n"
        f"const OPEN_RATE_DATA = {json.dumps(build_open_rate_data(), ensure_ascii=False)};\n"
    )

    # ---------------- 总览页 ----------------
    kpi_html = _cut_html('<!-- KPI Cards -->', '<!-- 多日趋势折线图（仅多日时显示） -->')
    trend_html = _cut_html('<!-- 多日趋势折线图（仅多日时显示） -->', '<!-- 视频素材标签分析（卡片形式） -->')
    tagcard_html = _cut_html('<!-- 视频素材标签分析（卡片形式） -->',
                             '<!-- 卡审分析：投放账户推送素材池（仅视频，图文过审数据导不出） -->')
    channel_html = _cut_html('<!-- 渠道账户总览（渠道数据不进明细） -->', '<!-- KPI Cards -->')
    ls = gdg.compute_stats(detail_days[-1][1])
    kpi_vals = {
        'total_spend': f"{ls['total_spend']:,.2f}",
        'total_imp': f"{ls['total_imp']:,.0f}",
        'avg_ctr': f"{ls['avg_ctr']:.2f}%",
        'avg_cvr': f"{ls['total_conv']/ls['total_clicks']*100:.2f}%" if ls['total_clicks'] else '—',
        'total_conv': f"{ls['total_conv']:.0f}",
        'avg_cpa': f"{ls['avg_cpa']:.2f}",
        'total_gaoquan': f"{ls['total_gaoquan']:.0f}",
        'deep_rate': f"{ls['total_gaoquan']/ls['total_conv']*100:.1f}%" if ls['total_conv'] else '—',
        'material_count': str(len(detail_days[-1][1])),
    }
    # 只替换 KPI 块里的占位符（该块无其他花括号）
    for k, v in kpi_vals.items():
        kpi_html = kpi_html.replace('{' + k + '}', v)
    overview_body = f'''<div class="page">
{channel_html}{kpi_html}
{trend_html}
{tagcard_html}
  <!-- 素材生命周期（iframe 卡片，随日报一并发布） -->
  <div class="chart-card" style="margin-top:20px">
    <div class="section-title" style="margin-bottom:10px">📈 素材生命周期</div>
    <iframe src="素材周期表现.html" title="素材生命周期" loading="lazy"
      style="width:100%;height:900px;border:1px solid var(--border);border-radius:var(--radius);background:#fff"></iframe>
  </div>
</div>'''
    overview_data = common + (
        f"const DAY_STATS = {json.dumps(day_stats, ensure_ascii=False)};\n"
        f"const TAG_STATS_BY_DAY = {json.dumps(tag_stats_by_day, ensure_ascii=False)};\n"
        f"const TYPE_STATS_BY_DAY = {json.dumps(type_stats_by_day, ensure_ascii=False)};\n"
        f"const CHANNEL_SUMMARY = {json.dumps(channel_by_date, ensure_ascii=False)};\n"
        f"const COMPARE_DATA = {json.dumps({'trend': compare_data.get('trend', [])}, ensure_ascii=False)};\n"
    )
    overview_js = js['channel'] + OVERVIEW_JS + r"""
document.addEventListener('DOMContentLoaded', function(){
  DateBar.init(ALL_DATES, DAY_SPEND, [ALL_DATES[ALL_DATES.length-1]]);
  if (typeof Chart !== 'undefined') {
    // 趋势图跟随日期选择最后一天往前30天（与旧版一致）
    window._initTrend = function(){
      const idx = ALL_DATES.indexOf(DateBar.selected[DateBar.selected.length-1]);
      if (idx < 0) return;
      const end = ALL_DATES[idx];
      const trend = (COMPARE_DATA.trend || []).filter(t => t.date <= end).slice(-30);
      const labels = trend.map(t => t.date);
      const convData = trend.map(t => t.conv);
      const gqData = trend.map(t => t.gaoquan);
      const cpaData = trend.map(t => t.cpa);
      const deepRateData = trend.map(t => t.conv > 0 ? parseFloat((t.gaoquan/t.conv*100).toFixed(1)) : 0);
      if (window.trendChart) window.trendChart.destroy();
      window.trendChart = new Chart(document.getElementById('chartTrend'), {
        type: 'line',
        data: { labels, datasets: [
          { label:'转化数', data:convData, yAxisID:'y', borderColor:'#3B82F6', backgroundColor:'#3B82F620', borderWidth:2, pointRadius:4, fill:true, tension:0.3 },
          { label:'高潜成交', data:gqData, yAxisID:'y', borderColor:'#D97706', backgroundColor:'#D9770620', borderWidth:2, pointRadius:4, fill:true, tension:0.3 },
          { label:'CPA(¥)', data:cpaData, yAxisID:'yRight', borderColor:'#10B981', borderDash:[4,3], borderWidth:2, pointRadius:4, fill:false, tension:0.3 },
          { label:'深转率(%)', data:deepRateData, yAxisID:'yRight', borderColor:'#8B5CF6', borderDash:[2,4], borderWidth:2, pointRadius:4, fill:false, tension:0.3 },
        ]},
        options: { responsive:true, maintainAspectRatio:false, interaction:{mode:'index',intersect:false},
          plugins:{ legend:{display:true,position:'top',labels:{font:{size:11},boxWidth:12,padding:12}} }},
          scales:{ x:{grid:{color:'#F1F5F9'},ticks:{font:{size:11}}},
            y:{position:'left',grid:{color:'#F1F5F9'},ticks:{font:{size:11}}},
            yRight:{position:'right',grid:{drawOnChartArea:false},ticks:{font:{size:11}}} }
      });
    };
    window._onDates = function(dates){
      renderKpi(dates);
      renderChannel(dates);
      renderTagCards(dates);
      renderTypeCards(dates);
      window._initTrend();
    };
    window._onDates(DateBar.selected);
    window._initTrend();
  } else {
    window._onDates = function(dates){
      renderKpi(dates); renderChannel(dates); renderTagCards(dates); renderTypeCards(dates);
    };
    window._onDates(DateBar.selected);
  }
});
"""
    overview_html = _html_head('引导素材日报', 'index', latest_mmdd, css) + overview_body + _html_tail(overview_data, overview_js, pre_js=chart_js_code)

    # ---------------- 卡审页 ----------------
    kajian_data = common + (
        f"const REJECT_ANALYSIS = {json.dumps(reject_analysis, ensure_ascii=False)};\n"
        f"const TEST_AUDIT_ANALYSIS = {json.dumps(test_audit_analysis, ensure_ascii=False)};\n"
    )
    kajian_body = f'<div class="page">{kajian_html}</div>{modal_html}'
    kajian_js = js['kajian'] + js['rej_init'] + js['open_video'] + js['close_modal'] + r"""
// 卡审页无近3周容器，这三个函数留空壳（initRejectModules 会调用）
function updatePassWeekLabels(){}
function renderPassList(){}
function renderPassPersonCards(){}
window._onDates = function(dates){ setRejDates(dates); };
document.addEventListener('DOMContentLoaded', function(){
  DateBar.init(ALL_DATES, DAY_SPEND, [ALL_DATES[ALL_DATES.length-1]]);
  initRejectModules();
});
"""
    kajian_page = _html_head('卡审分析', 'kajian', latest_mmdd, css) + kajian_body + _html_tail(kajian_data, kajian_js)

    # ---------------- 跑出与时效页 ----------------
    timing_js_filled = TIMING_JS
    timing_js_filled = timing_js_filled.replace('{timing_js}', json.dumps(timing, ensure_ascii=False))
    timing_js_filled = timing_js_filled.replace('{person_colors_js}', person_colors_json)
    for k, v in TOOLTIPS.items():
        timing_js_filled = timing_js_filled.replace('{tooltip_' + k + '}', v)
    timing_html_block = f'''
  <!-- ⏱️ 内容素材转化时效（全历史，按产出日期筛选，不随总览页日期） -->
  <div class="chart-card" style="margin-top:20px">
    <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:10px;flex-wrap:wrap;gap:8px">
      <div class="section-title" style="margin:0">⏱️ 内容素材转化时效</div>
      <div style="display:flex;gap:6px" id="timingViewBtns">
        <button class="sort-btn active" onclick="setTView('detail',this)">明细</button>
        <button class="sort-btn" onclick="setTView('month',this)">月度对比</button>
      </div>
    </div>
    <div class="legend"><b>口径说明（模块置顶）：</b>本模块统计 <b>仅自投账户、有转化的素材</b>（全历史 {timing['range'][0][:2]}/{timing['range'][0][2:]}–{timing['range'][1][:2]}/{timing['range'][1][2:]}），
    每个素材取 <b>5 个首次节点</b>：产出日期（名称 MMDD 前缀，无前缀用首现日）、首次投放日、首次有效投放日（单日消耗&gt;¥25）、首次转化日、首次高潜日；
    三个间隔天数（天）：<b>产出→首转</b>、<b>产出→起量</b>、<b>起量→首转</b>（可为负）。无高潜素材：产出→起量、起量→首转与首高潜列显示「—」。
    <b>不随总览页日期筛选变化</b>，产出日期筛选在页面顶部顶栏。</div>
    <div id="timingSummary" style="display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin-bottom:12px"></div>
    <div id="timingAllCard" style="margin-bottom:12px"></div>
    <div id="timingDirector" style="display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin-bottom:12px"></div>
    <div id="timingHist" style="margin-bottom:12px"></div>
    <div class="t-filter-col" id="timingFilters">
      <div class="t-filter-row">
        <span class="filter-label">类型</span>
        <span id="timingTypeBtns" style="display:flex;gap:6px">
          <button class="sort-btn active" onclick="setTFilterType('all',this)">全部</button>
          <button class="sort-btn" onclick="setTFilterType('视频',this)">视频</button>
          <button class="sort-btn" onclick="setTFilterType('图文',this)">图文</button>
        </span>
      </div>
      <div class="t-filter-row">
        <span class="filter-label">编导</span>
        <span id="timingPersonBtns" style="display:flex;gap:6px">
          <button class="sort-btn active" onclick="setTFilterPerson('all',this)">全部</button>
          <button class="sort-btn" onclick="setTFilterPerson('小敏',this)">小敏</button>
          <button class="sort-btn" onclick="setTFilterPerson('瑞晨',this)">瑞晨</button>
          <button class="sort-btn" onclick="setTFilterPerson('嘉丽',this)">嘉丽</button>
          <button class="sort-btn" onclick="setTFilterPerson('雅迪',this)">雅迪</button>
          <button class="sort-btn" onclick="setTFilterPerson('其他',this)">其他</button>
        </span>
      </div>
      <div class="t-filter-row">
        <span class="filter-label">标签</span>
        <span id="timingTagBtns" style="display:flex;gap:6px">
          <button class="sort-btn active" onclick="setTFilterTag('all',this)">全部</button>
          <button class="sort-btn" onclick="setTFilterTag('A1',this)">A1</button>
          <button class="sort-btn" onclick="setTFilterTag('A2',this)">A2</button>
          <button class="sort-btn" onclick="setTFilterTag('A3',this)">A3</button>
          <button class="sort-btn" onclick="setTFilterTag('A4',this)">A4</button>
          <button class="sort-btn" onclick="setTFilterTag('none',this)">未标记</button>
        </span>
      </div>
    </div>
    <div id="timingDetailView">
      <div class="table-wrap" style="max-height:600px;overflow-y:auto">
        <table style="font-size:12px" id="timingTable">
          <thead><tr>
            <th data-col="name">素材名称</th><th>素材ID</th><th data-col="type">类型</th><th data-col="person">编导</th><th>标签</th>
            <th data-col="pd">产出日期<span class="help-tip" data-tip="{{tooltip_pd}}"></span></th>
            <th data-col="first">首次投放<span class="help-tip" data-tip="{{tooltip_first_day}}"></span></th>
            <th data-col="eff">有效投放<span class="help-tip" data-tip="{{tooltip_eff_day}}"></span></th>
            <th data-col="conv_day" class="sorted-desc">首次转化↓<span class="help-tip" data-tip="{{tooltip_conv_day}}"></span></th>
            <th data-col="gq_day">首次高潜<span class="help-tip" data-tip="{{tooltip_gq_day}}"></span></th>
            <th data-col="gap_pc">产出→首转<span class="help-tip" data-tip="{{tooltip_gap_pc}}"></span></th>
            <th data-col="gap_pe">产出→起量<span class="help-tip" data-tip="{{tooltip_gap_pe}}"></span></th>
            <th data-col="gap_ec">起量→首转<span class="help-tip" data-tip="{{tooltip_gap_ec}}"></span></th>
            <th data-col="spend">消耗</th><th data-col="conv">转化</th><th data-col="gq">高潜</th><th data-col="ctr">点击率</th><th data-col="cvr">转化率</th><th data-col="deep_rate">深转率</th><th data-col="wf">完播率</th><th data-col="w3">3秒播放率</th><th data-col="wd">平均播放时长</th><th>视频</th>
          </tr></thead>
          <tbody id="timingBody"></tbody>
        </table>
      </div>
      <div id="timingCount" style="font-size:11px;color:var(--text-muted);margin-top:6px"></div>
    </div>
    <div id="timingMonthView" style="display:none">
      <div class="legend"><b>月度对比：</b>按产出月份分组（组内按当前筛选），对比每月素材数、有高潜数、三个间隔的<b>均值</b>（天）。</div>
      <div class="table-wrap" style="max-height:400px;overflow-y:auto">
        <table style="font-size:12px">
          <thead><tr><th>产出月</th><th>素材数</th><th>有高潜</th><th>产出→首转均值</th><th>产出→起量均值</th><th>起量→首转均值</th></tr></thead>
          <tbody id="timingMonthBody"></tbody>
        </table>
      </div>
    </div>
  </div>'''
    timing_html_block = timing_html_block.replace('{tooltip_pd}', TOOLTIPS['pd']) \
        .replace('{tooltip_first_day}', TOOLTIPS['first_day']) \
        .replace('{tooltip_eff_day}', TOOLTIPS['eff_day']) \
        .replace('{tooltip_conv_day}', TOOLTIPS['conv_day']) \
        .replace('{tooltip_gq_day}', TOOLTIPS['gq_day']) \
        .replace('{tooltip_gap_pc}', TOOLTIPS['gap_pc']) \
        .replace('{tooltip_gap_pe}', TOOLTIPS['gap_pe']) \
        .replace('{tooltip_gap_ec}', TOOLTIPS['gap_ec'])
    # ---------------- 近3周跑出页（独立 tab） ----------------
    pass_data_inject = common + (
        f"const RECENT_PASS_ANALYSIS = {json.dumps(recent_pass_analysis, ensure_ascii=False)};\n"
    )
    pass_body = f'<div class="page">{PASS3W_BODY}</div>{modal_html}'
    # 近3周页完全自绘：不再引用旧 js['pass']（竖排4区块 + 环比对比表）
    pass3w_js = js['close_modal'] + PASS3W_JS
    pass3w_page = _html_head('近3周跑出', 'pass3w', latest_mmdd, css) + pass_body + _html_tail(pass_data_inject, pass3w_js)

    # ---------------- 内容素材转化时效页（独立 tab） ----------------
    timing_data_inject = common
    timing_body = f'<div class="page">{timing_html_block}</div>{modal_html}'
    timing_js = timing_js_filled + r"""
function closeModal(e) {
  if (e && e.target !== document.getElementById('videoModal') && !(e.currentTarget && e.currentTarget.classList && e.currentTarget.classList.contains('modal-close'))) return;
  document.getElementById('videoModal').classList.remove('open');
  document.getElementById('videoWrap').innerHTML = '';
  document.body.style.overflow = '';
}
document.addEventListener('keydown', e => { if (e.key === 'Escape') closeModal({target: document.getElementById('videoModal')}); });
// 时效页顶部没有全局日期行，DateBar 仍注入但无需 init；全局日期选择通过顶部导航切到其他页操作
// 时效页产出日期筛选面板
const TimingPd = {
  open(){
    const el = document.getElementById('timingPdPicker');
    if (!el) return;
    const show = el.style.display === 'none';
    if (show) {
      const pds = T.all_pds && T.all_pds.length ? T.all_pds : [];
      const haveSet = new Set(pds);
      // 月份范围：有产出数据的最小月~最大月（含当前月完整到月末）
      const months = [];
      let mn = 99, mx = 0;
      pds.forEach(d => { const m = parseInt(d.slice(0,2)); if (m < mn) mn = m; if (m > mx) mx = m; });
      for (let m = mn; m <= mx; m++) months.push(('0'+m).slice(-2));
      const daysInMonth = mm => {
        const m = parseInt(mm);
        // 2026 年
        const last = [0,31,28,31,30,31,30,31,31,30,31,30,31][m];
        const arr = [];
        for (let d = 1; d <= last; d++) arr.push(('0'+m).slice(-2) + ('0'+d).slice(-2));
        return arr;
      };
      el.innerHTML = months.map(mm => {
        const md = daysInMonth(mm);
        const haveMd = md.filter(d => haveSet.has(d));
        const allSel = haveMd.length && haveMd.every(d => tPdSet.has(d));
        return `<div style="margin-bottom:6px"><div style="font-size:11px;font-weight:700;color:#1E40AF;margin-bottom:4px">${parseInt(mm)}月
          <button class="sort-btn" style="font-size:10px;margin-left:6px" onclick="TimingPd.toggleMonth('${mm}')">${allSel?'取消全选':'全选'}</button></div>
          <div style="display:flex;gap:4px;flex-wrap:wrap">${md.map(d => {
            const sel = tPdSet.has(d);
            const has = haveSet.has(d);
            if (!has) {
              return `<button class="filter-btn" title="该日期暂无产出数据" style="font-size:10px;font-family:monospace;color:#C3CBD8;border-style:dashed;cursor:not-allowed;opacity:.55">${d.slice(2)}</button>`;
            }
            return `<button class="filter-btn${sel?' active':''}" style="font-size:10px;font-family:monospace${sel?';background:#1E40AF;color:#fff':';color:#64748B'}" onclick="toggleTPd('${d}')">${d.slice(2)}</button>`;
          }).join('')}</div></div>`;
      }).join('');
      el.style.display = 'block';
    } else el.style.display = 'none';
  },
  toggleMonth(mm){
    const pds = T.all_pds && T.all_pds.length ? T.all_pds : [];
    const days = pds.filter(d => d.startsWith(mm));
    const allSel = days.length && days.every(d => tPdSet.has(d));
    days.forEach(d => allSel ? tPdSet.delete(d) : tPdSet.add(d));
    renderTPdChips(); renderTimingAll();
    document.getElementById('timingPdPicker').style.display = 'none';
  }
};
// 表头排序绑定（时效表）
document.addEventListener('DOMContentLoaded', function(){
  const th = document.querySelectorAll('#timingTable thead th[data-col]');
  th.forEach(el => el.onclick = () => {
    const col = el.dataset.col;
    if (tSortCol === col) tSortAsc = !tSortAsc;
    else { tSortCol = col; tSortAsc = (col === 'name'); }
    document.querySelectorAll('#timingTable thead th').forEach(t => t.classList.remove('sorted-asc','sorted-desc'));
    el.classList.add(tSortAsc ? 'sorted-asc' : 'sorted-desc');
    renderTimingTable();
  });
});
"""
    timing_page = _html_head('内容素材转化时效', 'timing', latest_mmdd, css, hide_dates=True) + timing_body + _html_tail(timing_data_inject, timing_js)

    # ---------------- 编导明细页 ----------------
    # 明细页瘦身：ALL_ROWS_BY_DATE 只保留每天消耗>0 的行（明细表默认 filter(spend>0)）；
    # 视频链接只保留最新一天（历史天播放按钮本就用不到）；五率已走独立 OPEN_RATE_DATA。
    # 链接按素材 ID 配：ID_URL_MAP（每 id 取最新日期的链接），行数据瘦身不含 URL
    _id_url = {}
    for _lbl, _rows in all_rows_by_date.items():
        for r in _rows:
            _id = (r.get('id') or '').strip()
            _u = (r.get('video_url') or '').strip()
            if _id and _u:
                _id_url[_id] = _u  # 按日期顺序后写入的覆盖=最新
    _slim = {}
    for _lbl, _rows in all_rows_by_date.items():
        _keep = [{**r, 'video_url': ''} for r in _rows if (r.get('spend') or 0) > 0]
        _slim[_lbl] = _keep
    detail_data = common + (
        f"const ALL_ROWS_BY_DATE = {json.dumps(_slim, ensure_ascii=False)};\n"
        f"const ALL_ROWS = {json.dumps(_slim.get(latest_label, []), ensure_ascii=False)};\n"
        f"const ID_URL_MAP = {json.dumps(_id_url, ensure_ascii=False)};\n"
        f"const AUDIT_BY_DATE = {{}};\n"
        f"const AUDIT_DATA = {{}};\n"
    )
    detail_body = f'<div class="page">{person_html}{filter_html}{table_html}</div>{modal_html}'
    # renderTable 账户筛选：包含该账户即显示
    js['table'] = js['table'].replace(
        ".filter(r => currentAccountFilter === 'all' ? true : r.account === currentAccountFilter)",
        ".filter(r => currentAccountFilter === 'all' ? true : (r.account || '').split(' / ').includes(currentAccountFilter))"
    )
    # renderTable 前回填单日行的 URL（ID_URL_MAP）
    js['table'] = js['table'].replace(
        "function renderTable() {",
        "function renderTable() {\n"
        "  (window.currentRows || []).forEach(r => { if (ID_URL_MAP && ID_URL_MAP[r.id] && !r.video_url) r.video_url = ID_URL_MAP[r.id]; });"
    )
    detail_js = js['merge_audit'] + js['merged_rows'] + person_cards_js + js['table'] + js['open_video'] + js['close_modal'] + DETAIL_JS + r"""
document.addEventListener('DOMContentLoaded', function(){
  DateBar.init(ALL_DATES, DAY_SPEND, [ALL_DATES[ALL_DATES.length-1]]);
  // 表头排序
  document.querySelectorAll('#matTable thead th[data-col]').forEach(th => {
    th.onclick = function(){
      const col = this.dataset.col;
      if (sortCol === col) sortAsc = !sortAsc;
      else { sortCol = col; sortAsc = (col === 'name' || col === 'person'); }
      document.querySelectorAll('#matTable thead th').forEach(t => t.classList.remove('sorted-asc','sorted-desc'));
      this.classList.add(sortAsc ? 'sorted-asc' : 'sorted-desc');
      pageNum = 1;
      renderTable();
    };
  });
});
"""
    detail_page = _html_head('编导&素材明细', 'detail', latest_mmdd, css) + detail_body + _html_tail(detail_data, detail_js)

    # ---- 4. 写文件 ----
    names = {
        'index': f'引导素材每日分析_{latest_mmdd}.html',
        'kajian': '卡审分析.html',
        'pass3w': '近3周跑出.html',
        'timing': '内容素材转化时效.html',
        'detail': '编导&素材明细.html',
    }
    pages = {'index': overview_html, 'kajian': kajian_page, 'pass3w': pass3w_page,
             'timing': timing_page, 'detail': detail_page}
    written = []
    for key, html in pages.items():
        p = out_dir / names[key]
        p.write_text(html, encoding='utf-8')
        written.append(p)
    return written
