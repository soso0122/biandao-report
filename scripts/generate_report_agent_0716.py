#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
代理商素材数据分析与HTML报告生成 - 2026.07.31
"""

import csv
import json
from collections import defaultdict
from datetime import datetime


def read_delivery_data(file_path):
    """读取投后看板数据"""
    data = []
    with open(file_path, 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        for row in reader:
            data.append(row)
    return data


def analyze_by_agent(delivery_data):
    """按代理商分析数据"""

    agent_stats = defaultdict(lambda: {
        '总消耗': 0.0,
        '总成交GMV': 0.0,
        '总成交单量': 0,
        '有消耗素材数': 0,
        '有成交素材数': 0,
        '平均投放天数': 0.0,
        '素材详情': [],
    })

    agent_product_orders = defaultdict(lambda: defaultdict(int))
    # 按 代理商+产品 维度聚合消耗/GMV/订单/素材数
    agent_product_stats = defaultdict(lambda: defaultdict(lambda: {'消耗': 0.0, 'GMV': 0.0, '订单': 0, '素材': set()}))
    material_delivery = defaultdict(list)
    material_first_time = {}
    material_days = {}

    for row in delivery_data:
        agent = row.get('代理商', '').strip()
        if not agent:
            continue

        material_name = row.get('素材名称', '').strip()
        material_link = row.get('素材预览', '').strip()
        product = row.get('投放产品', '').strip()
        first_time = row.get('首次消耗时间', '').strip()
        days_str = row.get('已上线投放天数', '').strip()

        key = agent + '###' + material_name
        if key not in material_first_time and first_time and first_time != '-':
            material_first_time[key] = first_time
        if key not in material_days and days_str and days_str not in ('', '-'):
            try:
                material_days[key] = int(days_str)
            except ValueError:
                pass

        try:
            consume = float(row.get('消耗', 0) or 0)
            gmv = float(row.get('成交GMV', 0) or 0)
            orders = int(float(row.get('成交单量', 0) or 0))

            agent_stats[agent]['总消耗'] += consume
            agent_stats[agent]['总成交GMV'] += gmv
            agent_stats[agent]['总成交单量'] += orders

            if product:
                agent_product_stats[agent][product]['消耗'] += consume
                agent_product_stats[agent][product]['GMV'] += gmv
                agent_product_stats[agent][product]['订单'] += orders
                if consume > 0:
                    agent_product_stats[agent][product]['素材'].add(material_name)

            if orders > 0 and product:
                agent_product_orders[agent][product] += orders

            material_delivery[key].append({
                '消耗': consume,
                'GMV': gmv,
                '单量': orders,
                '链接': material_link,
                '产品': product,
            })

        except (ValueError, TypeError):
            pass

    # 统计有效素材
    for agent in agent_stats:
        materials_with_consume = set()
        materials_with_orders = set()
        days_list = []

        for key, records in material_delivery.items():
            if not key.startswith(agent + '###'):
                continue
            material_name = key.split('###', 1)[1]

            total_consume = sum(r['消耗'] for r in records)
            total_orders = sum(r['单量'] for r in records)
            total_gmv = sum(r['GMV'] for r in records)

            if total_consume > 0:
                materials_with_consume.add(material_name)
            if total_orders > 0:
                materials_with_orders.add(material_name)
            if total_consume > 0 and key in material_days:
                days_list.append(material_days[key])

            material_link = records[0].get('链接', '') if records else ''
            first_time = material_first_time.get(key, '')
            days = material_days.get(key, None)
            # 取第一个非空产品值作为该素材的投放产品
            product_val = next((r['产品'] for r in records if r.get('产品')), '')

            agent_stats[agent]['素材详情'].append({
                '素材名称': material_name,
                '总消耗': total_consume,
                '总GMV': total_gmv,
                '总单量': total_orders,
                '链接': material_link,
                '首次消耗时间': first_time,
                '投放天数': days,
                '投放产品': product_val,
            })

        agent_stats[agent]['有消耗素材数'] = len(materials_with_consume)
        agent_stats[agent]['有成交素材数'] = len(materials_with_orders)
        agent_stats[agent]['平均投放天数'] = (
            sum(days_list) / len(days_list) if days_list else 0
        )

    # Top3 按成交单量
    for agent in agent_stats:
        sorted_materials = sorted(
            agent_stats[agent]['素材详情'],
            key=lambda x: x['总单量'],
            reverse=True
        )
        agent_stats[agent]['Top3素材'] = sorted_materials[:3]

    for agent in agent_stats:
        agent_stats[agent]['产品成单'] = dict(agent_product_orders[agent])

    # 全局素材分析
    global_materials = {}
    for key, records in material_delivery.items():
        agent, material_name = key.split('###', 1)
        total_consume = sum(r['消耗'] for r in records)
        if total_consume <= 0:
            continue
        material_link = records[0].get('链接', '') if records else ''
        first_time = material_first_time.get(key, '')
        days = material_days.get(key, None)
        product_val = next((r['产品'] for r in records if r.get('产品')), '')
        if material_name not in global_materials:
            global_materials[material_name] = {
                '素材名称': material_name,
                '代理商': agent,
                '总消耗': total_consume,
                '总GMV': sum(r['GMV'] for r in records),
                '总单量': sum(r['单量'] for r in records),
                '链接': material_link,
                '首次消耗时间': first_time,
                '投放天数': days,
                '投放产品': product_val,
            }
        else:
            global_materials[material_name]['总消耗'] += total_consume
            global_materials[material_name]['总GMV'] += sum(r['GMV'] for r in records)
            global_materials[material_name]['总单量'] += sum(r['单量'] for r in records)

    all_materials = list(global_materials.values())

    lifecycle_buckets = {'1-7天': [], '8-14天': [], '15-30天': [], '30天以上': []}
    for m in all_materials:
        d = m['投放天数']
        if d is None:
            continue
        if d <= 7:
            lifecycle_buckets['1-7天'].append(m)
        elif d <= 14:
            lifecycle_buckets['8-14天'].append(m)
        elif d <= 30:
            lifecycle_buckets['15-30天'].append(m)
        else:
            lifecycle_buckets['30天以上'].append(m)

    new_this_week = []
    for m in all_materials:
        ft = m['首次消耗时间']
        if not ft or ft == '-':
            continue
        try:
            dt = datetime.strptime(ft, '%Y/%m/%d')
            if datetime(2026, 7, 11) <= dt <= datetime(2026, 7, 16):
                new_this_week.append(m)
        except ValueError:
            pass
    new_this_week.sort(key=lambda x: x['总消耗'], reverse=True)

    global_analysis = {
        'lifecycle_buckets': lifecycle_buckets,
        'new_this_week': new_this_week,
        'total_with_consume': len(all_materials),
    }

    # 序列化：set → int，defaultdict → dict
    serializable = {}
    for a in agent_product_stats:
        serializable[a] = {}
        for p in agent_product_stats[a]:
            entry = agent_product_stats[a][p]
            serializable[a][p] = {
                '消耗': entry['消耗'],
                'GMV': entry['GMV'],
                '订单': entry['订单'],
                '素材': len(entry['素材']) if isinstance(entry['素材'], set) else entry['素材'],
            }

    return agent_stats, global_analysis, serializable


def generate_html(agent_stats, global_analysis, agent_product_stats, output_file='report_agent.html'):
    """生成HTML报告"""

    # 按总消耗降序排列代理商
    agents = sorted(agent_stats.keys(), key=lambda a: -agent_stats[a]['总消耗'])

    # 所有出现过的产品（按名称排序）
    all_products = sorted(set(
        p for a in agents for p in agent_product_stats[a].keys()
    ))

    total_consume = sum(s['总消耗'] for s in agent_stats.values())
    total_gmv = sum(s['总成交GMV'] for s in agent_stats.values())
    total_orders = sum(s['总成交单量'] for s in agent_stats.values())
    total_materials = sum(s['有消耗素材数'] for s in agent_stats.values())

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>代理商素材数据分析报告 - 2026.07.31</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link href="https://fonts.googleapis.com/css2?family=DM+Mono:wght@400;500&family=Syne:wght@700;800&family=DM+Sans:wght@300;400;500&display=swap" rel="stylesheet">
    <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
    <style>
        :root {{
            --bg: #0f1117;
            --surface: #181c27;
            --surface2: #1e2435;
            --border: rgba(255,255,255,0.07);
            --accent: #f0b429;
            --accent2: #38bdf8;
            --accent3: #34d399;
            --danger: #f87171;
            --text: #e8eaf0;
            --text-muted: #6b7280;
            --text-dim: #374151;
        }}

        * {{ margin: 0; padding: 0; box-sizing: border-box; }}

        body {{
            font-family: 'DM Sans', sans-serif;
            background: var(--bg);
            color: var(--text);
            padding: 32px 20px;
            min-height: 100vh;
            background-image:
                radial-gradient(ellipse 80% 50% at 20% -10%, rgba(240,180,41,0.08) 0%, transparent 60%),
                radial-gradient(ellipse 60% 40% at 80% 110%, rgba(56,189,248,0.06) 0%, transparent 60%);
        }}

        .container {{ max-width: 1440px; margin: 0 auto; }}

        /* ── HEADER ── */
        .report-header {{
            margin-bottom: 48px;
            padding-bottom: 32px;
            border-bottom: 1px solid var(--border);
            display: flex;
            align-items: flex-end;
            justify-content: space-between;
            flex-wrap: wrap;
            gap: 16px;
        }}

        .report-header-left h1 {{
            font-family: 'Syne', sans-serif;
            font-size: 42px;
            font-weight: 800;
            letter-spacing: -1px;
            color: var(--text);
            line-height: 1.1;
        }}

        .report-header-left h1 span {{
            color: var(--accent);
        }}

        .report-header-left .subtitle {{
            font-size: 13px;
            color: var(--text-muted);
            margin-top: 8px;
            font-family: 'DM Mono', monospace;
            letter-spacing: 0.5px;
        }}

        .report-badge {{
            display: inline-flex;
            align-items: center;
            gap: 6px;
            background: rgba(240,180,41,0.1);
            border: 1px solid rgba(240,180,41,0.25);
            color: var(--accent);
            padding: 6px 14px;
            border-radius: 20px;
            font-size: 12px;
            font-family: 'DM Mono', monospace;
        }}

        .report-badge::before {{
            content: '';
            width: 6px; height: 6px;
            background: var(--accent);
            border-radius: 50%;
        }}

        /* ── SECTION LABEL ── */
        .section-label {{
            font-family: 'DM Mono', monospace;
            font-size: 11px;
            letter-spacing: 2px;
            text-transform: uppercase;
            color: var(--text-muted);
            margin: 48px 0 20px 0;
            display: flex;
            align-items: center;
            gap: 12px;
        }}

        .section-label::after {{
            content: '';
            flex: 1;
            height: 1px;
            background: var(--border);
        }}

        /* ── SUMMARY CARDS ── */
        .summary-cards {{
            display: grid;
            grid-template-columns: repeat(4, 1fr);
            gap: 2px;
            background: var(--border);
            border: 1px solid var(--border);
            border-radius: 16px;
            overflow: hidden;
            margin-bottom: 0;
        }}

        .summary-card {{
            background: var(--surface);
            padding: 28px 24px;
            position: relative;
            overflow: hidden;
            transition: background 0.2s;
        }}

        .summary-card:hover {{ background: var(--surface2); }}

        .summary-card::before {{
            content: '';
            position: absolute;
            top: 0; left: 0; right: 0;
            height: 2px;
            background: var(--accent);
            opacity: 0;
            transition: opacity 0.2s;
        }}

        .summary-card:hover::before {{ opacity: 1; }}

        .summary-card h3 {{
            font-size: 11px;
            font-family: 'DM Mono', monospace;
            letter-spacing: 1.5px;
            text-transform: uppercase;
            color: var(--text-muted);
            margin-bottom: 14px;
        }}

        .summary-card .value {{
            font-family: 'DM Mono', monospace;
            font-size: 30px;
            font-weight: 500;
            color: var(--accent);
            line-height: 1;
            margin-bottom: 6px;
        }}

        .summary-card .label {{
            font-size: 12px;
            color: var(--text-dim);
        }}

        /* ── LIFECYCLE MODULE ── */
        .lifecycle-section {{
            background: var(--surface);
            border: 1px solid var(--border);
            border-radius: 16px;
            padding: 28px;
            margin-bottom: 0;
        }}

        .lifecycle-section h2 {{
            font-family: 'Syne', sans-serif;
            font-size: 18px;
            font-weight: 700;
            color: var(--text);
            margin-bottom: 24px;
        }}

        .lifecycle-grid {{
            display: grid;
            grid-template-columns: repeat(4, 1fr);
            gap: 10px;
            margin-bottom: 24px;
        }}

        .lifecycle-bucket {{
            border: 1px solid var(--border);
            border-radius: 10px;
            padding: 16px;
            cursor: pointer;
            transition: all 0.2s;
            background: var(--bg);
        }}

        .lifecycle-bucket:hover, .lifecycle-bucket.active {{
            border-color: var(--accent);
            background: rgba(240,180,41,0.05);
        }}

        .lifecycle-bucket-label {{
            font-family: 'DM Mono', monospace;
            font-size: 11px;
            letter-spacing: 1px;
            color: var(--text-muted);
            margin-bottom: 8px;
        }}

        .lifecycle-bucket-count {{
            font-family: 'DM Mono', monospace;
            font-size: 26px;
            font-weight: 500;
            line-height: 1;
        }}

        .lifecycle-bucket-sub {{
            font-size: 11px;
            color: var(--text-dim);
            margin-top: 6px;
            font-family: 'DM Mono', monospace;
        }}

        .lifecycle-chart-row {{
            display: flex;
            gap: 24px;
            align-items: flex-start;
        }}

        .lifecycle-chart-wrap {{ flex: 0 0 240px; height: 200px; position: relative; }}
        .lifecycle-detail {{ flex: 1; min-width: 0; }}

        .lifecycle-detail-title {{
            font-size: 12px;
            font-family: 'DM Mono', monospace;
            color: var(--text-muted);
            margin-bottom: 10px;
            letter-spacing: 0.5px;
        }}

        .material-list {{
            max-height: 260px;
            overflow-y: auto;
        }}

        .material-list::-webkit-scrollbar {{ width: 4px; }}
        .material-list::-webkit-scrollbar-track {{ background: transparent; }}
        .material-list::-webkit-scrollbar-thumb {{ background: var(--border); border-radius: 2px; }}

        .material-list-item {{
            display: flex;
            align-items: center;
            gap: 10px;
            padding: 8px 0;
            border-bottom: 1px solid var(--border);
            font-size: 12px;
        }}

        .material-list-item:last-child {{ border-bottom: none; }}
        .material-list-name {{ color: var(--text); flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
        .material-list-meta {{ color: var(--text-muted); font-family: 'DM Mono', monospace; font-size: 11px; white-space: nowrap; }}
        .material-list-link {{ color: var(--accent); text-decoration: none; font-size: 11px; white-space: nowrap; flex-shrink: 0; opacity: 0.8; }}
        .material-list-link:hover {{ opacity: 1; text-decoration: underline; }}

        .new-week-section {{
            margin-top: 24px;
            padding-top: 24px;
            border-top: 1px solid var(--border);
        }}

        .new-week-title {{
            font-family: 'Syne', sans-serif;
            font-size: 15px;
            font-weight: 700;
            color: var(--text);
            margin-bottom: 4px;
            display: flex;
            align-items: center;
            gap: 10px;
        }}

        .new-week-sub {{ font-size: 12px; color: var(--text-muted); margin-bottom: 14px; font-family: 'DM Mono', monospace; }}

        .new-week-badge {{
            display: inline-flex;
            align-items: center;
            background: rgba(52,211,153,0.15);
            border: 1px solid rgba(52,211,153,0.3);
            color: var(--accent3);
            padding: 2px 10px;
            border-radius: 10px;
            font-size: 11px;
            font-family: 'DM Mono', monospace;
        }}

        /* ── AGENT CARDS ── */
        .agent-cards {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(360px, 1fr));
            gap: 16px;
            margin-bottom: 0;
        }}

        .agent-card {{
            background: var(--surface);
            border: 1px solid var(--border);
            border-radius: 16px;
            padding: 24px;
            transition: border-color 0.2s;
        }}

        .agent-card:hover {{ border-color: rgba(240,180,41,0.3); }}

        .agent-card-header {{
            display: flex;
            align-items: center;
            justify-content: space-between;
            margin-bottom: 20px;
            padding-bottom: 16px;
            border-bottom: 1px solid var(--border);
        }}

        .agent-card h2 {{
            font-family: 'Syne', sans-serif;
            font-size: 22px;
            font-weight: 800;
            color: var(--text);
        }}

        .agent-rank {{
            font-family: 'DM Mono', monospace;
            font-size: 11px;
            color: var(--text-muted);
            background: var(--bg);
            border: 1px solid var(--border);
            padding: 3px 8px;
            border-radius: 6px;
        }}

        .data-section {{ margin-bottom: 18px; }}

        .section-header {{
            font-family: 'DM Mono', monospace;
            font-size: 10px;
            letter-spacing: 2px;
            text-transform: uppercase;
            color: var(--text-muted);
            margin-bottom: 12px;
            display: flex;
            align-items: center;
            gap: 8px;
        }}

        .section-header::after {{
            content: '';
            flex: 1;
            height: 1px;
            background: var(--border);
        }}

        .stat-row {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 9px 0;
            border-bottom: 1px solid rgba(255,255,255,0.03);
        }}

        .stat-row:last-child {{ border-bottom: none; }}
        .stat-label {{ color: var(--text-muted); font-size: 13px; }}
        .stat-value {{ font-family: 'DM Mono', monospace; font-weight: 500; color: var(--text); font-size: 14px; }}
        .stat-value.highlight {{ color: var(--accent); font-size: 16px; }}

        .product-orders {{
            margin-top: 12px;
            padding: 12px;
            background: var(--bg);
            border: 1px solid var(--border);
            border-radius: 8px;
        }}

        .product-orders-title {{
            font-family: 'DM Mono', monospace;
            font-size: 10px;
            letter-spacing: 1.5px;
            text-transform: uppercase;
            color: var(--text-muted);
            margin-bottom: 8px;
        }}

        .product-item {{
            padding: 4px 0;
            display: flex;
            justify-content: space-between;
            align-items: center;
            font-size: 12px;
        }}

        .product-name {{ color: var(--text-muted); }}
        .product-count {{ font-family: 'DM Mono', monospace; color: var(--accent2); font-weight: 500; }}

        .top3-section {{
            margin-top: 18px;
            padding-top: 18px;
            border-top: 1px solid var(--border);
        }}

        .top3-title {{
            font-family: 'DM Mono', monospace;
            font-size: 10px;
            letter-spacing: 2px;
            text-transform: uppercase;
            color: var(--text-muted);
            margin-bottom: 12px;
        }}

        .top3-item {{
            margin-bottom: 10px;
            padding: 10px 12px;
            background: var(--bg);
            border: 1px solid var(--border);
            border-radius: 8px;
            transition: border-color 0.15s;
        }}

        .top3-item:hover {{ border-color: rgba(240,180,41,0.2); }}

        .top3-rank {{
            display: inline-flex;
            align-items: center;
            justify-content: center;
            width: 20px; height: 20px;
            background: rgba(240,180,41,0.15);
            color: var(--accent);
            border-radius: 4px;
            font-weight: 700;
            font-size: 11px;
            font-family: 'DM Mono', monospace;
            margin-right: 8px;
        }}

        .top3-name {{ color: var(--text); font-size: 12px; margin-bottom: 5px; }}
        .top3-stats {{ color: var(--text-muted); font-size: 11px; font-family: 'DM Mono', monospace; margin-left: 28px; }}

        .top3-link {{
            color: var(--accent);
            text-decoration: none;
            font-size: 11px;
            font-family: 'DM Mono', monospace;
            margin-left: 28px;
            display: inline-block;
            margin-top: 5px;
            opacity: 0.7;
            transition: opacity 0.15s;
        }}

        .top3-link:hover {{ opacity: 1; }}

        .details-btn {{
            width: 100%;
            margin-top: 16px;
            background: transparent;
            color: var(--text-muted);
            border: 1px solid var(--border);
            padding: 9px 16px;
            border-radius: 8px;
            cursor: pointer;
            font-size: 12px;
            font-family: 'DM Mono', monospace;
            letter-spacing: 0.5px;
            transition: all 0.2s;
        }}

        .details-btn:hover {{
            border-color: var(--accent);
            color: var(--accent);
            background: rgba(240,180,41,0.05);
        }}

        /* ── CHARTS ── */
        .charts-section {{
            background: var(--surface);
            border: 1px solid var(--border);
            border-radius: 16px;
            padding: 28px;
        }}

        .charts-section h2 {{
            font-family: 'Syne', sans-serif;
            font-size: 18px;
            font-weight: 700;
            color: var(--text);
            margin-bottom: 24px;
        }}

        .charts-grid {{
            display: grid;
            grid-template-columns: repeat(2, 1fr);
            gap: 24px;
        }}

        .chart-container {{
            position: relative;
            height: 260px;
            background: var(--bg);
            border: 1px solid var(--border);
            border-radius: 10px;
            padding: 16px;
        }}

        /* ── TABLE ── */
        .table-section {{
            background: var(--surface);
            border: 1px solid var(--border);
            border-radius: 16px;
            padding: 28px;
            overflow-x: auto;
        }}

        .table-section h2 {{
            font-family: 'Syne', sans-serif;
            font-size: 18px;
            font-weight: 700;
            color: var(--text);
            margin-bottom: 20px;
        }}

        table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}

        th {{
            background: var(--bg);
            color: var(--text-muted);
            padding: 12px 14px;
            text-align: left;
            font-family: 'DM Mono', monospace;
            font-size: 10px;
            letter-spacing: 1.5px;
            text-transform: uppercase;
            border-bottom: 1px solid var(--border);
            font-weight: 400;
        }}

        td {{
            padding: 13px 14px;
            border-bottom: 1px solid rgba(255,255,255,0.03);
            font-family: 'DM Mono', monospace;
            font-size: 13px;
            color: var(--text-muted);
        }}

        td:first-child {{
            color: var(--text);
            font-size: 14px;
            font-family: 'Syne', sans-serif;
            font-weight: 700;
        }}

        tr:hover td {{ background: rgba(255,255,255,0.02); }}

        /* ── MODAL ── */
        .modal {{
            display: none;
            position: fixed;
            top: 0; left: 0;
            width: 100%; height: 100%;
            background: rgba(0,0,0,0.7);
            backdrop-filter: blur(4px);
            z-index: 1000;
            padding: 20px;
            overflow-y: auto;
        }}

        .modal-content {{
            background: var(--surface);
            border: 1px solid var(--border);
            max-width: 960px;
            margin: 60px auto;
            border-radius: 16px;
            padding: 32px;
            position: relative;
        }}

        .modal-content h2 {{
            font-family: 'Syne', sans-serif;
            font-size: 20px;
            font-weight: 800;
            color: var(--text);
            margin-bottom: 20px;
        }}

        .modal-close {{
            position: absolute;
            top: 20px; right: 24px;
            font-size: 24px;
            cursor: pointer;
            color: var(--text-muted);
            line-height: 1;
        }}

        .modal-close:hover {{ color: var(--text); }}

        .modal-content table th {{
            background: var(--bg);
        }}

        .modal-content a {{
            color: var(--accent);
            text-decoration: none;
        }}

        .modal-content a:hover {{ text-decoration: underline; }}

        .timestamp {{
            text-align: center;
            color: var(--text-dim);
            margin-top: 40px;
            font-size: 11px;
            font-family: 'DM Mono', monospace;
            letter-spacing: 1px;
        }}

        /* ── 消耗进度条 ── */
        .consume-bar-wrap {{
            margin: 14px 0 18px;
        }}

        .consume-bar-label {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 6px;
            font-family: 'DM Mono', monospace;
            font-size: 10px;
            color: var(--text-muted);
            letter-spacing: 0.5px;
        }}

        .consume-bar-label .pct {{
            color: var(--accent);
            font-size: 12px;
        }}

        .consume-bar-bg {{
            height: 4px;
            background: rgba(255,255,255,0.06);
            border-radius: 2px;
            overflow: hidden;
        }}

        .consume-bar-fill {{
            height: 100%;
            border-radius: 2px;
            background: var(--accent);
            width: 0;
            transition: width 1.2s cubic-bezier(0.16, 1, 0.3, 1);
        }}

        /* ── 卡片入场动画 ── */
        .fade-up {{
            opacity: 0;
            transform: translateY(24px);
            transition: opacity 0.5s ease, transform 0.5s ease;
        }}

        .fade-up.visible {{
            opacity: 1;
            transform: translateY(0);
        }}

        /* ── 数字计数 ── */
        .count-num {{ display: inline; }}

        /* ── 分桶展开面板 ── */
        .bucket-panel {{
            overflow: hidden;
            max-height: 0;
            transition: max-height 0.45s cubic-bezier(0.16, 1, 0.3, 1), opacity 0.3s ease;
            opacity: 0;
        }}

        .bucket-panel.open {{
            max-height: 500px;
            opacity: 1;
        }}

        .bucket-panel-inner {{
            padding: 16px 0 4px;
            border-top: 1px solid var(--border);
            margin-top: 20px;
        }}

        .bucket-panel-header {{
            display: flex;
            align-items: center;
            gap: 10px;
            margin-bottom: 12px;
        }}

        .bucket-panel-title {{
            font-family: 'DM Mono', monospace;
            font-size: 11px;
            letter-spacing: 1.5px;
            text-transform: uppercase;
            color: var(--text-muted);
        }}

        .bucket-panel-count {{
            font-family: 'DM Mono', monospace;
            font-size: 11px;
            color: var(--accent);
            background: rgba(240,180,41,0.1);
            border: 1px solid rgba(240,180,41,0.2);
            padding: 1px 7px;
            border-radius: 8px;
        }}

        /* ── 弹窗消耗进度条 ── */
        .modal-row-bar {{
            height: 3px;
            border-radius: 2px;
            margin-top: 4px;
            transition: width 0.8s cubic-bezier(0.16, 1, 0.3, 1);
        }}

        .modal-item {{
            padding: 14px 0;
            border-bottom: 1px solid var(--border);
        }}

        .modal-item:last-child {{ border-bottom: none; }}

        .modal-item-header {{
            display: flex;
            align-items: flex-start;
            gap: 12px;
            margin-bottom: 6px;
        }}

        .modal-item-rank {{
            font-family: 'DM Mono', monospace;
            font-size: 11px;
            color: var(--text-muted);
            min-width: 20px;
            padding-top: 2px;
        }}

        .modal-item-name {{
            flex: 1;
            font-size: 13px;
            color: var(--text);
            line-height: 1.4;
            min-width: 0;
        }}

        .modal-item-link {{
            color: var(--accent);
            text-decoration: none;
            font-size: 12px;
            font-family: 'DM Mono', monospace;
            opacity: 0.7;
            flex-shrink: 0;
            padding-top: 2px;
        }}

        .modal-item-link:hover {{ opacity: 1; }}

        .modal-item-stats {{
            display: flex;
            gap: 20px;
            margin-left: 32px;
            font-family: 'DM Mono', monospace;
            font-size: 11px;
            color: var(--text-muted);
        }}

        .modal-item-stats .val {{
            color: var(--text);
        }}

        .modal-item-stats .val.accent {{
            color: var(--accent);
        }}

        .modal-bar-wrap {{
            margin: 8px 0 0 32px;
        }}

        .modal-bar-bg {{
            height: 3px;
            background: rgba(255,255,255,0.05);
            border-radius: 2px;
            overflow: hidden;
        }}

        .modal-bar-fill {{
            height: 100%;
            border-radius: 2px;
            background: linear-gradient(90deg, var(--accent), var(--accent2));
            width: 0;
            transition: width 1s cubic-bezier(0.16, 1, 0.3, 1);
        }}
    </style>
</head>
<body>
    <div class="container">

        <div class="report-header">
            <div class="report-header-left">
                <h1>代理商<span>素材</span>分析</h1>
                <div class="subtitle">AGENT MATERIAL REPORT · 2026.07.31</div>
            </div>
            <div class="report-badge">数据截至 2026/07/16</div>
        </div>

        <!-- 总览 -->
        <div class="section-label">总览指标</div>
        <div class="summary-cards">
            <div class="summary-card">
                <h3>投放总消耗</h3>
                <div class="value">¥{total_consume:,.0f}</div>
                <div class="label">元</div>
            </div>
            <div class="summary-card">
                <h3>投放总 GMV</h3>
                <div class="value">¥{total_gmv:,.0f}</div>
                <div class="label">元</div>
            </div>
            <div class="summary-card">
                <h3>投放总订单</h3>
                <div class="value">{total_orders}</div>
                <div class="label">单</div>
            </div>
            <div class="summary-card">
                <h3>有消耗素材数</h3>
                <div class="value">{total_materials}</div>
                <div class="label">条</div>
            </div>
        </div>

        <!-- 素材投放分析 -->
        <div class="section-label">素材投放分析</div>
        <div class="lifecycle-section">
            <h2>素材生命周期 &amp; 本周新起量</h2>
            <div class="lifecycle-grid">
"""

    buckets = global_analysis['lifecycle_buckets']
    bucket_keys = ['1-7天', '8-14天', '15-30天', '30天以上']
    bucket_colors = ['#34d399', '#38bdf8', '#f0b429', '#f87171']
    total_with_consume = global_analysis['total_with_consume']

    for i, bk in enumerate(bucket_keys):
        items = buckets[bk]
        pct = len(items) / total_with_consume * 100 if total_with_consume else 0
        html += f"""
                <div class="lifecycle-bucket" id="bucket-{i}" onclick="selectBucket({i})">
                    <div class="lifecycle-bucket-label">{bk}</div>
                    <div class="lifecycle-bucket-count" style="color:{bucket_colors[i]}">{len(items)}</div>
                    <div class="lifecycle-bucket-sub">占有消耗素材 {pct:.0f}%</div>
                </div>
"""

    html += """
            </div>

            <!-- 图表 + 展开面板 -->
            <div class="lifecycle-chart-row">
                <div class="lifecycle-chart-wrap">
                    <canvas id="lifecycleChart"></canvas>
                </div>
                <div class="lifecycle-detail">
                    <div class="lifecycle-detail-title" id="bucketDetailTitle">← 点击左侧分桶查看素材明细</div>
                    <div class="material-list" id="bucketMaterialList"></div>
                </div>
            </div>

            <!-- 展开面板（全宽，点击分桶后滑出） -->
            <div class="bucket-panel" id="bucketPanel">
                <div class="bucket-panel-inner">
                    <div class="bucket-panel-header">
                        <span class="bucket-panel-title" id="bucketPanelTitle"></span>
                        <span class="bucket-panel-count" id="bucketPanelCount"></span>
                    </div>
                    <div class="material-list" id="bucketPanelList" style="max-height:320px"></div>
                </div>
            </div>
"""

    new_this_week = global_analysis['new_this_week']
    html += f"""
            <div class="new-week-section">
                <div class="new-week-title">
                    本周新起量素材
                    <span class="new-week-badge">{len(new_this_week)} 条</span>
                </div>
                <div class="new-week-sub">首次消耗时间在 7月11日 - 7月16日，共 {len(new_this_week)} 条素材本周开始产生消耗（占有消耗素材 {len(new_this_week)/total_with_consume*100:.0f}%）</div>
                <div class="material-list">
"""
    for m in new_this_week:
        link = m.get('链接', '')
        link_html = f'<a href="{link}" target="_blank" class="material-list-link">🎬 查看</a>' if link else ''
        html += f"""
                    <div class="material-list-item">
                        <span class="material-list-name" title="{m['素材名称']}">{m['素材名称']}</span>
                        <span class="material-list-meta">{m['代理商']} | 首消 {m['首次消耗时间']} | ¥{m['总消耗']:,.0f} | {m['总单量']}单</span>
                        {link_html}
                    </div>
"""
    html += """
                </div>
            </div>
        </div>

        <!-- 各代理商卡片 -->
        <div class="section-label">各代理商详细数据</div>
        <div class="agent-cards">
"""

    max_consume = max(agent_stats[a]['总消耗'] for a in agents) if agents else 1

    for agent in agents:
        s = agent_stats[agent]
        consume_pct = s['总消耗'] / max_consume * 100 if max_consume else 0

        html += f"""
            <div class="agent-card fade-up">
                <div class="agent-card-header">
                    <h2>{agent}</h2>
                    <span class="agent-rank">#{agents.index(agent)+1} by 消耗</span>
                </div>

                <div class="consume-bar-wrap">
                    <div class="consume-bar-label">
                        <span>消耗占比</span>
                        <span class="pct">{consume_pct:.0f}%</span>
                    </div>
                    <div class="consume-bar-bg">
                        <div class="consume-bar-fill" data-width="{consume_pct:.1f}"></div>
                    </div>
                </div>

                <div class="data-section">
                    <div class="section-header">投放效果</div>
                    <div class="stat-row">
                        <span class="stat-label">总消耗</span>
                        <span class="stat-value highlight" data-count="{s['总消耗']:.0f}" data-prefix="¥">¥{s['总消耗']:,.0f}</span>
                    </div>
                    <div class="stat-row">
                        <span class="stat-label">总GMV</span>
                        <span class="stat-value" data-count="{s['总成交GMV']:.0f}" data-prefix="¥">¥{s['总成交GMV']:,.0f}</span>
                    </div>
                    <div class="stat-row">
                        <span class="stat-label">总订单</span>
                        <span class="stat-value" data-count="{s['总成交单量']}" data-suffix=" 单">{s['总成交单量']} 单</span>
                    </div>
                    <div class="stat-row">
                        <span class="stat-label">有消耗素材 / 有成交素材</span>
                        <span class="stat-value">{s['有消耗素材数']} / {s['有成交素材数']}</span>
                    </div>
                    <div class="stat-row">
                        <span class="stat-label">平均投放天数</span>
                        <span class="stat-value">{s['平均投放天数']:.1f} 天</span>
                    </div>
"""

        # 产品成单明细
        product_orders = s.get('产品成单', {})
        if product_orders:
            html += """
                    <div class="product-orders">
                        <div class="product-orders-title">产品成单明细</div>
"""
            for product, orders in sorted(product_orders.items(), key=lambda x: -x[1]):
                html += f"""
                        <div class="product-item">
                            <span class="product-name">{product}</span>:
                            <span class="product-count">{orders}单</span>
                        </div>
"""
            html += """
                    </div>
"""

        html += """
                </div>
"""

        # Top3 素材
        top3 = s.get('Top3素材', [])
        if top3:
            html += """
                <div class="top3-section">
                    <div class="top3-title">成交单量 TOP 3 素材</div>
"""
            for idx, m in enumerate(top3, 1):
                first_time_str = f' | 首消 {m["首次消耗时间"]}' if m.get('首次消耗时间') else ''
                days_str = f' | 已投 {m["投放天数"]} 天' if m.get('投放天数') is not None else ''
                html += f"""
                    <div class="top3-item">
                        <div class="top3-name">
                            <span class="top3-rank">{idx}</span>{m['素材名称']}
                        </div>
                        <div class="top3-stats">成交 {m['总单量']} 单 | GMV ¥{m['总GMV']:,.2f}{first_time_str}{days_str}</div>
"""
                if m.get('链接'):
                    html += f"""
                        <a href="{m['链接']}" target="_blank" class="top3-link">🎬 查看素材</a>
"""
                html += """
                    </div>
"""
            html += """
                </div>
"""

        html += f"""
                <button class="details-btn" onclick="showDetails('{agent}')">查看Top 20详情</button>
            </div>
"""

    html += """
        </div>

        <!-- 数据可视化 -->
        <div class="section-label">代理商对比</div>
        <div class="charts-section">
            <div style="display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:10px;margin-bottom:16px">
                <h2 style="margin:0">按产品查看</h2>
                <div id="prodFilterBar" style="display:flex;gap:6px;flex-wrap:wrap">
                    <button class="prod-filter-btn active" onclick="filterByProduct('all',this)"
                        style="font-family:var(--mono);font-size:11px;padding:5px 14px;border-radius:20px;border:1px solid var(--border2);background:var(--ink);color:#fff;cursor:pointer">
                        全部
                    </button>
""" + "".join([
    f"""                    <button class="prod-filter-btn" onclick="filterByProduct({repr(prod)},this)"
                        style="font-family:var(--mono);font-size:11px;padding:5px 14px;border-radius:20px;border:1px solid var(--border2);background:var(--surface);color:var(--muted);cursor:pointer">
                        {prod}
                    </button>
"""
    for prod in all_products
]) + """                </div>
            </div>
            <div class="charts-grid">
                <div class="chart-container"><canvas id="consumeChart"></canvas></div>
                <div class="chart-container"><canvas id="gmvChart"></canvas></div>
                <div class="chart-container"><canvas id="ordersChart"></canvas></div>
                <div class="chart-container"><canvas id="materialsChart"></canvas></div>
            </div>
        </div>

        <!-- 详细对比表格 -->
        <div class="section-label">详细对比</div>
        <div class="table-section">
            <h2>代理商数据汇总</h2>
            <table>
                <thead>
                    <tr>
                        <th>代理商</th>
                        <th>总消耗</th>
                        <th>总GMV</th>
                        <th>总订单</th>
                        <th>有消耗素材</th>
                        <th>有成交素材</th>
                        <th>平均投放天数</th>
                    </tr>
                </thead>
                <tbody id="compareTableBody">
"""

    for agent in agents:
        s = agent_stats[agent]
        html += f"""
                    <tr>
                        <td><strong>{agent}</strong></td>
                        <td>¥{s['总消耗']:,.2f}</td>
                        <td>¥{s['总成交GMV']:,.2f}</td>
                        <td>{s['总成交单量']}</td>
                        <td>{s['有消耗素材数']}</td>
                        <td>{s['有成交素材数']}</td>
                        <td>{s['平均投放天数']:.1f} 天</td>
                    </tr>
"""

    html += """
                </tbody>
            </table>
        </div>

        <div class="timestamp">
            生成时间: """ + datetime.now().strftime('%Y-%m-%d %H:%M:%S') + """
        </div>
    </div>

    <!-- 详情弹窗 -->
    <div id="detailsModal" class="modal">
        <div class="modal-content">
            <span class="modal-close" onclick="closeDetails()">&times;</span>
            <div id="modalBody"></div>
        </div>
    </div>

    <script>
        // 生命周期分桶数据
        const lifecycleBuckets = """ + json.dumps({
            bk: [
                {
                    '素材名称': m['素材名称'],
                    '代理商': m['代理商'],
                    '总消耗': m['总消耗'],
                    '总单量': m['总单量'],
                    '首次消耗时间': m['首次消耗时间'],
                    '投放天数': m['投放天数'],
                    '链接': m['链接'],
                }
                for m in sorted(global_analysis['lifecycle_buckets'][bk], key=lambda x: x['总消耗'], reverse=True)
            ]
            for bk in ['1-7天', '8-14天', '15-30天', '30天以上']
        }) + """;
        const bucketColors = ['#34d399', '#38bdf8', '#f0b429', '#f87171'];
        const bucketKeys = ['1-7天', '8-14天', '15-30天', '30天以上'];
        let activeBucket = null;

        // ── 生命周期环形图（改为横向条形图）
        Chart.defaults.color = '#6b7280';
        Chart.defaults.borderColor = 'rgba(255,255,255,0.07)';

        new Chart(document.getElementById('lifecycleChart'), {
            type: 'bar',
            data: {
                labels: bucketKeys,
                datasets: [{
                    data: bucketKeys.map(k => lifecycleBuckets[k].length),
                    backgroundColor: bucketColors,
                    borderRadius: 4,
                    borderSkipped: false,
                }]
            },
            options: {
                indexAxis: 'y',
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { display: false },
                    title: { display: true, text: '生命周期分布', color: '#6b7280', font: { size: 11, family: 'DM Mono' } }
                },
                scales: {
                    x: { grid: { color: 'rgba(255,255,255,0.04)' }, ticks: { font: { family: 'DM Mono', size: 11 } } },
                    y: { grid: { display: false }, ticks: { font: { family: 'DM Mono', size: 11 } } }
                }
            }
        });

        // ── 分桶点击：侧边列表 + 全宽展开面板
        function selectBucket(idx) {
            const bk = bucketKeys[idx];
            const items = lifecycleBuckets[bk];

            // 切换高亮
            document.querySelectorAll('.lifecycle-bucket').forEach((el, i) => {
                el.classList.toggle('active', i === idx);
            });

            // 侧边小列表（图表右侧）
            document.getElementById('bucketDetailTitle').textContent =
                bk + '  ·  共 ' + items.length + ' 条';
            const sideList = document.getElementById('bucketMaterialList');
            sideList.innerHTML = items.slice(0, 8).map(m => {
                const linkHtml = m.链接
                    ? '<a href="' + m.链接 + '" target="_blank" class="material-list-link">查看</a>'
                    : '';
                return '<div class="material-list-item">' +
                    '<span class="material-list-name" title="' + m.素材名称 + '">' + m.素材名称 + '</span>' +
                    '<span class="material-list-meta">¥' + m.总消耗.toFixed(0) + '</span>' +
                    linkHtml + '</div>';
            }).join('') + (items.length > 8 ? '<div style="color:var(--text-dim);font-size:11px;padding:6px 0;font-family:DM Mono">还有 ' + (items.length - 8) + ' 条 ↓</div>' : '');

            // 全宽展开面板
            const panel = document.getElementById('bucketPanel');
            const panelList = document.getElementById('bucketPanelList');
            document.getElementById('bucketPanelTitle').textContent = bk + ' 素材明细';
            document.getElementById('bucketPanelCount').textContent = items.length + ' 条';

            const maxC = items.length ? Math.max(...items.map(m => m.总消耗)) : 1;
            panelList.innerHTML = items.map((m, i) => {
                const barPct = maxC > 0 ? (m.总消耗 / maxC * 100).toFixed(1) : 0;
                const linkHtml = m.链接
                    ? '<a href="' + m.链接 + '" target="_blank" class="material-list-link">🎬 查看</a>'
                    : '';
                return '<div class="material-list-item">' +
                    '<span style="font-family:DM Mono;font-size:11px;color:var(--text-dim);min-width:22px">' + (i+1) + '</span>' +
                    '<span class="material-list-name" title="' + m.素材名称 + '">' + m.素材名称 + '</span>' +
                    '<span class="material-list-meta">' + m.代理商 + ' | ' + (m.首次消耗时间||'-') + ' | ¥' + m.总消耗.toFixed(0) + ' | ' + m.总单量 + '单 | ' + (m.投放天数||'-') + '天</span>' +
                    linkHtml + '</div>';
            }).join('');

            if (activeBucket === idx) {
                panel.classList.remove('open');
                activeBucket = null;
            } else {
                panel.classList.add('open');
                activeBucket = idx;
                setTimeout(() => {
                    panel.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
                }, 100);
            }
        }

        // ── 代理商图表
        const agents = """ + json.dumps(agents) + """;

        // 全量数据（全部产品）
        const allProductData = {
            consume:   """ + json.dumps([agent_stats[a]['总消耗'] for a in agents]) + """,
            gmv:       """ + json.dumps([agent_stats[a]['总成交GMV'] for a in agents]) + """,
            orders:    """ + json.dumps([agent_stats[a]['总成交单量'] for a in agents]) + """,
            materials: """ + json.dumps([agent_stats[a]['有消耗素材数'] for a in agents]) + """
        };

        // 按产品维度数据：{产品名: {consume:[], gmv:[], orders:[], materials:[]}}
        const productData = """ + json.dumps({
            prod: {
                'consume':   [agent_product_stats.get(a, {}).get(prod, {}).get('消耗', 0) for a in agents],
                'gmv':       [agent_product_stats.get(a, {}).get(prod, {}).get('GMV', 0) for a in agents],
                'orders':    [agent_product_stats.get(a, {}).get(prod, {}).get('订单', 0) for a in agents],
                'materials': [agent_product_stats.get(a, {}).get(prod, {}).get('素材', 0) for a in agents],
            }
            for prod in all_products
        }) + """;

        // 兼容旧变量名（默认全量）
        let consumeData = allProductData.consume;
        let gmvData = allProductData.gmv;
        let ordersData = allProductData.orders;
        let materialsData = allProductData.materials;
        const chartColors = ['#f0b429', '#38bdf8', '#34d399', '#f87171', '#a78bfa'];

        const barOpts = (title) => ({
            responsive: true, maintainAspectRatio: false,
            plugins: {
                legend: { display: false },
                title: { display: true, text: title, color: '#6b7280', font: { size: 11, family: 'DM Mono' } }
            },
            scales: {
                x: { grid: { display: false }, ticks: { font: { family: 'DM Mono', size: 11 } } },
                y: { grid: { color: 'rgba(255,255,255,0.04)' }, ticks: { font: { family: 'DM Mono', size: 11 } } }
            }
        });

        const chartKeys = ['consume','gmv','orders','materials'];
        const chartTitles = ['总消耗对比', 'GMV 对比', '订单数对比', '有消耗素材数对比'];
        const charts = {};
        chartKeys.forEach((key, i) => {
            const data = allProductData[key];
            charts[key] = new Chart(document.getElementById(key + 'Chart'), {
                type: 'bar',
                data: { labels: agents, datasets: [{ data, backgroundColor: chartColors, borderRadius: 4, borderSkipped: false }] },
                options: barOpts(chartTitles[i])
            });
        });

        // 产品筛选：更新图表 + 表格
        function filterByProduct(prod, btn) {
            document.querySelectorAll('.prod-filter-btn').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            const d = prod === 'all' ? allProductData : (productData[prod] || allProductData);
            chartKeys.forEach(key => {
                charts[key].data.datasets[0].data = d[key];
                charts[key].update();
            });
            // 更新对比表格
            updateCompareTable(prod);
        }

        function updateCompareTable(prod) {
            const tbody = document.getElementById('compareTableBody');
            if (!tbody) return;
            agents.forEach((a, i) => {
                const d = prod === 'all' ? allProductData : (productData[prod] || allProductData);
                const row = tbody.rows[i];
                if (!row) return;
                row.cells[1].textContent = '¥' + d.consume[i].toLocaleString('zh', {maximumFractionDigits:2});
                row.cells[2].textContent = '¥' + d.gmv[i].toLocaleString('zh', {maximumFractionDigits:2});
                row.cells[3].textContent = d.orders[i];
                row.cells[4].textContent = d.materials[i];
            });
        }

        // ── 卡片入场动画（IntersectionObserver）
        const fadeEls = document.querySelectorAll('.fade-up');
        const observer = new IntersectionObserver((entries) => {
            entries.forEach((entry, i) => {
                if (entry.isIntersecting) {
                    setTimeout(() => entry.target.classList.add('visible'), i * 80);
                    observer.unobserve(entry.target);
                }
            });
        }, { threshold: 0.1 });
        fadeEls.forEach(el => observer.observe(el));

        // ── 消耗进度条动画
        function animateBars() {
            document.querySelectorAll('.consume-bar-fill').forEach(el => {
                const w = el.dataset.width;
                setTimeout(() => el.style.width = w + '%', 300);
            });
        }
        window.addEventListener('load', animateBars);

        // ── 数字计数动画
        function countUp(el, target, prefix, suffix, duration) {
            const start = performance.now();
            const update = (now) => {
                const elapsed = now - start;
                const progress = Math.min(elapsed / duration, 1);
                const ease = 1 - Math.pow(1 - progress, 3);
                const val = Math.round(ease * target);
                el.textContent = (prefix || '') + val.toLocaleString() + (suffix || '');
                if (progress < 1) requestAnimationFrame(update);
            };
            requestAnimationFrame(update);
        }

        const countObserver = new IntersectionObserver((entries) => {
            entries.forEach(entry => {
                if (entry.isIntersecting) {
                    const el = entry.target;
                    const target = parseFloat(el.dataset.count);
                    const prefix = el.dataset.prefix || '';
                    const suffix = el.dataset.suffix || '';
                    countUp(el, target, prefix, suffix, 1200);
                    countObserver.unobserve(el);
                }
            });
        }, { threshold: 0.5 });
        document.querySelectorAll('[data-count]').forEach(el => countObserver.observe(el));

        // ── Top20 弹窗（卡片式 + 消耗进度条）
        const materialDetails = """ + json.dumps({
            a: sorted(
                agent_stats[a]['素材详情'],
                key=lambda x: x['总消耗'],
                reverse=True
            )[:20]
            for a in agents
        }) + """;

        function showDetails(agent) {
            const modal = document.getElementById('detailsModal');
            const modalBody = document.getElementById('modalBody');
            const details = materialDetails[agent] || [];
            const maxC = details.length ? Math.max(...details.map(d => d.总消耗)) : 1;

            let html = '<h2>' + agent + ' · 消耗 TOP 20 素材</h2>';
            html += '<div style="margin-bottom:12px;font-family:DM Mono;font-size:11px;color:var(--text-muted);letter-spacing:1px">按消耗降序排列，进度条为相对占比</div>';

            details.forEach((item, i) => {
                const barPct = maxC > 0 ? (item.总消耗 / maxC * 100).toFixed(1) : 0;
                const linkHtml = item.链接
                    ? '<a href="' + item.链接 + '" target="_blank" class="modal-item-link">🎬 查看</a>'
                    : '';
                html += '<div class="modal-item">';
                html += '<div class="modal-item-header">';
                html += '<span class="modal-item-rank">' + (i+1).toString().padStart(2,'0') + '</span>';
                html += '<span class="modal-item-name">' + item.素材名称 + '</span>';
                html += linkHtml;
                html += '</div>';
                html += '<div class="modal-item-stats">';
                html += '<span>消耗 <span class="val accent">¥' + item.总消耗.toFixed(0) + '</span></span>';
                html += '<span>GMV <span class="val">¥' + item.总GMV.toFixed(0) + '</span></span>';
                html += '<span>成交 <span class="val">' + item.总单量 + ' 单</span></span>';
                html += '<span>首消 <span class="val">' + (item.首次消耗时间||'-') + '</span></span>';
                html += '<span>已投 <span class="val">' + (item.投放天数!=null?item.投放天数+'天':'-') + '</span></span>';
                html += '</div>';
                html += '<div class="modal-bar-wrap"><div class="modal-bar-bg"><div class="modal-bar-fill" style="width:0" data-w="' + barPct + '"></div></div></div>';
                html += '</div>';
            });

            modalBody.innerHTML = html;
            modal.style.display = 'block';

            // 触发进度条动画
            setTimeout(() => {
                modal.querySelectorAll('.modal-bar-fill').forEach(el => {
                    el.style.width = el.dataset.w + '%';
                });
            }, 80);
        }

        function closeDetails() {
            document.getElementById('detailsModal').style.display = 'none';
        }

        window.onclick = function(event) {
            const modal = document.getElementById('detailsModal');
            if (event.target == modal) modal.style.display = 'none';
        }
    </script>
</body>
</html>
"""

    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(html)
    print(f"✓ HTML报告已生成: {output_file}")
    return output_file


if __name__ == '__main__':
    delivery_data = read_delivery_data('data/【周报】投后素材看板数据-代理-0731.csv')
    print(f"✓ 已读取投放数据: {len(delivery_data)} 条")

    print("\n正在分析数据...")
    agent_stats, global_analysis, agent_product_stats = analyze_by_agent(delivery_data)

    print("\n各代理商汇总:")
    for agent in sorted(agent_stats.keys(), key=lambda a: -agent_stats[a]['总消耗']):
        s = agent_stats[agent]
        print(f"  {agent}: 消耗¥{s['总消耗']:,.0f} | GMV¥{s['总成交GMV']:,.0f} | {s['总成交单量']}单 | {s['有消耗素材数']}条有消耗素材 | 平均{s['平均投放天数']:.1f}天")

    print("\n正在生成HTML报告...")
    generate_html(agent_stats, global_analysis, agent_product_stats, 'reports/代理商数据分析_0731.html')
    print("\n完成！")
