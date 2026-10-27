#!/usr/bin/env python3
"""
Eagle素材库数据解析工具
用法：
1. 在Eagle页面选中所有素材（Ctrl+A 或 Cmd+A）
2. 复制（Ctrl+C 或 Cmd+C）
3. 运行此脚本
4. 粘贴复制的内容，按Ctrl+D（Mac）或Ctrl+Z（Windows）结束输入
"""

import re
import csv
from datetime import datetime
import sys

def parse_eagle_data(text):
    """解析Eagle复制的文本数据"""
    lines = text.strip().split('\n')
    materials = []
    
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        
        # 文件名：以日期开头（MMDD-）或者"6月4日"格式
        if re.match(r'^\d{4}-', line) or re.match(r'^\d+月\d+日', line):
            fileName = line
            
            # 下一行是状态
            if i + 1 < len(lines):
                status_line = lines[i + 1].strip()
                
                # 状态可能是"未同步"、"已同步"、"已投放"
                if status_line in ["未同步", "已同步", "已投放"]:
                    status = status_line
                else:
                    # 跳过非状态行
                    i += 1
                    continue
                
                # 向后查找上传人（格式：姓名（username））
                uploader = ""
                for j in range(i + 2, min(i + 6, len(lines))):
                    check_line = lines[j].strip()
                    if '（' in check_line and '）' in check_line:
                        match = re.search(r'（([^）]+)）', check_line)
                        if match:
                            uploader = match.group(1)
                            break
                
                materials.append({
                    'fileName': fileName,
                    'uploader': uploader,
                    'status': status
                })
        
        i += 1
    
    return materials

def remove_duplicates(materials):
    """去除重复的素材"""
    unique = {}
    for m in materials:
        fn = m['fileName']
        if fn not in unique:
            unique[fn] = m
    return list(unique.values())

def save_to_csv(materials, output_file):
    """保存为CSV文件"""
    with open(output_file, 'w', encoding='utf-8-sig', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['文件命名', '上传人', '状态'])
        
        for m in materials:
            writer.writerow([
                m['fileName'],
                m['uploader'],
                m['status']
            ])

def main():
    print("=" * 60)
    print("Eagle素材库数据解析工具".center(60))
    print("=" * 60)
    print("\n📋 使用说明：")
    print("1. 在Eagle页面全选素材（Ctrl+A 或 Cmd+A）")
    print("2. 复制（Ctrl+C 或 Cmd+C）")
    print("3. 将复制的内容粘贴到下方")
    print("4. Mac按Ctrl+D，Windows按Ctrl+Z后回车，结束输入\n")
    print("-" * 60)
    print("请粘贴Eagle复制的数据（输入完成后按Ctrl+D/Ctrl+Z）：\n")
    
    # 读取用户输入
    try:
        input_text = sys.stdin.read()
    except KeyboardInterrupt:
        print("\n\n❌ 操作已取消")
        return
    
    if not input_text.strip():
        print("\n❌ 未检测到输入数据")
        return
    
    print("\n⏳ 正在解析数据...")
    
    # 解析数据
    materials = parse_eagle_data(input_text)
    
    if not materials:
        print("❌ 未能解析出有效数据，请检查复制的内容格式")
        return
    
    print(f"✓ 解析到 {len(materials)} 条原始数据")
    
    # 去重
    unique_materials = remove_duplicates(materials)
    removed = len(materials) - len(unique_materials)
    
    if removed > 0:
        print(f"✓ 去除 {removed} 条重复数据")
    print(f"✓ 最终保留 {len(unique_materials)} 条唯一素材")
    
    # 生成文件名
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = f"Eagle素材库_{timestamp}.csv"
    
    # 保存CSV
    save_to_csv(unique_materials, output_file)
    
    print(f"\n✅ 数据已保存到：{output_file}")
    print(f"📊 包含 {len(unique_materials)} 条素材记录")
    
    # 显示前5条预览
    print("\n前5条数据预览：")
    for i, m in enumerate(unique_materials[:5], 1):
        name_preview = m['fileName'][:45] + '...' if len(m['fileName']) > 45 else m['fileName']
        print(f"  {i}. {name_preview}")
        print(f"     上传人: {m['uploader']}, 状态: {m['status']}")
    
    print("\n" + "=" * 60)
    print("处理完成！".center(60))
    print("=" * 60)

if __name__ == "__main__":
    main()
