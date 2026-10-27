#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
视频数据解析脚本 - 按子矜格式输出
从截图文本中提取: 文件命名,上传人,状态
"""

import re
import csv


def parse_video_list(text_data):
    """
    解析视频列表数据
    返回格式: [(文件命名, 上传人, 状态), ...]
    """
    videos = []
    lines = text_data.strip().split('\n')

    current_video = {}

    for line in lines:
        line = line.strip()

        if not line or line in ['视频封面', '-', '全选当前页']:
            continue

        # 跳过选择数量提示
        if '已选择' in line and '项' in line:
            continue

        # 检测视频标题 (以日期开头的行: 0521-, 0520-, 等)
        if re.match(r'^\d{4}-', line):
            # 保存上一个视频
            if current_video and '文件命名' in current_video:
                videos.append(current_video)

            # 开始新视频
            current_video = {'文件命名': line}
            continue

        # 检测状态
        if line in ['未同步', '已同步', '已投放']:
            current_video['状态'] = line
            continue

        # 检测作者信息: 格式为 "姓名(账号)" 或 "姓名（账号）" (中英文括号)
        author_match = re.search(r'([^(（]+)[（(]([^)）]+)[）)]', line)
        if author_match:
            # 使用账号作为上传人
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


def export_to_csv(videos, output_file='浩正.csv'):
    """
    导出为CSV文件,格式参考子矜.csv
    格式: 文件命名,上传人,状态
    """
    with open(output_file, 'w', encoding='utf-8', newline='') as f:
        writer = csv.writer(f)

        # 写入表头
        writer.writerow(['文件命名', '上传人', '状态'])

        # 写入数据
        for video in videos:
            filename = video.get('文件命名', '')
            uploader = video.get('上传人', '')
            status = video.get('状态', '')

            writer.writerow([filename, uploader, status])

    print(f"✓ 成功导出 {len(videos)} 条视频数据到: {output_file}")
    return len(videos)


def print_summary(videos):
    """打印数据摘要"""
    print("\n" + "="*60)
    print("数据摘要")
    print("="*60)
    print(f"总视频数: {len(videos)}")

    # 统计状态分布
    status_count = {}
    uploader_count = {}

    for video in videos:
        status = video.get('状态', '未知')
        uploader = video.get('上传人', '未知')

        status_count[status] = status_count.get(status, 0) + 1
        uploader_count[uploader] = uploader_count.get(uploader, 0) + 1

    print("\n状态分布:")
    for status, count in sorted(status_count.items()):
        print(f"  {status}: {count} ({count/len(videos)*100:.1f}%)")

    print("\n上传人分布:")
    for uploader, count in sorted(uploader_count.items(), key=lambda x: x[1], reverse=True):
        print(f"  {uploader}: {count}")

    print("="*60 + "\n")


if __name__ == '__main__':
    # 从文件读取数据
    input_file = 'video_data.txt'

    try:
        with open(input_file, 'r', encoding='utf-8') as f:
            text_data = f.read()
        print(f"✓ 已读取文件: {input_file}")
    except FileNotFoundError:
        print(f"✗ 未找到文件: {input_file}")
        print("\n请创建 video_data.txt 文件并粘贴视频列表数据")
        print("格式参考您提供的截图内容")
        exit(1)

    # 解析数据
    videos = parse_video_list(text_data)

    if not videos:
        print("✗ 未能解析到视频数据,请检查输入格式")
        exit(1)

    # 显示摘要
    print_summary(videos)

    # 导出CSV
    export_to_csv(videos, '浩正.csv')

    # 显示前几条预览
    print("\n数据预览 (前10条):")
    print("-" * 60)
    print(f"{'文件命名':<50} {'上传人':<15} {'状态'}")
    print("-" * 60)
    for i, video in enumerate(videos[:10], 1):
        filename = video.get('文件命名', '')[:48]
        uploader = video.get('上传人', '')
        status = video.get('状态', '')
        print(f"{filename:<50} {uploader:<15} {status}")

    if len(videos) > 10:
        print(f"... 还有 {len(videos) - 10} 条数据")
