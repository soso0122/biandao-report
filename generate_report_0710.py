#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
编导数据分析与HTML报告生成 - 2026.07.10
"""

import csv
import json
from collections import defaultdict
from datetime import datetime


def read_upload_data(file_path):
    """读取上传数据"""
    data = []
    with open(file_path, 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        for row in reader:
            data.append(row)
    return data


def read_delivery_data(file_path):
    """读取投后看板数据，筛选：编导确认不为空 & 是否自产自投=是 & 是否混剪=否"""
    data = []
    with open(file_path, 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        for row in reader:
            if (row.get('编导确认', '').strip()
                    and row.get('是否自产自投', '').strip() == '是'
                    and row.get('是否混剪', '').strip() == '否'):
                data.append(row)
    return data


def normalize_director_name(name):
    """统一编导名称"""
    # 统一不同写法
    name_map = {
        '子矜': '子衿',
        '魏嘉丽': '嘉丽',
        '贾子矜': '子衿',
        '杜浩正': '浩正',
        '王雅迪': '雅迪',
        '曲敏': '小敏',
        '吴婷玉': '婷玉'
    }
    return name_map.get(name, name)


def analyze_by_director(upload_data, delivery_data):
    """按编导分析数据"""

    # 统计各编导的素材产出(去重)
    director_materials = defaultdict(set)  # 使用set去重
    director_stats = defaultdict(lambda: {
        '总上传数': 0,
        '新素材数': 0,
        '拒审后二次上传数': 0,
        '未同步': 0,
        '已同步': 0,
        '已投放': 0,
        '唯一素材数': 0,  # 去重后的素材数
    })

    # 统计各编导的产品成单情况
    director_product_orders = defaultdict(lambda: defaultdict(int))

    # 分析上传数据
    for row in upload_data:
        director = normalize_director_name(row.get('编导', ''))
        if not director or director == '':
            continue

        filename = row.get('文件命名', '')
        status = row.get('状态', '')
        upload_type = row.get('上传类型', '')

        # 添加到去重集合
        director_materials[director].add(filename)

        # 统计
        director_stats[director]['总上传数'] += 1

        if upload_type == '新素材':
            director_stats[director]['新素材数'] += 1
        elif upload_type == '拒审后二次上传':
            director_stats[director]['拒审后二次上传数'] += 1

        if status == '未同步':
            director_stats[director]['未同步'] += 1
        elif status == '已同步':
            director_stats[director]['已同步'] += 1
        elif status == '已投放':
            director_stats[director]['已投放'] += 1

    # 统计唯一素材数
    for director in director_materials:
        director_stats[director]['唯一素材数'] = len(director_materials[director])

    # 分析投放数据
    delivery_stats = defaultdict(lambda: {
        '总消耗': 0.0,
        '总成交GMV': 0.0,
        '总成交单量': 0,
        '有消耗素材数': 0,
        '有成交素材数': 0,
        '平均投放天数': 0.0,
        '素材详情': []
    })

    material_delivery = defaultdict(list)  # 素材名->投放记录列表
    # 素材维度的首次消耗时间和投放天数：(director, material_name) -> 值
    material_first_time = {}
    material_days = {}

    for row in delivery_data:
        director = normalize_director_name(row.get('编导确认', ''))
        if not director or director == '':
            continue

        material_name = row.get('素材名称', '')
        material_link = row.get('素材预览', '')
        product = row.get('素材投放产品', '')
        date = row.get('日期', '')
        first_time = row.get('首次消耗时间', '').strip()
        days_str = row.get('已上线投放天数', '').strip()

        key = director + '###' + material_name
        # 每条素材只记录一次首次消耗时间和投放天数
        if key not in material_first_time and first_time and first_time != '-':
            material_first_time[key] = first_time
        if key not in material_days and days_str and days_str != '-':
            try:
                material_days[key] = int(days_str)
            except ValueError:
                pass

        try:
            consume = float(row.get('消耗', 0) or 0)
            gmv = float(row.get('成交GMV', 0) or 0)
            orders = int(float(row.get('成交单量', 0) or 0))

            delivery_stats[director]['总消耗'] += consume
            delivery_stats[director]['总成交GMV'] += gmv
            delivery_stats[director]['总成交单量'] += orders

            # 统计产品成单
            if orders > 0 and product:
                director_product_orders[director][product] += orders

            # 记录素材投放详情
            material_delivery[key].append({
                '消耗': consume,
                'GMV': gmv,
                '单量': orders,
                '日期': date,
                '链接': material_link
            })

        except (ValueError, TypeError):
            pass

    # 统计有效素材
    for director in delivery_stats:
        materials_with_consume = set()
        materials_with_orders = set()
        days_list = []

        for key, records in material_delivery.items():
            if not key.startswith(director + '###'):
                continue
            material_name = key.split('###')[1]

            total_consume = sum(r['消耗'] for r in records)
            total_orders = sum(r['单量'] for r in records)
            total_gmv = sum(r['GMV'] for r in records)

            if total_consume > 0:
                materials_with_consume.add(material_name)
            if total_orders > 0:
                materials_with_orders.add(material_name)

            # 收集有消耗素材的投放天数用于计算平均值
            if total_consume > 0 and key in material_days:
                days_list.append(material_days[key])

            material_link = records[0].get('链接', '') if records else ''
            first_time = material_first_time.get(key, '')
            days = material_days.get(key, None)

            delivery_stats[director]['素材详情'].append({
                '素材名称': material_name,
                '总消耗': total_consume,
                '总GMV': total_gmv,
                '总单量': total_orders,
                '链接': material_link,
                '首次消耗时间': first_time,
                '投放天数': days
            })

        delivery_stats[director]['有消耗素材数'] = len(materials_with_consume)
        delivery_stats[director]['有成交素材数'] = len(materials_with_orders)
        delivery_stats[director]['平均投放天数'] = (
            sum(days_list) / len(days_list) if days_list else 0
        )

    # 按成交单量排序，获取Top 3素材
    for director in delivery_stats:
        sorted_materials = sorted(
            delivery_stats[director]['素材详情'],
            key=lambda x: x['总单量'],
            reverse=True
        )
        delivery_stats[director]['Top3素材'] = sorted_materials[:3]

    # 将产品成单数据添加到delivery_stats
    for director in delivery_stats:
        delivery_stats[director]['产品成单'] = dict(director_product_orders[director])

    # 全局素材分析（不区分编导）
    global_materials = {}  # material_name -> 汇总信息
    for key, records in material_delivery.items():
        director, material_name = key.split('###', 1)
        total_consume = sum(r['消耗'] for r in records)
        if total_consume <= 0:
            continue
        material_link = records[0].get('链接', '') if records else ''
        first_time = material_first_time.get(key, '')
        days = material_days.get(key, None)
        if material_name not in global_materials:
            global_materials[material_name] = {
                '素材名称': material_name,
                '编导': director,
                '总消耗': total_consume,
                '总GMV': sum(r['GMV'] for r in records),
                '总单量': sum(r['单量'] for r in records),
                '链接': material_link,
                '首次消耗时间': first_time,
                '投放天数': days,
            }
        else:
            global_materials[material_name]['总消耗'] += total_consume
            global_materials[material_name]['总GMV'] += sum(r['GMV'] for r in records)
            global_materials[material_name]['总单量'] += sum(r['单量'] for r in records)

    all_materials = list(global_materials.values())

    # 生命周期分桶
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

    # 本周新起量素材（首次消耗时间在 2026/7/4 - 2026/7/10）
    new_this_week = []
    for m in all_materials:
        ft = m['首次消耗时间']
        if not ft or ft == '-':
            continue
        try:
            from datetime import datetime
            dt = datetime.strptime(ft, '%Y/%m/%d')
            if datetime(2026, 7, 4) <= dt <= datetime(2026, 7, 10):
                new_this_week.append(m)
        except ValueError:
            pass
    new_this_week.sort(key=lambda x: x['总消耗'], reverse=True)

    global_analysis = {
        'lifecycle_buckets': {k: v for k, v in lifecycle_buckets.items()},
        'new_this_week': new_this_week,
        'total_with_consume': len(all_materials),
    }

    return director_stats, delivery_stats, director_materials, global_analysis


def generate_html(director_stats, delivery_stats, global_analysis, output_file='report.html'):
    """生成HTML报告"""

    # 排序编导列表
    directors = sorted(director_stats.keys())

    # 计算总计
    total_materials = sum(s['唯一素材数'] for s in director_stats.values())
    total_consume = sum(s['总消耗'] for s in delivery_stats.values())
    total_gmv = sum(s['总成交GMV'] for s in delivery_stats.values())
    total_orders = sum(s['总成交单量'] for s in delivery_stats.values())

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>编导数据分析报告 - 2026.07.10</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}

        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            padding: 20px;
            color: #333;
        }}

        .container {{
            max-width: 1400px;
            margin: 0 auto;
        }}

        h1 {{
            text-align: center;
            color: white;
            margin-bottom: 10px;
            font-size: 36px;
            text-shadow: 2px 2px 4px rgba(0,0,0,0.2);
        }}

        .subtitle {{
            text-align: center;
            color: rgba(255,255,255,0.9);
            margin-bottom: 30px;
            font-size: 14px;
        }}

        .section-title {{
            color: white;
            font-size: 24px;
            margin: 40px 0 20px 0;
            padding-left: 10px;
            border-left: 4px solid white;
        }}

        .summary-cards {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }}

        .summary-card {{
            background: white;
            border-radius: 15px;
            padding: 25px;
            box-shadow: 0 10px 30px rgba(0,0,0,0.1);
            transition: transform 0.3s ease;
        }}

        .summary-card:hover {{
            transform: translateY(-5px);
        }}

        .summary-card h3 {{
            font-size: 13px;
            color: #666;
            margin-bottom: 10px;
            letter-spacing: 0.5px;
        }}

        .summary-card .value {{
            font-size: 32px;
            font-weight: bold;
            color: #667eea;
            margin-bottom: 5px;
        }}

        .summary-card .label {{
            font-size: 12px;
            color: #999;
        }}

        .director-cards {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(350px, 1fr));
            gap: 25px;
            margin-bottom: 40px;
        }}

        .director-card {{
            background: white;
            border-radius: 15px;
            padding: 25px;
            box-shadow: 0 10px 30px rgba(0,0,0,0.1);
        }}

        .director-card h2 {{
            font-size: 24px;
            color: #667eea;
            margin-bottom: 5px;
        }}

        .card-subtitle {{
            color: #999;
            font-size: 12px;
            margin-bottom: 20px;
            padding-bottom: 15px;
            border-bottom: 3px solid #667eea;
        }}

        .data-section {{
            margin-bottom: 20px;
        }}

        .section-header {{
            font-size: 15px;
            font-weight: bold;
            color: #555;
            margin-bottom: 10px;
            background: #f8f9ff;
            padding: 8px 12px;
            border-radius: 6px;
            border-left: 3px solid #667eea;
        }}

        .stat-row {{
            display: flex;
            justify-content: space-between;
            padding: 10px 0;
            border-bottom: 1px solid #f5f5f5;
        }}

        .stat-row:last-child {{
            border-bottom: none;
        }}

        .stat-label {{
            color: #666;
            font-size: 14px;
        }}

        .stat-value {{
            font-weight: bold;
            color: #333;
            font-size: 16px;
        }}

        .stat-value.highlight {{
            color: #667eea;
            font-size: 18px;
        }}

        .charts-section {{
            background: white;
            border-radius: 15px;
            padding: 30px;
            margin-bottom: 30px;
            box-shadow: 0 10px 30px rgba(0,0,0,0.1);
        }}

        .charts-section h2 {{
            font-size: 24px;
            color: #667eea;
            margin-bottom: 30px;
            text-align: center;
        }}

        .charts-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(400px, 1fr));
            gap: 30px;
        }}

        .chart-container {{
            position: relative;
            height: 300px;
        }}

        .table-section {{
            background: white;
            border-radius: 15px;
            padding: 30px;
            box-shadow: 0 10px 30px rgba(0,0,0,0.1);
            overflow-x: auto;
        }}

        .table-section h2 {{
            font-size: 24px;
            color: #667eea;
            margin-bottom: 20px;
        }}

        table {{
            width: 100%;
            border-collapse: collapse;
            font-size: 14px;
        }}

        th {{
            background: #667eea;
            color: white;
            padding: 15px;
            text-align: left;
            font-weight: 600;
            position: sticky;
            top: 0;
        }}

        td {{
            padding: 12px 15px;
            border-bottom: 1px solid #f0f0f0;
        }}

        tr:hover {{
            background: #f8f9ff;
        }}

        .badge {{
            display: inline-block;
            padding: 4px 12px;
            border-radius: 12px;
            font-size: 12px;
            font-weight: 600;
        }}

        .badge-success {{
            background: #d4edda;
            color: #155724;
        }}

        .badge-warning {{
            background: #fff3cd;
            color: #856404;
        }}

        .badge-danger {{
            background: #f8d7da;
            color: #721c24;
        }}

        .details-btn {{
            background: #667eea;
            color: white;
            border: none;
            padding: 8px 16px;
            border-radius: 8px;
            cursor: pointer;
            font-size: 12px;
            transition: background 0.3s;
        }}

        .details-btn:hover {{
            background: #5568d3;
        }}

        .top3-section {{
            margin-top: 20px;
            padding-top: 20px;
            border-top: 2px solid #f0f0f0;
        }}

        .top3-title {{
            font-size: 14px;
            font-weight: bold;
            color: #667eea;
            margin-bottom: 12px;
        }}

        .top3-item {{
            margin-bottom: 10px;
            padding: 8px;
            background: #f8f9ff;
            border-radius: 6px;
            font-size: 13px;
        }}

        .top3-rank {{
            display: inline-block;
            width: 22px;
            height: 22px;
            line-height: 22px;
            text-align: center;
            background: #667eea;
            color: white;
            border-radius: 50%;
            font-weight: bold;
            font-size: 12px;
            margin-right: 8px;
        }}

        .top3-name {{
            color: #333;
            margin-bottom: 4px;
        }}

        .top3-stats {{
            color: #666;
            font-size: 12px;
            margin-left: 30px;
        }}

        .top3-link {{
            color: #667eea;
            text-decoration: none;
            font-size: 12px;
            margin-left: 30px;
            display: inline-block;
            margin-top: 4px;
        }}

        .top3-link:hover {{
            text-decoration: underline;
        }}

        .product-orders {{
            margin-top: 10px;
            padding: 10px;
            background: #f8f9ff;
            border-radius: 6px;
            font-size: 13px;
        }}

        .product-orders-title {{
            font-weight: bold;
            color: #667eea;
            margin-bottom: 6px;
        }}

        .product-item {{
            padding: 4px 0;
            color: #666;
        }}

        .product-name {{
            color: #333;
            font-weight: 500;
        }}

        .product-count {{
            color: #667eea;
            font-weight: bold;
        }}

        .lifecycle-section {{
            background: white;
            border-radius: 15px;
            padding: 30px;
            margin-bottom: 30px;
            box-shadow: 0 10px 30px rgba(0,0,0,0.1);
        }}

        .lifecycle-section h2 {{
            font-size: 24px;
            color: #667eea;
            margin-bottom: 20px;
        }}

        .lifecycle-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
            gap: 15px;
            margin-bottom: 25px;
        }}

        .lifecycle-bucket {{
            border: 2px solid #e8eaff;
            border-radius: 10px;
            padding: 15px;
            cursor: pointer;
            transition: all 0.2s;
        }}

        .lifecycle-bucket:hover {{
            border-color: #667eea;
            background: #f8f9ff;
        }}

        .lifecycle-bucket.active {{
            border-color: #667eea;
            background: #f0f2ff;
        }}

        .lifecycle-bucket-label {{
            font-size: 13px;
            color: #888;
            margin-bottom: 6px;
        }}

        .lifecycle-bucket-count {{
            font-size: 28px;
            font-weight: bold;
            color: #667eea;
        }}

        .lifecycle-bucket-sub {{
            font-size: 12px;
            color: #aaa;
            margin-top: 4px;
        }}

        .lifecycle-chart-row {{
            display: flex;
            gap: 30px;
            align-items: flex-start;
        }}

        .lifecycle-chart-wrap {{
            flex: 0 0 280px;
            height: 220px;
            position: relative;
        }}

        .lifecycle-detail {{
            flex: 1;
        }}

        .lifecycle-detail-title {{
            font-size: 14px;
            font-weight: bold;
            color: #555;
            margin-bottom: 10px;
        }}

        .material-list {{
            max-height: 280px;
            overflow-y: auto;
        }}

        .material-list-item {{
            display: flex;
            align-items: center;
            justify-content: space-between;
            padding: 8px 10px;
            border-bottom: 1px solid #f5f5f5;
            font-size: 13px;
            gap: 8px;
        }}

        .material-list-item:last-child {{
            border-bottom: none;
        }}

        .material-list-name {{
            color: #333;
            flex: 1;
            min-width: 0;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
        }}

        .material-list-meta {{
            color: #999;
            font-size: 12px;
            white-space: nowrap;
        }}

        .material-list-link {{
            color: #667eea;
            text-decoration: none;
            font-size: 12px;
            white-space: nowrap;
            flex-shrink: 0;
        }}

        .material-list-link:hover {{
            text-decoration: underline;
        }}

        .new-week-section {{
            margin-top: 25px;
            padding-top: 20px;
            border-top: 2px solid #f0f0f0;
        }}

        .new-week-title {{
            font-size: 16px;
            font-weight: bold;
            color: #333;
            margin-bottom: 5px;
        }}

        .new-week-sub {{
            font-size: 13px;
            color: #999;
            margin-bottom: 15px;
        }}

        .new-week-badge {{
            display: inline-block;
            background: #43e97b;
            color: white;
            padding: 2px 8px;
            border-radius: 10px;
            font-size: 12px;
            font-weight: bold;
            margin-left: 6px;
        }}

        .modal {{
            display: none;
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background: rgba(0,0,0,0.5);
            z-index: 1000;
            padding: 20px;
            overflow-y: auto;
        }}

        .modal-content {{
            background: white;
            max-width: 900px;
            margin: 50px auto;
            border-radius: 15px;
            padding: 30px;
            position: relative;
        }}

        .modal-close {{
            position: absolute;
            top: 20px;
            right: 20px;
            font-size: 30px;
            cursor: pointer;
            color: #999;
        }}

        .modal-close:hover {{
            color: #333;
        }}

        .timestamp {{
            text-align: center;
            color: white;
            margin-top: 30px;
            font-size: 14px;
            opacity: 0.8;
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>📊 编导数据分析报告</h1>
        <div class="subtitle">数据日期: 2026年7月10日</div>

        <!-- 总览卡片 -->
        <h2 class="section-title">📈 数据总览</h2>
        <div class="summary-cards">
            <div class="summary-card">
                <h3>总上传素材数</h3>
                <div class="value">{total_materials}</div>
                <div class="label">条(去重后)</div>
            </div>
            <div class="summary-card">
                <h3>投放总消耗</h3>
                <div class="value">¥{total_consume:,.0f}</div>
                <div class="label">元</div>
            </div>
            <div class="summary-card">
                <h3>投放总GMV</h3>
                <div class="value">¥{total_gmv:,.0f}</div>
                <div class="label">元</div>
            </div>
            <div class="summary-card">
                <h3>投放总订单</h3>
                <div class="value">{total_orders}</div>
                <div class="label">单</div>
            </div>
        </div>

        <!-- 素材生命周期分析 -->
        <h2 class="section-title">🔍 素材投放分析</h2>
        <div class="lifecycle-section">
            <h2>素材生命周期 & 本周新起量</h2>

            <!-- 分桶按钮 -->
            <div class="lifecycle-grid">
"""
    buckets = global_analysis['lifecycle_buckets']
    bucket_keys = ['1-7天', '8-14天', '15-30天', '30天以上']
    bucket_colors = ['#43e97b', '#4facfe', '#667eea', '#fa709a']
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

            <!-- 图表 + 素材列表 -->
            <div class="lifecycle-chart-row">
                <div class="lifecycle-chart-wrap">
                    <canvas id="lifecycleChart"></canvas>
                </div>
                <div class="lifecycle-detail">
                    <div class="lifecycle-detail-title" id="bucketDetailTitle">点击上方分桶查看素材列表</div>
                    <div class="material-list" id="bucketMaterialList"></div>
                </div>
            </div>
