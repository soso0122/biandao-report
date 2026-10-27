#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
素材生命周期分析（千川信息流项目）
用法:
  python3 scripts/material_lifecycle_analysis.py

口径:
  - 消耗 > 0 的一天 = 该素材当天"在投"
  - 消耗 = 0 或当天不在库 = 当天"未投"
  - 深转 = 回访-高潜成交 > 0
  - 范围: 引导加微每日数据-*.csv 全部日期（主页素材排除，Ai 单列标记）

输出:
  reports/素材生命周期_每日明细.csv   在投日的逐日明细
  reports/素材生命周期_总结.csv       每个曾投素材的一生
"""
import csv, sys, re
from pathlib import Path
from datetime import datetime, timedelta
from collections import defaultdict

ROOT = Path(__file__).parent.parent
DATA = ROOT / 'data'
OUT  = ROOT / 'reports'

sys.path.insert(0, str(Path(__file__).parent))
from generate_report_daily_guide import load_csv, is_homepage, is_ai  # noqa: E402


def parse_date(mmdd: str) -> datetime:
    return datetime(2026, int(mmdd[:2]), int(mmdd[2:]))


def main():
    files = [f for f in sorted(DATA.glob('引导加微每日数据-*.csv'))
             if re.fullmatch(r'引导加微每日数据-\d{4}', f.stem)]
    if not files:
        print('找不到数据文件'); sys.exit(1)

    # 标签表
    label_map = {}
    lf = DATA / '历史打标.csv'
    if lf.exists():
        with open(lf, encoding='utf-8-sig') as f:
            for r in csv.DictReader(f):
                sid = (r.get('素材id') or '').strip()
                name = (r.get('视频名称') or '').strip()
                tag = (r.get('标签') or '').strip()
                if sid: label_map[sid] = tag
                if name: label_map[name] = tag

    # ---- 第一遍扫描：建立 名字→主素材id 映射（0827 等文件缺素材id列，按名字归并）----
    from collections import Counter as _Counter
    name_to_id = {}
    id_spend = _Counter()  # 每个 id 的累计消耗，用于同名撞车时选主
    for f in files:
        with open(f, encoding='utf-8-sig') as fh:
            for r in csv.DictReader(fh):
                name = (r.get('视频名称') or '').strip()
                sid = (r.get('素材id') or '').strip()
                if not sid:
                    continue
                try:
                    id_spend[sid] += float(str(r.get('消耗') or '0').replace(',', ''))
                except Exception:
                    pass
                for n in {name, name[5:] if name.startswith('推送视频_') else name}:
                    if not n:
                        continue
                    if n not in name_to_id:
                        name_to_id[n] = sid
                    elif id_spend[name_to_id[n]] < id_spend[sid]:
                        name_to_id[n] = sid

    def norm_key(name, sid, account):
        """归一化素材身份：优先用名字匹配到的主id，其次自带id，最后名字+账户"""
        if name in name_to_id:
            return name_to_id[name]
        if sid:
            return sid
        return f"{name}|{account}"

    mat_info = {}   # key -> 素材最新信息
    day_rows = []   # 每日明细
    seq = []        # (date_label, {key: {spend,conv,gq,...}})

    for f in files:
        mmdd = re.search(r'(\d{4})', f.stem).group(1)
        label = f"{mmdd[:2]}/{mmdd[2:]}"
        rows = load_csv(f)
        day_map = {}
        for r in rows:
            if r['_is_homepage']:  # 主页素材不是千川投放素材，排除
                continue
            name, sid = r['_name'], r['_id']
            tag = label_map.get(sid) or label_map.get(name)
            if not tag and name.startswith('推送视频_'):
                tag = label_map.get(name[len('推送视频_'):]) or ''
            key = norm_key(name, sid, r['_account'])
            if key not in day_map:
                day_map[key] = dict(spend=0.0, conv=0.0, gq=0.0, imp=0.0, click=0.0,
                                    name=name, person=r['_person'], is_tuwen=r['_is_tuwen'],
                                    is_ai=r['_is_ai'], tag=tag or '', account=r['_account'])
            d = day_map[key]
            d['spend'] += r['_消耗']; d['conv'] += r['_转化数']; d['gq'] += r['_高潜成交']
            d['imp'] += r['_展示数']; d['click'] += r['_点击数']
        seq.append((label, day_map))
        for key, d in day_map.items():
            info = dict(name=d['name'], person=d['person'], is_tuwen=d['is_tuwen'],
                        is_ai=d['is_ai'], tag=d['tag'], account=d['account'])
            mat_info.setdefault(key, info)
            # 用当天出现的行做信息兜底（同日多行已聚合）
    print(f'加载 {len(files)} 天：{seq[0][0]} ~ {seq[-1][0]}')

    # ---- 每日明细 ----
    for label, day_map in seq:
        for key, d in day_map.items():
            if d['spend'] <= 0:
                continue
            inf = mat_info[key]
            day_rows.append({
                '日期': label, '素材id': key if key.isdigit() or 'E' in key else '', '素材名称': d['name'],
                '人': d['person'], '类型': 'Ai' if d['is_ai'] else ('图文' if d['is_tuwen'] else '视频'),
                '标签': d['tag'], '账户': d['account'],
                '消耗': round(d['spend'], 2), '转化': d['conv'], '高潜成交': d['gq'],
                '深转状态': '有深转' if d['gq'] > 0 else '无深转',
            })

    # ---- 每素材生命周期 ----
    last_date = parse_date(seq[-1][0].replace('/', ''))
    first_date = parse_date(seq[0][0].replace('/', ''))

    life = []
    for key, inf in mat_info.items():
        days = {}
        for label, day_map in seq:
            d = day_map.get(key)
            days[label] = d if d else dict(spend=0.0, conv=0.0, gq=0.0)
        active = sorted(dt for dt, d in days.items() if d['spend'] > 0)
        if not active:
            continue  # 从未在投
        ever_gq = any(days[dt]['gq'] > 0 for dt in active)
        first_act, last_act = parse_date(active[0].replace('/', '')), parse_date(active[-1].replace('/', ''))
        span = (last_act - first_act).days + 1
        stop_events = 0
        one_day_gaps = 0  # 停1天（噪音，不计入真停投）
        max_gap = 0
        cur_gap = 0
        dt_cursor = first_act
        while dt_cursor <= last_act:
            lbl = dt_cursor.strftime('%m/%d')
            sp = days.get(lbl, {}).get('spend', 0)
            if sp <= 0:
                cur_gap += 1
                max_gap = max(max_gap, cur_gap)
                if cur_gap == 1:
                    one_day_gaps += 1
                elif cur_gap == 2:
                    stop_events += 1  # 连续停≥2天才算一次停投
            else:
                cur_gap = 0
            dt_cursor += timedelta(days=1)
        days_since_last = (last_date - last_act).days

        # 深转模式（在投天数≥2 才有"持续/消失"可言；单日素材单独归类）
        gq_flags = [1 if days[dt]['gq'] > 0 else 0 for dt in active]
        gq_transitions = sum(1 for a, b in zip(gq_flags, gq_flags[1:]) if a != b)
        if not ever_gq:
            gq_mode = '从未有深转'
        elif len(active) == 1:
            gq_mode = '仅投一天(有深转)'
        elif gq_flags[0] == 1 and gq_flags[-1] == 1 and gq_transitions == 0:
            gq_mode = '持续有深转'
        elif gq_flags[0] == 0 and gq_flags[-1] == 1:
            gq_mode = '后来才有深转'
        elif gq_flags[0] == 1 and gq_flags[-1] == 0:
            gq_mode = '以前有深转现在没有'
        else:
            gq_mode = '深转时有时无'

        # 投放模式（停投间隔≥2天才算真停；停1天视为平台放量噪音）
        if len(active) == 1:
            run_mode = '试投一天即停'
        elif days_since_last == 0 and stop_events == 0 and len(active) >= 5:
            run_mode = '持续在跑'
        elif days_since_last == 0 and stop_events >= 1:
            run_mode = '波动投放中'
        elif days_since_last <= 3:
            run_mode = '近期刚停'
        elif stop_events >= 1:
            run_mode = '停投后复投又停'
        else:
            run_mode = '连续投放后停投'

        tot_spend = sum(days[dt]['spend'] for dt in active)
        tot_conv = sum(days[dt]['conv'] for dt in active)
        tot_gq = sum(days[dt]['gq'] for dt in active)
        # 深转消失信号：≥2个在投日，曾出现深转，且此后连续≥3个在投日无深转（收紧，排除正常波动）
        gq_ever_flag = [1 if days[dt]['gq'] > 0 else 0 for dt in active]
        gq_lost_after_peak = False
        if len(active) >= 2 and 1 in gq_ever_flag:
            peak_idx = gq_ever_flag.index(1)
            tail = gq_ever_flag[peak_idx:]
            if len(tail) >= 3 and sum(tail[-3:]) == 0:
                gq_lost_after_peak = True

        life.append({
            '素材id': key if (key.isdigit() or 'E' in key) else '',
            '素材名称': inf['name'], '人': inf['person'],
            '类型': 'Ai' if inf['is_ai'] else ('图文' if inf['is_tuwen'] else '视频'),
            '标签': inf['tag'], '账户': inf['account'],
            '首投日期': active[0], '末投日期': active[-1],
            '在投天数': len(active), '时间跨度': span,
            '停投次数(≥2天)': stop_events, '停1天次数': one_day_gaps,
            '最长连续停投': max_gap, '已停天数': days_since_last,
            '总消耗': round(tot_spend, 2), '总转化': int(tot_conv), '总高潜': int(tot_gq),
            '深转模式': gq_mode, '深转消失信号': '是' if gq_lost_after_peak else '',
            '投放模式': run_mode,
        })

    life.sort(key=lambda x: -x['总消耗'])

    OUT.mkdir(exist_ok=True)
    d1 = OUT / '素材生命周期_每日明细.csv'
    with open(d1, 'w', newline='', encoding='utf-8-sig') as f:
        w = csv.DictWriter(f, fieldnames=list(day_rows[0].keys()))
        w.writeheader(); w.writerows(day_rows)
    d2 = OUT / '素材生命周期_总结.csv'
    with open(d2, 'w', newline='', encoding='utf-8-sig') as f:
        w = csv.DictWriter(f, fieldnames=list(life[0].keys()))
        w.writeheader(); w.writerows(life)

    print(f'每日明细 {len(day_rows)} 行 → {d1.name}')
    print(f'素材总结 {len(life)} 个 → {d2.name}')

    # ---- 看片清单（视频素材优先看什么）----
    videos = [x for x in life if x['类型'] == '视频']
    p0, p1, p2, p3, skip, plan = [], [], [], [], [], []
    for r in videos:
        spend = float(r['总消耗']); gq = int(r['总高潜'])
        mode = r['深转模式']; run = r['投放模式']
        if mode == '仅投一天(有深转)':
            p0.append(r)  # 疑似停错：一天出了深转却被停
        elif mode == '以前有深转现在没有':
            p0.append(r)  # 真·深转消失，内容衰减嫌疑最大
        elif mode in ('深转时有时无', '后来才有深转'):
            p1.append(r)
        elif gq == 0 and spend >= 200:
            p2.append(r)
        elif run == '试投一天即停' and spend >= 10:
            p3.append(r)
        else:
            skip.append(r)
    watch_rows = []
    for pri, lst in [('P0', p0), ('P1', p1), ('P2', p2), ('P3', p3), ('跳过', skip)]:
        for r in sorted(lst, key=lambda x: -float(x['总消耗'])):
            watch_rows.append({
                '看片优先级': pri, '素材名称': r['素材名称'], '人': r['人'], '标签': r['标签'],
                '首投': r['首投日期'], '末投': r['末投日期'], '在投天数': r['在投天数'],
                '总消耗': r['总消耗'], '总转化': r['总转化'], '总高潜': r['总高潜'],
                '深转模式': r['深转模式'], '投放模式': r['投放模式'],
            })
    d3 = OUT / '看片清单_视频素材.csv'
    with open(d3, 'w', newline='', encoding='utf-8-sig') as f:
        w = csv.DictWriter(f, fieldnames=list(watch_rows[0].keys()))
        w.writeheader(); w.writerows(watch_rows)
    print(f'看片清单 {len(watch_rows)} 行 → {d3.name}')
    print(f'  P0 深转消失/疑似停错 {len(p0)} | P1 深转波动 {len(p1)} | P2 花钱多零深转 {len(p2)} | P3 浅投即停 {len(p3)} | 跳过 {len(skip)}')

    # ---- 汇总统计（供文字总结）----
    from collections import Counter
    run_mode_cnt = Counter(x['投放模式'] for x in life)
    gq_mode_cnt = Counter(x['深转模式'] for x in life)
    now_active = sum(1 for x in life if x['已停天数'] == 0)
    print('\n== 投放模式分布 ==')
    for m, c in run_mode_cnt.most_common():
        print(f'  {m}: {c}')
    print('== 深转模式分布 ==')
    for m, c in gq_mode_cnt.most_common():
        print(f'  {m}: {c}')
    print(f'\n曾投素材: {len(life)}   当前在投: {now_active}')
    total_spend_all = sum(x['总消耗'] for x in life)
    print(f'总消耗: ¥{total_spend_all:,.0f}')
    # 持续在跑 vs 其他 的标签分布
    def tag_first(x):
        return (x['标签'] or '未标记').split('-')[0]
    cont = [x for x in life if x['投放模式'] == '持续在跑']
    stop = [x for x in life if x['投放模式'] in ('试投一天即停', '连续投放后停投')]
    print(f'\n持续在跑 {len(cont)} 个，标签分布: {Counter(tag_first(x) for x in cont)}')
    print(f'停投类 {len(stop)} 个，标签分布: {Counter(tag_first(x) for x in stop)}')
    print(f'持续在跑 类型: {Counter(x["类型"] for x in cont)}')
    print(f'停投类 类型: {Counter(x["类型"] for x in stop)}')
    print(f'持续在跑 人均: {Counter(x["人"] for x in cont)}')
    # 复投素材总量
    fubo = [x for x in life if x['停投次数(≥2天)'] >= 1]
    print(f'\n有停投复投记录的素材(≥2天): {len(fubo)}')
    # 深转消失的
    lost = [x for x in life if x['深转模式'] == '以前有深转现在没有']
    gain = [x for x in life if x['深转模式'] == '后来才有深转']
    print(f'以前有深转现在没有: {len(lost)}   后来才有深转: {len(gain)}')

    # 逐日活跃素材数与总消耗（判断停投是全局性还是素材个体性）
    print('\n== 逐日活跃素材数/总消耗 ==')
    for label, day_map in seq:
        act = sum(1 for d in day_map.values() if d['spend'] > 0)
        sp = sum(d['spend'] for d in day_map.values())
        print(f'  {label}: 活跃{act}  消耗¥{sp:,.0f}')


if __name__ == '__main__':
    main()
