"""
千川视频库/图文库数据自动下载合并脚本

用法:
    python3 scripts/download_daily_data.py               # 昨天数据
    python3 scripts/download_daily_data.py --date today  # 今天数据
    python3 scripts/download_daily_data.py --date 0810   # 指定日期
    python3 scripts/download_daily_data.py --date 0806,0807,0808  # 多天
    python3 scripts/download_daily_data.py --dry-run     # 只下载不合并不推送
"""

import argparse
import csv
import io
import os
import shutil
import subprocess
import sys
import time
from datetime import date, timedelta
from pathlib import Path
from typing import Optional

from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

sys.path.insert(0, str(Path(__file__).parent))
from accounts_config import ACCOUNTS

# ── 路径配置 ──────────────────────────────────────────────────────────────────
PROJECT_DIR = Path(__file__).parent.parent
DATA_DIR    = PROJECT_DIR / "data"
TMP_DIR     = DATA_DIR / "_tmp_downloads"

CHROME_USER_DATA = Path.home() / "Library/Application Support/Google/Chrome"
CHROME_PROFILE   = "Default"
COOKIES_FILE = PROJECT_DIR / ".eagle_cookies.json"

VIDEO_URL = "https://ad.oceanengine.com/material_center/management/video?aadvid={aadvid}#source=ad_navigator"
IMAGE_URL = "https://ad.oceanengine.com/material_center/management/carousel?aadvid={aadvid}"

LOGIN_URL  = "https://ad.oceanengine.com"
LOGIN_CHECK = "ad.oceanengine.com/overture"   # 登录后的路径特征

# ── 日期解析 ──────────────────────────────────────────────────────────────────

def parse_dates(raw: str) -> list[date]:
    today = date.today()
    results = []
    for token in raw.split(","):
        token = token.strip()
        if token == "today":
            results.append(today)
        elif token == "yesterday":
            results.append(today - timedelta(days=1))
        elif len(token) == 4 and token.isdigit():   # MMDD
            mm, dd = int(token[:2]), int(token[2:])
            d = date(today.year, mm, dd)
            if d > today:
                d = date(today.year - 1, mm, dd)
            results.append(d)
        elif len(token) == 10:                       # YYYY-MM-DD
            results.append(date.fromisoformat(token))
        else:
            raise ValueError(f"无法识别日期格式: {token}，支持 today/yesterday/MMDD/YYYY-MM-DD")
    return results

# ── Playwright 工具函数 ───────────────────────────────────────────────────────

def load_chrome_cookies() -> list:
    """从运行中的 Chrome 读取 oceanengine.com 的 Cookie，转换为 Playwright 格式"""
    import browser_cookie3
    cj = browser_cookie3.chrome(domain_name='.oceanengine.com')
    result = []
    for c in cj:
        cookie = {
            "name":   c.name,
            "value":  c.value,
            "domain": c.domain if c.domain.startswith(".") else "." + c.domain,
            "path":   c.path or "/",
        }
        if c.expires:
            cookie["expires"] = int(c.expires)
        if c.secure:
            cookie["secure"] = True
        result.append(cookie)
    print(f"[Cookie] 从 Chrome 读取 {len(result)} 条 oceanengine.com Cookie")
    return result
    """确保已登录：检测到登录页则等待用户登录，登录后保存 Cookie"""
    time.sleep(2)
    url = page.url
    print(f"  [当前URL] {url}")

    if "login" not in url and "passport" not in url and "sso" not in url:
        print("  [已登录] Cookie 有效")
        return

    print("\n" + "="*60)
    print("[需要登录] 请在弹出的 Chrome 窗口中完成登录。")
    print("登录成功后脚本会自动继续，无需任何操作。")
    print("="*60 + "\n")

    deadline = time.time() + 300  # 最多等 5 分钟
    while time.time() < deadline:
        time.sleep(2)
        try:
            cur = page.url
        except Exception:
            continue
        if "login" not in cur and "passport" not in cur and "sso" not in cur:
            print(f"[OK] 登录成功，正在保存 Cookie...")
            time.sleep(2)
            cookies = context.cookies()
            import json
            COOKIES_FILE.write_text(json.dumps(cookies, ensure_ascii=False, indent=2))
            print(f"[OK] Cookie 已保存到 {COOKIES_FILE.name}，下次无需重新登录")
            return

    raise RuntimeError("等待登录超时（5分钟），请重试")
    """等待素材列表加载完成"""
    page.wait_for_selector(
        "table tbody tr, .material-list-item, [class*='list-item']",
        timeout=timeout
    )