"""

    # 本周新起量
    new_this_week = global_analysis['new_this_week']
    html += f"""
            <!-- 本周新起量 -->
            <div class="new-week-section">
                <div class="new-week-title">
                    本周新起量素材
                    <span class="new-week-badge">{len(new_this_week)} 条</span>
                </div>
                <div class="new-week-sub">首次消耗时间在 7月4日 - 7月10日，共 {len(new_this_week)} 条素材本周开始产生消耗（占有消耗素材 {len(new_this_week)/total_with_consume*100:.0f}%）</div>
                <div class="material-list">
"""
    for m in new_this_week:
        link = m.get('链接', '')
        link_html = f'<a href="{link}" target="_blank" class="material-list-link">🎬 查看</a>' if link else ''
        html += f"""
                    <div class="material-list-item">
                        <span class="material-list-name" title="{m['素材名称']}">{m['素材名称']}</span>
                        <span class="material-list-meta">{m['编导']} | 首消 {m['首次消耗时间']} | ¥{m['总消耗']:,.0f} | {m['总单量']}单</span>
                        {link_html}
                    </div>
"""
    html += """
                </div>
            </div>
        </div>

        <!-- 各编导数据卡片 -->
        <h2 class="section-title">👥 各编导详细数据</h2>
        <div class="director-cards">
