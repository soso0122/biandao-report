# Eagle Data Parser — 项目说明

这是一个内容投放数据分析项目，每周从千川导出 CSV，生成 HTML 可视化报告，自动推送到 GitHub Pages。

---

## 目录结构

```
eagle-data-parser/          ← 主仓库，对应 soso0122/biandao-report
├── data/                   ← 所有原始数据文件（CSV）
├── reports/                ← 生成的 HTML 报告
│   └── index.html          ← 导航首页（同步推到 eagle-nav 仓库）
├── scripts/                ← 生成脚本
│   └── generate_report_agent_0807.py ← 代理商报告脚本（当前版本）
└── generate_report_combined.py      ← 主脚本：编导历史+周报合并版
```

外部仓库本地路径：
- `soso0122/agent-report` → `/Users/soso/Desktop/agent-report/`
- `soso0122/eagle-nav` → `/tmp/eagle-nav/`（导航首页）
- `soso0122/guide-report` → `/tmp/guide-report/`（引导素材报告）
- `soso0122/reject-report` → `/Users/soso/Desktop/reject-report/`（拒审日报）
- `soso0122/daily-guide-report` → `/Users/soso/Desktop/daily-guide-report/`（引导素材每日分析）
- `soso0122/ip-report` → `/tmp/ip-report/`（IP老师素材分析）

---

## 四个线上地址

| 报告 | GitHub 仓库 | 线上地址 |
|---|---|---|
| 导航首页 | `soso0122/eagle-nav` | `https://soso0122.github.io/eagle-nav/` |
| 编导数据分析 | `soso0122/biandao-report` | `https://soso0122.github.io/biandao-report/` |
| 引导素材分析（周报） | `soso0122/guide-report` | `https://soso0122.github.io/guide-report/` |
| 引导素材每日分析 | `soso0122/daily-guide-report` | `https://soso0122.github.io/daily-guide-report/` |
| 代理商数据分析 | `soso0122/agent-report` | `https://soso0122.github.io/agent-report/` |
| 拒审日报分析 | `soso0122/reject-report` | `https://soso0122.github.io/reject-report/` |
| IP老师素材分析 | `soso0122/ip-report` | `https://soso0122.github.io/ip-report/` |

---

## 每周更新完整流程

用户把 CSV 放入 `data/` 后，说"帮我更新"，助手完成生成和推送，用户不需要手动操作 git。

### 1. 编导报告（每周必更新）

用户提供：`【周报】投后素材看板数据-MMDD.csv`（放入 `data/`）

**步骤：**
1. 将新数据追加合并到 `data/投后数据-编导-历史.csv`（去重，唯一键：素材名称+编导，取最新指标）
2. 更新 `generate_report_combined.py` 顶部日期变量 `WEEK_START` 和底部 CSV 路径
3. 运行脚本生成报告
4. 复制合并版报告覆盖根目录 `index.html`
5. 推送到 `biandao-report`

```bash
cd /Users/soso/Desktop/eagle-data-parser
python generate_report_combined.py
cp reports/编导数据分析报告_合并版.html index.html
git add index.html reports/编导数据分析报告_合并版.html
git commit -m "更新编导数据分析报告 MMDD"
git push
```

### 2. 引导素材报告（有新数据才更新）

用户提供：`【周报】引导素材投放-MMDD.csv`（从 0807 起文件名含「投放」，新增「账户」列）

**步骤：**
1. 运行脚本生成报告（编导优先于剪辑归属，主页素材单独分组）
2. 覆盖推送到 `guide-report`

```bash
python3 scripts/gen_guide_report_0807.py MMDD
cp reports/引导素材分析报告_MMDD.html /tmp/guide-report/index.html
cd /tmp/guide-report
git add index.html
git commit -m "更新引导素材分析报告 MMDD"
git push
```

### 3. 代理商报告（有新数据才更新）

用户提供：`【周报】投后素材看板数据-代理-MMDD.csv`（CSV 里代理商为全称，脚本自动归一化）

**步骤：**
1. 在脚本顶部 `_WEEK_MAP` 里添加新一期映射
2. 运行脚本（自动读取上期做双周对比，自动扫描历史期做趋势图）
3. 推送到 `agent-report`

```bash
python3 scripts/generate_report_agent_0807.py MMDD
cp reports/代理商数据分析报告_MMDD.html /Users/soso/Desktop/agent-report/index.html
cd /Users/soso/Desktop/agent-report
git add index.html
git commit -m "更新代理商数据分析报告 MMDD"
git push
```

### 4. IP老师素材报告（有新数据才更新，从 0904 开始）

数据来源：同时读编导和代理商两个 CSV，无需额外文件

```bash
python3 scripts/generate_ip_report.py MMDD
cp reports/IP素材分析报告_MMDD.html /tmp/ip-report/index.html
cd /tmp/ip-report
git add index.html
git commit -m "更新IP素材分析报告 MMDD"
git push
```

IP名单：李博、白琳、王晶（严嘉伟已移除）

### 5. 拒审日报（有新数据才更新）

用户提供：`拒审导出-MMDD.csv`（放入 `data/`）

**步骤：**
1. 更新脚本顶部 `DATA_FILE` 和 `REPORT_DATE` 变量
2. 运行脚本生成报告
3. 推送到 `reject-report`

```bash
python generate_reject_report_0725.py
cp reports/拒审日报分析_MMDD.html /tmp/reject-report/index.html
cd /tmp/reject-report
git add index.html
git commit -m "更新拒审日报分析 MMDD"
git push
```

```bash
cp /Users/soso/Desktop/eagle-data-parser/reports/index.html /tmp/eagle-nav/index.html
cd /tmp/eagle-nav
git add index.html
git commit -m "更新导航首页"
git push
```

---

## 数据文件说明

### 编导报告所需文件

| 文件 | 说明 | 更新频率 |
|---|---|---|
| `data/投后数据-编导-历史.csv` | 历史累积投放数据，每周追加 | 每周追加（不替换） |
| `data/【周报】投后素材看板数据-MMDD.csv` | 当周新增投放数据 | 每周新增 |
| `data/上传数据_增强版_MMDD.csv` | 当周上传记录（脚本生成） | 每周生成 |

### 代理商报告所需文件

| 文件 | 说明 |
|---|---|
| `data/【周报】投后素材看板数据-代理-MMDD.csv` | 代理商投后数据 |

---

## 业务规则

### 数据过滤条件（编导报告）

```python
编导确认 != ''          # 编导确认列不为空
AND 是否自产自投 == '是'
AND 是否混剪 == '否'
```

### 产品分类（`投放产品` 列）

```python
含 '李博' 或 '物理'  →  '9元李博'
含 '199' 或 '双科'   →  '199双科'
其他                  →  原始名称 或 '其他'
```

### 编导名称归一化

```python
'子矜' / '贾子矜' → '子衿'
'魏嘉丽' → '嘉丽'
'杜浩正' → '浩正'
'王雅迪' → '雅迪'
'曲敏'   → '小敏'
'吴婷玉' → '婷玉'
```

---

## 历史数据追加规则

每次新增一期数据，需将新 CSV 合并到 `data/投后数据-编导-历史.csv`：
- 唯一键：`素材名称 + 编导确认`
- 冲突时取新文件的数据（最新一期的指标）
- 过滤条件同上（编导确认非空 + 自产自投 + 非混剪）