def check_login(page):
    time.sleep(2)
    url = page.url
    print(f"  [当前URL] {url}")
    if "login" in url or "passport" in url:
        raise RuntimeError(
            "Cookie 注入后仍跳转到登录页，可能 Cookie 已过期。\n"
            "请确认你的 Chrome 中 ad.oceanengine.com 仍处于登录状态，然后重试。"
        )

def set_date_range(page, target_date: date):
    """将页面日期设置为指定日期"""
    from datetime import date as _date
    yesterday = _date.today() - timedelta(days=1)

    page.get_by_text("数据统计时间").first.click()
    time.sleep(1)

    # 关闭可能挡住快捷按钮的浮层（如任务提示 poptip）
    for sel in ["[class*='poptip-close']", "[class*='poptip'] button", "[class*='poptip-title'] ~ *"]:
        try:
            el = page.locator(sel).first
            if el.is_visible(timeout=500):
                el.click()
                time.sleep(0.3)
                break
        except Exception:
            pass
    # 也可以按 Escape 关闭浮层
    page.keyboard.press("Escape")
    time.sleep(0.5)
    page.get_by_text("数据统计时间").first.click()
    time.sleep(1)

    if target_date == yesterday:
        shortcut = page.locator("[class*='shortcut']", has_text="昨天").last
        shortcut.click(timeout=10000)
    elif target_date == _date.today():
        page.locator("[class*='shortcut']", has_text="今天").last.click(timeout=10000)
    else:
        try:
            page.get_by_text("自定义").last.click()
            time.sleep(0.5)
        except Exception:
            pass
        date_str = target_date.strftime("%Y-%m-%d")
        inputs = page.locator("input[placeholder*='开始'], input[placeholder*='结束']").all()
        if len(inputs) >= 2:
            inputs[0].fill(date_str)
            inputs[0].press("Enter")
            time.sleep(0.3)
            inputs[1].fill(date_str)
            inputs[1].press("Enter")
        for txt in ["确认", "确定", "查询"]:
            try:
                btn = page.get_by_text(txt).first
                if btn.is_visible(timeout=1000):
                    btn.click()
                    break
            except Exception:
                pass

    time.sleep(2)


def select_custom_columns(page):
    """点「选择列」→ 线索收集 → 勾选三个回访列 → 确定"""
    target_cols = [
        "回访-加为好友(计费时间)",
        "回访-高潜成交(计费时间)",
        "回访-信息确认(计费时间)",
    ]

    # 点「选择列」按钮
    page.locator('button:has(iconpark-icon[name="oc-icon-metrics"])').first.click()
    time.sleep(2)

    # 点「线索收集」分类
    try:
        page.get_by_text("线索收集", exact=True).first.click()
        time.sleep(1)
    except Exception as e:
        print(f"  [列] 点击「线索收集」失败: {e}")

    # 逐个勾选（已勾选则跳过）
    for col_name in target_cols:
        try:
            # 找包含该文字的 label 下的 checkbox
            label = page.locator(f"label:has-text('{col_name}')").first
            checkbox = label.locator("input[type=checkbox]")
            if checkbox.count() == 0:
                checkbox = label.locator("[role=checkbox]")
            is_checked = checkbox.evaluate("el => el.checked || el.getAttribute('aria-checked') === 'true'")
            if not is_checked:
                checkbox.click(force=True)
                time.sleep(0.3)
                print(f"  [列] 已勾选: {col_name}")
            else:
                print(f"  [列] 已是勾选状态: {col_name}")
        except Exception as e:
            print(f"  [列] 勾选 {col_name} 失败: {e}")

    # 点「确定」
    try:
        page.get_by_text("确定", exact=True).first.click()
        time.sleep(2)
        print("  [列] 已点确定")
    except Exception as e:
        print(f"  [列] 点确定失败: {e}")


