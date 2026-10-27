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

# 渠道账户：只出数据总览，不进明细分析
CHANNEL_ACCOUNTS = {'1873204791217159', '1873204789662083', '1872584956721257', '1869499299085324'}  # jl01-jl04
ACCOUNT_NAMES = {
    '1873128068752651': '高中-猿起武汉-自投9户-智擎',
    '1874565773248713': '【agent测试】高中-猿起武汉-自投8户',
    '1874565772131337': '【agent智擎】高中-猿起武汉-自投6户',
    '1873204791217159': '高中-渠道-jl02',
    '1873204789662083': '高中-渠道-jl03',
    '1872584956721257': '高中-渠道-JL04',
    '1869499299085324': '高中-渠道-JL01',
    '1873204790479944': '高中-猿起武汉-自投5户',
    '1870673884733577': '高中-猿起武汉-自投1户',
    '1869580643367964': '高中-猿起武汉-自投2户',
}
PERSON_COLORS = {
    '小敏': '#3B82F6', '嘉丽': '#8B5CF6', '瑞晨': '#10B981',
    '浩正': '#F59E0B', '雅迪': '#EC4899', '魏怡': '#EF4444',
    '婷玉': '#14B8A6', '其他': '#94A3B8', '外部': '#F97316', 'AI': '#6366F1',
}
PERSON_BG = {
    '小敏': '#EFF6FF', '嘉丽': '#F5F3FF', '瑞晨': '#ECFDF5',
    '浩正': '#FFFBEB', '雅迪': '#FDF2F8', '魏怡': '#FEF2F2',
    '婷玉': '#F0FDFA', '其他': '#F8FAFC', '外部': '#FFF7ED', 'AI': '#EEF2FF',
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

def is_ai(name):
    return name.strip().upper().startswith('AI')

def has_known_person(name):
    return any(p in name for p in EDITORS + CUTTERS)

def is_tuwen(name):
    return '图文' in name

def extract_tag_from_name(name):
    """从名称提取 A1/A2/A3/A4 标签"""
    tags = re.findall(r'A[1-4]', name)
    return ','.join(sorted(set(tags))) if tags else ''

def extract_version(name):
    """提取改版信息：0改/1改/2改/3改"""
    m = re.search(r'-(\d)改', name)
    if m:
        return f"{m.group(1)}改"
    if re.search(r'改|修改', name):
        return '1改'
    return '0改'

def extract_produce_day(name):
    """产出日期：名称开头的 MMDD 日期前缀（兼容 -—－）；无则空串"""
    m = re.match(r'^(\d{2})(\d{2})[-—－]', (name or '').strip())
    if not m:
        return ''
    mm, dd = int(m.group(1)), int(m.group(2))
    if not (1 <= mm <= 12 and 1 <= dd <= 31):
        return ''
    return f"{mm:02d}{dd:02d}"

def base_material_name(name):
    """基础名：去 .mp4 和 -N改/-改 后缀（多版本合并用）"""
    n = (name or '').strip()
    n = re.sub(r'\.mp4$', '', n)
    n = re.sub(r'-(\d)改$', '', n)
    n = re.sub(r'-改$', '', n)
    return n

# 全局标签字典（素材id → 标签），由 load_label_map 初始化
_LABEL_MAP = {}

def load_label_map(csv_path):
    """加载历史打标表到全局字典"""
    global _LABEL_MAP
    _LABEL_MAP = {}
    if not Path(csv_path).exists():
        return
    with open(csv_path, encoding='utf-8-sig') as f:
        for r in csv.DictReader(f):
            sid  = r.get('素材id', '').strip()
            name = r.get('视频名称', '').strip()
            tag  = r.get('标签', '').strip()
            if sid:  _LABEL_MAP[sid]  = tag
            if name: _LABEL_MAP[name] = tag

def get_label(row):
    """从打标字典获取标签，fallback 到名称提取"""
    sid  = row.get('_id', '')
    name = row.get('_name', '')
    tag  = _LABEL_MAP.get(sid) or _LABEL_MAP.get(name)
    # 如果没匹配到，去掉"推送视频_"前缀再查一次
    if not tag and name.startswith('推送视频_'):
        stripped = name[len('推送视频_'):]
        tag = _LABEL_MAP.get(stripped)
    if not tag:
        tag = extract_tag_from_name(name)
    return tag

# 全局：素材名称 → 真实账户id（用于修正被 Excel 转成科学计数法的账户列）
_NAME_TO_ACCOUNT = {}

# 科学计数法账户值 → 主要真实账户（按素材名称归属数量最多的账户；历史数据损坏，无法完美恢复）
_SCI_ACCOUNT_FALLBACK = {
    '1.86958E+15': '1869580643367964',
    '1.87067E+15': '1870673884733577',
    '1.8732E+15': '1873204790479944',
}
def load_name_account_map(csv_path):
    """扫描单个CSV建立 名称→账户id 映射（仅完整16位数字id参与）"""
    if not Path(csv_path).exists():
        return
    with open(csv_path, encoding='utf-8-sig') as f:
        for r in csv.DictReader(f):
            acc = (r.get('账户id') or '').strip()
            name = (r.get('视频名称') or '').strip()
            if re.fullmatch(r'\d{16,}', acc) and name:
                if name not in _NAME_TO_ACCOUNT:
                    _NAME_TO_ACCOUNT[name] = acc

def clean_name(name):
    return re.sub(r'\.mp4\.mp4$', '.mp4', name.strip())

# 全局：基础名/名称 → 首次出现日（MMDD），用于产出日期兜底（名称无日期前缀时）
_NAME_TO_FIRST_DAY = {}

def load_name_first_day_map(csv_path):
    """扫描单个CSV建立 基础名→首现日（MMDD） 映射（基础名无日期前缀时兜底用）"""
    if not Path(csv_path).exists():
        return
    m = re.search(r'(\d{4})', Path(csv_path).stem)
    mmdd = m.group(1) if m else ''
    with open(csv_path, encoding='utf-8-sig') as f:
        for r in csv.DictReader(f):
            name = (r.get('视频名称') or '').strip()
            if not name:
                continue
            bn = base_material_name(clean_name(name))
            if bn and bn not in _NAME_TO_FIRST_DAY:
                _NAME_TO_FIRST_DAY[bn] = mmdd

def load_csv(path):
    with open(path, encoding='utf-8-sig') as f:
        rows = list(csv.DictReader(f))
    valid = [r for r in rows if (r.get('视频名称') or '').strip()]
    for r in valid:
        name = r.get('视频名称', '')
        r['_name']        = clean_name(name)
        r['_id']          = r.get('素材id', '').strip()
        video_url         = r.get('视频链接', '').strip()
        mat_type          = r.get('素材类型', '')
        # 优先用"素材类型"列判断（merge_daily_csv.py 写入），fallback 到视频链接
        if mat_type:
            r['_is_tuwen'] = mat_type == '图文'
        else:
            r['_is_tuwen'] = len(video_url) < 10
        r['_is_external'] = is_external(name)
        r['_is_ai']       = is_ai(name)
        r['_person']      = ('AI'   if r['_is_ai'] else
                             '外部' if (is_external(name) or not has_known_person(name)) else
                             extract_person(name))
        r['_collab']      = extract_collab(name)
        _raw_account = (r.get('账户id') or '').strip() or (r.get('账户名称') or '').strip()
        # 科学计数法账户用素材名称修正为真实账户；修正失败用主导账户兜底
        if _raw_account and not re.fullmatch(r'\d{16,}', _raw_account):
            fixed = _NAME_TO_ACCOUNT.get(clean_name(name), '')
            if fixed:
                _raw_account = fixed
            else:
                _raw_account = _SCI_ACCOUNT_FALLBACK.get(_raw_account, _raw_account)
        r['_account']     = ACCOUNT_NAMES.get(_raw_account, _raw_account)
        r['_is_channel']  = _raw_account in CHANNEL_ACCOUNTS
        r['_tag']         = ''  # 由 main 里 load_label_map 后再填充
        r['_version']     = extract_version(name) if not r['_is_tuwen'] else ''
        # 产出日期：名称 MMDD- 前缀；无前缀用基础名首现日兜底
        _pd = extract_produce_day(clean_name(name))
        if not _pd:
            _pd = _NAME_TO_FIRST_DAY.get(base_material_name(clean_name(name)), '')
        r['_produce_day'] = _pd
        r['_is_key_test'] = ('-起' in clean_name(name))  # 重点测标记（名称含「-起」）
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
        r['_审核建议']   = (r.get('审核建议') or '').strip()
        r['_is_pushed']  = name.strip().startswith('推送视频_')
        # 播放质量列（千川 2026-10-22 起导出；缺列时为空，前端显示—）
        r['_q3']         = safe_float(r.get('3秒播放率'))
        r['_q5']         = safe_float(r.get('5秒播放率'))
        r['_qf']         = safe_float(r.get('完播率(%)') if r.get('完播率(%)') not in (None, '') else r.get('完播率'))
        r['_qd']         = safe_float(r.get('平均单次播放时长'))
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
        'total_clicks': tc,
        'avg_cpa': ts/tz if tz else 0,
        'avg_ctr': tc/ti*100 if ti else 0,
        'by_person': dict(by_person)
    }

def rows_to_json(rows, include_video_url=True):
    out = []
    for r in sorted(rows, key=lambda x: -x['_消耗']):
        out.append({
            'id': r['_id'],
            'name': r['_name'],
            'person': r['_person'],
            'account': r['_account'],
            'is_external': r['_is_external'],
            'is_tuwen': r['_is_tuwen'],
            'is_ai': r['_is_ai'],
            'collab': r['_collab'],
            'tag': r['_tag'],
            'version': r['_version'],
            'produce_day': r['_produce_day'],
            'is_key_test': r['_is_key_test'],
            'status': r['_投放情况'],
            'spend': r['_消耗'],
            'impressions': r['_展示数'],
            'clicks': r['_点击数'],
            'ctr': r['_点击率'],
            'conversions': r['_转化数'],
            # 单条素材转化率 = 转化数/点击数（百分比，无点击记 0）
            'cvr': (r['_转化数'] / r['_点击数'] * 100) if r['_点击数'] else 0,
            'cpa': r['_转化成本'],
            'gaoquan': r['_高潜成交'],
            # 单条素材深转率 = 高潜成交/转化数（百分比，未转化记 0）
            'deep_rate': (r['_高潜成交'] / r['_转化数'] * 100) if r['_转化数'] else 0,
            'cpm': r['_CPM'],
            'cpc': r['_CPC'],
            # 播放质量（有值>0 才显示，0=缺数据显示—）
            'q3': r['_q3'] if r['_q3'] > 0 else None,
            'q5': r['_q5'] if r['_q5'] > 0 else None,
            'qf': r['_qf'] if r['_qf'] > 0 else None,
            'qd': r['_qd'] if r['_qd'] > 0 else None,
            'video_url': r['_视频链接'] if include_video_url else '',
        })
    return out

def _load_history_series():
    """扫描 data/ 下全部每日 CSV，构建 {素材id: {mmdd: 当日聚合}}。

    聚合规则：同一天多账户行合并（消耗/转化/高潜求和）；卡审状态优先；
    渠道账户行跳过。用于卡审分析和近3周跑出表现（全历史视角）。
    """
    data_dir = Path(__file__).parent.parent / 'data'
    series = defaultdict(dict)
    for f in sorted(data_dir.glob('引导加微每日数据-*.csv')):
        m = re.fullmatch(r'引导加微每日数据-(\d{4})', f.stem)
        if not m:
            continue
        mmdd = m.group(1)
        with open(f, encoding='utf-8-sig') as fh:
            for r in csv.DictReader(fh):
                name = (r.get('视频名称') or '').strip()
                if not name:
                    continue
                raw_acc = (r.get('账户id') or '').strip()
                if raw_acc in CHANNEL_ACCOUNTS:
                    continue  # 渠道不进推送池分析
                sid = (r.get('素材id') or '').strip().lstrip('\t')
                if not sid:
                    continue
                adv = (r.get('审核建议') or '').strip()
                mat_type = (r.get('素材类型') or '').strip()
                day = series[sid].get(mmdd)
                if day is None:
                    series[sid][mmdd] = {
                        'name': clean_name(name), 'adv': adv,
                        'type': mat_type, 'url': (r.get('视频链接') or '').strip(),
                        'spend': safe_float(r.get('消耗')),
                        'conv': safe_float(r.get('转化数')),
                        'gq': safe_float(r.get('回访-高潜成交(计费时间)')),
                        'imp': safe_float(r.get('展示数')),
                        'click': safe_float(r.get('点击数')),
                        'q3': safe_float(r.get('3秒播放率')),
                        'q5': safe_float(r.get('5秒播放率')),
                        'qf': safe_float(r.get('完播率(%)') if r.get('完播率(%)') not in (None, '') else r.get('完播率')),
                        'qd': safe_float(r.get('平均单次播放时长')),
                        'person': extract_person(name),
                        'is_pushed': name.startswith('推送视频_'),
                        'accts': {ACCOUNT_NAMES.get(raw_acc, raw_acc)},
                    }
                else:
                    day['spend'] += safe_float(r.get('消耗'))
                    day['conv'] += safe_float(r.get('转化数'))
                    day['gq'] += safe_float(r.get('回访-高潜成交(计费时间)'))
                    day['imp'] += safe_float(r.get('展示数'))
                    day['click'] += safe_float(r.get('点击数'))
                    day['accts'].add(ACCOUNT_NAMES.get(raw_acc, raw_acc))
                    if name.startswith('推送视频_'):
                        day['is_pushed'] = True
                    if '不通过' in adv and '不通过' not in day['adv']:
                        day['adv'] = adv  # 卡审状态优先
                    elif adv and not day['adv']:
                        day['adv'] = adv
    # 链接刷新：data/视频库-新链接-*.csv 按素材id优先，其次名称（兼容去「推送视频_」前缀）
    try:
        sys.path.insert(0, str(Path(__file__).parent))
        from fresh_links import load_fresh_links
        fresh = load_fresh_links()
    except Exception:
        fresh = {'by_id': {}, 'by_name': {}}
    for sid, days in series.items():
        ordered = sorted(days.items())
        if not ordered:
            continue
        last = ordered[-1][1]
        name = last['name']
        new_url = (fresh['by_id'].get(sid) or fresh['by_name'].get(name)
                   or fresh['by_name'].get(name.replace('推送视频_', '', 1)))
        if new_url:
            last['url'] = new_url
    return series


def _latest_mmdd():
    data_dir = Path(__file__).parent.parent / 'data'
    dts = [f.stem[-4:] for f in data_dir.glob('引导加微每日数据-*.csv')
           if re.fullmatch(r'引导加微每日数据-\d{4}', f.stem)]
    return max(dts) if dts else ''


def _load_audit_verdict():
    """测试账户过审文件的最终判定：基础名 → 是否任一版本通过。

    业务规则：只有测试账户「审核通过」的素材才会被推送到投放账户；
    所以过审文件里全部版本都不通过的素材，不应计入投放账户推送池。
    返回 {基础名: bool}（True=至少一个版本通过）。
    """
    data_dir = Path(__file__).parent.parent / 'data'
    verdict = {}
    for f in sorted(data_dir.glob('*投放过审.csv')):
        with open(f, encoding='utf-8-sig') as fh:
            for r in csv.DictReader(fh):
                name = (r.get('视频名称') or '').strip()
                if not name or '图文' in name:
                    continue
                bn = base_material_name(clean_name(name))
                if not bn:
                    continue
                passed = (r.get('审核建议') or '').strip() == '审核通过'
                if passed:
                    verdict[bn] = True
                elif bn not in verdict:
                    verdict[bn] = False
    return verdict


def build_reject_analysis():
    """① 卡审分析：投放账户「推送视频_」素材池，按改版 × 分日/分周/总计。

    口径：
      - 推送池 = 素材id曾在任一天以「推送视频_」前缀出现（测试账户推送过来）
      - 仅测试账户审核通过的素材才会被推送 → 过审文件里从未通过的素材不进推送池
      - 卡审   = 任一天审核建议含「不通过」；状态单调（卡审后不回退）
      - 刚推送卡审 = 首次卡审日前消耗为0；用着用着卡审 = 卡审前已有消耗
      - 推送日   = 素材首次出现在每日数据的日期（近似）
    """
    series = _load_history_series()
    latest = _latest_mmdd()
    audit_verdict = _load_audit_verdict()  # 基础名 → 测试账户是否任一版本通过

    # 逐素材汇总（只看视频；图文过审数据导不出，用户确认不看）
    materials = []  # {id, name, version, first_day, first_rej_day, status, url}
    # 三维视图：{view: {bucket: {version: {pushed,rejected,immediate,inuse,ok}}}}
    by_view = {'day': defaultdict(lambda: defaultdict(lambda: {'pushed':0,'rejected':0,'immediate':0,'inuse':0,'ok':0})),
               'week': defaultdict(lambda: defaultdict(lambda: {'pushed':0,'rejected':0,'immediate':0,'inuse':0,'ok':0})),
               'total': defaultdict(lambda: {'pushed':0,'rejected':0,'immediate':0,'inuse':0,'ok':0})}
    # 标签视图（A1-A4）：{view: {bucket: {tag: {pushed,rejected,ok}}}}
    tag_views = {'day': defaultdict(lambda: defaultdict(lambda: {'pushed':0,'rejected':0,'ok':0})),
                 'week': defaultdict(lambda: defaultdict(lambda: {'pushed':0,'rejected':0,'ok':0})),
                 'total': defaultdict(lambda: {'pushed':0,'rejected':0,'ok':0})}
    VERSIONS = ['0改', '1改', '2改', '3改']

    def bump(stats, version, status):
        s = stats[version]
        s['pushed'] += 1
        if status:
            s[status] += 1
            if status in ('immediate', 'inuse'):
                s['rejected'] += 1

    for sid, days in series.items():
        ordered = sorted(days.items())
        if not ordered:
            continue
        first_mmdd = ordered[0][0]
        is_pushed = any(d['is_pushed'] for _, d in ordered)
        if not is_pushed:
            continue
        mat_type = ordered[-1][1]['type']
        if mat_type == '图文':
            continue  # 图文过审不看
        name = next((d['name'] for _, d in ordered if d['name']), '')
        # 业务规则：只有测试账户通过的素材才会推送到投放账户；
        # 过审文件里从未通过的素材不进推送池分母
        bn = base_material_name(clean_name(name))
        if bn in audit_verdict and not audit_verdict[bn]:
            continue
        version = extract_version(name)
        if version not in VERSIONS:
            continue  # 4改等不参与改版分析

        first_rej = next((mm for mm, d in ordered if '不通过' in d['adv']), None)
        status = 'ok'  # 推送后未卡审
        if first_rej:
            spend_before = sum(d['spend'] for mm, d in ordered if mm < first_rej)
            status = 'inuse' if spend_before > 0 else 'immediate'
        # 全历史出现的账户（去重、保序）
        accts = []
        for _, d in ordered:
            for a in sorted(d.get('accts') or []):
                if a not in accts:
                    accts.append(a)
        materials.append({
            'id': sid, 'name': name, 'version': version,
            'first_day': first_mmdd, 'first_rej_day': first_rej or '',
            'status': status, 'url': ordered[-1][1]['url'],
            'accounts': accts,
        })

        # 总计
        bump(by_view['total'], version, status)
        bump(by_view['total'], '全部', status)
        # 日桶
        bump(by_view['day'][first_mmdd], version, status)
        bump(by_view['day'][first_mmdd], '全部', status)
        # 周桶
        import datetime
        mm, dd = int(first_mmdd[:2]), int(first_mmdd[2:])
        dt = datetime.date(2026, mm, dd)
        wk = dt.isocalendar()[:2]
        w_key = f"{wk[0]}-W{wk[1]:02d}"
        bump(by_view['week'][w_key], version, status)
        bump(by_view['week'][w_key], '全部', status)

        # 标签统计（A1-A4，取名称中第一个标签）
        tags = re.findall(r'A[1-4]', name)
        if tags:
            tag = tags[0]
            def bump_tag(stats, st):
                s = stats[tag]
                s['pushed'] += 1
                if st == 'ok':
                    s['ok'] += 1
                elif st in ('immediate', 'inuse'):
                    s['rejected'] += 1
            bump_tag(tag_views['total'], status)
            bump_tag(tag_views['day'][first_mmdd], status)
            bump_tag(tag_views['week'][w_key], status)

    def bucket_to_obj(v):
        total = v['pushed']
        rej = v['rejected']
        ok = v['ok']
        return {
            'pushed': total, 'rejected': rej,
            'reject_rate': round(rej/total*100, 1) if total else 0,
            # 三个去向占比，分母都是推送数
            'immediate': v['immediate'], 'inuse': v['inuse'], 'ok': ok,
            'immediate_pct': round(v['immediate']/total*100, 1) if total else 0,
            'inuse_pct': round(v['inuse']/total*100, 1) if total else 0,
            'ok_pct': round(ok/total*100, 1) if total else 0,
        }

    def version_row(vmap):
        return {ver: bucket_to_obj(vmap.get(ver, {'pushed':0,'rejected':0,'immediate':0,'inuse':0,'ok':0}))
                for ver in VERSIONS + ['全部']}

    view_json = {
        'total': version_row(by_view['total']),
        'day': {k: version_row(v) for k, v in by_view['day'].items()},
        'week': {k: version_row(v) for k, v in by_view['week'].items()},
    }

    # 标签视图序列化：{tag: {pushed, ok, rejected, ok_rate, reject_rate}}
    def tag_bucket_to_obj(v):
        t = v['pushed']
        ok = v['ok']
        rej = v['rejected']
        return {
            'pushed': t, 'ok': ok, 'rejected': rej,
            'ok_rate': round(ok/t*100, 1) if t else 0,
            'reject_rate': round(rej/t*100, 1) if t else 0,
        }
    tag_view_json = {
        'total': {tag: tag_bucket_to_obj(v) for tag, v in tag_views['total'].items()},
        'day': {k: {tag: tag_bucket_to_obj(v) for tag, v in bucket.items()}
                for k, bucket in tag_views['day'].items()},
        'week': {k: {tag: tag_bucket_to_obj(v) for tag, v in bucket.items()}
                 for k, bucket in tag_views['week'].items()},
    }

    # 日→周映射（ISO 周，与 isocalendar 对齐）：覆盖数据全量日期范围（含无推送日期），
    # 供前端选中日期定位所在周（分周明细跟随多选）
    day_week_map = {}
    week_range_map = {}  # 周key → (周一MMDD, 周日MMDD)
    import datetime as _dt
    day_keys = sorted(by_view['day'].keys())
    if day_keys:
        d0 = _dt.date(2026, int(day_keys[0][:2]), int(day_keys[0][2:]))
        d1 = _dt.date(2026, int(day_keys[-1][:2]), int(day_keys[-1][2:]))
        cur = d0
        while cur <= d1:
            k = f"{cur.month:02d}{cur.day:02d}"
            iso = cur.isocalendar()
            wk = f"{iso[0]}-W{iso[1]:02d}"
            day_week_map[k] = wk
            # 该周周一/周日
            monday = cur - _dt.timedelta(days=cur.weekday())
            sunday = monday + _dt.timedelta(days=6)
            if wk not in week_range_map:
                week_range_map[wk] = (f"{monday.month:02d}{monday.day:02d}",
                                      f"{sunday.month:02d}{sunday.day:02d}")
            cur += _dt.timedelta(days=1)

    # 推送素材去向清单（按推送日倒序）
    materials.sort(key=lambda x: (x['first_day'], x['name']), reverse=True)
    return {'views': view_json, 'tag_views': tag_view_json, 'materials': materials,
            'latest': latest, 'version_order': VERSIONS, 'day_week_map': day_week_map,
            'week_range_map': week_range_map}


