#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
「浅投 → 跑出」对比信息图生成器
用法: python3 scripts/generate_bloom_image.py
输出: reports/浅投跑出对比.png
"""
import json
from pathlib import Path

ROOT = Path(__file__).parent.parent
OUT = ROOT / 'reports'

with open(OUT / '_bloom_compare.json', encoding='utf-8') as fh:
    DATA = json.load(fh)


def fmt_n(v):
    if v >= 10000:
        return f"{v/10000:.1f}万"
    if v >= 1000:
        return f"{v:,.0f}"
    return f"{v:,.2f}" if v < 100 and v != int(v) else f"{v:,.0f}"


def fmt_money(v):
    if v >= 10000:
        return f"¥{v/10000:.2f}万"
    return f"¥{v:,.2f}"


cards = []
for r in DATA:
    # 增长倍数
    mult = r['b_spend'] / r['s_spend'] if r['s_spend'] > 0 else 0
    short_name = r['name'].replace('推送视频_', '').replace('.mp4.mp4', '.mp4').replace('.mp4', '')
    if len(short_name) > 22:
        short_name = short_name[:21] + '…'
    metrics = [
        ('消耗', fmt_money(r['s_spend']), fmt_money(r['b_spend'])),
        ('展示', fmt_n(r['s_imp']), fmt_n(r['b_imp'])),
        ('点击', fmt_n(r['s_click']), fmt_n(r['b_click'])),
        ('转化', fmt_n(r['s_conv']), fmt_n(r['b_conv'])),
    ]
    metric_html = ''
    for label, sv, bv in metrics:
        metric_html += f'''
        <div class="m">
          <div class="ml">{label}</div>
          <div class="mv gray">{sv}</div>
          <div class="arrow">→</div>
          <div class="mv green">{bv}</div>
        </div>'''
    cards.append(f'''
    <div class="card">
      <div class="top">
        <div class="name">{short_name}</div>
        <div class="months"><span class="chip gray">{int(r['shallow_mm'])}月 · 浅投</span><span class="chip green">{int(r['bloom_mm'])}月 · 跑出</span></div>
        <div class="mult">×{mult:,.0f}</div>
      </div>
      <div class="metrics">{metric_html}</div>
    </div>''')

cards_html = ''.join(cards)

html = f'''<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="UTF-8"><style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{width:900px;background:#F0F4FA;font-family:'PingFang SC','Microsoft YaHei',sans-serif;padding:28px}}
.title{{font-size:24px;font-weight:700;color:#1E3A8A;margin-bottom:6px}}
.subtitle{{font-size:13px;color:#64748B;margin-bottom:20px}}
.card{{
  background:#fff;border:1px solid #DBEAFE;border-radius:12px;padding:12px 16px;
  margin-bottom:10px;box-shadow:0 1px 2px rgba(30,64,175,.05);
}}
.top{{display:flex;align-items:center;gap:10px;margin-bottom:8px}}
.name{{font-size:13.5px;font-weight:600;color:#1E3A8A;flex:none;max-width:340px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}}
.months{{display:flex;gap:6px;flex:none}}
.chip{{padding:2px 10px;border-radius:10px;font-size:11px;font-weight:600}}
.chip.gray{{background:#F1F5F9;color:#64748B}}
.chip.green{{background:#ECFDF5;color:#059669}}
.mult{{margin-left:auto;font-size:13px;font-weight:700;color:#D97706;flex:none;background:#FFFBEB;padding:2px 10px;border-radius:10px}}
.metrics{{display:grid;grid-template-columns:1fr 1fr 1fr 1fr;gap:8px}}
.m{{background:#F8FAFC;border-radius:8px;padding:7px 10px;text-align:center}}
.ml{{font-size:10.5px;color:#94A3B8;margin-bottom:3px}}
.mv{{font-size:13px;font-weight:700;font-family:monospace}}
.mv.gray{{color:#64748B}}
.mv.green{{color:#059669}}
.arrow{{font-size:12px;color:#CBD5E1;margin:2px 0;text-align:center}}
.foot{{margin-top:18px;font-size:11px;color:#94A3B8;text-align:center}}
</style></head><body>
<div class="title">素材「浅投 → 跑出」对比 · 共 {len(DATA)} 个</div>
<div class="subtitle">口径：浅投月 = 当月消耗≤¥10；跑出月 = 后续单月消耗≥¥50 且转化≥3。× 为消耗增幅倍数。</div>
{cards_html}
<div class="foot">数据范围 07/21–10/08 · 千川信息流 · 引导加微项目</div>
</body></html>'''

html_path = OUT / '_bloom_image.html'
html_path.write_text(html, encoding='utf-8')

from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page(viewport={'width': 1000, 'height': 800})
    page.goto(f'file://{html_path.resolve()}')
    page.wait_for_timeout(400)
    height = page.evaluate('document.body.scrollHeight')
    page.set_viewport_size({'width': 900, 'height': height + 40})
    page.wait_for_timeout(300)
    out_png = OUT / '浅投跑出对比.png'
    page.screenshot(path=str(out_png), full_page=True)
    browser.close()

print(f'信息图已生成: {out_png}')
