# Eagle Data Parser — 项目说明

这是一个内容投放数据分析项目，每周从千川导出 CSV，生成 HTML 可视化报告，自动推送到 GitHub Pages。

---

## 当前状态（2026-10-09 更新）

**每周必更新的报告只剩两个：代理商报告 + IP老师素材报告。**
编导报告、引导素材周报、上传数据增强版均已停更（用户确认）。

---

## 目录结构

```
eagle-data-parser/          ← 主仓库
├── data/                   ← 所有原始数据文件（CSV）
├── reports/                ← 生成的 HTML 报告
├── scripts/                ← 生成脚本
│   ├── generate_report_agent_0807.py ← 代理商报告脚本（当前使用）
│   └── generate_ip_report.py         ← IP老师素材报告脚本
```

外部仓库本地路径：
- `soso0122/agent-report` → `/Users/soso/Desktop/agent-report/`
- `soso0122/ip-report` → `/Users/soso/Desktop/ip-report/`
- `soso0122/eagle-nav` → `/tmp/eagle-nav/`（导航首页，重启后需重新 clone）
- `soso0122/reject-report` → `/Users/soso/Desktop/reject-report/`（拒审日报）

---

## 线上地址

| 报告 | GitHub 仓库 | 线上地址 |
|---|---|---|
| 导航首页 | `soso0122/eagle-nav` | `https://soso0122.github.io/eagle-nav/` |
| 代理商数据分析 | `soso0122/agent-report` | `https://soso0122.github.io/agent-report/` |
| IP老师素材分析 | `soso0122/ip-report` | `https://soso0122.github.io/ip-report/` |
| 拒审日报分析 | `soso0122/reject-report` | `https://soso0122.github.io/reject-report/` |
| 引流加微每日日报 | `soso0122/daily-guide-report` | `https://soso0122.github.io/daily-guide-report/` |

（编导报告 biandao-report、引导素材 guide-report 已停更，保留线上页面但不再更新）

---

## 引流加微每日日报（每日更新，两报告联动）

用户把千川导出的 `视频库_*.csv` / `图文库_*.csv`（过审文件带 `-过审`）放入 `~/Desktop/111/` 后说"更新"，助手**一次性跑两个报告**：

```bash
# 0. 检查图文库是否需填充（千川图文库导出 bug：数值全0）
python3 scripts/check_111_files.py
#    如输出「⚠️ 需要填充」，请用户从千川网页复制数据，
#    用 scripts/fill_tuwen_data.py 数据.txt 目标CSV.csv 写回
#    详见记忆 tuwen-data-fill-workflow

# 1. 合并当天数据（先核对 111 文件名时间戳与目标日期一致！）
python3 scripts/merge_daily_csv.py MMDD

# 2. 同步最新打标表到 data/（如用户提供了新版历史打标.csv）
# 3. 生成日报全部页面（一个脚本出5页）
python3 scripts/generate_report_daily_guide.py
#    页面拆分逻辑与「内容素材转化时效」模块在 scripts/report_pages.py

# 4. 生成素材周期表现页（数据源相同，必须一起跑，防遗漏）
python3 scripts/material_period_report.py

# 5. 六个文件一起复制发布（缺一个线上就坏）
cp reports/引导素材每日分析_MMDD.html /Users/soso/Desktop/daily-guide-report/index.html
cp reports/卡审分析.html /Users/soso/Desktop/daily-guide-report/卡审分析.html
cp reports/近3周跑出.html /Users/soso/Desktop/daily-guide-report/近3周跑出.html
cp reports/内容素材转化时效.html /Users/soso/Desktop/daily-guide-report/内容素材转化时效.html
cp reports/编导&素材明细.html /Users/soso/Desktop/daily-guide-report/编导&素材明细.html
cp reports/素材周期表现.html /Users/soso/Desktop/daily-guide-report/素材周期表现.html
cd /Users/soso/Desktop/daily-guide-report
git add -A && git commit -m "更新日报+分页 MMDD" && git push

# 6. 截图确认（系统 Python /usr/bin/python3，Playwright 浏览器在系统环境）
/usr/bin/python3 scripts/push_daily_report.py

# 7. 只有用户明确说"推送"才加 --send 发企微
```