def build_test_audit_analysis():
    """测试账户过审分析：过审文件（*-投放过审.csv）按改版 × 日期统计。

    口径：
      - 按素材id去重（同id跨文件重复时取首现日期与建议）
      - 状态桶：通过 / 不通过 / 生态风险 / 未知
      - 日期 = 过审文件对应日期（文件命名 MMDD）
      - 图文跳过；4改不显示
    """
    import datetime as _dt
    data_dir = Path(__file__).parent.parent / 'data'
    VERSIONS = ['0改', '1改', '2改', '3改']

    def classify(adv):
        adv = (adv or '').strip()
        if adv == '审核通过':
            return 'pass'
        if adv == '生态风险判定不通过':
            return 'eco'
        if '不通过' in adv:
            return 'fail'
        return 'unknown'

    # id → (first_mmdd, status, name, version)；同名素材按「去改版后缀的基础名」合并成一条
    # 合并规则：同一条素材的多个版本（0改/1改/2改/3改），任一版本通过即整条算通过；
    # 记 基础名 → 合并记录（取各版本中"最好"的状态：pass > eco > fail > unknown）
    STATUS_RANK = {'pass': 3, 'eco': 2, 'fail': 1, 'unknown': 0}

    def base_name(name):
        """去掉改版后缀（-N改/-改）得到基础名；.mp4 在改版后缀后，需先去扩展名"""
        n = name.strip()
        n = re.sub(r'\.mp4$', '', n)
        n = re.sub(r'-(\d)改$', '', n)
        n = re.sub(r'-改$', '', n)
        return n

    first_seen = {}       # sid → record（原始去重，按id）
    for f in sorted(data_dir.glob('*投放过审.csv')):
        m = re.fullmatch(r'(\d{4})投放过审', f.stem)
        if not m:
            continue
        mmdd = m.group(1)
        with open(f, encoding='utf-8-sig') as fh:
            for r in csv.DictReader(fh):
                name = (r.get('视频名称') or '').strip()
                if not name:
                    continue
                if '图文' in name:
                    continue  # 图文不看
                sid = (r.get('素材id') or '').strip().lstrip('\t')
                if not sid:
                    continue
                if sid in first_seen:
                    continue
                ver = extract_version(name)
                if ver not in VERSIONS:
                    continue
                first_seen[sid] = (mmdd, classify(r.get('审核建议')), name, ver)

    # 按基础名合并：基础名 → {'mmdd','status','name','version','aliases'}
    merged = {}
    for sid, (mmdd, status, name, ver) in first_seen.items():
        bn = base_name(name)
        rec = merged.get(bn)
        if rec is None:
            merged[bn] = {'mmdd': mmdd, 'status': status, 'name': name, 'version': ver,
                          'aliases': [name]}
        else:
            if name not in rec['aliases']:
                rec['aliases'].append(name)
            # 状态取更优（任一版本通过 → pass）；日期跟随最优状态的版本
            if STATUS_RANK[status] > STATUS_RANK[rec['status']]:
                rec['status'] = status
                rec['name'] = name
                rec['version'] = ver
                rec['mmdd'] = mmdd
            elif STATUS_RANK[status] == STATUS_RANK[rec['status']] and mmdd < rec['mmdd']:
                rec['mmdd'] = mmdd

    def tag_of(rec):
        """标签提取：打标表优先（任一版本别名），名称正则兜底"""
        aliases = [rec['name']] + [a for a in rec['aliases'] if a != rec['name']]
        for n in aliases:
            lbl = _LABEL_MAP.get(n) or ''
            t = re.search(r'A[1-4]', lbl or '')
            if t:
                return t.group(0)
        for n in aliases:
            t = re.search(r'A[1-4]', n)
            if t:
                return t.group(0)
        return None

    # 视图：{view: {bucket: {version: {submitted,pass,fail,eco,unknown}}}}
    # 改版维度按版本原样计数（看改到第几次能过，不去重）
    by_view = {
        'day': defaultdict(lambda: defaultdict(lambda: {'submitted':0,'pass':0,'fail':0,'eco':0,'unknown':0})),
        'week': defaultdict(lambda: defaultdict(lambda: {'submitted':0,'pass':0,'fail':0,'eco':0,'unknown':0})),
        'total': defaultdict(lambda: {'submitted':0,'pass':0,'fail':0,'eco':0,'unknown':0}),
    }
    # 合计/标签维度按基础名合并后计数（任一版本通过即通过）
    all_view = {
        'day': defaultdict(lambda: {'submitted':0,'pass':0,'fail':0,'eco':0,'unknown':0}),
        'week': defaultdict(lambda: {'submitted':0,'pass':0,'fail':0,'eco':0,'unknown':0}),
        'total': {'submitted':0,'pass':0,'fail':0,'eco':0,'unknown':0},
    }
    # 标签视图（A1-A4）：{view: {bucket: {tag: {submitted,pass,fail,eco,unknown}}}}
    tag_views = {
        'day': defaultdict(lambda: defaultdict(lambda: {'submitted':0,'pass':0,'fail':0,'eco':0,'unknown':0})),
        'week': defaultdict(lambda: defaultdict(lambda: {'submitted':0,'pass':0,'fail':0,'eco':0,'unknown':0})),
        'total': defaultdict(lambda: {'submitted':0,'pass':0,'fail':0,'eco':0,'unknown':0}),
    }

    def _wk(mmdd):
        mm, dd = int(mmdd[:2]), int(mmdd[2:])
        wk = _dt.date(2026, mm, dd).isocalendar()
        return f"{wk[0]}-W{wk[1]:02d}"

    def bump(stats, v, st):
        s = stats[v]
        s['submitted'] += 1
        s[st] += 1

    # 改版维度：每个版本独立计数
    for sid, (mmdd, status, name, ver) in first_seen.items():
        bump(by_view['total'], ver, status)
        bump(by_view['day'][mmdd], ver, status)
        bump(by_view['week'][_wk(mmdd)], ver, status)

    # 合计/标签：按基础名合并后计数
    materials = []
    for bn, rec in merged.items():
        mmdd, status, name, ver = rec['mmdd'], rec['status'], rec['name'], rec['version']
        # 合计是扁平 dict
        s_all = all_view['total']
        s_all['submitted'] += 1
        s_all[status] += 1
        for target, k in ((all_view['day'], mmdd), (all_view['week'], _wk(mmdd))):
            s2 = target[k]
            s2['submitted'] += 1
            s2[status] += 1
        # 标签统计：打标表优先、名称兜底（与日报明细口径一致）
        tag = tag_of(rec)
        if tag:
            bump(tag_views['total'], tag, status)
            bump(tag_views['day'][mmdd], tag, status)
            bump(tag_views['week'][_wk(mmdd)], tag, status)
        materials.append({
            'id': bn, 'name': name, 'version': ver,
            'audit_day': mmdd, 'status': status, 'url': '',
        })

    def bucket_to_obj(v):
        t = v['submitted']
        return {
            'submitted': t,
            'pass': v['pass'], 'fail': v['fail'],
            'eco': v['eco'], 'unknown': v['unknown'],
            'pass_rate': round(v['pass']/t*100, 1) if t else 0,
            'fail_rate': round((v['fail']+v['eco'])/t*100, 1) if t else 0,
        }

    def version_row(vmap):
        return {ver: bucket_to_obj(vmap.get(ver, {'submitted':0,'pass':0,'fail':0,'eco':0,'unknown':0}))
                for ver in VERSIONS}

    # 版本合计（不去重）：各改版 submitted 之和，直接累加原始版本计数
    def raw_total_of(vmap):
        v = {'submitted':0,'pass':0,'fail':0,'eco':0,'unknown':0}
        for ver in VERSIONS:
            s = vmap.get(ver, {'submitted':0,'pass':0,'fail':0,'eco':0,'unknown':0})
            for k in v:
                v[k] += s[k]
        return v

    view_json = {
        # 改版维度：按版本计数；合计「全部」桶：按基础名合并后计数；「版本合计」：不去重
        'total': {**version_row(by_view['total']),
                  '全部': bucket_to_obj(all_view['total']),
                  '版本合计': bucket_to_obj(raw_total_of(by_view['total']))},
        'day': {k: {**version_row(v),
                    '全部': bucket_to_obj(all_view['day'].get(k, {'submitted':0,'pass':0,'fail':0,'eco':0,'unknown':0})),
                    '版本合计': bucket_to_obj(raw_total_of(v))}
                for k, v in by_view['day'].items()},
        'week': {k: {**version_row(v),
                     '全部': bucket_to_obj(all_view['week'].get(k, {'submitted':0,'pass':0,'fail':0,'eco':0,'unknown':0})),
                     '版本合计': bucket_to_obj(raw_total_of(v))}
                 for k, v in by_view['week'].items()},
    }
    # 标签视图序列化：{tag: {submitted, pass, fail, eco, unknown, pass_rate, fail_rate}}
    def tag_bucket_to_obj(v):
        t = v['submitted']
        return {
            'submitted': t, 'pass': v['pass'], 'fail': v['fail'],
            'eco': v['eco'], 'unknown': v['unknown'],
            'pass_rate': round(v['pass']/t*100, 1) if t else 0,
            'fail_rate': round((v['fail']+v['eco'])/t*100, 1) if t else 0,
        }
    tag_view_json = {
        'total': {tag: tag_bucket_to_obj(v) for tag, v in tag_views['total'].items()},
        'day': {k: {tag: tag_bucket_to_obj(v) for tag, v in bucket.items()}
                for k, bucket in tag_views['day'].items()},
        'week': {k: {tag: tag_bucket_to_obj(v) for tag, v in bucket.items()}
                 for k, bucket in tag_views['week'].items()},
    }
    # 日→周映射（全量日期范围）
    day_week_map = {}
    week_range_map = {}
    day_keys = sorted(by_view['day'].keys())
    if day_keys:
        d0 = _dt.date(2026, int(day_keys[0][:2]), int(day_keys[0][2:]))
        d1 = _dt.date(2026, int(day_keys[-1][:2]), int(day_keys[-1][2:]))
        cur = d0
        while cur <= d1:
            k = f"{cur.month:02d}{cur.day:02d}"
            iso = cur.isocalendar()
            wk = f"{iso[0]}-W{iso[1]:02d}"
            day_week_map[k] = wk
            monday = cur - _dt.timedelta(days=cur.weekday())
            sunday = monday + _dt.timedelta(days=6)
            if wk not in week_range_map:
                week_range_map[wk] = (f"{monday.month:02d}{monday.day:02d}",
                                      f"{sunday.month:02d}{sunday.day:02d}")
            cur += _dt.timedelta(days=1)
    materials.sort(key=lambda x: (x['audit_day'], x['name']), reverse=True)
    return {'views': view_json, 'tag_views': tag_view_json, 'materials': materials,
            'day_week_map': day_week_map, 'week_range_map': week_range_map}


def build_recent_pass_analysis():
    """② 近3周跑出表现：推送池未卡审的视频 + 新产出图文，按（编导, 基础名）一行聚合。

    口径（2026-10-26 定稿）：
      - 行粒度 = 编导 + 基础名去重（与时效页一致）；同名多版本/多ID合并为一行；
        无素材ID的老素材也按名称聚合计入（不再因缺ID被丢弃）。
      - 视频：任一版本「推送视频_」且投放账户从未卡审；图文：名称有日期前缀。
      - 产出日：名称 MMDD 前缀优先（先剥「推送视频_」），无前缀用首现日。
      - 同名出现多个素材ID：id 列取首个真实ID；名称列并列展示去重后的所有名称。
      - audit_week：过审提交分周统计（分图文/视频）：提交数按基础名去重（多次修改算1次）、
        过审数=基础名任一版本最终通过，归属首次提交日所在自然周（周日为键）。
    """
    import datetime
    data_dir = Path(__file__).parent.parent / 'data'
    latest = _latest_mmdd()
    CORE4 = ['小敏', '瑞晨', '嘉丽', '雅迪']

    def person_of(name):
        for p in CORE4:
            if p in name:
                return p
        return '其他'

    def produce_day(name):
        """名称 MMDD 前缀（先剥「推送视频_」，兼容 -—－）；无则空"""
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

    # ---- 第一遍：全文件流式聚合（含无ID老素材、未推送自投视频、无前缀图文、卡审视频） ----
    # 全部投放素材都进 agg（产出数量=全量工作量口径）；池内过滤放到行构建阶段
    agg = {}      # key=(person, base_name) -> 行聚合
    key_order = []
    for f in sorted(data_dir.glob('引导加微每日数据-*.csv')):
        m = re.fullmatch(r'引导加微每日数据-(\d{4})', f.stem)
        if not m:
            continue
        mmdd = m.group(1)
        with open(f, encoding='utf-8-sig') as fh:
            for r in csv.DictReader(fh):
                name = (r.get('视频名称') or '').strip()
                if not name:
                    continue
                raw_acc = (r.get('账户id') or '').strip()
                if raw_acc in CHANNEL_ACCOUNTS:
                    continue
                typ = (r.get('素材类型') or '').strip()
                is_tuwen = (typ == '图文')
                bn = base_material_name(clean_name(name))
                p = person_of(name)
                key = (p, bn)
                if key not in agg:
                    agg[key] = {
                        'names': [], 'name_set': set(), 'ids': [], 'id_set': set(),
                        'is_tuwen': is_tuwen, 'is_pushed': False, 'pd': '', 'pd_prefix': False,
                        'first': mmdd, 'last': mmdd, 'rejected': False,
                        'daily': {}, 'url': '',
                    }
                    key_order.append(key)
                a = agg[key]
                if name.startswith('推送视频_'):
                    a['is_pushed'] = True
                if name not in a['name_set']:
                    a['name_set'].add(name)
                    a['names'].append(name)
                sid = (r.get('素材id') or '').strip().lstrip('\t')
                if sid and sid not in a['id_set']:
                    a['id_set'].add(sid)
                    a['ids'].append(sid)
                pdp = produce_day(name)
                if pdp and not a['pd']:
                    a['pd'] = pdp
                    a['pd_prefix'] = True
                if mmdd < a['first']:
                    a['first'] = mmdd
                if mmdd > a['last']:
                    a['last'] = mmdd
                url = (r.get('视频链接') or '').strip()
                if url:
                    a['url'] = url
                if not is_tuwen and '不通过' in (r.get('审核建议') or ''):
                    a['rejected'] = True
                d = a['daily'].setdefault(mmdd, {'spend': 0.0, 'conv': 0.0, 'gq': 0.0,
                                                 'imp': 0.0, 'click': 0.0,
                                                 'w3': 0.0, 'w5': 0.0, 'wf': 0.0, 'wd': 0.0})
                d['spend'] += safe_float(r.get('消耗'))
                d['conv'] += safe_float(r.get('转化数'))
                d['gq'] += safe_float(r.get('回访-高潜成交(计费时间)'))
                d['imp'] += safe_float(r.get('展示数'))
                d['click'] += safe_float(r.get('点击数'))
                d['w3'] += safe_float(r.get('3秒播放率')) or 0
                d['w5'] += safe_float(r.get('5秒播放率')) or 0
                qf = r.get('完播率(%)') if r.get('完播率(%)') not in (None, '') else r.get('完播率')
                d['wf'] += safe_float(qf) or 0
                d['wd'] += safe_float(r.get('平均单次播放时长')) or 0

    rows = []
    produce = []
    for key in key_order:
        a = agg[key]
        # 池内行（指标用）：图文=名称有日期前缀；视频=推送池且从未卡审
        if a['is_tuwen']:
            if not a['pd_prefix']:
                continue  # 无日期前缀的图文不进池（仍计入产出数量）
        else:
            if not a['is_pushed'] or a['rejected']:
                continue  # 未推送/卡审视频不进池（仍计入产出数量）
        # 产出日：名称前缀优先；无前缀用首现日兜底
        push_day = a['pd'] or a['first']
        rows.append({
            'id': a['ids'][0] if a['ids'] else '',
            'name': ' / '.join(a['names']),
            'names': a['names'],
            'type': 'tuwen' if a['is_tuwen'] else 'video',
            'version': extract_version(a['names'][0]),
            'person': key[0],
            'push_day': push_day,
            'first': a['first'],
            'daily': a['daily'],
            'url': a['url'],
        })
    # 产出数量（全量工作量口径，0改/1改/2改/3改按基础名算1条）
    for key in key_order:
        a = agg[key]
        produce.append({'p': key[0],
                        't': 'tuwen' if a['is_tuwen'] else 'video',
                        'pd': a['pd'] or a['first']})
    rows.sort(key=lambda x: x['push_day'], reverse=True)

    # ---- 过审提交统计（全按视频；多次修改按基础名算1次） ----
    # 归属日：任一版本通过 → 首次通过日；一直不通过 → 首次提交日（用户 2026-10-27 定）
    audit_first = {}   # base_name -> {'first_day', 'pass_day', 'name'}
    for f in sorted(data_dir.glob('*投放过审.csv')):
        m = re.fullmatch(r'(\d{4})投放过审', f.stem)
        if not m:
            continue
        mmdd = m.group(1)
        with open(f, encoding='utf-8-sig') as fh:
            for r in csv.DictReader(fh):
                name = (r.get('视频名称') or '').strip()
                if not name:
                    continue
                bn = base_material_name(clean_name(name))
                rec = audit_first.setdefault(bn, {'first_day': mmdd, 'name': name, 'pass_day': ''})
                if (r.get('审核建议') or '').strip() == '审核通过' and not rec['pass_day']:
                    rec['pass_day'] = mmdd
    audit_week = {}
    # 产出数量补过审素材：投放数据未出现的过审素材也计入（工作量口径），产出日=名称MMDD前缀、无则首次提交日
    for bn, rec in audit_first.items():
        day = rec['pass_day'] or rec['first_day']
        d = datetime.date(2026, int(day[:2]), int(day[2:]))
        sunday = d + datetime.timedelta(days=(6 - d.weekday()))
        wk = f'{sunday.month:02d}{sunday.day:02d}'
        w = audit_week.setdefault(wk, {'submitted': 0, 'passed': 0, 'by_person': {}})
        w['submitted'] += 1
        if rec['pass_day']:
            w['passed'] += 1
            p = person_of(rec['name'])
            bp = w['by_person'].setdefault(p, {'submitted': 0, 'passed': 0})
            bp['submitted'] += 1
            bp['passed'] += 1
        else:
            p = person_of(rec['name'])
            bp = w['by_person'].setdefault(p, {'submitted': 0, 'passed': 0})
            bp['submitted'] += 1
        # 产出清单补录（过审提交过的素材，哪怕从未进投放数据也算产出；过审文件全按视频）
        agg_bases = {bn_ for (_, bn_) in key_order}
        if bn not in agg_bases:
            produce.append({'p': person_of(rec['name']),
                            't': 'video',
                            'pd': produce_day(rec['name']) or rec['first_day']})

    return {
        'latest': latest or '',
        'rows': rows,
        'audit_week': audit_week,
        'produce': produce,
    }


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
                            'is_ai': r['_is_ai'],
                    'video_url': r['_视频链接'],
                    'days': {}
                }
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

