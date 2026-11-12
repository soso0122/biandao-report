# -*- coding: utf-8 -*-
"""快手投放数据报告（2026-10-30 起，数据源=石墨文档）

数据源：data/kuaishou_shimo_data.json（由 fetch_shimo_kuaishou.py 从石墨拉取）。

页面结构（2026-11-02 用户定稿）：
  TAB1 投放数据表现：KPI 14卡 → 九级漏斗 → 逐日趋势 → 账户总览/筛选 →
       聚合维度表（素材名称/计划/组三选一）→ 分时表现（24小时柱线+热力+优劣势时段）
  TAB2 素材数据表现：KPI 8卡（素材数按名称去重）→ 类型卡+编导卡 → 素材明细
  （含深转/有效获客，列序：名称/类型/编导/花费/转化/转化成本/开口1/3/5/10/深转/有效获客/
   封面曝光/封面点击率/素材曝光/素材点击率/行为数/行为率/3秒/5秒/完播/播放）

联动（重点，勿漏）：账户筛选、日期多选为两个 TAB 共享状态；
类型/编导/搜索/聚合维度只作用于所属表格。分时模块随日期与账户联动。

用法：python3 scripts/generate_kuaishou_report.py [MMDD]
输出：reports/快手投放报告_MMDD.html
"""

import json
import sys
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
REPORTS_DIR = BASE_DIR / "reports"
DATA_JSON = BASE_DIR / "data" / "kuaishou_shimo_data.json"
CHART_JS_PATH = Path(__file__).parent / "chart.min.js"

TODAY = datetime.now()
TARGET = sys.argv[1] if len(sys.argv) > 1 else TODAY.strftime("%m%d")
TARGET_DT = datetime(TODAY.year, int(TARGET[:2]), int(TARGET[2:]))
if TARGET_DT > TODAY:
    TARGET_DT = TARGET_DT.replace(year=TODAY.year - 1)
REPORT_MMDD = TARGET_DT.strftime("%m%d")

PERSON_COLORS = {
    "小敏": "#3B82F6", "嘉丽": "#8B5CF6", "瑞晨": "#10B981",
    "浩正": "#F59E0B", "雅迪": "#EC4899", "魏怡": "#EF4444",
    "婷玉": "#14B8A6", "国星": "#0EA5E9", "其他": "#94A3B8",
}
PERSON_BG = {
    "小敏": "#EFF6FF", "嘉丽": "#F5F3FF", "瑞晨": "#ECFDF5",
    "浩正": "#FFFBEB", "雅迪": "#FDF2F8", "魏怡": "#FEF2F2",
    "婷玉": "#F0FDFA", "国星": "#E0F2FE", "其他": "#F8FAFC",
}

CSS = """
:root{--bg:#F8FAFC;--card:#FFFFFF;--border:#DBEAFE;--primary:#1E40AF;--primary-light:#3B82F6;
--accent:#D97706;--accent-bg:#FFFBEB;--text:#1E3A8A;--text-secondary:#64748B;--text-muted:#94A3B8;
--success:#059669;--danger:#DC2626;--shadow:0 1px 3px rgba(0,0,0,.08);--shadow-md:0 4px 6px rgba(0,0,0,.07);
--radius:10px;font-family:'Fira Sans',system-ui,sans-serif}
*{box-sizing:border-box;margin:0;padding:0}
body{background:var(--bg);color:var(--text);font-size:14px;line-height:1.5;min-height:100vh}

.topbar{position:sticky;top:0;z-index:1000;background:#fff;border-bottom:1.5px solid var(--border);
box-shadow:0 2px 6px rgba(0,0,0,.06);padding:8px 24px 10px}
.topbar-row1{display:flex;align-items:center;gap:14px;flex-wrap:wrap;margin-bottom:6px}
.brand{font-size:13px;font-weight:700;color:var(--primary);white-space:nowrap}
.nav{display:flex;gap:6px}
.tab-btn{padding:5px 14px;border-radius:8px;border:1px solid var(--border);background:var(--bg);
color:var(--text-secondary);font-size:12px;font-weight:500;cursor:pointer}
.tab-btn.active{background:var(--primary);color:#fff;border-color:var(--primary)}
.topbar-row2{display:flex;align-items:center;gap:8px;flex-wrap:wrap}
.topbar-row2 .label{font-size:12px;color:var(--text-secondary);font-weight:500}
.date-chip{font-size:11px;padding:3px 9px;border-radius:12px;background:#EFF6FF;color:var(--primary);
border:1px solid #BFDBFE;cursor:pointer}
.date-chip.sel{background:var(--primary);color:#fff;border-color:var(--primary)}
.date-dropdown{position:relative}
.date-dropdown-btn{padding:5px 14px;border-radius:8px;border:1.5px solid var(--border);background:var(--card);
color:var(--text);font-size:12px;font-weight:500;cursor:pointer}
.date-dropdown-btn:hover{border-color:var(--primary-light);color:var(--primary)}
.date-dropdown-panel{position:absolute;top:110%;left:0;z-index:1200;background:#fff;
border:1.5px solid var(--border);border-radius:10px;box-shadow:0 8px 24px rgba(0,0,0,.12);
padding:10px;width:330px}
.dd-head{display:flex;gap:6px;margin-bottom:8px;flex-wrap:wrap}
.dd-grid{display:grid;grid-template-columns:repeat(7,1fr);gap:5px;max-height:260px;overflow-y:auto}
.dd-item{font-size:11px;padding:4px 0;text-align:center;border-radius:8px;border:1.5px solid var(--border);
cursor:pointer;color:var(--text-secondary);background:var(--bg)}
.dd-item:hover{border-color:var(--primary-light)}
.dd-item.sel{background:var(--primary);color:#fff;border-color:var(--primary)}
.acct-chip{font-size:11px;padding:3px 9px;border-radius:12px;background:#F0FDF4;color:#047857;
border:1px solid #A7F3D0;cursor:pointer}
.acct-chip.sel{background:#047857;color:#fff;border-color:#047857}
.range-btn{font-size:11px;padding:3px 9px;border-radius:12px;border:1px solid var(--border);
background:#fff;color:var(--text-secondary);cursor:pointer}
.range-btn:hover{border-color:var(--primary-light);color:var(--primary)}
.range-btn.active{background:var(--primary);color:#fff;border-color:var(--primary)}

.page{max-width:1500px;margin:0 auto;padding:20px 24px}
.section-title{font-size:13px;font-weight:600;color:var(--text);margin-bottom:12px;
display:flex;align-items:center;gap:6px}
.section-title::before{content:'';display:inline-block;width:3px;height:14px;
background:var(--primary-light);border-radius:2px}

.caliber-card{background:var(--card);border:1.5px solid var(--border);border-radius:var(--radius);
box-shadow:var(--shadow);margin-bottom:16px;overflow:hidden}
.caliber-head{display:flex;align-items:center;justify-content:space-between;
padding:10px 14px;background:#F0F6FF;border-bottom:1px solid var(--border);cursor:pointer;
font-size:13px;font-weight:600;color:var(--primary)}
.caliber-head .arrow{transition:transform .2s;font-size:11px;color:var(--text-secondary)}
.caliber-body{padding:12px 16px;display:grid;grid-template-columns:repeat(auto-fill,minmax(330px,1fr));gap:8px 20px}
.caliber-item{font-size:12px;color:#475569;line-height:1.7}
.caliber-item b{color:var(--primary);font-weight:600}
.caliber-card.collapsed .caliber-body{display:none}
.caliber-card.collapsed .arrow{transform:rotate(-90deg)}

.kpi-grid{display:grid;grid-template-columns:repeat(7,1fr);gap:10px;margin-bottom:20px}
.kpi-card{background:var(--card);border:1px solid var(--border);border-radius:var(--radius);
padding:12px 14px;box-shadow:var(--shadow)}
.kpi-card.accent{background:var(--accent-bg);border-color:#FCD34D}
.kpi-label{font-size:11px;color:var(--text-secondary);font-weight:500;text-transform:uppercase;
letter-spacing:.4px;margin-bottom:5px}
.kpi-value{font-size:20px;font-weight:700;color:var(--primary);font-family:'Fira Code',monospace;line-height:1.1}
.kpi-card.accent .kpi-value{color:var(--accent)}
.kpi-sub{font-size:10.5px;color:var(--text-muted);margin-top:3px}
.kpi-sub .open-rate{font-size:13px;font-weight:700;color:var(--success)}
.cell-tip{position:relative;display:inline-block;font-size:10.5px;color:var(--primary-light);cursor:help}
.cell-tip:hover::after{content:attr(data-tip);position:fixed;z-index:99999;pointer-events:none;
background:#1E3A8A;color:#fff;border-radius:8px;padding:8px 10px;font-size:11px;font-weight:400;
line-height:1.5;white-space:normal;word-break:break-all;max-width:420px;
box-shadow:0 4px 12px rgba(0,0,0,.3)}
.tip-cell{position:relative}
.tip-cell:hover::after{content:attr(data-tip);position:fixed;z-index:99999;pointer-events:none;
background:#1E3A8A;color:#fff;border-radius:8px;padding:8px 10px;font-size:11px;font-weight:400;
line-height:1.5;white-space:pre-wrap;word-break:break-all;max-width:420px;
box-shadow:0 4px 12px rgba(0,0,0,.3)}
.audit-cell{background:#F8FAFC;border-radius:6px;padding:6px 8px;text-align:center;position:relative;cursor:help}
.audit-cell .audit-label{font-size:10px;color:#94A3B8}
.audit-cell .audit-val{font-size:13px;font-weight:700;color:#059669;font-family:monospace}
.audit-cell .audit-frac{font-size:9px;color:#64748B;font-family:monospace}
.audit-cell:hover::after{content:attr(data-tip);position:fixed;z-index:99999;pointer-events:none;
background:#1E3A8A;color:#fff;border-radius:8px;padding:10px 12px;font-size:11px;font-weight:400;
line-height:1.7;white-space:pre-wrap;word-break:break-all;max-width:480px;
box-shadow:0 4px 12px rgba(0,0,0,.3)}
.tc-diff{font-weight:600;display:inline-block;font-size:10px}
.tc-diff.inc{color:var(--success)}
.tc-diff.dec{color:var(--danger)}
.help-tip{display:inline-flex;align-items:center;justify-content:center;width:11px;height:11px;
border-radius:50%;background:#DBEAFE;color:var(--primary);font-size:9px;font-weight:700;line-height:1;
margin-left:3px;flex-shrink:0;position:relative;vertical-align:middle}
.help-tip::before{content:'?'}
.help-tip:hover::after{content:attr(data-tip);position:fixed;z-index:99999;pointer-events:none;
background:#1E3A8A;color:#fff;border-radius:8px;padding:8px 10px;font-size:11px;font-weight:400;
line-height:1.5;white-space:normal;word-break:break-all;max-width:380px;box-shadow:0 4px 12px rgba(0,0,0,.3)}

.charts-row{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:20px}
.chart-card{background:var(--card);border:1px solid var(--border);border-radius:var(--radius);
padding:16px;box-shadow:var(--shadow)}
.chart-wrap{position:relative;height:240px;width:100%}
.funnel-wrap{position:relative;height:320px;width:100%}

.filter-bar{display:flex;align-items:center;gap:8px;flex-wrap:wrap;background:var(--card);
border:1px solid var(--border);border-radius:var(--radius);padding:10px 14px;margin-bottom:12px;
box-shadow:var(--shadow)}
.filter-label{font-size:12px;color:var(--text-secondary);font-weight:500;white-space:nowrap}
.filter-btn{padding:4px 12px;border-radius:20px;border:1.5px solid var(--border);font-size:12px;
font-weight:500;cursor:pointer;transition:all .15s;background:var(--bg);color:var(--text-secondary)}
.filter-btn:hover{border-color:currentColor;opacity:.9}
.filter-btn.active{color:#fff;border-color:transparent;background:var(--primary)}
.filter-btn-video{color:#3B82F6}
.filter-btn-tuwen{color:#8B5CF6}
.filter-btn-ai{color:#6366F1}
.filter-btn-huahuo{color:#F43F5E}
.filter-sep{width:1px;height:18px;background:var(--border);margin:0 4px}
.search-box{padding:5px 10px;border-radius:8px;border:1.5px solid var(--border);font-size:12px;
outline:none;width:180px;background:var(--bg);color:var(--text)}
.search-box:focus{border-color:var(--primary-light)}

.table-card{background:var(--card);border:1px solid var(--border);border-radius:var(--radius);
box-shadow:var(--shadow);overflow:hidden}
.table-toolbar{display:flex;align-items:center;justify-content:space-between;
padding:10px 14px;border-bottom:1px solid var(--border);flex-wrap:wrap;gap:8px}
.table-info{font-size:12px;color:var(--text-secondary)}
.table-info span{font-weight:600;color:var(--primary)}
.table-wrap{overflow-x:auto}
table{width:100%;border-collapse:collapse;font-size:13px}
thead th{padding:8px 10px;text-align:left;font-size:11px;font-weight:600;color:var(--text-secondary);
background:#F1F5F9;border-bottom:1px solid var(--border);white-space:nowrap;cursor:pointer;
user-select:none;position:sticky;top:0;z-index:5}
thead th:hover{color:var(--primary)}
thead th.sorted-asc::after{content:' ↑'}
thead th.sorted-desc::after{content:' ↓'}
tbody tr{border-bottom:1px solid #F1F5F9;transition:background .1s}
tbody tr:hover{background:var(--bg)}
tbody td{padding:8px 10px;vertical-align:middle}
tbody tr:last-child{border-bottom:none}

.person-badge{display:inline-flex;align-items:center;padding:2px 8px;border-radius:12px;
font-size:11px;font-weight:600;white-space:nowrap}
.type-video{background:#EFF6FF;color:#3B82F6}
.type-tuwen{background:#F5F3FF;color:#8B5CF6}
.type-ai{background:#EEF2FF;color:#6366F1}
.type-huahuo{background:#FFF1F2;color:#F43F5E}
.mat-name{min-width:320px;max-width:420px;white-space:normal;word-break:break-all;font-size:12px;
color:var(--text);line-height:1.45}
.num{font-family:'Fira Code',monospace;font-size:12px}
.num-zero{color:var(--text-muted)}
.gaoquan-cell{font-family:'Fira Code',monospace;font-size:12.5px;font-weight:700;color:var(--accent)}
.gaoquan-zero{color:var(--text-muted);font-weight:400}
.btn-play{display:inline-flex;align-items:center;gap:4px;padding:4px 10px;border-radius:6px;
border:1.5px solid var(--border);background:var(--bg);color:var(--primary-light);font-size:11px;
font-weight:500;cursor:pointer}
.btn-play:hover{background:var(--primary);color:#fff;border-color:var(--primary)}

.heat-table{width:100%;border-collapse:collapse;font-size:12px}
.heat-table th{position:sticky;top:0;z-index:5;text-align:center}
.heat-table td{text-align:center;padding:6px 8px;border:1px solid #EEF2FF}
.heat-table .hour-label{font-family:'Fira Code',monospace;font-size:11px;color:var(--text-secondary);
background:#F8FAFC;white-space:nowrap}
.heat-cell{font-family:'Fira Code',monospace;font-size:11px}
.hour-tags{display:flex;gap:8px;flex-wrap:wrap;margin:10px 0}
.hour-tag{display:inline-flex;align-items:center;gap:4px;font-size:11px;padding:3px 10px;
border-radius:12px;background:var(--bg);border:1.5px solid var(--border);color:#475569}
.hour-tag.good{background:#ECFDF5;border-color:#A7F3D0;color:#047857}
.hour-tag.bad{background:#FEF2F2;border-color:#FECACA;color:#B91C1C}
.hour-caliber{font-size:11px;color:#475569;background:#F8FAFC;border:1.5px solid var(--border);
border-radius:8px;padding:8px 12px;margin-bottom:12px;line-height:1.7}
.hour-caliber b{color:var(--primary);font-weight:600}

.modal-overlay{position:fixed;inset:0;background:rgba(15,23,42,.7);display:none;
align-items:center;justify-content:center;z-index:1000;backdrop-filter:blur(4px)}
.modal-overlay.open{display:flex}
.modal{background:#0F172A;border-radius:14px;overflow:hidden;width:min(900px,95vw);
box-shadow:0 25px 50px rgba(0,0,0,.5);display:flex;flex-direction:column;max-height:90vh}
.modal-header{display:flex;align-items:center;justify-content:space-between;
padding:12px 16px;border-bottom:1px solid rgba(255,255,255,.1)}
.modal-title{color:#E2E8F0;font-size:13px;font-weight:500;max-width:calc(100% - 40px);
overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.modal-close{width:28px;height:28px;border-radius:6px;border:none;background:rgba(255,255,255,.1);
color:#94A3B8;cursor:pointer;display:flex;align-items:center;justify-content:center;font-size:18px}
.modal-close:hover{background:rgba(255,255,255,.2);color:#fff}
.video-wrap{background:#000;display:flex;align-items:center;justify-content:center;flex:1}
video{max-width:100%;max-height:65vh;display:block}
.empty-state{text-align:center;padding:40px 20px;color:var(--text-muted);font-size:13px}
.pager{display:flex;justify-content:flex-end;align-items:center;gap:4px;padding:8px 14px;
border-top:1px solid var(--border);flex-wrap:wrap}
.pager-info{font-size:11px;color:var(--text-muted);margin-right:8px}
.page-btn{display:inline-block;padding:2px 9px;border:1px solid var(--border);border-radius:6px;
background:#fff;font-size:11px;color:var(--text-secondary);cursor:pointer}
.page-btn:hover{border-color:var(--primary-light);color:var(--primary)}
.page-btn.active{background:var(--primary);border-color:var(--primary);color:#fff;font-weight:600}
.page-btn:disabled{opacity:.4;cursor:default}
@media(max-width:900px){.kpi-grid{grid-template-columns:repeat(2,1fr)}.charts-row{grid-template-columns:1fr}}
"""