**注意**：
- **日报已分页**（2026-10-25 起）：总览（index.html）+ 卡审分析.html + 近3周跑出.html + 内容素材转化时效.html + 编导&素材明细.html + 素材周期表现.html，**六个文件都要复制推送**。tab 导航在每页顶部 sticky 顶栏，日期选择写 URL 参数 `?d=` 跨页同步
- 素材周期表现是**总览页底部 iframe 卡片**（不再跳转）；编导&素材明细页最大（明细数据所在，约 14MB），子页点击才加载
- 「⏱️内容素材转化时效」独立 tab：仅自投、有转化素材、5个首次节点+3个间隔，**不随全局日期**，用自己的产出日期筛选；编导卡含开口率/成单率/首转/首高潜天数
- 两个脚本读同一批 `data/引导加微每日数据-*.csv`，跑素材周期前先跑日报合并
- 素材周期页由用户在别的会话单独优化，助手更新时直接重跑 `material_period_report.py` 覆盖即可，不改其内部逻辑


---

## 每周更新流程

用户把 CSV 放入 `data/` 后，说"帮我更新"，助手完成生成和推送。

### 1. 代理商报告（每周必更新）

用户提供：`data/【周报】投后素材看板数据-代理-MMDD.csv`
（**累计快照**，包含历史素材；「新起量」按首次消耗时间过滤）

**步骤：**
1. 更新脚本顶部 `WEEK_START` / `WEEK_END` 为本次数据周期（用户会说，如 9/18–10/9）
2. `_WEEK_MAP` 顶部添加新期映射
3. 运行并推送

```bash
python3 scripts/generate_report_agent_0807.py MMDD
cp reports/代理商数据分析报告_MMDD.html /Users/soso/Desktop/agent-report/index.html
cd /Users/soso/Desktop/agent-report
git add index.html && git commit -m "更新代理商数据分析报告 MMDD" && git push
```

### 2. IP老师素材报告（每周必更新）

**数据来源：** 只读代理商 CSV（编导侧停更后代理文件已覆盖全部素材，无需编导文件）

```bash
python3 scripts/generate_ip_report.py MMDD
cp reports/IP素材分析报告_MMDD.html /Users/soso/Desktop/ip-report/index.html
cd /Users/soso/Desktop/ip-report
git add index.html && git commit -m "更新IP素材分析报告 MMDD" && git push
```

**IP老师名单**（脚本 `IP_NAMES` 变量）：李博、白琳、王晶。用户会通知增删。

### 3. 拒审日报（有新数据才更新）

用户提供：`拒审导出-MMDD.csv`（放入 `data/`）

```bash
python generate_reject_report_0725.py
cp reports/拒审日报分析_MMDD.html /Users/soso/Desktop/reject-report/index.html
cd /Users/soso/Desktop/reject-report
git add index.html && git commit -m "更新拒审日报分析 MMDD" && git push
```

---

## 已停更的报告（不要再跑）

- **编导报告**（biandao-report）：数据从 0918 止，`generate_report_combined.py` 不再使用
- **引导素材周报**（guide-report）：用户自行额外更新，助手不跑
- **上传数据_增强版 CSV**：停更，不再生成

---

## 数据文件说明

### 代理商报告所需文件

| 文件 | 说明 |
|---|---|
| `data/【周报】投后素材看板数据-代理-MMDD.csv` | 代理商投后数据（累计快照） |

### 历史文件（保留，不再追加）

| 文件 | 说明 |
|---|---|
| `data/投后数据-编导-历史.csv` | 编导历史数据，止于 0918 |
| `data/上传数据_增强版_MMDD.csv` | 历史上传记录，止于 0918 |