def wait_for_list(page, timeout=60000):
    """等待下载按钮出现（说明数据已加载）"""
    page.wait_for_selector(
        'button:has(iconpark-icon[name="oc-icon-download"])',
        timeout=timeout
    )

def click_export(page, account_name: str, lib_type: str) -> Optional[Path]:
    """点击导出（下载）按钮，等待文件下载，返回下载文件路径"""
    TMP_DIR.mkdir(parents=True, exist_ok=True)

    selector = 'button:has(iconpark-icon[name="oc-icon-download"])'
    try:
        btn = page.locator(selector).first
        btn.wait_for(state="visible", timeout=10000)
    except Exception:
        print(f"  [警告] {account_name} {lib_type} 未找到下载按钮，跳过")
        return None

    # 等待自定义列完全渲染
    time.sleep(4)

    safe_name = account_name.replace("/", "_").replace(" ", "_")
    dest = TMP_DIR / f"{safe_name}_{lib_type}.csv"

    with page.expect_download(timeout=60000) as dl_info:
        btn.click()

    download = dl_info.value
    download.save_as(str(dest))
    print(f"  [OK] 下载完成: {dest.name}")
    return dest

# ── CSV 合并 ──────────────────────────────────────────────────────────────────

FIELD_MAP = {
    "素材名称": "视频名称",   # 图文库
    "预览链接": "视频链接",   # 图文库
    "图文名称": "视频名称",
    "图文链接": "视频链接",
    "图文id":   "素材id",
}




def normalize_row(row: dict, account: dict, lib_type: str) -> dict:
    normalized = {}
    for k, v in row.items():
        key = FIELD_MAP.get(k.strip(), k.strip())
        normalized[key] = v.strip() if isinstance(v, str) else v
    normalized["账户名称"] = account["name"]
    normalized["账户类型"] = account["type"]
    return normalized

