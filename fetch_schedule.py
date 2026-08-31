#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fetch_schedule.py (中文翻译版)
功能：获取北京时间（UTC+8）今天与明天的白名单联赛赛程，
      过滤掉已完场（FT）的比赛，仅保留未开赛（NS）和正在进行中的比赛，
      并将球队和联赛名强制翻译为中文，最终生成 schedule.html
环境需求：仅使用 Python 标准库
环境变量：API_FOOTBALL_KEY
"""
import argparse
import json
import os
import urllib.request
import urllib.parse
from datetime import datetime, timedelta, timezone

# --------------------------配置区--------------------------
LEAGUE_WHITELIST = [
    "Segunda Division", "Segunda División", "Serie B",
    "Premier League Russia", "Premier League - Russia",
    "K League 1", "Brasileiro Serie B", "Serie B - Brazil"
]
OUTPUT_HTML = "schedule.html"
FINISHED_STATUSES = ["FT", "AET", "PEN", "CANC", "POST", "ABD", "AWD", "WO"]

# 【联赛中文翻译】
LEAGUE_NAME_MAP = {
    "Segunda División": "西乙", "Segunda Division": "西乙", "La Liga 2": "西乙",
    "Serie B": "意乙",
    "K League 1": "韩K1",
    "Premier League - Russia": "俄超", "Premier League Russia": "俄超", "Russian Premier League": "俄超",
    "Serie B - Brazil": "巴乙", "Brasileiro Serie B": "巴乙"
}

# 【球队中文翻译字典（常用必抓球队）】
TEAM_NAME_MAP = {
    "Leganes": "莱加内斯", "Las Palmas": "拉斯帕尔马斯", "Real Zaragoza": "萨拉戈萨",
    "Sporting Gijon": "希洪竞技", "Espanyol": "西班牙人", "Eibar": "埃瓦尔",
    "Valladolid": "巴利亚多利德", "Oviedo": "奥维耶多", "Racing Santander": "桑坦德竞技",
    "Tenerife": "特内里费", "Levante": "莱万特", "Elche": "埃尔切", "Huesca": "韦斯卡",
    "Parma": "帕尔马", "Venezia": "威尼斯", "Cremonese": "克雷莫内塞", "Como": "科莫",
    "Palermo": "巴勒莫", "Catanzaro": "卡坦扎罗", "Brescia": "布雷西亚", "Sampdoria": "桑普多利亚",
    "Zenit Saint Petersburg": "泽尼特", "Krasnodar": "克拉斯诺达尔", "Dynamo Moscow": "莫斯科迪纳摩",
    "Spartak Moscow": "莫斯科斯巴达", "Lokomotiv Moscow": "莫斯科火车头", "CSKA Moscow": "莫斯科中央陆军",
    "Rostov": "罗斯托夫", "Rubin Kazan": "喀山红宝石",
    "Ulsan Hyundai": "蔚山现代", "Ulsan HD": "蔚山HD", "Jeonbuk Hyundai Motors": "全北现代",
    "Pohang Steelers": "浦项制铁", "Gwangju FC": "光州FC", "Incheon United": "仁川联",
    "Daegu FC": "大邱FC", "FC Seoul": "首尔FC", "Daejeon Hana Citizen": "大田韩亚市民",
    "Jeju United": "济州联", "Suwon FC": "水原FC", "Gangwon FC": "江原FC", "Gimcheon Sangmu": "金泉尚武",
    "Santos": "桑托斯", "America Mineiro": "美洲矿工", "Sport Recife": "累西腓体育", "Ceara": "塞阿拉",
    "Goias": "戈亚斯", "Coritiba": "科里蒂巴", "Avai": "阿瓦伊", "CRB": "CRB马塞约",
    "Vila Nova": "维拉诺瓦", "Novorizontino": "诺沃里宗蒂诺", "Ponte Preta": "蓬特普雷塔",
    "Operario-PR": "奥佩拉里奥", "Chapecoense": "沙佩科恩斯", "Guarani": "瓜拉尼"
}

def get_api_key():
    key = os.environ.get("API_FOOTBALL_KEY", "").strip()
    if not key:
        raise SystemExit("ERROR: 环境变量 API_FOOTBALL_KEY 未设置！")
    return key

def get_beijing_now():
    utc_now = datetime.now(timezone.utc)
    beijing_tz = timezone(timedelta(hours=8))
    return utc_now.astimezone(beijing_tz)

def fetch_fixtures_by_date(date_str: str, api_key: str):
    url = f"https://v3.football.api-sports.io/fixtures?date={urllib.parse.quote(date_str)}"
    headers = {"User-Agent": "Mozilla/5.0", "x-apisports-key": api_key}
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            raw = resp.read().decode("utf-8")
            data = json.loads(raw)
        return data.get("response", [])
    except Exception as e:
        print(f"[警告] 获取日期 {date_str} 赛程失败: {e}")
        return []

def utc_to_beijing_str(utc_iso_str: str):
    clean_str = utc_iso_str.replace("Z", "+00:00")
    dt_utc = datetime.fromisoformat(clean_str)
    beijing_tz = timezone(timedelta(hours=8))
    dt_beijing = dt_utc.astimezone(beijing_tz)
    return dt_beijing.strftime("%Y-%m-%d %H:%M")

def generate_html(match_list):
    html_template = """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>白名单联赛赛程 (今明两天)</title>