def caliber_html(suffix=""):
    cid = "caliberCard" + suffix
    return f"""
<div class="caliber-card collapsed" id="{cid}">
  <div class="caliber-head" onclick="document.getElementById('{cid}').classList.toggle('collapsed')">
    <span>📌 指标口径说明（点击展开）</span><span class="arrow">▼</span>
  </div>
  <div class="caliber-body">
    <div class="caliber-item"><b>数据源</b>：石墨文档「【快手】引流加微数据」（账户表现 + 素材表现 + 拒审台账-主账户/子账户 + 当日数据记录），快手投放 2026-10-30 起。</div>
    <div class="caliber-item"><b>行为数</b>：快手的「行为」约等于素材点击。行为率 = 行为数 ÷ 曝光数。</div>
    <div class="caliber-item"><b>转化率</b> = 转化数(计费时间) ÷ 行为数；<b>CPA</b> = 花费 ÷ 转化数。</div>
    <div class="caliber-item"><b>深转数/深转率</b>：来自「当日数据记录」的销售反馈出单（真实回传，天级）。KPI/漏斗/趋势用真实出单；素材/账户级明细无法拆分显示「—」；单账户视图显示「单账户未回传」。</div>
    <div class="caliber-item"><b>⚠️ 开口口径</b>：快手导出的「企微开口」是当天所有开口的用户数，含数据窗口（10/30）之前转化、后来才开口的用户，也含「转化0、开口1」的导出差异。因此开口可长期大于窗口内转化、开口率可超 100%，属后台导出口径，非计算错误。</div>
    <div class="caliber-item"><b>开口率</b> = 开口N次 ÷ 有效获客（投放TAB KPI卡）；<b>回流开口</b> = 开口1次 − 有效获客，标在素材明细「回流开口」列。</div>
    <div class="caliber-item"><b>素材分类</b>（互斥优先级）：名称含「花火」→花火AI；创意名称含「系统自动」或名称=AIGC→平台AI；素材内容有视频链接→视频；名称含「图文集合_」→图文。四类互斥不重叠。</div>
    <div class="caliber-item"><b>编导归属</b>：名称匹配 4 位核心编导（嘉丽、小敏、雅迪、瑞晨），其余全部「其他」。视频和图文都按名称匹配。</div>
    <div class="caliber-item"><b>素材点击率</b> = 行为数 ÷ 素材曝光数；<b>封面点击率</b> = 封面点击 ÷ 封面曝光；<b>3秒/5秒/完播率</b>按曝光加权。</div>
    <div class="caliber-item"><b>素材去重</b>：素材总数按素材名称去重；同名素材在台账/报表只算 1 条；账户表为广告组级拆分，数字按行加总后重算比率。</div>
    <div class="caliber-item"><b>分时</b>：按小时聚合，选多天按小时跨日累计；优差时段 = 先取「有花费的时段」算均值，🟢优质=转化率≥均值×1.15 且花费≥均值×0.5，🔴差=转化率<均值×0.85 且花费≥均值×0.5，其余不标。</div>
    <div class="caliber-item"><b>近3周跑出 · 素材池</b>：台账（主+子）∪ 报表，按产出日归近3个自然周（周一起）；仅视频+图文（排除AI/花火AI）；随账户筛选变化（全选=双台账并集，单选=该账户台账∪该账户报表素材）。</div>
    <div class="caliber-item"><b>过审率（素材页/编导卡）</b>：分母=素材池合并去重（同名只算1条）；过审状态=严格合并（全选时两边都过审才算过审，单选按对应台账）。编导卡悬停可看过审/卡审素材名单。</div>
    <div class="caliber-item"><b>近3周跑出 · 产出日期</b>：素材名 MMDD 前缀 → 中文日期（如「11月4日」）→ AI拒审修复时间戳 → 特例（1007→10/07、国庆→10/01、中秋→09/25、11056→11/05、713→07/13）→ 台账上传日期 → 报表首现日。数字ID、raw哈希、图文集合、无日期名称不计入。</div>
    <div class="caliber-item"><b>近3周跑出 · 过审</b>：三分类 = 过审（审核状态是「审核通过」或「-」，且关联创意无「未通过」字眼）/ 上传卡审（状态=审核未通过）/ 投放卡审（关联创意含「未通过」且状态非未通过）。全选账户=双台账严格合并（两边都过审才算过审；卡审从严：上传卡审&gt;投放卡审；一边过审一边无记录=过审）；单选=对应账户台账。</div>
    <div class="caliber-item"><b>近3周跑出 · 指标</b>：素材按产出日归周，但周内指标=产出日→数据最新日的全期累计（不按周窗口截断）；跑出素材=窗口内产出且有转化的素材；跑出率=跑出素材÷素材池；开口率=开口10次÷产出数；有效投放天数=当天花费>0的天数。</div>
    <div class="caliber-item"><b>漏斗</b>：转化 → 深转 → 有效获客 → 企微开口 1/3/5/10 次（逐级递减）。</div>
  </div>
</div>
"""

def build_html():
    data = json.load(open(DATA_JSON, encoding="utf-8"))
    chart_js = CHART_JS_PATH.read_text(encoding="utf-8") if CHART_JS_PATH.exists() else ""

    html = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>快手投放日报 · __MMDD__</title>
<style>__CSS__</style>
</head>
<body>
<div class="topbar">
  <div class="topbar-row1">
    <span class="brand">🟠 快手投放日报 · __MMDD__</span>
    <nav class="nav">
      <button class="tab-btn active" id="tabBtn1" onclick="switchTab(1)">📊 投放数据表现</button>
      <button class="tab-btn" id="tabBtn2" onclick="switchTab(2)">🎬 素材数据表现</button>
      <button class="tab-btn" id="tabBtn3" onclick="switchTab(3)">📅 近3周跑出</button>
      <button class="tab-btn" id="tabBtn4" onclick="switchTab(4)">🚦 过审数据</button>
    </nav>
  </div>
  <div class="topbar-row2">
    <span class="label">日期</span>
    <div class="date-dropdown" id="dateDropdown">
      <button class="date-dropdown-btn" id="dateDropdownBtn">选择日期 ▾</button>
      <div class="date-dropdown-panel" id="dateDropdownPanel" style="display:none">
        <div class="dd-head">
          <button class="range-btn active" data-dd="latest">最新</button>
          <button class="range-btn" data-dd="7d">近7天</button>
          <button class="range-btn" data-dd="all">全部</button>
          <button class="range-btn" data-dd="clear">清空</button>
        </div>
        <div class="dd-grid" id="ddGrid"></div>
      </div>
    </div>
    <span class="filter-sep" style="display:inline-block"></span>
    <span class="label">账户</span>
    <span id="acctChips" style="display:flex;gap:4px;flex-wrap:wrap"></span>
  </div>
</div>
<div class="page">

<!-- ============ TAB1 投放数据表现 ============ -->
<div id="tab1">
  __CALIBER1__
  <div class="kpi-grid" id="kpiGrid1"></div>
  <div class="chart-card" style="margin-bottom:20px">
    <div class="section-title">转化漏斗（所选日期累计）</div>
    <div class="funnel-wrap"><canvas id="chartFunnel"></canvas></div>
  </div>
  <div class="charts-row">
    <div class="chart-card">
      <div class="section-title">逐日花费 / 转化 / 深转</div>
      <div class="chart-wrap"><canvas id="chartTrend"></canvas></div>
    </div>
    <div class="chart-card">
      <div class="section-title">逐日 CPA / 转化率</div>
      <div class="chart-wrap"><canvas id="chartCpa"></canvas></div>
    </div>
  </div>
  <div class="chart-card" style="margin-bottom:20px">
    <div class="section-title">⏰ 分时表现（哪个小时跑得好）<span class="table-info" id="hourlyNote"></span></div>
    <div class="hour-caliber" id="hourCaliber"></div>
    <div class="chart-wrap" style="height:260px"><canvas id="chartHour"></canvas></div>
    <div class="hour-tags" id="hourTags"></div>
    <div class="table-wrap" style="max-height:420px;overflow-y:auto">
      <table class="heat-table" id="heatTable"><thead></thead><tbody id="heatBody"></tbody></table>
    </div>
  </div>
  <div class="table-card" style="margin-bottom:20px" id="acctSection">
    <div class="table-toolbar">
      <div class="section-title" style="margin:0">📊 账户总览</div>
      <div class="table-info">点击账户名筛选全页</div>
    </div>
    <div class="table-wrap"><table id="acctTable"><thead></thead><tbody id="acctBody"></tbody></table></div>
  </div>
  <div class="filter-bar">
    <span class="filter-label">聚合维度</span>
    <button class="filter-btn active" data-dim="material">素材名称</button>
    <button class="filter-btn" data-dim="plan">计划</button>
    <button class="filter-btn" data-dim="group">组</button>
  </div>
  <div class="table-card" style="margin-bottom:20px">
    <div class="table-toolbar">
      <div class="section-title" style="margin:0">🎯 投放明细（按<span id="dimLabel">素材名称</span>聚合）</div>
      <div class="table-info">共 <span id="dimCount">0</span> 条</div>
    </div>
    <div class="table-wrap"><table id="dimTable"><thead></thead><tbody id="dimBody"></tbody></table></div>
    <div class="pager" id="dimPager"></div>
  </div>
</div>

<!-- ============ TAB2 素材数据表现 ============ -->
<div id="tab2" style="display:none">
  __CALIBER2__
  <div class="kpi-grid" id="kpiGrid2" style="grid-template-columns:repeat(5,1fr)"></div>
  <div class="chart-card" style="margin-bottom:20px">
    <div class="section-title">素材类型</div>
    <div id="typeRow" style="display:grid;grid-template-columns:repeat(4,1fr);gap:12px"></div>
    <div class="section-title" style="margin-top:16px">编导表现（点卡片筛选明细）</div>
    <div id="personRow" style="display:grid;grid-template-columns:repeat(5,1fr);gap:12px"></div>
  </div>
  <div class="filter-bar" style="flex-direction:column;align-items:stretch;gap:8px">
    <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap">
      <span class="filter-label">类型</span>
      <button class="filter-btn active" data-t="all">全部</button>
      <button class="filter-btn filter-btn-video" data-t="视频">视频</button>
      <button class="filter-btn filter-btn-tuwen" data-t="图文">图文</button>
      <button class="filter-btn filter-btn-ai" data-t="AI">平台AI</button>
      <button class="filter-btn filter-btn-huahuo" data-t="花火AI">花火AI</button>
    </div>
    <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap">
      <span class="filter-label">编导</span>
      <span id="personBtns" style="display:flex;gap:6px;flex-wrap:wrap"></span>
    </div>
    <div>
      <input class="search-box" id="searchBox" placeholder="🔍 搜索素材名称" style="width:100%">
    </div>
  </div>
  <div class="table-card">
    <div class="table-toolbar">
      <div class="section-title" style="margin:0">🎬 素材明细</div>
      <div class="table-info">共 <span id="matCount">0</span> 条素材（按名称去重）</div>
    </div>
    <div class="table-wrap"><table id="matTable"><thead></thead><tbody id="matBody"></tbody></table></div>
    <div class="pager" id="matPager"></div>
  </div>
</div>

