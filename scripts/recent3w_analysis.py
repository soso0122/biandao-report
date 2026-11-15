#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""近3周产出分析（聊天框用）

复用 generate_report_daily_guide.py 的近3周口径：
  - 窗口 = 最新数据日往前 21 天（闭区间），行过滤=产出日落窗口，指标=窗口内截断
  - 视频：任一版本「推送视频_」且从未卡审；图文：名称有日期前缀
  - 产出日：名称 MMDD 前缀优先（先剥「推送视频_」），无前缀用首现日
  - 按（编导, 基础名）一行聚合，渠道账户剔除

输出：
  1. 窗口概览（总消耗/转化/CPA/深转/出单数出单率，按编导）
  2. 池内素材明细表（按消耗降序，全部列出）
  3. 分层结论用分组（出单组 / 转化>5无深转 / 有转化 / 零转化）
用法：python3 scripts/recent3w_analysis.py
"""
import csv
import re
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from generate_report_daily_guide import (CHANNEL_ACCOUNTS, safe_float,
                                         base_material_name, clean_name, extract_version)

DATA_DIR = Path(__file__).resolve().parent.parent / 'data'
CORE4 = ['小敏', '瑞晨', '嘉丽', '雅迪']


def person_of(name):
    for p in CORE4:
        if p in name:
            return p
    return '其他'


def produce_day(name):
    nm = (name or '').strip()
    m = re.match(r'^(\d{2})(\d{2})[-—－]', nm)
    if not m and nm.startswith('推送视频_'):
        m = re.match(r'^(\d{2})(\d{2})[-—－]', nm[len('推送视频_'):])
    if not m:
        return ''
    mm, dd = int(m.group(1)), int(m.group(2))
    if not (1 <= mm <= 12 and 1 <= dd <= 31):
        return ''
    return f'{mm:02d}{dd:02d}'


def mmdd_to_date(mmdd):
    return date(2026, int(mmdd[:2]), int(mmdd[2:]))


def main():
    files = sorted(DATA_DIR.glob('引导加微每日数据-*.csv'))
    all_days = []
    for f in files:
        m = re.fullmatch(r'引导加微每日数据-(\d{4})', f.stem)
        if m:
            all_days.append(m.group(1))
    latest = all_days[-1]
    last_d = mmdd_to_date(latest)
    win_start_d = last_d - timedelta(days=20)  # 21天窗口
    win_days = []
    for mmdd in all_days:
        d = mmdd_to_date(mmdd)
        if win_start_d <= d <= last_d:
            win_days.append(mmdd)

    agg = {}
    order = []
    for f in files:
        m = re.fullmatch(r'引导加微每日数据-(\d{4})', f.stem)
        if not m:
            continue
        mmdd = m.group(1)
        in_win = mmdd in win_days
        with open(f, encoding='utf-8-sig') as fh:
            for r in csv.DictReader(fh):
                name = (r.get('视频名称') or '').strip()
                if not name:
                    continue
                if (r.get('账户id') or '').strip() in CHANNEL_ACCOUNTS:
                    continue
                typ = (r.get('素材类型') or '').strip()
                is_tuwen = (typ == '图文')
                bn = base_material_name(clean_name(name))
                p = person_of(name)
                key = (p, bn)
                if key not in agg:
                    agg[key] = {'names': [], 'name_set': set(), 'is_tuwen': is_tuwen,
                                'is_pushed': False, 'pd': '', 'pd_prefix': False,
                                'first': mmdd, 'rejected': False,
                                'spend': 0.0, 'conv': 0.0, 'gq': 0.0,
                                'imp': 0.0, 'click': 0.0, 'w3': 0.0, 'w5': 0.0,
                                'wf': 0.0, 'wd': 0.0, 'active': set()}
                    order.append(key)
                a = agg[key]
                if name.startswith('推送视频_'):
                    a['is_pushed'] = True
                if name not in a['name_set']:
                    a['name_set'].add(name)
                    a['names'].append(name)
                pdp = produce_day(name)
                if pdp and not a['pd']:
                    a['pd'] = pdp
                    a['pd_prefix'] = True
                if mmdd < a['first']:
                    a['first'] = mmdd
                if not is_tuwen and '不通过' in (r.get('审核建议') or ''):
                    a['rejected'] = True
                if not in_win:
                    continue
                sp = safe_float(r.get('消耗'))
                a['spend'] += sp
                a['conv'] += safe_float(r.get('转化数'))
                a['gq'] += safe_float(r.get('回访-高潜成交(计费时间)'))
                a['imp'] += safe_float(r.get('展示数'))
                a['click'] += safe_float(r.get('点击数'))
                a['w3'] += safe_float(r.get('3秒播放率')) or 0
                a['w5'] += safe_float(r.get('5秒播放率')) or 0
                qf = r.get('完播率(%)') if r.get('完播率(%)') not in (None, '') else r.get('完播率')
                a['wf'] += safe_float(qf) or 0
                a['wd'] += safe_float(r.get('平均单次播放时长')) or 0
                if sp > 0:
                    a['active'].add(mmdd)

    rows = []
    for key in order:
        a = agg[key]
        if a['is_tuwen']:
            if not a['pd_prefix']:
                continue
        else:
            if not a['is_pushed'] or a['rejected']:
                continue
        push_day = a['pd'] or a['first']
        # 行过滤：产出日必须落在窗口内（否则混入窗口外老素材，2026-10-25 踩过的坑）
        if mmdd_to_date(push_day) < win_start_d or mmdd_to_date(push_day) > last_d:
            continue
        rows.append({'person': key[0], 'name': ' / '.join(a['names']),
                     'names': a['names'], 'type': '图文' if a['is_tuwen'] else '视频',
                     'version': extract_version(a['names'][0]), 'push_day': push_day,
                     'spend': a['spend'], 'conv': a['conv'], 'gq': a['gq'],
                     'imp': a['imp'], 'click': a['click'],
                     'w3': a['w3'], 'w5': a['w5'], 'wf': a['wf'], 'wd': a['wd'],
                     'active': len(a['active'])})
    rows.sort(key=lambda x: -x['spend'])

    tot_sp = sum(r['spend'] for r in rows)
    tot_cv = sum(r['conv'] for r in rows)
    tot_gq = sum(r['gq'] for r in rows)
    print(f"=== 近3周跑出分析 ===")
    print(f"窗口: {win_start_d.strftime('%m-%d')} ~ {last_d.strftime('%m-%d')}（最新数据 {latest}，21天）")
    print(f"池内素材 {len(rows)} 条  总消耗 {tot_sp:,.0f}  转化 {tot_cv:.0f}  CPA {tot_sp/tot_cv if tot_cv else 0:.2f}  "
          f"深转 {tot_gq:.0f}  深转率 {tot_gq/tot_cv if tot_cv else 0:.1%}  "
          f"出单素材 {sum(1 for r in rows if r['gq']>0)} 条（出单率 {sum(1 for r in rows if r['gq']>0)/len(rows):.0%}）")
    print()
    by_p = {}
    for r in rows:
        a = by_p.setdefault(r['person'], {'n': 0, 'sp': 0.0, 'cv': 0.0, 'gq': 0.0, 'deal': 0})
        a['n'] += 1
        a['sp'] += r['spend']
        a['cv'] += r['conv']
        a['gq'] += r['gq']
        if r['gq'] > 0:
            a['deal'] += 1
    print("按编导：")
    for p in CORE4 + ['其他']:
        a = by_p.get(p)
        if not a:
            continue
        cr = a['cv'] / a['n']
        print(f"  {p:<3} 素材{a['n']:>3}条  消耗{a['sp']:>8,.0f}  转化{a['cv']:>5.0f}  CPA {a['sp']/a['cv'] if a['cv'] else 0:>6.2f}  "
              f"深转{a['gq']:>4.0f}  出单{a['deal']}/{a['n']} ({a['deal']/a['n']:.0%})")
    print()
    print("=== 明细（按消耗降序） ===")
    print(f"{'产出':>5} {'类型':<4} {'编导':<4} {'消耗':>8} {'点击率':>6} {'转化':>5} {'CPA':>7} {'深转':>4} {'深转率':>6} {'3秒':>6} {'5秒':>6} {'完播':>6} {'在投':>4}  名称")
    for r in rows:
        ctr = r['click'] / r['imp'] if r['imp'] else 0
        cpa = r['spend'] / r['conv'] if r['conv'] else 0
        dr = r['gq'] / r['conv'] if r['conv'] else 0
        w3 = r['w3'] / r['imp'] * 100 if r['imp'] else 0
        w5 = r['w5'] / r['imp'] * 100 if r['imp'] else 0
        wf = r['wf'] / r['imp'] * 100 if r['imp'] else 0
        print(f"{r['push_day']:>5} {r['type']:<4} {r['person']:<4} {r['spend']:>8,.0f} {ctr:>6.1%} {r['conv']:>5.0f} "
              f"{cpa:>7.2f} {r['gq']:>4.0f} {dr:>6.1%} {w3:>6.1f} {w5:>6.1f} {wf:>6.1f} {r['active']:>4}  {r['name'][:58]}")


if __name__ == '__main__':
    main()