"""

    # 生成各编导卡片
    for director in directors:
        upload_s = director_stats[director]
        delivery_s = delivery_stats.get(director, {})

        reject_rate = (upload_s['拒审后二次上传数'] / upload_s['总上传数'] * 100
                      if upload_s['总上传数'] > 0 else 0)

        html += f"""
            <div class="director-card">
                <h2>{director}</h2>
                <div class="card-subtitle">数据概览</div>

                <!-- 素材产出部分 -->
                <div class="data-section">
                    <div class="section-header">📤 素材产出</div>
                    <div class="stat-row">
                        <span class="stat-label">唯一素材数(去重后)</span>
                        <span class="stat-value highlight">{upload_s['唯一素材数']} 条</span>
                    </div>
                    <div class="stat-row">
                        <span class="stat-label">新素材 / 拒审二传</span>
                        <span class="stat-value">{upload_s['新素材数']} / {upload_s['拒审后二次上传数']}</span>
                    </div>
                    <div class="stat-row">
                        <span class="stat-label">状态分布</span>
                        <span class="stat-value">未同步{upload_s['未同步']} | 已同步{upload_s['已同步']} | 已投放{upload_s['已投放']}</span>
                    </div>
                </div>

                <!-- 投放效果部分 -->
                <div class="data-section">
                    <div class="section-header">📊 投放效果</div>
                    <div class="stat-row">
                        <span class="stat-label">总消耗</span>
                        <span class="stat-value">¥{delivery_s.get('总消耗', 0):,.2f}</span>
                    </div>
                    <div class="stat-row">
                        <span class="stat-label">总GMV</span>
                        <span class="stat-value">¥{delivery_s.get('总成交GMV', 0):,.2f}</span>
                    </div>
                    <div class="stat-row">
                        <span class="stat-label">总订单</span>
                        <span class="stat-value">{delivery_s.get('总成交单量', 0)} 单</span>
                    </div>
                    <div class="stat-row">
                        <span class="stat-label">有消耗素材 / 有成交素材</span>
                        <span class="stat-value">{delivery_s.get('有消耗素材数', 0)} / {delivery_s.get('有成交素材数', 0)}</span>
                    </div>
                    <div class="stat-row">
                        <span class="stat-label">平均投放天数</span>
                        <span class="stat-value">{delivery_s.get('平均投放天数', 0):.1f} 天</span>
                    </div>
