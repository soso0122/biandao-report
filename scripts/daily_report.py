#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
每日数据日报生成器
用法:
  python3 scripts/daily_report.py 0908        # 生成 9月8日 日报
  python3 scripts/daily_report.py 0908 --push # 生成并推送企微
"""
import csv, json, sys, os, re, urllib.request
from pathlib import Path
from collections import defaultdict

DATA_DIR    = Path(__file__).parent.parent / 'data'
REPORTS_DIR = Path(__file__).parent.parent / 'reports' / 'daily'

WECOM_WEBHOOK = "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=12caf804-d031-4d77-a740-4609e9ed430e"
DAILY_REPORT_URL = "https://soso0122.github.io/daily-report/"
DAILY_REPORT_REPO = "/Users/soso/Desktop/daily-report"

# ──────────────────────────────────────────
# 通用工具
# ──────────────────────────────────────────
AGENT_NAME_MAP = {
    '申坤互动（北京）信息技术有限公司': '申坤',
    '成都发条荔枝文化传媒有限公司': '荔枝',
    '天津掌视广通信息技术有限公司': '掌视',
    '北京有范儿科技有限公司': '有范',
    '北京启航时代文化传媒有限公司': '启航',
}

def normalize_agent(name):
    return AGENT_NAME_MAP.get(name, name)

def safe_float(v):
    try:
        return float(str(v).replace(',', '').replace('%', '') or 0)
    except:
        return 0.0

def fmt_money(v):
    return f"¥{v:,.2f}"

def fmt_pct(v):
    return f"{v:.2f}%"

def fmt_int(v):
    return f"{int(v):,}"

# ──────────────────────────────────────────
# 模块一：引导加微
# ──────────────────────────────────────────
GUIDE_PERSONS = ['小敏', '嘉丽', '瑞晨', '浩正', '雅迪', '魏怡', '婷玉']
GUIDE_EDITORS = set(['小敏', '嘉丽', '浩正', '雅迪', '婷玉'])
GUIDE_CUTTERS = ['魏怡', '瑞晨', '国星']

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

def _is_homepage(name):
    n = name.strip()
    return bool(re.fullmatch(r'\d+', n) or re.fullmatch(r'[\d.]+[eE][+\-]?\d+', n))

def _extract_person(name):
    for p in GUIDE_EDITORS:
        if p in name:
            return p
    for p in GUIDE_CUTTERS:
        if p in name:
            return p
    return '其他'

# 渠道账户（外投合作账号）：数据不进明细，与 generate_report_daily_guide.py 保持一致
CHANNEL_ACCOUNTS = {'1873204791217159', '1873204789662083', '1872584956721257', '1869499299085324'}  # jl01-jl04

def load_guide(mmdd):
    path = DATA_DIR / f'引导加微每日数据-{mmdd}.csv'
    if not path.exists():
        return None, f"找不到文件: {path.name}"
    with open(path, encoding='utf-8-sig') as f:
        rows = list(csv.DictReader(f))
    out = []
    for r in rows:
        account = (r.get('账户id') or '').strip()
        if account in CHANNEL_ACCOUNTS:
            continue
        name = (r.get('视频名称') or '').strip()
        if not name:
            continue
        is_hp = _is_homepage(name)
        person = '主页' if is_hp else _extract_person(name)
        out.append({
            'name': name,
            'person': person,
            'spend': safe_float(r.get('消耗')),
            'conv': safe_float(r.get('转化数')),
            'cpa': safe_float(r.get('转化成本')),
            'gaoquan': safe_float(r.get('回访-高潜成交(计费时间)')),
            'ctr': safe_float(r.get('点击率(%)')),
            'cpm': safe_float(r.get('平均千次展现费用(元)')),
            'imp': safe_float(r.get('展示数')),
            'video_url': r.get('视频链接', ''),
        })
    return out, None

def guide_stats(rows):
    ts = sum(r['spend'] for r in rows)
    tc = sum(r['conv'] for r in rows)
    tg = sum(r['gaoquan'] for r in rows)
    by_person = defaultdict(lambda: {'spend': 0, 'conv': 0, 'gaoquan': 0, 'count': 0})
    for r in rows:
        p = r['person']
        by_person[p]['spend']   += r['spend']
        by_person[p]['conv']    += r['conv']
        by_person[p]['gaoquan'] += r['gaoquan']
        by_person[p]['count']   += 1
    return {
        'total_spend': ts,
        'total_conv': tc,
        'total_gaoquan': tg,
        'avg_cpa': ts / tc if tc else 0,
        'deep_rate': tg / tc * 100 if tc else 0,
        'by_person': dict(by_person),
        'mat_count': len(set(r['name'] for r in rows if r['spend'] > 0)),    }

# ──────────────────────────────────────────
# 模块二：千川（视频号直播 + 千川）
# ──────────────────────────────────────────
def load_qianchuan(mmdd):
    path = DATA_DIR / f'【日报】千川报表-{mmdd}.csv'
    if not path.exists():
        return None, f"找不到文件: {path.name}"
    with open(path, encoding='utf-8-sig') as f:
        rows = list(csv.DictReader(f))
    out = []
    for r in rows:
        spend = safe_float(r.get('消耗'))
        # 成交单量列名随渠道口径变化：兼容旧列名和新的长列名
        orders = safe_float(r.get('成交单量'))
        if not orders and any('成交单量' in k for k in r):
            long_key = next(k for k in r if '成交单量' in k)
            orders = safe_float(r.get(long_key))
        if spend <= 0 and orders <= 0:
            continue
        out.append({
            'name': (r.get('素材名称') or '').strip(),
            'channel': (r.get('渠道') or '').strip(),
            'product': (r.get('投放产品') or '').strip(),
            'source': (r.get('来源') or '').strip(),
            'agent': normalize_agent((r.get('代理商') or '').strip()),
            'marketer': (r.get('市场员') or '').strip(),
            'spend': spend,
            'gmv': safe_float(r.get('成交GMV')),
            'orders': orders,
            'roi': safe_float(r.get('ROI')),
            'cpm': safe_float(r.get('CPM（千次曝光成本）')),
            'cpa': safe_float(r.get('CPA')),
            'ctr': safe_float(r.get('CTR')),
            'cvr': safe_float(r.get('CVR')),
            'rate3s': safe_float(r.get('3s播放率')),
            'preview': r.get('素材预览', ''),
        })
    return out, None

def qianchuan_stats(rows):
    ts = sum(r['spend'] for r in rows)
    tg = sum(r['gmv'] for r in rows)
    to = sum(r['orders'] for r in rows)
    by_channel = defaultdict(lambda: {'spend': 0, 'gmv': 0, 'orders': 0, 'count': 0, 'imp': 0, 'click': 0, 'conv': 0})
    by_source  = defaultdict(lambda: {'spend': 0, 'gmv': 0, 'orders': 0, 'imp': 0, 'click': 0, 'conv': 0})
    total_imp   = 0
    total_click = 0
    total_conv  = 0
    for r in rows:
        imp   = r['spend'] / r['cpm'] * 1000 if r['cpm'] else 0
        click = imp * r['ctr'] / 100
        conv  = click * r['cvr'] / 100
        by_channel[r['channel']]['spend']  += r['spend']
        by_channel[r['channel']]['gmv']    += r['gmv']
        by_channel[r['channel']]['orders'] += r['orders']
        by_channel[r['channel']]['count']  += 1
        by_channel[r['channel']]['imp']    += imp
        by_channel[r['channel']]['click']  += click
        by_channel[r['channel']]['conv']   += conv
        by_source[r['source']]['spend']    += r['spend']
        by_source[r['source']]['gmv']      += r['gmv']
        by_source[r['source']]['orders']   += r['orders']
        by_source[r['source']]['imp']      += imp
        by_source[r['source']]['click']    += click
        by_source[r['source']]['conv']     += conv
        total_imp   += imp
        total_click += click
        total_conv  += conv
    real_ctr = total_click / total_imp * 100 if total_imp else 0
    real_cvr = total_conv  / total_click * 100 if total_click else 0
    real_cpm = ts / total_imp * 1000 if total_imp else 0
    return {
        'total_spend': ts,
        'total_gmv': tg,
        'total_orders': to,
        'total_imp': total_imp,
        'avg_roi': tg / ts if ts else 0,
        'avg_cpa': ts / to if to else 0,
        'avg_ctr': real_ctr,
        'avg_cvr': real_cvr,
        'avg_cpm': real_cpm,
        'by_channel': dict(by_channel),
        'by_source': dict(by_source),
        'mat_count': len(set(r['name'] for r in rows)),
    }

# ──────────────────────────────────────────
# 模块三：B站
# ──────────────────────────────────────────
BILIBILI_AGENTS = {
    '3772984': '酱鱼', '4071240': '酱鱼', '4227513': '酱鱼',
    '4227514': '酱鱼', '4227515': '酱鱼', '4516413': '酱鱼',
    '4514759': '酱鱼',
    '4217725': '六月', '4109939': '六月', '4569704': '六月', '4100084': '六月',
    '4542870': '墨幸', '4541275': '墨幸', '4631746': '墨幸',
    '4631174': '墨幸', '4641480': '墨幸', '4641479': '墨幸',
}

def get_bili_agent(account_id):
    return BILIBILI_AGENTS.get(str(account_id).strip(), '其他')

def load_bilibili(mmdd):
    path = DATA_DIR / f'【日报】创意报表- B站-{mmdd}.csv'
    if not path.exists():
        return None, f"找不到文件: {path.name}"
    with open(path, encoding='utf-8-sig') as f:
        rows = list(csv.DictReader(f))
    raw = []
    for r in rows:
        spend = safe_float(r.get('总花费'))
        if spend <= 0:
            continue
        raw.append({
            'title': re.sub(r'\{area,[^}]+\}', '', (r.get('标题内容') or '')).strip(),
            'account': (r.get('账户名称') or '').strip(),
            'account_id': (r.get('账户ID') or '').strip(),
            'agent': get_bili_agent(r.get('账户ID','')),
            'video_url': r.get('视频URL', ''),
            'spend': spend,
            'imp': safe_float(r.get('展示量')),
            'clicks': safe_float(r.get('点击量')),
            'ctr': safe_float(r.get('点击率').replace('%','') if r.get('点击率') else 0),
            'cpm': safe_float(r.get('千次展示价格')),
            'form_cnt': safe_float(r.get('表单提交数')),
            'form_cost': safe_float(r.get('表单提交成本')),
            'lead_cnt': safe_float(r.get('有效线索数')),
            'lead_cost': safe_float(r.get('有效线索成本')),
            'wx_cnt': safe_float(r.get('微信加粉数')),
            'wx_cost': safe_float(r.get('微信加粉成本')),
        })
    # 按标题合并
    merged = defaultdict(lambda: {'title':'','video_url':'','spend':0,'imp':0,'clicks':0,
        'form_cnt':0,'lead_cnt':0,'wx_cnt':0,'accounts':set(),'agents':set()})
    for r in raw:
        m = merged[r['title']]
        m['title']    = r['title']
        m['video_url'] = m['video_url'] or r['video_url']
        m['spend']    += r['spend']
        m['imp']      += r['imp']
        m['clicks']   += r['clicks']
        m['form_cnt'] += r['form_cnt']
        m['lead_cnt'] += r['lead_cnt']
        m['wx_cnt']   += r['wx_cnt']
        m['accounts'].add(r['account'])
        m['agents'].add(r['agent'])
    out = []
    for m in merged.values():
        out.append({
            'title': m['title'],
            'account': f"{len(m['accounts'])}个账户",
            'video_url': m['video_url'],
            'spend': m['spend'],
            'imp': m['imp'],
            'clicks': m['clicks'],
            'ctr': m['clicks'] / m['imp'] * 100 if m['imp'] else 0,
            'cpm': m['spend'] / m['imp'] * 1000 if m['imp'] else 0,
            'form_cnt': m['form_cnt'],
            'form_cost': m['spend'] / m['form_cnt'] if m['form_cnt'] else 0,
            'lead_cnt': m['lead_cnt'],
            'lead_cost': m['spend'] / m['lead_cnt'] if m['lead_cnt'] else 0,
            'wx_cnt': m['wx_cnt'],
            'wx_cost': m['spend'] / m['wx_cnt'] if m['wx_cnt'] else 0,
        })
    return out, None, raw

def get_bili_agent(account_id):
    return BILIBILI_AGENTS.get(str(account_id).strip(), '其他')

def bilibili_stats(rows, raw=None):
    ts   = sum(r['spend'] for r in rows)
    ti   = sum(r['imp'] for r in rows)
    tclk = sum(r['clicks'] for r in rows)
    tf   = sum(r['form_cnt'] for r in rows)
    tl   = sum(r['lead_cnt'] for r in rows)
    tw   = sum(r['wx_cnt'] for r in rows)
    by_agent = defaultdict(lambda: {'spend':0,'imp':0,'clicks':0,'form_cnt':0,'lead_cnt':0,'wx_cnt':0})
    for r in (raw or []):
        a = r.get('agent', '其他')
        by_agent[a]['spend']    += r['spend']
        by_agent[a]['imp']      += r['imp']
        by_agent[a]['clicks']   += r['clicks']
        by_agent[a]['form_cnt'] += r['form_cnt']
        by_agent[a]['lead_cnt'] += r['lead_cnt']
        by_agent[a]['wx_cnt']   += r['wx_cnt']
    return {
        'total_spend': ts,
        'total_imp': ti,
        'total_clicks': tclk,
        'avg_ctr': tclk / ti * 100 if ti else 0,
        'avg_cpm': ts / ti * 1000 if ti else 0,
        'form_cnt': tf,
        'form_cost': ts / tf if tf else 0,
        'lead_cnt': tl,
        'lead_cost': ts / tl if tl else 0,
        'wx_cnt': tw,
        'wx_cost': ts / tw if tw else 0,
        'mat_count': len(rows),
        'by_agent': dict(by_agent),
    }

# ──────────────────────────────────────────
# 多日数据收集（供前端日期多选聚合）
# ──────────────────────────────────────────
def _delta_pair(curr, prev, fmt='money'):
    """与单日模板 delta_fmt 一致：[文本, 颜色] 或 None"""
    if prev is None or abs(curr - prev) < 0.005:
        return None
    sign = '+' if curr >= prev else '-'
    color = '#059669' if curr >= prev else '#DC2626'
    if fmt == 'money':
        s = f"{sign}¥{abs(curr-prev):,.2f}"
    elif fmt == 'int':
        s = f"{sign}{abs(curr-prev):.0f}"
    else:  # pct
        s = f"{sign}{abs(curr-prev):.2f}%"
    return [s, color]

def _guide_day(rows):
    gs = guide_stats(rows)
    # 同名素材可能有多行（分账户记录），先按 素材名×人物 聚合
    agg = defaultdict(lambda: {'spend': 0, 'conv': 0, 'gao': 0})
    for r in rows:
        k = (r['name'], r['person'])
        agg[k]['spend'] += r['spend']
        agg[k]['conv'] += r['conv']
        agg[k]['gao'] += r['gaoquan']
    cand = {}
    for (name, person), d in sorted(agg.items(), key=lambda x: -x[1]['spend']):
        if d['spend'] <= 0:
            break
        cand[name] = {'name': name, 'person': person, 'spend': d['spend'],
                      'conv': d['conv'], 'gao': d['gao']}
        if len(cand) >= 20:
            break
    for (name, person), d in sorted(agg.items(), key=lambda x: -x[1]['gao']):
        if name in cand or d['gao'] <= 0:
            continue
        cand[name] = {'name': name, 'person': person, 'spend': d['spend'],
                      'conv': d['conv'], 'gao': d['gao']}
        if len(cand) >= 25:
            break
    top = [{
        'name': r['name'], 'person': r['person'],
        'spend': round(r['spend'], 2), 'conv': r['conv'],
        'cpa': round(r['spend'] / r['conv'], 2) if r['conv'] else 0,
        'gaoquan': r['gao'],
    } for r in cand.values()]
    by_person = {}
    for p, d in gs['by_person'].items():
        mat_count = len(set(r['name'] for r in rows if r['person'] == p and r['spend'] > 0))
        by_person[p] = {'spend': round(d['spend'],2), 'conv': d['conv'], 'gao': d['gaoquan'],
                        'mat_count': mat_count}
    return {
        'stats': {'spend': round(gs['total_spend'],2), 'conv': gs['total_conv'], 'gao': gs['total_gaoquan'],
                  'cpa': round(gs['avg_cpa'],2), 'deep_rate': round(gs['deep_rate'],2),
                  'mat_count': gs['mat_count']},
        'by_person': by_person,
        'top': top,
    }

def _qc_day(rows):
    qs = qianchuan_stats(rows)
    merged = defaultdict(lambda: {'name':'','spend':0,'orders':0,'imp':0,'click':0,'conv':0,
                                  'agents':set(),'preview':''})
    for r in rows:
        m = merged[r['name']]
        m['name'] = r['name']
        m['preview'] = m['preview'] or r['preview']
        m['spend'] += r['spend']
        m['orders'] += r['orders']
        imp = r['spend']/r['cpm']*1000 if r['cpm'] else 0
        m['imp'] += imp
        m['click'] += imp * r['ctr'] / 100
        m['conv'] += imp * r['ctr'] / 100 * r['cvr'] / 100
        m['agents'].add(r['agent'] or '—')
    mats = [{
        'name': m['name'], 'agents': sorted(m['agents']),
        'spend': round(m['spend'],2), 'orders': m['orders'],
        'imp': round(m['imp'],0), 'click': round(m['click'],0), 'conv': round(m['conv'],2),
        'preview': m['preview'],
    } for m in sorted(merged.values(), key=lambda x: -x['spend']) if m['orders'] > 0]
    by_agent = defaultdict(lambda: {'spend':0,'gmv':0,'orders':0,'imp':0,'click':0,'conv':0})
    for r in rows:
        key = r['agent'] or '未知'
        by_agent[key]['spend'] += r['spend']
        by_agent[key]['gmv'] += r['gmv']
        by_agent[key]['orders'] += r['orders']
        imp = r['spend'] / r['cpm'] * 1000 if r['cpm'] else 0
        by_agent[key]['imp'] += imp
        by_agent[key]['click'] += imp * r['ctr'] / 100
        by_agent[key]['conv'] += imp * r['ctr'] / 100 * r['cvr'] / 100
    by_agent_out = {a: {'spend': round(d['spend'],2), 'gmv': round(d['gmv'],2), 'orders': d['orders'],
                        'imp': round(d['imp'],0), 'click': round(d['click'],0), 'conv': round(d['conv'],2)}
                    for a, d in by_agent.items()}
    by_channel_out = {c: {'spend': round(d['spend'],2), 'orders': d['orders'],
                          'imp': round(d['imp'],0), 'click': round(d['click'],0), 'conv': round(d['conv'],2),
                          'gmv': round(d['gmv'],2)}
                      for c, d in qs['by_channel'].items()}
    detail = [{
        'name': r['name'], 'agent': r['agent'], 'spend': round(r['spend'],2), 'orders': r['orders'],
        'ctr': round(r['ctr'],2), 'cvr': round(r['cvr'],2), 'cpm': round(r['cpm'],2),
        'cpa': round(r['cpa'],2), 'preview': r['preview'],
    } for r in sorted([x for x in rows if x['orders'] > 0], key=lambda x: -x['spend'])]
    return {
        'stats': {'spend': round(qs['total_spend'],2), 'gmv': round(qs['total_gmv'],2), 'orders': qs['total_orders'],
                  'roi': round(qs['avg_roi'],4), 'cpa': round(qs['avg_cpa'],2),
                  'imp': round(qs['total_imp'],0) if 'total_imp' in qs else 0,
                  'ctr': round(qs['avg_ctr'],2), 'cvr': round(qs['avg_cvr'],2), 'cpm': round(qs['avg_cpm'],2),
                  'mat_count': qs['mat_count']},
        'by_channel': by_channel_out,
        'by_agent': by_agent_out,
        'mats': mats,
        'detail': detail,
    }

def _bili_day(rows, raw):
    bs = bilibili_stats(rows, raw)
    top = [{
        'title': r['title'], 'video_url': r['video_url'],
        'spend': round(r['spend'],2), 'imp': round(r['imp'],0), 'clicks': round(r['clicks'],0),
        'ctr': round(r['ctr'],2), 'cpm': round(r['cpm'],2),
        'form_cnt': r['form_cnt'], 'form_cost': round(r['form_cost'],2),
        'lead_cnt': r['lead_cnt'], 'lead_cost': round(r['lead_cost'],2),
        'wx_cnt': r['wx_cnt'], 'wx_cost': round(r['wx_cost'],2),
    } for r in sorted([x for x in rows if x['lead_cnt'] > 0 or x['wx_cnt'] > 0 or x['form_cnt'] > 0],
                      key=lambda x: -x['spend'])[:30]]
    by_agent = {a: {'spend': round(d['spend'],2), 'imp': round(d['imp'],0), 'clicks': round(d['clicks'],0),
                    'form_cnt': d['form_cnt'], 'lead_cnt': d['lead_cnt'], 'wx_cnt': d['wx_cnt']}
                for a, d in bs['by_agent'].items()}
    return {
        'stats': {'spend': round(bs['total_spend'],2), 'imp': round(bs['total_imp'],0),
                  'clicks': round(bs['total_clicks'],0),
                  'ctr': round(bs['avg_ctr'],2), 'cpm': round(bs['avg_cpm'],2),
                  'form_cnt': bs['form_cnt'], 'form_cost': round(bs['form_cost'],2),
                  'lead_cnt': bs['lead_cnt'], 'lead_cost': round(bs['lead_cost'],2),
                  'wx_cnt': bs['wx_cnt'], 'wx_cost': round(bs['wx_cost'],2),
                  'mat_count': bs['mat_count']},
        'by_agent': by_agent,
        'top': top,
    }

def collect_multi_day_data(target_mmdd, days=30):
    """收集 target 往前 N 天的日级数据（有文件才收录），供前端日期多选聚合。"""
    from datetime import datetime, timedelta
    tgt = datetime.strptime(f"2026{target_mmdd}", "%Y%m%d")
    dates, cache = [], {}
    for i in range(days):
        d = tgt - timedelta(days=i)
        m = f"{d.month:02d}{d.day:02d}"
        g, ge = load_guide(m)
        q, qe = load_qianchuan(m)
        b, be, br = load_bilibili(m)
        if not (g or q or b):
            continue
        dates.append(m)
        cache[m] = (g, ge, q, qe, b, be, br)
    dates.sort()
    out_days, prev = {}, {'guide': None, 'qc': None, 'bili': None}
    for m in dates:
        g, ge, q, qe, b, be, br = cache[m]
        day = {}
        if g:
            gd = _guide_day(g)
            day['guide'] = {
                'data': gd,
                'delta': {
                    'spend': _delta_pair(gd['stats']['spend'], prev['guide']['data']['stats']['spend'] if prev['guide'] else None, 'money'),
                    'conv': _delta_pair(gd['stats']['conv'], prev['guide']['data']['stats']['conv'] if prev['guide'] else None, 'int'),
                    'cpa': _delta_pair(gd['stats']['cpa'], prev['guide']['data']['stats']['cpa'] if prev['guide'] else None, 'money'),
                    'gao': _delta_pair(gd['stats']['gao'], prev['guide']['data']['stats']['gao'] if prev['guide'] else None, 'int'),
                    'deep': _delta_pair(gd['stats']['deep_rate'], prev['guide']['data']['stats']['deep_rate'] if prev['guide'] else None, 'pct'),
                },
            }
            prev['guide'] = day['guide']
        if q:
            qd = _qc_day(q)
            day['qc'] = {
                'data': qd,
                'delta': {
                    'spend': _delta_pair(qd['stats']['spend'], prev['qc']['data']['stats']['spend'] if prev['qc'] else None, 'money'),
                    'gmv': _delta_pair(qd['stats']['gmv'], prev['qc']['data']['stats']['gmv'] if prev['qc'] else None, 'money'),
                    'orders': _delta_pair(qd['stats']['orders'], prev['qc']['data']['stats']['orders'] if prev['qc'] else None, 'int'),
                    'roi': _delta_pair(qd['stats']['roi'], prev['qc']['data']['stats']['roi'] if prev['qc'] else None, 'pct'),
                    'cpa': _delta_pair(qd['stats']['cpa'], prev['qc']['data']['stats']['cpa'] if prev['qc'] else None, 'money'),
                    'ctr': _delta_pair(qd['stats']['ctr'], prev['qc']['data']['stats']['ctr'] if prev['qc'] else None, 'pct'),
                    'cvr': _delta_pair(qd['stats']['cvr'], prev['qc']['data']['stats']['cvr'] if prev['qc'] else None, 'pct'),
                    'cpm': _delta_pair(qd['stats']['cpm'], prev['qc']['data']['stats']['cpm'] if prev['qc'] else None, 'money'),
                },
            }
            prev['qc'] = day['qc']
        if b:
            bd = _bili_day(b, br)
            day['bili'] = {
                'data': bd,
                'delta': {
                    'spend': _delta_pair(bd['stats']['spend'], prev['bili']['data']['stats']['spend'] if prev['bili'] else None, 'money'),
                    'ctr': _delta_pair(bd['stats']['ctr'], prev['bili']['data']['stats']['ctr'] if prev['bili'] else None, 'pct'),
                    'cpm': _delta_pair(bd['stats']['cpm'], prev['bili']['data']['stats']['cpm'] if prev['bili'] else None, 'money'),
                    'form': _delta_pair(bd['stats']['form_cnt'], prev['bili']['data']['stats']['form_cnt'] if prev['bili'] else None, 'int'),
                    'lead': _delta_pair(bd['stats']['lead_cnt'], prev['bili']['data']['stats']['lead_cnt'] if prev['bili'] else None, 'int'),
                    'wx': _delta_pair(bd['stats']['wx_cnt'], prev['bili']['data']['stats']['wx_cnt'] if prev['bili'] else None, 'int'),
                },
            }
            prev['bili'] = day['bili']
        out_days[m] = day
    return {'dates': dates, 'default': target_mmdd, 'days': out_days,
            'colors': PERSON_COLORS, 'bgs': PERSON_BG}


# ──────────────────────────────────────────
# HTML 生成
# ──────────────────────────────────────────
# ──────────────────────────────────────────
# HTML 生成
# ──────────────────────────────────────────
def build_html(mmdd, guide_rows, guide_err, qc_rows, qc_err, bili_rows, bili_err, bili_raw=None):
    date_str = f"{mmdd[:2]}月{mmdd[2:]}日"
    multi = collect_multi_day_data(mmdd, days=30)
    data_json = json.dumps(multi, ensure_ascii=False)
    return (HTML_TEMPLATE
            .replace('{date_str}', date_str)
            .replace('{DATA_JSON}', data_json))


HTML_TEMPLATE = '''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>每日素材数据 · {date_str}</title>
<style>
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
:root{
  --bg:#F8FAFC;--card:#fff;--border:#DBEAFE;
  --primary:#1E40AF;--primary-light:#3B82F6;
  --accent:#D97706;--accent-bg:#FFFBEB;
  --text:#1E3A8A;--text-secondary:#64748B;--text-muted:#94A3B8;
  --shadow:0 1px 3px rgba(0,0,0,.08);
  --radius:10px;
  font-family:system-ui,-apple-system,sans-serif;
}
body{background:var(--bg);color:var(--text);font-size:14px;line-height:1.5}
.header{
  background:linear-gradient(135deg,#1E3A8A 0%,#1E40AF 60%,#2563EB 100%);
  padding:20px 28px;display:flex;align-items:center;justify-content:space-between;
}
.header h1{color:#fff;font-size:18px;font-weight:700}
.header p{color:rgba(255,255,255,.65);font-size:12px;margin-top:2px}
.header-badge{background:rgba(255,255,255,.15);border:1px solid rgba(255,255,255,.25);
  color:#fff;padding:5px 14px;border-radius:20px;font-size:13px;font-weight:600}
.page{max-width:1500px;margin:0 auto;padding:24px;display:flex;gap:16px;align-items:flex-start}
/* 日期多选侧栏：滚动时固定 */
.date-picker{
  position:sticky;top:16px;flex:0 0 190px;
  background:var(--card);border:1px solid var(--border);border-radius:var(--radius);
  box-shadow:var(--shadow);padding:12px 12px;margin-bottom:0;max-height:calc(100vh - 32px);overflow-y:auto;
}
.page-content{flex:1 1 auto;min-width:0}
.date-picker .dp-label{display:block;font-size:12px;font-weight:700;color:var(--text-secondary);
  margin:0 0 8px;white-space:nowrap}
.date-chip{
  display:block;width:100%;text-align:center;border:1.5px solid var(--border);background:var(--bg);
  color:var(--text-secondary);border-radius:16px;padding:4px 8px;font-size:12px;font-weight:600;cursor:pointer;
  transition:all .12s;user-select:none;margin-bottom:6px;white-space:nowrap;
}
.date-chip:hover{border-color:var(--primary-light);color:var(--primary)}
.date-chip.on{background:var(--primary);border-color:var(--primary);color:#fff}
.date-chip.dim{opacity:.35}
.date-quick{display:flex;flex-wrap:wrap;gap:6px;margin:2px 0 10px}
.date-quick button{
  flex:1 1 auto;border:1.5px solid var(--border);background:var(--bg);color:var(--text-secondary);
  border-radius:14px;padding:3px 8px;font-size:11px;font-weight:600;cursor:pointer;transition:all .12s;
}
.date-quick button:hover{border-color:var(--primary-light);color:var(--primary)}
@media(max-width:900px){{
  .page{{flex-direction:column}}
  .date-picker{{position:static;max-height:none;flex:none;width:100%}}
}}
.module{background:var(--card);border:1px solid var(--border);border-radius:var(--radius);
  margin-bottom:24px;box-shadow:var(--shadow);overflow:hidden}
.section-header{padding:14px 20px;border-bottom:1px solid var(--border);
  display:flex;align-items:center;background:#F1F5F9}
.section-header h2{font-size:15px;font-weight:700;color:var(--primary);
  display:flex;align-items:center;gap:8px}
.section-header h2::before{content:'';display:inline-block;width:3px;height:16px;
  background:var(--primary-light);border-radius:2px}
.module-body{padding:20px}
.kpi-grid{display:flex;flex-wrap:wrap;gap:10px;margin-bottom:20px}
.kpi-grid.kpi-full .kpi-card{flex:1 1 0;max-width:none}
/* B站指标卡：量+成本+环比 */
.metric-row{display:flex;gap:10px;margin-bottom:20px}
.metric-card{flex:1 1 0;min-width:0;background:var(--card);border:1px solid var(--border);
  border-radius:8px;padding:12px 16px;box-shadow:var(--shadow)}
.metric-card.metric-accent{background:var(--accent-bg);border-color:#FCD34D}
.metric-card.metric-accent .metric-num{color:var(--accent)}
.metric-label{font-size:11px;color:var(--text-secondary);font-weight:600;
  letter-spacing:.4px;margin-bottom:8px;white-space:nowrap}
.metric-sub-row{display:flex;gap:8px}
.metric-sub{flex:1 1 0;min-width:0;background:var(--bg);border:1px solid var(--border);
  border-radius:6px;padding:8px 10px}
.metric-sub-label{font-size:10px;color:var(--text-muted);font-weight:600;margin-bottom:2px}
.metric-num{font-size:20px;font-weight:700;color:var(--primary);font-family:monospace;line-height:1.1}
.metric-cost{font-size:16px;font-weight:700;color:var(--accent);font-family:monospace;line-height:1.1}
.metric-chip{display:inline-block;font-size:10px;font-weight:600;margin-top:4px;
  padding:1px 6px;border-radius:8px;font-family:monospace}
.metric-chip.down{color:#059669;background:#ECFDF5}
.metric-chip.up{color:#DC2626;background:#FEF2F2}
@media(max-width:700px){{
  .metric-row{{flex-direction:column}}
}}
.kpi-card{background:var(--bg);border:1px solid var(--border);border-radius:8px;
  padding:10px 14px;flex:1 1 110px;min-width:0;max-width:200px}
.kpi-card.accent{background:var(--accent-bg);border-color:#FCD34D}
.kpi-label{font-size:10px;color:var(--text-secondary);font-weight:600;
  text-transform:uppercase;letter-spacing:.5px;margin-bottom:4px;white-space:nowrap}
.kpi-value{font-size:17px;font-weight:700;color:var(--primary);font-family:monospace;
  word-break:break-all;line-height:1.2}
.kpi-card.accent .kpi-value{color:var(--accent)}
.kpi-sub{font-size:11px;color:var(--text-muted);margin-top:2px}
.kpi-delta{font-size:11px;font-weight:600;margin-top:3px}
.table-label{font-size:12px;font-weight:600;color:var(--text-secondary);
  margin:16px 0 8px;text-transform:uppercase;letter-spacing:.4px}
.table-wrap{overflow-x:auto;margin-bottom:16px}
table{width:100%;border-collapse:collapse;font-size:13px}
thead th{padding:8px 10px;text-align:left;font-size:11px;font-weight:600;
  color:var(--text-secondary);text-transform:uppercase;letter-spacing:.4px;
  background:#F1F5F9;border-bottom:1px solid var(--border);white-space:nowrap}
tbody tr{border-bottom:1px solid #F1F5F9}
tbody tr:hover{background:#F8FAFC}
tbody td{padding:8px 10px;vertical-align:middle}
.num{font-family:monospace;font-size:12px}
.hi{color:var(--accent);font-weight:700}
.badge{display:inline-flex;align-items:center;padding:2px 8px;
  border-radius:12px;font-size:11px;font-weight:600}
.mat-name{max-width:280px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:12px}
.cell-main{font-family:monospace;font-size:13px;font-weight:600;color:var(--primary)}
.cell-sub{font-size:11px;color:var(--text-muted);margin-top:1px}
.cell-cost{font-family:monospace;font-size:12px;font-weight:600;color:var(--accent);margin-top:2px}
.sub-row td{background:#F8FAFC;border-left:3px solid var(--border);}
.two-col{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:8px}
.no-data{padding:24px;text-align:center;color:var(--text-muted);font-size:13px}
.btn-preview{
  display:inline-block;padding:3px 10px;border-radius:6px;
  border:1.5px solid var(--border);background:var(--bg);
  color:var(--primary-light);font-size:11px;font-weight:500;
  text-decoration:none;white-space:nowrap;transition:all .15s;
}
.btn-preview:hover{background:var(--primary);color:#fff;border-color:var(--primary)}
thead th.sortable{cursor:pointer;user-select:none}
thead th.sortable:hover{color:var(--primary)}
thead th.sort-asc::after{content:' ↑'}
thead th.sort-desc::after{content:' ↓'}
.filter-btn{
  border:1.5px solid var(--border);background:var(--bg);color:var(--text-secondary);
  border-radius:14px;padding:3px 12px;font-size:12px;font-weight:600;cursor:pointer;margin:0 4px 8px 0;
}
.filter-btn.active{background:var(--primary);border-color:var(--primary);color:#fff}
@media(max-width:700px){
  .kpi-grid{gap:8px}.kpi-card{min-width:100px}
  .two-col{grid-template-columns:1fr}
}
</style>
</head>
<body>
<div class="header">
  <div>
    <h1>每日素材数据</h1>
    <p>数据日期：<span id="hdr-date">{date_str}</span> · 三大项目汇总</p>
  </div>
  <div class="header-badge" id="hdr-badge">{date_str}</div>
</div>
<div class="page">
  <div class="date-picker" id="date-picker">
    <span class="dp-label">📅 日期（可多选）</span>
  </div>
  <div class="page-content">
  <div class="module">
    <div class="section-header"><h2>引导加微</h2></div>
    <div class="module-body" id="mod-guide"></div>
  </div>
  <div class="module">
    <div class="section-header"><h2>千川 · 199高中双科</h2></div>
    <div class="module-body" id="mod-qc"></div>
  </div>
  <div class="module">
    <div class="section-header"><h2>B站</h2></div>
    <div class="module-body" id="mod-bili"></div>
  </div>
  </div>
</div>
<script>
const MULTI = {DATA_JSON};
const COLORS = MULTI.colors || {}, BGS = MULTI.bgs || {};
const SELECTED = new Set([MULTI.default]);
const AGENTS_ALL = 'all';

function esc(s) {
  return String(s == null ? '' : s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}
function fMoney(v) { return '¥' + Number(v||0).toLocaleString('zh-CN', {minimumFractionDigits:2, maximumFractionDigits:2}); }
function fInt(v) { return Number(v||0).toLocaleString('zh-CN'); }
function fPct(v) { return Number(v||0).toFixed(2) + '%'; }
function dash(v) { return (v>0) ? String(v) : '—'; }
function deltaHtml(d) {
  if (!d) return '';
  return '<div class="kpi-delta" style="color:' + d[1] + '">' + esc(d[0]) + '</div>';
}
function kpiCard(label, value, sub, delta, accent) {
  return '<div class="kpi-card' + (accent ? ' accent' : '') + '">'
    + '<div class="kpi-label">' + esc(label) + '</div>'
    + '<div class="kpi-value">' + value + '</div>'
    + (sub ? '<div class="kpi-sub">' + esc(sub) + '</div>' : '')
    + deltaHtml(delta) + '</div>';
}
function metricCard(label, num, numDelta, cost, costDelta, accent) {
  const cls = function(d) { return d[1] === '#059669' ? 'down' : 'up'; };
  const numChip = numDelta ? '<div class="metric-chip ' + cls(numDelta) + '">' + esc(numDelta[0]) + '</div>' : '';
  const costChip = costDelta ? '<div class="metric-chip ' + cls(costDelta) + '">' + esc(costDelta[0]) + '</div>' : '';
  return '<div class="metric-card' + (accent ? ' metric-accent' : '') + '">'
    + '<div class="metric-label">' + esc(label) + '</div>'
    + '<div class="metric-sub-row">'
    + '<div class="metric-sub"><div class="metric-sub-label">数量</div><div class="metric-num">' + num + '</div>' + numChip + '</div>'
    + '<div class="metric-sub"><div class="metric-sub-label">成本</div><div class="metric-cost">' + cost + '</div>' + costChip + '</div>'
    + '</div>'
    + '</div>';
}

// ── 聚合工具 ──
function aggObj(items, keys) {
  const o = {};
  items.forEach(function(it) {
    keys.forEach(function(k) {
      o[k] = (o[k] || 0) + (Number(it[k]) || 0);
    });
  });
  return o;
}
function aggStat(items, keys) {
  // 加权/比率字段单独算；这里只返回简单求和
  return aggObj(items, keys);
}

// ── 引导加微渲染 ──
function renderGuide() {
  const el = document.getElementById('mod-guide');
  const items = [];
  SELECTED.forEach(function(m) {
    const d = MULTI.days[m];
    if (d && d.guide) items.push(d.guide.data);
  });
  if (!items.length) { el.innerHTML = '<div class="no-data">⚠️ 所选日期无引导加微数据</div>'; return; }
  const spend = items.reduce((s,x)=>s+x.stats.spend,0);
  const conv  = items.reduce((s,x)=>s+x.stats.conv,0);
  const gao   = items.reduce((s,x)=>s+x.stats.gao,0);
  const cpa   = conv ? spend/conv : 0;
  const deep  = conv ? gao/conv*100 : 0;
  // 素材名×人物 聚合（多日同名素材累加）
  const matMap = new Map();
  items.forEach(function(d) {
    (d.top||[]).forEach(function(r) {
      const k = r.name + '\u0001' + r.person;
      if (!matMap.has(k)) matMap.set(k, {name:r.name, person:r.person, spend:0, conv:0, gao:0, cpa:0});
      const o = matMap.get(k);
      o.spend += r.spend; o.conv += r.conv; o.gao += r.gaoquan;
    });
  });
  const mats = Array.from(matMap.values()).sort((a,b)=>b.spend-a.spend).slice(0,10);
  mats.forEach(function(o) { o.cpa = o.conv ? o.spend/o.conv : 0; });
  // 人物聚合
  const pMap = new Map();
  items.forEach(function(d) {
    Object.keys(d.by_person||{}).forEach(function(p) {
      const v = d.by_person[p];
      if (!pMap.has(p)) pMap.set(p, {spend:0,conv:0,gao:0,mat:0});
      const o = pMap.get(p);
      o.spend += v.spend; o.conv += v.conv; o.gao += v.gao; o.mat += v.mat_count;
    });
  });
  const persons = Array.from(pMap.entries()).filter(([p,o])=>o.spend>0).sort((a,b)=>b[1].spend-a[1].spend);
  const sel = Array.from(SELECTED);
  const single = sel.length === 1 ? MULTI.days[sel[0]] : null;
  const prevSingle = single && sel[0] !== MULTI.dates[0] ? MULTI.days[MULTI.dates[MULTI.dates.indexOf(sel[0])-1]] : null;
  const prevStats = prevSingle && prevSingle.guide ? prevSingle.guide.data.stats : null;
  const dSpend = deltaPair(spend, prevStats ? prevStats.spend : null, 'money');
  const dConv  = deltaPair(conv,  prevStats ? prevStats.conv  : null, 'int');
  const dCpa   = deltaPair(cpa,   prevStats ? prevStats.cpa   : null, 'money');
  const dGao   = deltaPair(gao,   prevStats ? prevStats.gao   : null, 'int');
  const dDeep  = deltaPair(deep,  prevStats ? prevStats.deep_rate : null, 'pct');

  let personRows = '';
  persons.forEach(function([p, o]) {
    const cpaV = o.conv ? o.spend/o.conv : 0;
    personRows += '<tr><td><span class="badge" style="background:' + (BGS[p]||'#f8fafc') + ';color:' + (COLORS[p]||'#64748b') + '">' + esc(p) + '</span></td>'
      + '<td class="num">' + fMoney(o.spend) + '</td>'
      + '<td class="num">' + fInt(o.conv) + '</td>'
      + '<td class="num">' + fInt(o.gao) + '</td>'
      + '<td class="num">' + (cpaV ? fMoney(cpaV) : '—') + '</td>'
      + '<td class="num">' + o.mat + '</td></tr>';
  });
  let matRows = '';
  mats.forEach(function(r) {
    matRows += '<tr><td><span class="badge" style="background:' + (BGS[r.person]||'#f8fafc') + ';color:' + (COLORS[r.person]||'#64748b') + '">' + esc(r.person) + '</span></td>'
      + '<td class="mat-name" title="' + esc(r.name) + '">' + esc(r.name) + '</td>'
      + '<td class="num">' + fMoney(r.spend) + '</td>'
      + '<td class="num">' + (r.conv ? fInt(r.conv) : '—') + '</td>'
      + '<td class="num">' + (r.cpa ? fMoney(r.cpa) : '—') + '</td>'
      + '<td class="num hi">' + (r.gao ? fInt(r.gao) : '—') + '</td></tr>';
  });
  const selCount = SELECTED.size;
  const matSub = selCount === 1 ? (items[0].stats.mat_count + ' 条素材') : '';
  el.innerHTML = '<div class="kpi-grid">'
    + kpiCard('总消耗', fMoney(spend), matSub, dSpend)
    + kpiCard('总转化', fInt(conv), '次', dConv)
    + kpiCard('平均 CPA', fMoney(cpa), null, dCpa)
    + kpiCard('高潜成交', fInt(gao), '深度转化', dGao, true)
    + kpiCard('深转率', fPct(deep), '高潜/转化', dDeep, true)
    + '</div>'
    + '<div class="table-wrap"><table><thead><tr><th>人物</th><th>消耗</th><th>转化</th><th>高潜</th><th>CPA</th><th>在投素材</th></tr></thead><tbody>' + personRows + '</tbody></table></div>'
    + '<div class="table-label">Top 素材（消耗排序）</div>'
    + '<div class="table-wrap"><table><thead><tr><th>人物</th><th>素材名称</th><th>消耗</th><th>转化</th><th>CPA</th><th>高潜 ★</th></tr></thead><tbody>' + matRows + '</tbody></table></div>';
}

function deltaPair(curr, prev, fmt, invertColor) {
  if (prev == null || Math.abs(curr - prev) < 0.005) return null;
  const diff = curr - prev;
  const sign = diff >= 0 ? '+' : '-';
  // invertColor=true 时：降=绿、涨=红（成本类指标）
  const upGood = !invertColor;
  const upIsRed = upGood ? diff < 0 : diff > 0;
  const color = upIsRed ? '#DC2626' : '#059669';
  let s;
  if (fmt === 'money') s = sign + '¥' + Math.abs(diff).toLocaleString('zh-CN', {minimumFractionDigits:2, maximumFractionDigits:2});
  else if (fmt === 'int') s = sign + Math.abs(diff).toFixed(0);
  else s = sign + Math.abs(diff).toFixed(2) + '%';
  return [s, color];
}

// ── 千川渲染 ──
function renderQC(agentFilter) {
  const el = document.getElementById('mod-qc');
  const items = [];
  SELECTED.forEach(function(m) {
    const d = MULTI.days[m];
    if (d && d.qc) items.push(d.qc.data);
  });
  if (!items.length) { el.innerHTML = '<div class="no-data">⚠️ 所选日期无千川数据</div>'; return; }
  // 素材×代理商按素材名合并（跨日累加）
  const mMap = new Map();
  items.forEach(function(d) {
    (d.detail||[]).forEach(function(r) {
      if (!mMap.has(r.name)) mMap.set(r.name, {name:r.name, spend:0, orders:0, imp:0, click:0, conv:0, agents:new Set(), preview:''});
      const o = mMap.get(r.name);
      o.spend += r.spend; o.orders += r.orders; o.preview = o.preview || r.preview;
      o.agents.add(r.agent || '—');
    });
  });
  const mats = Array.from(mMap.values()).filter(o=>o.orders>0).sort((a,b)=>b.spend-a.spend);
  // 代理商聚合
  const aMap = new Map();
  items.forEach(function(d) {
    Object.keys(d.by_agent||{}).forEach(function(a) {
      const v = d.by_agent[a];
      if (!aMap.has(a)) aMap.set(a, {spend:0,gmv:0,orders:0,imp:0,click:0,conv:0});
      const o = aMap.get(a);
      o.spend+=v.spend; o.gmv+=v.gmv; o.orders+=v.orders; o.imp+=v.imp; o.click+=v.click; o.conv+=v.conv;
    });
  });
  const agents = Array.from(aMap.entries()).filter(([a,o])=>(o.spend>0 || o.orders>0)).sort((a,b)=>b[1].spend-a[1].spend);
  // 渠道聚合
  const cMap = new Map();
  items.forEach(function(d) {
    Object.keys(d.by_channel||{}).forEach(function(c) {
      const v = d.by_channel[c];
      if (!cMap.has(c)) cMap.set(c, {spend:0,gmv:0,orders:0,imp:0,click:0,conv:0});
      const o = cMap.get(c);
      o.spend+=v.spend; o.gmv+=v.gmv; o.orders+=v.orders; o.imp+=v.imp; o.click+=v.click; o.conv+=v.conv;
    });
  });
  const channels = Array.from(cMap.entries()).filter(([c,o])=>o.spend>0).sort((a,b)=>b[1].spend-a[1].spend);
  // 汇总 KPI
  let spend=0, gmv=0, orders=0, imp=0, click=0, conv=0;
  items.forEach(function(d) {
    spend+=d.stats.spend; gmv+=d.stats.gmv; orders+=d.stats.orders;
    imp+=d.stats.imp||0; click+=imp&&d.stats.ctr? imp*d.stats.ctr/100 : 0;
  });
  // imp/click 从代理商聚合里取更准（都是派生值，用 by_agent 累加）
  let aImp=0, aClick=0, aConv=0;
  aMap.forEach(function(o) { aImp+=o.imp; aClick+=o.click; aConv+=o.conv; });
  imp = aImp; click = aClick; conv = aConv;
  const roi = spend ? gmv/spend : 0;
  const cpa = orders ? spend/orders : 0;
  const ctr = imp ? click/imp*100 : 0;
  const cvr = click ? conv/click*100 : 0;
  const cpm = imp ? spend/imp*1000 : 0;
  const sel = Array.from(SELECTED);
  const single = sel.length === 1 ? MULTI.days[sel[0]] : null;
  const prevSingle = single && sel[0] !== MULTI.dates[0] ? MULTI.days[MULTI.dates[MULTI.dates.indexOf(sel[0])-1]] : null;
  const pv = prevSingle && prevSingle.qc ? prevSingle.qc.data.stats : null;
  const dSpend = deltaPair(spend, pv?pv.spend:null, 'money');
  const dGmv   = deltaPair(gmv, pv?pv.gmv:null, 'money');
  const dOrders = deltaPair(orders, pv?pv.orders:null, 'int');
  const dRoi   = deltaPair(roi, pv?pv.roi:null, 'pct');
  const dCpa   = deltaPair(cpa, pv?pv.cpa:null, 'money');
  const dCtr   = deltaPair(ctr, pv?pv.ctr:null, 'pct');
  const dCvr   = deltaPair(cvr, pv?pv.cvr:null, 'pct');
  const dCpm   = deltaPair(cpm, pv?pv.cpm:null, 'money');

  let chanRows = '';
  channels.forEach(function([c, o]) {
    const cpaV = o.orders ? o.spend/o.orders : 0;
    const roiV = o.spend ? o.gmv/o.spend : 0;
    const ctrV = o.imp ? o.click/o.imp*100 : 0;
    const cvrV = o.click ? o.conv/o.click*100 : 0;
    chanRows += '<tr><td>' + esc(c||'—') + '</td><td class="num">' + fMoney(o.spend) + '</td>'
      + '<td class="num">' + fInt(o.orders) + '</td>'
      + '<td class="num">' + (cpaV?fMoney(cpaV):'—') + '</td>'
      + '<td class="num">' + roiV.toFixed(2) + '</td>'
      + '<td class="num">' + ctrV.toFixed(2) + '%</td>'
      + '<td class="num">' + cvrV.toFixed(2) + '%</td></tr>';
  });
  let agentRows = '';
  agents.forEach(function([a, o]) {
    const cpaV = o.orders ? o.spend/o.orders : 0;
    const ctrV = o.imp ? o.click/o.imp*100 : 0;
    const cvrV = o.click ? o.conv/o.click*100 : 0;
    agentRows += '<tr><td>' + esc(a) + '</td><td class="num">' + fMoney(o.spend) + '</td>'
      + '<td class="num">' + fInt(o.orders) + '</td>'
      + '<td class="num">' + (cpaV?fMoney(cpaV):'—') + '</td>'
      + '<td class="num">' + ctrV.toFixed(2) + '%</td>'
      + '<td class="num">' + cvrV.toFixed(2) + '%</td></tr>';
  });
  const filtered = (agentFilter && agentFilter !== AGENTS_ALL)
    ? mats.filter(function(o) { return Array.from(o.agents).indexOf(agentFilter) >= 0; })
    : mats;
  let matRows = '';
  filtered.forEach(function(o) {
    const cpaV = o.orders ? o.spend/o.orders : 0;
    const prev = o.preview ? '<a href="' + esc(o.preview) + '" target="_blank" class="btn-preview">▶ 预览</a>' : '—';
    matRows += '<tr class="mat-parent"><td class="mat-name" title="' + esc(o.name) + '">' + esc(o.name) + '</td>'
      + '<td class="num" style="font-size:11px;color:var(--text-muted)">' + esc(Array.from(o.agents).join('、')) + '</td>'
      + '<td class="num">' + fMoney(o.spend) + '</td>'
      + '<td class="num">' + fInt(o.orders) + '</td>'
      + '<td class="num">' + (cpaV?fMoney(cpaV):'—') + '</td>'
      + '<td>' + prev + '</td></tr>';
  });
  // 代理商筛选按钮
  const agentList = Array.from(aMap.keys()).sort();
  let btnHtml = '<div id="qc-agent-btns" style="margin:12px 0 4px"><button class="filter-btn' + ((!agentFilter||agentFilter===AGENTS_ALL)?' active':'') + '" onclick="setQcAgent(\\'all\\')">全部</button>';
  agentList.forEach(function(a) {
    btnHtml += '<button class="filter-btn' + (agentFilter===a?' active':'') + '" onclick="setQcAgent(\\'' + esc(a) + '\\')">' + esc(a) + '</button>';
  });
  btnHtml += '</div>';
  const qcMatSub = SELECTED.size === 1 ? (items[0].stats.mat_count + ' 条素材') : '';
  el.innerHTML = '<div class="kpi-grid">'
    + kpiCard('总消耗', fMoney(spend), qcMatSub, dSpend)
    + kpiCard('总 GMV', fMoney(gmv), null, dGmv)
    + kpiCard('总订单', fInt(orders), null, dOrders)
    + kpiCard('整体 ROI', roi.toFixed(2), null, dRoi, true)
    + kpiCard('平均 CPA', fMoney(cpa), null, dCpa)
    + kpiCard('CTR', fPct(ctr), null, dCtr)
    + kpiCard('CVR', fPct(cvr), null, dCvr)
    + kpiCard('CPM', fMoney(cpm), null, dCpm)
    + '</div>'
    + '<div class="two-col"><div><div class="table-label">按渠道</div>'
    + '<div class="table-wrap agent-summary-wrap"><table><thead><tr><th>渠道</th><th>消耗</th><th>订单</th><th>CPA</th><th>ROI</th><th>CTR</th><th>CVR</th></tr></thead><tbody>' + chanRows + '</tbody></table></div></div>'
    + '<div><div class="table-label">按来源（自有 / 代理商）</div>'
    + '<div class="table-wrap agent-summary-wrap"><table><thead><tr><th>代理商</th><th>消耗</th><th>订单</th><th>CPA</th><th>CTR</th><th>CVR</th></tr></thead><tbody>' + agentRows + '</tbody></table></div></div></div>'
    + '<div class="table-label">素材明细（有成交 / 可排序）</div>' + btnHtml
    + '<div class="table-wrap"><table id="qc-mat-table"><thead><tr><th>素材名称</th><th>代理商</th><th>消耗</th><th>成交量</th><th>CPA</th><th>预览</th></tr></thead><tbody>' + matRows + '</tbody></table></div>';
  initSortableTable('qc-mat-table');
}
let QC_AGENT_FILTER = AGENTS_ALL;
function setQcAgent(a) { QC_AGENT_FILTER = a; renderQC(a); }

// ── B站渲染 ──
function renderBili() {
  const el = document.getElementById('mod-bili');
  const items = [];
  SELECTED.forEach(function(m) {
    const d = MULTI.days[m];
    if (d && d.bili) items.push(d.bili.data);
  });
  if (!items.length) { el.innerHTML = '<div class="no-data">⚠️ 所选日期无B站数据</div>'; return; }
  const mMap = new Map();
  items.forEach(function(d) {
    (d.top||[]).forEach(function(r) {
      if (!mMap.has(r.title)) mMap.set(r.title, {title:r.title, video_url:r.video_url, spend:0, imp:0, clicks:0, form_cnt:0, lead_cnt:0, wx_cnt:0});
      const o = mMap.get(r.title);
      o.spend+=r.spend; o.imp+=r.imp; o.clicks+=r.clicks; o.form_cnt+=r.form_cnt; o.lead_cnt+=r.lead_cnt; o.wx_cnt+=r.wx_cnt;
      o.video_url = o.video_url || r.video_url;
    });
  });
  const mats = Array.from(mMap.values()).filter(o=>o.lead_cnt>0||o.wx_cnt>0||o.form_cnt>0).sort((a,b)=>b.spend-a.spend).slice(0,30);
  const aMap = new Map();
  items.forEach(function(d) {
    Object.keys(d.by_agent||{}).forEach(function(a) {
      const v = d.by_agent[a];
      if (!aMap.has(a)) aMap.set(a, {spend:0,imp:0,clicks:0,form_cnt:0,lead_cnt:0,wx_cnt:0});
      const o = aMap.get(a);
      o.spend+=v.spend; o.imp+=v.imp; o.clicks+=v.clicks; o.form_cnt+=v.form_cnt; o.lead_cnt+=v.lead_cnt; o.wx_cnt+=v.wx_cnt;
    });
  });
  const agents = Array.from(aMap.entries()).filter(([a,o])=>o.spend>0).sort((a,b)=>b[1].spend-a[1].spend);
  let spend=0, imp=0, clicks=0, form=0, lead=0, wx=0;
  aMap.forEach(function(o) { spend+=o.spend; imp+=o.imp; clicks+=o.clicks; form+=o.form_cnt; lead+=o.lead_cnt; wx+=o.wx_cnt; });
  const ctr = imp ? clicks/imp*100 : 0;
  const cpm = imp ? spend/imp*1000 : 0;
  const formCost = form ? spend/form : 0;
  const leadCost = lead ? spend/lead : 0;
  const wxCost = wx ? spend/wx : 0;
  const sel = Array.from(SELECTED);
  const single = sel.length === 1 ? MULTI.days[sel[0]] : null;
  const prevSingle = single && sel[0] !== MULTI.dates[0] ? MULTI.days[MULTI.dates[MULTI.dates.indexOf(sel[0])-1]] : null;
  const pv = prevSingle && prevSingle.bili ? prevSingle.bili.data.stats : null;
  const dSpend = deltaPair(spend, pv?pv.spend:null, 'money');
  const dCtr   = deltaPair(ctr, pv?pv.ctr:null, 'pct');
  const dCpm   = deltaPair(cpm, pv?pv.cpm:null, 'money');
  // 成本类指标：降=绿（好事），涨=红
  const dForm = deltaPair(form, pv?pv.form_cnt:null, 'int');
  const dLead = deltaPair(lead, pv?pv.lead_cnt:null, 'int');
  const dWx   = deltaPair(wx, pv?pv.wx_cnt:null, 'int');
  const dFormCpa = deltaPair(formCost, pv?pv.form_cost:null, 'money', true);
  const dLeadCpa = deltaPair(leadCost, pv?pv.lead_cost:null, 'money', true);
  const dWxCpa   = deltaPair(wxCost, pv?pv.wx_cost:null, 'money', true);

  let agentRows = '';
  agents.forEach(function([a, o]) {
    const ctrV = o.imp ? o.clicks/o.imp*100 : 0;
    const cpmV = o.imp ? o.spend/o.imp*1000 : 0;
    agentRows += '<tr><td><strong>' + esc(a) + '</strong></td><td class="num">' + fMoney(o.spend) + '</td>'
      + '<td class="num">' + ctrV.toFixed(2) + '%</td><td class="num">' + fMoney(cpmV) + '</td>'
      + '<td class="num">' + fInt(o.form_cnt) + ' / ' + (o.form_cnt?fMoney(o.spend/o.form_cnt):'—') + '</td>'
      + '<td class="num">' + fInt(o.lead_cnt) + ' / ' + (o.lead_cnt?fMoney(o.spend/o.lead_cnt):'—') + '</td>'
      + '<td class="num">' + fInt(o.wx_cnt) + ' / ' + (o.wx_cnt?fMoney(o.spend/o.wx_cnt):'—') + '</td></tr>';
  });
  let matRows = '';
  mats.forEach(function(r) {
    const prev = r.video_url ? '<a href="' + esc(r.video_url) + '" target="_blank" class="btn-preview">▶ 预览</a>' : '—';
    const ctrV = r.imp ? r.clicks/r.imp*100 : 0;
    const cpmV = r.imp ? r.spend/r.imp*1000 : 0;
    matRows += '<tr><td class="mat-name" title="' + esc(r.title) + '">' + esc(r.title) + '</td>'
      + '<td class="num">' + fMoney(r.spend) + '</td>'
      + '<td class="num">' + ctrV.toFixed(2) + '%</td>'
      + '<td class="num">' + fMoney(cpmV) + '</td>'
      + '<td class="num"><div class="cell-main">' + fInt(r.form_cnt) + '</div><div class="cell-cost">' + (r.form_cnt?fMoney(r.spend/r.form_cnt):'—') + '</div></td>'
      + '<td class="num"><div class="cell-main">' + fInt(r.lead_cnt) + '</div><div class="cell-cost">' + (r.lead_cnt?fMoney(r.spend/r.lead_cnt):'—') + '</div></td>'
      + '<td class="num"><div class="cell-main">' + fInt(r.wx_cnt) + '</div><div class="cell-cost">' + (r.wx_cnt?fMoney(r.spend/r.wx_cnt):'—') + '</div></td>'
      + '<td>' + prev + '</td></tr>';
  });
  const biliMatSub = SELECTED.size === 1 ? (items[0].stats.mat_count + ' 条素材') : '';
  el.innerHTML = '<div class="kpi-grid kpi-full">'
    + kpiCard('总花费', fMoney(spend), biliMatSub, dSpend)
    + kpiCard('CTR', fPct(ctr), null, dCtr)
    + kpiCard('CPM', fMoney(cpm), null, dCpm)
    + '</div>'
    + '<div class="metric-row">'
    + metricCard('表单提交量', fInt(form), dForm, form?fMoney(formCost):'—', dFormCpa, true)
    + metricCard('有效线索量', fInt(lead), dLead, lead?fMoney(leadCost):'—', dLeadCpa)
    + metricCard('微信加粉量', fInt(wx), dWx, wx?fMoney(wxCost):'—', dWxCpa)
    + '</div>'
    + '<div class="table-label">按代理商</div>'
    + '<div class="table-wrap agent-summary-wrap"><table><thead><tr><th>代理商</th><th>花费</th><th>CTR</th><th>CPM</th><th>表单（量/成本）</th><th>有效线索（量/成本）</th><th>加粉（量/成本）</th></tr></thead><tbody>' + agentRows + '</tbody></table></div>'
    + '<div class="table-label">Top 素材（有线索 / 可排序）</div>'
    + '<div class="table-wrap"><table id="bili-mat-table"><thead><tr><th>标题</th><th>花费</th><th>CTR</th><th>CPM</th><th>表单（量/成本）</th><th>有效线索（量/成本）</th><th>加粉（量/成本）</th><th>预览</th></tr></thead><tbody>' + matRows + '</tbody></table></div>';
  initSortableTable('bili-mat-table');
}

// ── 日期选择 ──
function renderChips() {
  const el = document.getElementById('date-picker');
  const latest = MULTI.dates[MULTI.dates.length-1];
  let html = '<span class="dp-label">📅 日期（可多选）</span>'
    + '<div class="date-quick" id="date-quick">'
    + '<button data-mode="latest">最新</button>'
    + '<button data-mode="last7">最近7天</button>'
    + '<button data-mode="all">全部</button>'
    + '<button data-mode="none">清空</button>'
    + '</div>';
  MULTI.dates.forEach(function(m) {
    const y = '2026-' + m.slice(0,2) + '-' + m.slice(2,4);
    html += '<span class="date-chip' + (SELECTED.has(m)?' on':'') + '" data-date="' + m + '">' + y + '</span>';
  });
  el.innerHTML = html;
  el.querySelectorAll('.date-chip').forEach(function(chip) {
    chip.addEventListener('click', function() {
      const m = chip.dataset.date;
      if (SELECTED.has(m)) {
        if (SELECTED.size > 1) SELECTED.delete(m);
      } else {
        SELECTED.add(m);
      }
      renderChips();
      renderAll();
    });
  });
  el.querySelectorAll('#date-quick button').forEach(function(btn) {
    btn.addEventListener('click', function() {
      quickSelect(btn.dataset.mode);
    });
  });
}
function quickSelect(mode) {
  SELECTED.clear();
  if (mode === 'latest') {
    SELECTED.add(MULTI.dates[MULTI.dates.length-1]);
  } else if (mode === 'last7') {
    MULTI.dates.slice(-7).forEach(function(m) { SELECTED.add(m); });
  } else if (mode === 'all') {
    MULTI.dates.forEach(function(m) { SELECTED.add(m); });
  }
  renderChips();
  renderAll();
}
function renderAll() {
  const sel = Array.from(SELECTED).sort();
  const last = sel[sel.length-1];
  const label = sel.length === 0 ? '未选择'
    : sel.length === 1
    ? '2026年' + last.slice(0,2) + '月' + last.slice(2,4) + '日'
    : sel.length + ' 天';
  document.getElementById('hdr-date').textContent = label;
  document.getElementById('hdr-badge').textContent = label;
  renderGuide();
  renderQC(QC_AGENT_FILTER);
  renderBili();
}

// ── 可排序表格 ──
function initSortableTable(tableId) {
  const table = document.getElementById(tableId);
  if (!table) return;
  table.querySelectorAll('th.sortable').forEach(function(th) {
    th.onclick = function() {
      const col = parseInt(this.dataset.col);
      const asc = this.classList.contains('sort-desc');
      table.querySelectorAll('th.sortable').forEach(function(h) { h.classList.remove('sort-asc','sort-desc'); });
      this.classList.add(asc ? 'sort-asc' : 'sort-desc');
      const tbody = table.querySelector('tbody');
      const rows = Array.from(tbody.querySelectorAll('tr'));
      rows.sort(function(a, b) {
        const va = a.cells[col] ? a.cells[col].textContent.replace(/[¥,%]/g,'').trim() : '';
        const vb = b.cells[col] ? b.cells[col].textContent.replace(/[¥,%]/g,'').trim() : '';
        const na = parseFloat(va), nb = parseFloat(vb);
        const cmp = isNaN(na) || isNaN(nb) ? va.localeCompare(vb,'zh') : na - nb;
        return asc ? cmp : -cmp;
      });
      rows.forEach(function(r) { tbody.appendChild(r); });
    };
  });
}

renderChips();
renderAll();
</script>
</html>'''




# ──────────────────────────────────────────
# 企微推送
# ──────────────────────────────────────────
def build_wecom_text(mmdd, guide_rows, guide_err, qc_rows, qc_err, bili_rows, bili_err, bili_raw=None):
    date_str = f"{mmdd[:2]}月{mmdd[2:]}日"
    lines = [f"📊 {date_str} 素材日报\n"]

    # 引导加微
    if guide_err:
        lines.append(f"【引导加微】⚠️ 昨日后台数据有误，明天开始正常推送\n")
    elif guide_rows:
        gs = guide_stats(guide_rows)
        lines.append("【引导加微】")
        lines.append(f"💰 消耗 ¥{gs['total_spend']:,.0f}  🎯 转化 {int(gs['total_conv'])}  📉 CPA ¥{gs['avg_cpa']:.0f}")
        lines.append(f"⭐ 高潜成交 {int(gs['total_gaoquan'])}  深转率 {gs['deep_rate']:.1f}%")
        top3_agg = defaultdict(lambda: {'person': '', 'gao': 0})
        for r in guide_rows:
            if r['gaoquan'] > 0:
                k = r['name']
                top3_agg[k]['gao'] += r['gaoquan']
                top3_agg[k]['person'] = r['person']
        top3 = sorted(top3_agg.values(), key=lambda x: -x['gao'])[:3]
        top3_names = [k for k, _ in sorted(top3_agg.items(), key=lambda x: -x[1]['gao'])[:3]]
        if top3:
            lines.append("🏆 高潜 Top3：")
            for k, v in zip(top3_names, top3):
                lines.append(f"  · {v['person']} {k[:18]}  高潜{int(v['gao'])}")
        lines.append("")

    # 千川
    if qc_err:
        lines.append(f"【千川·双科】⚠️ {qc_err}\n")
    elif qc_rows:
        qs = qianchuan_stats(qc_rows)
        lines.append("【千川·199高中双科】")
        lines.append(f"💰 消耗 ¥{qs['total_spend']:,.0f}  📦 GMV ¥{qs['total_gmv']:,.0f}  🎯 ROI {qs['avg_roi']:.2f}")
        lines.append(f"📋 订单 {int(qs['total_orders'])}  💡 CPA ¥{qs['avg_cpa']:.0f}")
        lines.append(f"📈 CTR {qs['avg_ctr']:.2f}%  🔄 CVR {qs['avg_cvr']:.2f}%  📡 CPM ¥{qs['avg_cpm']:.2f}")
        # 代理商明细
        by_agent = defaultdict(lambda: {'spend': 0, 'orders': 0})
        for r in qc_rows:
            key = r['agent'] or '未知'
            by_agent[key]['spend']  += r['spend']
            by_agent[key]['orders'] += r['orders']
        lines.append("代理商：")
        for agent, d in sorted(by_agent.items(), key=lambda x: -x[1]['spend']):
            _cpa = f"CPA ¥{d['spend']/d['orders']:.0f}" if d['orders'] else "无成单"
            lines.append(f"  · {agent}  消耗 ¥{d['spend']:,.0f}  成单 {int(d['orders'])}  {_cpa}")
        lines.append("")

    # B站
    if bili_err:
        lines.append(f"【B站】⚠️ {bili_err}\n")
    elif bili_rows:
        bs = bilibili_stats(bili_rows, bili_raw)
        lines.append("【B站】")
        lines.append(f"💰 花费 ¥{bs['total_spend']:,.0f}  📈 CTR {bs['avg_ctr']:.2f}%  📡 CPM ¥{bs['avg_cpm']:.2f}")
        lines.append(f"📋 表单 {int(bs['form_cnt'])}（¥{bs['form_cost']:.0f}）  👤 线索 {int(bs['lead_cnt'])}（¥{bs['lead_cost']:.0f}）  ➕ 加粉 {int(bs['wx_cnt'])}（¥{bs['wx_cost']:.0f}）")
        lines.append("")

    lines.append(f"🔗 完整报告：{DAILY_REPORT_URL}")
    return "\n".join(lines)

def build_card_html(mmdd, guide_rows, guide_err, qc_rows, qc_err, bili_rows, bili_err, bili_raw=None):
    date_str = f"{mmdd[:2]}月{mmdd[2:]}日"
    sections = []

    def kpi_row(items):
        cells = ''.join(f'<div class="kpi"><div class="kv">{v}</div><div class="kl">{l}</div></div>' for l, v in items)
        return f'<div class="kpi-row">{cells}</div>'

    def agent_table(rows):
        trs = ''
        by_agent = defaultdict(lambda: {'spend': 0, 'orders': 0})
        for r in rows:
            key = r['agent'] or '未知'
            by_agent[key]['spend']  += r['spend']
            by_agent[key]['orders'] += r['orders']
        for agent, d in sorted(by_agent.items(), key=lambda x: -x[1]['spend']):
            cpa = f"¥{d['spend']/d['orders']:.0f}" if d['orders'] else "—"
            trs += f'<tr><td>{agent}</td><td>¥{d["spend"]:,.0f}</td><td>{int(d["orders"])}</td><td>{cpa}</td></tr>'
        return f'''<table><thead><tr><th>代理商</th><th>消耗</th><th>成单</th><th>CPA</th></tr></thead><tbody>{trs}</tbody></table>'''

    # 引导加微
    if guide_err:
        sections.append(f'<div class="section"><div class="sec-title">引导加微</div><div class="warn">⚠️ 昨日后台数据有误，明天开始正常推送</div></div>')
    elif guide_rows:
        gs = guide_stats(guide_rows)
        sections.append(f'''<div class="section">
          <div class="sec-title">引导加微</div>
          {kpi_row([("消耗", f"¥{gs['total_spend']:,.0f}"), ("转化", int(gs['total_conv'])), ("CPA", f"¥{gs['avg_cpa']:.0f}"), ("高潜成交", f'<span class="hi">{int(gs["total_gaoquan"])}</span>'), ("深转率", f"{gs['deep_rate']:.1f}%")])}
        </div>''')

    # 千川
    if qc_err:
        sections.append(f'<div class="section"><div class="sec-title">千川·199高中双科</div><div class="warn">⚠️ 数据缺失</div></div>')
    elif qc_rows:
        qs = qianchuan_stats(qc_rows)
        sections.append(f'''<div class="section">
          <div class="sec-title">千川 · 199高中双科</div>
          {kpi_row([("消耗", f"¥{qs['total_spend']:,.0f}"), ("GMV", f"¥{qs['total_gmv']:,.0f}"), ("ROI", f'<span class="hi">{qs["avg_roi"]:.2f}</span>'), ("订单", int(qs['total_orders'])), ("CPA", f"¥{qs['avg_cpa']:.0f}")])}
          {kpi_row([("CTR", f"{qs['avg_ctr']:.2f}%"), ("CVR", f"{qs['avg_cvr']:.2f}%"), ("CPM", f"¥{qs['avg_cpm']:.2f}")])}
          <div class="sub-label">代理商明细</div>
          {agent_table(qc_rows)}
        </div>''')

    # B站
    if bili_err:
        sections.append(f'<div class="section"><div class="sec-title">B站</div><div class="warn">⚠️ 数据缺失</div></div>')
    elif bili_rows:
        bs = bilibili_stats(bili_rows, bili_raw)
        sections.append(f'''<div class="section">
          <div class="sec-title">B站</div>
          {kpi_row([("花费", f"¥{bs['total_spend']:,.0f}"), ("CTR", f"{bs['avg_ctr']:.2f}%"), ("CPM", f"¥{bs['avg_cpm']:.2f}")])}
          {kpi_row([("表单", f'<span class="hi">{int(bs["form_cnt"])}</span>'), ("表单成本", f"¥{bs['form_cost']:.0f}"), ("有效线索", f'<span class="hi">{int(bs["lead_cnt"])}</span>'), ("线索成本", f"¥{bs['lead_cost']:.0f}"), ("加粉", f'<span class="hi">{int(bs["wx_cnt"])}</span>'), ("加粉成本", f"¥{bs['wx_cost']:.0f}")])}
        </div>''')

    body = ''.join(sections)
    return f'''<!DOCTYPE html>
<html><head><meta charset="UTF-8">
<style>
* { box-sizing: border-box; margin: 0; padding: 0; }
body { background: #1E293B; font-family: system-ui, -apple-system, sans-serif;
  padding: 20px; width: 580px; }
.card { background: #0F172A; border-radius: 14px; overflow: hidden; }
.card-header { background: linear-gradient(135deg,#1E40AF,#2563EB);
  padding: 16px 20px; display: flex; justify-content: space-between; align-items: center; }
.card-header h1 { color: #fff; font-size: 16px; font-weight: 700; }
.card-header .date { color: rgba(255,255,255,.75); font-size: 13px; }
.section { padding: 14px 20px; border-bottom: 1px solid #1E293B; }
.section:last-child { border-bottom: none; }
.sec-title { font-size: 12px; font-weight: 700; color: #60A5FA;
  text-transform: uppercase; letter-spacing: .5px; margin-bottom: 10px; }
.kpi-row { display: flex; gap: 8px; margin-bottom: 8px; flex-wrap: wrap; }
.kpi { background: #1E293B; border-radius: 8px; padding: 8px 12px; flex: 1; min-width: 70px; }
.kv { font-size: 16px; font-weight: 700; color: #E2E8F0; font-family: monospace; }
.kl { font-size: 10px; color: #64748B; margin-top: 2px; }
.hi { color: #F59E0B; }
.sub-label { font-size: 11px; color: #475569; margin: 8px 0 6px; }
table { width: 100%; border-collapse: collapse; font-size: 12px; }
thead th { padding: 5px 8px; text-align: left; color: #475569; font-weight: 600;
  border-bottom: 1px solid #1E293B; font-size: 11px; }
tbody td { padding: 5px 8px; color: #CBD5E1; border-bottom: 1px solid #0F172A; }
tbody tr:last-child td { border-bottom: none; }
.footer { padding: 10px 20px; text-align: right; }
.footer a { color: #3B82F6; font-size: 11px; text-decoration: none; }
.warn { color: #F87171; font-size: 12px; }
</style></head>
<body><div class="card">
  <div class="card-header">
    <h1>📊 素材日报</h1>
    <div class="date">{date_str}</div>
  </div>
  {body}
  <div class="footer"><a href="{DAILY_REPORT_URL}">{DAILY_REPORT_URL}</a></div>
</div></body></html>'''


def render_page_snapshot(html_path, out_path):
    import subprocess
    script = f"""
