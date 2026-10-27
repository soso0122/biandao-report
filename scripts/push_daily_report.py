#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
截图并推送引导素材日报到企微
用法:
  python scripts/push_daily_report.py                  # 截图，等待确认
  python scripts/push_daily_report.py --send            # 截图 + 发送企微
"""
import sys, re, json, base64, urllib.request
from pathlib import Path

WEBHOOK = 'https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=9abcd213-0acf-4ce1-993a-ec4ebd82a96a'
REPORTS_DIR = Path(__file__).parent.parent / 'reports'
SCREENSHOT_PATH = Path(__file__).parent.parent / 'reports' / 'snapshot_latest.png'

def get_latest_report():
    files = sorted(REPORTS_DIR.glob('引导素材每日分析_*.html'))
    return files[-1] if files else None

def extract_stats(html_path):
    """从 HTML 里提取 KPI 数据用于文字摘要"""
    with open(html_path, encoding='utf-8') as f:
        content = f.read()
    def get(pattern):
        m = re.search(pattern, content)
        return m.group(1) if m else '—'
    mmdd = re.search(r'引导素材每日分析_(\d{4})\.html', html_path.name)
    date = f"{mmdd.group(1)[:2]}/{mmdd.group(1)[2:]}" if mmdd else ''
    spend    = get(r'id="kpi-spend"[^>]*>([^<]+)<')
    imp      = get(r'id="kpi-imp"[^>]*>([^<]+)<')
    ctr      = get(r'id="kpi-ctr"[^>]*>([^<]+)<')
    conv     = get(r'id="kpi-conv"[^>]*>([^<]+)<')
    cpa      = get(r'id="kpi-cpa"[^>]*>([^<]+)<')
    gaoquan  = get(r'id="kpi-gaoquan"[^>]*>([^<]+)<')
    deeprate = get(r'id="kpi-deeprate"[^>]*>([^<]+)<')
    return date, spend, imp, ctr, conv, cpa, gaoquan, deeprate

def take_screenshot(html_path, out_path):
    """用 playwright 截图 header + KPI + 趋势图区域"""
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={'width': 1440, 'height': 4000})
        page.goto(f'file://{html_path.resolve()}')
        # 等待 KPI 和卡片渲染完成
        page.wait_for_selector('#kpi-spend', timeout=15000)
        page.wait_for_selector('#typeCardsRow', timeout=10000)
        page.wait_for_timeout(2500)
        # 自动计算截到过审率区域结束的高度
        height = page.evaluate('''() => {
            const el = document.getElementById('auditTagCardsRow') || document.getElementById('auditCardsRow') || document.getElementById('typeCardsRow');
            if (!el) return 2000;
            const rect = el.getBoundingClientRect();
            return Math.ceil(rect.bottom + window.scrollY) + 60;
        }''')
        height = min(int(height), 4000)
        page.screenshot(path=str(out_path), clip={'x': 0, 'y': 0, 'width': 1440, 'height': height})
        browser.close()
    print(f'截图已保存: {out_path}')

def send_image(img_path):
    """发图片到企微"""
    with open(img_path, 'rb') as f:
        img_data = f.read()
    import hashlib
    md5 = hashlib.md5(img_data).hexdigest()
    b64 = base64.b64encode(img_data).decode()
    payload = {'msgtype': 'image', 'image': {'base64': b64, 'md5': md5}}
    req = urllib.request.Request(
        WEBHOOK, data=json.dumps(payload).encode(),
        headers={'Content-Type': 'application/json'}
    )
    resp = urllib.request.urlopen(req, timeout=10)
    return json.loads(resp.read())

def send_text(text):
    """发文字到企微"""
    payload = {'msgtype': 'text', 'text': {'content': text}}
    req = urllib.request.Request(
        WEBHOOK, data=json.dumps(payload).encode(),
        headers={'Content-Type': 'application/json'}
    )
    resp = urllib.request.urlopen(req, timeout=10)
    return json.loads(resp.read())

def main():
    send_mode = '--send' in sys.argv

    report = get_latest_report()
    if not report:
        print('找不到报告文件')
        sys.exit(1)

    print(f'报告: {report.name}')

    # 截图
    take_screenshot(report, SCREENSHOT_PATH)

    # 提取摘要
    date, spend, imp, ctr, conv, cpa, gaoquan, deeprate = extract_stats(report)

    summary = (
        f"📊 引导素材日报 {date}\n"
        f"消耗 {spend}  展示 {imp}\n"
        f"点击率 {ctr}  转化数 {conv}\n"
        f"平均CPA {cpa}  高潜成交 {gaoquan}\n"
        f"深转率 {deeprate}\n"
        f"🔗 https://soso0122.github.io/daily-guide-report/"
    )
    print(f'\n摘要:\n{summary}')

    if send_mode:
        print('\n发送图片...')
        r1 = send_image(SCREENSHOT_PATH)
        print(f'图片: {r1}')
        print('发送文字...')
        r2 = send_text(summary)
        print(f'文字: {r2}')
        print('推送完成！')
    else:
        print('\n截图已生成，确认后运行:')
        print(f'  python scripts/push_daily_report.py --send')

if __name__ == '__main__':
    main()
