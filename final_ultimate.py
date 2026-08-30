#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
final_ultimate.py 极简滚球筛选器
规则：仅保留白名单联赛 + 50-70分钟，命中直接推送中文队名！
支持 --mock 模拟模式，仅使用 urllib/json 标准库。
"""
import argparse
import json
import os
import urllib.request
import urllib.parse

API_FOOTBALL_KEY = os.environ.get("API_FOOTBALL_KEY", "")
BARK_URL = "https://api.day.app/xZFcs4kMkNaRxVs3aXzzfM/"

# 配置
LEAGUE_WHITELIST = ["Segunda Division", "Serie B", "Premier League Russia", "K League 1", "Brasileiro Serie B"]
LEAGUE_BLACKLIST = ["Eredivisie", "Super Lig", "Saudi Pro League", "A-League"]
MAX_MATCHES = 3

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
    "Dynamo Moscow": "莫斯科迪纳摩",
    "Rostov": "罗斯托夫",
    "Rubin Kazan": "喀山红宝石",
    "Krasnodar": "克拉斯诺达尔",
    "CSKA Moscow": "莫斯科中央陆军",
    "Lokomotiv Moscow": "莫斯科火车头",
    "Ulsan HD": "蔚山HD",
    "Jeonbuk Hyundai Motors": "全北现代",
    "Pohang Steelers": "浦项制铁",
    "FC Seoul": "FC首尔",
    "Gwangju FC": "光州FC",
    "Sangju Sangmu": "尚州尚武",
    "Vasco da Gama": "瓦斯科达伽马",
    "Coritiba": "科里蒂巴",
    "Ceara": "塞阿拉",
    "Sport Recife": "累西腓体育",
    "Brusque": "布鲁斯基",
    "Novorizontino": "诺瓦里松蒂诺",
    "Mirassol": "米拉索尔",
    "Ponte Preta": "庞特普雷塔"
}

def translate_team_name(team_name):
    """英文球队名翻译中文，字典不存在直接返回原文本"""
    if team_name in TEAM_NAME_MAP:
        return TEAM_NAME_MAP[team_name]
    return team_name

def send_bark_push(title: str, body: str):
    """发送Bark消息推送"""
    payload = {"title": title, "body": body}
    params = urllib.parse.urlencode(payload)
    full_url = f"{BARK_URL}?{params}"
    try:
        req = urllib.request.Request(full_url, method="GET")
        with urllib.request.urlopen(req, timeout=10) as resp:
            resp.read()
    except Exception as e:
        print(f"⚠️ Bark推送异常: {e}")

def fetch_live_matches():
    """获取实时live=all比赛"""
    if not API_FOOTBALL_KEY:
        raise SystemExit("ERROR: 环境变量 API_FOOTBALL_KEY 未设置")
    # 使用官方正确域名
    url = "https://v3.football.api-sports.io/fixtures?live=all"
    headers = {"x-apisports-key": API_FOOTBALL_KEY}
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=20) as res:
        # 加上 utf-8 解码，防止中文报错
        data = json.loads(res.read().decode('utf-8'))
    return data.get("response", [])

def parse_minute(minute_str):
    """解析比赛分钟，兼容60+，只取数字部分"""
    if not minute_str:
        return None
    clean = str(minute_str).replace("+", "")
    if clean.isdigit():
        return int(clean)
    return None

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mock", action="store_true", help="模拟测试模式，不请求真实API")
    args = parser.parse_args()

    if args.mock:
        print("✅模拟测试成功")
        return

    matches = fetch_live_matches()
    hit_count = 0

    for item in matches:
        if hit_count >= MAX_MATCHES:
            print(f"已经找到{MAX_MATCHES}场，停止扫描")
            break

        league_name = item["league"]["name"]
        # 获取原始英文名并翻译
        home_raw = item["teams"]["home"]["name"]
        away_raw = item["teams"]["away"]["name"]
        home_team = translate_team_name(home_raw)
        away_team = translate_team_name(away_raw)
        status_minute = item["fixture"]["status"]["elapsed"]

        # 黑名单直接跳过
        if any(b in league_name for b in LEAGUE_BLACKLIST):
            continue
        # 白名单校验
        if league_name not in LEAGUE_WHITELIST:
            continue

        minute = parse_minute(status_minute)
        if minute is None:
            continue
        # 时间条件：50-70分钟，允许带+补时
        if 50 <= minute <= 70:
            hit_count += 1
            msg_title = "⚽滚球命中场次"
            msg_body = f"联赛:{league_name}｜{home_team} VS {away_team}｜时间:{status_minute}分钟"
            print(f"✅命中，已推送｜{msg_body}")
            send_bark_push(msg_title, msg_body)

    print(f"扫描结束，本次命中{hit_count}场")

if __name__ == "__main__":
    main()