from playwright.sync_api import sync_playwright
from pathlib import Path
html_path = Path(r'{html_path}')
out_path = Path(r'{out_path}')
with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page(viewport={{'width': 1300, 'height': 900}})
    page.goto(f'file://{{html_path}}')
    page.wait_for_timeout(500)
    page.evaluate('''
        document.getElementById("date-picker").style.display = "none";
        document.querySelectorAll(".table-wrap").forEach(function(el) {{
            if (!el.classList.contains("agent-summary-wrap")) el.style.display = "none";
        }});
        document.querySelectorAll(".table-label").forEach(function(el) {{
            var next = el.nextElementSibling;
            if (next && !next.classList.contains("agent-summary-wrap") && !next.classList.contains("two-col")) el.style.display = "none";
        }});
    ''')
    page.wait_for_timeout(300)
    page.screenshot(path=str(out_path), full_page=True)
    browser.close()
"""
    result = subprocess.run(['/usr/bin/python3', '-c', script], capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"截图失败: {result.stderr}")


def push_via_gh_api(local_index, mmdd):
    """GitHub git push 网络故障时的兜底：用 gh api Contents API 直接更新线上 index.html"""
    import base64, json as _json, subprocess as _sp
    try:
        with open(local_index, 'rb') as f:
            b64 = base64.b64encode(f.read()).decode()
        # 查当前线上 sha
        r = _sp.run(['gh', 'api', 'repos/soso0122/daily-report/contents/index.html',
                     '--jq', '.sha'], capture_output=True, text=True)
        if r.returncode != 0:
            print(f"  [API] 查询 sha 失败: {r.stderr.strip()[:100]}")
            return False
        sha = r.stdout.strip()
        payload = _json.dumps({
            'message': f'更新素材日报 {mmdd}',
            'content': b64,
            'sha': sha,
            'branch': 'main',
        })
        import tempfile, os
        fd, path = tempfile.mkstemp(suffix='.json')
        with os.fdopen(fd, 'w') as f:
            f.write(payload)
        r2 = _sp.run(['gh', 'api', '-X', 'PUT',
                      'repos/soso0122/daily-report/contents/index.html',
                      '--input', path], capture_output=True, text=True)
        os.unlink(path)
        if r2.returncode == 0:
            print("  [API] index.html 已更新到 main")
            return True
        print(f"  [API] 更新失败: {r2.stderr.strip()[:150]}")
        return False
    except Exception as e:
        print(f"  [API] 异常: {e}")
        return False


def push_wecom(text, date_str):
    import subprocess, json
    payload = json.dumps({"msgtype": "text", "text": {"content": text}})
    result = subprocess.run(
        ['curl', '-s', '-X', 'POST', WECOM_WEBHOOK,
         '-H', 'Content-Type: application/json',
         '-d', payload],
        capture_output=True, text=True
    )
    resp = json.loads(result.stdout)
    if resp.get("errcode") == 0:
        print("企微文字推送成功")
    else:
        print(f"企微推送失败: {resp}")


def push_wecom_image(img_path):
    import base64, hashlib, subprocess, json
    with open(img_path, 'rb') as f:
        data = f.read()
    b64 = base64.b64encode(data).decode()
    md5 = hashlib.md5(data).hexdigest()
    payload = json.dumps({"msgtype": "image", "image": {"base64": b64, "md5": md5}})
    result = subprocess.run(
        ['curl', '-s', '-X', 'POST', WECOM_WEBHOOK,
         '-H', 'Content-Type: application/json',
         '-d', payload],
        capture_output=True, text=True
    )
    resp = json.loads(result.stdout)
    if resp.get("errcode") == 0:
        print("企微图片推送成功")
    else:
        print(f"企微图片推送失败: {resp}")


# ──────────────────────────────────────────
# 主入口
# ──────────────────────────────────────────
def main():
    args = sys.argv[1:]
    if not args or args[0] in ('-h', '--help'):
        print("用法: python3 scripts/daily_report.py MMDD [--push]")
        sys.exit(0)

    mmdd = args[0].strip()
    do_push = '--push' in args

    print(f"=== 生成 {mmdd[:2]}月{mmdd[2:]}日 日报 ===")

    guide_rows, guide_err = load_guide(mmdd)
    qc_rows,    qc_err    = load_qianchuan(mmdd)
    bili_rows, bili_err, bili_raw = load_bilibili(mmdd)

    if guide_rows: print(f"引导加微: {len(guide_rows)} 条")
    else:          print(f"引导加微: {guide_err}")
    if qc_rows:    print(f"千川:     {len(qc_rows)} 条（有消耗）")
    else:          print(f"千川:     {qc_err}")
    if bili_rows:  print(f"B站:      {len(bili_rows)} 条（有花费）")
    else:          print(f"B站:      {bili_err}")

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = REPORTS_DIR / f'日报_{mmdd}.html'
    html = build_html(mmdd, guide_rows, guide_err, qc_rows, qc_err, bili_rows, bili_err, bili_raw)
    out_path.write_text(html, encoding='utf-8')
    print(f"\n✅ 报告已生成: {out_path}")

    # 文字摘要
    summary = build_wecom_text(mmdd, guide_rows, guide_err, qc_rows, qc_err, bili_rows, bili_err, bili_raw)
    print("\n─── 文字摘要 ───")
    print(summary)

    if do_push:
        print("\n─── 推送到 GitHub Pages ───")
        import shutil, subprocess
        shutil.copy(out_path, f"{DAILY_REPORT_REPO}/index.html")
        result = subprocess.run(
            f'cd {DAILY_REPORT_REPO} && git add index.html && git commit -m "更新素材日报 {mmdd}" && git push',
            shell=True, capture_output=True, text=True
        )
        if result.returncode == 0:
            print(f"GitHub Pages 更新成功: {DAILY_REPORT_URL}")
        else:
            print(f"git push 失败，尝试 GitHub API 兜底: {result.stderr.strip()[:120]}")
            ok = push_via_gh_api(f"{DAILY_REPORT_REPO}/index.html", mmdd)
            if ok:
                print(f"GitHub Pages 更新成功（API 兜底）: {DAILY_REPORT_URL}")
            else:
                print("GitHub 推送失败（git 与 API 均不可用，稍后手动补推）")

        print("\n─── 推送企微 ───")
        card_img = REPORTS_DIR / f'snapshot_{mmdd}.png'
        render_page_snapshot(out_path.resolve(), card_img)
        print(f"快照已生成: {card_img}")
        push_wecom_image(card_img)
        # 第二条：文字+链接
        link_text = f"📊 {mmdd[:2]}月{mmdd[2:]}日 素材日报\n点开可查素材明细和预览视频 👉 {DAILY_REPORT_URL}"
        push_wecom(link_text, f"{mmdd[:2]}月{mmdd[2:]}日")

if __name__ == '__main__':
    main()
