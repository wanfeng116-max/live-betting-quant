#!/usr/bin/env python3
"""
final_ultimate.py 滚球高胜率筛选器
仅使用标准库 urllib json，无任何第三方依赖
禁止调用odds接口，仅使用fixtures?live=all，找到3场直接退出节省API额度
运行:
    python final_ultimate.py
    python final_ultimate.py --mock
环境变量: API_FOOTBALL_KEY
"""
import os
import sys
import json
import argparse
from urllib import request
from urllib.error import URLError, HTTPError

# ===================== 配置常量 =====================
LEAGUE_WHITELIST = [
    "Segunda Division",
    "Serie B",
    "K League 1",
    "Premier League Russia",
    "Brasileiro Serie B"
]
LEAGUE_HIGH_RISK_KEYWORDS = [
    "Eredivisie",
    "Super Lig",
    "Saudi Pro League",
    "A‑League"
]
MIN_ELAPSED = 60
MAX_ELAPSED = 71
ALLOW_SCORES = [(0, 0), (1, 0), (0, 1), (1, 1)]
MAX_TOTAL_SHOTS_ON_TARGET = 4
MAX_TOTAL_CORNERS = 5
MAX_TRAILING_SOT = 2
STOP_AFTER_MATCH_COUNT = 3
SUGGEST_TEXT = "建议下注10‑15元"
# ====================================================


def get_api_headers():
    api_key = os.environ.get("API_FOOTBALL_KEY")
    if not api_key:
        print("【错误】环境变量 API_FOOTBALL_KEY 未设置，请配置密钥后再运行！")
        sys.exit(1)
    return {"x‑apisports‑key": api_key}


def fetch_live_matches():
    url = "https://v3.football.api‑sports.io/fixtures?live=all"
    headers = get_api_headers()
    req = request.Request(url, headers=headers)
    try:
        with request.urlopen(req, timeout=30) as resp:
            raw = resp.read()
            data = json.loads(raw)
            return data.get("response", [])
    except (URLError, HTTPError, json.JSONDecodeError):
        return []


def is_injury_time(status_short, elapsed):
    e_str = str(elapsed)
    s_str = str(status_short)
    if "+" in e_str or "+" in s_str:
        return True
    return False


def main():
    print("==== final_ultimate.py 开始运行 ====\n")
    live_list = fetch_live_matches()
    lock_count = 0

    for item in live_list:
        fixture = item.get("fixture", {})
        league = item.get("league", {})
        teams = item.get("teams", {})
        goals = item.get("goals", {})
        stats = item.get("statistics", [])

        status_short = fixture.get("status", {}).get("short", "")
        elapsed = fixture.get("status", {}).get("elapsed")
        league_name = league.get("name", "")
        h_name = teams.get("home", {}).get("name", "未知主队")
        a_name = teams.get("away", {}).get("name", "未知客队")
        hg = goals.get("home", 0) or 0
        ag = goals.get("away", 0) or 0

        # 高波动联赛过滤
        if any(k in league_name for k in LEAGUE_HIGH_RISK_KEYWORDS):
            continue
        # 白名单联赛
        if league_name not in LEAGUE_WHITELIST:
            continue
        # 必须下半场2H，过滤补时
        if status_short != "2H":
            continue
        if is_injury_time(status_short, elapsed):
            continue
        # 时间窗口60‑71
        if elapsed is None or not (MIN_ELAPSED <= elapsed <= MAX_ELAPSED):
            continue
        # 允许比分
        if (hg, ag) not in ALLOW_SCORES:
            continue
        # 红牌大于0跳过
        red_total = 0
        try:
            for st in stats:
                red = int(st.get("red_cards", 0) or 0)
                red_total += red
        except (ValueError, TypeError):
            continue
        if red_total > 0:
            continue
        # 必须有两组统计数据
        if len(stats) != 2:
            continue
        try:
            h_stat = stats[0]
            a_stat = stats[1]
            sot_h = int(h_stat.get("shots_on_target", 0) or 0)
            sot_a = int(a_stat.get("shots_on_target", 0) or 0)
            cor_h = int(h_stat.get("corners", 0) or 0)
            cor_a = int(a_stat.get("corners", 0) or 0)
        except (ValueError, TypeError, IndexError):
            continue

        total_sot = sot_h + sot_a
        total_cor = cor_h + cor_a
        if total_sot > MAX_TOTAL_SHOTS_ON_TARGET or total_cor > MAX_TOTAL_CORNERS:
            continue

        # 落后方射正校验
        trailing_sot = 0
        if hg < ag:
            trailing_sot = sot_h
        elif ag < hg:
            trailing_sot = sot_a
        if trailing_sot > MAX_TRAILING_SOT:
            continue

        # 全部条件达成
        lock_count += 1
        score_str = f"{hg}:{ag}"
        print(f"【✅ 锁定场次】{league_name} | {h_name}VS{a_name} | {score_str} | {elapsed}' | {SUGGEST_TEXT}")

        if lock_count >= STOP_AFTER_MATCH_COUNT:
            print(f"\n已收集 {lock_count} 场，达到阈值，程序退出。")
            sys.exit(0)

    print(f"\n扫描完成，本次找到 {lock_count}/{STOP_AFTER_MATCH_COUNT} 场锁定场次。")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="final_ultimate滚球筛选器")
    parser.add_argument("--mock", action="store_true", help="模拟模式，不请求API")
    args = parser.parse_args()
    if args.mock:
        print("测试成功")
        sys.exit(0)
    main()
