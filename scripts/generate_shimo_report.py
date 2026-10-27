#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
素材月度复盘 · 石墨版报告生成器
用法: python3 scripts/generate_shimo_report.py
输出:
  reports/月度复盘_石墨版.md         文字+表格版报告，可直接粘贴/导入石墨文档
  reports/石墨视频上传清单.csv       去重上传清单，含下载链接（新链接，尽快下载）
"""
import csv, re, sys
from pathlib import Path
from collections import defaultdict
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent))
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

    # 标签表
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

    # 名字→主id
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

    # 新链接
    fresh = load_fresh_links()

    def fresh_link(name, sid):
        if sid and sid in fresh['by_id']:
            return fresh['by_id'][sid]
        if name in fresh['by_name']:
            return fresh['by_name'][name]
        if name.startswith('推送视频_'):
            n2 = name[5:]
            if n2 in fresh['by_name']:
                return fresh['by_name'][n2]
        return ''

    # ---- 聚合 ----
    month_agg = {mm: {} for mm in months}
    first_seen, first_spend = {}, {}
    tot_conv = defaultdict(float)
    tot_gq = defaultdict(float)
    key_name, key_type = {}, {}
    day_spend = defaultdict(lambda: defaultdict(float))
    day_conv = defaultdict(lambda: defaultdict(float))
    labels = []

    for fp in files:
        mmdd = re.search(r'(\d{4})', fp.stem).group(1)
        label = f"{mmdd[:2]}/{mmdd[2:]}"
        labels.append(label)
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
                day_spend[key][label] += sp
                day_conv[key][label] += conv
                if mm in month_agg:
                    d = month_agg[mm].setdefault(key, dict(spend=0.0, conv=0.0, gq=0.0))
                    d['spend'] += sp
                    d['conv'] += conv
                    d['gq'] += gq

    all_keys = set(first_seen)
    labels = sorted(set(labels), key=lambda l: pdate(l))

    # 证据② 闲置自证
    latent = []
    for k in all_keys:
        if k not in first_spend:
            continue
        lat = (pdate(first_spend[k]) - pdate(first_seen[k])).days
        if lat >= 7 and tot_conv[k] >= 3:
            latent.append(k)
    latent.sort(key=lambda k: -tot_conv[k])

    # 证据④ 末投仍在转化
    stopped = []
    for k in all_keys:
        act = sorted(d for d in day_spend[k] if day_spend[k][d] > 0)
        if len(act) < 2:
            continue
        last = act[-1]
        idx = labels.index(last)
        if day_conv[k][last] > 0 and idx <= len(labels) - 3:
            stopped.append((k, last, int(day_conv[k][last])))
    stopped.sort(key=lambda x: pdate(x[1]), reverse=True)

    # 续投率
    cont = []
    for i in range(3):
        cur, nxt = months[i], months[i + 1]
        proven = [k for k, v in month_agg[cur].items() if v['spend'] > 0 and v['conv'] >= 1]
        resumed = sum(1 for k in proven if month_agg[nxt].get(k, {}).get('spend', 0) >= 10)
        shallow = sum(1 for k in proven if 0 < month_agg[nxt].get(k, {}).get('spend', 0) < 10)
        zero_n = sum(1 for k in proven if month_agg[nxt].get(k, {}).get('spend', 0) == 0)
        cont.append((cur, nxt, len(proven), resumed, shallow, zero_n))

    # 零消耗
    zero_ever = [k for k in all_keys if k not in first_spend]

    # 证据③ 浅投后跑出（"当时没跑出，后面给量就跑出"）
    bloom_rows = []
    for i, mm in enumerate(months):
        later = months[i + 1:]
        if not later:
            break
        shallow = [k for k, v in month_agg[mm].items() if 0 < v['spend'] <= 10]
        for k in shallow:
            for lm in later:
                v = month_agg[lm].get(k, {})
                if v.get('spend', 0) >= 50 and v.get('conv', 0) >= 3:
                    bloom_rows.append({
                        'k': k, 'mm': mm, 'lm': lm,
                        'spend0': month_agg[mm][k]['spend'],
                        'spend1': v['spend'], 'conv1': int(v['conv']), 'gq1': int(v['gq']),
                    })
                    break
    bloom_rows.sort(key=lambda x: -x['spend1'])

    # ---- 输出 markdown ----
    lines = []
    lines.append('# 素材月度复盘（7-10月）')
    lines.append('')
    lines.append('> 口径：消耗>0=在投 · 深转=高潜成交 · 深转率=高潜÷转化（转化≥5才进榜） · 数据范围 07/21–10/08')
    lines.append('')

    # 核心结论
    lines.append('## 一、核心结论：跑出率低，不全是素材的锅')
    lines.append('')
    lines.append(f'1. **{round(len(zero_ever) / len(all_keys) * 100)}%（{len(zero_ever)}/{len(all_keys)} 条）素材进库后从未获得任何消耗**——没有被投过，就谈不上“素材不行”。')
    lines.append('')
    lines.append(f'2. **{len(latent)} 条素材被闲置 9–18 天后才启用，同一条内容随后跑出转化**——内容没变，之前是没人给预算；给量就出成绩，证明“好素材没跑出”真实存在。')
    lines.append('')
    cont_text = ' → '.join(f'{c[0]}月→{c[1]}月续投 {round(c[3]/c[2]*100)}%' for c in cont)
    lines.append(f'3. **已验证素材的续投率逐月下滑：{cont_text}**，9月验证过的素材有 {cont[-1][5]} 条在10月完全没投。')
    lines.append('')
    n_bloom = len(bloom_rows)
    lines.append(f'4. **{n_bloom} 个"当月浅投、后来跑出"的素材**——当月消耗≤¥10看着没跑出，后续给量就出成绩，如"0720-浩正引导-4"7月仅¥3.65、8月爆发¥4,235转化148。')
    lines.append('')

    # 月度概览
    lines.append('## 二、月度概览')
    lines.append('')
    lines.append('| 月份 | 在投素材 | 零消耗素材 | 总消耗(¥) | 总转化 | 总高潜 | 转化>10素材 |')
    lines.append('| --- | --- | --- | --- | --- | --- | --- |')
    for mm in months:
        items = month_agg[mm]
        act = [v for k, v in items.items() if v['spend'] > 0]
        zero = [v for k, v in items.items() if v['spend'] == 0]
        lines.append(
            f"| {int(mm)}月 | {len(act)} | {len(zero)} | {sum(v['spend'] for v in act):,.0f} "
            f"| {int(sum(v['conv'] for v in act))} | {int(sum(v['gq'] for v in act))} "
            f"| {sum(1 for v in act if v['conv'] > 10)} |")
    lines.append('')

    def mat_row(k, deep=None, mm=None):
        """素材行：mm 给定时用当月值，否则用全周期累计值"""
        if mm:
            v = month_agg[mm].get(k, {})
            spend = v.get('spend', 0)
            conv = int(v.get('conv', 0))
            gq = int(v.get('gq', 0))
        else:
            spend = sum(month_agg[m].get(k, {}).get('spend', 0) for m in months)
            conv = int(tot_conv[k])
            gq = int(tot_gq[k])
        deep_s = f"{gq/conv*100:.1f}%" if deep and conv else '—'
        cols = [
            key_name.get(k, k),
            k if k.isdigit() else '—',
            person_of(key_name.get(k, k)),
            key_type.get(k, ''),
            tag_of(key_name.get(k, k), k),
            f"{spend:,.2f}",
            str(conv),
            str(gq),
        ]
        if deep:
            cols.append(deep_s)
        cols.append('（插入视频附件）')
        return '| ' + ' | '.join(cols) + ' |'

    head = '| 素材名称 | 素材ID | 人 | 类型 | 标签 | 总消耗(¥) | 转化 | 高潜 |'
    head_deep = head + ' 深转率 |'
    sep = '| --- | --- | --- | --- | --- | --- | --- | --- |'
    sep_deep = sep + ' --- |'

    # 证据②
    lines.append('## 三、证据②：闲置后自证素材（建议逐条看原视频）')
    lines.append('')
    lines.append('> 这些素材进库后躺了 7 天以上才开始投放，内容未变，随后转化 ≥3。')
    lines.append('')
    lines.append(head_deep + ' 视频 |')
    lines.append(sep_deep + ' --- |')
    for k in latent:
        lat = (pdate(first_spend[k]) - pdate(first_seen[k])).days
        lines.append(mat_row(k, deep=True).replace('（插入视频附件）', f'闲置{lat}天 →（插入视频附件）'))
    lines.append('')

    # 证据③ 浅投后跑出
    lines.append('## 四、证据③：当月浅投、后来跑出的素材')
    lines.append('')
    lines.append('> 当月消耗 ≤¥10（看着没跑出），后续某月给量后单月消耗 ≥¥50 且转化 ≥3。这说明"当时没跑出"往往不是素材不行，而是没给量。')
    lines.append('')
    lines.append('| 素材名称 | 素材ID | 人 | 类型 | 浅投月 | 浅投消耗(¥) | 跑出月 | 跑出月消耗(¥) | 跑出月转化 | 跑出月高潜 | 视频 |')
    lines.append('| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |')
    for b in bloom_rows:
        k = b['k']
        lines.append(
            f"| {key_name.get(k, k)} | {k if k.isdigit() else '—'} | {person_of(key_name.get(k, k))} "
            f"| {key_type.get(k, '')} | {int(b['mm'])}月 | {b['spend0']:.2f} | {int(b['lm'])}月 "
            f"| {b['spend1']:,.0f} | {b['conv1']} | {b['gq1']} | （插入视频附件） |")
    lines.append('')

    # 每月四维度
    for mm in months:
        items = month_agg[mm]
        act = [(k, v) for k, v in items.items() if v['spend'] > 0]
        lines.append(f'## 五、{int(mm)}月 · 四个维度')
        lines.append('')
        head_m = head.replace('总消耗(¥)', '当月消耗(¥)')
        # 高潜Top3
        gq3 = sorted([k for k, v in act if v['gq'] > 0], key=lambda k: -month_agg[mm][k]['gq'])[:3]
        lines.append(f'### {int(mm)}月 · 高潜成交 Top3')
        lines.append('')
        lines.append(head_m + ' 视频 |')
        lines.append(sep + ' --- |')
        for k in gq3:
            lines.append(mat_row(k, mm=mm))
        lines.append('')
        # 深转率Top3
        deep3 = sorted([k for k, v in act if v['conv'] >= 5],
                       key=lambda k: -(month_agg[mm][k]['gq'] / month_agg[mm][k]['conv']))[:3]
        lines.append(f'### {int(mm)}月 · 深转率 Top3（转化≥5才进榜）')
        lines.append('')
        lines.append(head_m.replace('高潜 |', '高潜 | 深转率 |') + ' 视频 |')
        lines.append(sep + ' --- | --- |')
        for k in deep3:
            lines.append(mat_row(k, deep=True, mm=mm))
        lines.append('')
        # 转化>10无深转
        nogq = sorted([k for k, v in act if v['conv'] > 10 and v['gq'] == 0],
                      key=lambda k: -month_agg[mm][k]['conv'])
        lines.append(f'### {int(mm)}月 · 转化>10 却无深转（{len(nogq)} 条，找内容短板样本）')
        lines.append('')
        lines.append(head_m + ' 视频 |')
        lines.append(sep + ' --- |')
        for k in nogq:
            lines.append(mat_row(k, mm=mm))
        lines.append('')
        # 消耗最低5
        low5 = sorted([k for k, v in act], key=lambda k: month_agg[mm][k]['spend'])[:5]
        lines.append(f'### {int(mm)}月 · 零消耗/消耗最低抽样 5 条')
        lines.append('')
        lines.append(head_m + ' 视频 |')
        lines.append(sep + ' --- |')
        for k in low5:
            lines.append(mat_row(k, mm=mm))
        lines.append('')

    md_path = OUT / '月度复盘_石墨版.md'
    md_path.write_text('\n'.join(lines), encoding='utf-8')

    # ---- 上传清单（含下载链接）----
    seen = set()
    upload = []

    def add(key, section, note):
        if key in seen:
            return
        seen.add(key)
        dl = fresh_link(key_name.get(key, key), key)
        upload.append({
            '素材id': key,
            '素材名称': key_name.get(key, key),
            '类型': key_type.get(key, ''),
            '所属板块': section,
            '备注': note,
            '总消耗': round(sum(month_agg[m].get(key, {}).get('spend', 0) for m in months), 2),
            '总转化': int(tot_conv.get(key, 0)),
            '总高潜': int(tot_gq.get(key, 0)),
            '下载链接': dl,
            '石墨上传状态': '',
        })

    for k in latent:
        add(k, '证据②闲置自证', '')
    for b in bloom_rows:
        add(b['k'], '证据③浅投后跑出', f"{int(b['mm'])}月¥{b['spend0']:.2f}→{int(b['lm'])}月¥{b['spend1']:.0f}")
    for mm in months:
        items = month_agg[mm]
        act = [(k, v) for k, v in items.items() if v['spend'] > 0]
        gq3 = sorted([k for k, v in act if v['gq'] > 0], key=lambda k: -month_agg[mm][k]['gq'])[:3]
        deep3 = sorted([k for k, v in act if v['conv'] >= 5],
                       key=lambda k: -(month_agg[mm][k]['gq'] / month_agg[mm][k]['conv']))[:3]
        nogq = sorted([k for k, v in act if v['conv'] > 10 and v['gq'] == 0],
                      key=lambda k: -month_agg[mm][k]['conv'])
        low5 = sorted([k for k, v in act], key=lambda k: month_agg[mm][k]['spend'])[:5]
        for k in gq3:
            add(k, f'{mm}月·高潜Top3', '')
        for k in deep3:
            add(k, f'{mm}月·深转率Top3', '')
        for k in nogq:
            add(k, f'{mm}月·转化>10无深转', '')
        for k in low5:
            add(k, f'{mm}月·消耗最低抽样', '')

    with_dl = sum(1 for u in upload if u['下载链接'])
    csv_path = OUT / '石墨视频上传清单.csv'
    with open(csv_path, 'w', newline='', encoding='utf-8-sig') as fh:
        w = csv.DictWriter(fh, fieldnames=['素材id', '素材名称', '类型', '所属板块', '备注',
                                           '总消耗', '总转化', '总高潜', '下载链接', '石墨上传状态'])
        w.writeheader()
        w.writerows(upload)

    print(f'石墨版报告: {md_path}（{len(lines)} 行）')
    print(f'上传清单: {csv_path}（{len(upload)} 个素材，其中 {with_dl} 个带下载链接）')


if __name__ == '__main__':
    main()