<!-- ============ TAB3 近3周跑出 ============ -->
<div id="tab3" style="display:none">
  __CALIBER3__
  <div class="kpi-grid" id="kpiGrid3" style="grid-template-columns:repeat(7,1fr)"></div>
  <div class="chart-card" style="margin-bottom:20px">
    <div class="section-title" style="justify-content:space-between">
      <span>编导表现</span>
      <span id="passWeekBtns" style="display:flex;gap:6px"></span>
    </div>
    <div id="passPersonRow" style="display:grid;grid-template-columns:repeat(5,1fr);gap:12px"></div>
  </div>
  <div class="chart-card" style="margin-bottom:20px">
    <div class="section-title">📅 近3周跑出表现（自然周 · 按产出日期归周）</div>
    <div class="table-info" style="margin-bottom:10px">
      素材池 = 拒审台账 ∪ 报表（含未过审/0数据素材）；仅视频+图文（排除平台AI/花火AI）；过审率为<b>按账户筛选（全选=双台账严格合并）</b>（拒审台账-子账户）。
    </div>
    <div id="pass3wWrap"></div>
  </div>
</div>

<!-- ============ TAB4 过审数据 ============ -->
<div id="tab4" style="display:none">
  __CALIBER4__
  <div class="kpi-grid" id="kpiGrid4" style="grid-template-columns:repeat(4,1fr)"></div>
  <div class="charts-row">
    <div class="chart-card">
      <div class="section-title">逐日上传与过审趋势（按上传日期）</div>
      <div class="chart-wrap"><canvas id="chartAuditTrend"></canvas></div>
    </div>
    <div class="chart-card">
      <div class="section-title">审核三分类占比（主账户+子账户合并去重）</div>
      <div class="chart-wrap"><canvas id="chartAuditPie"></canvas></div>
    </div>
  </div>
  <div class="chart-card" style="margin-bottom:20px">
    <div class="section-title">编导过审率对比</div>
    <div class="chart-wrap" style="height:260px"><canvas id="chartAuditPerson"></canvas></div>
  </div>
  <div class="table-card">
    <div class="table-toolbar">
      <div class="section-title" style="margin:0">⚠️ 卡审素材清单（上传卡审 + 投放卡审）</div>
      <div class="table-info">共 <span id="auditFailCount">0</span> 条（随账户筛选）</div>
    </div>
    <div class="table-wrap"><table id="auditTable"><thead></thead><tbody id="auditBody"></tbody></table></div>
    <div class="pager" id="auditPager"></div>
  </div>
</div>

</div>

<div class="modal-overlay" id="videoModal">
  <div class="modal">
    <div class="modal-header">
      <span class="modal-title" id="modalTitle"></span>
      <button class="modal-close" onclick="closeModal()">✕</button>
    </div>
    <div class="video-wrap"><video id="modalVideo" controls></video></div>
  </div>
</div>

<script>__CHARTJS__</script>
<script>
const DATA = __DATA_JSON__;
const PERSON_COLORS = __COLORS_JS__;
const PERSON_BG = __BG_JS__;

const ZM = () => ({sp:0,im:0,ac:0,cv:0,dp:0,va:0,o1:0,o3:0,o5:0,o10:0});
const ZQ = () => ({qi:0,qmi:0,cc:0,ce:0,p3:0,p5:0,fn:0});
const MKEYS = ['sp','im','ac','cv','dp','va','o1','o3','o5','o10'];
const QKEYS = ['qi','qmi','cc','ce','p3','p5','fn'];
const addM = (t,s) => MKEYS.forEach(k => t[k] += (s[k]||0));
const addQ = (t,s) => QKEYS.forEach(k => t[k] += (s[k]||0));

const state = {
  tab: 1,
  dates: [DATA.dates[DATA.dates.length-1]],  // 默认最新一天（日报口径）
  acct: 'all',
  dim: 'material',
  type: 'all',
  person: 'all',
  search: '',
};
// 快手深转暂未回传（导出表里深转=转化，无参考意义）：显示层统一展示「未回传」。
// 等快手回传深转后，用户告知，将本行删掉即恢复真实值。
// 深转真实回传来自「当日数据记录-销售反馈出单」（天级，不分素材/账户）。
// 天级聚合（KPI/漏斗/趋势）用 DATA.deep_real；素材级明细行无法拆分，深转列显示「—」。
const DEEP_PENDING = false;
function deepRealTotal() {
  if (state.acct !== 'all') return 0;   // 深转回传不分账户，单账户视图不展示
  let n = 0;
  for (const d of selDates()) n += (DATA.deep_real && DATA.deep_real[d]) || 0;
  return n;
}
// 当日（所选日期中最新一天）产出素材的跑出率/过审率（台账∪报表口径，随账户筛选）
let todayStatsCache = null;
function buildTodayStats() {
  const sel = [...state.dates].sort();
  if (!sel.length) return {total: 0, run: 0, passed: 0, submit: 0};
  const today = sel[sel.length - 1];
  // 当日素材池 = 当天上传（台账上传日期=today）的素材，主+子合并去重
  const pool = new Map();   // name -> {subAudit, mainAudit}
  for (const l of (DATA.ledger_sub || [])) {
    if (l.upload !== today) continue;
    const e = pool.get(l.name) || {name: l.name, subAudit: null, mainAudit: null};
    e.subAudit = l.audit;
    pool.set(l.name, e);
  }
  for (const l of (DATA.ledger_main || [])) {
    if (l.upload !== today) continue;
    const e = pool.get(l.name) || {name: l.name, subAudit: null, mainAudit: null};
    e.mainAudit = l.audit;
    pool.set(l.name, e);
  }
  // 报表首现日=today 的素材也进池（台账漏记的兜底）
  for (const m of DATA.materials) {
    if (m.type === 'AI' || m.type === '花火AI') continue;
    if (m.type !== '视频' && m.type !== '图文') continue;
    if (excludePass3w(m.name)) continue;
    const days = Object.keys(m.days).sort();
    if (days[0] !== today) continue;
    if (!pool.has(m.name)) {
      pool.set(m.name, {name: m.name, subAudit: null, mainAudit: null});
    }
  }
  // 跑出判定：素材全期累计转化 > 0
  const cvByName = new Map();
  for (const m of DATA.materials) {
    if (m.type === 'AI' || m.type === '花火AI') continue;
    let cv = 0;
    for (const [d, accts] of Object.entries(m.days)) {
      for (const [acct, mc] of Object.entries(accts)) {
        if (state.acct !== 'all' && acct !== state.acct) continue;
        cv += (mc.m && mc.m.cv) || 0;
      }
    }
    if (cv > 0) cvByName.set(m.name, cv);
  }
  // 统计（分母=合并去重后的素材数）
  let total = 0, run = 0, passed = 0, submit = 0;
  for (const [name, e] of pool) {
    total += 1;
    if (cvByName.has(name)) run += 1;
    const audit = currentAuditOf(e);
    if (audit !== null && audit !== undefined) {
      submit += 1;
      if (audit === '过审') passed += 1;
    }
  }
  todayStatsCache = {total, run, passed, submit, today};
  return todayStatsCache;
}
const selDates = () => new Set(state.dates);

/* 从嵌套 days 聚合指标+质量。支持三种结构：
   accounts: {date: metrics}
   plans/groups: {date: {acct: metrics}}
   materials: {date: {acct: {m, q}}} */
function aggDays(days) {
  const m = ZM(), q = ZQ();
  for (const d of selDates()) {
    const day = days[d];
    if (!day) continue;
    if (day.sp !== undefined) {
      addM(m, day);
    } else {
      for (const [acct, val] of Object.entries(day)) {
        if (state.acct !== 'all' && acct !== state.acct) continue;
        if (val && val.m) { addM(m, val.m); addQ(q, val.q || {}); }
        else addM(m, val || {});
      }
    }
  }
  return {m, q};
}
function derive(m, q) {
  const r = {...m};
  r.act_rate = m.im ? m.ac/m.im*100 : 0;
  r.cvr = m.ac ? m.cv/m.ac*100 : 0;
  r.deep_rate = m.cv ? m.dp/m.cv*100 : 0;
  r.cpa = m.cv ? m.sp/m.cv : 0;
  r.o10r = m.va ? m.o10/m.va*100 : 0;
  // 回流开口：当日开口1次超过有效获客的部分（历史用户回流/非获客开口）
  r.back_open = Math.max(0, m.o1 - m.va);
  r.mat_click_rate = q.qmi ? m.ac/q.qmi*100 : 0;
  r.cover_rate = q.ce ? q.cc/q.ce*100 : 0;
  r.p3 = q.qi ? q.p3/q.qi : 0;
  r.p5 = q.qi ? q.p5/q.qi : 0;
  r.fin = q.qi ? q.fn/q.qi : 0;
  r.qmi = q.qmi; r.qi = q.qi; r.ce = q.ce; r.cc = q.cc;
  return r;
}

const fmtM = v => '¥' + v.toLocaleString('zh-CN', {minimumFractionDigits:2, maximumFractionDigits:2});
const fmtI = v => Math.round(v).toLocaleString('zh-CN');
const fmtP = v => v.toFixed(2) + '%';
const fmtP1 = v => v.toFixed(1) + '%';

/* ---------------- TAB 切换 ---------------- */
function switchTab(t) {
  state.tab = t;
  document.getElementById('tab1').style.display = t === 1 ? '' : 'none';
  document.getElementById('tab2').style.display = t === 2 ? '' : 'none';
  document.getElementById('tab3').style.display = t === 3 ? '' : 'none';
  document.getElementById('tab4').style.display = t === 4 ? '' : 'none';
  document.getElementById('tabBtn1').classList.toggle('active', t === 1);
  document.getElementById('tabBtn2').classList.toggle('active', t === 2);
  document.getElementById('tabBtn3').classList.toggle('active', t === 3);
  document.getElementById('tabBtn4').classList.toggle('active', t === 4);
}

/* ---------------- 顶部 chips（共享） ---------------- */
function renderChips() {
  // 日期下拉多选
  const btn = document.getElementById('dateDropdownBtn');
  btn.textContent = state.dates.length === DATA.dates.length ? '全部日期 ▾'
    : '已选 ' + state.dates.length + ' 天 ▾';
  const grid = document.getElementById('ddGrid');
  grid.innerHTML = DATA.dates.map(d =>
    '<div class="dd-item' + (state.dates.includes(d) ? ' sel' : '') + '" data-d="' + d + '">' + d.slice(5) + '</div>').join('');
  grid.querySelectorAll('.dd-item').forEach(el => el.addEventListener('click', () => {
    const d = el.dataset.d;
    state.dates = state.dates.includes(d)
      ? (state.dates.length > 1 ? state.dates.filter(x => x !== d) : state.dates)
      : [...state.dates, d].sort();
    renderAll();
  }));

  const aw = document.getElementById('acctChips');
  const accts = DATA.accounts.map(a => a.id);
  aw.innerHTML = '<span class="acct-chip' + (state.acct==='all'?' sel':'') + '" data-a="all">全部账户</span>' +
    accts.map(a => '<span class="acct-chip' + (state.acct===a?' sel':'') + '" data-a="' + a + '">' + a + '</span>').join('');
  aw.querySelectorAll('.acct-chip').forEach(el => el.addEventListener('click', () => {
    state.acct = el.dataset.a;
    renderAll();
  }));
}
function initDateDropdown() {
  const panel = document.getElementById('dateDropdownPanel');
  document.getElementById('dateDropdownBtn').addEventListener('click', e => {
    e.stopPropagation();
    panel.style.display = panel.style.display === 'none' ? '' : 'none';
  });
  document.addEventListener('click', () => { panel.style.display = 'none'; });
  panel.addEventListener('click', e => e.stopPropagation());
  panel.querySelectorAll('.range-btn[data-dd]').forEach(b => b.addEventListener('click', () => {
    const mode = b.dataset.dd;
    if (mode === 'latest') state.dates = [DATA.dates[DATA.dates.length-1]];
    else if (mode === '7d') state.dates = DATA.dates.slice(-7);
    else if (mode === 'all') state.dates = [...DATA.dates];
    else state.dates = [];
    panel.querySelectorAll('.range-btn').forEach(x => x.classList.remove('active'));
    b.classList.add('active');
    renderAll();
  }));
}

