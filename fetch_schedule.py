#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fetch_schedule.py
功能：获取北京时间（UTC+8）今天与明天的白名单联赛赛程，
      过滤掉已完场（FT）的比赛，仅保留未开赛（NS）和正在进行中的比赛，
      最终生成 schedule.html
环境需求：仅使用 Python 标准库 urllib / json / argparse / datetime
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
    "Segunda Division",
    "Segunda División",
    "Serie B",
    "Premier League Russia",
    "Premier League - Russia",
    "K League 1",
    "Brasileiro Serie B",
    "Serie B - Brazil"
]
OUTPUT_HTML = "schedule.html"

# 已完场/终结状态黑名单（过滤掉这些状态）
FINISHED_STATUSES = ["FT", "AET", "PEN", "CANC", "POST", "ABD", "AWD", "WO"]
# -----------------------------------------------------------

def get_api_key():
    key = os.environ.get("API_FOOTBALL_KEY", "").strip()
    if not key:
        raise SystemExit("ERROR: 环境变量 API_FOOTBALL_KEY 未设置！")
    return key

def get_beijing_now():
    """获取当前北京时间（UTC+8）"""
    utc_now = datetime.now(timezone.utc)
    beijing_tz = timezone(timedelta(hours=8))
    return utc_now.astimezone(beijing_tz)

def fetch_fixtures_by_date(date_str: str, api_key: str):
    """调用 api-sports fixtures?date=xxx 获取指定日期赛程"""
    url = f"https://v3.football.api-sports.io/fixtures?date={urllib.parse.quote(date_str)}"
    headers = {
        "User-Agent": "Mozilla/5.0",
        "x-apisports-key": api_key
    }
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
    """
    API 返回 UTC ISO 时间（如 "2026-08-30T16:00:00+00:00" 或 "2026-08-30T16:00:00Z"），
    转为北京时间格式化字符串 "YYYY-MM-DD HH:MM"
    """
    clean_str = utc_iso_str.replace("Z", "+00:00")
    dt_utc = datetime.fromisoformat(clean_str)
    beijing_tz = timezone(timedelta(hours=8))
    dt_beijing = dt_utc.astimezone(beijing_tz)
    return dt_beijing.strftime("%Y-%m-%d %H:%M")

def generate_html(match_list):
    """生成包含今明两天未完场赛程的 HTML"""
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
            {
                "kick_utc_raw": "2026-08-31T14:00:00Z",
                "kick_beijing": f"{today_str} 22:00",
                "status": "未开赛",
                "league": "Segunda Division",
                "home": "萨拉戈萨",
                "away": "希洪竞技"
            },
            {
                "kick_utc_raw": "2026-09-01T15:15:00Z",
                "kick_beijing": f"{tomorrow_str} 23:15",
                "status": "未开赛",
                "league": "Serie B",
                "home": "帕尔马",
                "away": "巴勒莫"
            }
        ]
        html_text = generate_html(mock_data)
        with open(OUTPUT_HTML, "w", encoding="utf-8") as f:
            f.write(html_text)
        print(f"✅ 模拟完成，已成功生成 {OUTPUT_HTML}")
        return

    print(f"📅 当前北京时间今天: {today_str} | 明天: {tomorrow_str}")
    api_key = get_api_key()

    # 分别获取今天与明天的赛程
    raw_matches_today = fetch_fixtures_by_date(today_str, api_key)
    raw_matches_tomorrow = fetch_fixtures_by_date(tomorrow_str, api_key)
    
    # 合并去重（根据 fixture id 避免跨天重复）
    combined_matches = {item["fixture"]["id"]: item for item in (raw_matches_today + raw_matches_tomorrow)}.values()

    parsed_list = []
    for item in combined_matches:
        league_name = item.get("league", {}).get("name", "")
        
        # 1. 校验联赛白名单
        if not any(wl.lower() in league_name.lower() for wl in LEAGUE_WHITELIST):
            continue

        # 2. 校验比赛状态（排除已完场 FT 等状态）
        status_short = item.get("fixture", {}).get("status", {}).get("short", "")
        if status_short in FINISHED_STATUSES:
            continue

        status_text = "未开赛" if status_short == "NS" else f"进行中({status_short})"

        kick_utc_str = item["fixture"]["date"]
        home_name = item["teams"]["home"]["name"]
        away_name = item["teams"]["away"]["name"]
        kick_beijing_str = utc_to_beijing_str(kick_utc_str)

        parsed_list.append({
            "kick_utc_raw": kick_utc_str,
            "kick_beijing": kick_beijing_str,
            "status": status_text,
            "league": league_name,
            "home": home_name,
            "away": away_name
        })

    # 按照开球时间升序排列
    parsed_list.sort(key=lambda x: x["kick_utc_raw"])

    html_content = generate_html(parsed_list)
    with open(OUTPUT_HTML, "w", encoding="utf-8") as f:
        f.write(html_content)

    print(f"🎉 处理完成！筛选出今明两天共 {len(parsed_list)} 场未完场白名单比赛，已导出至 {OUTPUT_HTML}")

if __name__ == "__main__":
    main()