.kpi-grid{{display:grid;grid-template-columns:repeat(8,1fr);gap:12px;margin-bottom:20px}}
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
.kpi-diff{{margin-right:6px;font-size:10.5px;font-weight:600;display:inline-block}}
.kpi-diff.up{{color:var(--success)}}
.kpi-diff.down{{color:var(--danger)}}
.help-tip{{
  display:inline-flex;align-items:center;justify-content:center;
  width:11px;height:11px;border-radius:50%;background:#DBEAFE;color:#1E40AF;
  font-size:9px;font-weight:700;line-height:1;margin-left:3px;flex-shrink:0;
  position:relative;vertical-align:middle;text-align:center;
}}
.help-tip::before{{
  content:'?';
}}
.table-wrap thead th{{
  position:sticky;top:0;background:#F1F5F9;z-index:5;
  box-shadow:0 1px 0 var(--border);
}}
/* 悬浮表头时整体提到最高层，避免问号 tooltip 被相邻列头盖住 */
.table-wrap thead th:hover{{
  z-index:9990;
}}
.order-rate-value{{
  position:relative;
}}
.order-rate-value:hover::after{{
  content:attr(data-tip);
  position:fixed;z-index:99999;pointer-events:none;
  background:#1E3A8A;color:#fff;border-radius:8px;padding:8px 10px;
  font-size:11px;font-weight:400;line-height:1.6;white-space:pre-wrap;max-width:420px;
  box-shadow:0 4px 12px rgba(0,0,0,.3);
  left:50%;transform:translateX(-50%);
}}
.order-rate-badge{{
  position:relative;
}}
.order-rate-badge:hover::after{{
  content:attr(data-tip);
  position:fixed;z-index:99999;pointer-events:none;
  background:#1E3A8A;color:#fff;border-radius:8px;padding:8px 10px;
  font-size:11px;font-weight:400;line-height:1.6;white-space:normal;word-break:break-all;
  box-shadow:0 4px 12px rgba(0,0,0,.3);
  left:50%;transform:translateX(-50%);
}}
.help-tip:hover::after{{
  content:attr(data-tip);
  position:fixed;z-index:99999;pointer-events:none;
  background:#1E3A8A;color:#fff;border-radius:8px;padding:8px 10px;
  font-size:11px;font-weight:400;line-height:1.5;white-space:normal;word-break:break-all;max-width:380px;
  box-shadow:0 4px 12px rgba(0,0,0,.3);
  left:50%;transform:translateX(-50%);
  bottom:auto;top:auto;
}}
.tc-diff{{font-weight:600;display:inline-block}}
.tc-diff.inc{{color:var(--success)}}
.tc-diff.dec{{color:var(--danger)}}

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
.range-btn{{
  padding:4px 13px;border-radius:16px;border:1.5px solid var(--border);
  font-size:12px;font-weight:500;color:var(--text-secondary);cursor:pointer;
  background:var(--card);transition:all .15s;white-space:nowrap;
}}
.range-btn:hover{{border-color:var(--primary-light);color:var(--primary)}}
.range-btn.active{{background:var(--primary);border-color:var(--primary);color:#fff;box-shadow:var(--shadow-md)}}
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
.page-btn{{display:inline-block;margin:0 2px;padding:1px 8px;border:1px solid var(--border);border-radius:6px;background:#fff;font-size:11px;color:var(--text-secondary);cursor:pointer}}
.page-btn:hover{{border-color:var(--primary-light);color:var(--primary)}}
.page-btn.active{{background:var(--primary);border-color:var(--primary);color:#fff;font-weight:600}}
.page-btn:disabled{{opacity:.4;cursor:default}}
.page-ellipsis{{margin:0 2px;font-size:11px;color:var(--text-muted)}}
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

.mat-name{{max-width:260px;white-space:normal;word-break:break-all;
  font-size:12px;color:var(--text);line-height:1.45}}
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
  thead th:nth-child(6),
  thead th:nth-child(7),
  thead th:nth-child(9){{display:none}}
  tbody td:nth-child(6),
  tbody td:nth-child(7),
  tbody td:nth-child(9){{display:none}}
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

  <!-- 渠道账户总览（渠道数据不进明细） -->
  <div class="table-card" id="channelSection" style="display:none;margin-bottom:20px">
    <div class="table-toolbar">
      <div class="section-title" style="margin:0">🤝 渠道账户总览</div>
      <div class="table-info">渠道数据单独统计，不进明细分析</div>
    </div>
    <div class="table-wrap">
      <table id="channelTable">
        <thead>
          <tr>
            <th>账户</th>
            <th>消耗</th>
            <th>展示</th>
            <th>点击率</th>
            <th>转化数</th>
            <th>转化率</th>
            <th>CPA</th>
            <th>高潜</th>
            <th>深转率</th>
          </tr>
        </thead>
        <tbody id="channelBody"></tbody>
      </table>
    </div>
  </div>

  <!-- KPI Cards -->
  <div class="kpi-grid">
    <div class="kpi-card">
      <div class="kpi-label">总消耗</div>
      <div class="kpi-value" id="kpi-spend">¥{total_spend}</div>
      <div class="kpi-sub"><span id="kpi-spend-diff" class="kpi-diff"></span><span id="kpi-count">{material_count} 条素材</span></div>
    </div>
    <div class="kpi-card">
      <div class="kpi-label">总展示</div>
      <div class="kpi-value" id="kpi-imp">{total_imp}</div>
      <div class="kpi-sub"><span id="kpi-imp-diff" class="kpi-diff"></span>次曝光</div>
    </div>
    <div class="kpi-card">
      <div class="kpi-label">平均点击率</div>
      <div class="kpi-value" id="kpi-ctr">{avg_ctr}</div>
      <div class="kpi-sub"><span id="kpi-ctr-diff" class="kpi-diff"></span>CTR</div>
    </div>
    <div class="kpi-card">
      <div class="kpi-label">转化率</div>
      <div class="kpi-value" id="kpi-cvr" style="color:#8B5CF6">{avg_cvr}</div>
      <div class="kpi-sub"><span id="kpi-cvr-diff" class="kpi-diff"></span>总转化数 / 总点击</div>
    </div>
    <div class="kpi-card">
      <div class="kpi-label">总转化数</div>
      <div class="kpi-value" id="kpi-conv">{total_conv}</div>
      <div class="kpi-sub"><span id="kpi-conv-diff" class="kpi-diff"></span>次转化</div>
    </div>
    <div class="kpi-card">
      <div class="kpi-label">平均 CPA</div>
      <div class="kpi-value" id="kpi-cpa">¥{avg_cpa}</div>
      <div class="kpi-sub"><span id="kpi-cpa-diff" class="kpi-diff"></span>转化成本</div>
    </div>
    <div class="kpi-card accent">
      <div class="kpi-label">高潜成交</div>
      <div class="kpi-value" id="kpi-gaoquan">{total_gaoquan}</div>
      <div class="kpi-sub"><span id="kpi-gaoquan-diff" class="kpi-diff"></span>深度转化 · 核心指标</div>
    </div>
    <div class="kpi-card accent">
      <div class="kpi-label">深转率</div>
      <div class="kpi-value" id="kpi-deeprate">{deep_rate}</div>
      <div class="kpi-sub"><span id="kpi-deeprate-diff" class="kpi-diff"></span>高潜成交 / 总转化</div>
    </div>
  </div>

  <!-- 多日趋势折线图（仅多日时显示） -->
  <div id="trendSection" style="display:none;margin-bottom:20px">
    <div class="chart-card">
      <div class="section-title">每日趋势：转化数 / 高潜成交 / CPA（近30天）</div>
      <div class="chart-wrap" style="height:200px"><canvas id="chartTrend"></canvas></div>
    </div>
  </div>

  <!-- 多日切换标签（仅多日时显示） -->
  <div id="tabsContainer" style="display:none;margin-bottom:16px">
    <div id="rangeBtns" style="display:flex;align-items:center;gap:6px;flex-wrap:wrap;margin-bottom:8px">
      <span style="font-size:12px;color:var(--text-secondary);font-weight:500">快捷范围</span>
    </div>
    <div class="tabs" id="tabHeaders">
      <div class="tabs-sort">
        <button class="sort-btn active" id="sortByDate" onclick="setTabSort('date')">日期 ↑</button>
        <button class="sort-btn" id="sortBySpend" onclick="setTabSort('spend')">消耗 ↓</button>
      </div>
    </div>
  </div>

  <!-- 视频素材标签分析（卡片形式） -->
  <div class="chart-card" style="margin-bottom:20px">
    <div class="section-title">视频素材表现（按标签）</div>
    <div id="tagCardsRow" style="display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-top:12px"></div>
    <div style="margin-top:16px">
      <div class="section-title" style="margin-bottom:12px">按素材类型</div>
      <div id="typeCardsRow" style="display:grid;grid-template-columns:repeat(3,1fr);gap:12px"></div>
    </div>
  </div>

  <!-- 卡审分析：投放账户推送素材池（仅视频，图文过审数据导不出） -->
  <div class="chart-card" style="margin-bottom:20px">
    <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:12px;flex-wrap:wrap;gap:8px">
      <div class="section-title" style="margin:0">🚦 卡审分析 <span id="rejScopeLabel" style="color:var(--text-muted);font-weight:400;font-size:11px"></span></div>
      <div style="display:flex;gap:6px">
        <button class="sort-btn active" id="modeDelivery" onclick="setAnalysisMode('delivery',this)">投放账户</button>
        <button class="sort-btn" id="modeTest" style="color:#0EA5E9" onclick="setAnalysisMode('test',this)">测试账户</button>
      </div>
    </div>
    <div id="rejectCardsRow" style="display:grid;grid-template-columns:repeat(4,1fr);gap:12px"></div>
    <div style="margin-top:16px">
      <div class="section-title" style="margin-bottom:12px">按内容标签（A1-A4）</div>
      <div id="rejectTagCardsRow" style="display:grid;grid-template-columns:repeat(4,1fr);gap:12px"></div>
    </div>
    <div style="margin-top:12px">
      <div style="font-size:11px;color:var(--text-muted)" id="analysisModeDesc">卡审口径：测试账户推送（名称「推送视频_」开头）到投放账户后，审核建议出现过「不通过」；状态单调不回退。刚推送卡审 = 卡审前消耗为0；用着用着卡审 = 卡审前已有消耗。卡片/明细按推送日统计，跟随顶部日期筛选；比例分母均为推送数。</div>
      <div style="margin-top:10px">
        <div style="font-size:12px;font-weight:600;color:var(--text);margin-bottom:6px">分日明细 <span style="color:var(--text-muted);font-weight:400;font-size:11px">（跟随顶部日期）</span></div>
        <div class="table-wrap" style="max-height:200px;overflow-y:auto;border:1px solid var(--border);border-radius:8px">
          <table style="font-size:12px">
            <thead id="rejectDayHead"><tr>
              <th>推送日</th>
              <th style="text-align:center">推送数</th>
              <th style="text-align:center">卡审数</th>
              <th style="text-align:center">总卡审率</th>
              <th style="text-align:center">环比昨日</th>
              <th style="text-align:center">0改</th>
              <th style="text-align:center">1改</th>
              <th style="text-align:center">2改</th>
              <th style="text-align:center">3改</th>
            </tr></thead>
            <tbody id="rejectBucketBody"></tbody>
          </table>
        </div>
      </div>
      <div style="margin-top:10px">
        <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:6px;flex-wrap:wrap;gap:8px">
          <div style="font-size:12px;font-weight:600;color:var(--text)">分周明细 <span style="color:var(--text-muted);font-weight:400;font-size:11px">（本周 vs 上周）</span></div>
          <button class="sort-btn" id="rejWeekExpandBtn" onclick="toggleWeekExpand()" style="font-size:11px">查看全部周 ▾</button>
        </div>
        <div class="table-wrap" style="max-height:200px;overflow-y:auto;border:1px solid var(--border);border-radius:8px">
          <table style="font-size:12px">
            <thead id="rejectWeekHead"><tr>
              <th>推送周</th>
              <th style="text-align:center">推送数</th>
              <th style="text-align:center">卡审数</th>
              <th style="text-align:center">总卡审率</th>
              <th style="text-align:center">环比上周</th>
              <th style="text-align:center">0改</th>
              <th style="text-align:center">1改</th>
              <th style="text-align:center">2改</th>
              <th style="text-align:center">3改</th>
            </tr></thead>
            <tbody id="rejectWeekBody"></tbody>
          </table>
        </div>
      </div>
    </div>
    <div style="margin-top:12px">
      <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:6px;flex-wrap:wrap;gap:8px">
        <div style="font-size:12px;font-weight:600;color:var(--text)" id="rejectListTitle">推送素材去向明细 <span id="rejectListCount" style="color:var(--text-muted);font-weight:400"></span></div>
        <div style="display:flex;gap:6px" id="rejFilterGroup">
          <button class="sort-btn active" id="rejFilterAll" onclick="setRejFilter('all',this)">全部</button>
          <button class="sort-btn" id="rejFilterImmediate" style="color:#DC2626" onclick="setRejFilter('immediate',this)">刚推送卡审</button>
          <button class="sort-btn" id="rejFilterInuse" style="color:#D97706" onclick="setRejFilter('inuse',this)">用着用着卡审</button>
          <button class="sort-btn" id="rejFilterOk" style="color:#059669" onclick="setRejFilter('ok',this)">推送后未卡审</button>
        </div>
      </div>
      <div class="table-wrap" style="max-height:360px;overflow-y:auto;border:1px solid var(--border);border-radius:8px">
        <table style="font-size:12px" id="rejectListTable">
          <thead id="rejectListHead"><tr>
            <th data-col="name">素材名称</th><th data-col="version">改版</th><th>账户</th><th data-col="first_day">推送日</th><th data-col="first_rej_day" class="sorted-desc">卡审日 ↓</th><th>去向</th><th>视频</th>
          </tr></thead>
          <tbody id="rejectListBody"></tbody>
        </table>
      </div>
    </div>
  </div>

  <!-- 近3周过审素材跑出表现（视频+图文） -->
  <div class="chart-card" style="margin-bottom:20px">
    <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:12px;flex-wrap:wrap;gap:8px">
      <div class="section-title" style="margin:0">📈 近3周过审视频+图文跑出表现 <span id="passWindowLabel" style="color:var(--text-muted);font-weight:400;font-size:11px"></span></div>
      <div style="display:flex;gap:6px" id="passWeekBtns">
        <button class="sort-btn active" id="passWeekAll" onclick="setPassWeek('all',this)">全部3周</button>
        <button class="sort-btn" id="passWeek1" onclick="setPassWeek('w1',this)">第1周</button>
        <button class="sort-btn" id="passWeek2" onclick="setPassWeek('w2',this)">第2周</button>
        <button class="sort-btn" id="passWeek3" onclick="setPassWeek('w3',this)">第3周</button>
      </div>
    </div>
    <div id="passSummaryRow" style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:12px;align-items:center"></div>
    <div id="passPersonSummaryRow" style="display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin-bottom:12px"></div>
    <div id="passPersonCards" style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:12px"></div>
    <div class="table-wrap" style="max-height:420px;overflow-y:auto">
      <table style="font-size:12px" id="passListTable">
        <thead><tr>
          <th data-col="name">素材名称</th><th data-col="type">类型</th><th data-col="version">改版</th><th data-col="push_day">产出日</th><th data-col="spend" class="sorted-desc">消耗 ↓</th><th data-col="ctr">点击率<span class="help-tip" data-tip="点击率=点击÷展示，窗口内加权"></span></th><th data-col="conv">转化</th><th data-col="cpa">CPA</th><th data-col="gq">深转</th><th data-col="deep_rate">深转率<span class="help-tip" data-tip="深转率=高潜成交÷转化数"></span></th><th data-col="qf">完播率</th><th data-col="q3">3秒播放率</th><th data-col="q5">5秒播放率</th><th data-col="qd">播放时长</th><th data-col="active_days">在投天数<span class="help-tip" data-tip="窗口内有消耗的天数"></span></th><th>视频</th>
        </tr></thead>
        <tbody id="passListBody"></tbody>
      </table>
    </div>
    <div class="empty-state" id="passListEmpty" style="display:none">该筛选下暂无数据</div>
  </div>

  <!-- 编导卡片 -->
  <div class="chart-card" style="margin-bottom:20px">
    <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:12px">
      <div class="section-title" style="margin:0">编导表现</div>
      <div style="display:flex;gap:6px">
        <button class="sort-btn active" id="personTypeAll" onclick="setPersonType('all',this)">全部</button>
        <button class="sort-btn" id="personTypeVideo" onclick="setPersonType('video',this)" style="color:#3B82F6">视频</button>
        <button class="sort-btn" id="personTypeTuwen" onclick="setPersonType('tuwen',this)" style="color:#8B5CF6">图文</button>
      </div>
    </div>
    <div id="personCardsRow" style="display:grid;grid-template-columns:repeat(4,1fr);gap:12px"></div>
  </div>

  <!-- 筛选栏 -->
  <div class="filter-bar" style="flex-direction:column;align-items:flex-start;gap:10px">
    <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap">
      <span class="filter-label">类型</span>
      <button class="filter-btn active" data-type="all" onclick="filterType('all',this)">全部</button>
      <button class="filter-btn filter-btn-video" data-type="video" onclick="filterType('video',this)">视频</button>
      <button class="filter-btn filter-btn-tuwen" data-type="tuwen" onclick="filterType('tuwen',this)">图文</button>
      <button class="filter-btn" data-type="ai" onclick="filterType('ai',this)" style="color:#6366F1">Ai</button>
    </div>
    <div style="width:100%;height:1px;background:var(--border)"></div>
    <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap">
      <span class="filter-label">标签</span>
      <button class="filter-btn active" data-tag="all" onclick="filterTag('all',this)">全部</button>
      <button class="filter-btn" data-tag="A1" onclick="filterTag('A1',this)" style="color:#3B82F6">A1技巧</button>
      <button class="filter-btn" data-tag="A2" onclick="filterTag('A2',this)" style="color:#8B5CF6">A2经历</button>
      <button class="filter-btn" data-tag="A3" onclick="filterTag('A3',this)" style="color:#10B981">A3结果</button>
      <button class="filter-btn" data-tag="A4" onclick="filterTag('A4',this)" style="color:#F59E0B">A4情绪</button>
      <button class="filter-btn" data-tag="none" onclick="filterTag('none',this)" style="color:#94A3B8">未标记</button>
      <div class="filter-sep"></div>
      <button class="filter-btn" data-tag="keytest" onclick="filterTag('keytest',this)" style="color:#D97706">重点测<span class="help-tip" data-tip="重点测：素材名称含「-起」标记（如 1026-婷玉-图文-邪修-1-起），独立筛选"></span></button>
    </div>
    <div style="width:100%;height:1px;background:var(--border)"></div>
    <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap">
      <span class="filter-label">改版</span>
      <button class="filter-btn active" data-version="all" onclick="filterVersion('all',this)">全部</button>
      <button class="filter-btn" data-version="0改" onclick="filterVersion('0改',this)" style="color:#64748B">0改</button>
      <button class="filter-btn" data-version="1改" onclick="filterVersion('1改',this)" style="color:#64748B">1改</button>
      <button class="filter-btn" data-version="2改" onclick="filterVersion('2改',this)" style="color:#64748B">2改</button>
      <button class="filter-btn" data-version="3改" onclick="filterVersion('3改',this)" style="color:#64748B">3改</button>
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
    <div style="width:100%;height:1px;background:var(--border)"></div>
    <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap">
      <span class="filter-label">产出日期<span class="help-tip" data-tip="产出日期 = 素材名称开头的 MMDD 日期前缀；名称无日期时取投放数据首次出现日。可多选；选完自动联动顶部日期"></span></span>
      <button class="filter-btn active" id="pdClearBtn" onclick="clearProduceDay(this)" style="color:#64748B">全部</button>
      <div id="produceDayChips" style="display:flex;gap:4px;flex-wrap:wrap"></div>
      <div class="filter-sep"></div>
      <div style="position:relative">
        <button class="sort-btn" id="pdPickBtn" onclick="togglePdPicker()" style="font-size:12px">选择日期 ▾</button>
        <div id="pdPicker" style="display:none;position:absolute;top:100%;left:0;z-index:500;background:#fff;border:1.5px solid var(--border);border-radius:8px;box-shadow:var(--shadow-md);padding:10px;min-width:320px;max-height:360px;overflow-y:auto">
          <div style="display:flex;gap:4px;flex-wrap:wrap;margin-bottom:8px" id="pdMonthBtns"></div>
          <div style="display:grid;grid-template-columns:repeat(7,1fr);gap:4px" id="pdDayGrid"></div>
        </div>
      </div>
    </div>
  </div>

  <!-- 素材明细表 -->
  <div class="table-card">
    <div class="table-toolbar" style="flex-direction:column;align-items:flex-start;gap:8px">
      <div style="display:flex;align-items:center;justify-content:space-between;width:100%">
        <div class="section-title" style="margin:0">素材明细</div>
        <div class="table-info">显示 <span id="visibleCount">-</span> / {material_count} 条 · 点击列头排序 · <span id="pagerBox"></span></div>
      </div>
      <div style="display:flex;gap:8px;flex-wrap:wrap;align-items:center" id="personOrderRateRow">
        <span style="font-size:11px;color:var(--text-secondary)">编导高潜成交率<span class="help-tip" data-tip="高潜成交率 = 深转>0 的素材数 ÷ 该编导总素材数（按名称基础名去重：同名多版本算一条，任一版本深转>0 即高潜成交）；跟随顶部日期、产出日期、标签/类型筛选联动"></span></span>
        <span id="personOrderRates" style="display:flex;gap:6px;flex-wrap:wrap"></span>
      </div>
    </div>
    <div class="table-wrap">
      <table id="matTable">
        <thead>
          <tr>
            <th data-col="person">人物</th>
            <th data-col="account">账户</th>
            <th data-col="name">素材名称</th>
            <th data-col="id" title="千川素材ID（纯文本展示，避免精度丢失）">素材ID</th>
            <th data-col="tag">标签</th>
            <th data-col="version">改版</th>
            <th data-col="produce_day">产出日期<span class="help-tip" data-tip="产出日期 = 素材名称开头的 MMDD 日期前缀（如 1015-xxx → 10/15）；名称无日期时取投放数据首次出现日"></span></th>
            <th data-col="spend" class="sorted-desc">消耗</th>
            <th data-col="impressions">展示数</th>
            <th data-col="ctr">点击率%</th>
            <th data-col="conversions">转化数</th>
            <th data-col="cvr" title="转化数÷点击数">转化率%</th>
            <th data-col="cpa">CPA</th>
            <th data-col="gaoquan" title="高潜成交（深度转化核心指标）">高潜成交 ★</th>
            <th data-col="deep_rate" title="高潜成交÷转化数">深转率</th>
            <th data-col="q3">3秒播放率<span class="help-tip" data-tip="3秒播放率：视频前3秒被观看的比例，多日合并时按展示数加权"></span></th>
            <th data-col="q5">5秒播放率</th>
            <th data-col="qf">完播率<span class="help-tip" data-tip="完播率：完整播放的比例，多日合并时按展示数加权"></span></th>
            <th data-col="qd">播放时长</th>
            <th>视频</th>
          </tr>
        </thead>
        <tbody id="tableBody"></tbody>
      </table>
    </div>
    <div class="empty-state" id="emptyState" style="display:none">该筛选条件下暂无数据</div>
  </div>

  <!-- 素材生命周期（独立网页嵌入，随日报一并发布） -->
  <div class="chart-card" style="margin-top:20px">
    <div class="section-title" style="margin-bottom:10px">📈 素材生命周期</div>
    <iframe src="素材周期表现.html" title="素材生命周期" loading="lazy"
      style="width:100%;height:900px;border:1px solid var(--border);border-radius:var(--radius);background:#fff"></iframe>
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
const TAG_LABELS  = {tag_labels_js};
const TAG_SPEND   = {tag_spend_js};
const TAG_CONV    = {tag_conv_js};
const TAG_GAOQUAN = {tag_gaoquan_js};
const TAG_COLORS  = {tag_colors_js};
const AUDIT_DATA  = {audit_data_js};
const AUDIT_BY_DATE = {audit_by_date_js};
const IS_MULTI = {is_multi};
const COMPARE_DATA = {compare_js};
const ALL_DATES = {all_dates_js};
const ALL_ROWS_BY_DATE = {all_rows_by_date_js};
const CHANNEL_SUMMARY = {channel_summary_js};
const REJECT_ANALYSIS = {reject_analysis_js};
const RECENT_PASS_ANALYSIS = {recent_pass_analysis_js};
const TEST_AUDIT_ANALYSIS = {test_audit_analysis_js};

// ---------- 图表 ----------
const chartDefaults = {{
  responsive: true, maintainAspectRatio: false,
  plugins: {{ legend: {{ display: false }}, tooltip: {{ callbacks: {{}} }} }},
  scales: {{ x: {{ grid: {{ color: '#F1F5F9' }} }}, y: {{ grid: {{ color: '#F1F5F9' }}, ticks: {{ font: {{ size: 11 }} }} }} }},
}};

let trendChart;

function initTrendChart() {{
  if (!IS_MULTI) return;
  const trend = (COMPARE_DATA.trend || []).slice(-30);
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
let tagSpendChart, tagConvChart, tagGaoquanChart, auditChart;

function updateTagCards(rows) {{  const container = document.getElementById('tagCardsRow');
  if (!container) return;
  const TAG_FULL = {{'A1':'A1 技巧','A2':'A2 经历','A3':'A3 结果','A4':'A4 情绪'}};
  const TAG_ORDER_JS = ['A1','A2','A3','A4'];
  const TAG_COLORS_MAP = {{'A1':'#3B82F6','A2':'#8B5CF6','A3':'#10B981','A4':'#F59E0B'}};

  // 计算当前 rows 的标签统计
  const stats = {{}};
  TAG_ORDER_JS.forEach(t => stats[t] = {{spend:0,conv:0,gq:0,click:0,imp:0}});
  rows.forEach(r => {{
    if (!r.tag || r.spend === 0 || r.is_tuwen) return;
    r.tag.split(',').forEach(t => {{
      const base = t.split('-')[0].trim();
      if (stats[base]) {{
        stats[base].spend += r.spend;
        stats[base].conv  += r.conversions;
        stats[base].gq    += r.gaoquan;
        stats[base].click += r.clicks;
        stats[base].imp   += r.impressions;
      }}
    }});
  }});

  container.innerHTML = TAG_ORDER_JS.map(t => {{
    const s = stats[t];
    const label = TAG_FULL[t];
    const color = TAG_COLORS_MAP[t];
    const cpa = s.conv > 0 ? (s.spend / s.conv).toFixed(2) : '—';
    const deepRate = s.conv > 0 ? (s.gq / s.conv * 100).toFixed(1) + '%' : '—';
    const ctr = s.imp > 0 ? (s.click / s.imp * 100).toFixed(2) + '%' : '—';
    const cvr = s.click > 0 ? (s.conv / s.click * 100).toFixed(2) + '%' : '—';
    const hasData = s.spend > 0;
    return `<div style="background:#fff;border:1.5px solid ${{color}}33;border-radius:10px;padding:14px 16px;box-shadow:0 1px 3px rgba(0,0,0,.06);">
      <div style="display:flex;align-items:center;gap:6px;margin-bottom:10px">
        <span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:${{color}}"></span>
        <span style="font-size:13px;font-weight:700;color:${{color}}">${{label}}</span>
      </div>
      ${{hasData ? `
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:6px">
        <div style="background:#F8FAFC;border-radius:6px;padding:8px 10px">
          <div style="font-size:10px;color:#94A3B8;margin-bottom:2px">消耗</div>
          <div style="font-size:15px;font-weight:700;color:#1E40AF;font-family:monospace">¥${{s.spend.toLocaleString('zh',{{maximumFractionDigits:0}})}}</div>
        </div>
        <div style="background:#F8FAFC;border-radius:6px;padding:8px 10px">
          <div style="font-size:10px;color:#94A3B8;margin-bottom:2px">转化数</div>
          <div style="font-size:15px;font-weight:700;color:#059669;font-family:monospace">${{s.conv}}</div>
        </div>
        <div style="background:#F8FAFC;border-radius:6px;padding:8px 10px">
          <div style="font-size:10px;color:#94A3B8;margin-bottom:2px">点击率</div>
          <div style="font-size:15px;font-weight:700;color:#3B82F6;font-family:monospace">${{ctr}}</div>
          <div style="font-size:10px;color:#94A3B8;margin-top:2px">点击 ${{s.click.toLocaleString('zh',{{maximumFractionDigits:0}})}}</div>
        </div>
        <div style="background:#F8FAFC;border-radius:6px;padding:8px 10px">
          <div style="font-size:10px;color:#94A3B8;margin-bottom:2px">转化率</div>
          <div style="font-size:15px;font-weight:700;color:#8B5CF6;font-family:monospace">${{cvr}}</div>
          <div style="font-size:10px;color:#94A3B8;margin-top:2px">转化 ${{s.conv}} / 点击 ${{s.click.toLocaleString('zh',{{maximumFractionDigits:0}})}}</div>
        </div>
        <div style="background:#F8FAFC;border-radius:6px;padding:8px 10px">
          <div style="font-size:10px;color:#94A3B8;margin-bottom:2px">高潜成交</div>
          <div style="font-size:15px;font-weight:700;color:#D97706;font-family:monospace">${{s.gq}}</div>
        </div>
        <div style="background:#F8FAFC;border-radius:6px;padding:8px 10px">
          <div style="font-size:10px;color:#94A3B8;margin-bottom:2px">CPA</div>
          <div style="font-size:15px;font-weight:700;color:#64748B;font-family:monospace">¥${{cpa}}</div>
        </div>
        <div style="background:#FFFBEB;border-radius:6px;padding:8px 10px;grid-column:span 2">
          <div style="font-size:10px;color:#94A3B8;margin-bottom:2px">深转率（高潜/转化）</div>
          <div style="font-size:15px;font-weight:700;color:#D97706;font-family:monospace">${{deepRate}}</div>
        </div>
      </div>` : `<div style="color:#94A3B8;font-size:12px;text-align:center;padding:20px 0">暂无数据</div>`}}
    </div>`;
  }}).join('');
}}


function initAuditChart() {{
  updateAuditCards(AUDIT_DATA);
}}

let _personType = 'all';  // 'all' | 'video' | 'tuwen'
let _currentDateLabel = '';  // 当前渲染的单日日期（'MM/DD'）；多日为 ''
let _personRows = [];
let _personAudit = null;

window.setPersonType = function(type, btn) {{
  _personType = type;
  document.querySelectorAll('#personTypeAll,#personTypeVideo,#personTypeTuwen').forEach(b => {{
    b.classList.remove('active'); b.style.background='';
  }});
  btn.classList.add('active');
  updatePersonCards(_personRows, _personAudit);
}};

function updatePersonCards(rows, auditData) {{
  _personRows = rows; _personAudit = auditData;
  const container = document.getElementById('personCardsRow');
  if (!container) return;

  // 从过审数据建立：编导 → {{pass:[素材名], fail:[素材名]}}
  const auditByPerson = {{}};
  if (auditData && auditData.person_audit) {{
    Object.entries(auditData.person_audit).forEach(([p, d]) => {{ auditByPerson[p] = d; }});
  }}

  // 按编导聚合投放数据（根据当前类型过滤；编导卡片只看4人，用户 2026-10-23 定）
  const ALL_PERSONS_ORDER = {person_order_js};
  const CORE_EDITORS = ['小敏', '瑞晨', '嘉丽', '雅迪'];
  const personStats = {{}};
  const orderRateStats = {{}};  // 高潜成交率：基础名去重
  rows.forEach(r => {{
    if (r.spend === 0) return;
    if (r.is_ai) return;  // AI素材不计入编导
    const p = r.person;
    if (!CORE_EDITORS.includes(p)) return;  // 只统计核心4编导
    if (!personStats[p]) personStats[p] = {{videoSpend:0,tuwenSpend:0,conv:0,gq:0,click:0,imp:0,person:p}};
    const isTw = r.is_tuwen;
    if (isTw) personStats[p].tuwenSpend += r.spend;
    else       personStats[p].videoSpend += r.spend;
    // 只在对应类型下累计转化/高潜/点击/展示
    if (_personType === 'all' ||
        (_personType === 'video' && !isTw) ||
        (_personType === 'tuwen' && isTw)) {{
      personStats[p].conv += r.conversions;
      personStats[p].gq   += r.gaoquan;
      personStats[p].click += r.clicks;
      personStats[p].imp   += r.impressions;
    }}
    // 高潜成交率：基础名去重；高潜成交 = 深转>0（任一版本）；记录高潜成交素材名
    let bn = (r.name || '').replace(/\.mp4$/, '').replace(/-(\d)改$/, '').replace(/-改$/, '');
    if (!orderRateStats[p]) orderRateStats[p] = {{total:0, order:0, seen:new Set(), orderNames:[]}};
    if (!orderRateStats[p].seen.has(bn)) {{
      orderRateStats[p].seen.add(bn);
      orderRateStats[p].total += 1;
      if ((r.gaoquan || 0) > 0) {{
        orderRateStats[p].order += 1;
        orderRateStats[p].orderNames.push(r.name);
      }}
    }}
  }});

  // 按总消耗排序，过滤无数据的人
  const sorted = Object.values(personStats)
    .filter(d => (d.videoSpend + d.tuwenSpend) > 0)
    .sort((a,b) => (b.videoSpend+b.tuwenSpend) - (a.videoSpend+a.tuwenSpend));

  // 响应式列数
  const cols = Math.min(sorted.length, 4);
  container.style.gridTemplateColumns = `repeat(${{cols}},1fr)`;

  container.innerHTML = sorted.map(d => {{
    const p = d.person;
    const color = PERSON_COLORS[p] || '#94A3B8';
    const bg    = PERSON_BG[p]    || '#F8FAFC';
    const totalSpend = _personType === 'video' ? d.videoSpend :
                       _personType === 'tuwen' ? d.tuwenSpend :
                       d.videoSpend + d.tuwenSpend;
    const cpa = d.conv > 0 ? (totalSpend / d.conv).toFixed(2) : '—';
    const deepRate = d.conv > 0 ? (d.gq / d.conv * 100).toFixed(1) + '%' : '—';
    const ctr = d.imp > 0 ? (d.click / d.imp * 100).toFixed(2) + '%' : '—';
    const cvr = d.click > 0 ? (d.conv / d.click * 100).toFixed(2) + '%' : '—';

    // 过审率
    const pa = auditByPerson[p];
    let auditHtml = '';
    if (pa) {{
      const total = pa.pass.length + pa.fail.length;
      const rate  = total > 0 ? (pa.pass.length / total * 100).toFixed(1) : '0';
      const barColor = parseFloat(rate) >= 50 ? '#10B981' : parseFloat(rate) >= 25 ? '#F59E0B' : '#EF4444';
      const passNames = pa.pass.length > 0
        ? pa.pass.map(n => `<div style="padding:2px 0;border-bottom:1px solid rgba(255,255,255,.1)">${{n}}</div>`).join('')
        : '<div style="color:#94A3B8">无</div>';
      const failNames = pa.fail.length > 0
        ? pa.fail.map(n => `<div style="padding:2px 0;border-bottom:1px solid rgba(255,255,255,.1)">${{n}}</div>`).join('')
        : '<div style="color:#94A3B8">无</div>';
      auditHtml = `
        <div style="margin-top:8px;padding-top:8px;border-top:1px solid ${{color}}22">
          <div style="font-size:10px;color:#94A3B8;margin-bottom:4px">${{
            (auditData && auditData.source_file && auditData.source_file.includes('+'))
              ? '多日上传过审率（' + total + '条）'
              : '昨日上传过审率（' + total + '条）'
          }}</div>
          <div style="display:flex;align-items:center;gap:6px">
            <div style="flex:1;background:#F1F5F9;border-radius:20px;height:6px;overflow:hidden">
              <div style="height:100%;width:${{rate}}%;background:${{barColor}};border-radius:20px"></div>
            </div>
            <span style="font-size:12px;font-weight:700;color:${{barColor}};font-family:monospace">${{rate}}%</span>
          </div>
          <div class="audit-tooltip-trigger" style="font-size:10px;color:#94A3B8;margin-top:3px;cursor:pointer;position:relative">
            过审 ${{pa.pass.length}} / 未过审 ${{pa.fail.length}}
            <div class="audit-tooltip" style="display:none;position:absolute;bottom:100%;left:0;z-index:100;
              background:#1E3A8A;color:#fff;border-radius:8px;padding:10px 12px;min-width:180px;max-width:320px;
              max-height:320px;overflow-y:auto;
              font-size:11px;box-shadow:0 4px 12px rgba(0,0,0,.3);margin-bottom:4px">
              <div style="font-weight:600;margin-bottom:6px;color:#93C5FD">✓ 过审素材（${{pa.pass.length}}）</div>
              ${{passNames}}
              <div style="font-weight:600;margin:8px 0 6px;color:#FCA5A5">✗ 未过审素材（${{pa.fail.length}}）</div>
              ${{failNames}}
            </div>
          </div>
        </div>`;
    }}

    return `<div style="background:#fff;border:1.5px solid ${{color}}33;border-radius:10px;padding:14px 16px;box-shadow:0 1px 3px rgba(0,0,0,.06)">
      <div style="display:flex;align-items:center;gap:6px;margin-bottom:10px">
        <span style="width:8px;height:8px;border-radius:50%;background:${{color}};display:inline-block"></span>
        <span style="font-size:13px;font-weight:700;color:${{color}}">${{p}}</span>
      </div>
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:5px">
        <div style="background:#F8FAFC;border-radius:6px;padding:7px 9px">
          <div style="font-size:10px;color:#94A3B8;margin-bottom:1px">${{_personType==='tuwen' ? '图文消耗' : '视频消耗'}}</div>
          <div style="font-size:13px;font-weight:700;color:#1E40AF;font-family:monospace">¥${{(_personType==='tuwen' ? d.tuwenSpend : d.videoSpend).toFixed(2)}}</div>
        </div>
        <div style="background:#F8FAFC;border-radius:6px;padding:7px 9px">
          <div style="font-size:10px;color:#94A3B8;margin-bottom:1px">${{_personType==='all' ? '图文消耗' : '总消耗'}}</div>
          <div style="font-size:13px;font-weight:700;color:#8B5CF6;font-family:monospace">¥${{(_personType==='all' ? d.tuwenSpend : totalSpend).toFixed(2)}}</div>
        </div>        <div style="background:#F8FAFC;border-radius:6px;padding:7px 9px">
          <div style="font-size:10px;color:#94A3B8;margin-bottom:1px">转化数</div>
          <div style="font-size:13px;font-weight:700;color:#059669;font-family:monospace">${{d.conv}}</div>
        </div>
        <div style="background:#F8FAFC;border-radius:6px;padding:7px 9px">
          <div style="font-size:10px;color:#94A3B8;margin-bottom:1px">点击率</div>
          <div style="font-size:13px;font-weight:700;color:#3B82F6;font-family:monospace">${{ctr}}</div>
          <div style="font-size:10px;color:#94A3B8;margin-top:1px">点击 ${{d.click.toLocaleString('zh',{{maximumFractionDigits:0}})}}</div>
        </div>
        <div style="background:#F8FAFC;border-radius:6px;padding:7px 9px">
          <div style="font-size:10px;color:#94A3B8;margin-bottom:1px">转化率</div>
          <div style="font-size:13px;font-weight:700;color:#8B5CF6;font-family:monospace">${{cvr}}</div>
          <div style="font-size:10px;color:#94A3B8;margin-top:1px">转化 ${{d.conv}} / 点击 ${{d.click.toLocaleString('zh',{{maximumFractionDigits:0}})}}</div>
        </div>
        <div style="background:#F8FAFC;border-radius:6px;padding:7px 9px">
          <div style="font-size:10px;color:#94A3B8;margin-bottom:1px">高潜成交</div>
          <div style="font-size:13px;font-weight:700;color:#D97706;font-family:monospace">${{d.gq}}</div>
        </div>
        <div style="background:#F8FAFC;border-radius:6px;padding:7px 9px">
          <div style="font-size:10px;color:#94A3B8;margin-bottom:1px">CPA</div>
          <div style="font-size:13px;font-weight:700;color:#64748B;font-family:monospace">¥${{cpa}}</div>
        </div>
        <div style="background:#FFFBEB;border-radius:6px;padding:7px 9px">
          <div style="font-size:10px;color:#94A3B8;margin-bottom:1px">深转率</div>
          <div style="font-size:13px;font-weight:700;color:#D97706;font-family:monospace">${{deepRate}}</div>
        </div>
        <div style="background:#EFF6FF;border-radius:6px;padding:7px 9px">
          <div style="font-size:10px;color:#94A3B8;margin-bottom:1px">高潜成交率<span class="help-tip" data-tip="高潜成交率 = 深转>0 的素材数 ÷ 该编导总素材数；按名称基础名去重；跟随顶部日期筛选"></span></div>
          <div class="order-rate-value" style="font-size:13px;font-weight:700;color:#1E40AF;font-family:monospace" data-tip="${{orderTipOf(p)}}">${{orderRateOf(p)}}</div>
          <div style="font-size:10px;color:#64748B;margin-top:1px;font-family:monospace">${{orderFractionOf(p)}}</div>
        </div>
      </div>
      ${{auditHtml}}
    </div>`;
  }}).join('');

  // tooltip hover 交互
  container.querySelectorAll('.audit-tooltip-trigger').forEach(el => {{
    const tip = el.querySelector('.audit-tooltip');
    el.addEventListener('mouseenter', () => {{ if(tip) tip.style.display = 'block'; }});
    el.addEventListener('mouseleave', () => {{ if(tip) tip.style.display = 'none'; }});
  }});

  function orderRateOf(p) {{
    const s = orderRateStats[p];
    if (!s || s.total === 0) return '—';
    return (s.order / s.total * 100).toFixed(0) + '%';
  }}
  function orderFractionOf(p) {{
    const s = orderRateStats[p];
    if (!s) return '—';
    return s.order + ' / ' + s.total + ' 条';
  }}
  function orderTipOf(p) {{
    const s = orderRateStats[p];
    if (!s) return '暂无数据';
    const names = (s.orderNames || []).slice(0, 20).join('、');
    const more = (s.orderNames || []).length > 20 ? ' 等' : '';
    return '高潜成交素材（' + s.order + ' 条）: ' + (names || '无') + more + ' ｜ 分母（总素材数）: ' + s.total + ' 条';
  }}
}}

function updateTypeCards(rows) {{  const container = document.getElementById('typeCardsRow');
  if (!container) return;

  // 全量数据（用于计算占比）
  const allRows = rows; // rows 已是当前选中日期的合并数据
  const totSpend = allRows.reduce((s, r) => s + r.spend, 0);
  const totConv  = allRows.reduce((s, r) => s + r.conversions, 0);
  const totGq    = allRows.reduce((s, r) => s + r.gaoquan, 0);

  // 单日视图时，计算前一日各类型的差值（加减法）
  let prevByType = null;
  if (_currentDateLabel && ALL_DATES.length > 1) {{
    const idx = ALL_DATES.indexOf(_currentDateLabel);
    if (idx > 0) {{
      const prevLabel = ALL_DATES[idx - 1];
      const prevRows = ALL_ROWS_BY_DATE[prevLabel] || [];
      prevByType = {{ video: {{spend:0,imp:0,click:0,conv:0,gq:0}}, tuwen: {{spend:0,imp:0,click:0,conv:0,gq:0}}, ai: {{spend:0,imp:0,click:0,conv:0,gq:0}} }};
      prevRows.forEach(r => {{
        const t = r.is_ai ? 'ai' : r.is_tuwen ? 'tuwen' : 'video';
        const p = prevByType[t];
        p.spend += r.spend; p.imp += r.impressions; p.click += r.clicks;
        p.conv += r.conversions; p.gq += r.gaoquan;
      }});
    }}
  }}

  const diffFmt = (label, curVal, prevVal, digits, prefix, suffix) => {{
    const d = curVal - prevVal;
    if (d === 0) return '<span>' + label + ' ±0</span>';
    const sign = d > 0 ? '+' : '-';
    const cls = d > 0 ? 'inc' : 'dec';
    return '<span>' + label + ' <span class="tc-diff ' + cls + '">' + sign + prefix + Math.abs(d).toFixed(digits) + suffix + '</span></span>';
  }};

  const types = [
    {{ key: 'video',    label: '视频', color: '#3B82F6', bg: '#EFF6FF',
       filter: r => !r.is_tuwen }},
    {{ key: 'tuwen',   label: '图文', color: '#8B5CF6', bg: '#F5F3FF',
       filter: r => r.is_tuwen }},
    {{ key: 'ai',      label: 'Ai',   color: '#6366F1', bg: '#EEF2FF',
       filter: r => r.is_ai }},
  ];

  container.innerHTML = types.map(t => {{
    const filtered = allRows.filter(r => r.spend > 0 && t.filter(r));
    const spend = filtered.reduce((s, r) => s + r.spend, 0);
    const conv  = filtered.reduce((s, r) => s + r.conversions, 0);
    const gq    = filtered.reduce((s, r) => s + r.gaoquan, 0);
    const click = filtered.reduce((s, r) => s + r.clicks, 0);
    const imp   = filtered.reduce((s, r) => s + r.impressions, 0);
    const cpa   = conv > 0 ? (spend / conv).toFixed(2) : '—';
    const deepRate = conv > 0 ? (gq / conv * 100).toFixed(1) + '%' : '—';
    const ctr = imp > 0 ? (click / imp * 100).toFixed(2) + '%' : '—';
    const cvr = click > 0 ? (conv / click * 100).toFixed(2) + '%' : '—';
    const spendPct = totSpend > 0 ? (spend / totSpend * 100).toFixed(1) : '0';
    const convPct  = totConv  > 0 ? (conv  / totConv  * 100).toFixed(1) : '0';
    const gqPct    = totGq    > 0 ? (gq    / totGq    * 100).toFixed(1) : '0';

    return `<div style="background:#fff;border:1.5px solid ${{t.color}}33;border-radius:10px;padding:14px 16px;box-shadow:0 1px 3px rgba(0,0,0,.06)">
      <div style="display:flex;align-items:center;gap:6px;margin-bottom:10px">
        <span style="width:8px;height:8px;border-radius:50%;background:${{t.color}};display:inline-block"></span>
        <span style="font-size:13px;font-weight:700;color:${{t.color}}">${{t.label}}</span>
        <span style="font-size:11px;color:#94A3B8;margin-left:auto">${{filtered.length}} 条素材${{t.key==='ai' ? '（已含于视频/图文）' : ''}}</span>
      </div>
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:6px">
        <div style="background:#F8FAFC;border-radius:6px;padding:8px 10px">
          <div style="font-size:10px;color:#94A3B8;margin-bottom:2px">消耗</div>
          <div style="font-size:15px;font-weight:700;color:#1E40AF;font-family:monospace">¥${{spend.toLocaleString('zh',{{minimumFractionDigits:2,maximumFractionDigits:2}})}}</div>
          <div style="font-size:10px;color:${{t.color}};margin-top:2px">占比 ${{spendPct}}%</div>
        </div>
        <div style="background:#F8FAFC;border-radius:6px;padding:8px 10px">
          <div style="font-size:10px;color:#94A3B8;margin-bottom:2px">转化数</div>
          <div style="font-size:15px;font-weight:700;color:#059669;font-family:monospace">${{conv}}</div>
          <div style="font-size:10px;color:${{t.color}};margin-top:2px">占比 ${{convPct}}%</div>
        </div>
        <div style="background:#F8FAFC;border-radius:6px;padding:8px 10px">
          <div style="font-size:10px;color:#94A3B8;margin-bottom:2px">点击率</div>
          <div style="font-size:15px;font-weight:700;color:#3B82F6;font-family:monospace">${{ctr}}</div>
          <div style="font-size:10px;color:${{t.color}};margin-top:2px">点击 ${{click.toLocaleString('zh',{{maximumFractionDigits:0}})}}</div>
        </div>
        <div style="background:#F8FAFC;border-radius:6px;padding:8px 10px">
          <div style="font-size:10px;color:#94A3B8;margin-bottom:2px">转化率</div>
          <div style="font-size:15px;font-weight:700;color:#8B5CF6;font-family:monospace">${{cvr}}</div>
          <div style="font-size:10px;color:${{t.color}};margin-top:2px">转化 ${{conv}} / 点击 ${{click.toLocaleString('zh',{{maximumFractionDigits:0}})}}</div>
        </div>
        <div style="background:#F8FAFC;border-radius:6px;padding:8px 10px">
          <div style="font-size:10px;color:#94A3B8;margin-bottom:2px">高潜成交</div>
          <div style="font-size:15px;font-weight:700;color:#D97706;font-family:monospace">${{gq}}</div>
          <div style="font-size:10px;color:${{t.color}};margin-top:2px">占比 ${{gqPct}}%</div>
        </div>
        <div style="background:#F8FAFC;border-radius:6px;padding:8px 10px">
          <div style="font-size:10px;color:#94A3B8;margin-bottom:2px">CPA</div>
          <div style="font-size:15px;font-weight:700;color:#64748B;font-family:monospace">¥${{cpa}}</div>
        </div>
        <div style="background:#FFFBEB;border-radius:6px;padding:8px 10px;grid-column:span 2">
          <div style="font-size:10px;color:#94A3B8;margin-bottom:2px">深转率（高潜/转化）</div>
          <div style="font-size:15px;font-weight:700;color:#D97706;font-family:monospace">${{deepRate}}</div>
        </div>
      </div>
      ${{prevByType ? (() => {{
        const p = prevByType[t.key];
        const pCpa = p.conv > 0 ? p.spend / p.conv : 0;
        const pCtr = p.imp > 0 ? p.click / p.imp * 100 : 0;
        const pCvr = p.click > 0 ? p.conv / p.click * 100 : 0;
        const cCtr = imp > 0 ? click / imp * 100 : 0;
        const cCvr = click > 0 ? conv / click * 100 : 0;
        const cCpa = conv > 0 ? spend / conv : 0;
        return `<div style="margin-top:8px;padding-top:8px;border-top:1px dashed ${{t.color}}44;font-size:11px;color:#64748B;line-height:1.9">
          <div style="font-weight:600;margin-bottom:2px;color:#94A3B8">较昨日</div>
          ${{diffFmt('消耗', spend, p.spend, 2, '¥', '')}}　
          ${{diffFmt('展示', imp, p.imp, 0, '', '')}}　
          ${{diffFmt('点击', click, p.click, 0, '', '')}}<br>
          ${{diffFmt('点击率', cCtr, pCtr, 2, '', '%')}}　
          ${{diffFmt('转化率', cCvr, pCvr, 2, '', '%')}}　
          ${{diffFmt('转化', conv, p.conv, 0, '', '')}}<br>
          ${{diffFmt('高潜', gq, p.gq, 0, '', '')}}　
          ${{diffFmt('CPA', cCpa, pCpa, 2, '¥', '')}}
        </div>`;
      }})() : ''}}
    </div>`;
  }}).join('');
}}

function updateAuditCards(data) {{
  if (!data || !data.version_labels) {{
    const c = document.getElementById('auditCardsRow');
    if (c) c.innerHTML = '<div style="color:#94A3B8;font-size:12px;padding:20px;text-align:center;grid-column:span 4">暂无过审数据</div>';
    const tc = document.getElementById('auditTagCardsRow');
    if (tc) tc.innerHTML = '<div style="color:#94A3B8;font-size:12px;padding:12px;grid-column:span 5">暂无数据</div>';
    const sl = document.getElementById('auditSourceLabel');
    if (sl) sl.textContent = '';
    return;
  }}

  const srcLabel = document.getElementById('auditSourceLabel');
  if (srcLabel) srcLabel.textContent = data.source_file ? '数据来源：' + data.source_file : '';
  const titleEl = document.getElementById('auditSectionTitle');
  if (titleEl) titleEl.textContent = (data.source_file && data.source_file.includes('+'))
    ? '多日新上传视频过审率（按改版）'
    : '昨日新上传视频过审率（按改版）';
  const container = document.getElementById('auditCardsRow');
  if (!container) return;
  const labels = data.version_labels;
  container.innerHTML = labels.map((ver, i) => {{
    const pass  = data.pass_counts[i];
    const fail  = data.fail_counts[i];
    const total = pass + fail;
    const rate  = data.pass_rates[i];
    const barW  = rate + '%';
    const color = rate >= 50 ? '#10B981' : rate >= 25 ? '#F59E0B' : '#EF4444';
    const borderColor = ver === '代理素材' ? '#F97316' : '#E2E8F0';
    return `<div style="background:#fff;border:1.5px solid ${{borderColor}};border-radius:10px;padding:14px 16px;
                        box-shadow:0 1px 3px rgba(0,0,0,.06)">
      <div style="font-size:13px;font-weight:700;color:#1E3A8A;margin-bottom:10px">${{ver}}</div>
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:6px;margin-bottom:10px">
        <div style="background:#ECFDF5;border-radius:6px;padding:8px 10px;text-align:center">
          <div style="font-size:10px;color:#059669;margin-bottom:2px">过审</div>
          <div style="font-size:18px;font-weight:700;color:#059669;font-family:monospace">${{pass}}</div>
        </div>
        <div style="background:#FEF2F2;border-radius:6px;padding:8px 10px;text-align:center">
          <div style="font-size:10px;color:#DC2626;margin-bottom:2px">未过审</div>
          <div style="font-size:18px;font-weight:700;color:#DC2626;font-family:monospace">${{fail}}</div>
        </div>
      </div>
      <div style="font-size:10px;color:#94A3B8;margin-bottom:4px">过审率（共${{total}}条）</div>
      <div style="background:#F1F5F9;border-radius:20px;height:8px;overflow:hidden">
        <div style="height:100%;width:${{barW}};background:${{color}};border-radius:20px;transition:width .3s"></div>
      </div>
      <div style="font-size:14px;font-weight:700;color:${{color}};margin-top:4px;font-family:monospace">${{rate}}%</div>
    </div>`;
  }}).join('');

  if (labels.length === 0) {{
    container.innerHTML = '<div style="color:#94A3B8;font-size:12px;padding:20px;text-align:center;grid-column:span 4">暂无过审数据</div>';
  }}

  // 按标签过审卡片
  const tagContainer = document.getElementById('auditTagCardsRow');
  if (tagContainer && data.tag_labels && data.tag_labels.length > 0) {{
    const TAG_COLOR_MAP = {{'A1':'#3B82F6','A2':'#8B5CF6','A3':'#10B981','A4':'#F59E0B','AI':'#6366F1','Ai':'#6366F1','未标记':'#94A3B8'}};
    tagContainer.innerHTML = data.tag_labels.map((tag, i) => {{
      const pass = data.tag_pass_counts[i];
      const fail = data.tag_fail_counts[i];
      const total = pass + fail;
      const rate = data.tag_pass_rates[i];
      const color = TAG_COLOR_MAP[tag] || '#94A3B8';
      const barColor = rate >= 50 ? '#10B981' : rate >= 25 ? '#F59E0B' : '#EF4444';
      return `<div style="background:#fff;border:1.5px solid ${{color}}33;border-radius:10px;padding:14px 16px;box-shadow:0 1px 3px rgba(0,0,0,.06)">
        <div style="font-size:13px;font-weight:700;color:${{color}};margin-bottom:10px">${{tag === 'AI' ? 'Ai' : tag}}</div>
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:6px;margin-bottom:10px">
          <div style="background:#ECFDF5;border-radius:6px;padding:8px 10px;text-align:center">
            <div style="font-size:10px;color:#059669;margin-bottom:2px">过审</div>
            <div style="font-size:18px;font-weight:700;color:#059669;font-family:monospace">${{pass}}</div>
          </div>
          <div style="background:#FEF2F2;border-radius:6px;padding:8px 10px;text-align:center">
            <div style="font-size:10px;color:#DC2626;margin-bottom:2px">未过审</div>
            <div style="font-size:18px;font-weight:700;color:#DC2626;font-family:monospace">${{fail}}</div>
          </div>
        </div>
        <div style="font-size:10px;color:#94A3B8;margin-bottom:4px">过审率（共${{total}}条）</div>
        <div style="background:#F1F5F9;border-radius:20px;height:8px;overflow:hidden">
          <div style="height:100%;width:${{rate}}%;background:${{barColor}};border-radius:20px"></div>
        </div>
        <div style="font-size:14px;font-weight:700;color:${{barColor}};margin-top:4px;font-family:monospace">${{rate}}%</div>
      </div>`;
    }}).join('');
  }} else if (tagContainer) {{
    tagContainer.innerHTML = '<div style="color:#94A3B8;font-size:12px;padding:12px;grid-column:span 5">标签数据待补充</div>';
  }}
}}

// ---------- 问号 tooltip 跟随定位 ----------
document.addEventListener('mouseover', e => {{
  const tip = e.target.closest && e.target.closest('.help-tip');
  if (!tip) return;
  const rect = tip.getBoundingClientRect();
  const tipW = Math.min(380, (tip.getAttribute('data-tip') || '').length * 12 + 20);
  let left = rect.left + rect.width/2 - tipW/2;
  left = Math.max(8, Math.min(left, window.innerWidth - tipW - 8));
  const style = document.createElement('style');
  style.id = 'helpTipPos';
  style.textContent = `.help-tip:hover::after{{left:${{left}}px !important;top:${{rect.top - 8}}px !important;transform:none !important}}`;
  document.getElementById('helpTipPos')?.remove();
  document.head.appendChild(style);
}}, true);

// ---------- 卡审分析 & 近3周跑出 ----------
let analysisMode = 'delivery';        // delivery(投放账户) | test(测试账户)
let rejFilter = 'all';               // delivery: all/immediate/inuse/ok；test: all/pass/fail/eco/unknown
let REJ_DATES = [ALL_DATES[ALL_DATES.length - 1]];  // 跟随顶部日期筛选（'MM/DD'）
let _weekExpanded = false;
let rejSortCol = 'first_day';
let rejSortAsc = false;
let passSortCol = 'spend';
let passSortAsc = false;

const REJ_VERSIONS = ['0改', '1改', '2改', '3改', '全部'];

function fmtDate(mmdd) {{
  if (!mmdd) return '<span style="color:var(--text-muted)">—</span>';
  return mmdd.slice(0,2) + '/' + mmdd.slice(2);
}}

function labelToKey(label) {{ return label.replace('/', ''); }}   // '10/20' → '1020'

function setRejDates(dates) {{
  REJ_DATES = dates;
  updatePassWeekLabels();
  renderRejectModules();
}}

function setAnalysisMode(mode, btn) {{
  analysisMode = mode;
  document.querySelectorAll('#modeDelivery,#modeTest').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  rejFilter = 'all';
  setupModeUI();
  renderRejectModules();
}}

function setupModeUI() {{
  const isTest = analysisMode === 'test';
  // 口径说明
  const desc = document.getElementById('analysisModeDesc');
  if (desc) {{
    desc.textContent = isTest
      ? '测试账户口径：过审文件（-过审 CSV）按素材id去重统计；状态分 通过 / 普通不通过 / 生态风险 / 未知 四类；日期 = 过审文件对应日期，跟随顶部日期筛选；比例分母均为提交数。'
      : '投放账户口径：测试账户推送（名称「推送视频_」开头）到投放账户后，审核建议出现过「不通过」；状态单调不回退。刚推送卡审 = 卡审前消耗为0；用着用着卡审 = 卡审前已有消耗。卡片/明细按推送日统计，跟随顶部日期筛选；比例分母均为推送数。';
  }}
  // 明细标题
  const lt = document.getElementById('rejectListTitle');
  if (lt) lt.innerHTML = (isTest ? '测试账户素材明细 ' : '推送素材去向明细 ') +
    '<span id="rejectListCount" style="color:var(--text-muted);font-weight:400"></span>';
  // 筛选按钮组
  const fg = document.getElementById('rejFilterGroup');
  if (fg) {{
    if (isTest) {{
      fg.innerHTML = `
        <button class="sort-btn active" id="rejFilterAll" onclick="setRejFilter('all',this)">全部</button>
        <button class="sort-btn" id="rejFilterPass" style="color:#059669" onclick="setRejFilter('pass',this)">通过</button>
        <button class="sort-btn" id="rejFilterFail" style="color:#DC2626" onclick="setRejFilter('fail',this)">不通过</button>
        <button class="sort-btn" id="rejFilterEco" style="color:#F59E0B" onclick="setRejFilter('eco',this)">生态风险</button>
        <button class="sort-btn" id="rejFilterUnknown" style="color:#94A3B8" onclick="setRejFilter('unknown',this)">未知</button>`;
    }} else {{
      fg.innerHTML = `
        <button class="sort-btn active" id="rejFilterAll" onclick="setRejFilter('all',this)">全部</button>
        <button class="sort-btn" id="rejFilterImmediate" style="color:#DC2626" onclick="setRejFilter('immediate',this)">刚推送卡审</button>
        <button class="sort-btn" id="rejFilterInuse" style="color:#D97706" onclick="setRejFilter('inuse',this)">用着用着卡审</button>
        <button class="sort-btn" id="rejFilterOk" style="color:#059669" onclick="setRejFilter('ok',this)">推送后未卡审</button>`;
    }}
  }}
  // 表头
  const dayHead = document.getElementById('rejectDayHead');
  if (dayHead) {{
    dayHead.innerHTML = isTest
      ? `<tr><th>提交日</th><th style="text-align:center">提交数</th><th style="text-align:center">通过数</th><th style="text-align:center">通过率</th><th style="text-align:center">环比昨日</th><th style="text-align:center">0改</th><th style="text-align:center">1改</th><th style="text-align:center">2改</th><th style="text-align:center">3改</th></tr>`
      : `<tr><th>推送日</th><th style="text-align:center">推送数</th><th style="text-align:center">通过数</th><th style="text-align:center">通过率</th><th style="text-align:center">环比昨日</th><th style="text-align:center">0改</th><th style="text-align:center">1改</th><th style="text-align:center">2改</th><th style="text-align:center">3改</th></tr>`;
  }}
  const weekHead = document.getElementById('rejectWeekHead');
  if (weekHead) {{
    weekHead.innerHTML = isTest
      ? `<tr><th>提交周</th><th style="text-align:center">提交数</th><th style="text-align:center">通过数</th><th style="text-align:center">通过率</th><th style="text-align:center">环比上周</th><th style="text-align:center">0改</th><th style="text-align:center">1改</th><th style="text-align:center">2改</th><th style="text-align:center">3改</th></tr>`
      : `<tr><th>推送周</th><th style="text-align:center">推送数</th><th style="text-align:center">通过数</th><th style="text-align:center">通过率</th><th style="text-align:center">环比上周</th><th style="text-align:center">0改</th><th style="text-align:center">1改</th><th style="text-align:center">2改</th><th style="text-align:center">3改</th></tr>`;
  }}
  const listHead = document.getElementById('rejectListHead');
  if (listHead) {{
    listHead.innerHTML = isTest
      ? `<tr><th data-col="name">素材名称</th><th data-col="version">改版</th><th data-col="audit_day">提交日</th><th>审核结果</th></tr>`
      : `<tr><th data-col="name">素材名称</th><th data-col="version">改版</th><th>账户</th><th data-col="first_day">推送日</th><th data-col="first_rej_day" class="sorted-desc">卡审日 ↓</th><th>去向</th><th>视频</th></tr>`;
  }}
  bindRejectSorts();
}}

function setRejFilter(filter, btn) {{
  rejFilter = filter;
  document.querySelectorAll('#rejFilterGroup .sort-btn').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  renderRejectList();
}}

function rejectRowHtml(key, row, isDay, prevRow) {{
  const all = row['全部'] || {{pushed:0,rejected:0,reject_rate:0,ok:0}};
  const okCount = all.ok || 0;
  const okRate = all.pushed > 0 ? Math.round(okCount/all.pushed*1000)/10 : 0;
  // 环比昨日：通过率与前一个推送日的差值（加减法）
  let momHtml = '<span style="color:var(--text-muted)">—</span>';
  if (isDay && prevRow) {{
    const prevAll = prevRow['全部'] || {{pushed:0,ok:0}};
    if (prevAll.pushed > 0) {{
      const prevOkRate = Math.round(prevAll.ok/prevAll.pushed*1000)/10;
      const diff = okRate - prevOkRate;
      if (Math.abs(diff) < 0.05) momHtml = '<span style="color:#64748B">持平</span>';
      else if (diff > 0) momHtml = '<span style="color:#059669;font-weight:600">↑' + diff.toFixed(1) + 'pp</span>';
      else momHtml = '<span style="color:#DC2626;font-weight:600">↓' + Math.abs(diff).toFixed(1) + 'pp</span>';
    }}
  }}
  const cells = ['0改','1改','2改','3改'].map(v => {{
    const b = row[v] || {{pushed:0,ok:0}};
    if (!b.pushed) return '<td style="text-align:center;color:var(--text-muted)">—</td>';
    const vr = Math.round(b.ok/b.pushed*1000)/10;
    return `<td style="font-family:monospace;text-align:center">${{b.ok}}/${{b.pushed}}<br><span style="color:${{vr >= 80 ? '#059669' : vr >= 50 ? '#D97706' : '#DC2626'}};font-size:10px">${{vr}}%</span></td>`;
  }}).join('');
  return `<tr>
    <td style="font-weight:600">${{isDay ? fmtDate(key) : key}}</td>
    <td style="text-align:center">${{all.pushed}}</td>
    <td style="color:#059669;font-weight:600;text-align:center">${{okCount}}</td>
    <td style="font-family:monospace;text-align:center">${{okRate}}%</td>
    ${{isDay ? `<td style="text-align:center">${{momHtml}}</td>` : ''}}
    ${{cells}}
  </tr>`;
}}

function renderRejectBucketTable() {{
  const tbody = document.getElementById('rejectBucketBody');
  if (!tbody) return;
  if (analysisMode === 'test') {{
    renderTestDayTable(tbody);
  }} else {{
    const views = REJECT_ANALYSIS.views || {{}};
    // 分日明细：只显示顶部选中的日期；环比基准取全量日序列的前一天
    const d = views.day || {{}};
    const dayKeys = Object.keys(d).sort();
    const keys = REJ_DATES.map(labelToKey).filter(k => d[k]);
    tbody.innerHTML = keys.map(k => {{
      const idx = dayKeys.indexOf(k);
      const prevRow = idx > 0 ? d[dayKeys[idx - 1]] : null;
      return rejectRowHtml(k, d[k], true, prevRow);
    }}).join('') ||
      '<tr><td colspan="9" style="color:#94A3B8;text-align:center;padding:10px">选中日期无推送数据</td></tr>';
  }}
  renderRejectWeekTable();
}}

function renderTestDayTable(tbody) {{
  const d = (TEST_AUDIT_ANALYSIS.views || {{}}).day || {{}};
  const dayKeys = Object.keys(d).sort();
  const keys = REJ_DATES.map(labelToKey).filter(k => d[k]);
  tbody.innerHTML = keys.map(k => {{
    const idx = dayKeys.indexOf(k);
    const prevRow = idx > 0 ? d[dayKeys[idx - 1]] : null;
    return testRowHtml(k, d[k], true, prevRow);
  }}).join('') ||
    '<tr><td colspan="9" style="color:#94A3B8;text-align:center;padding:10px">选中日期无提交数据</td></tr>';
}}

function testRowHtml(key, row, isDay, prevRow) {{
  const all = row['全部'] || {{submitted:0,pass:0,fail:0,eco:0,unknown:0,pass_rate:0,fail_rate:0}};
  let momHtml = '<span style="color:var(--text-muted)">—</span>';
  if (isDay && prevRow) {{
    const prevAll = prevRow['全部'] || {{submitted:0,pass_rate:0}};
    if (prevAll.submitted > 0) {{
      const diff = all.pass_rate - prevAll.pass_rate;
      if (Math.abs(diff) < 0.05) momHtml = '<span style="color:#64748B">持平</span>';
      else if (diff > 0) momHtml = '<span style="color:#059669;font-weight:600">↑' + diff.toFixed(1) + 'pp</span>';
      else momHtml = '<span style="color:#DC2626;font-weight:600">↓' + Math.abs(diff).toFixed(1) + 'pp</span>';
    }}
  }}
  const cells = ['0改','1改','2改','3改'].map(v => {{
    const b = row[v] || {{submitted:0,pass:0,fail:0,eco:0,unknown:0,pass_rate:0,fail_rate:0}};
    return b.submitted > 0
      ? `<td style="font-family:monospace;text-align:center">${{b.pass}}/${{b.submitted}}<br><span style="color:${{b.pass_rate >= 50 ? '#059669' : b.pass_rate >= 20 ? '#D97706' : '#DC2626'}};font-size:10px">${{b.pass_rate}}%</span></td>`
      : '<td style="text-align:center;color:var(--text-muted)">—</td>';
  }}).join('');
  return `<tr>
    <td style="font-weight:600">${{isDay ? fmtDate(key) : key}}</td>
    <td style="text-align:center">${{all.submitted}}</td>
    <td style="color:#059669;font-weight:600;text-align:center">${{all.pass}}</td>
    <td style="font-family:monospace;text-align:center">${{all.pass_rate}}%</td>
    ${{isDay ? `<td style="text-align:center">${{momHtml}}</td>` : ''}}
    ${{cells}}
  </tr>`;
}}

function renderRejectWeekTable() {{
  const weekBody = document.getElementById('rejectWeekBody');
  if (!weekBody) return;
  const isTest = analysisMode === 'test';
  const d = isTest
    ? ((TEST_AUDIT_ANALYSIS.views || {{}}).week || {{}})
    : ((REJECT_ANALYSIS.views || {{}}).week || {{}});
  const dayWeekMap = isTest
    ? (TEST_AUDIT_ANALYSIS.day_week_map || {{}})
    : (REJECT_ANALYSIS.day_week_map || {{}});
  const weekRangeMap = isTest
    ? (TEST_AUDIT_ANALYSIS.week_range_map || {{}})
    : (REJECT_ANALYSIS.week_range_map || {{}});
  const weekLabel = k => {{
    const rng = weekRangeMap[k];
    if (rng && rng[0] && rng[1]) {{
      return k + '（' + fmtDate(rng[0]).replace(/<[^>]+>/g,'') + '-' + fmtDate(rng[1]).replace(/<[^>]+>/g,'') + '）';
    }}
    return k;
  }};
  const allKeys = Object.keys(d).sort();
  if (!allKeys.length) {{ weekBody.innerHTML = ''; return; }}

  // 选中日期覆盖的周（直接用 Python 下发的 ISO 周映射）
  const selWeeks = new Set(REJ_DATES.map(dd => dayWeekMap[labelToKey(dd)]).filter(Boolean));
  // 周排序：解析 ISO key 为可比较字符串（年份+周数补零）
  const weekSort = k => {{
    const m = k.match(/(\\d{{4}})-W(\\d{{2}})/);
    return m ? m[1] + m[2] : k;
  }};
  const ordered = [...allKeys].sort((a, b) => weekSort(a) < weekSort(b) ? -1 : 1);

  // 要显示的周：展开时全部；收起时 = 选中覆盖的全部周 + 最早上周（环比基准）
  let showKeys;
  if (_weekExpanded) {{
    showKeys = ordered;
  }} else {{
    const selIdxs = ordered.map((k, i) => selWeeks.has(k) ? i : -1).filter(i => i >= 0);
    if (!selIdxs.length) {{
      showKeys = ordered.slice(-2);
    }} else {{
      const minIdx = Math.min(...selIdxs);
      const maxIdx = Math.max(...selIdxs);
      showKeys = ordered.slice(Math.max(0, minIdx - 1), maxIdx + 1);
    }}
  }}
  weekBody.innerHTML = showKeys.map((k, i) => {{
    const cur = d[k] || {{}};
    const all = cur['全部'] || (isTest ? {{submitted:0,pass:0,fail:0,eco:0,unknown:0,pass_rate:0,fail_rate:0}} : {{pushed:0,rejected:0,reject_rate:0,ok:0}});
    // 环比：上一周（ordered 中前一个）
    const oi = ordered.indexOf(k);
    const prevCur = oi > 0 ? (d[ordered[oi-1]] || {{}}) : null;
    const prevAll = prevCur ? (prevCur['全部'] || null) : null;
    let momHtml = '<span style="color:var(--text-muted)">—</span>';
    if (prevAll && prevAll[isTest ? 'submitted' : 'pushed'] > 0) {{
      const curRate = isTest ? all.pass_rate : (all.pushed > 0 ? Math.round(all.ok/all.pushed*1000)/10 : 0);
      const prevRate = isTest ? prevAll.pass_rate : (prevAll.pushed > 0 ? Math.round(prevAll.ok/prevAll.pushed*1000)/10 : 0);
      const diff = curRate - prevRate;
      if (Math.abs(diff) < 0.05) momHtml = '<span style="color:#64748B">持平</span>';
      else if (diff > 0) momHtml = '<span style="color:#059669;font-weight:600">↑' + diff.toFixed(1) + 'pp</span>';
      else momHtml = '<span style="color:#DC2626;font-weight:600">↓' + Math.abs(diff).toFixed(1) + 'pp</span>';
    }}
    const cells = ['0改','1改','2改','3改'].map(v => {{
      const b = cur[v] || null;
      if (!b) return '<td style="text-align:center;color:var(--text-muted)">—</td>';
      if (isTest) {{
        return b.submitted > 0
          ? `<td style="font-family:monospace;text-align:center">${{b.pass}}/${{b.submitted}}<br><span style="color:${{b.pass_rate >= 50 ? '#059669' : b.pass_rate >= 20 ? '#D97706' : '#DC2626'}};font-size:10px">${{b.pass_rate}}%</span></td>`
          : '<td style="text-align:center;color:var(--text-muted)">—</td>';
      }}
      if (!b.pushed) return '<td style="text-align:center;color:var(--text-muted)">—</td>';
      const vr = Math.round(b.ok/b.pushed*1000)/10;
      return `<td style="font-family:monospace;text-align:center">${{b.ok}}/${{b.pushed}}<br><span style="color:${{vr >= 80 ? '#059669' : vr >= 50 ? '#D97706' : '#DC2626'}};font-size:10px">${{vr}}%</span></td>`;
    }}).join('');
    const total = isTest ? all.submitted : all.pushed;
    const okCount = isTest ? all.pass : (all.ok || 0);
    const okRate = isTest ? all.pass_rate : (all.pushed > 0 ? Math.round(all.ok/all.pushed*1000)/10 : 0);
    return `<tr>
      <td style="font-weight:600">${{weekLabel(k)}}</td>
      <td style="text-align:center">${{total}}</td>
      <td style="color:#059669;font-weight:600;text-align:center">${{okCount}}</td>
      <td style="font-family:monospace;text-align:center">${{okRate}}%</td>
      <td style="text-align:center">${{momHtml}}</td>
      ${{cells}}
    </tr>`;
  }}).join('');
}}

function toggleWeekExpand() {{
  _weekExpanded = !_weekExpanded;
  const btn = document.getElementById('rejWeekExpandBtn');
  if (btn) btn.textContent = _weekExpanded ? '收起 ▴' : '查看全部周 ▾';
  renderRejectWeekTable();
}}

function renderRejectCards() {{
  const container = document.getElementById('rejectCardsRow');
  const scopeEl = document.getElementById('rejScopeLabel');
  if (!container) return;
  if (analysisMode === 'test') {{
    renderTestCards(container, scopeEl);
    return;
  }}
  const views = REJECT_ANALYSIS.views || {{}};
  // 卡片跟随顶部日期筛选：合并选中日期对应的日桶
  const keys = REJ_DATES.map(labelToKey);
  const row = {{}};
  keys.forEach(k => {{
    const dayRow = (views.day || {{}})[k];
    if (!dayRow) return;
    REJ_VERSIONS.forEach(v => {{
      const b = dayRow[v];
      if (!b) return;
      if (!row[v]) row[v] = {{pushed:0,rejected:0,immediate:0,inuse:0,ok:0}};
      row[v].pushed += b.pushed;
      row[v].rejected += b.rejected;
      row[v].immediate += b.immediate;
      row[v].inuse += b.inuse;
      row[v].ok += b.ok;
    }});
  }});
  REJ_VERSIONS.forEach(v => {{
    if (!row[v]) return;
    const t = row[v].pushed, r = row[v].rejected;
    row[v].reject_rate = t ? Math.round(r/t*1000)/10 : 0;
    row[v].immediate_pct = t ? Math.round(row[v].immediate/t*1000)/10 : 0;
    row[v].inuse_pct = t ? Math.round(row[v].inuse/t*1000)/10 : 0;
    row[v].ok_pct = t ? Math.round(row[v].ok/t*1000)/10 : 0;
  }});
  if (scopeEl) {{
    scopeEl.textContent = REJ_DATES.length === 1
      ? '（' + REJ_DATES[0] + ' 推送）'
      : '（' + REJ_DATES.length + ' 天合并）';
  }}
  const cards = REJ_VERSIONS.filter(v => (row[v] && row[v].pushed > 0) || v === '全部');
  container.style.gridTemplateColumns = 'repeat(' + Math.min(cards.length, 5) + ',1fr)';
  container.innerHTML = cards.map(v => {{
    const b = row[v] || {{pushed:0,rejected:0,reject_rate:0,immediate:0,inuse:0,ok:0,immediate_pct:0,inuse_pct:0,ok_pct:0}};
    const isAll = v === '全部';
    return `<div style="background:#fff;border:1.5px solid ${{isAll ? '#94A3B8' : '#E2E8F0'}};border-radius:10px;padding:14px 16px;box-shadow:0 1px 3px rgba(0,0,0,.06)">
      <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:8px">
        <div style="font-size:13px;font-weight:700;color:#1E3A8A">${{isAll ? '合计' : v}}</div>
        <div style="font-size:10px;color:#94A3B8">素材 ${{b.pushed}} 条</div>
      </div>
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:6px;margin-bottom:8px">
        <div style="background:#ECFDF5;border-radius:6px;padding:7px 9px;text-align:center">
          <div style="font-size:10px;color:#059669;margin-bottom:2px">通过</div>
          <div style="font-size:16px;font-weight:700;color:#059669;font-family:monospace">${{b.ok}}</div>
          <div style="font-size:10px;color:#059669;font-family:monospace">${{b.ok_pct}}%</div>
        </div>
        <div style="background:#FEF2F2;border-radius:6px;padding:7px 9px;text-align:center">
          <div style="font-size:10px;color:#DC2626;margin-bottom:2px">不通过</div>
          <div style="font-size:16px;font-weight:700;color:#DC2626;font-family:monospace">${{b.rejected}}</div>
          <div style="font-size:10px;color:#DC2626;font-family:monospace">${{b.reject_rate}}%</div>
        </div>
      </div>
      <div style="margin-top:8px;padding-top:8px;border-top:1px solid #F1F5F9;font-size:11px;color:#64748B;line-height:1.7">
        刚推送卡审 <b style="color:#DC2626">${{b.immediate}}</b>（${{b.immediate_pct}}%）<br>
        用着用着卡审 <b style="color:#F59E0B">${{b.inuse}}</b>（${{b.inuse_pct}}%）<br>
        推送后未卡审 <b style="color:#059669">${{b.ok}}</b>（${{b.ok_pct}}%）
      </div>
    </div>`;
  }}).join('');
}}

function renderTestCards(container, scopeEl) {{
  const views = TEST_AUDIT_ANALYSIS.views || {{}};
  const keys = REJ_DATES.map(labelToKey);
  const row = {{}};
  keys.forEach(k => {{
    const dayRow = (views.day || {{}})[k];
    if (!dayRow) return;
    // 改版 + 全部 + 版本合计 三类桶都累加
    ['0改','1改','2改','3改','全部','版本合计'].forEach(v => {{
      const b = dayRow[v];
      if (!b) return;
      if (!row[v]) row[v] = {{submitted:0,pass:0,fail:0,eco:0,unknown:0}};
      row[v].submitted += b.submitted;
      row[v].pass += b.pass;
      row[v].fail += b.fail;
      row[v].eco += b.eco;
      row[v].unknown += b.unknown;
    }});
  }});
  ['0改','1改','2改','3改','全部','版本合计'].forEach(v => {{
    if (!row[v]) return;
    const t = row[v].submitted;
    row[v].pass_rate = t ? Math.round(row[v].pass/t*1000)/10 : 0;
    row[v].fail_rate = t ? Math.round((row[v].fail+row[v].eco)/t*1000)/10 : 0;
    row[v].eco_pct = t ? Math.round(row[v].eco/t*1000)/10 : 0;
    row[v].unknown_pct = t ? Math.round(row[v].unknown/t*1000)/10 : 0;
    row[v].fail_pct = t ? Math.round(row[v].fail/t*1000)/10 : 0;
  }});
  if (scopeEl) {{
    scopeEl.textContent = REJ_DATES.length === 1
      ? '（' + REJ_DATES[0] + ' 提交）'
      : '（' + REJ_DATES.length + ' 天合并）';
  }}
  const cards = ['0改','1改','2改','3改','全部','版本合计'].filter(v => (row[v] && row[v].submitted > 0) || v === '全部' || v === '版本合计');
  container.style.gridTemplateColumns = 'repeat(' + Math.min(cards.length, 6) + ',1fr)';
  container.innerHTML = cards.map(v => {{
    const b = row[v] || {{submitted:0,pass:0,fail:0,eco:0,unknown:0,pass_rate:0,fail_rate:0,eco_pct:0,unknown_pct:0,fail_pct:0}};
    const isAll = v === '全部';
    const isVerAll = v === '版本合计';
    const title = isAll ? '合计' : (isVerAll ? '版本合计' : v);
    const borderColor = isAll ? '#94A3B8' : (isVerAll ? '#CBD5E1' : '#E2E8F0');
    return `<div style="background:#fff;border:1.5px solid ${{borderColor}};border-radius:10px;padding:14px 16px;box-shadow:0 1px 3px rgba(0,0,0,.06)">
      <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:8px">
        <div style="font-size:13px;font-weight:700;color:#1E3A8A">${{title}}</div>
        <div style="font-size:10px;color:#94A3B8">${{isVerAll ? '版本不去重' : '素材'}} ${{b.submitted}} 条</div>
      </div>
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:6px;margin-bottom:8px">
        <div style="background:#ECFDF5;border-radius:6px;padding:7px 9px;text-align:center">
          <div style="font-size:10px;color:#059669;margin-bottom:2px">通过</div>
          <div style="font-size:16px;font-weight:700;color:#059669;font-family:monospace">${{b.pass}}</div>
          <div style="font-size:10px;color:#059669;font-family:monospace">${{b.pass_rate}}%</div>
        </div>
        <div style="background:#FEF2F2;border-radius:6px;padding:7px 9px;text-align:center">
          <div style="font-size:10px;color:#DC2626;margin-bottom:2px">不通过</div>
          <div style="font-size:16px;font-weight:700;color:#DC2626;font-family:monospace">${{b.fail + b.eco}}</div>
          <div style="font-size:10px;color:#DC2626;font-family:monospace">${{b.fail_rate}}%</div>
        </div>
      </div>
      <div style="margin-top:8px;padding-top:8px;border-top:1px solid #F1F5F9;font-size:11px;color:#64748B;line-height:1.7">
        普通不通过 <b style="color:#DC2626">${{b.fail}}</b>（${{b.fail_pct}}%）<br>
        生态风险 <b style="color:#F59E0B">${{b.eco}}</b>（${{b.eco_pct}}%）<br>
        未知 <b style="color:#94A3B8">${{b.unknown}}</b>（${{b.unknown_pct}}%）
      </div>
    </div>`;
  }}).join('');
}}

function renderRejectList() {{
  const tbody = document.getElementById('rejectListBody');
  const countEl = document.getElementById('rejectListCount');
  if (!tbody) return;
  const isTest = analysisMode === 'test';
  const keys = new Set(REJ_DATES.map(labelToKey));
  let list;
  if (isTest) {{
    list = (TEST_AUDIT_ANALYSIS.materials || []).filter(m => keys.has(m.audit_day));
    if (rejFilter !== 'all') list = list.filter(m => m.status === rejFilter);
  }} else {{
    list = (REJECT_ANALYSIS.materials || []).filter(m => keys.has(m.first_day));
    if (rejFilter !== 'all') list = list.filter(m => m.status === rejFilter);
  }}
  if (countEl) countEl.textContent = '（' + list.length + ' 条 · ' + (REJ_DATES.length === 1 ? REJ_DATES[0] : REJ_DATES.length + '天') + '）';
  if (!list.length) {{ tbody.innerHTML = '<tr><td colspan="7" style="color:#94A3B8;text-align:center;padding:14px">该日期/筛选下暂无素材</td></tr>'; return; }}
  const sorted = [...list].sort((a, b) => {{
    let va = a[rejSortCol], vb = b[rejSortCol];
    if (rejSortCol === 'name' || rejSortCol === 'version') {{
      va = va || ''; vb = vb || '';
      return rejSortAsc ? va.localeCompare(vb, 'zh') : vb.localeCompare(va, 'zh');
    }}
    if (rejSortCol === 'first_rej_day' || rejSortCol === 'audit_day') {{
      va = va || '9999'; vb = vb || '9999';
    }}
    return rejSortAsc ? (va < vb ? -1 : va > vb ? 1 : 0) : (vb < va ? -1 : vb > va ? 1 : 0);
  }});
  if (isTest) {{
    tbody.innerHTML = sorted.map((m, i) => {{
      const label = m.status === 'pass'
        ? '<span style="background:#ECFDF5;color:#059669;padding:2px 8px;border-radius:10px;font-size:10px;font-weight:600">通过</span>'
        : m.status === 'eco'
        ? '<span style="background:#FFFBEB;color:#D97706;padding:2px 8px;border-radius:10px;font-size:10px;font-weight:600">生态风险</span>'
        : m.status === 'unknown'
        ? '<span style="background:#F8FAFC;color:#94A3B8;padding:2px 8px;border-radius:10px;font-size:10px;font-weight:600">未知</span>'
        : '<span style="background:#FEF2F2;color:#DC2626;padding:2px 8px;border-radius:10px;font-size:10px;font-weight:600">不通过</span>';
      return `<tr>
        <td><div class="mat-name" style="max-width:360px" title="${{m.name}}">${{m.name}}</div></td>
        <td><span class="num">${{m.version}}</span></td>
        <td>${{fmtDate(m.audit_day)}}</td>
        <td>${{label}}</td>
      </tr>`;
    }}).join('');
    return;
  }}
  tbody.innerHTML = sorted.map((m, i) => {{
    const statusLabel = m.status === 'immediate'
      ? '<span style="background:#FEF2F2;color:#DC2626;padding:2px 8px;border-radius:10px;font-size:10px;font-weight:600">刚推送卡审</span>'
      : m.status === 'inuse'
      ? '<span style="background:#FFFBEB;color:#D97706;padding:2px 8px;border-radius:10px;font-size:10px;font-weight:600">用着用着卡审</span>'
      : '<span style="background:#ECFDF5;color:#059669;padding:2px 8px;border-radius:10px;font-size:10px;font-weight:600">推送后未卡审</span>';
    const rejDay = m.first_rej_day ? fmtDate(m.first_rej_day) : '<span style="color:var(--text-muted)">—</span>';
    const acctHtml = (m.accounts && m.accounts.length)
      ? m.accounts.map(a => `<span style="display:inline-block;background:#EFF6FF;color:#1E40AF;padding:1px 6px;border-radius:8px;font-size:10px;margin:1px 2px 1px 0;white-space:nowrap">${{a}}</span>`).join('')
      : '<span style="color:var(--text-muted)">—</span>';
    const playBtn = m.url && m.url.length > 10
      ? `<button class="btn-play" onclick="openRejectVideo('${{encodeURIComponent(m.id)}}')"><svg viewBox="0 0 16 16" fill="currentColor"><path d="M4 3l10 5-10 5V3z"/></svg>播放</button>`
      : '<span style="color:var(--text-muted);font-size:11px">无链接</span>';
    return `<tr>
      <td><div class="mat-name" style="max-width:300px" title="${{m.name}}">${{m.name}}</div></td>
      <td><span class="num">${{m.version}}</span></td>
      <td style="max-width:220px">${{acctHtml}}</td>
      <td>${{fmtDate(m.first_day)}}</td>
      <td>${{rejDay}}</td>
      <td>${{statusLabel}}</td>
      <td>${{playBtn}}</td>
    </tr>`;
  }}).join('');
}}

function openRejectVideo(encodedId) {{
  const id = decodeURIComponent(encodedId);
  const m = (REJECT_ANALYSIS.materials || []).find(x => x.id === id);
  if (!m || !m.url) return;
  const st = m.status === 'immediate' ? '刚推送卡审' : m.status === 'inuse' ? '用着用着卡审' : '推送后未卡审';
  document.getElementById('modalTitle').textContent = m.name;
  document.getElementById('modalMeta').innerHTML =
    '<span class="modal-badge">推送日 ' + fmtDate(m.first_day).replace(/<[^>]+>/g,'') + '</span>' +
    (m.first_rej_day
      ? '<span class="modal-badge" style="background:#DC262622;color:#DC2626">卡审日 ' + fmtDate(m.first_rej_day).replace(/<[^>]+>/g,'') + '</span>'
      : '<span class="modal-badge" style="background:#05966922;color:#059669">' + st + '</span>');
  document.getElementById('videoWrap').innerHTML =
    `<video controls autoplay preload="metadata" style="max-width:100%;max-height:65vh"><source src="${{m.url}}" type="video/mp4"></video>`;
  document.getElementById('videoModal').classList.add('open');
  document.body.style.overflow = 'hidden';
}}

function passWindowForDates() {{
  // 窗口跟随顶部多选的最后一天：end = 最后选中日，start = end - 21 天
  const ends = REJ_DATES.map(dd => {{
    const mm = parseInt(dd.slice(0,2)), d = parseInt(dd.slice(3));
    return new Date(2026, mm-1, d);
  }});
  const end = new Date(Math.max(...ends.map(x => x.getTime())));
  const start = new Date(end.getTime() - 21*86400000);
  return [start, end];
}}

let passPersonFilter = 'all';   // all | 编导名
let passWeek = 'all';           // all | w1(最近7天) | w2 | w3

function weekRangeLabel(wIdx) {{
  // w1=最近7天，w2=再前7天，w3=再前7天；返回 'MM/DD-MM/DD'
  const [start, end] = passWindowForDates();
  const f = d => ('0'+(d.getMonth()+1)).slice(-2) + '/' + ('0'+d.getDate()).slice(-2);
  if (wIdx === 'w1') return f(new Date(end.getTime() - 6*86400000)) + '-' + f(end);
  if (wIdx === 'w2') return f(new Date(end.getTime() - 13*86400000)) + '-' + f(new Date(end.getTime() - 7*86400000));
  return f(start) + '-' + f(new Date(end.getTime() - 14*86400000));
}}

function setPassWeek(w, btn) {{
  passWeek = w;
  document.querySelectorAll('#passWeekBtns .sort-btn').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  renderPassPersonCards();
  renderPassList();
}}

function updatePassWeekLabels() {{
  // 周按钮显示实际日期区间
  const w1 = document.getElementById('passWeek1');
  const w2 = document.getElementById('passWeek2');
  const w3 = document.getElementById('passWeek3');
  if (w1) w1.textContent = '第1周 ' + weekRangeLabel('w1');
  if (w2) w2.textContent = '第2周 ' + weekRangeLabel('w2');
  if (w3) w3.textContent = '第3周 ' + weekRangeLabel('w3');
}}

function passWeekStartOf(cPushDay, wStart, wEnd) {{
  // 返回该产出日落在第几周：w1=最近7天，w2=再前7天，w3=再前7天；窗口外返回 null
  const t = new Date(2026, parseInt(cPushDay.slice(0,2))-1, parseInt(cPushDay.slice(2))).getTime();
  if (t < wStart || t > wEnd) return null;
  const daysFromEnd = Math.floor((wEnd - t) / 86400000);
  if (daysFromEnd < 7) return 'w1';
  if (daysFromEnd < 14) return 'w2';
  return 'w3';
}}

function renderPassPersonCards() {{
  const container = document.getElementById('passPersonCards');
  if (!container) return;
  const CORE = ['小敏', '瑞晨', '嘉丽', '雅迪'];
  const rows = RECENT_PASS_ANALYSIS.rows || [];
  const cnt = {{}};
  rows.forEach(r => {{ cnt[r.person] = (cnt[r.person] || 0) + 1; }});
  const persons = CORE.filter(p => cnt[p]);
  if (!persons.length) {{ container.innerHTML = ''; return; }}
  const colors = PERSON_COLORS;
  container.innerHTML = `<button class="sort-btn ${{passPersonFilter === 'all' ? 'active' : ''}}" onclick="setPassPerson('all',this)" style="font-size:11px">全部</button>` +
    persons.map(p =>
      `<button class="sort-btn ${{passPersonFilter === p ? 'active' : ''}}" onclick="setPassPerson('${{p}}',this)" style="font-size:11px;color:${{colors[p]}}">${{p}} <span style="opacity:.6">${{cnt[p]}}</span></button>`).join('');
}}

function setPassPerson(p, btn) {{
  passPersonFilter = p;
  renderPassPersonCards();
  renderPassList();
}}

function renderPassList() {{
  const tbody = document.getElementById('passListBody');
  const empty = document.getElementById('passListEmpty');
  const winLabel = document.getElementById('passWindowLabel');
  if (!tbody) return;
  const [start, end] = passWindowForDates();
  const wStart = start.getTime(), wEnd = end.getTime();
  if (winLabel) {{
    const f = d => ('0'+(d.getMonth()+1)).slice(-2) + '/' + ('0'+d.getDate()).slice(-2);
    winLabel.textContent = '（' + f(start) + ' ~ ' + f(end) + ' 产出 · 指标按窗口内）';
  }}
  const allRows = RECENT_PASS_ANALYSIS.rows || [];
  const dkey = mmdd => new Date(2026, parseInt(mmdd.slice(0,2))-1, parseInt(mmdd.slice(2))).getTime();
  // 计算窗口内聚合指标
  const computed = allRows.map(r => {{
    const daily = r.daily || {{}};
    let spend=0, conv=0, gq=0, imp=0, click=0, w3n=0, w5n=0, wfn=0, wdn=0, impQ=0, actDays=0;
    let firstSpend='', firstConv='', firstGq='';
    Object.keys(daily).sort().forEach(mm => {{
      const t = dkey(mm);
      if (t < wStart || t > wEnd) return;   // 窗口截断：只累加窗口内天数
      const x = daily[mm];
      spend += x.spend || 0; conv += x.conv || 0; gq += x.gq || 0;
      imp += x.imp || 0; click += x.click || 0;
      if ((x.spend || 0) > 0) {{ actDays += 1; if (!firstSpend) firstSpend = mm; }}
      if ((x.conv || 0) > 0 && !firstConv) firstConv = mm;
      if ((x.gq || 0) > 0 && !firstGq) firstGq = mm;
      // 播放质量展示加权（只累计有数据的行）
      if ((x.imp || 0) > 0) {{
        if ((x.w3 || 0) > 0) {{ w3n += x.w3 * x.imp; impQ += x.imp; }}
        if ((x.w5 || 0) > 0) {{ w5n += x.w5 * x.imp; impQ = Math.max(impQ, 0); }}
        if ((x.wf || 0) > 0) wfn += x.wf * x.imp;
        if ((x.wd || 0) > 0) wdn += x.wd * x.imp;
      }}
    }});
    return {{
      r: r, spend: spend, conv: conv, gq: gq, imp: imp, click: click,
      ctr: imp > 0 ? click/imp*100 : -1,
      cpa: conv > 0 ? spend/conv : -1,
      deep_rate: conv > 0 ? gq/conv*100 : -1,
      qf: imp > 0 && wfn > 0 ? wfn/imp : -1,
      q3: imp > 0 && w3n > 0 ? w3n/imp : -1,
      q5: imp > 0 && w5n > 0 ? w5n/imp : -1,
      qd: imp > 0 && wdn > 0 ? wdn/imp : -1,
      firstSpend: firstSpend, firstConv: firstConv, firstGq: firstGq,
      active_days: actDays,
    }};
  }});
  // 产出日筛窗口 + 周筛 + 编导筛选
  const rows = computed.filter(c => {{
    const t = dkey(c.r.push_day);
    if (t < wStart || t > wEnd) return false;
    if (passWeek !== 'all' && passWeekStartOf(c.r.push_day, wStart, wEnd) !== passWeek) return false;
    if (passPersonFilter !== 'all' && c.r.person !== passPersonFilter) return false;
    return true;
  }}).sort((a, b) => {{
    const k = passSortCol;
    let va = k === 'ctr' || k === 'cpa' || k === 'deep_rate' || k === 'qf' || k === 'q3' || k === 'q5' || k === 'qd' ? a[k] : (a[k] !== undefined ? a[k] : a.spend);
    let vb = k === 'ctr' || k === 'cpa' || k === 'deep_rate' || k === 'qf' || k === 'q3' || k === 'q5' || k === 'qd' ? b[k] : (b[k] !== undefined ? b[k] : b.spend);
    if (va === '' || va === null || va === undefined) va = '9999';
    if (vb === '' || vb === null || vb === undefined) vb = '9999';
    if (k === 'name' || k === 'version' || k === 'type' || k === 'push_day') {{
      return passSortAsc ? String(va).localeCompare(String(vb), 'zh') : String(vb).localeCompare(String(va), 'zh');
    }}
    if (typeof va === 'string' || typeof vb === 'string') {{
      return passSortAsc ? String(va).localeCompare(String(vb)) : String(vb).localeCompare(String(va));
    }}
    return passSortAsc ? va - vb : vb - va;
  }});
  if (!rows.length) {{ tbody.innerHTML = ''; if (empty) empty.style.display = 'block'; renderPassSummary([]); return; }}
  if (empty) empty.style.display = 'none';
  renderPassSummary(rows);
  const fmtPct = v => v >= 0 ? v.toFixed(2) + '%' : '<span style="color:var(--text-muted)">—</span>';
  const fmtSec = v => v >= 0 ? v.toFixed(1) + 's' : '<span style="color:var(--text-muted)">—</span>';
  tbody.innerHTML = rows.map((c, i) => {{
    const r = c.r;
    const playBtn = r.url && r.url.length > 10
      ? `<button class="btn-play" onclick="openPassVideo('${{encodeURIComponent(r.id)}}')"><svg viewBox="0 0 16 16" fill="currentColor"><path d="M4 3l10 5-10 5V3z"/></svg>播放</button>`
      : '<span style="color:var(--text-muted);font-size:11px">无链接</span>';
    return `<tr>
      <td><div class="mat-name" style="max-width:260px" title="${{r.name}}">${{r.name}}</div></td>
      <td>${{r.type === 'tuwen' ? '<span style="color:#8B5CF6;font-size:10px;font-weight:600">图文</span>' : '<span style="color:#3B82F6;font-size:10px;font-weight:600">视频</span>'}}</td>
      <td><span class="num">${{r.version}}</span></td>
      <td>${{fmtDate(r.push_day)}}</td>
      <td><span class="num num-hi">¥${{c.spend.toFixed(2)}}</span></td>
      <td><span class="num">${{fmtPct(c.ctr)}}</span></td>
      <td>${{c.conv > 0 ? '<span class="num num-hi">' + c.conv + '</span>' : '<span class="num num-zero">—</span>'}}</td>
      <td><span class="num">${{c.cpa >= 0 ? '¥' + c.cpa.toFixed(0) : '—'}}</span></td>
      <td>${{c.gq > 0 ? '<span class="gaoquan-cell">' + c.gq + '</span>' : '<span class="gaoquan-zero num-zero">—</span>'}}</td>
      <td>${{c.deep_rate >= 0 ? '<span class="num" style="color:' + (c.deep_rate >= 15 ? '#D97706' : '#94A3B8') + '">' + c.deep_rate.toFixed(1) + '%</span>' : '<span class="num num-zero">—</span>'}}</td>
      <td><span class="num">${{fmtPct(c.qf)}}</span></td>
      <td><span class="num">${{fmtPct(c.q3)}}</span></td>
      <td><span class="num">${{fmtPct(c.q5)}}</span></td>
      <td><span class="num">${{fmtSec(c.qd)}}</span></td>
      <td><span class="num">${{c.active_days}}</span></td>
      <td>${{playBtn}}</td>
    </tr>`;
  }}).join('');
}}

function renderPassSummary(rows) {{
  const container = document.getElementById('passSummaryRow');
  const personContainer = document.getElementById('passPersonSummaryRow');
  if (!container) return;
  if (!rows.length) {{
    container.innerHTML = '';
    if (personContainer) personContainer.innerHTML = '';
    return;
  }}
  // 全部汇总（1张卡）
  const tSpend = rows.reduce((s,c) => s+c.spend, 0);
  const tConv = rows.reduce((s,c) => s+c.conv, 0);
  const tGq = rows.reduce((s,c) => s+c.gq, 0);
  const tImp = rows.reduce((s,c) => s+c.imp, 0);
  const tClick = rows.reduce((s,c) => s+c.click, 0);
  const ctr = tImp > 0 ? tClick/tImp*100 : -1;
  const cpa = tConv > 0 ? tSpend/tConv : -1;
  const deep = tConv > 0 ? tGq/tConv*100 : -1;
  // 出单统计：基础名去重，深转>0 即出单
  const orderSet = new Set();
  rows.forEach(c => {{ if ((c.gq || 0) > 0) orderSet.add(c.r.id || c.r.name); }});
  const orderCount = orderSet.size;
  const totalMat = new Set(rows.map(c => c.r.id || c.r.name)).size;
  const orderRate = totalMat > 0 ? (orderCount / totalMat * 100) : 0;
  const cell = (l, v) => `<div style="background:#F8FAFC;border-radius:6px;padding:6px 8px;text-align:center"><div style="font-size:10px;color:#94A3B8">${{l}}</div><div style="font-size:14px;font-weight:700;font-family:monospace;color:#1E40AF">${{v}}</div></div>`;
  container.innerHTML = `<div style="flex:1;background:#fff;border:1.5px solid #BFDBFE;border-radius:10px;padding:12px 16px;box-shadow:0 1px 3px rgba(0,0,0,.06)">
    <div style="font-size:12px;font-weight:700;color:#1E3A8A;margin-bottom:8px">全部汇总</div>
    <div style="display:grid;grid-template-columns:repeat(7,1fr);gap:6px">
      ${{cell('点击率', ctr >= 0 ? ctr.toFixed(2)+'%' : '—')}}
      ${{cell('CPA', cpa >= 0 ? '¥'+cpa.toFixed(0) : '—')}}
      ${{cell('转化', tConv)}}
      ${{cell('高潜', tGq)}}
      ${{cell('深转率', deep >= 0 ? deep.toFixed(1)+'%' : '—')}}
      ${{cell('高潜成交数', orderCount)}}
      ${{cell('高潜成交率', orderRate.toFixed(0)+'%')}}
    </div>
  </div>`;
  // 各编导汇总（4张卡）
  const CORE = ['小敏','瑞晨','嘉丽','雅迪'];
  if (personContainer) {{
    personContainer.innerHTML = CORE.map(p => {{
      const sub = rows.filter(c => c.r.person === p);
      if (!sub.length) return '<div style="background:#F8FAFC;border:1.5px dashed #E2E8F0;border-radius:10px;padding:12px 16px;color:#94A3B8;font-size:12px;text-align:center">无数据</div>';
      const sp = sub.reduce((s,c)=>s+c.spend,0);
      const cv = sub.reduce((s,c)=>s+c.conv,0);
      const gq = sub.reduce((s,c)=>s+c.gq,0);
      const imp = sub.reduce((s,c)=>s+c.imp,0);
      const clk = sub.reduce((s,c)=>s+c.click,0);
      const pctr = imp>0 ? clk/imp*100 : -1;
      const pcpa = cv>0 ? sp/cv : -1;
      const pdeep = cv>0 ? gq/cv*100 : -1;
      const pOrderSet = new Set();
      sub.forEach(c => {{ if ((c.gq || 0) > 0) pOrderSet.add(c.r.id || c.r.name); }});
      const pOrderCount = pOrderSet.size;
      const pTotalMat = new Set(sub.map(c => c.r.id || c.r.name)).size;
      const pOrderRate = pTotalMat > 0 ? (pOrderCount / pTotalMat * 100) : 0;
      const color = PERSON_COLORS[p] || '#64748B';
      return `<div style="background:#fff;border:1.5px solid ${{color}}44;border-radius:10px;padding:12px 14px;box-shadow:0 1px 3px rgba(0,0,0,.06);cursor:pointer" onclick="setPassPerson('${{p}}',this);renderPassPersonCards();">
        <div style="font-size:12px;font-weight:700;color:${{color}};margin-bottom:8px">${{p}}</div>
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:4px;font-size:11px;color:#64748B">
          <span>点击率 <b style="color:#1E40AF">${{pctr>=0?pctr.toFixed(2)+'%':'—'}}</b></span>
          <span>CPA <b style="color:#1E40AF">${{pcpa>=0?'¥'+pcpa.toFixed(0):'—'}}</b></span>
          <span>转化 <b style="color:#059669">${{cv}}</b></span>
          <span>高潜 <b style="color:#D97706">${{gq}}</b></span>
          <span>深转率 <b style="color:#D97706">${{pdeep>=0?pdeep.toFixed(1)+'%':'—'}}</b></span>
          <span>出单 <b style="color:#D97706">${{pOrderCount}}/${{pTotalMat}}</b></span>
          <span>高潜成交率 <b style="color:#D97706">${{pOrderRate.toFixed(0)+'%'}}</b></span>
        </div>
      </div>`;
    }}).join('');
  }}
}}

function openPassVideo(encodedId) {{
  const id = decodeURIComponent(encodedId);
  const r = (RECENT_PASS_ANALYSIS.rows || []).find(x => x.id === id);
  if (!r || !r.url) return;
  document.getElementById('modalTitle').textContent = r.name;
  document.getElementById('modalMeta').innerHTML =
    '<span class="modal-badge" style="background:#05966922;color:#059669">产出 ' + fmtDate(r.push_day).replace(/<[^>]+>/g,'') + '</span>';
  document.getElementById('videoWrap').innerHTML =
    `<video controls autoplay preload="metadata" style="max-width:100%;max-height:65vh"><source src="${{r.url}}" type="video/mp4"></video>`;
  document.getElementById('videoModal').classList.add('open');
  document.body.style.overflow = 'hidden';
}}

// 表头点击排序：卡审明细 + 近3周跑出表
function bindRejectSorts() {{
  const t1 = document.getElementById('rejectListTable');
  if (t1) {{
    t1.querySelectorAll('thead th[data-col]').forEach(th => {{
      th.onclick = () => {{
        const col = th.dataset.col;
        if (rejSortCol === col) rejSortAsc = !rejSortAsc;
        else {{ rejSortCol = col; rejSortAsc = col === 'name' || col === 'version'; }}
        t1.querySelectorAll('thead th').forEach(t => t.classList.remove('sorted-asc','sorted-desc'));
        th.classList.add(rejSortAsc ? 'sorted-asc' : 'sorted-desc');
        renderRejectList();
      }};
    }});
  }}
  const t2 = document.getElementById('passListTable');
  if (t2) {{
    t2.querySelectorAll('thead th[data-col]').forEach(th => {{
      th.onclick = () => {{
        const col = th.dataset.col;
        if (passSortCol === col) passSortAsc = !passSortAsc;
        else {{ passSortCol = col; passSortAsc = col === 'name' || col === 'version'; }}
        t2.querySelectorAll('thead th').forEach(t => t.classList.remove('sorted-asc','sorted-desc'));
        th.classList.add(passSortAsc ? 'sorted-asc' : 'sorted-desc');
        renderPassList();
      }};
    }});
  }}
}}

function initRejectModules() {{
  setupModeUI();
  bindRejectSorts();
  updatePassWeekLabels();
  renderRejectModules();
}}

function renderRejectTagCards() {{
  const container = document.getElementById('rejectTagCardsRow');
  if (!container) return;
  const isTest = analysisMode === 'test';
  const tagData = isTest ? (TEST_AUDIT_ANALYSIS.tag_views || {{}}) : (REJECT_ANALYSIS.tag_views || {{}});
  const TAG_COLORS = {{'A1':'#3B82F6','A2':'#8B5CF6','A3':'#10B981','A4':'#F59E0B'}};
  const keys = REJ_DATES.map(labelToKey);
  const row = {{}};
  keys.forEach(k => {{
    const dayRow = (tagData.day || {{}})[k];
    if (!dayRow) return;
    ['A1','A2','A3','A4'].forEach(t => {{
      const b = dayRow[t];
      if (!b) return;
      if (!row[t]) row[t] = isTest ? {{submitted:0,pass:0,fail:0,eco:0,unknown:0}} : {{pushed:0,ok:0,rejected:0}};
      if (isTest) {{
        row[t].submitted += b.submitted; row[t].pass += b.pass;
        row[t].fail += b.fail; row[t].eco += b.eco; row[t].unknown += b.unknown;
      }} else {{
        row[t].pushed += b.pushed; row[t].ok += b.ok; row[t].rejected += b.rejected;
      }}
    }});
  }});
  ['A1','A2','A3','A4'].forEach(t => {{
    if (!row[t]) return;
    const b = row[t];
    if (isTest) {{
      b.pass_rate = b.submitted ? Math.round(b.pass/b.submitted*1000)/10 : 0;
      b.fail_rate = b.submitted ? Math.round((b.fail+b.eco)/b.submitted*1000)/10 : 0;
    }} else {{
      b.ok_rate = b.pushed ? Math.round(b.ok/b.pushed*1000)/10 : 0;
      b.reject_rate = b.pushed ? Math.round(b.rejected/b.pushed*1000)/10 : 0;
    }}
  }});
  const tags = ['A1','A2','A3','A4'].filter(t => row[t] && (isTest ? row[t].submitted > 0 : row[t].pushed > 0));
  if (!tags.length) {{ container.innerHTML = '<div style="color:#94A3B8;font-size:12px;padding:12px">选中日期无标签数据</div>'; return; }}
  container.style.gridTemplateColumns = 'repeat(' + tags.length + ',1fr)';
  container.innerHTML = tags.map(t => {{
    const b = row[t];
    const color = TAG_COLORS[t];
    const total = isTest ? b.submitted : b.pushed;
    const ok = isTest ? b.pass : b.ok;
    const okRate = isTest ? b.pass_rate : b.ok_rate;
    const bad = isTest ? (b.fail + b.eco) : b.rejected;
    const badRate = isTest ? b.fail_rate : b.reject_rate;
    return `<div style="background:#fff;border:1.5px solid ${{color}}44;border-radius:10px;padding:14px 16px;box-shadow:0 1px 3px rgba(0,0,0,.06)">
      <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:8px">
        <div style="font-size:13px;font-weight:700;color:${{color}}">${{t}}</div>
        <div style="font-size:10px;color:#94A3B8">素材 ${{total}} 条</div>
      </div>
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:6px">
        <div style="background:#ECFDF5;border-radius:6px;padding:7px 9px;text-align:center">
          <div style="font-size:10px;color:#059669;margin-bottom:2px">通过</div>
          <div style="font-size:16px;font-weight:700;color:#059669;font-family:monospace">${{ok}}</div>
          <div style="font-size:10px;color:#059669;font-family:monospace">${{okRate}}%</div>
        </div>
        <div style="background:#FEF2F2;border-radius:6px;padding:7px 9px;text-align:center">
          <div style="font-size:10px;color:#DC2626;margin-bottom:2px">不通过</div>
          <div style="font-size:16px;font-weight:700;color:#DC2626;font-family:monospace">${{bad}}</div>
          <div style="font-size:10px;color:#DC2626;font-family:monospace">${{badRate}}%</div>
        </div>
      </div>
    </div>`;
  }}).join('');
}}

function renderRejectModules() {{
  renderRejectCards();
  renderRejectTagCards();
  renderRejectBucketTable();
  renderRejectList();
  renderPassPersonCards();
  renderPassList();
}}

function initCharts(labels, spendData, cpaData, convData, gaoquanData) {{
  // 柱状图已替换为编导卡片，此函数保留供 renderDay 调用
}}

function updateKpiDiffs(dateLabel, cur) {{
  // 单日（dateLabel 为 'MM/DD' 形式）时，与 ALL_DATES 中的前一天对比；多日合并时清空差值
  const dEls = ['spend','imp','ctr','cvr','conv','cpa','gaoquan','deeprate'];
  const isSingleDay = /^\\d{{2}}\\/\\d{{2}}$/.test(dateLabel);
  let prev = null;
  if (isSingleDay && ALL_DATES.length > 1) {{
    const idx = ALL_DATES.indexOf(dateLabel);
    if (idx > 0) {{
      const prevLabel = ALL_DATES[idx - 1];
      const prevRows = ALL_ROWS_BY_DATE[prevLabel] || [];
      let psp=0, pimp=0, pclk=0, pconv=0, pgq=0;
      prevRows.forEach(r => {{ psp+=r.spend; pimp+=r.impressions; pclk+=r.clicks; pconv+=r.conversions; pgq+=r.gaoquan; }});
      prev = {{
        spend:psp, imp:pimp, clicks:pclk, conv:pconv, gaoquan:pgq,
        cpa: pconv ? psp/pconv : 0,
        ctr: pimp ? pclk/pimp*100 : 0,
        cvr: pclk ? pconv/pclk*100 : 0,
        deeprate: pconv ? pgq/pconv*100 : 0,
      }};
    }}
  }}

  // 清空所有差值槽位
  dEls.forEach(k => {{
    const el = document.getElementById('kpi-' + k + '-diff');
    if (el) {{ el.textContent = ''; el.className = 'kpi-diff'; }}
  }});
  if (!prev) return;

  const fmtSign = (v, digits, prefix, suffix) => {{
    const sign = v > 0 ? '+' : v < 0 ? '-' : '±0';
    const abs = Math.abs(v).toFixed(digits);
    const cls = v > 0 ? 'up' : v < 0 ? 'down' : '';
    return {{ text: sign + prefix + abs + suffix, cls }};
  }};
  const set = (key, build) => {{
    const el = document.getElementById('kpi-' + key + '-diff');
    if (!el) return;
    const r = build(cur, prev);
    if (r) {{ el.textContent = r.text; if (r.cls) el.className = 'kpi-diff ' + r.cls; }}
  }};
  // 对成本/CPA 用反色：上升是坏事（红up），下降是好事（绿down）→ 保持 up=红 down=绿 语义一致
  set('spend',  (c,p) => fmtSign(c.spend - p.spend, 2, '¥', ''));
  set('imp',    (c,p) => fmtSign(c.imp - p.imp, 0, '', ''));
  set('ctr',    (c,p) => fmtSign(c.ctr - p.ctr, 2, '', '%'));
  set('cvr',    (c,p) => fmtSign(c.cvr - p.cvr, 2, '', '%'));
  set('conv',   (c,p) => fmtSign(c.conv - p.conv, 0, '', ''));
  set('cpa',    (c,p) => fmtSign(c.cpa - p.cpa, 2, '¥', ''));
  set('gaoquan',(c,p) => fmtSign(c.gaoquan - p.gaoquan, 0, '', ''));
  set('deeprate', (c,p) => {{
    const dc = c.conv ? c.gaoquan/c.conv*100 : 0;
    const dp = p.conv ? p.gaoquan/p.conv*100 : 0;
    return fmtSign(dc - dp, 1, '', '%');
  }});
}}

// ---------- 渲染单日 ----------
function renderDay(rows, dateLabel) {{
  // 计算当日汇总
  let ts=0, ti=0, tc=0, tz=0, tg=0;
  rows.forEach(r => {{ ts+=r.spend; ti+=r.impressions; tc+=r.clicks; tz+=r.conversions; tg+=r.gaoquan; }});
  const cpa = tz ? ts/tz : 0;
  const ctr = ti ? tc/ti*100 : 0;
  const cvr = tc ? tz/tc*100 : 0;
  document.getElementById('kpi-spend').textContent  = '¥' + ts.toLocaleString('zh',{{minimumFractionDigits:2,maximumFractionDigits:2}});
  document.getElementById('kpi-count').textContent  = rows.length + ' 条素材';
  document.getElementById('kpi-imp').textContent    = ti.toLocaleString('zh',{{maximumFractionDigits:0}});
  document.getElementById('kpi-ctr').textContent    = ctr.toFixed(2) + '%';
  document.getElementById('kpi-cvr').textContent    = cvr.toFixed(2) + '%';
  document.getElementById('kpi-conv').textContent   = tz.toFixed(0);
  document.getElementById('kpi-cpa').textContent    = '¥' + cpa.toFixed(2);
  document.getElementById('kpi-gaoquan').textContent= tg.toFixed(0);
  document.getElementById('kpi-deeprate').textContent= (tz ? (tg/tz*100).toFixed(1)+'%' : '—');

  // 与前一日对比（单日时显示加减差值；多日合并时不显示）
  _currentDateLabel = /^\\d{{2}}\\/\\d{{2}}$/.test(dateLabel) ? dateLabel : '';
  updateKpiDiffs(dateLabel, {{spend:ts, imp:ti, clicks:tc, conv:tz, gaoquan:tg, cpa:cpa, ctr:ctr, cvr:cvr}});
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
    btn.textContent = a.replace('高中-猿起武汉-', '').replace('【agent测试】', '').replace('【agent智擎】', '').replace('高中-渠道-', '渠道-');
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
  // 产出日期筛选在顶部日期切换时不重置（用户手动选择保留）
  // 更新表格数据源
  window.currentRows = rows;
  renderProduceDayFilters();
  pageNum = 1;
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
let currentTag = 'all';
let currentVersion = 'all';
let currentAccountFilter = 'all';
let sortCol = 'spend';
let sortAsc = false;
let pageNum = 1;         // 当前页（1起）
const PAGE_SIZE = 20;    // 每页行数

// ---------- 产出日期多选 ----------
let produceDaySet = new Set();   // 选中的产出日（'MMDD'）；空=全部
let pdPickerMonth = '';          // 面板当前展示的月份

function allProduceDays() {{
  const rows = ALL_ROWS || [];
  return [...new Set(rows.map(r => r.produce_day).filter(Boolean))].sort().reverse();
}}

function togglePdPicker() {{
  const picker = document.getElementById('pdPicker');
  if (!picker) return;
  const show = picker.style.display === 'none';
  picker.style.display = show ? 'block' : 'none';
  if (show) renderPdPicker();
}}

function renderPdPicker() {{
  const days = allProduceDays();
  const months = [...new Set(days.map(d => d.slice(0, 2)))].sort().reverse();
  if (!pdPickerMonth) pdPickerMonth = months[0] || '';
  // 月份按钮 + 全选本月
  const mb = document.getElementById('pdMonthBtns');
  if (mb) {{
    const monthDays = days.filter(d => d.slice(0, 2) === pdPickerMonth);
    const allSel = monthDays.length > 0 && monthDays.every(d => produceDaySet.has(d));
    mb.innerHTML = months.map(mm =>
      `<button class="filter-btn ${{pdPickerMonth === mm ? 'active' : ''}}" style="font-size:11px;color:#64748B"
        onclick="setPdPickerMonth('${{mm}}')">${{parseInt(mm)}}月</button>`).join('') +
      `<div style="flex:1"></div>` +
      `<button class="filter-btn ${{allSel ? 'active' : ''}}" style="font-size:11px;color:#D97706"
        onclick="toggleProduceMonth('${{pdPickerMonth}}')">${{allSel ? '取消全选' : '全选'}} ${{parseInt(pdPickerMonth)}}月</button>`;
  }}
  // 该月日期网格
  const grid = document.getElementById('pdDayGrid');
  if (grid) {{
    const monthDays = days.filter(d => d.slice(0, 2) === pdPickerMonth);
    grid.innerHTML = monthDays.map(d => {{
      const sel = produceDaySet.has(d);
      return `<button class="filter-btn ${{sel ? 'active' : ''}}" style="font-size:11px;font-family:monospace;${{sel ? 'background:#1E40AF;color:#fff' : 'color:#64748B'}}"
        onclick="toggleProduceDay('${{d}}')">${{fmtDate(d)}}</button>`;
    }}).join('') || '<span style="font-size:11px;color:var(--text-muted)">该月无产出</span>';
  }}
}}

function toggleProduceMonth(mm) {{
  const days = allProduceDays().filter(d => d.slice(0, 2) === mm);
  const allSel = days.every(d => produceDaySet.has(d));
  if (allSel) {{
    days.forEach(d => produceDaySet.delete(d));
  }} else {{
    days.forEach(d => produceDaySet.add(d));
  }}
  renderPdPicker();
  renderProduceDayChips();
  applyProduceDayFilter();
}}

function setPdPickerMonth(mm) {{
  pdPickerMonth = mm;
  renderPdPicker();
}}

function toggleProduceDay(d) {{
  if (produceDaySet.has(d)) produceDaySet.delete(d);
  else produceDaySet.add(d);
  renderPdPicker();
  renderProduceDayChips();
  applyProduceDayFilter();
}}

function clearProduceDay(btn) {{
  produceDaySet.clear();
  renderProduceDayChips();
  applyProduceDayFilter();
}}

function renderProduceDayChips() {{
  const chips = document.getElementById('produceDayChips');
  const clearBtn = document.getElementById('pdClearBtn');
  if (!chips) return;
  const sel = [...produceDaySet].sort().reverse();
  // 按月聚合显示：该月全部产出日都在集合内 → 一个「N月(全M天)」chip
  const months = [...new Set(sel.map(d => d.slice(0, 2)))].sort().reverse();
  const monthFull = months.filter(mm => {{
    const monthAll = allProduceDays().filter(d => d.slice(0, 2) === mm);
    return monthAll.length > 0 && monthAll.every(d => produceDaySet.has(d));
  }});
  const looseDays = sel.filter(d => !monthFull.includes(d.slice(0, 2)));
  chips.innerHTML =
    monthFull.map(mm =>
      `<button class="filter-btn active" style="font-size:11px;background:#1E40AF;color:#fff;border-color:#1E40AF" onclick="toggleProduceMonth('${{mm}}')">${{parseInt(mm)}}月(整月) ✕</button>`).join('') +
    looseDays.map(d =>
      `<button class="filter-btn active" style="font-size:11px;background:#1E40AF;color:#fff;border-color:#1E40AF" onclick="toggleProduceDay('${{d}}')">${{fmtDate(d)}} ✕</button>`).join('');
  if (clearBtn) {{
    clearBtn.classList.toggle('active', sel.length === 0);
    if (sel.length === 0) {{ clearBtn.style.background='var(--primary)'; clearBtn.style.color='#fff'; }}
    else {{ clearBtn.style.background=''; clearBtn.style.color='#64748B'; }}
  }}
}}

function applyProduceDayFilter() {{
  // 单向联动：选中产出日对应的所有快照日 → 全局日期并集
  if (produceDaySet.size && window._switchDays) {{
    const labels = [...produceDaySet].map(d => fmtDate(d)).filter(l => ALL_DATES.includes(l));
    if (labels.length) window._switchDays(labels);
  }}
  pageNum = 1;
  renderTable();
}}

// 兼容旧引用：renderProduceDayFilters 现在渲染 chips + 面板
function renderProduceDayFilters() {{
  renderProduceDayChips();
  const clearBtn = document.getElementById('pdClearBtn');
  if (clearBtn && produceDaySet.size === 0) {{
    clearBtn.classList.add('active');
    clearBtn.style.background = 'var(--primary)';
    clearBtn.style.color = '#fff';
  }}
}}

function filterTag(tag, btn) {{
  currentTag = tag;
  const TAG_COLORS = {{'A1':'#3B82F6','A2':'#8B5CF6','A3':'#10B981','A4':'#F59E0B','none':'#94A3B8','keytest':'#D97706'}};
  document.querySelectorAll('.filter-btn[data-tag]').forEach(b => {{
    b.classList.remove('active'); b.style.background='';
    b.style.color = TAG_COLORS[b.dataset.tag] || '';
  }});
  btn.classList.add('active');
  if (tag !== 'all') {{ btn.style.background = TAG_COLORS[tag]||'#64748B'; btn.style.color='#fff'; }}
  else {{ btn.style.background='var(--primary)'; btn.style.color='#fff'; }}
  pageNum = 1;
  renderTable();
}}

function filterVersion(ver, btn) {{
  currentVersion = ver;
  document.querySelectorAll('.filter-btn[data-version]').forEach(b => {{
    b.classList.remove('active'); b.style.background=''; b.style.color='#64748B';
  }});
  btn.classList.add('active');
  btn.style.background = 'var(--primary)'; btn.style.color = '#fff';
  pageNum = 1;
  renderTable();
}}

function filterType(type, btn) {{
  currentType = type;
  const colors = {{ video:'#3B82F6', tuwen:'#8B5CF6', homepage:'#059669', ai:'#6366F1' }};
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
  pageNum = 1;
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
  pageNum = 1;
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
  pageNum = 1;
  renderTable();
}}

document.querySelectorAll('thead th[data-col]').forEach(th => {{
  th.onclick = function() {{
    const col = this.dataset.col;
    if (sortCol === col) sortAsc = !sortAsc;
    else {{ sortCol = col; sortAsc = col === 'name' || col === 'person'; }}
    document.querySelectorAll('thead th').forEach(t => t.classList.remove('sorted-asc','sorted-desc'));
    this.classList.add(sortAsc ? 'sorted-asc' : 'sorted-desc');
    pageNum = 1;
    renderTable();
  }};
}});

function sortRows(rows) {{
  return [...rows].sort((a, b) => {{
    let va = a[sortCol], vb = b[sortCol];
    if (va === null || va === undefined) va = -1;
    if (vb === null || vb === undefined) vb = -1;
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

function renderChannel(dates) {{
  const section = document.getElementById('channelSection');
  const body = document.getElementById('channelBody');
  if (!section || !body) return;
  const accs = Object.keys(CHANNEL_SUMMARY || {{}});
  if (!accs.length) {{
    section.style.display = 'none';
    return;
  }}
  section.style.display = '';
  // 未传日期时用全部日期（等同于全周期）
  const sel = (dates && dates.length) ? dates : Object.keys(CHANNEL_SUMMARY[accs[0]] || {{}});
  const escC = s => String(s || '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
  const fmtPct = v => (v === null || v === undefined || !(v > 0)) ? '—' : v.toFixed(2) + '%';
  const fmtDeep = v => (v === null || v === undefined || !(v > 0)) ? '—' : v.toFixed(1) + '%';
  const fmtCpa = v => (v === null || v === undefined || !(v > 0)) ? '—' : '¥' + v.toFixed(2);
  body.innerHTML = accs.map(name => {{
    const byDate = CHANNEL_SUMMARY[name] || {{}};
    let spend = 0, imp = 0, click = 0, conv = 0, gq = 0;
    sel.forEach(d => {{
      const t = byDate[d];
      if (!t) return;
      spend += t.spend; imp += t.imp; click += t.click; conv += t.conv; gq += t.gq;
    }});
    const ctr = imp > 0 ? click / imp * 100 : null;
    const cvr = click > 0 ? conv / click * 100 : null;
    const cpa = conv > 0 ? spend / conv : null;
    const deep = conv > 0 ? gq / conv * 100 : null;
    return `<tr>
      <td>${{escC(name)}}</td>
      <td class="num">¥${{spend.toLocaleString('zh', {{minimumFractionDigits:2, maximumFractionDigits:2}})}}</td>
      <td class="num">${{imp.toLocaleString('zh')}}</td>
      <td class="num">${{fmtPct(ctr)}}</td>
      <td class="num num-hi">${{conv}}</td>
      <td class="num" style="color:#8B5CF6">${{fmtPct(cvr)}}</td>
      <td class="num">${{fmtCpa(cpa)}}</td>
      <td class="num warn">${{gq}}</td>
      <td class="num warn">${{fmtDeep(deep)}}</td>
    </tr>`;
  }}).join('');
}}

function renderPager(totalPages) {{
  const box = document.getElementById('pagerBox');
  if (!box) return;
  if (totalPages <= 1) {{ box.innerHTML = ''; return; }}
  let html = '';
  const mk = (label, page, disabled, active) =>
    `<button class="page-btn${{active ? ' active' : ''}}" data-page="${{page}}"${{disabled ? ' disabled' : ''}}>${{label}}</button>`;
  // 页码窗口：当前页前后各2页，加首末页
  const pages = new Set([1, totalPages, pageNum - 2, pageNum - 1, pageNum, pageNum + 1, pageNum + 2]);
  const sorted = [...pages].filter(p => p >= 1 && p <= totalPages).sort((a, b) => a - b);
  html += mk('‹', pageNum - 1, pageNum <= 1, false);
  let prev = 0;
  sorted.forEach(p => {{
    if (prev && p - prev > 1) html += '<span class="page-ellipsis">…</span>';
    html += mk(p, p, false, p === pageNum);
    prev = p;
  }});
  html += mk('›', pageNum + 1, pageNum >= totalPages, false);
  box.innerHTML = html;
  box.querySelectorAll('.page-btn').forEach(btn => {{
    btn.onclick = () => {{
      if (btn.disabled) return;
      pageNum = +btn.dataset.page;
      renderTable();
    }};
  }});
}}

function renderTable() {{
  const rows = window.currentRows || ALL_ROWS;
  const filtered = (currentFilter === 'all' ? rows : rows.filter(r => r.person === currentFilter))
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
    .filter(r => produceDaySet.size === 0 ? true : produceDaySet.has(r.produce_day));
  const sorted = sortRows(filtered);
  const totalPages = Math.max(1, Math.ceil(sorted.length / PAGE_SIZE));
  if (pageNum > totalPages) pageNum = totalPages;
  const start = (pageNum - 1) * PAGE_SIZE;
  const shown = sorted.slice(start, start + PAGE_SIZE);
  const tbody = document.getElementById('tableBody');
  const empty = document.getElementById('emptyState');
  document.getElementById('visibleCount').textContent =
    sorted.length + ' 条 · 第 ' + pageNum + '/' + totalPages + ' 页';

  // 分页控件
  renderPager(totalPages);

  if (!sorted.length) {{ tbody.innerHTML = ''; empty.style.display = 'block'; return; }}
  empty.style.display = 'none';

  tbody.innerHTML = shown.map((r, i) => {{
    const pc = PERSON_COLORS[r.person] || '#94A3B8';
    const bg = PERSON_BG[r.person]  || '#F8FAFC';
    const extBadge = r.is_external ? '<span class="ext-badge">外部</span>' : '';
    const tuwenBadge = r.is_tuwen ? '<span class="ext-badge" style="background:#F5F3FF;color:#7C3AED;border-color:#DDD6FE">图文</span>' : '';
    const aiBadge = r.is_ai ? '<span class="ext-badge" style="background:#EEF2FF;color:#6366F1;border-color:#C7D2FE">Ai</span>' : '';
    const collabBadge = r.collab ? `<span class="ext-badge" style="background:#F0F9FF;color:#0369A1;border-color:#BAE6FD">${{r.collab}}</span>` : '';
    const statusCls = r.status === '已使用' ? 'status-active' : 'status-inactive';
    const cpaDisp = r.cpa > 0 ? fmt(r.cpa) : '<span class="num num-zero">—</span>';
    const gaoquanDisp = r.gaoquan > 0
      ? '<span class="gaoquan-cell">' + r.gaoquan + '</span>'
      : '<span class="gaoquan-zero num-zero">—</span>';
    const deepRateDisp = r.conversions > 0
      ? '<span class="num" style="color:#D97706">' + ((r.gaoquan / r.conversions) * 100).toFixed(1) + '%</span>'
      : '<span class="num num-zero">—</span>';
    const qDisp = v => (v != null && v > 0) ? '<span class="num">' + v.toFixed(2) + '%</span>' : '<span class="num num-zero">—</span>';
    const qdDisp = (r.qd != null && r.qd > 0) ? '<span class="num">' + r.qd.toFixed(1) + 's</span>' : '<span class="num num-zero">—</span>';
    const hasVideo = r.video_url && r.video_url.length > 10 && !r.is_tuwen;
    const playBtn = hasVideo
      ? `<button class="btn-play" onclick="openVideoByName('${{encodeURIComponent(r.name)}}','${{encodeURIComponent(r.id || '')}}')">
           <svg viewBox="0 0 16 16" fill="currentColor"><path d="M4 3l10 5-10 5V3z"/></svg>播放
         </button>`
      : '<span style="color:var(--text-muted);font-size:11px">无链接</span>';
    const TAG_COLORS = {{'A1':'#3B82F6','A2':'#8B5CF6','A3':'#10B981','A4':'#F59E0B'}};
    const tagDisp = r.tag ? r.tag.split(',').map(t => {{
      const base = t.split('-')[0];
      const c = TAG_COLORS[base] || '#94A3B8';
      return `<span class="ext-badge" style="background:${{c}}18;color:${{c}};border-color:${{c}}44">${{t}}</span>`;
    }}).join('') : '<span class="num-zero">—</span>';
    const versionDisp = r.version ? `<span class="ext-badge" style="background:#F8FAFC;color:#64748B;border-color:#CBD5E1">${{r.version}}</span>` : '<span class="num-zero">—</span>';
    const keyTestBadge = r.is_key_test ? '<span class="ext-badge" style="background:#FFF7ED;color:#D97706;border-color:#FED7AA">重点测</span>' : '';
    return `<tr>
      <td><span class="person-badge" style="background:${{bg}};color:${{pc}}">${{r.person}}</span></td>
      <td><span style="font-size:11px;color:var(--text-secondary);white-space:nowrap" title="${{r.account}}">${{(r.account||'').replace('高中-猿起武汉-', '').replace('【agent测试】', '').replace('【agent智擎】', '').replace('高中-渠道-', '渠道-')}}</span></td>
      <td><div style="display:flex;align-items:flex-start;gap:4px;flex-wrap:wrap">
        <span class="mat-name" title="${{r.name}}">${{r.name}}</span>${{extBadge}}${{tuwenBadge}}${{aiBadge}}${{collabBadge}}${{keyTestBadge}}</div></td>
      <td><span class="mat-id" style="font-family:monospace;font-size:11px;color:var(--text-muted);white-space:nowrap" title="${{r.id}}">${{r.id || '—'}}</span></td>
      <td>${{tagDisp}}</td>
      <td>${{versionDisp}}</td>
      <td>${{r.produce_day ? fmtDate(r.produce_day) : '<span class="num-zero">—</span>'}}</td>
      <td>${{fmt(r.spend)}}</td>
      <td>${{fmtInt(r.impressions)}}</td>
      <td><span class="num">${{r.ctr > 0 ? r.ctr.toFixed(2)+'%' : '—'}}</span></td>
      <td>${{r.conversions > 0 ? '<span class="num num-hi">'+r.conversions+'</span>' : '<span class="num num-zero">—</span>'}}</td>
      <td><span class="num" style="color:#8B5CF6">${{r.cvr > 0 ? r.cvr.toFixed(2)+'%' : '—'}}</span></td>
      <td>${{cpaDisp}}</td>
      <td>${{gaoquanDisp}}</td>
      <td>${{deepRateDisp}}</td>
      <td>${{qDisp(r.q3)}}</td>
      <td>${{qDisp(r.q5)}}</td>
      <td>${{qDisp(r.qf)}}</td>
      <td>${{qdDisp}}</td>
      <td>${{playBtn}}</td>
    </tr>`;
  }}).join('');
  updatePersonOrderRates(sorted);
}}

// ---------- 编导高潜成交率徽章（跟随筛选联动） ----------
function updatePersonOrderRates(sortedRows) {{
  const container = document.getElementById('personOrderRates');
  if (!container) return;
  const CORE = ['小敏', '瑞晨', '嘉丽', '雅迪'];
  // 用传入的已过滤行（与当前筛选一致）；但注意 sortRows 是排序后的完整 filtered 列表
  const stats = {{}};
  const seen = {{}};   // 基础名去重集合
  sortedRows.forEach(r => {{
    if (!CORE.includes(r.person)) return;
    if (!stats[r.person]) stats[r.person] = {{total:0, order:0, seen:new Set()}};
    // 基础名去重：同名多版本算一条
    let bn = (r.name || '').replace(/\.mp4$/, '').replace(/-(\d)改$/, '').replace(/-改$/, '');
    if (stats[r.person].seen.has(bn)) return;
    stats[r.person].seen.add(bn);
    stats[r.person].total += 1;
    if ((r.gaoquan || 0) > 0) stats[r.person].order += 1;
  }});
  const colors = PERSON_COLORS;
  container.innerHTML = CORE.filter(p => stats[p]).map(p => {{
    const s = stats[p];
    const rate = s.total > 0 ? (s.order / s.total * 100).toFixed(0) : 0;
    const tipText = '高潜成交素材 ' + s.order + ' 条 / 总素材 ' + s.total + ' 条';
    return `<span class="order-rate-badge" data-tip="${{tipText}}" style="display:inline-flex;align-items:center;gap:4px;background:${{
      colors[p] || '#F8FAFC'}}18;border:1px solid ${{colors[p]}}44;border-radius:14px;
      padding:3px 10px;font-size:11px;font-weight:600;color:${{colors[p]}}">
      ${{p}} 高潜成交率 ${{rate}}%<span style="opacity:.6;font-weight:400">（${{s.order}}/${{s.total}}）</span>
    </span>`;
  }}).join('') || '<span style="font-size:11px;color:var(--text-muted)">该筛选下无编导数据</span>';
}}

// ---------- 视频弹窗 ----------
function openVideoByName(encodedName, encodedId) {{
  const name = decodeURIComponent(encodedName);
  const id = decodeURIComponent(encodedId || '');
  const rows = window.currentRows || ALL_ROWS;
  // 优先按素材id匹配，避免同名素材串到第一个的链接
  const r = rows.find(x => id && x.id === id) || rows.find(x => x.name === name);
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
    ${{r.conversions > 0 ? '<span class="modal-badge accent">深转率 ' + ((r.gaoquan / r.conversions) * 100).toFixed(1) + '%</span>' : ''}}
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
function mergeAuditData(dates) {{
  // 合并多天过审数据
  const vStats = {{}};
  const tStats = {{}};
  const pStats = {{}};  // person audit
  let sourceFiles = [];
  dates.forEach(d => {{
    const a = AUDIT_BY_DATE[d];
    if (!a) return;
    sourceFiles.push(a.source_file || d);
    (a.version_labels || []).forEach((v, i) => {{
      if (!vStats[v]) vStats[v] = {{pass:0, fail:0}};
      vStats[v].pass += a.pass_counts[i];
      vStats[v].fail += a.fail_counts[i];
    }});
    (a.tag_labels || []).forEach((t, i) => {{
      if (!tStats[t]) tStats[t] = {{pass:0, fail:0}};
      tStats[t].pass += a.tag_pass_counts[i];
      tStats[t].fail += a.tag_fail_counts[i];
    }});
    if (a.person_audit) {{
      Object.entries(a.person_audit).forEach(([p, d]) => {{
        if (!pStats[p]) pStats[p] = {{pass:[], fail:[]}};
        pStats[p].pass.push(...(d.pass||[]));
        pStats[p].fail.push(...(d.fail||[]));
      }});
    }}
  }});
  const pAudit = pStats;
  if (!Object.keys(vStats).length && !Object.keys(tStats).length) return null;

  const vOrder = ['0改','1改','2改','3改','代理素材'];
  const v_labels=[], v_pass=[], v_fail=[], v_rate=[];
  vOrder.forEach(v => {{
    if (!vStats[v]) return;
    const p=vStats[v].pass, f=vStats[v].fail, tot=p+f;
    v_labels.push(v); v_pass.push(p); v_fail.push(f);
    v_rate.push(tot ? parseFloat((p/tot*100).toFixed(1)) : 0);
  }});

  const tOrder=['A1','A2','A3','A4','AI','未标记'];
  const t_labels=[], t_pass=[], t_fail=[], t_rate=[];
  tOrder.forEach(t => {{
    if (!tStats[t]) return;
    const p=tStats[t].pass, f=tStats[t].fail, tot=p+f;
    t_labels.push(t); t_pass.push(p); t_fail.push(f);
    t_rate.push(tot ? parseFloat((p/tot*100).toFixed(1)) : 0);
  }});

  return {{
    version_labels: v_labels, pass_counts: v_pass, fail_counts: v_fail, pass_rates: v_rate,
    tag_labels: t_labels, tag_pass_counts: t_pass, tag_fail_counts: t_fail, tag_pass_rates: t_rate,
    person_audit: pAudit,
    source_file: sourceFiles.join(' + '),
  }};
}}

function initTabs() {{
  if (!IS_MULTI) return;

  const daySpend = {{}};
  ALL_DATES.forEach(d => {{
    const rows = ALL_ROWS_BY_DATE[d] || [];
    daySpend[d] = rows.reduce((s, r) => s + r.spend, 0);
  }});

  let tabSortMode = 'date';
  let tabSortAsc  = true;
  let selectedDates = [ALL_DATES[ALL_DATES.length - 1]];  // 多选，默认最新一天
  let activeRange = null;  // 当前生效的快捷范围：'07'/'08'/... 或 'all'

  // 由选中日期推导高亮：选齐某月全部日期则该月按钮亮；选齐全部日期则"全年"亮
  function deriveRange() {{
    const sel = new Set(selectedDates);
    const months = [...new Set(ALL_DATES.map(d => d.slice(0, 2)))];
    if (ALL_DATES.every(d => sel.has(d))) {{
      activeRange = 'all';
    }} else {{
      activeRange = months.find(mm => {{
        const md = ALL_DATES.filter(d => d.startsWith(mm));
        return md.length > 0 && md.every(d => sel.has(d));
      }}) || null;
    }}
    const rangeBtns = document.getElementById('rangeBtns');
    if (rangeBtns) {{
      rangeBtns.querySelectorAll('.range-btn').forEach(el => {{
        el.classList.toggle('active', el.dataset.key === activeRange);
      }});
    }}
  }}

  function getSortedDates() {{
    return [...ALL_DATES].sort((a, b) => {{
      if (tabSortMode === 'spend') return tabSortAsc ? daySpend[a] - daySpend[b] : daySpend[b] - daySpend[a];
      return tabSortAsc ? a.localeCompare(b) : b.localeCompare(a);
    }});
  }}

  function mergedRows(dates) {{
    // 多天时按素材ID聚合，避免同一素材多行
    const map = {{}};
    dates.forEach(d => {{
      (ALL_ROWS_BY_DATE[d] || []).forEach(r => {{
        const key = r.id || r.name;
        if (!map[key]) {{
          map[key] = Object.assign({{}}, r);
          // 播放质量加权累加器（率×展示；有值才累计）
          map[key]._w3 = (r.q3 != null && r.q3 > 0) ? r.q3 * r.impressions : 0;
          map[key]._i3 = (r.q3 != null && r.q3 > 0) ? r.impressions : 0;
          map[key]._w5 = (r.q5 != null && r.q5 > 0) ? r.q5 * r.impressions : 0;
          map[key]._i5 = (r.q5 != null && r.q5 > 0) ? r.impressions : 0;
          map[key]._wf = (r.qf != null && r.qf > 0) ? r.qf * r.impressions : 0;
          map[key]._if = (r.qf != null && r.qf > 0) ? r.impressions : 0;
          map[key]._wd = (r.qd != null && r.qd > 0) ? r.qd * r.impressions : 0;
          map[key]._id = (r.qd != null && r.qd > 0) ? r.impressions : 0;
        }} else {{
          // 累加数值字段
          map[key].spend       += r.spend;
          map[key].impressions += r.impressions;
          map[key].clicks      += r.clicks;
          map[key].conversions += r.conversions;
          map[key].gaoquan     += r.gaoquan;
          // CPA/CTR 重新计算
          map[key].cpa = map[key].conversions > 0 ? map[key].spend / map[key].conversions : 0;
          map[key].ctr = map[key].impressions > 0 ? map[key].clicks / map[key].impressions * 100 : 0;
          map[key].cvr = map[key].clicks > 0 ? map[key].conversions / map[key].clicks * 100 : 0;
          map[key].deep_rate = map[key].conversions > 0 ? map[key].gaoquan / map[key].conversions * 100 : 0;
          // 播放质量：按展示数加权累加
          if (r.q3 != null && r.q3 > 0) {{ map[key]._w3 += r.q3 * r.impressions; map[key]._i3 += r.impressions; }}
          if (r.q5 != null && r.q5 > 0) {{ map[key]._w5 += r.q5 * r.impressions; map[key]._i5 += r.impressions; }}
          if (r.qf != null && r.qf > 0) {{ map[key]._wf += r.qf * r.impressions; map[key]._if += r.impressions; }}
          if (r.qd != null && r.qd > 0) {{ map[key]._wd += r.qd * r.impressions; map[key]._id += r.impressions; }}
        }}
      }});
    }});
    Object.values(map).forEach(m => {{
      m.q3 = m._i3 > 0 ? Math.round(m._w3 / m._i3 * 100) / 100 : null;
      m.q5 = m._i5 > 0 ? Math.round(m._w5 / m._i5 * 100) / 100 : null;
      m.qf = m._if > 0 ? Math.round(m._wf / m._if * 100) / 100 : null;
      m.qd = m._id > 0 ? Math.round(m._wd / m._id * 100) / 100 : null;
    }});
    return Object.values(map);
  }}

  function switchDays(dates) {{
    selectedDates = dates;
    window._switchDays = dates => switchDays(dates);
    window._selectedDates = selectedDates;
    // 同步顶部日期触发按钮文本（多选时显示「N 天已选」）
    const trig = document.querySelector('.tab-select');
    if (trig) {{
      trig.textContent = dates.length === 1
        ? dates[0] + ' ¥' + (daySpend[dates[0]] != null ? daySpend[dates[0]].toFixed(0) : '0')
        : dates.length + ' 天已选';
    }}
    const rows = mergedRows(dates);
    renderDay(rows, dates.join('+'));
    renderChannel(dates);
    updateTagCards(rows);
    updateTypeCards(rows);
    updatePersonCards(rows, mergeAuditData(dates));
    // 过审：多选时合并所有选中日期的过审数据
    updateAuditCards(mergeAuditData(dates));
    // 卡审分析跟随顶部日期筛选
    setRejDates(dates);
  }}

  function renderTabButtons() {{
    const sorted = getSortedDates();
    const container = document.getElementById('tabHeaders');
    container.querySelectorAll('.tab-btn, .tab-select, .tabs-label, .tab-multi-wrap').forEach(el => el.remove());
    const sortDiv = container.querySelector('.tabs-sort');

    if (sorted.length <= 7) {{
      // ≤7天：胶囊按钮多选
      sorted.forEach(d => {{
        const btn = document.createElement('button');
        const isSelected = selectedDates.includes(d);
        btn.className = 'tab-btn' + (isSelected ? ' active' : '');
        btn.textContent = d + ' ¥' + daySpend[d].toFixed(0);
        btn.onclick = () => {{
          if (selectedDates.includes(d)) {{
            if (selectedDates.length === 1) return; // 至少保留一天
            selectedDates = selectedDates.filter(x => x !== d);
          }} else {{
            selectedDates = [...selectedDates, d];
          }}
          deriveRange();
          renderTabButtons();
          switchDays(selectedDates);
        }};
        container.insertBefore(btn, sortDiv);
      }});
    }} else {{
      // >7天：多选下拉
      const wrap = document.createElement('div');
      wrap.className = 'tab-multi-wrap';
      wrap.style.cssText = 'position:relative;display:inline-block';

      const trigger = document.createElement('button');
      trigger.className = 'tab-select';
      trigger.style.cssText = 'cursor:pointer;min-width:160px;text-align:left';
      const updateTrigger = () => {{
        trigger.textContent = selectedDates.length === 1
          ? selectedDates[0] + ' ¥' + daySpend[selectedDates[0]].toFixed(0)
          : selectedDates.length + ' 天已选';
      }};
      updateTrigger();

      const dropdown = document.createElement('div');
      dropdown.style.cssText = 'display:none;position:absolute;top:100%;left:0;z-index:200;background:#fff;' +
        'border:1.5px solid var(--border);border-radius:8px;box-shadow:var(--shadow-md);min-width:200px;max-height:320px;overflow-y:auto;padding:6px 0';

      sorted.forEach(d => {{
        const item = document.createElement('div');
        const isSelected = selectedDates.includes(d);
        item.style.cssText = 'display:flex;align-items:center;gap:8px;padding:7px 14px;cursor:pointer;font-size:13px;' +
          (isSelected ? 'background:#EFF6FF;font-weight:600;color:#1E40AF' : 'color:#374151');
        item.innerHTML = `<span style="width:14px;text-align:center">${{isSelected ? '✓' : ''}}</span>` +
          `<span>${{d}} ¥${{daySpend[d].toFixed(0)}}</span>`;
        item.onclick = (e) => {{
          e.stopPropagation();
          if (selectedDates.includes(d)) {{
            if (selectedDates.length === 1) return;
            selectedDates = selectedDates.filter(x => x !== d);
          }} else {{
            selectedDates = [...selectedDates, d];
          }}
          // 重新渲染 dropdown items
          dropdown.querySelectorAll('div').forEach((el, i) => {{
            const dd = sorted[i];
            const sel = selectedDates.includes(dd);
            el.style.background = sel ? '#EFF6FF' : '';
            el.style.fontWeight  = sel ? '600' : '';
            el.style.color       = sel ? '#1E40AF' : '#374151';
            el.querySelector('span').textContent = sel ? '✓' : '';
          }});
          updateTrigger();
          deriveRange();
          switchDays(selectedDates);
        }};
        dropdown.appendChild(item);
      }});

      trigger.onclick = (e) => {{
        e.stopPropagation();
        dropdown.style.display = dropdown.style.display === 'none' ? 'block' : 'none';
      }};
      document.addEventListener('click', () => {{ dropdown.style.display = 'none'; }}, {{ once: false }});

      wrap.appendChild(trigger);
      wrap.appendChild(dropdown);
      container.insertBefore(wrap, sortDiv);
    }}
  }}

  function renderRangeButtons() {{
    const container = document.getElementById('rangeBtns');
    if (!container) return;
    const months = [...new Set(ALL_DATES.map(d => d.slice(0, 2)))];
    const ranges = [
      ...months.map(mm => ({{ label: mm.replace(/^0/, '') + '月', key: mm }})),
      {{ label: '全年', key: 'all' }},
    ];
    container.querySelectorAll('.range-btn').forEach(el => el.remove());
    const refresh = () => {{
      container.querySelectorAll('.range-btn').forEach(el => {{
        el.classList.toggle('active', el.dataset.key === activeRange);
      }});
    }};
    ranges.forEach(r => {{
      const btn = document.createElement('button');
      btn.className = 'range-btn';
      btn.dataset.key = r.key;
      btn.textContent = r.label;
      btn.onclick = () => {{
        if (activeRange === r.key) {{
          // 再次点击已点亮的按钮：取消范围，回到单日选择（默认最新一天）
          activeRange = null;
          selectedDates = [ALL_DATES[ALL_DATES.length - 1]];
          refresh();
          renderTabButtons();
          switchDays(selectedDates);
          return;
        }}
        activeRange = r.key;
        const dates = r.key === 'all' ? ALL_DATES : ALL_DATES.filter(d => d.startsWith(r.key));
        selectedDates = [...dates];
        refresh();
        renderTabButtons();
        switchDays(selectedDates);
      }};
      container.appendChild(btn);
    }});
    refresh();
  }}

  window.setTabSort = function(mode) {{
    if (tabSortMode === mode) {{
      tabSortAsc = !tabSortAsc;
    }} else {{
      tabSortMode = mode;
      tabSortAsc = mode === 'date';
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
  renderRangeButtons();
  deriveRange();
  switchDays(selectedDates);
}}

// ---------- 对比表 ----------
// ---------- 初始化 ----------
document.addEventListener('DOMContentLoaded', function() {{
  // 等 Chart.js 加载完再初始化
  function init() {{
    renderChannel(ALL_DATES.slice(-1));
    initRejectModules();
    if (!IS_MULTI) {{
      renderDay(ALL_ROWS, '');
      updateTagCards(ALL_ROWS);
      updateTypeCards(ALL_ROWS);
      updatePersonCards(ALL_ROWS, AUDIT_DATA);
      updateAuditCards(AUDIT_DATA);
    }} else {{
      document.getElementById('tabsContainer').style.display = '';
      document.getElementById('trendSection').style.display = '';
      if (typeof Chart !== 'undefined') initTrendChart();
      initTabs();
    }}
  }}
  if (typeof Chart !== 'undefined') {{
    init();
  }} else {{
    window.addEventListener('load', init);
  }}
}});
</script>
</body>
</html>
"""

def generate_html(days_data):
    # ---- 拆分渠道行：渠道账户不进明细，单独出总览 ----
    detail_days = []
    channel_stats = defaultdict(lambda: defaultdict(lambda: {'spend':0.0,'imp':0.0,'click':0.0,'conv':0.0,'gq':0.0}))
    for label, rows in days_data:
        detail_rows = []
        for r in rows:
            if r.get('_is_channel'):
                c = channel_stats[r['_account']][label]
                c['spend'] += r['_消耗']
                c['imp']   += r['_展示数']
                c['click'] += r['_点击数']
                c['conv']  += r['_转化数']
                c['gq']    += r['_高潜成交']
            else:
                detail_rows.append(r)
        detail_days.append((label, detail_rows))
    days_data = detail_days

    # 渠道逐日数据（随日期筛选联动）：{账户名: {日期: 指标}}
    channel_by_date = {}
    for acc, by_date in channel_stats.items():
        channel_by_date[ACCOUNT_NAMES.get(acc, acc)] = {
            label: {
                'spend': round(d['spend'], 2),
                'imp': int(d['imp']),
                'click': int(d['click']),
                'conv': int(d['conv']),
                'gq': int(d['gq']),
            }
            for label, d in by_date.items()
        }

    latest_label, latest_rows = days_data[-1]
    ls = compute_stats(latest_rows)
    is_multi = len(days_data) > 1


    # 最新日的人名数据用于图表（编导只看4人：小敏/瑞晨/嘉丽/雅迪，用户 2026-10-23 定）
    CORE_EDITORS = ['小敏', '瑞晨', '嘉丽', '雅迪']
    sorted_persons = sorted(
        [(p, d) for p, d in ls['by_person'].items()
         if d['消耗'] > 0 and p in CORE_EDITORS],
        key=lambda x: -x[1]['消耗']
    )
    person_labels = json.dumps([p for p, _ in sorted_persons], ensure_ascii=False)
    person_spend = json.dumps([round(d['消耗'], 2) for _, d in sorted_persons])
    person_cpa = json.dumps([round(d['CPA'], 2) for _, d in sorted_persons])
    person_bg_arr = json.dumps([PERSON_COLORS.get(p, '#94A3B8') for p, _ in sorted_persons])

    # 标签分组统计（仅视频素材，非图文）
    TAG_ORDER = ['A1', 'A2', 'A3', 'A4']
    TAG_NAMES = {'A1': 'A1技巧', 'A2': 'A2经历', 'A3': 'A3结果', 'A4': 'A4情绪'}
    TAG_COLORS_PY = {'A1': '#3B82F6', 'A2': '#8B5CF6', 'A3': '#10B981', 'A4': '#F59E0B'}
    tag_stats = defaultdict(lambda: {'消耗': 0, '转化': 0, '高潜': 0, '素材数': 0})
    for r in latest_rows:
        if r['_is_tuwen'] or r['_消耗'] == 0:
            continue
        tag_str = r['_tag']
        if not tag_str:
            continue
        for t in tag_str.split(','):
            base = t.split('-')[0].strip()
            if base in TAG_ORDER:
                tag_stats[base]['消耗']  += r['_消耗']
                tag_stats[base]['转化']  += r['_转化数']
                tag_stats[base]['高潜']  += r['_高潜成交']
                tag_stats[base]['素材数'] += 1

    tag_labels_js   = json.dumps([TAG_NAMES[t] for t in TAG_ORDER], ensure_ascii=False)
    tag_spend_js    = json.dumps([round(tag_stats[t]['消耗'], 2) for t in TAG_ORDER])
    tag_conv_js     = json.dumps([round(tag_stats[t]['转化'], 1) for t in TAG_ORDER])
    tag_gaoquan_js  = json.dumps([round(tag_stats[t]['高潜'], 1) for t in TAG_ORDER])
    tag_colors_js   = json.dumps([TAG_COLORS_PY[t] for t in TAG_ORDER])

    # 过审数据：按日期收集，格式 {label: audit_data}
    _data_dir = Path(Path(__file__).parent.parent / 'data')

    def load_audit_for_date(mmdd):
        audit_file = _data_dir / f'{mmdd}投放过审.csv'
        if not audit_file.exists():
            return {}
        version_stats  = defaultdict(lambda: {'pass': 0, 'fail': 0})
        tag_audit_stats = defaultdict(lambda: {'pass': 0, 'fail': 0})
        person_audit_stats = defaultdict(lambda: {'pass': [], 'fail': []})
        ALL_PERSONS = EDITORS + CUTTERS

        def base_name(n):
            """去掉改版后缀得到基础名（.mp4 在改版后缀后）"""
            n = n.strip()
            n = re.sub(r'\.mp4$', '', n)
            n = re.sub(r'-(\d)改$', '', n)
            n = re.sub(r'-改$', '', n)
            return n

        # 编导过审率按基础名合并：基础名 → 最优状态（任一版本通过即通过）
        person_merged = {}

        with open(audit_file, encoding='utf-8-sig') as f:
            for row in csv.DictReader(f):
                name = (row.get('视频名称') or '').strip()
                if not name: continue
                video_url = (row.get('视频链接','') or '').strip()
                if len(video_url) < 10: continue
                passed = row.get('审核建议','') == '审核通过'
                # 看不出编导的归为"代理素材"，不放入改版统计
                has_person = any(p in name for p in ALL_PERSONS)
                if is_ai(name):
                    # AI 素材单独分组，不走改版
                    pass  # tag_audit_stats 已处理
                elif has_person:
                    ver = extract_version(name)
                    if passed: version_stats[ver]['pass'] += 1
                    else:      version_stats[ver]['fail'] += 1
                else:
                    if passed: version_stats['代理素材']['pass'] += 1
                    else:      version_stats['代理素材']['fail'] += 1
                sid = (row.get('素材id','') or '').strip()
                tag = _LABEL_MAP.get(sid) or _LABEL_MAP.get(name) or extract_tag_from_name(name)
                bases = list(set(re.findall(r'A[1-4]', tag))) if tag else []
                tag_key = bases[0] if bases else ('AI' if is_ai(name) else '未标记')
                if passed: tag_audit_stats[tag_key]['pass'] += 1
                else:      tag_audit_stats[tag_key]['fail'] += 1
                # 编导维度：按基础名合并（同名多版本算一条，任一版本通过即通过）
                person = extract_person(name)
                if person == '其他': person = '未知'
                bn = base_name(name)
                rec = person_merged.get(bn)
                if rec is None:
                    person_merged[bn] = {'person': person, 'name': name, 'passed': passed}
                else:
                    if passed and not rec['passed']:
                        rec['passed'] = True
                        rec['name'] = name

        for bn, rec in person_merged.items():
            p = rec['person']
            if rec['passed']:
                person_audit_stats[p]['pass'].append(rec['name'])
            else:
                person_audit_stats[p]['fail'].append(rec['name'])

        version_order = ['0改', '1改', '2改', '3改', '代理素材']
        v_labels, v_pass, v_fail, v_pass_rate = [], [], [], []
        for v in version_order:
            p = version_stats[v]['pass']; f_ = version_stats[v]['fail']
            total = p + f_
            if total == 0: continue
            v_labels.append(v); v_pass.append(p); v_fail.append(f_)
            v_pass_rate.append(round(p/total*100, 1))

        TAG_ORDER_FULL = ['A1', 'A2', 'A3', 'A4', 'AI', '未标记']
        tg_labels, tg_pass, tg_fail, tg_pass_rate = [], [], [], []
        for t in TAG_ORDER_FULL:
            p = tag_audit_stats[t]['pass']; f_ = tag_audit_stats[t]['fail']
            total = p + f_
            if total == 0: continue
            tg_labels.append(t); tg_pass.append(p); tg_fail.append(f_)
            tg_pass_rate.append(round(p/total*100, 1))

        if not v_labels and not tg_labels and not person_audit_stats:
            return {}
        return {
            'version_labels': v_labels, 'pass_counts': v_pass,
            'fail_counts': v_fail, 'pass_rates': v_pass_rate,
            'tag_labels': tg_labels, 'tag_pass_counts': tg_pass,
            'tag_fail_counts': tg_fail, 'tag_pass_rates': tg_pass_rate,
            'person_audit': {p: {'pass': d['pass'], 'fail': d['fail']} for p, d in person_audit_stats.items()},
            'source_file': audit_file.name,
        }

    # 为每个日期加载过审数据
    audit_by_date = {}
    for label, _ in days_data:
        mmdd_str = label.replace('/', '')
        ad = load_audit_for_date(mmdd_str)
        if ad:
            audit_by_date[label] = ad
    # 默认用最新日期的过审数据
    audit_data = audit_by_date.get(latest_label, {})

    # 多日对比数据
    compare_data = build_compare(days_data) if is_multi else {}

    # ── 卡审分析：投放账户推送素材池 ─────────────────────────────────────
    reject_analysis = build_reject_analysis()
    test_audit_analysis = build_test_audit_analysis()
    # ── 近3周过审素材跑出表现 ─────────────────────────────────────────
    recent_pass_analysis = build_recent_pass_analysis()

    html = HTML_TEMPLATE.format(
        date_str=latest_label,
        total_spend=f"{ls['total_spend']:,.2f}",
        total_imp=f"{ls['total_imp']:,.0f}",
        total_conv=f"{ls['total_conv']:.0f}",
        avg_cpa=f"{ls['avg_cpa']:.2f}",
        avg_ctr=f"{ls['avg_ctr']:.2f}%",
        avg_cvr=f"{ls['total_conv']/ls['total_clicks']*100:.2f}%" if ls['total_clicks'] else '—',
        total_gaoquan=f"{ls['total_gaoquan']:.0f}",
        deep_rate=f"{ls['total_gaoquan']/ls['total_conv']*100:.1f}%" if ls['total_conv'] else '—',
        material_count=str(len(latest_rows)),
        person_colors_js=json.dumps(PERSON_COLORS, ensure_ascii=False),
        person_bg_js=json.dumps(PERSON_BG, ensure_ascii=False),
        rows_js=json.dumps(rows_to_json(latest_rows, include_video_url=True), ensure_ascii=False),
        person_labels=person_labels,
        person_order_js=json.dumps(EDITORS + CUTTERS + ['外部', '其他'], ensure_ascii=False),
        person_spend=person_spend,
        person_cpa=person_cpa,
        person_bg_arr=person_bg_arr,
        tag_labels_js=tag_labels_js,
        tag_spend_js=tag_spend_js,
        tag_conv_js=tag_conv_js,
        tag_gaoquan_js=tag_gaoquan_js,
        tag_colors_js=tag_colors_js,
        audit_data_js=json.dumps(audit_data, ensure_ascii=False),
        audit_by_date_js=json.dumps(audit_by_date, ensure_ascii=False),
        reject_analysis_js=json.dumps(reject_analysis, ensure_ascii=False),
        test_audit_analysis_js=json.dumps(test_audit_analysis, ensure_ascii=False),
        recent_pass_analysis_js=json.dumps(recent_pass_analysis, ensure_ascii=False),
        is_multi='true' if is_multi else 'false',
        compare_js=json.dumps(compare_data, ensure_ascii=False) if is_multi else '{}',
        all_dates_js=json.dumps([l for l, _ in days_data], ensure_ascii=False),
        all_rows_by_date_js=json.dumps(
            {l: rows_to_json(r, include_video_url=(l == latest_label)) for l, r in days_data},
            ensure_ascii=False
        ),
        channel_summary_js=json.dumps(channel_by_date, ensure_ascii=False),
    )

    # 内嵌 Chart.js，避免 CDN 网络依赖
    chart_js_path = Path(__file__).parent / 'chart.min.js'
    if chart_js_path.exists():
        chart_js_code = chart_js_path.read_text(encoding='utf-8')
        html = html.replace(
            '<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>',
            f'<script>{chart_js_code}</script>',
            1
        )
    return html

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
    # 先扫描所有文件建立 名称→账户id 映射（修正科学计数法账户）
    for f in files:
        load_name_account_map(str(f))
        load_name_first_day_map(str(f))
    # 加载历史打标表
    label_csv = data_dir / '历史打标.csv'
    if label_csv.exists():
        load_label_map(str(label_csv))
        print(f'加载打标表: {len(_LABEL_MAP)} 条')

    for f in files:
        m = re.search(r'(\d{4})', f.stem)
        mmdd = m.group(1) if m else f.stem[-4:]
        label = f"{mmdd[:2]}/{mmdd[2:]}"
        rows = load_csv(f)
        # 填充标签（需在 load_label_map 之后）
        for r in rows:
            r['_tag'] = get_label(r) if not r['_is_tuwen'] else ''
        days_data.append((label, rows))
        s = compute_stats(rows)
        print(f"{label}: {len(rows)}条  消耗¥{s['total_spend']:.2f}  转化{s['total_conv']:.0f}  高潜{s['total_gaoquan']:.0f}")

    # 补标检查放在分页生成之前（分页失败兜底也需要它）
    _, latest_rows = days_data[-1]
    unlabeled = []
    for r in latest_rows:
        if safe_float(r.get('_转化数', 0)) == 0: continue
        if r['_is_tuwen']: continue
        if r.get('_is_channel'): continue
        if not r['_tag']:
            unlabeled.append((r['_消耗'], r['_转化数'], r['_name']))
    if unlabeled:
        unlabeled.sort(reverse=True)
        print(f'\n⚠️  需要补标签（有转化但未打标）：{len(unlabeled)} 条')
        for s, c, n in unlabeled:
            print(f'  ¥{s:.2f}  转化{c:.0f}  {n}')
        print()

    out_dir = Path(__file__).parent.parent / 'reports'
    out_dir.mkdir(exist_ok=True)
    latest_mmdd = re.search(r'(\d{4})', files[-1].stem).group(1)
    latest_label = f"{latest_mmdd[:2]}/{latest_mmdd[2:]}"

    # 分页生成（总览/卡审/跑出时效/编导明细，一个脚本一次全出）
    try:
        import report_pages
        written = report_pages.generate_pages(days_data, latest_label, latest_mmdd, out_dir)
        for p in written:
            print(f'报告已生成: {p}')
    except Exception as e:
        # 兜底：仍生成旧版单页，保证日报流程不中断
        import traceback
        traceback.print_exc()
        print(f'[警告] 分页生成失败，回退旧版单页：{e}')
        html = generate_html(days_data)
        out_path = out_dir / f'引导素材每日分析_{latest_mmdd}.html'
        with open(out_path, 'w', encoding='utf-8') as f:
            f.write(html)
        print(f'报告已生成: {out_path}')

if __name__ == '__main__':
    main()