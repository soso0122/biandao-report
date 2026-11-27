#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
推送快手投放日报到企微（文字版）
用法:
  python scripts/push_kuaishou_report.py          # 本地预览推送文字，不发送
  python scripts/push_kuaishou_report.py --send   # 发送企微
"""
import sys
import re
import json
import base64
import urllib.request
import hashlib
from pathlib import Path

WEBHOOK = 'https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=9abcd213-0acf-4ce1-993a-ec4ebd82a96a'

BASE_DIR = Path(__file__).resolve().parent.parent
REPORTS_DIR = BASE_DIR / 'reports'
DATA_JSON = BASE_DIR / 'data' / 'kuaishou_shimo_data.json'
SCREENSHOT_PATH = REPORTS_DIR / 'kuaishou_snapshot_latest.png'


def get_latest_report():
    files = sorted(REPORTS_DIR.glob('快手投放报告_*.html'))
    return files[-1] if files else None


def fnum(v):
    try:
        x = float(str(v).replace(',', '').replace('%', ''))
        return x if abs(x) < 1e300 else 0.0
    except (TypeError, ValueError):
        return 0.0


def extract_text():
    """从 data/kuaishou_shimo_data.json 取两个项目最新一天 KPI，合并一条文字"""
    data = json.load(open(DATA_JSON, encoding='utf-8'))
    # 全局最新日期：取两项目中较新者，落后于它的项目视为当天未投放
    all_latest = max(sorted(p['dates'])[-1] for p in (data['student'], data['parent']))

    def proj_text(proj, label):
        d = data[proj]
        latest = sorted(d['dates'])[-1]
        if latest < all_latest:
            return f"{label} {all_latest[5:7]}/{all_latest[8:10]}\n⏸️ 今日未投放"
        label = f"{label} {latest[5:7]}/{latest[8:10]}"
        m = {k: 0.0 for k in ('sp', 'cv', 'o1', 'o3', 'o5', 'o10', 'va')}
        for a in d['accounts']:
            day = a['days'].get(latest)
            if not day:
                continue
            for k in m:
                m[k] += day.get(k, 0.0)
        cpa = m['sp'] / m['cv'] if m['cv'] else 0.0
        deep = (d.get('deep_real') or {}).get(latest, 0)
        deep_rate = deep / m['cv'] * 100 if m['cv'] else 0.0
        # 开口各级：超过有效获客的部分=回流，自动标注
        def open_part(key):
            n = int(m[key])
            back = max(0, n - int(m['va']))
            return f"{n}（含回流 {back}）" if back > 0 else str(n)
        return (
            f"{label}\n"
            f"💰 消耗：¥{m['sp']:,.2f} ｜ 转化：{int(m['cv'])} ｜ CPA：¥{cpa:,.2f}\n"
            f"🧾 深转出单：{int(deep)}（深转率 {deep_rate:.2f}%）\n"
            f"💬 企微开口：1次 {open_part('o1')} ｜ 3次 {open_part('o3')} ｜ 5次 {open_part('o5')} ｜ 10次 {open_part('o10')}"
        )

    student_text = proj_text('student', '📊 快手19元（学生）')
    parent_text = proj_text('parent', '📊 快手0元（家长）')
    text = (
        f"# {student_text.splitlines()[0]}\n"
        f"{chr(10).join(student_text.splitlines()[1:])}\n\n"
        f"# {parent_text.splitlines()[0]}\n"
        f"{chr(10).join(parent_text.splitlines()[1:])}\n\n"
        f"[点开查看完整明细 👉](https://soso0122.github.io/kuaishou-report/)"
    )
    return text


def send_text(text):
    """curl 发送 markdown 消息（支持标题加粗）"""
    import subprocess
    payload = json.dumps({'msgtype': 'markdown', 'markdown': {'content': text}}, ensure_ascii=False)
    r = subprocess.run(
        ['curl', '-s', '-m', '15', '-X', 'POST', WEBHOOK,
         '-H', 'Content-Type: application/json', '-d', payload],
        capture_output=True, text=True, timeout=20)
    try:
        return json.loads(r.stdout)
    except Exception:
        return {'raw': r.stdout[:200], 'stderr': r.stderr[:200]}


def main():
    send_mode = '--send' in sys.argv
    report = get_latest_report()
    text = extract_text()
    print('=' * 44)
    print(text)
    print('=' * 44)
    if send_mode:
        r = send_text(text)
        print('发送结果:', r)
    else:
        print('\n（本地预览模式。确认无误后加 --send 发送企微。）')


if __name__ == '__main__':
    main()