"""

        # 添加产品成单明细
        product_orders = delivery_s.get('产品成单', {})
        if product_orders:
            html += """
                    <div class="product-orders">
                        <div class="product-orders-title">📦 产品成单明细</div>
"""
            # 按成单数排序
            sorted_products = sorted(product_orders.items(), key=lambda x: x[1], reverse=True)
            for product, orders in sorted_products:
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

        # 添加Top 3素材展示
        top3_materials = delivery_s.get('Top3素材', [])
        if top3_materials:
            html += """
                <div class="top3-section">
                    <div class="top3-title">🏆 成交单量Top 3素材</div>
"""
            for idx, material in enumerate(top3_materials, 1):
                material_name = material['素材名称']
                total_orders = material['总单量']
                total_gmv = material['总GMV']
                material_link = material.get('链接', '')
                first_time = material.get('首次消耗时间', '')
                days = material.get('投放天数', None)

                first_time_str = f' | 首消 {first_time}' if first_time else ''
                days_str = f' | 已投 {days} 天' if days is not None else ''

                html += f"""
                    <div class="top3-item">
                        <div class="top3-name">
                            <span class="top3-rank">{idx}</span>{material_name}
                        </div>
                        <div class="top3-stats">成交 {total_orders} 单 | GMV ¥{total_gmv:,.2f}{first_time_str}{days_str}</div>
