#!/usr/bin/env python3
"""
IP调研批量工具
1. 自动调用 API 批量分析（auto 模式）
2. 生成批量 prompt 文件，手动粘贴获取分析（generate 模式）
3. 解析手动结果，写入 CSV（parse 模式）
"""

import csv
import os
import re
import time

ACCOUNTS = [
    ("北大胡源讲数学", "63202050543"),
    ("步学赵礼显数学", "tongjizlx"),
    ("亮亮巧解数学", "wll0310520"),
    ("小竹数学", "baihuishuxue"),
    ("老胡模型数学思维提升", "97665973460"),
    ("孙明杰高阶数学｜澜启思", "168611641"),
    ("梦言通解数学", "38231157381"),
    ("北大胡源数学", "58639908055"),
    ("勇哥高中数学", "yggzsx"),
    ("数学王子悦老师", "34419618241"),
    ("高中数学刘阳", "dy0yrzeph7vh"),
    ("高中数学-李钰提分课堂", "grsx20230606"),
    ("夏梦迪物理", "602799701"),
    ("黄夫人物理讲义", "84482798170"),
    ("石墨哥物理（不刷题）", "56127596468"),
    ("云南投学林老师物理", "24156872010"),
    ("林老师物理（进援领…", "26071358694"),
    ("王羽物理", "785741388"),
    ("北大物理莫荒年", "271304488"),
    ("罗卜高中物理", "physics_tt"),
    ("天津物理王老师", "24555038104"),
    ("高中物理核姐（好课晗）", "40866953065"),
    ("欢哥讲化学", "20870768727"),
    ("张梅酷好化学", "vx.zmgkh06"),
    ("小计老师-高中化学", "68564996563"),
    ("赵老师讲化学", "qkhxwg"),
    ("柱哥陪你学化学", "36446462427"),
    ("李林生物", "AnderLi"),
    ("李林生物", "82532099967"),
    ("奇函侃语文-前沿洞界", "26702725352"),
    ("杨奇函讲语文", "54799536643"),
    ("乘风语文（湖哪）", "Chengfengyuwen"),
    ("清华奇函老师讲语文", "99631854961"),
    ("杨奇函清华说语文", "77390293657"),
    ("学过石油的语文老师", "54212554005"),
    ("杨奇函说语文-凡七文化", "46246023283"),
    ("语文老师李妍", "40129413160"),
    ("陈朝辉大语文讲堂", "71826409371"),
    ("语文有点Q", "57977427103"),
    ("清华杨奇函数语文", "30676015985"),
    ("高考英语私教", "52432685518"),
    ("豆神英语·剑桥小王者", "heranyingyu"),
    ("曹志巧学英语", "60430935048"),
    ("叽里呱啦英语启蒙", "jiliguala168"),
    ("郑州英语Coco", "36506533431"),
    ("猫耳朵英语CLUB", "cat_ear"),
    ("暖暖读英语", "Nuan910ma"),
    ("白老师英语阅读", "73339908666"),
    ("学丞晓艳英语图书旗舰", "55505163362"),
    ("英语老师张得分", "83097884608"),
    ("学丞刘晓艳-初中英语", "50910612781"),
    ("学丞刘晓艳-小学英语", "89694837506"),
    ("LingoAce英语口语提", "80855549742"),
    ("英语段老师", "renrenshuo666"),
    ("肖数说", "xiaoym1024"),
    ("卷卷学姐", "55434336194"),
    ("小单学长", "92840645695"),
    ("小蓝颖Yancy", "1807071340"),
    ("高阶物理~张哲", "zhangzhewuli"),
    ("祝小诺", "zhu1nuo_"),
    ("从前有座石榴园", "65489281418"),
    ("郑在磕数理竞赛", "72320153004"),
    ("北大白杨老师", "kaiqiao2026"),
    ("小马爱讲地理", "97682754754"),
    ("张三三-", "avazhangsansan"),
]