/* ---------------- KPI 卡片渲染 ---------------- */
function kpiCard(label, valueHtml, sub, accent) {
  return '<div class="kpi-card' + (accent ? ' accent' : '') + '">' +
    '<div class="kpi-label">' + label + '</div>' +
    '<div class="kpi-value">' + valueHtml + '</div>' +
    '<div class="kpi-sub">' + sub + '</div></div>';
}
function renderKpi1() {
  const tot = ZM(), tq = ZQ();
  for (const a of DATA.accounts) {
    if (state.acct !== 'all' && a.id !== state.acct) continue;
    const {m} = aggDays(a.days);
    addM(tot, m);
  }
  const t = derive(tot, tq);
  // 环比（仅单日）
  const prevD = DATA.dates[DATA.dates.indexOf(state.dates[0]) - 1];
  let diff = (cur, prev) => {
    if (!prevD || state.dates.length !== 1) return '';
    const cls = cur >= prev ? 'inc' : 'dec';
    return '<span class="tc-diff ' + cls + '">' + (cur >= prev ? '+' : '') + (cur - prev).toLocaleString('zh-CN') + '</span>';
  };
  let prevTot = ZM();
  if (prevD) {
    const save = state.dates; state.dates = [prevD];
    for (const a of DATA.accounts) { if (state.acct !== 'all' && a.id !== state.acct) continue; addM(prevTot, aggDays(a.days).m); }
    state.dates = save;
  }
  const g = document.getElementById('kpiGrid1');
  const rows = [
    ['总消耗', fmtM(t.sp), diff(t.sp, prevTot.sp) + '较昨日', false],
    ['曝光数', fmtI(t.im), '总曝光', false],
    ['行为数', fmtI(t.ac), '约等于点击', false],
    ['行为率', fmtP(t.act_rate), '行为÷曝光', false],
    ['转化数', fmtI(t.cv), diff(t.cv, prevTot.cv) + '转化(计费)', false],
    ['转化率', fmtP(t.cvr), '转化÷行为', false],
    ['平均CPA', fmtM(t.cpa), '花费÷转化', false],
    ['深转数', state.acct === 'all' ? fmtI(deepRealTotal()) : '单账户未回传',
     state.acct === 'all' ? '销售反馈' : '深转回传数据不分账户', false],
    ['深转率', state.acct === 'all' ? (t.cv ? fmtP(deepRealTotal()/t.cv*100) : fmtP(0)) : '单账户未回传',
     state.acct === 'all' ? '销售反馈' : '深转回传数据不分账户', false],
    ['有效获客', fmtI(t.va), '有效获客数', false],
    ['开口1次', fmtI(t.o1), '开口率 <b class="open-rate">' + (t.va ? fmtP(t.o1/t.va*100) : fmtP(0)) + '</b>（开口1次/有效获客）· 回流开口 ' + fmtI(Math.max(0, t.o1 - t.va)), true],
    ['开口3次', fmtI(t.o3), '开口率 <b class="open-rate">' + (t.va ? fmtP(t.o3/t.va*100) : fmtP(0)) + '</b>（开口3次/有效获客）', false],
    ['开口5次', fmtI(t.o5), '开口率 <b class="open-rate">' + (t.va ? fmtP(t.o5/t.va*100) : fmtP(0)) + '</b>（开口5次/有效获客）', false],
    ['开口10次', fmtI(t.o10), '开口率 <b class="open-rate">' + (t.va ? fmtP(t.o10/t.va*100) : fmtP(0)) + '</b>（开口10次/有效获客）', false],
  ];
  g.innerHTML = rows.map(r => kpiCard(r[0], r[1], r[2], r[3])).join('');
}
function renderKpi2() {
  const names = new Set();
  let tot = ZM(), tq = ZQ();
  for (const m of DATA.materials) {
    const {m: mm, q} = aggDays(m.days);
    // 素材总数与明细表同口径联动：所选日期内有投放数据的素材按名称去重
    if (mm.sp > 0 || mm.im > 0 || mm.cv > 0 || mm.ac > 0 || mm.dp > 0) {
      names.add(m.name);
      addM(tot, mm); addQ(tq, q);
    }
  }
  const t = derive(tot, tq);
  // 素材页过审率/跑出率：素材池=台账∪报表（产出日在所选日期窗口内，排除AI/花火/无日期）
  const subByName = new Map(), mainByName = new Map();
  for (const l of (DATA.ledger_sub || [])) {
    if (!subByName.has(l.name)) subByName.set(l.name, []);
    subByName.get(l.name).push(l);
  }
  for (const l of (DATA.ledger_main || [])) {
    if (!mainByName.has(l.name)) mainByName.set(l.name, []);
    mainByName.get(l.name).push(l);
  }
  const selSet = selDates();
  const pool2 = new Map();
  const addLedger2 = (map, src) => {
    for (const [ln, recs] of map) {
      if (excludePass3w(ln)) continue;
      // 素材池按「上传日期」落在所选日期窗口
      if (!recs[0].upload || !selSet.has(recs[0].upload)) continue;
      const e = pool2.get(ln) || {name: ln, subAudit: null, mainAudit: null};
      if (src === 'sub') e.subAudit = recs[0].audit;
      else e.mainAudit = recs[0].audit;
      pool2.set(ln, e);
    }
  };
  addLedger2(subByName, 'sub');
  addLedger2(mainByName, 'main');
  for (const m of DATA.materials) {
    if (m.type === 'AI' || m.type === '花火AI') continue;
    if (m.type !== '视频' && m.type !== '图文') continue;
    if (excludePass3w(m.name)) continue;
    // 报表首现日落在窗口的素材进池（台账漏记兜底）
    const days = Object.keys(m.days).sort();
    if (!days.length || !selSet.has(days[0])) continue;
    const e = pool2.get(m.name) || {name: m.name, subAudit: null, mainAudit: null};
    e.cv = 0;
    for (const [d, accts] of Object.entries(m.days)) {
      if (!selSet.has(d)) continue;
      for (const [acct, mc] of Object.entries(accts)) {
        if (state.acct !== 'all' && acct !== state.acct) continue;
        e.cv += (mc.m && mc.m.cv) || 0;
      }
    }
    pool2.set(m.name, e);
  }
  // 随账户筛选
  let poolN = 0, passN = 0, submitN = 0, runN = 0;
  for (const [name, e] of pool2) {
    if (state.acct !== 'all') {
      const hasLedger = state.acct === '125240890'
        ? (e.subAudit !== null && e.subAudit !== undefined)
        : (e.mainAudit !== null && e.mainAudit !== undefined);
      if (!hasLedger && e.cv === undefined) continue;
    }
    poolN += 1;
    if (e.cv > 0) runN += 1;
    const audit = currentAuditOf(e);
    if (audit !== null && audit !== undefined) {
      submitN += 1;
      if (audit === '过审') passN += 1;
    }
  }
  const g = document.getElementById('kpiGrid2');
  const rows = [
    ['素材总数', fmtI(names.size), '按名称去重 · 随日期筛选', false],
    ['花费', fmtM(t.sp), '素材花费', false],
    ['素材曝光', fmtI(t.qmi), '素材曝光数', false],
    ['素材点击率', fmtP(t.mat_click_rate), '行为÷素材曝光', false],
    ['封面点击率', fmtP(t.cover_rate), '封面点击÷封面曝光', false],
    ['3秒播放率', fmtP1(t.p3), '曝光加权', false],
    ['5秒播放率', fmtP1(t.p5), '曝光加权', false],
    ['完播率', fmtP1(t.fin), '曝光加权', false],
    ['过审率', submitN ? fmtP(passN / submitN * 100) : fmtP(0), '过审÷提交（' + passN + '/' + submitN + '）· 随账户筛选', true],
    ['跑出率', poolN ? fmtP(runN / poolN * 100) : fmtP(0), '有转化÷素材池（' + runN + '/' + poolN + '）', true],
  ];
  g.innerHTML = rows.map((r,i) => kpiCard(r[0], r[1], r[2], i===0 || i>=8)).join('');
}

/* ---------------- 漏斗图 ---------------- */
let chartFunnel = null;
function renderFunnel() {
  const tot = ZM();
  for (const a of DATA.accounts) {
    if (state.acct !== 'all' && a.id !== state.acct) continue;
    addM(tot, aggDays(a.days).m);
  }
  const stages = [
    ['转化', tot.cv],
    ['有效获客', tot.va], ['开口1次', tot.o1], ['开口3次', tot.o3],
    ['开口5次', tot.o5], ['开口10次', tot.o10],
    [state.acct === 'all' ? '深转' : '深转(单账户未回传)', state.acct === 'all' ? deepRealTotal() : 0],
  ];
  const colors = ['#3B82F6','#8B5CF6','#A78BFA','#F59E0B','#FBBF24','#10B981','#60A5FA'];
  if (chartFunnel) chartFunnel.destroy();
  chartFunnel = new Chart(document.getElementById('chartFunnel'), {
    type: 'bar',
    data: {labels: stages.map(s => s[0]),
      datasets: [{data: stages.map(s => s[1]), backgroundColor: colors, borderRadius: 4}]},
    options: {indexAxis: 'y', responsive: true, maintainAspectRatio: false,
      plugins: {legend: {display: false},
        tooltip: {callbacks: {label: c => ' ' + fmtI(c.raw)}}},
      scales: {x: {beginAtZero: true, ticks: {font: {size: 10}}},
        y: {ticks: {font: {size: 11}}}}}
  });
}

/* ---------------- 逐日趋势 ---------------- */
let chartTrend = null, chartCpa = null;
function dailySeries() {
  const spend = [], conv = [], deepReal = [], cpa = [], cvr = [], labels = [];
  for (const d of selDates()) {
    const s = ZM();
    for (const a of DATA.accounts) {
      if (state.acct !== 'all' && a.id !== state.acct) continue;
      const day = a.days[d];
      if (day) addM(s, day);
    }
    labels.push(d.slice(5));
    spend.push(+s.sp.toFixed(2));
    conv.push(+s.cv.toFixed(1));
    deepReal.push(+(state.acct === 'all' ? ((DATA.deep_real && DATA.deep_real[d]) || 0) : 0).toFixed(1));
    cpa.push(s.cv ? +(+s.sp/s.cv).toFixed(2) : 0);
    cvr.push(s.ac ? +(s.cv/s.ac*100).toFixed(2) : 0);
  }
  return {labels, spend, conv, deepReal, cpa, cvr};
}
function renderTrend() {
  const s = dailySeries();
  const base = {responsive: true, maintainAspectRatio: false,
    plugins: {legend: {labels: {boxWidth: 12, font: {size: 11}}}},
    scales: {y: {beginAtZero: true, ticks: {font: {size: 10}}}, x: {ticks: {font: {size: 10}}}}};
  if (chartTrend) chartTrend.destroy();
  chartTrend = new Chart(document.getElementById('chartTrend'), {
    data: {labels: s.labels, datasets: [
      {type:'bar', label:'花费', data:s.spend, backgroundColor:'#BFDBFE', borderRadius:3, yAxisID:'y'},
      {type:'line', label:'转化', data:s.conv, borderColor:'#3B82F6', tension:.3, pointRadius:2, yAxisID:'y1'},
      {type:'line', label: state.acct === 'all' ? '深转' : '深转(单账户未回传)', data: s.deepReal, borderColor:'#F59E0B', tension:.3, pointRadius:2, yAxisID:'y1'}
    ]},
    options: Object.assign({}, base, {scales: {
      y: Object.assign({}, base.scales.y, {position:'left', grid:{drawOnChartArea:false}}),
      y1: Object.assign({}, base.scales.y, {position:'right', grid:{drawOnChartArea:false}})}})
  });
  if (chartCpa) chartCpa.destroy();
  chartCpa = new Chart(document.getElementById('chartCpa'), {
    data: {labels: s.labels, datasets: [
      {type:'line', label:'CPA', data:s.cpa, borderColor:'#8B5CF6', tension:.3,
       pointRadius:5, pointHoverRadius:7, yAxisID:'y'},
      {type:'line', label:'转化率%', data:s.cvr, borderColor:'#10B981', tension:.3,
       pointRadius:5, pointHoverRadius:7, yAxisID:'y1'}
    ]},
    options: Object.assign({}, base, {
      interaction: {mode: 'nearest', intersect: false},
      scales: {
        y: Object.assign({}, base.scales.y, {position:'left', grid:{drawOnChartArea:false}}),
        y1: Object.assign({}, base.scales.y, {position:'right', grid:{drawOnChartArea:false}})}})
  });
}

/* ---------------- 账户总览表 ---------------- */
function renderAcct() {
  const cols = [['账户','id','txt'],['花费','sp','fmtM'],['曝光','im','fmtI'],['行为数','ac','fmtI'],
    ['行为率','act_rate','fmtP'],['转化','cv','fmtI'],['转化率','cvr','fmtP'],['CPA','cpa','fmtM'],
    ['深转','dp','fmtI'],['深转率','deep_rate','fmtP'],['有效获客','va','fmtI'],
    ['开口1','o1','fmtI'],['开口3','o3','fmtI'],['开口5','o5','fmtI'],['开口10','o10','fmtI']];
  const thead = document.querySelector('#acctTable thead');
  thead.innerHTML = '<tr>' + cols.map(c => '<th data-k="' + c[1] + '">' + c[0] + '</th>').join('') + '</tr>';
  const rows = DATA.accounts.map(a => {
    const t = derive(aggDays(a.days).m, ZQ());
    return {id: a.id, ...t, _raw: t};
  });
  rows.sort((a,b) => b.sp - a.sp);
  const body = document.getElementById('acctBody');
  body.innerHTML = rows.map(r => '<tr style="cursor:pointer" data-acct="' + r.id + '">' +
    cols.map(c => {
      if (c[2]==='txt') return '<td><span class="person-badge" style="background:#ECFDF5;color:#047857">' + r.id + '</span></td>';
      if (c[1]==='dp' || c[1]==='deep_rate') return '<td class="num num-zero">—</td>';
      const v = r[c[1]]||0;
      if (c[2]==='fmtI' && v===0) return '<td class="num num-zero">0</td>';
      if (c[1]==='dp' && v>0) return '<td class="gaoquan-cell">' + fmtI(v) + '</td>';
      return '<td class="num">' + (c[2]==='fmtM'?fmtM(v):c[2]==='fmtP'?fmtP(v):fmtI(v)) + '</td>';
    }).join('') + '</tr>').join('') || '<tr><td colspan="15" class="empty-state">暂无数据</td></tr>';
  body.querySelectorAll('tr[data-acct]').forEach(tr => tr.addEventListener('click', () => {
    state.acct = (state.acct === tr.dataset.acct) ? 'all' : tr.dataset.acct;
    renderAll();
  }));
}

/* ---------------- TAB1 聚合维度表 ---------------- */
const DIM_COLS = [['名称','name','txt'],['花费','sp','fmtM'],['曝光','im','fmtI'],['行为数','ac','fmtI'],
  ['行为率','act_rate','fmtP'],['转化','cv','fmtI'],['转化率','cvr','fmtP'],['CPA','cpa','fmtM'],
  ['深转','dp','fmtI'],['深转率','deep_rate','fmtP'],['有效获客','va','fmtI'],
  ['开口1','o1','fmtI'],['开口3','o3','fmtI'],['开口5','o5','fmtI'],['开口10','o10','fmtI'],
  ['开口10率','o10r','o10rate']];
const MAT_COLS = [['素材名称','name','name'],['类型','type','type'],['编导','person','person'],
  ['花费','sp','fmtM'],['转化','cv','fmtI'],['转化成本','cpa','fmtM'],
  ['开口1','o1','fmtI'],['开口3','o3','fmtI'],['开口5','o5','fmtI'],['开口10','o10','fmtI'],
  ['开口10率','o10r','o10rate'],
  ['回流开口','back_open','back'],
  ['深转','dp','fmtI'],['有效获客','va','fmtI'],
  ['封面曝光','ce','fmtI'],['封面点击率','cover_rate','fmtP'],
  ['素材曝光','qmi','fmtI'],['素材点击率','mat_click_rate','fmtP'],
  ['行为数','ac','fmtI'],['行为率','act_rate','fmtP'],
  ['3秒播放率','p3','fmtP'],['5秒播放率','p5','fmtP'],['完播率','fin','fmtP'],['播放','','play']];