<style>
*{{box-sizing:border-box;margin:0;padding:0;font-family:system-ui,-apple-system,sans-serif;}}
body{{padding:16px;background:#f5f7fa;}}
h1{{text-align:center;margin-bottom:16px;font-size:20px;color:#222;}}
table{{width:100%;border-collapse:collapse;background:#fff;border-radius:8px;overflow:hidden;box-shadow:0 1px 6px #00000014;}}
th,td{{padding:12px 8px;text-align:left;border-bottom:1px solid #eee;font-size:14px;}}
th{{background:#2c3e50;color:#fff;}}
tr:nth-child(even){{background:#fafbfc;}}
.status-ns{{color:#27ae60;font-weight:bold;}}
.status-live{{color:#e74c3c;font-weight:bold;}}
.tip{{margin-top:12px;text-align:center;color:#666;font-size:13px;}}
</style>
</head>
<body>
    <h1>⚽ 白名单联赛赛程 (北京时间 今明两天)</h1>
    <table>
        <thead>
            <tr>
                <th>开球时间 (北京时间)</th>
                <th>状态</th>
                <th>联赛</th>
                <th>主队</th>
                <th>客队</th>
            </tr>
        </thead>
        <tbody>
{table_rows}
        </tbody>
    </table>
    <div class="tip">仅显示未开赛及进行中比赛 | 包含联赛：西乙 / 意乙 / 俄超 / 韩K1 / 巴乙</div>
</body>
</html>
"""
    row_html = ""
    if not match_list:
        row_html = "<tr><td colspan='5' style='text-align:center;'>今明两天暂无符合条件的白名单比赛</td></tr>\n"
    else:
        for m in match_list:
            status_class = "status-live" if m['status'] != "未开赛" else "status-ns"
            row_html += (
                f"<tr>"
                f"<td>{m['kick_beijing']}</td>"
                f"<td class='{status_class}'>{m['status']}</td>"
                f"<td>{m['league']}</td>"
                f"<td>{m['home']}</td>"
                f"<td>{m['away']}</td>"
                f"</tr>\n"
            )
    return html_template.format(table_rows=row_html)

def main():
    parser = argparse.ArgumentParser(description="fetch_schedule 获取北京时间今明两天白名单未完场赛程并输出 HTML")
    parser.add_argument("--mock", action="store_true", help="模拟模式，不请求真实 API")
    args = parser.parse_args()

    beijing_now = get_beijing_now()
    today_str = beijing_now.strftime("%Y-%m-%d")
    tomorrow_str = (beijing_now + timedelta(days=1)).strftime("%Y-%m-%d")

    if args.mock:
        print("💡 开启 MOCK 模拟模式運行...")
        mock_data = [
            {"kick_utc_raw": "2026-08-31T14:00:00Z", "kick_beijing": f"{today_str} 22:00", "status": "未开赛", "league": "西乙", "home": "萨拉戈萨", "away": "希洪竞技"},
            {"kick_utc_raw": "2026-09-01T15:15:00Z", "kick_beijing": f"{tomorrow_str} 23:15", "status": "未开赛", "league": "意乙", "home": "帕尔马", "away": "巴勒莫"}
        ]
        html_text = generate_html(mock_data)
        with open(OUTPUT_HTML, "w", encoding="utf-8") as f:
            f.write(html_text)
        print(f"✅ 模拟完成，已成功生成 {OUTPUT_HTML}")
        return

    print(f"📅 当前北京时间今天: {today_str} | 明天: {tomorrow_str}")
    api_key = get_api_key()

    raw_matches_today = fetch_fixtures_by_date(today_str, api_key)
    raw_matches_tomorrow = fetch_fixtures_by_date(tomorrow_str, api_key)
    
    combined_matches = {item["fixture"]["id"]: item for item in (raw_matches_today + raw_matches_tomorrow)}.values()

    parsed_list = []
    for item in combined_matches:
        raw_league = item.get("league", {}).get("name", "")
        
        if not any(wl.lower() in raw_league.lower() for wl in LEAGUE_WHITELIST):
            continue

        status_short = item.get("fixture", {}).get("status", {}).get("short", "")
        if status_short in FINISHED_STATUSES:
            continue

        status_text = "未开赛" if status_short == "NS" else f"进行中({status_short})"

        # 强制翻译
        raw_home = item["teams"]["home"]["name"]
        raw_away = item["teams"]["away"]["name"]
        league_cn = LEAGUE_NAME_MAP.get(raw_league, raw_league)
        home_cn = TEAM_NAME_MAP.get(raw_home, raw_home)
        away_cn = TEAM_NAME_MAP.get(raw_away, raw_away)

        kick_utc_str = item["fixture"]["date"]
        kick_beijing_str = utc_to_beijing_str(kick_utc_str)

        parsed_list.append({
            "kick_utc_raw": kick_utc_str,
            "kick_beijing": kick_beijing_str,
            "status": status_text,
            "league": league_cn,
            "home": home_cn,
            "away": away_cn
        })

    parsed_list.sort(key=lambda x: x["kick_utc_raw"])
    html_content = generate_html(parsed_list)
    with open(OUTPUT_HTML, "w", encoding="utf-8") as f:
        f.write(html_content)

    print(f"🎉 处理完成！筛选出今明两天共 {len(parsed_list)} 场未完场白名单比赛，已导出至 {OUTPUT_HTML}")

if __name__ == "__main__":
    main()