ACCOUNTS_BATCH2 = [
    ("学丞刘晓艳-高中满分", "51266676049"),
    ("英语老师Anita", "27776405173"),
    ("孙志立英语", "837375133"),
    ("Todd外教英语", "toddenglish"),
    ("Iris学英语", "seven_teennnnn"),
    ("上海英语阿紫老师", "33470279976"),
    ("英语十七老师", "yingyu17"),
    ("龙坚英语", "23043837291"),
    ("Bingo教英语", "74804585465"),
    ("悉尼崔珉CC讲英语", "98475933469"),
    ("何凯文英语思维", "74099823015"),
    ("小蕾老师教英语", "xiaoleiyingyu"),
    ("Frank新概念特色精讲", "franktopgear"),
    ("辰哥初中英语", "92966691391"),
    ("俊杰老师说英语", "33122985601"),
    ("教英语的Sharon老师", "161090088"),
    ("王子英语小课堂", "60791866726"),
    ("Ranne助力英语", "RanneEnglish"),
    ("王子老师讲英语", "47730296988"),
    ("洋女婿·大麦英语", "1190636711"),
    ("英语雪梨老师(早8:00)", "xueliyingyu"),
    ("媛媛老师讲英语", "LHYYDSWL"),
    ("鲸鱼老师教英语", "24974923945"),
    ("杨妈英语思维起飞", "79985934772"),
    ("星星学长晚八点直播", "78401723369"),
    ("小单学长", "92840645696"),
    ("哈工大傅学长", "hit_fu"),
    ("北大学长跳跳", "20799736"),
    ("清华安心学长-自学能", "qinghuaanxin"),
    ("木木学长（研）", "Zhemuhelper1"),
    ("高中数学精讲--李", "lt1017663126"),
    ("高中数学杨老师（深度陪跑）", "txpeipao"),
    ("小计老师-高中化学", "68564936563"),
    ("榆高高中数学宁老师", "2023gaokaoManfen"),
    ("高中数学刘阳", "dy0yrzaph7vh"),
    ("高中数学-李钰提分课堂", "gzsx20230606"),
    ("高中班主任李老师", "68356084343"),
    ("一数儿的课高中", "41001162038"),
    ("刘勋雯政史地提分(不)", "59943877492"),
    ("清华宇情-学习方法", "62414274746"),
    ("清华宇情讲学习（渐入嘉境）", "94037836839"),
    ("叁月聚粮", "83377844502"),
    ("伴读马老狮", "25593998509"),
    ("奇函侃语文-前沿跨界", "28702725352"),
    ("老贵本尊", "33343238164"),
    ("非少讲理科-扬涵", "97797696063"),
    ("杨奇函讲语文", "54798536643"),
    ("司马一", "SMYaixuexi"),
    ("清华杨奇函来了", "98548013635"),
    ("鱼蛋教育圈", "22043127112"),
    ("AkkkkEN.", "Xinkai.C_0418"),
    ("王垚博士", "77140253068"),
    ("曾曦老师讲作文", "91055872445"),
    ("柴风语文（溺罐）", "chengfengyuwen"),
    ("北大张钰蔓", "m314358657"),
    ("李大海（差点火了版）", "YouAskedForIt111"),
    ("刘彬老师速记单词", "53093652679"),
    ("齐腾老师思维训练", "32829960154"),
    ("学霸三人行", "80632814937"),
    ("清华奇函老师讲语文", "39631854961"),
    ("兔子学姐", "dyeuas7398a4"),
    ("石墨哥物理（不刷题）", "56127586468"),
    ("林老师讲物理", "35575295252"),
    ("理学-亮亮聊思维", "43664617687"),
]

PROMPT_TEMPLATE = """请分析抖音账号「{name}」（抖音号：{douyin_id}），严格按以下格式输出，每项一行，不要多余内容：

所属机构：（机构全称，独立运营则写"独立"）
IP人设定位：（20字以内）
差异化背书：（学历/经历/头衔，20字以内）
IP内容风格：（20字以内）
核心选题方向：（主要打什么用户痛点，20字以内）
视觉/表达风格：（画面感+语言风格，20字以内，如不确定注明"待核实"）
IP后端转化：（引流路径，20字以内，如不确定注明"待核实"）
商业模式：（变现方式，20字以内）
可借鉴点：（对标参考价值，30字以内）"""

FIELDS = [
    "所属机构",
    "IP人设定位",
    "差异化背书",
    "IP内容风格",
    "核心选题方向",
    "视觉/表达风格",
    "IP后端转化",
    "商业模式",
    "可借鉴点",
]

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
PROMPT_FILE = os.path.join(OUTPUT_DIR, "ip_research_prompts.txt")
RESULT_INPUT_FILE = os.path.join(OUTPUT_DIR, "ip_research_results.txt")
CSV_OUTPUT_FILE = os.path.join(OUTPUT_DIR, "ip_research_output.csv")
CSV_OUTPUT_FILE_BATCH2 = os.path.join(OUTPUT_DIR, "ip_research_output_batch2.csv")

API_KEY = os.environ.get("ZHENGUANYU_API_KEY", "")
BASE_URL = "https://model.zhenguanyu.com/v1"
MODEL = "deepseek-v4-pro"


def call_api(name: str, douyin_id: str) -> str:
    try:
        from openai import OpenAI
    except ImportError:
        print("❌ 缺少 openai 库，请运行：pip install openai")
        raise
    client = OpenAI(api_key=API_KEY, base_url=BASE_URL)
    prompt = PROMPT_TEMPLATE.format(name=name, douyin_id=douyin_id)
    response = client.chat.completions.create(
        model=MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3,
    )
    return response.choices[0].message.content.strip()


def parse_block(block: str) -> dict:
    row = {}
    for field in FIELDS:
        pattern = rf"{re.escape(field)}[：:]\s*(.+)"
        match = re.search(pattern, block)
        row[field] = match.group(1).strip() if match else ""
    return row