function cellHtml(c, r) {
  if (c[2]==='name') return '<td class="mat-name">' + r.name + '</td>';
  if (c[2]==='type') {
    const t = r.type || '视频';
    const cls = t==='图文' ? 'type-tuwen' : t==='AI' ? 'type-ai' : t==='花火AI' ? 'type-huahuo' : 'type-video';
    return '<td><span class="person-badge ' + cls + '">' + (t==='AI'?'平台AI':t) + '</span></td>';
  }
  if (c[2]==='person') {
    const p = r.person || '其他';
    return '<td><span class="person-badge" style="background:' + (PERSON_BG[p]||'#F8FAFC') + ';color:' + (PERSON_COLORS[p]||'#64748B') + '">' + p + '</span></td>';
  }
  if (c[2]==='play') return r.content
    ? '<td><button class="btn-play" data-vname="' + r.name.replace(/&/g,'&amp;').replace(/"/g,'&quot;') + '">▶</button></td>'
    : '<td class="num-zero">—</td>';
  if (c[2]==='txt') return '<td>' + r[c[1]] + '</td>';
  if (c[1]==='dp') return '<td class="num num-zero">—</td>';
  if (c[1]==='deep_rate') return '<td class="num num-zero">—</td>';
  const v = r[c[1]]||0;
  if (c[2]==='o10rate') {
    if (!v) return '<td class="num num-zero">0.00%</td>';
    return '<td class="num" style="color:#0EA5E9;font-weight:600">' + fmtP(v) + '</td>';
  }
  if (c[2]==='back') {
    if (!v) return '<td class="num num-zero">0</td>';
    return '<td class="num" style="color:#0EA5E9;font-weight:600">+' + fmtI(v) + '</td>';
  }
  if (c[2]==='fmtI' && v===0) return '<td class="num num-zero">0</td>';
  if (c[1]==='dp' && v>0) return '<td class="gaoquan-cell">' + fmtI(v) + '</td>';
  return '<td class="num">' + (c[2]==='fmtM'?fmtM(v):c[2]==='fmtP'?fmtP(v):fmtI(v)) + '</td>';
}

/* ---------------- 通用分页 ---------------- */
const PAGE_SIZE = 30;
const PASS_PAGE_SIZE = 10;
const pageState = {dimTable: 1, matTable: 1};
const passPageState = {0: 1, 1: 1, 2: 1};

function renderPager(tableId, total) {
  const pages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const cur = pageState[tableId];
  if (cur > pages) pageState[tableId] = pages;
  const pager = document.getElementById(tableId === 'dimTable' ? 'dimPager' : 'matPager');
  if (!pager) return;
  const p = pageState[tableId];
  let btns = '';
  const start = Math.max(1, Math.min(p - 2, pages - 4));
  const end = Math.min(pages, start + 4);
  if (p > 1) btns += '<button class="page-btn" data-pg="' + (p-1) + '">‹</button>';
  for (let i = start; i <= end; i++) {
    btns += '<button class="page-btn' + (i === p ? ' active' : '') + '" data-pg="' + i + '">' + i + '</button>';
  }
  if (p < pages) btns += '<button class="page-btn" data-pg="' + (p+1) + '">›</button>';
  pager.innerHTML = '<span class="pager-info">共 ' + total + ' 条 · ' + pages + ' 页</span>' + btns;
  pager.querySelectorAll('.page-btn[data-pg]').forEach(b => b.addEventListener('click', () => {
    pageState[tableId] = +b.dataset.pg;
    if (tableId === 'dimTable') renderDim();
    else renderMaterials();
  }));
}
function sliceRows(rows, tableId) {
  const p = pageState[tableId];
  const start = (p - 1) * PAGE_SIZE;
  return rows.slice(start, start + PAGE_SIZE);
}

function renderDim() {
  const label = {material:'素材名称', plan:'计划', group:'组'}[state.dim];
  document.getElementById('dimLabel').textContent = label;
  let rows = [];
  if (state.dim === 'material') {
    rows = DATA.materials.map(m => {
      const t = derive(aggDays(m.days).m, aggDays(m.days).q);
      return {name: m.name, ...t};
    }).filter(r => r.sp > 0 || r.im > 0 || r.cv > 0 || r.ac > 0);
  } else if (state.dim === 'plan') {
    rows = DATA.plans.map(p => {
      const t = derive(aggDays(p.days).m, ZQ());
      return {name: p.name, ...t};
    }).filter(r => r.sp > 0 || r.im > 0 || r.cv > 0 || r.ac > 0);
  } else {
    rows = DATA.groups.map(g => {
      const t = derive(aggDays(g.days).m, ZQ());
      return {name: g.name, ...t};
    }).filter(r => r.sp > 0 || r.im > 0 || r.cv > 0 || r.ac > 0);
  }
  const sk = sortState['dimTable'];
  if (sk) rows.sort((a,b) => sk.dir === 'asc' ? (a[sk.k]||0)-(b[sk.k]||0) : (b[sk.k]||0)-(a[sk.k]||0));
  else rows.sort((a,b) => b.sp - a.sp);
  document.getElementById('dimCount').textContent = rows.length;
  const paged = sliceRows(rows, 'dimTable');
  const thead = document.querySelector('#dimTable thead');
  thead.innerHTML = '<tr>' + DIM_COLS.map(c => '<th data-k="' + c[1] + '">' + c[0] + '</th>').join('') + '</tr>';
  document.getElementById('dimBody').innerHTML = paged.map(r => '<tr>' +
    DIM_COLS.map(c => cellHtml(c, r)).join('') + '</tr>').join('') ||
    '<tr><td colspan="15" class="empty-state">暂无数据</td></tr>';
  renderPager('dimTable', rows.length);
}

/* ---------------- 分时模块 ---------------- */
let chartHour = null;
function hourlyAgg() {
  // 返回 24 小时指标数组（跨日按小时累计）
  const hours = Array.from({length: 24}, () => ZM());
  for (const a of DATA.accounts) {
    if (state.acct !== 'all' && a.id !== state.acct) continue;
    const hd = DATA.hourly[a.id] || {};
    for (const d of selDates()) {
      const day = hd[d];
      if (!day) continue;
      for (const [h, m] of Object.entries(day)) {
        addM(hours[+h], m);
      }
    }
  }
  return hours.map(m => derive(m, ZQ()));
}
function renderHourly() {
  const hours = hourlyAgg();
  const note = document.getElementById('hourlyNote');
  note.textContent = state.dates.length > 1 ? '（按小时跨日累计）' : '（' + state.dates[0] + '）';
  // 柱线图：柱=花费，线=转化
  const base = {responsive: true, maintainAspectRatio: false,
    plugins: {legend: {labels: {boxWidth: 12, font: {size: 11}}}},
    scales: {y: {beginAtZero: true, ticks: {font: {size: 10}}}, x: {ticks: {font: {size: 10}}}}};
  if (chartHour) chartHour.destroy();
  chartHour = new Chart(document.getElementById('chartHour'), {
    data: {labels: Array.from({length:24}, (_,i) => i + '时'),
      datasets: [
        {type:'bar', label:'花费', data: hours.map(h => +h.sp.toFixed(2)), backgroundColor:'#BFDBFE', borderRadius:2, yAxisID:'y'},
        {type:'line', label:'转化', data: hours.map(h => +h.cv.toFixed(1)), borderColor:'#3B82F6', tension:.3, pointRadius:2, yAxisID:'y1'},
        {type:'line', label:'开口1次', data: hours.map(h => +h.o1.toFixed(1)), borderColor:'#10B981', tension:.3, pointRadius:2, yAxisID:'y1'}
      ]},
    options: Object.assign({}, base, {scales: {
      y: Object.assign({}, base.scales.y, {position:'left', grid:{drawOnChartArea:false}}),
      y1: Object.assign({}, base.scales.y, {position:'right', grid:{drawOnChartArea:false}})}})
  });
  // 优劣势时段判定口径（2026-11-02 用户拍板，均以「有投放的时段」计算均值）
  // 优质：转化率 ≥ 平均×1.15 且 花费 ≥ 平均×0.5（转化好 + 有量）
  // 差：转化率 < 平均×0.85 且 花费 ≥ 平均×0.5（花了钱但转化差）
  const active = hours.filter(h => h.cv > 0 || h.sp > 0);
  document.getElementById('hourCaliber').innerHTML =
    '判定口径：先取「有花费的时段」算均值，<b>🟢 优质时段</b> = 转化率 ≥ 均值×1.15 且 花费 ≥ 均值×0.5；' +
    '<b>🔴 差时段</b> = 转化率 < 均值×0.85 且 花费 ≥ 均值×0.5（花了钱但转化差，可考虑不投）；其余不标记。';
  if (active.length) {
    const avgCvr = active.reduce((s,h) => s + h.cvr, 0) / active.length;
    const avgSp = active.reduce((s,h) => s + h.sp, 0) / active.length;
    const good = hours.map((h,i) => [i,h]).filter(([i,h]) => h.cv > 0 && h.cvr >= avgCvr * 1.15 && h.sp >= avgSp * 0.5).map(([i]) => i);
    const bad = hours.map((h,i) => [i,h]).filter(([i,h]) => (h.cv > 0 || h.sp > 0) && h.cvr < avgCvr * 0.85 && h.sp >= avgSp * 0.5).map(([i]) => i);
    document.getElementById('hourTags').innerHTML =
      (good.length ? '<span class="hour-tag good">🟢 优质时段（转化率高）: ' + good.map(h => h + '时').join('、') + '</span>' : '') +
      (bad.length ? '<span class="hour-tag bad">🔴 差时段（考虑不投）: ' + bad.map(h => h + '时').join('、') + '</span>' : '') +
      (good.length || bad.length ? '' : '<span class="hour-tag">暂无显著优差时段</span>');
  } else {
    document.getElementById('hourTags').innerHTML = '<span class="hour-tag">所选日期无分时数据</span>';
  }
  // 热力表（表头居中；含开口1/3/5/10）
  const maxVals = {sp: Math.max(...hours.map(h => h.sp), 1), ac: Math.max(...hours.map(h => h.ac), 1),
    cv: Math.max(...hours.map(h => h.cv), 1), cvr: Math.max(...hours.map(h => h.cvr), 1),
    o1: Math.max(...hours.map(h => h.o1), 1), o3: Math.max(...hours.map(h => h.o3), 1),
    o5: Math.max(...hours.map(h => h.o5), 1), o10: Math.max(...hours.map(h => h.o10), 1)};
  const cols = [['花费','sp','fmtM'],['行为','ac','fmtI'],['转化','cv','fmtI'],['转化率','cvr','fmtP'],
    ['开口1','o1','fmtI'],['开口3','o3','fmtI'],['开口5','o5','fmtI'],['开口10','o10','fmtI']];
  document.querySelector('#heatTable thead').innerHTML = '<tr><th style="cursor:default">小时</th>' +
    cols.map(c => '<th style="cursor:default">' + c[0] + '</th>').join('') + '</tr>';
  document.getElementById('heatBody').innerHTML = hours.map((h,i) => {
    return '<tr><td class="hour-label">' + i + ':00</td>' + cols.map(c => {
      const v = h[c[1]] || 0;
      const ratio = v / maxVals[c[1]];
      const bg = ratio > 0.9 ? 'rgba(30,64,175,.55)' : ratio > 0.6 ? 'rgba(59,130,246,.45)'
        : ratio > 0.3 ? 'rgba(96,165,250,.32)' : ratio > 0 ? 'rgba(147,197,253,.18)' : '#F8FAFC';
      const color = ratio > 0.6 ? '#fff' : '#334155';
      return '<td class="heat-cell" style="background:' + bg + ';color:' + color + '">' +
        (c[2]==='fmtM'?fmtM(v):c[2]==='fmtP'?fmtP(v):fmtI(v)) + '</td>';
    }).join('') + '</tr>';
  }).join('');
}

/* ---------------- TAB2 ---------------- */
function renderTypes() {
  const agg = {视频: {cnt:new Set(), m:ZM(), q:ZQ()}, 图文: {cnt:new Set(), m:ZM(), q:ZQ()},
               AI: {cnt:new Set(), m:ZM(), q:ZQ()}, 花火AI: {cnt:new Set(), m:ZM(), q:ZQ()}};
  for (const m of DATA.materials) {
    const t = m.type || '视频';
    const a = agg[t] || agg['视频'];
    const {m: mm, q} = aggDays(m.days);
    // 条数随日期联动：所选日期内有投放数据的素材才计数
    if (mm.sp > 0 || mm.im > 0 || mm.cv > 0 || mm.ac > 0 || mm.dp > 0) {
      a.cnt.add(m.name);
      addM(a.m, mm); addQ(a.q, q);
    }
  }
  const wrap = document.getElementById('typeRow');
  const defs = [['视频','filter-btn-video'],['图文','filter-btn-tuwen'],['AI','filter-btn-ai'],['花火AI','filter-btn-huahuo']];
  wrap.innerHTML = defs.map(([t, cls]) => {
    const a = agg[t];
    const d = derive(a.m, a.q);
    return '<div class="kpi-card" style="margin:0;cursor:pointer" data-type="' + t + '">' +
      '<div class="kpi-label"><span class="person-badge ' + cls + '">' + (t==='AI'?'平台AI':t) + '</span></div>' +
      '<div class="kpi-value" style="font-size:18px">' + fmtM(d.sp) + '</div>' +
      '<div class="kpi-sub">' + a.cnt.size + ' 条素材 · 转化 ' + fmtI(d.cv) + ' · 点击率 ' + fmtP(d.mat_click_rate) + ' · CPA ' + fmtM(d.cpa) + '</div>' +
    '</div>';
  }).join('');
}
function renderPersons() {
  const map = {};
  for (const m of DATA.materials) {
    const p = m.person || '其他';
    if (!map[p]) map[p] = {cnt: new Set(), m: ZM(), q: ZQ(), runCnt: 0, passN: 0, submitN: 0, runNames: [], passNames: [], failNames: []};
    const {m: mm, q} = aggDays(m.days);
    // 条数随日期联动：所选日期内有投放数据的素材才计数
    if (mm.sp > 0 || mm.im > 0 || mm.cv > 0 || mm.ac > 0 || mm.dp > 0) {
      map[p].cnt.add(m.name);
      addM(map[p].m, mm); addQ(map[p].q, q);
      if (mm.cv > 0) { map[p].runCnt += 1; map[p].runNames.push(m.name); }
    }
  }
  // 每个编导的过审统计：台账池按编导归集（同名合并去重，严格合并状态）
  const subByName = new Map(), mainByName = new Map();
  for (const l of (DATA.ledger_sub || [])) {
    if (!subByName.has(l.name)) subByName.set(l.name, []);
    subByName.get(l.name).push(l);
  }
  for (const l of (DATA.ledger_main || [])) {
    if (!mainByName.has(l.name)) mainByName.set(l.name, []);
    mainByName.get(l.name).push(l);
  }
  const merged = new Map();   // name -> {subAudit, mainAudit, upload}
  for (const [ln, recs] of subByName) {
    const e = merged.get(ln) || {subAudit: null, mainAudit: null, upload: recs[0].upload};
    e.subAudit = recs[0].audit;
    if (recs[0].upload < e.upload) e.upload = recs[0].upload;
    merged.set(ln, e);
  }
  for (const [ln, recs] of mainByName) {
    const e = merged.get(ln) || {subAudit: null, mainAudit: null, upload: recs[0].upload};
    e.mainAudit = recs[0].audit;
    if (recs[0].upload < e.upload) e.upload = recs[0].upload;
    merged.set(ln, e);
  }
  const personLedger = {};
  for (const p of Object.keys(map)) personLedger[p] = {passN: 0, submitN: 0, passNames: [], failNames: []};
  const selSet = selDates();
  for (const [name, e] of merged) {
    if (excludePass3w(name)) continue;
    // 当日过审率：只算所选日期内上传的素材（随日期联动）
    if (!e.upload || !selSet.has(e.upload)) continue;
    const p = personOf3(name);
    if (!personLedger[p]) personLedger[p] = {passN: 0, submitN: 0, passNames: [], failNames: []};
    personLedger[p].submitN += 1;
    const audit = currentAuditOf(e);
    if (audit === '过审') { personLedger[p].passN += 1; personLedger[p].passNames.push(name); }
    else if (audit) personLedger[p].failNames.push(name);
  }
  const wrap = document.getElementById('personRow');
  const list = Object.entries(map).sort((a,b) => b[1].m.sp - a[1].m.sp);
  wrap.innerHTML = list.map(([p, a]) => {
    const c = PERSON_COLORS[p] || '#64748B', bg = PERSON_BG[p] || '#F8FAFC';
    const d = derive(a.m, a.q);
    const pl = personLedger[p] || {passN: 0, submitN: 0, passNames: [], failNames: []};
    const runRate = a.cnt.size ? (a.runCnt / a.cnt.size * 100) : 0;
    const open10Rate = a.cnt.size ? (d.o10 / a.cnt.size * 100) : 0;
    const passRate = pl.submitN ? (pl.passN / pl.submitN * 100) : 0;
    // 悬停明细：过审名单与卡审名单换行显示
    const passList = pl.passNames.length ? pl.passNames.join('&#10;') : '无';
    const failList = pl.failNames.length ? pl.failNames.join('&#10;') : '无';
    const auditTip = '【过审 ' + pl.passN + '/' + pl.submitN + '】&#10;' + passList +
      '&#10;&#10;【卡审】&#10;' + failList;
    return '<div class="kpi-card" style="margin:0;cursor:pointer" data-person="' + p + '">' +
      '<div class="kpi-label"><span class="person-badge" style="background:' + bg + ';color:' + c + '">' + p + '</span></div>' +
      '<div class="kpi-value" style="font-size:17px;color:' + c + '">' + fmtM(d.sp) + '</div>' +
      '<div class="kpi-sub">' + a.cnt.size + ' 条 · 转化 ' + fmtI(d.cv) + ' · 深转 —</div>' +
      '<div class="kpi-sub">CPA ' + fmtM(d.cpa) + '</div>' +
      '<div class="kpi-sub">跑出率 <b class="open-rate">' + fmtP(runRate) + '</b> · 开口10率 <b class="open-rate">' + fmtP(open10Rate) + '</b></div>' +
      '<div class="audit-cell" data-tip="' + auditTip.replace(/"/g, '&quot;').replace(/</g, '&lt;') + '">' +
        '<div class="audit-label">过审率</div>' +
        '<div class="audit-val">' + (pl.submitN ? fmtP(passRate) : '—') + '</div>' +
        '<div class="audit-frac">' + pl.passN + '/' + pl.submitN + ' 条</div>' +
      '</div>' +
    '</div>';
  }).join('') || '<div class="empty-state">暂无数据</div>';
}
function renderPersonBtns() {
  const persons = ['all', ...new Set(DATA.materials.map(m => m.person || '其他'))];
  const wrap = document.getElementById('personBtns');
  wrap.innerHTML = persons.map(p =>
    '<button class="filter-btn' + (state.person === p ? ' active' : '') + '" data-p="' + p + '">' +
    (p === 'all' ? '全部' : p) + '</button>').join('');
  wrap.querySelectorAll('.filter-btn').forEach(b => b.addEventListener('click', () => {
    state.person = b.dataset.p; renderMaterials(); renderPersonBtns();
  }));
}
function renderMaterials() {
  const thead = document.querySelector('#matTable thead');
  thead.innerHTML = '<tr>' + MAT_COLS.map(c => '<th data-k="' + c[1] + '">' + c[0] + '</th>').join('') + '</tr>';
  const list = [];
  for (const m of DATA.materials) {
    if (state.type !== 'all' && m.type !== state.type) continue;
    if (state.person !== 'all' && (m.person || '其他') !== state.person) continue;
    if (state.search && !(m.name || '').toLowerCase().includes(state.search.toLowerCase())) continue;
    const {m: mm, q} = aggDays(m.days);
    if (mm.sp <= 0 && mm.im <= 0 && mm.cv <= 0 && mm.ac <= 0 && mm.dp <= 0) continue;
    const d = derive(mm, q);
    list.push({name: m.name, type: m.type, person: m.person, content: m.content, ...d});
  }
  const sk = sortState['matTable'];
  if (sk) list.sort((a,b) => sk.dir === 'asc' ? (a[sk.k]||0)-(b[sk.k]||0) : (b[sk.k]||0)-(a[sk.k]||0));
  else list.sort((a,b) => b.sp - a.sp);
  document.getElementById('matCount').textContent = list.length;
  const paged = sliceRows(list, 'matTable');
  document.getElementById('matBody').innerHTML = paged.map(r => '<tr>' +
    MAT_COLS.map(c => cellHtml(c, r)).join('') + '</tr>').join('') ||
    '<tr><td colspan="22" class="empty-state">暂无数据</td></tr>';
  renderPager('matTable', list.length);
}

/* ---------------- TAB3 近3周跑出 ---------------- */
const CORE4 = ['嘉丽', '小敏', '雅迪', '瑞晨'];
function personOf3(name) {
  for (const p of CORE4) if (name.includes(p)) return p;
  return '其他';
}
function produceDay3(name) {
  // 产出日期规则（2026-11-11 用户定）：
  // 1) MMDD 前缀（MMDD 后跟分隔符或非数字，排除19位纯数字ID）
  // 2) 中文日期「11月4日」
  // 3) AI拒审修复_YYYYMMDD 时间戳
  // 4) 名称含「1007」尾缀→10/07；「国庆」→10/01；「11056」→11/05
  const n = (name || '').trim();
  const m = n.match(/^(\d{2})(\d{2})(?=[-—－_]|[^\d])/);
  if (m) {
    const mm = +m[1], dd = +m[2];
    if (mm >= 1 && mm <= 12 && dd >= 1 && dd <= 31) return '2026-' + m[1] + '-' + m[2];
  }
  const cn = n.match(/^(\d{1,2})月(\d{1,2})日/);
  if (cn) {
    const mm = +cn[1], dd = +cn[2];
    if (mm >= 1 && mm <= 12 && dd >= 1 && dd <= 31) {
      return '2026-' + String(mm).padStart(2, '0') + '-' + String(dd).padStart(2, '0');
    }
  }
  const ai = n.match(/AI拒审修复_(\d{4})(\d{2})(\d{2})/);
  if (ai) return ai[1] + '-' + ai[2] + '-' + ai[3];
  if (/1007/.test(n)) return '2026-10-07';
  if (n.includes('中秋')) return '2026-09-25';
  if (n.includes('国庆')) return '2026-10-01';
  if (/^11056/.test(n)) return '2026-11-05';
  if (/^713-/.test(n)) return '2026-07-13';
  return '';
}
// 不计入近3周的素材（无日期且无法确认产出日：数字ID、raw哈希、图文集合、无日期名称等）
function excludePass3w(name) {
  const n = (name || '').trim();
  if (/^\d{15,}$/.test(n)) return true;                        // 纯数字ID
  if (/_raw\.mp4$/i.test(n) || /^[0-9a-f]{32}/i.test(n)) return true;   // raw哈希
  if (n.includes('图文集合')) return true;
  if (n.includes('高三学习上瘾')) return true;
  return false;
}
function nameMatch(name, target) {
  // 台账名称 vs 报表名称：精确匹配或去后缀（改版等）
  const clean = s => (s || '').replace(/\.mp4$/i, '').replace(/\((\d+)\)$/, '').trim();
  return clean(name) === clean(target);
}
let pass3wData = null;   // 缓存聚合结果
let passWeekSel = 'near3';   // 编导卡周切换：near3/0/1/2
function buildPass3w() {
  // 1. 素材池：双台账 + 报表（视频/图文，排除AI花火），产出日三级兜底
  const pool = new Map();   // name -> {name, produce, subAudit, mainAudit, upload}
  const subByName = new Map(), mainByName = new Map();
  for (const l of (DATA.ledger_sub || [])) {
    if (!subByName.has(l.name)) subByName.set(l.name, []);
    subByName.get(l.name).push(l);
  }
  for (const l of (DATA.ledger_main || [])) {
    if (!mainByName.has(l.name)) mainByName.set(l.name, []);
    mainByName.get(l.name).push(l);
  }
  // 先放台账素材（子账户+主账户）
  for (const [srcMap, src] of [[subByName, 'sub'], [mainByName, 'main']]) {
    for (const [ln, recs] of srcMap) {
      if (excludePass3w(ln)) continue;
      const rec = recs[0];
      if (pool.has(ln)) {
        const e = pool.get(ln);
        if (src === 'sub') { e.subAudit = rec.audit; if (!e.upload) e.upload = rec.upload; }
        else { e.mainAudit = rec.audit; if (!e.upload) e.upload = rec.upload; }
        if (!e.produce) e.produce = produceDay3(ln) || rec.upload || '';
        continue;
      }
      const e = {name: ln, produce: produceDay3(ln) || rec.upload || '',
                 subAudit: src === 'sub' ? rec.audit : null,
                 mainAudit: src === 'main' ? rec.audit : null,
                 upload: rec.upload};
      pool.set(ln, e);
    }
  }
  // 报表素材：首现日 + 账户归属（素材出现在哪个账户的报表数据里）
  const firstSeen = {};
  const matAccts = {};   // name -> Set(acct)
  for (const m of DATA.materials) {
    if (m.type === 'AI' || m.type === '花火AI') continue;
    if (m.type !== '视频' && m.type !== '图文') continue;
    if (excludePass3w(m.name)) continue;   // 无日期不可确认的素材不计入
    if (!firstSeen[m.name]) {
      const days = Object.keys(m.days).sort();
      firstSeen[m.name] = days[0] || '';
    }
    if (!matAccts[m.name]) matAccts[m.name] = new Set();
    for (const d of Object.keys(m.days)) {
      for (const acct of Object.keys(m.days[d])) matAccts[m.name].add(acct);
    }
    // 台账匹配（同名或清理后同名）
    let subRec = null, mainRec = null;
    for (const [ln, recs] of subByName) { if (nameMatch(ln, m.name)) { subRec = recs[0]; break; } }
    for (const [ln, recs] of mainByName) { if (nameMatch(ln, m.name)) { mainRec = recs[0]; break; } }
    if (pool.has(m.name)) {
      const e = pool.get(m.name);
      if (!e.produce) e.produce = produceDay3(m.name) || e.upload || firstSeen[m.name] || '';
      if (subRec && !e.subAudit) e.subAudit = subRec.audit;
      if (mainRec && !e.mainAudit) e.mainAudit = mainRec.audit;
    } else {
      const produce = produceDay3(m.name) || (subRec ? subRec.upload : '') || (mainRec ? mainRec.upload : '') || firstSeen[m.name] || '';
      pool.set(m.name, {name: m.name, produce,
        subAudit: subRec ? subRec.audit : null,
        mainAudit: mainRec ? mainRec.audit : null,
        upload: (subRec ? subRec.upload : '') || (mainRec ? mainRec.upload : '')});
    }
  }
  // 素材池随账户筛选：单选时只留该账户台账或报表覆盖的素材
  const poolForAcct = new Map();
  for (const [name, e] of pool) {
    if (state.acct === 'all') { poolForAcct.set(name, e); continue; }
    if (state.acct === '125240890') {
      if (e.subAudit !== null && e.subAudit !== undefined) { poolForAcct.set(name, e); continue; }
      if (matAccts[name] && matAccts[name].has('125240890')) poolForAcct.set(name, e);
      continue;
    }
    if (state.acct === '125110802') {
      if (e.mainAudit !== null && e.mainAudit !== undefined) { poolForAcct.set(name, e); continue; }
      if (matAccts[name] && matAccts[name].has('125110802')) poolForAcct.set(name, e);
    }
  }
  // 2. 自然周窗口：锚定最新数据日，最多取3个完整自然周
  const latestDate = DATA.dates[DATA.dates.length - 1];
  const latest = new Date(latestDate + 'T00:00:00');
  // 锚点所在周的周日（自然周周一开始）
  const dow = (latest.getDay() + 6) % 7;   // 周一=0
  const anchorSunday = new Date(latest);
  anchorSunday.setDate(latest.getDate() + (6 - dow));
  const weekStarts = [];   // 最近的3个周一的日期
  for (let w = 0; w < 3; w++) {
    const monday = new Date(anchorSunday);
    monday.setDate(anchorSunday.getDate() - 6 - (2 - w) * 7);
    weekStarts.push(monday);
  }
  const fmtD = d => {
    const y = d.getFullYear(), mo = String(d.getMonth() + 1).padStart(2, '0'), da = String(d.getDate()).padStart(2, '0');
    return y + '-' + mo + '-' + da;
  };
  // 3. 每个素材归周 + 指标聚合
  const matByIdx = new Map();
  DATA.materials.forEach(m => { if (m.type === '视频' || m.type === '图文') matByIdx.set(m.name, m); });
  const weeks = weekStarts.map((monday, wi) => {
    const sunday = new Date(monday);
    sunday.setDate(monday.getDate() + 6);
    const rows = new Map();   // key=(person,name) -> row
    let submit = 0, passed = 0;
    const auditCnt = {过审: 0, 上传卡审: 0, 投放卡审: 0};
    for (const [name, e] of poolForAcct) {
      if (!e.produce) continue;
      const pd = new Date(e.produce + 'T00:00:00');
      if (pd >= monday && pd <= sunday) {
        // 提交/过审（按当前账户筛选取台账口径）
        const curAudit = currentAuditOf(e);
        const hasLedger = (e.subAudit !== null && e.subAudit !== undefined) ||
                          (e.mainAudit !== null && e.mainAudit !== undefined);
        // 单选账户时，只有该账户台账有记录才算提交；全选时任一有记录算提交
        let submitN = 0;
        if (state.acct === 'all') {
          submitN = hasLedger ? 1 : 0;
        } else if (state.acct === '125240890') {
          submitN = (e.subAudit !== null && e.subAudit !== undefined) ? 1 : 0;
        } else if (state.acct === '125110802') {
          submitN = (e.mainAudit !== null && e.mainAudit !== undefined) ? 1 : 0;
        }
        const passedN = (curAudit === '过审') ? 1 : 0;
        submit += submitN;
        passed += passedN;
        // 跑出指标（报表数据，窗口内投放日聚合）
        const m = matByIdx.get(name);
        const person = personOf3(name);
        const key = person + '|' + name;
        if (!rows.has(key)) rows.set(key, {
          person, name, produce: e.produce, subAudit: e.subAudit, mainAudit: e.mainAudit,
          submitN: submitN, passedN: passedN,
          sp: 0, im: 0, ac: 0, cv: 0, dp: 0, va: 0, o1: 0, o3: 0, o5: 0, o10: 0,
          qi: 0, qmi: 0, cc: 0, ce: 0, p3: 0, p5: 0, fn: 0, days: new Set(),
        });
        const row = rows.get(key);
        if (m) {
          // 指标 = 产出日 → 锚点日（数据最新日）累计，不按周窗口截断
          // （2026-11-12 用户定：素材按产出日归周，但指标看全生命周期累计表现）
          for (const [d, accts] of Object.entries(m.days)) {
            const dd = new Date(d + 'T00:00:00');
            if (dd <= anchorSunday) {
              // 有效投放天数 = 当天有花费的天数
              let dsp = 0;
              for (const [acct, mc] of Object.entries(accts)) {
                if (state.acct !== 'all' && acct !== state.acct) continue;   // 随账户筛选
                dsp += (mc.m && mc.m.sp) || 0;
              }
              if (dsp > 0) row.days.add(d);
              for (const [acct, mc] of Object.entries(accts)) {
                if (state.acct !== 'all' && acct !== state.acct) continue;   // 随账户筛选
                for (const k of MKEYS) row[k] += mc.m[k] || 0;
                for (const k of QKEYS) row[k] += mc.q[k] || 0;
              }
            }
          }
        }
      }
    }
    return {start: fmtD(monday), end: fmtD(sunday), rows: [...rows.values()], submit, passed};
  });
  pass3wData = {weeks, poolSize: pool.size, acct: state.acct};
  return pass3wData;
}
// 当前账户筛选下的审核状态（全选=合并严格口径；单选=对应台账）
function currentAuditOf(e) {
  const sub = e.subAudit, main = e.mainAudit;
  if (state.acct === 'all') {
    // 两边都过审才过审；卡审从严：上传卡审 > 投放卡审 > 过审
    if (sub === '过审' && main === '过审') return '过审';
    if (sub === '上传卡审' || main === '上传卡审') return '上传卡审';
    if (sub === '投放卡审' || main === '投放卡审') return '投放卡审';
    if (sub === '过审' || main === '过审') return '过审';   // 一边过审一边无记录 → 过审
    return null;   // 都没记录
  }
  if (state.acct === '125240890') return sub;
  if (state.acct === '125110802') return main;
  return null;
}
function renderPass3w() {
  if (!pass3wData) buildPass3w();
  const {weeks} = pass3wData;
  // 顶部 KPI：3周窗口合计（素材池按产出日归周后去重；跑出=窗口内有投放数据）
  let totalPool = 0, totalSubmit = 0, totalPassed = 0;
  let totM = ZM(), totQ = ZQ();
  const personAgg = {};
  for (const p of [...CORE4, '其他']) personAgg[p] = {cnt: 0, m: ZM(), q: ZQ(), submit: 0, passed: 0, cvCnt: 0};
  const seen = new Set();
  for (const wk of weeks) {
    totalPool += wk.rows.length;
    totalSubmit += wk.submit;
    totalPassed += wk.passed;
    for (const r of wk.rows) {
      const k = r.person + '|' + r.name;
      if (seen.has(k)) continue;
      seen.add(k);
      for (const mk of MKEYS) totM[mk] += r[mk] || 0;
      for (const qk of QKEYS) totQ[qk] += r[qk] || 0;
      const pa = personAgg[r.person] || personAgg['其他'];
      pa.cnt += 1;
      if (r.cv > 0) pa.cvCnt += 1;
      for (const mk of MKEYS) pa.m[mk] += r[mk] || 0;
      for (const qk of QKEYS) pa.q[qk] += r[qk] || 0;
      pa.submit += (r.submitN || 0);
      pa.passed += (r.passedN || 0);
    }
  }
  const t = derive(totM, totQ);
  const runCnt = [...seen].filter(k => { const row = weeks.flatMap(w => w.rows).find(r => r.person + '|' + r.name === k); return row && row.cv > 0; }).length;
  const g = document.getElementById('kpiGrid3');
  const passRate = totalSubmit ? (totalPassed / totalSubmit * 100) : 0;
  g.innerHTML = [
    ['素材池', fmtI(totalPool), '台账∪报表（3周产出）', false],
    ['跑出素材', fmtI(runCnt), '有转化', false],
    ['跑出率', totalPool ? fmtP(runCnt / totalPool * 100) : fmtP(0), '跑出÷素材池', false],
    ['过审数', fmtI(totalPassed), '按账户筛选（全选=双台账严格合并）', false],
    ['过审率', fmtP(passRate), '过审÷提交（子账户）', true],
    ['开口率', totalPool ? fmtP(t.o10 / totalPool * 100) : fmtP(0), '开口10次÷产出数', true],
    ['3周消耗', fmtM(t.sp), '窗口内投放消耗', false],
  ].map((r, i) => kpiCard(r[0], r[1], r[2], r[3])).join('');
  // 编导卡（支持按周切换：near3=近3周合计，0/1/2=第1/2/3周）
  if (!passWeekSel) passWeekSel = 'near3';
  let personRows;   // 参与编导卡统计的周集合
  if (passWeekSel === 'near3') personRows = weeks.flatMap(w => w.rows);
  else personRows = weeks[+passWeekSel] ? weeks[+passWeekSel].rows : [];
  const pAgg = {};
  for (const p of [...CORE4, '其他']) pAgg[p] = {cnt: 0, m: ZM(), q: ZQ(), submit: 0, passed: 0, cvCnt: 0};
  const pSeen = new Set();
  for (const r of personRows) {
    const key = r.person + '|' + r.name;
    if (pSeen.has(key)) continue;
    pSeen.add(key);
    const pa = pAgg[r.person] || pAgg['其他'];
    pa.cnt += 1;
    if (r.cv > 0) pa.cvCnt += 1;
    for (const mk of MKEYS) pa.m[mk] += r[mk] || 0;
    for (const qk of QKEYS) pa.q[qk] += r[qk] || 0;
    pa.submit += (r.submitN || 0);
    pa.passed += (r.passedN || 0);
  }
  const weekBtns = document.getElementById('passWeekBtns');
  const wkOptions = [['near3', '近3周'], ['0', '第1周'], ['1', '第2周'], ['2', '第3周']];
  weekBtns.innerHTML = wkOptions.map(([v, label]) =>
    '<button class="range-btn' + (passWeekSel === v ? ' active' : '') + '" data-pass-wk-sel="' + v + '">' + label + '</button>').join('');
  weekBtns.querySelectorAll('.range-btn').forEach(b => b.addEventListener('click', () => {
    passWeekSel = b.dataset.passWkSel;
    renderPass3w();
  }));
  const wrapP = document.getElementById('passPersonRow');
  wrapP.innerHTML = [...CORE4, '其他'].map(p => {
    const pa = pAgg[p];
    const d = derive(pa.m, pa.q);
    const c = PERSON_COLORS[p] || '#64748B', bg = PERSON_BG[p] || '#F8FAFC';
    const pr = pa.submit ? (pa.passed / pa.submit * 100) : 0;
    const runRate = pa.cnt ? (pa.cvCnt / pa.cnt * 100) : 0;         // 跑出率=转化素材数÷产出素材数
    const openRate = pa.cnt ? (d.o10 / pa.cnt * 100) : 0;            // 开口率=开口10次÷产出数
    return '<div class="kpi-card" style="margin:0">' +
      '<div class="kpi-label"><span class="person-badge" style="background:' + bg + ';color:' + c + '">' + p + '</span></div>' +
      '<div class="kpi-value" style="font-size:17px;color:' + c + '">' + fmtM(d.sp) + '</div>' +
      '<div class="kpi-sub">' + pa.cnt + ' 条素材 · 转化 ' + fmtI(d.cv) + '</div>' +
      '<div class="kpi-sub">CPA ' + fmtM(d.cpa) + ' · 过审率 ' + (pa.submit ? fmtP(pr) : '—') + '</div>' +
      '<div class="kpi-sub">跑出率 <b class="open-rate">' + fmtP(runRate) + '</b> · 开口率 <b class="open-rate">' + fmtP(openRate) + '</b></div>' +
    '</div>';
  }).join('');
  // 周区块（每页10行分页）
  const wrap = document.getElementById('pass3wWrap');
  let html = '';
  weeks.forEach((wk, wi) => {
    const wkLabel = '第' + (wi + 1) + '周';
    const sorted = [...wk.rows].sort((a, b) => b.sp - a.sp);
    const pages = Math.max(1, Math.ceil(sorted.length / PASS_PAGE_SIZE));
    const curPage = Math.min(passPageState[wi] || 1, pages);
    passPageState[wi] = curPage;
    const startIdx = (curPage - 1) * PASS_PAGE_SIZE;
    const pageRows = sorted.slice(startIdx, startIdx + PASS_PAGE_SIZE);
    // 分周总览
    const wkM = ZM(), wkQ = ZQ();
    let wkRun = 0;
    for (const r of wk.rows) {
      for (const mk of MKEYS) wkM[mk] += r[mk] || 0;
      for (const qk of QKEYS) wkQ[qk] += r[qk] || 0;
      if (r.cv > 0) wkRun += 1;
    }
    const wkD = derive(wkM, wkQ);
    const wkRunRate = wk.rows.length ? (wkRun / wk.rows.length * 100) : 0;
    const wkOpenRate = wk.rows.length ? (wkD.o10 / wk.rows.length * 100) : 0;
    html += '<div class="table-card" style="margin-bottom:16px">';
    html += '<div class="table-toolbar"><div class="section-title" style="margin:0">' + wkLabel +
      '（' + wk.start.slice(5).replace('-', '/') + ' - ' + wk.end.slice(5).replace('-', '/') + '）</div>' +
      '<div class="table-info">素材池 ' + wk.rows.length + ' 条 · 过审率 ' +
      (wk.submit ? (wk.passed / wk.submit * 100).toFixed(1) + '%（按账户筛选（全选=双台账严格合并））' : '—') +
      '</div></div>';
    html += '<div style="display:grid;grid-template-columns:repeat(6,1fr);gap:8px;padding:10px 14px;border-bottom:1px solid var(--border)">' +
      '<div class="kpi-card" style="margin:0;padding:8px 10px"><div class="kpi-label">周消耗</div><div class="kpi-value" style="font-size:15px">' + fmtM(wkD.sp) + '</div></div>' +
      '<div class="kpi-card" style="margin:0;padding:8px 10px"><div class="kpi-label">周转化</div><div class="kpi-value" style="font-size:15px">' + fmtI(wkD.cv) + '</div></div>' +
      '<div class="kpi-card" style="margin:0;padding:8px 10px"><div class="kpi-label">跑出素材</div><div class="kpi-value" style="font-size:15px">' + fmtI(wkRun) + '</div></div>' +
      '<div class="kpi-card" style="margin:0;padding:8px 10px"><div class="kpi-label">跑出率</div><div class="kpi-value" style="font-size:15px;color:#059669">' + fmtP(wkRunRate) + '</div></div>' +
      '<div class="kpi-card" style="margin:0;padding:8px 10px"><div class="kpi-label">开口率</div><div class="kpi-value" style="font-size:15px;color:#059669">' + fmtP(wkOpenRate) + '</div></div>' +
      '<div class="kpi-card" style="margin:0;padding:8px 10px"><div class="kpi-label">过审率</div><div class="kpi-value" style="font-size:15px;color:#D97706">' + (wk.submit ? fmtP(wk.passed / wk.submit * 100) : '—') + '</div></div>' +
      '</div>';
    html += '<div class="table-wrap"><table><thead><tr>' +
      '<th>编导</th><th>素材名称</th><th>产出日</th><th>有效投放天数</th><th>消耗</th><th>点击率</th>' +
      '<th>转化</th><th>CPA</th><th>深转</th><th>深转率</th><th>完播率</th><th>3秒率</th><th>5秒率</th><th>审核</th>' +
      '</tr></thead><tbody>';
    for (const r of pageRows) {
      const d = derive(r, r);
      const c = PERSON_COLORS[r.person] || '#64748B';
      const bg = PERSON_BG[r.person] || '#F8FAFC';
      const auditVal = currentAuditOf(r);
      const auditTxt = auditVal
        ? (auditVal === '过审' ? '<span style="color:#059669;font-weight:600">过审</span>'
          : auditVal === '上传卡审' ? '<span style="color:#D97706;font-weight:600">上传卡审</span>'
          : '<span style="color:#DC2626;font-weight:600">投放卡审</span>')
        : '<span style="color:#94A3B8">—</span>';
      html += '<tr>' +
        '<td><span class="person-badge" style="background:' + bg + ';color:' + c + '">' + r.person + '</span></td>' +
        '<td class="mat-name">' + r.name + '</td>' +
        '<td class="num">' + (r.produce || '—').slice(5).replace('-', '/') + '</td>' +
        '<td class="num">' + r.days.size + '</td>' +
        '<td class="num">' + fmtM(d.sp) + '</td>' +
        '<td class="num">' + fmtP(d.act_rate) + '</td>' +
        '<td class="num">' + fmtI(d.cv) + '</td>' +
        '<td class="num">' + fmtM(d.cpa) + '</td>' +
        '<td class="num">—</td>' +
        '<td class="num">—</td>' +
        '<td class="num">' + fmtP(d.fin) + '</td>' +
        '<td class="num">' + fmtP(d.p3) + '</td>' +
        '<td class="num">' + fmtP(d.p5) + '</td>' +
        '<td>' + auditTxt + '</td>' +
        '</tr>';
    }
    html += '</tbody></table></div>';
    if (pages > 1) {
      html += '<div class="pager" id="passPager' + wi + '"><span class="pager-info">共 ' +
        sorted.length + ' 条 · ' + pages + ' 页</span>';
      for (let p2 = 1; p2 <= pages; p2++) {
        html += '<button class="page-btn' + (p2 === curPage ? ' active' : '') +
          '" data-pass-wk="' + wi + '" data-pass-pg="' + p2 + '">' + p2 + '</button>';
      }
      html += '</div>';
    }
    html += '</div>';
  });
  wrap.innerHTML = html;
  // 分页事件（事件委托）
  wrap.querySelectorAll('.page-btn[data-pass-wk]').forEach(btn => {
    btn.addEventListener('click', () => {
      passPageState[+btn.dataset.passWk] = +btn.dataset.passPg;
      renderPass3w();
    });
  });
}

/* ---------------- TAB4 过审数据 ---------------- */
let auditCharts = {};
function buildAuditData() {
  // 合并台账：主+子，同名去重（严格合并状态）
  const subByName = new Map(), mainByName = new Map();
  for (const l of (DATA.ledger_sub || [])) {
    if (!subByName.has(l.name)) subByName.set(l.name, []);
    subByName.get(l.name).push(l);
  }
  for (const l of (DATA.ledger_main || [])) {
    if (!mainByName.has(l.name)) mainByName.set(l.name, []);
    mainByName.get(l.name).push(l);
  }
  // 合并去重素材：name -> {upload(最早), subAudit, mainAudit}
  const pool = new Map();
  for (const [ln, recs] of subByName) {
    const e = pool.get(ln) || {name: ln, upload: recs[0].upload, subAudit: null, mainAudit: null};
    e.subAudit = recs[0].audit;
    if (recs[0].upload < e.upload) e.upload = recs[0].upload;
    pool.set(ln, e);
  }
  for (const [ln, recs] of mainByName) {
    const e = pool.get(ln) || {name: ln, upload: recs[0].upload, subAudit: null, mainAudit: null};
    e.mainAudit = recs[0].audit;
    if (recs[0].upload < e.upload) e.upload = recs[0].upload;
    pool.set(ln, e);
  }
  // 逐日上传趋势 + 三分类 + 编导
  const selSet = selDates();
  const daily = new Map();   // date -> {upload, pass, up, cast}
  const byAudit = {过审: 0, 上传卡审: 0, 投放卡审: 0};
  const byPerson = {};
  // 报表素材归属账户（供单选过滤）
  const matAccts = new Map();
  for (const m of DATA.materials) {
    if (!matAccts.has(m.name)) matAccts.set(m.name, new Set());
    for (const d of Object.keys(m.days)) {
      for (const acct of Object.keys(m.days[d])) matAccts.get(m.name).add(acct);
    }
  }
  for (const [name, e] of pool) {
    if (excludePass3w(name)) continue;
    // 日期筛选：上传日期在所选窗口内
    if (e.upload && !selSet.has(e.upload)) continue;
    // 账户筛选：单选时只留该账户台账或该账户报表素材
    if (state.acct !== 'all') {
      const hasLedger = state.acct === '125240890'
        ? (e.subAudit !== null && e.subAudit !== undefined)
        : (e.mainAudit !== null && e.mainAudit !== undefined);
      const inMat = matAccts.has(name) && matAccts.get(name).has(state.acct);
      if (!hasLedger && !inMat) continue;
    }
    const audit = currentAuditOf(e);
    if (audit) byAudit[audit] += 1;
    const p = personOf3(name);
    if (!byPerson[p]) byPerson[p] = {pass: 0, total: 0};
    byPerson[p].total += 1;
    if (audit === '过审') byPerson[p].pass += 1;
    if (e.upload) {
      const d = daily.get(e.upload) || {upload: 0, pass: 0, up: 0, cast: 0};
      d.upload += 1;
      if (audit === '过审') d.pass += 1;
      else if (audit === '上传卡审') d.up += 1;
      else if (audit === '投放卡审') d.cast += 1;
      daily.set(e.upload, d);
    }
  }
  // 卡审清单（同样日期+账户过滤）
  const fails = [];
  for (const [name, e] of pool) {
    if (excludePass3w(name)) continue;
    if (e.upload && !selSet.has(e.upload)) continue;
    if (state.acct !== 'all') {
      const hasLedger = state.acct === '125240890'
        ? (e.subAudit !== null && e.subAudit !== undefined)
        : (e.mainAudit !== null && e.mainAudit !== undefined);
      const inMat = matAccts.has(name) && matAccts.get(name).has(state.acct);
      if (!hasLedger && !inMat) continue;
    }
    const audit = currentAuditOf(e);
    if (audit === '上传卡审' || audit === '投放卡审') {
      fails.push({name, audit, upload: e.upload, person: personOf3(name)});
    }
  }
  fails.sort((a, b) => (b.upload || '').localeCompare(a.upload || ''));
  return {daily, byAudit, byPerson, fails, total: pool.size};
}
function renderAudit() {
  const {daily, byAudit, byPerson, fails, total} = buildAuditData();
  // KPI 4卡
  const g = document.getElementById('kpiGrid4');
  const totalN = byAudit['过审'] + byAudit['上传卡审'] + byAudit['投放卡审'];
  g.innerHTML = [
    ['台账素材', fmtI(totalN), '主+子合并去重', false],
    ['过审', fmtI(byAudit['过审']), fmtP(totalN ? byAudit['过审'] / totalN * 100 : 0), false],
    ['上传卡审', fmtI(byAudit['上传卡审']), '审核状态=未通过', false],
    ['投放卡审', fmtI(byAudit['投放卡审']), '关联创意含未通过', false],
  ].map((r, i) => kpiCard(r[0], r[1], r[2], i === 1)).join('');
  // 趋势图
  const dates = Object.keys(daily).sort();
  const labels = dates.map(d => d.slice(5));
  if (auditCharts.trend) auditCharts.trend.destroy();
  auditCharts.trend = new Chart(document.getElementById('chartAuditTrend'), {
    type: 'bar',
    data: {labels, datasets: [
      {label: '上传', data: dates.map(d => daily[d].upload), backgroundColor: '#BFDBFE', borderRadius: 3},
      {label: '过审', data: dates.map(d => daily[d].pass), backgroundColor: '#34D399', borderRadius: 3},
      {label: '上传卡审', data: dates.map(d => daily[d].up), backgroundColor: '#FBBF24', borderRadius: 3},
      {label: '投放卡审', data: dates.map(d => daily[d].cast), backgroundColor: '#F87171', borderRadius: 3},
    ]},
    options: {responsive: true, maintainAspectRatio: false,
      plugins: {legend: {labels: {boxWidth: 12, font: {size: 11}}}},
      scales: {y: {beginAtZero: true, ticks: {font: {size: 10}}}, x: {ticks: {font: {size: 10}}}}}
  });
  // 三分类饼图
  if (auditCharts.pie) auditCharts.pie.destroy();
  auditCharts.pie = new Chart(document.getElementById('chartAuditPie'), {
    type: 'doughnut',
    data: {labels: ['过审', '上传卡审', '投放卡审'],
      datasets: [{data: [byAudit['过审'], byAudit['上传卡审'], byAudit['投放卡审']],
        backgroundColor: ['#34D399', '#FBBF24', '#F87171']}]},
    options: {responsive: true, maintainAspectRatio: false,
      plugins: {legend: {position: 'right', labels: {boxWidth: 12, font: {size: 11}}}}}
  });
  // 编导过审率
  const persons = [...CORE4, '其他'];
  if (auditCharts.person) auditCharts.person.destroy();
  auditCharts.person = new Chart(document.getElementById('chartAuditPerson'), {
    type: 'bar',
    data: {labels: persons, datasets: [{
      label: '过审率%',
      data: persons.map(p => {
        const bp = byPerson[p];
        return bp && bp.total ? +(bp.pass / bp.total * 100).toFixed(1) : 0;
      }),
      backgroundColor: persons.map(p => PERSON_COLORS[p] || '#94A3B8'), borderRadius: 4,
    }]},
    options: {responsive: true, maintainAspectRatio: false, indexAxis: 'y',
      plugins: {legend: {display: false},
        tooltip: {callbacks: {label: c => {
          const p = persons[c.dataIndex]; const bp = byPerson[p];
          return ' 过审率 ' + c.raw + '%（' + (bp ? bp.pass : 0) + '/' + (bp ? bp.total : 0) + '）';
        }}}},
      scales: {x: {beginAtZero: true, max: 100, ticks: {font: {size: 10}, callback: v => v + '%'}},
        y: {ticks: {font: {size: 11}}}}}
  });
  // 卡审清单
  document.getElementById('auditFailCount').textContent = fails.length;
  const thead = document.querySelector('#auditTable thead');
  thead.innerHTML = '<tr><th>素材名称</th><th>编导</th><th>卡审类型</th><th>上传日期</th></tr>';
  const pageRows = fails.slice(0, 30);
  document.getElementById('auditBody').innerHTML = pageRows.map(f => {
    const c = PERSON_COLORS[f.person] || '#64748B', bg = PERSON_BG[f.person] || '#F8FAFC';
    const typeTxt = f.audit === '上传卡审'
      ? '<span style="color:#D97706;font-weight:600">上传卡审</span>'
      : '<span style="color:#DC2626;font-weight:600">投放卡审</span>';
    return '<tr><td class="mat-name">' + f.name + '</td>' +
      '<td><span class="person-badge" style="background:' + bg + ';color:' + c + '">' + f.person + '</span></td>' +
      '<td>' + typeTxt + '</td>' +
      '<td class="num">' + (f.upload || '—').slice(5).replace('-', '/') + '</td></tr>';
  }).join('') || '<tr><td colspan="4" class="empty-state">暂无卡审素材</td></tr>';
  const pager = document.getElementById('auditPager');
  if (fails.length > 30) {
    pager.innerHTML = '<span class="pager-info">共 ' + fails.length + ' 条 · 显示前 30 条</span>';
  } else {
    pager.innerHTML = '<span class="pager-info">共 ' + fails.length + ' 条</span>';
  }
}

/* ---------------- 视频弹窗 ---------------- */
function openVideo(name) {
  const m = DATA.materials.find(x => x.name === name);
  if (!m || !m.content) return;
  document.getElementById('modalTitle').textContent = m.name;
  document.getElementById('modalVideo').src = m.content;
  document.getElementById('videoModal').classList.add('open');
}
function closeModal() {
  document.getElementById('videoModal').classList.remove('open');
  document.getElementById('modalVideo').pause();
  document.getElementById('modalVideo').src = '';
}
document.getElementById('videoModal').addEventListener('click', e => {
  if (e.target.id === 'videoModal') closeModal();
});

/* ---------------- 排序（事件委托，表头一次性绑定） ---------------- */
const sortState = {};
function bindSort(tableId) {
  const thead = document.querySelector('#' + tableId + ' thead');
  thead.addEventListener('click', e => {
    const th = e.target.closest('th');
    if (!th || !th.dataset.k) return;
    const k = th.dataset.k;
    const prev = sortState[tableId];
    const dir = (prev && prev.k === k && prev.dir === 'desc') ? 'asc' : 'desc';
    sortState[tableId] = {k, dir};
    thead.querySelectorAll('th').forEach(x => x.classList.remove('sorted-asc','sorted-desc'));
    th.classList.add('sorted-' + dir);
    if (tableId === 'dimTable') renderDim();
    else if (tableId === 'matTable') renderMaterials();
    else if (tableId === 'acctTable') renderAcctSorted(k, dir);
  });
}
function renderAcctSorted(k, dir) {
  const rows = DATA.accounts.map(a => ({id: a.id, ...derive(aggDays(a.days).m, ZQ())}));
  rows.sort((a,b) => dir === 'asc' ? (a[k]||0)-(b[k]||0) : (b[k]||0)-(a[k]||0));
  const cols = [['账户','id','txt'],['花费','sp','fmtM'],['曝光','im','fmtI'],['行为数','ac','fmtI'],
    ['行为率','act_rate','fmtP'],['转化','cv','fmtI'],['转化率','cvr','fmtP'],['CPA','cpa','fmtM'],
    ['深转','dp','fmtI'],['深转率','deep_rate','fmtP'],['有效获客','va','fmtI'],
    ['开口1','o1','fmtI'],['开口3','o3','fmtI'],['开口5','o5','fmtI'],['开口10','o10','fmtI']];
  document.getElementById('acctBody').innerHTML = rows.map(r => '<tr style="cursor:pointer" data-acct="' + r.id + '">' +
    cols.map(c => {
      if (c[2]==='txt') return '<td><span class="person-badge" style="background:#ECFDF5;color:#047857">' + r.id + '</span></td>';
      if (c[1]==='dp' || c[1]==='deep_rate') return '<td class="num num-zero">—</td>';
      const v = r[c[1]]||0;
      if (c[2]==='fmtI' && v===0) return '<td class="num num-zero">0</td>';
      if (c[1]==='dp' && v>0) return '<td class="gaoquan-cell">' + fmtI(v) + '</td>';
      return '<td class="num">' + (c[2]==='fmtM'?fmtM(v):c[2]==='fmtP'?fmtP(v):fmtI(v)) + '</td>';
    }).join('') + '</tr>').join('');
  document.querySelectorAll('#acctBody tr[data-acct]').forEach(tr => tr.addEventListener('click', () => {
    state.acct = (state.acct === tr.dataset.acct) ? 'all' : tr.dataset.acct;
    renderAll();
  }));
}

/* ---------------- 初始化 ---------------- */
function initFilters() {
  document.querySelectorAll('.filter-btn[data-dim]').forEach(b => b.addEventListener('click', () => {
    document.querySelectorAll('.filter-btn[data-dim]').forEach(x => x.classList.remove('active'));
    b.classList.add('active');
    state.dim = b.dataset.dim;
    renderDim();
  }));
  document.querySelectorAll('.filter-btn[data-t]').forEach(b => b.addEventListener('click', () => {
    document.querySelectorAll('.filter-btn[data-t]').forEach(x => x.classList.remove('active'));
    b.classList.add('active');
    state.type = b.dataset.t;
    renderMaterials();
  }));
  document.getElementById('searchBox').addEventListener('input', e => {
    state.search = e.target.value.trim();
    renderMaterials();
  });
  document.getElementById('typeRow').addEventListener('click', e => {
    const card = e.target.closest('[data-type]');
    if (!card) return;
    const t = card.dataset.type;
    state.type = (state.type === t) ? 'all' : t;
    document.querySelectorAll('.filter-btn[data-t]').forEach(x =>
      x.classList.toggle('active', x.dataset.t === state.type));
    renderMaterials();
  });
  document.getElementById('personRow').addEventListener('click', e => {
    const card = e.target.closest('[data-person]');
    if (!card) return;
    const p = card.dataset.person;
    state.person = (state.person === p) ? 'all' : p;
    renderMaterials();
    renderPersonBtns();
  });
}

function renderAll() {
  renderChips();
  renderKpi1();
  renderKpi2();
  renderFunnel();
  renderTrend();
  renderAcct();
  renderDim();
  renderHourly();
  renderTypes();
  renderPersons();
  renderPersonBtns();
  renderMaterials();
  // 账户筛选变化时重建近3周缓存
  if (pass3wData && pass3wData.acct !== state.acct) pass3wData = null;
  renderPass3w();
  renderAudit();
}

// 表头一次性绑定（thead 内容重渲染不影响事件委托）
bindSort('acctTable');
bindSort('dimTable');
bindSort('matTable');
// 播放按钮事件委托
document.getElementById('matBody').addEventListener('click', e => {
  const btn = e.target.closest('.btn-play');
  if (btn) openVideo(btn.dataset.vname);
});
initFilters();
initDateDropdown();
renderAll();
</script>
</body>
</html>"""

    html = (html.replace("__MMDD__", REPORT_MMDD)
                .replace("__CSS__", CSS)
                .replace("__CALIBER1__", caliber_html("1"))
                .replace("__CALIBER2__", caliber_html("2"))
                .replace("__CALIBER3__", caliber_html("3"))
                .replace("__CALIBER4__", caliber_html("4"))
                .replace("__CHARTJS__", chart_js)
                .replace("__DATA_JSON__", json.dumps(data, ensure_ascii=False))
                .replace("__COLORS_JS__", json.dumps(PERSON_COLORS, ensure_ascii=False))
                .replace("__BG_JS__", json.dumps(PERSON_BG, ensure_ascii=False)))
    return html


def main():
    html = build_html()
    out = REPORTS_DIR / f"快手投放报告_{REPORT_MMDD}.html"
    out.write_text(html, encoding="utf-8")
    print(f"[OK] {out} ({out.stat().st_size/1024:.0f} KB)")


if __name__ == "__main__":
    main()
