#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
视频数据解析脚本 - 0626版本
格式: 文件命名,上传人,状态,编导,上传类型
"""

import re
import csv
from collections import defaultdict, Counter


# 账号到编导名称的映射
ACCOUNT_TO_NAME = {
    'duhaozheng': '浩正',
    'wangyadibj01': '雅迪',
    'weijiali': '嘉丽',
    'quminbj': '小敏',
    'wutingyubj': '婷玉',
    'jiazijinbj': '子衿',
    'hancg': '韩晨国'
}


def parse_video_list(text_data):
    """解析视频列表数据"""
    videos = []
    lines = text_data.strip().split('\n')
    current_video = {}

    for line in lines:
        line = line.strip()

        if not line or line in ['视频封面', '-', '全选当前页']:
            continue

        if '已选择' in line and '项' in line:
            continue

        # 检测视频标题
        if re.match(r'^\d{4}-', line):
            if current_video and '文件命名' in current_video:
                videos.append(current_video)
            current_video = {'文件命名': line}
            continue

        # 检测状态
        if line in ['未同步', '已同步', '已投放']:
            current_video['状态'] = line
            continue

        # 检测作者信息
        author_match = re.search(r'([^(（]+)[（(]([^)）]+)[）)]', line)
        if author_match:
            current_video['上传人'] = author_match.group(2)
            continue

        # 检测平台标记
        if '腾讯-首发素材' in line:
            if '平台标记' not in current_video:
                current_video['平台标记'] = line
            continue

    # 添加最后一个视频
    if current_video and '文件命名' in current_video:
        videos.append(current_video)

    return videos


def determine_upload_type(uploader, director):
    """
    判断上传类型
    - hancg: 拒审后二次上传
    - 编导自己的账号: 新素材
    """
    if uploader == 'hancg':
        return '拒审后二次上传'
    else:
        return '新素材'


def extract_director_from_filename(filename):
    """从文件名中提取编导名称"""
    # 文件名格式: 日期-产品-...-编导-...
    # 例如: 0521-状元笔记-自产-自产主--曲中雨-浩正---有-6

    # 常见编导名称列表
    directors = ['浩正', '雅迪', '嘉丽', '小敏', '婷玉', '子衿']

    for director in directors:
        if director in filename:
            return director

    return ''


def enrich_video_data(videos):
    """丰富视频数据，添加编导和上传类型"""
    for video in videos:
        filename = video.get('文件命名', '')
        uploader = video.get('上传人', '')

        # 提取编导
        director = extract_director_from_filename(filename)
        video['编导'] = director

        # 判断上传类型
        upload_type = determine_upload_type(uploader, director)
        video['上传类型'] = upload_type

    return videos


def export_to_csv(videos, output_file='output.csv'):
    """导出为CSV文件"""
    with open(output_file, 'w', encoding='utf-8', newline='') as f:
        writer = csv.writer(f)

        # 写入表头
        writer.writerow(['文件命名', '上传人', '状态', '编导', '上传类型'])

        # 写入数据
        for video in videos:
            filename = video.get('文件命名', '')
            uploader = video.get('上传人', '')
            status = video.get('状态', '')
            director = video.get('编导', '')
            upload_type = video.get('上传类型', '')

            writer.writerow([filename, uploader, status, director, upload_type])

    print(f"✓ 成功导出 {len(videos)} 条视频数据到: {output_file}")
    return len(videos)


def print_summary(videos):
    """打印数据摘要"""
    print("\n" + "="*70)
    print("数据摘要")
    print("="*70)
    print(f"总视频数: {len(videos)}")

    # 按编导统计
    director_count = Counter([v.get('编导', '未知') for v in videos])
    print("\n【按编导分类】")
    for director, count in sorted(director_count.items(), key=lambda x: x[1], reverse=True):
        if director:
            print(f"  {director:<10} {count:>3} 条")

    # 按上传类型统计
    upload_type_count = Counter([v.get('上传类型', '未知') for v in videos])
    print("\n【按上传类型分类】")
    for upload_type, count in sorted(upload_type_count.items()):
        pct = count / len(videos) * 100
        print(f"  {upload_type:<15} {count:>3} 条 ({pct:.1f}%)")

    # 按状态统计
    status_count = Counter([v.get('状态', '未知') for v in videos])
    print("\n【按状态分类】")
    for status, count in sorted(status_count.items()):
        pct = count / len(videos) * 100
        print(f"  {status:<10} {count:>3} 条 ({pct:.1f}%)")

    # 按编导分组统计上传类型
    print("\n【各编导上传类型详情】")
    print(f"{'编导':<10} {'新素材':<10} {'拒审后二次上传':<15} {'合计'}")
    print("-"*70)

    by_director = defaultdict(lambda: {'新素材': 0, '拒审后二次上传': 0})
    for video in videos:
        director = video.get('编导', '未知')
        upload_type = video.get('上传类型', '')
        by_director[director][upload_type] += 1

    for director in sorted(by_director.keys()):
        new_count = by_director[director]['新素材']
        reject_count = by_director[director]['拒审后二次上传']
        total = new_count + reject_count
        print(f"{director:<10} {new_count:<10} {reject_count:<15} {total}")

    print("="*70 + "\n")


if __name__ == '__main__':
    input_file = 'video_data_new_0626.txt'

    try:
        with open(input_file, 'r', encoding='utf-8') as f:
            text_data = f.read()
        print(f"✓ 已读取文件: {input_file}")
    except FileNotFoundError:
        print(f"✗ 未找到文件: {input_file}")
        exit(1)

    # 解析数据
    videos = parse_video_list(text_data)

    if not videos:
        print("✗ 未能解析到视频数据")
        exit(1)

    # 丰富数据
    videos = enrich_video_data(videos)

    # 显示摘要
    print_summary(videos)

    # 导出总CSV
    export_to_csv(videos, '上传数据_增强版_0626.csv')

    # 按编导分组导出
    print("\n按编导分组导出:")
    by_director = defaultdict(list)
    for video in videos:
        director = video.get('编导', '未知')
        if director and director != '未知':
            by_director[director].append(video)

    for director, director_videos in sorted(by_director.items()):
        filename = f'{director}_详细_0626.csv'
        export_to_csv(director_videos, filename)
        print(f"  {director}: {filename}")

    print("\n✓ 所有文件已生成完毕")
