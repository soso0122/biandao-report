#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
图文库数据填充脚本

千川「图文库」导出偶发 bug：数值列（消耗/展示/点击/转化等）全部为 0，
需要用户从千川网页后台复制数据文本，本脚本把粘贴文本按素材id写回 CSV。

用法:
  1. 把用户粘贴的网页数据存到文本文件（每行: 名称|素材id|消耗|展示|点击|...）
  2. python3 scripts/fill_tuwen_data.py 数据文件.txt 目标CSV.csv

数据行格式（支持两种列结构）:
  A. 16列: 消耗|展示|点击|点击率|单价|CPM|转化|转化成本|转化率|深转数|深转成本|深转率|高潜成本|加好友|高潜|信息确认
  B. 15列: 消耗|展示|点击|点击率|单价|CPM|转化|转化成本|转化率|深转数|深转成本|深转率|加好友|高潜|信息确认

特性:
  - 按素材id（去tab/空白）精确匹配写回
  - 百分号自动去掉（点击率/转化率/深度转化率）
  - 增量：多次运行同一文件，已写回的行不会被重复覆盖（相同值幂等）
  - 输出进度：写回数/总行数、剩余0值行数
"""
import csv
import sys
from pathlib import Path

# 网页列名 → CSV 列名
COLS_A = ['消耗','展示数','点击数','点击率(%)','平均点击单价(元)','平均千次展现费用(元)',
          '转化数','转化成本','转化率(%)','深度转化次数','深度转化成本','深度转化率(%)',
          '高潜成交成本(计费时间)','回访-加为好友(计费时间)','回访-高潜成交(计费时间)','回访-信息确认(计费时间)']
COLS_B = ['消耗','展示数','点击数','点击率(%)','平均点击单价(元)','平均千次展现费用(元)',
          '转化数','转化成本','转化率(%)','深度转化次数','深度转化成本','深度转化率(%)',
          '回访-加为好友(计费时间)','回访-高潜成交(计费时间)','回访-信息确认(计费时间)']

PCT_COLS = ('点击率(%)', '转化率(%)', '深度转化率(%)')


def parse_data_file(path):
    """解析粘贴数据文本 → {素材id: {csv列: 值}}"""
    fix = {}
    with open(path, encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line or '|' not in line:
                continue
            parts = line.split('|')
            if len(parts) < 4:
                continue
            name, sid = parts[0], parts[1].strip()
            vals = [v.strip() for v in parts[2:]]
            # 判断列结构
            if len(vals) == 16:
                cols = COLS_A
            elif len(vals) == 15:
                cols = COLS_B
            else:
                print(f'⚠️ 跳过（列数 {len(vals)} 无法识别）: {name}')
                continue
            d = dict(zip(cols, vals))
            for c in PCT_COLS:
                d[c] = d[c].replace('%', '')
            fix[sid] = d
    return fix


def main():
    if len(sys.argv) < 3:
        print('用法: python3 scripts/fill_tuwen_data.py 数据文件.txt 目标CSV.csv')
        sys.exit(1)
    data_path = Path(sys.argv[1])
    csv_path = Path(sys.argv[2])
    if not data_path.exists():
        print(f'数据文件不存在: {data_path}')
        sys.exit(1)
    if not csv_path.exists():
        print(f'目标CSV不存在: {csv_path}')
        sys.exit(1)

    fix = parse_data_file(data_path)
    print(f'解析粘贴数据: {len(fix)} 条')

    with open(csv_path, encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        fields = reader.fieldnames
        rows = list(reader)

    matched = 0
    for r in rows:
        sid = (r.get('素材id') or '').strip().lstrip('\t')
        if sid in fix:
            d = fix[sid]
            for col, val in d.items():
                if col in r:  # 只在CSV存在的列写入
                    r[col] = val
            matched += 1

    with open(csv_path, 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction='ignore')
        w.writeheader()
        w.writerows(rows)

    # 汇总
    spend = sum(float(str(r.get('消耗') or '0').replace(',', '') or 0) for r in rows)
    conv = sum(float(str(r.get('转化数') or '0').replace(',', '') or 0) for r in rows)
    zero = sum(1 for r in rows if float(str(r.get('消耗') or '0').replace(',', '') or 0) == 0
               and float(str(r.get('展示数') or '0').replace(',', '') or 0) == 0)
    print(f'写回 {matched} / {len(rows)} 行')
    print(f'写回后汇总: 消耗 ¥{spend:,.2f} 转化 {conv:.0f}')
    print(f'剩余消耗+展示都为0的行: {zero}（应全是未投放素材）')


if __name__ == '__main__':
    main()
