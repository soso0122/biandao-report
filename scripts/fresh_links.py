#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
千川视频链接刷新模块

千川导出的视频链接带时效签名，会过期。用户每次可重新导出视频库 CSV
（文件名匹配 data/视频库-新链接-*.csv），本模块从中构建
「素材id → 新链接」和「视频名称 → 新链接」映射，供各报告脚本刷新链接。

用法:
  from fresh_links import load_fresh_links
  fresh = load_fresh_links()   # {'by_id': {...}, 'by_name': {...}}
  link = fresh['by_id'].get(sid) or fresh['by_name'].get(name)
"""
import csv
from pathlib import Path

DATA_DIR = Path(__file__).parent.parent / 'data'


def load_fresh_links():
    by_id = {}
    by_name = {}
    for fp in sorted(DATA_DIR.glob('视频库-新链接-*.csv')):
        try:
            with open(fp, encoding='utf-8-sig') as fh:
                reader = csv.DictReader(fh)
                if reader.fieldnames and '视频链接' not in reader.fieldnames:
                    continue
                for r in reader:
                    sid = (r.get('素材id') or '').strip()
                    name = (r.get('视频名称') or '').strip()
                    link = (r.get('视频链接') or '').strip()
                    if len(link) < 10:
                        continue
                    if sid:
                        by_id[sid] = link
                    if name:
                        by_name[name] = link
                        # 兼容"推送视频_"前缀
                        if name.startswith('推送视频_'):
                            by_name.setdefault(name[len('推送视频_'):], link)
        except Exception as e:
            print(f'[fresh_links] 读取 {fp.name} 失败: {e}')
    return {'by_id': by_id, 'by_name': by_name}


if __name__ == '__main__':
    m = load_fresh_links()
    print(f'新链接映射: 按id {len(m["by_id"])} 条, 按名称 {len(m["by_name"])} 条')
