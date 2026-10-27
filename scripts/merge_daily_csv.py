#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
合并 111 文件夹里的视频库/图文库 CSV，输出到 data/引导加微每日数据-MMDD.csv
同时合并过审文件（文件名含"-过审"），输出到 data/MMDD投放过审.csv
用法: python scripts/merge_daily_csv.py 0913
"""
import csv, sys
from pathlib import Path

SRC_DIR  = Path.home() / 'Desktop' / '111'
DATA_DIR = Path(__file__).parent.parent / 'data'

FIELD_MAP = {'素材名称': '视频名称', '预览链接': '视频链接'}

MASTER_FIELDS = [
    '素材id', '视频名称', '视频链接', '素材类型', '账户id',
    '投放情况', '审核建议', '素材评估', '关联在投单元数', '标签',
    '消耗', '展示数', '点击数', '点击率(%)', '平均点击单价(元)',
    '平均千次展现费用(元)', '转化数', '转化成本', '转化率(%)',
    '深度转化次数', '深度转化成本', '深度转化率(%)',
    '回访-加为好友(计费时间)', '回访-高潜成交(计费时间)', '回访-信息确认(计费时间)',
    # 2026-10-22 千川导出新增播放质量列（视频库/图文库都有；完播率列名带(%)）
    '平均单次播放时长', '完播率(%)', '3秒播放率', '5秒播放率',
    '25%进度播放率', '50%进度播放率', '75%进度播放率', '99%进度播放率',
]

AUDIT_FIELDS = [
    '素材id', '视频名称', '视频链接', '账户id',
    '投放情况', '审核建议', '素材评估', '创建时间',
]

def get_account_id(fname):
    """从文件名提取账户ID，兼容多种格式"""
    import re
    stem = Path(fname).stem
    # 去掉"-过审"后缀
    stem = stem.replace('-过审', '')
    if stem.startswith(('视频库_', '图文库_')):
        parts = stem.split('_')
        # 旧格式: 视频库_1869580643367964_时间 → parts[1] 是账户ID
        if len(parts) > 1 and re.fullmatch(r'\d+', parts[1]):
            return parts[1]
        # 新格式: 视频库__时间-N户 → 取末尾 -N户 作为账户标识
        m = re.search(r'-(\d+户)$', stem)
        if m:
            return m.group(1)
        return ''
    else:
        # 自投N户-视频库__ 格式
        return fname.split('-')[0]

def main():
    if len(sys.argv) < 2:
        print('用法: python scripts/merge_daily_csv.py MMDD')
        sys.exit(1)
    mmdd = sys.argv[1]

    all_files = sorted(f for f in SRC_DIR.glob('*.csv')
                       if f.name.startswith(('视频库', '图文库', '自投')))

    # 分类：过审文件 vs 投放文件
    audit_files = [f for f in all_files if '过审' in f.name]
    invest_files = [f for f in all_files if '过审' not in f.name]

    # ── 合并投放数据 ──────────────────────────────────────────────
    if not invest_files:
        print(f'找不到投放数据文件: {SRC_DIR}')
        sys.exit(1)

    all_rows = []
    for f in invest_files:
        mat_type   = '图文' if '图文库' in f.name else '视频'
        account_id = get_account_id(f.name)
        with open(f, encoding='utf-8-sig') as fh:
            for row in csv.DictReader(fh):
                mapped = {FIELD_MAP.get(k, k): v for k, v in row.items()}
                mapped['素材类型'] = mat_type
                # 账户id 加 tab 前缀 → Excel 打开不会转科学计数法
                mapped['账户id']   = '\t' + account_id if account_id else ''
                for col in MASTER_FIELDS:
                    if col not in mapped:
                        mapped[col] = ''
                all_rows.append(mapped)

    out_path = DATA_DIR / f'引导加微每日数据-{mmdd}.csv'
    with open(out_path, 'w', encoding='utf-8-sig', newline='') as fh:
        writer = csv.DictWriter(fh, fieldnames=MASTER_FIELDS, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(all_rows)
    print(f'投放数据: {len(invest_files)}个文件  {len(all_rows)}行 → {out_path.name}')

    # ── 合并过审数据 ──────────────────────────────────────────────
    if audit_files:
        audit_rows = []
        for f in audit_files:
            account_id = get_account_id(f.name)
            with open(f, encoding='utf-8-sig') as fh:
                for row in csv.DictReader(fh):
                    mapped = {FIELD_MAP.get(k, k): v for k, v in row.items()}
                    mapped['账户id'] = account_id
                    for col in AUDIT_FIELDS:
                        if col not in mapped:
                            mapped[col] = ''
                    audit_rows.append(mapped)

        audit_out = DATA_DIR / f'{mmdd}投放过审.csv'
        with open(audit_out, 'w', encoding='utf-8-sig', newline='') as fh:
            writer = csv.DictWriter(fh, fieldnames=AUDIT_FIELDS, extrasaction='ignore')
            writer.writeheader()
            writer.writerows(audit_rows)
        print(f'过审数据: {len(audit_files)}个文件  {len(audit_rows)}行 → {audit_out.name}')
    else:
        print('未找到过审文件（文件名需含"-过审"）')

if __name__ == '__main__':
    main()