"""
                if material_link:
                    html += f"""
                        <a href="{material_link}" target="_blank" class="top3-link">🎬 查看素材</a>
"""
                html += """
                    </div>
"""
            html += """
                </div>
"""

        html += f"""
                <button class="details-btn" onclick="showDetails('{director}')">查看Top 20详情</button>
            </div>
"""

    html += """
        </div>

        <!-- 数据可视化图表 -->
        <div class="charts-section">
            <h2>📈 数据可视化</h2>
            <div class="charts-grid">
                <div class="chart-container">
                    <canvas id="materialsChart"></canvas>
                </div>
                <div class="chart-container">
                    <canvas id="consumeChart"></canvas>
                </div>
                <div class="chart-container">
                    <canvas id="gmvChart"></canvas>
                </div>
                <div class="chart-container">
                    <canvas id="ordersChart"></canvas>
                </div>
            </div>
        </div>

        <!-- 详细数据表格 -->
        <div class="table-section">
            <h2>📋 详细对比数据</h2>
            <table>
                <thead>
                    <tr>
                        <th>编导</th>
                        <th>唯一素材数</th>
                        <th>总消耗</th>
                        <th>总GMV</th>
                        <th>总订单</th>
                        <th>有消耗素材</th>
                        <th>有成交素材</th>
                        <th>平均投放天数</th>
                    </tr>
                </thead>
                <tbody>
