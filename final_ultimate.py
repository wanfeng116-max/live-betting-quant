#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
final_ultimate.py 滚球高胜率筛选器
彻底修复 latin-1 编码报错：全部特殊短横线替换为普通'-'，quote编码Bark推送
新增：球队英文转中文 + Bark推送
约束：仅使用urllib json，无第三方库；支持--mock；北京时间23:30后退出；找到3-5场退出省API额度
"""

import argparse
import json
import os
import sys
import urllib.request
from urllib.parse import quote
from datetime import datetime, timezone, timedelta

# ===================== 球队名称中英翻译字典 =====================
TEAM_NAME_MAP = {
    "Leganes": "莱加内斯",
    "Las Palmas": "拉斯帕尔马斯",
    "Eibar": "埃瓦尔",
    "Espanyol": "西班牙人",
    "Parma": "帕尔马",
    "Palermo": "巴勒莫",
    "Sampdoria": "桑普多利亚",
    "Zenit": "泽尼特",
    "Spartak Moscow": "莫斯科斯巴达",
    "Dynamo Moscow": "莫斯科迪纳摩"
}

# ===================== 联赛配置 全部使用普通减号- =====================
LEAGUE_WHITELIST = ["Segunda Division", "Serie B", "K League 1", "Premier League Russia", "Brasileiro Serie B"]
LEAGUE_BLACKLIST = ["Eredivisie", "Super Lig", "Saudi Pro League", "A-League"]

# Bark推送地址
BARK_URL = "https://api.day.app/xFZcs4kMkNaRxVs3aXzzfM/"

# 北京时间时区
BJ_TZ = timezone(timedelta(hours=8))

# ===================== 球队翻译函数 =====================
def translate_team_name(team_name):
    """英文球队名翻译中文，字典不存在直接返回原文本"""
    if team_name in TEAM_NAME_MAP:
        return TEAM_NAME_MAP[team_name]
    return team_name


def send_bark_notification(title, content):
    """使用urllib发送Bark推送消息，quote编码解决中文特殊字符编码报错"""
    try:
        encoded_title = quote(title)
        encoded_body = quote(content)
        full_url = f"{BARK_URL}{encoded_title}/{encoded_body}"
        req = urllib.request.Request(full_url, method="GET")
        with urllib.request.urlopen(req, timeout=10) as resp:
            resp.read()
    except Exception as e:
        print(f"⚠️ Bark推送异常: {str(e)}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mock", action="store_true", help="mock模拟模式，不请求真实API")
    args = parser.parse_args()

    # mock模式直接输出测试信息
    if args.mock:
        print("【Mock测试模式】测试成功")
        send_bark_notification("Mock测试通知", "程序模拟运行正常，中文测试：莱加内斯 VS 埃瓦尔")
        sys.exit(0)

    # 读取环境变量API Key
    api_key = os.environ.get("API_FOOTBALL_KEY", "")
    if not api_key:
        print("❌ 环境变量 API_FOOTBALL_KEY 未设置，程序退出")
        sys.exit(1)

    # 获取当前北京时间，23:30之后直接退出
    now_beijing = datetime.now(BJ_TZ)
    current_hour = now_beijing.hour
    current_minute = now_beijing.minute
    if current_hour >= 23 and current_minute >= 30:
        print(f"🕐 当前北京时间 {current_hour}:{current_minute}，23:30之后停止运行，程序退出")
        sys.exit(0)

    # 【关键修正】正确的 API 头部和地址
    headers = {
        "x-apisports-key": api_key
    }

    # 请求实时live全部比赛
    url = "https://v3.football.api-sports.io/fixtures?live=all"
    req = urllib.request.Request(url, headers=headers)

    try:
        with urllib.request.urlopen(req, timeout=15) as response:
            raw_data = response.read()
            resp_json = json.loads(raw_data)
    except Exception as err:
        print(f"❌ API网络请求失败：{err}")
        sys.exit(1)

    response_data = resp_json.get("response", [])
    match_hit_list = []

    for item in response_data:
        fixture = item.get("fixture", {})
        league = item.get("league", {})
        teams = item.get("teams", {})
        home_raw = teams.get("home", {}).get("name", "")
        away_raw = teams.get("away", {}).get("name", "")
        home_cn = translate_team_name(home_raw)
        away_cn = translate_team_name(away_raw)

        league_name = league.get("name", "")
        minute = fixture.get("status", {}).get("elapsed", 0)
        status_short = fixture.get("status", {}).get("short", "")

        # 黑名单联赛直接跳过
        is_black = any(b in league_name for b in LEAGUE_BLACKLIST)
        if is_black:
            continue
        # 不在白名单联赛跳过
        if league_name not in LEAGUE_WHITELIST:
            continue

        # 比赛时间条件：50-70分钟，排除带+补时
        if not (50 <= minute <= 70):
            continue
        if "+" in str(status_short):
            continue

        home_goals = item.get("goals", {}).get("home", 0) or 0
        away_goals = item.get("goals", {}).get("away", 0) or 0
        score_str = f"{home_goals}-{away_goals}"
        allow_score = ["0-0", "1-0", "0-1", "1-1"]
        if score_str not in allow_score:
            continue

        # 收集命中的场次
        match_info = {
            "league": league_name,
            "home_cn": home_cn,
            "away_cn": away_cn,
            "minute": minute,
            "score": score_str
        }
        match_hit_list.append(match_info)
        print(f"✅命中候选比赛｜{league_name}｜{home_cn} VS {away_cn}｜{minute}分钟｜比分 {score_str}")

        # 找到3-5场就停止遍历，节省API额度
        if len(match_hit_list) >= 4:
            break

    # 组装推送内容
    if len(match_hit_list) > 0:
        bark_body = ""
        for m in match_hit_list:
            bark_body += f"联赛:{m['league']}\n{m['home_cn']} VS {m['away_cn']}\n时间:{m['minute']}分 比分:{m['score']}\n--------\n"
        send_bark_notification("滚球筛选命中场次", bark_body)
    else:
        send_bark_notification("滚球筛选结果", "本轮未找到符合条件比赛")

    print(f"\n📊本轮共筛选出 {len(match_hit_list)} 场候选比赛，程序执行完毕")


if __name__ == "__main__":
    main()
