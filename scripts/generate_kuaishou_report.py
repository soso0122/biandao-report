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
.mat-name{max-width:280px;white-space:normal;word-break:break-all;font-size:12px;
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
    <div class="caliber-item"><b>数据源</b>：石墨文档「【快手】引流加微数据」（账户表现 + 素材表现），快手投放 2026-10-30 起。</div>
    <div class="caliber-item"><b>行为数</b>：快手的「行为」约等于素材点击。行为率 = 行为数 ÷ 曝光数。</div>
    <div class="caliber-item"><b>转化率</b> = 转化数(计费时间) ÷ 行为数；<b>深转率</b> = 深转数 ÷ 转化数。</div>
    <div class="caliber-item"><b>CPA</b> = 花费 ÷ 转化数；<b>转化成本</b> = 花费 ÷ 转化数（素材维度）。</div>
    <div class="caliber-item"><b>开口率</b> = 开口N次 ÷ 有效获客（快手口径下开口含历史用户回流，可能 >100%）。</div>
    <div class="caliber-item"><b>回流开口</b> = 当日开口1次 − 当日有效获客（历史转化用户的回访开口；素材当日无有效获客时其开口全部计为回流）。</div>
    <div class="caliber-item"><b>漏斗</b>：曝光 → 行为 → 转化 → 深转 → 有效获客 → 企微开口 1/3/5/10 次。</div>
    <div class="caliber-item"><b>素材分类</b>：素材内容有视频链接=视频；名称=AIGC=平台AI；名称含图文集合_=图文。</div>
    <div class="caliber-item"><b>编导归属</b>：名称匹配已知编导/剪辑（小敏、嘉丽、浩正、雅迪、婷玉、魏怡、瑞晨、国星），其余「其他」。</div>
    <div class="caliber-item"><b>素材点击率</b> = 行为数 ÷ 素材曝光数；<b>封面点击率</b> = 封面点击 ÷ 封面曝光。</div>
    <div class="caliber-item"><b>3秒/5秒/完播率</b>：按曝光数加权平均。</div>
    <div class="caliber-item"><b>去重口径</b>：素材总数按素材名称去重；账户表为广告组级拆分，数字按行加总后重算比率。</div>
    <div class="caliber-item"><b>分时</b>：按小时聚合；选多天时按小时跨日累计。优/差时段按该小时转化率相对全天判断。</div>
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
  <div class="kpi-grid" id="kpiGrid2"></div>
  <div class="chart-card" style="margin-bottom:20px">
    <div class="section-title">素材类型</div>
    <div id="typeRow" style="display:grid;grid-template-columns:repeat(3,1fr);gap:12px"></div>
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
const DEEP_PENDING = true;
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
  document.getElementById('tabBtn1').classList.toggle('active', t === 1);
  document.getElementById('tabBtn2').classList.toggle('active', t === 2);
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
    ['深转数', DEEP_PENDING ? '未回传' : fmtI(t.dp), DEEP_PENDING ? '快手暂未回传' : '深度转化', false],
    ['深转率', DEEP_PENDING ? '未回传' : fmtP(t.deep_rate), DEEP_PENDING ? '快手暂未回传' : '深转÷转化', false],
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
  ];
  g.innerHTML = rows.map((r,i) => kpiCard(r[0], r[1], r[2], i===0)).join('');
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
    ['转化', tot.cv], ['深转(未回传)', DEEP_PENDING ? 0 : tot.dp],
    ['有效获客', tot.va], ['开口1次', tot.o1], ['开口3次', tot.o3],
    ['开口5次', tot.o5], ['开口10次', tot.o10],
  ];
  const colors = ['#3B82F6','#60A5FA','#8B5CF6','#A78BFA','#F59E0B','#FBBF24','#10B981'];
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
  const spend = [], conv = [], deep = [], cpa = [], cvr = [], labels = [];
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
    deep.push(+s.dp.toFixed(1));
    cpa.push(s.cv ? +(+s.sp/s.cv).toFixed(2) : 0);
    cvr.push(s.ac ? +(s.cv/s.ac*100).toFixed(2) : 0);
  }
  return {labels, spend, conv, deep, cpa, cvr};
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
      {type:'line', label: DEEP_PENDING ? '深转(未回传)' : '深转', data: DEEP_PENDING ? s.deep.map(() => 0) : s.deep, borderColor:'#F59E0B', tension:.3, pointRadius:2, yAxisID:'y1'}
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
      if (DEEP_PENDING && (c[1]==='dp' || c[1]==='deep_rate')) return '<td class="num num-zero">未回传</td>';
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
    const cls = t==='图文' ? 'type-tuwen' : t==='AI' ? 'type-ai' : 'type-video';
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
  if (DEEP_PENDING && c[1]==='dp') return '<td class="num num-zero">未回传</td>';
  if (DEEP_PENDING && c[1]==='deep_rate') return '<td class="num num-zero">未回传</td>';
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
const pageState = {dimTable: 1, matTable: 1};

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
  const agg = {视频: {cnt:new Set(), m:ZM(), q:ZQ()}, 图文: {cnt:new Set(), m:ZM(), q:ZQ()}, AI: {cnt:new Set(), m:ZM(), q:ZQ()}};
  for (const m of DATA.materials) {
    const t = m.type || '视频';
    const a = agg[t];
    const {m: mm, q} = aggDays(m.days);
    // 条数随日期联动：所选日期内有投放数据的素材才计数
    if (mm.sp > 0 || mm.im > 0 || mm.cv > 0 || mm.ac > 0 || mm.dp > 0) {
      a.cnt.add(m.name);
      addM(a.m, mm); addQ(a.q, q);
    }
  }
  const wrap = document.getElementById('typeRow');
  const defs = [['视频','filter-btn-video'],['图文','filter-btn-tuwen'],['AI','filter-btn-ai']];
  wrap.innerHTML = defs.map(([t, cls]) => {
    const a = agg[t];
    const d = derive(a.m, a.q);
    return '<div class="kpi-card" style="margin:0;cursor:pointer" data-type="' + t + '">' +
      '<div class="kpi-label"><span class="person-badge ' + cls + '">' + (t==='AI'?'平台AI':t) + '</span></div>' +
      '<div class="kpi-value" style="font-size:18px">' + fmtM(d.sp) + '</div>' +
      '<div class="kpi-sub">' + a.cnt.size + ' 条素材 · 转化 ' + fmtI(d.cv) + ' · 点击率 ' + fmtP(d.mat_click_rate) + '</div>' +
    '</div>';
  }).join('');
}
function renderPersons() {
  const map = {};
  for (const m of DATA.materials) {
    const p = m.person || '其他';
    if (!map[p]) map[p] = {cnt: new Set(), m: ZM(), q: ZQ()};
    const {m: mm, q} = aggDays(m.days);
    // 条数随日期联动：所选日期内有投放数据的素材才计数
    if (mm.sp > 0 || mm.im > 0 || mm.cv > 0 || mm.ac > 0 || mm.dp > 0) {
      map[p].cnt.add(m.name);
      addM(map[p].m, mm); addQ(map[p].q, q);
    }
  }
  const wrap = document.getElementById('personRow');
  const list = Object.entries(map).sort((a,b) => b[1].m.sp - a[1].m.sp);
  wrap.innerHTML = list.map(([p, a]) => {
    const c = PERSON_COLORS[p] || '#64748B', bg = PERSON_BG[p] || '#F8FAFC';
    const d = derive(a.m, a.q);
    return '<div class="kpi-card" style="margin:0;cursor:pointer" data-person="' + p + '">' +
      '<div class="kpi-label"><span class="person-badge" style="background:' + bg + ';color:' + c + '">' + p + '</span></div>' +
      '<div class="kpi-value" style="font-size:17px;color:' + c + '">' + fmtM(d.sp) + '</div>' +
      '<div class="kpi-sub">' + a.cnt.size + ' 条 · 转化 ' + fmtI(d.cv) + ' · 深转 ' + (DEEP_PENDING ? '未回传' : fmtI(d.dp)) + '</div>' +
      '<div class="kpi-sub">CPA ' + fmtM(d.cpa) + ' · 深转率 ' + (DEEP_PENDING ? '未回传' : fmtP(d.deep_rate)) + '</div>' +
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
      if (DEEP_PENDING && (c[1]==='dp' || c[1]==='deep_rate')) return '<td class="num num-zero">未回传</td>';
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