def auto_run(batch=1):
    if not API_KEY:
        print("❌ 未设置 API Key，请运行：")
        print('   export ZHENGUANYU_API_KEY="你的key"')
        return

    accounts = ACCOUNTS if batch == 1 else ACCOUNTS_BATCH2
    output_file = CSV_OUTPUT_FILE if batch == 1 else CSV_OUTPUT_FILE_BATCH2

    print(f"🚀 开始批量分析第{batch}批，共 {len(accounts)} 个账号，模型：{MODEL}\n")
    rows = []
    failed = []

    for i, (name, douyin_id) in enumerate(accounts, 1):
        print(f"[{i:2d}/{len(accounts)}] {name}...", end="", flush=True)
        try:
            result = call_api(name, douyin_id)
            row = parse_block(result)
            rows.append({"达人": name, "抖音号": douyin_id, **row})
            print(" ✅")
            time.sleep(1)
        except Exception as e:
            print(f" ❌ ({e})")
            failed.append((i, name, str(e)))
            rows.append({"达人": name, "抖音号": douyin_id, **{f: "" for f in FIELDS}})

    with open(output_file, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["达人", "抖音号"] + FIELDS)
        writer.writeheader()
        writer.writerows(rows)

    print(f"\n✅ 完成！CSV：{output_file}")
    print(f"   成功：{len(rows) - len(failed)} 条，失败：{len(failed)} 条")
    if failed:
        print("\n失败账号：")
        for idx, name, err in failed:
            print(f"  [{idx}] {name}: {err}")


def generate_prompts():
    """生成批量 prompt 文件"""
    lines = []
    lines.append("=" * 60)
    lines.append(f"共 {len(ACCOUNTS)} 个账号，每个账号复制一段给 DeepSeek")
    lines.append("把所有结果粘贴到 ip_research_results.txt，再运行 parse 模式")
    lines.append("=" * 60 + "\n")

    for i, (name, douyin_id) in enumerate(ACCOUNTS, 1):
        lines.append(f"【账号 {i}/{len(ACCOUNTS)}】")
        lines.append(PROMPT_TEMPLATE.format(name=name, douyin_id=douyin_id))
        lines.append("\n" + "-" * 40 + "\n")

    with open(PROMPT_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(f"✅ 已生成 prompt 文件：{PROMPT_FILE}")
    print(f"   共 {len(ACCOUNTS)} 个账号")
    print()
    print("下一步：")
    print("1. 打开上面的文件，逐段复制给 DeepSeek 网页版")
    print("2. 把所有结果粘贴到：")
    print(f"   {RESULT_INPUT_FILE}")
    print("3. 运行：python ip_research_batch.py parse")


def parse_results():
    """解析 DeepSeek 返回结果，写入 CSV"""
    if not os.path.exists(RESULT_INPUT_FILE):
        print(f"❌ 找不到结果文件：{RESULT_INPUT_FILE}")
        print("请先把 DeepSeek 的输出粘贴到该文件后再运行")
        return

    with open(RESULT_INPUT_FILE, "r", encoding="utf-8") as f:
        content = f.read()

    # 按账号分割（每段分析之间用分隔线或空行隔开）
    # 尝试按 FIELDS[0]（所属机构）出现来分割
    blocks = re.split(r"\n(?=所属机构：)", content)
    blocks = [b.strip() for b in blocks if b.strip()]

    rows = []
    for block in blocks:
        row = {}
        for field in FIELDS:
            pattern = rf"{re.escape(field)}[：:]\s*(.+)"
            match = re.search(pattern, block)
            row[field] = match.group(1).strip() if match else ""
        if any(row.values()):
            rows.append(row)

    if not rows:
        print("❌ 未能解析到任何结果，请检查结果文件格式")
        return

    # 写入 CSV
    with open(CSV_OUTPUT_FILE, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["达人", "抖音号"] + FIELDS)
        writer.writeheader()

        for i, row in enumerate(rows):
            name, douyin_id = ACCOUNTS[i] if i < len(ACCOUNTS) else ("", "")
            full_row = {"达人": name, "抖音号": douyin_id}
            full_row.update(row)
            writer.writerow(full_row)

    print(f"✅ 已生成 CSV：{CSV_OUTPUT_FILE}")
    print(f"   成功解析 {len(rows)} 条记录")
    print()
    print("直接用 Excel/Google Sheet 打开，列顺序：")
    print("达人 | 抖音号 | 所属机构 | IP人设定位 | 差异化背书 | IP内容风格 |")
    print("核心选题方向 | 视觉/表达风格 | IP后端转化 | 商业模式 | 可借鉴点")


if __name__ == "__main__":
    import sys

    mode = sys.argv[1] if len(sys.argv) > 1 else "auto"
    batch = int(sys.argv[2]) if len(sys.argv) > 2 else 1

    if mode == "auto":
        auto_run(batch=batch)
    elif mode == "parse":
        parse_results()
    else:
        generate_prompts()