def merge_csvs(file_map: list, output_path: Path):
    """
    file_map: [(csv_path, account_dict, lib_type), ...]
    去重键：素材id + 账户名称
    """
    seen     = set()
    all_rows = []

    for csv_path, account, lib_type in file_map:
        if csv_path is None or not csv_path.exists():
            continue
        with open(csv_path, encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                norm = normalize_row(row, account, lib_type)
                key  = (norm.get("素材id", "").strip(), account["name"])
                if key in seen:
                    continue
                seen.add(key)
                all_rows.append(norm)

    if not all_rows:
        print("[警告] 没有收集到任何数据行，跳过输出")
        return

    fieldnames = list(all_rows[0].keys())

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(all_rows)

    print(f"\n[合并完成] {len(all_rows)} 行 → {output_path}")

# ── 主流程 ────────────────────────────────────────────────────────────────────

def download_one_account(page, account: dict, target_date: date) -> tuple:
    """下载一个账户的视频库和图文库，返回 (video_path, image_path)"""
    name   = account["name"]
    aadvid = account["aadvid"]
    results = []

    for lib_type, url_tpl in [("视频库", VIDEO_URL), ("图文库", IMAGE_URL)]:
            url = url_tpl.format(aadvid=aadvid)
            print(f"\n  → {name} | {lib_type}")
            try:
                try:
                    page.goto(url, wait_until="domcontentloaded", timeout=45000)
                except Exception as nav_err:
                    if "Download is starting" in str(nav_err):
                        # 导航触发了下载，等一下再重新导航
                        time.sleep(2)
                        page.goto(url, wait_until="domcontentloaded", timeout=30000)
                    else:
                        raise
                page.wait_for_load_state("networkidle", timeout=15000)
                set_date_range(page, target_date)
                wait_for_list(page)
                select_custom_columns(page)
                wait_for_list(page)  # 确定后页面刷新，重新等下载按钮
                path = click_export(page, name, lib_type)
                results.append(path)
            except RuntimeError:
                raise
            except PWTimeout:
                print(f"  [超时] {name} {lib_type} 页面加载超时，跳过")
                results.append(None)
            except Exception as e:
                print(f"  [错误] {name} {lib_type}: {e}")
                results.append(None)

    return tuple(results)

def run(dates: list, dry_run: bool, limit: Optional[int] = None):
    accounts = [a for a in ACCOUNTS if a["type"] == "自投"]
    if limit:
        accounts = accounts[:limit]
    print(f"[开始] 处理日期: {[d.isoformat() for d in dates]}")
    print(f"[账户数] {len(accounts)}（仅自投）")

    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            channel="chrome",
            headless=True,
            args=["--disable-blink-features=AutomationControlled"],
        )

        # 加载已保存的 Cookie（如果有）
        import json
        context_opts = {"accept_downloads": True}
        context = browser.new_context(**context_opts)
        TMP_DIR.mkdir(parents=True, exist_ok=True)

        # 从运行中的 Chrome 直接读取 Cookie
        cookies = load_chrome_cookies()
        context.add_cookies(cookies)

        page = context.new_page()
        # 遇到意外下载时保存到临时目录，不阻断导航
        page.on("download", lambda dl: dl.save_as(str(TMP_DIR / dl.suggested_filename)))

        # 先访问首页检查登录
        page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=30000)
        check_login(page)

        for target_date in dates:
            date_tag   = target_date.strftime("%m%d")
            output_csv = DATA_DIR / f"引导加微每日数据-{date_tag}.csv"
            file_map   = []

            print(f"\n{'='*50}")
            print(f"[日期] {target_date.isoformat()}")

            for account in accounts:
                video_path, image_path = download_one_account(page, account, target_date)
                if video_path:
                    file_map.append((video_path, account, "视频"))
                if image_path:
                    file_map.append((image_path, account, "图文"))

            if dry_run:
                print(f"\n[dry-run] 跳过合并和推送，临时文件在 {TMP_DIR}")
                continue

            merge_csvs(file_map, output_csv)

            # 触发日报生成（读全部历史文件，叠加多日）
            report_script = PROJECT_DIR / "scripts" / "generate_report_daily_guide.py"
            guide_report_dir = Path.home() / "Desktop/daily-guide-report"
            if report_script.exists():
                print(f"\n[日报] 生成多日叠加报告...")
                result = subprocess.run(
                    [sys.executable, str(report_script)],
                    cwd=str(PROJECT_DIR),
                    capture_output=True, text=True,
                )
                print(result.stdout.strip())
                # 找生成的最新报告
                reports = sorted((PROJECT_DIR / "reports").glob("引导素材每日分析_*.html"))
                if reports and guide_report_dir.exists():
                    shutil.copy2(str(reports[-1]), str(guide_report_dir / "index.html"))
                    print(f"[日报] 已覆盖 {guide_report_dir}/index.html")

        browser.close()

    # 清理临时文件
    if not dry_run and TMP_DIR.exists():
        shutil.rmtree(TMP_DIR)
        print(f"\n[清理] 删除临时目录 {TMP_DIR}")

    if not dry_run:
        git_push(dates)

def git_push(dates: list[date]):
    tags    = [d.strftime("%m%d") for d in dates]
    msg     = f"auto: 更新每日数据 {', '.join(tags)}"
    cmds = [
        ["git", "add", "data/"],
        ["git", "commit", "-m", msg],
        ["git", "push"],
    ]
    for cmd in cmds:
        result = subprocess.run(cmd, cwd=str(PROJECT_DIR), capture_output=True, text=True)
        if result.returncode != 0:
            print(f"[git] {' '.join(cmd)} 失败: {result.stderr.strip()}")
        else:
            print(f"[git] {' '.join(cmd)} OK")

# ── CLI 入口 ──────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="千川素材库每日数据下载合并脚本")
    parser.add_argument(
        "--date", default="yesterday",
        help="日期: today / yesterday / MMDD / YYYY-MM-DD，多天用逗号分隔"
    )
    parser.add_argument("--dry-run", action="store_true", help="只下载，不合并不推送")
    parser.add_argument("--limit", type=int, default=None, help="只跑前 N 个账户（用于测试）")
    args = parser.parse_args()

    dates = parse_dates(args.date)
    run(dates, dry_run=args.dry_run, limit=args.limit)

if __name__ == "__main__":
    main()