"""

    # 生成表格行
    for director in directors:
        upload_s = director_stats[director]
        delivery_s = delivery_stats.get(director, {})

        html += f"""
                    <tr>
                        <td><strong>{director}</strong></td>
                        <td>{upload_s['唯一素材数']}</td>
                        <td>¥{delivery_s.get('总消耗', 0):,.2f}</td>
                        <td>¥{delivery_s.get('总成交GMV', 0):,.2f}</td>
                        <td>{delivery_s.get('总成交单量', 0)}</td>
                        <td>{delivery_s.get('有消耗素材数', 0)}</td>
                        <td>{delivery_s.get('有成交素材数', 0)}</td>
                        <td>{delivery_s.get('平均投放天数', 0):.1f} 天</td>
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
                    '编导': m['编导'],
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
        const bucketColors = ['#43e97b', '#4facfe', '#667eea', '#fa709a'];
        const bucketKeys = ['1-7天', '8-14天', '15-30天', '30天以上'];
        let currentBucket = null;

        // 生命周期环形图
        new Chart(document.getElementById('lifecycleChart'), {
            type: 'doughnut',
            data: {
                labels: bucketKeys,
                datasets: [{
                    data: bucketKeys.map(k => lifecycleBuckets[k].length),
                    backgroundColor: bucketColors,
                    borderWidth: 2,
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { position: 'bottom', labels: { font: { size: 12 } } },
                    title: { display: true, text: '素材生命周期分布' }
                }
            }
        });

        function selectBucket(idx) {
            const bk = bucketKeys[idx];
            // 高亮选中
            document.querySelectorAll('.lifecycle-bucket').forEach((el, i) => {
                el.classList.toggle('active', i === idx);
            });
            currentBucket = bk;
            const items = lifecycleBuckets[bk];
            document.getElementById('bucketDetailTitle').textContent =
                bk + ' 的素材（共 ' + items.length + ' 条，按消耗排序）';
            const list = document.getElementById('bucketMaterialList');
            if (items.length === 0) {
                list.innerHTML = '<div style="color:#aaa;padding:12px">暂无数据</div>';
                return;
            }
            list.innerHTML = items.map(m => {
                const linkHtml = m.链接
                    ? '<a href="' + m.链接 + '" target="_blank" class="material-list-link">🎬 查看</a>'
                    : '';
                return '<div class="material-list-item">' +
                    '<span class="material-list-name" title="' + m.素材名称 + '">' + m.素材名称 + '</span>' +
                    '<span class="material-list-meta">' + m.编导 + ' | ' + (m.首次消耗时间 || '-') + ' | ¥' + m.总消耗.toFixed(0) + ' | ' + m.总单量 + '单</span>' +
                    linkHtml +
                    '</div>';
            }).join('');
        }

        // 准备数据
        const directors = """ + json.dumps(directors) + """;
        const materialsData = """ + json.dumps([director_stats[d]['唯一素材数'] for d in directors]) + """;
        const consumeData = """ + json.dumps([delivery_stats.get(d, {}).get('总消耗', 0) for d in directors]) + """;
        const gmvData = """ + json.dumps([delivery_stats.get(d, {}).get('总成交GMV', 0) for d in directors]) + """;
        const ordersData = """ + json.dumps([delivery_stats.get(d, {}).get('总成交单量', 0) for d in directors]) + """;

        const chartColors = [
            '#667eea', '#764ba2', '#f093fb', '#4facfe',
            '#43e97b', '#fa709a', '#fee140', '#30cfd0'
        ];

        // 素材数量图表
        new Chart(document.getElementById('materialsChart'), {
            type: 'bar',
            data: {
                labels: directors,
                datasets: [{
                    label: '唯一素材数',
                    data: materialsData,
                    backgroundColor: chartColors,
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    title: {
                        display: true,
                        text: '各编导素材产出对比'
                    }
                }
            }
        });

        // 消耗图表
        new Chart(document.getElementById('consumeChart'), {
            type: 'bar',
            data: {
                labels: directors,
                datasets: [{
                    label: '总消耗(元)',
                    data: consumeData,
                    backgroundColor: chartColors,
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    title: {
                        display: true,
                        text: '各编导消耗对比'
                    }
                }
            }
        });

        // GMV图表
        new Chart(document.getElementById('gmvChart'), {
            type: 'bar',
            data: {
                labels: directors,
                datasets: [{
                    label: '总GMV(元)',
                    data: gmvData,
                    backgroundColor: chartColors,
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    title: {
                        display: true,
                        text: '各编导GMV对比'
                    }
                }
            }
        });

        // 订单数图表
        new Chart(document.getElementById('ordersChart'), {
            type: 'bar',
            data: {
                labels: directors,
                datasets: [{
                    label: '总订单数',
                    data: ordersData,
                    backgroundColor: chartColors,
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    title: {
                        display: true,
                        text: '各编导订单数对比'
                    }
                }
            }
        });

        // 素材详情数据 (按消耗排序)
        const materialDetails = """ + json.dumps({
            d: sorted(
                delivery_stats.get(d, {}).get('素材详情', []),
                key=lambda x: x['总消耗'],
                reverse=True
            )[:20]  # 按消耗降序，显示前20条
            for d in directors
        }) + """;

        function showDetails(director) {
            const modal = document.getElementById('detailsModal');
            const modalBody = document.getElementById('modalBody');

            const details = materialDetails[director] || [];

            let html = '<h2>' + director + ' - 素材详情(前20条)</h2>';
            html += '<table><thead><tr>';
            html += '<th>素材名称</th><th>首次消耗时间</th><th>已投放天数</th><th>总消耗</th><th>总GMV</th><th>总单量</th>';
            html += '</tr></thead><tbody>';

            details.forEach(item => {
                html += '<tr>';
                html += '<td>' + item.素材名称 + '</td>';
                html += '<td>' + (item.首次消耗时间 || '-') + '</td>';
                html += '<td>' + (item.投放天数 != null ? item.投放天数 + ' 天' : '-') + '</td>';
                html += '<td>¥' + item.总消耗.toFixed(2) + '</td>';
                html += '<td>¥' + item.总GMV.toFixed(2) + '</td>';
                html += '<td>' + item.总单量 + '</td>';
                html += '</tr>';
            });

            html += '</tbody></table>';

            modalBody.innerHTML = html;
            modal.style.display = 'block';
        }

        function closeDetails() {
            document.getElementById('detailsModal').style.display = 'none';
        }

        // 点击模态框外部关闭
        window.onclick = function(event) {
            const modal = document.getElementById('detailsModal');
            if (event.target == modal) {
                modal.style.display = 'none';
            }
        }
    </script>
</body>
</html>
"""

    # 写入文件
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(html)

    print(f"✓ HTML报告已生成: {output_file}")
    return output_file


if __name__ == '__main__':
    # 读取数据
    upload_data = read_upload_data('上传数据_增强版_0710.csv')
    delivery_data = read_delivery_data('【周报】投后素材看板数据-0710.csv')

    print(f"✓ 已读取上传数据: {len(upload_data)} 条")
    print(f"✓ 已读取投放数据: {len(delivery_data)} 条")

    # 分析数据
    print("\n正在分析数据...")
    director_stats, delivery_stats, director_materials, global_analysis = analyze_by_director(upload_data, delivery_data)

    # 生成HTML
    print("\n正在生成HTML报告...")
    output_file = '编导数据分析报告_0710.html'
    generate_html(director_stats, delivery_stats, global_analysis, output_file)

    print("\n" + "="*70)
    print("数据分析完成!")
    print("="*70)

    # 输出摘要
    print("\n各编导素材产出(去重后):")
    for director in sorted(director_stats.keys()):
        unique_count = director_stats[director]['唯一素材数']
        total_count = director_stats[director]['总上传数']
        print(f"  {director}: {unique_count} 条(总上传 {total_count} 次)")
