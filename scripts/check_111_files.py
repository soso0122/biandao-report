#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
检查 111 文件夹里的图文库文件是否需要填充

千川「图文库」导出偶发 bug：数值列全部为 0，需用户从网页复制数据回填。
本脚本扫描 111 里的图文库 CSV，报告哪些文件疑似需要填充。

用法:
  python3 scripts/check_111_files.py
"""
import csv
from pathlib import Path

SRC = Path.home() / 'Desktop' / '111'

# 2026-10-22 千川导出新增播放质量列（用户要求：缺少时提醒；完播率列名带(%)；播放数用户已取消）
NEW_PLAY_COLS = [
    '平均单次播放时长', '完播率(%)', '3秒播放率', '5秒播放率',
    '25%进度播放率', '50%进度播放率', '75%进度播放率', '99%进度播放率',
]


def check_file(fp):
    """返回 (总行数, 非零消耗行数, 非零展示行数)"""
    total = nz_spend = nz_imp = 0
    with open(fp, encoding='utf-8-sig') as f:
        for r in csv.DictReader(f):
            total += 1
            try:
                spend = float(str(r.get('消耗') or '0').replace(',', '') or 0)
                imp = float(str(r.get('展示数') or '0').replace(',', '') or 0)
            except Exception:
                continue
            if spend > 0:
                nz_spend += 1
            if imp > 0:
                nz_imp += 1
    return total, nz_spend, nz_imp


def check_new_cols(fp):
    """返回缺失的新播放质量列（空列表=齐全）"""
    with open(fp, encoding='utf-8-sig') as f:
        fieldnames = csv.DictReader(f).fieldnames or []
    missing = [c for c in NEW_PLAY_COLS if c not in fieldnames]
    return missing


def main():
    files = sorted(SRC.glob('图文库_*.csv')) + sorted(SRC.glob('图文库_*-需要填充.csv'))
    seen = set()
    print('检查 111 文件夹图文库文件:')
    print('=' * 80)
    for fp in files:
        if fp.name in seen:
            continue
        seen.add(fp.name)
        total, nz_spend, nz_imp = check_file(fp)
        # 判定：消耗/展示全部为 0 才是千川导出 bug（部分为0是未投放素材，正常）
        suspect = nz_spend == 0 and nz_imp == 0 and total > 0
        flag = '⚠️ 需要填充' if suspect else '✓ 正常'
        print(f'{flag} | {fp.name[:60]:62s} {total}行 非零消耗{nz_spend} 非零展示{nz_imp}')
        # 新播放质量列检查
        missing = check_new_cols(fp)
        if missing:
            print(f'   ⚠️ 缺新播放质量列: {", ".join(missing)}')
    print('=' * 80)
    print('提示: 标注「需要填充」的文件，等用户从千川网页复制数据后，')
    print('      用 scripts/fill_tuwen_data.py 写回。')

    # 视频库新列检查
    video_files = sorted(SRC.glob('视频库_*.csv'))
    if video_files:
        print()
        print('检查视频库新播放质量列:')
        for fp in video_files:
            missing = check_new_cols(fp)
            if missing:
                print(f'   ⚠️ {fp.name[:60]:62s} 缺: {", ".join(missing)}')
        if not any(check_new_cols(fp) for fp in video_files):
            print('   ✓ 所有视频库文件新列齐全')


if __name__ == '__main__':
    main()
