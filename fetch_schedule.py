#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fetch_schedule.py
功能：拉取指定日期赛程，仅白名单联赛，UTC转北京时间，输出schedule.html
仅使用标准库 urllib / json / argparse / datetime
支持 --mock 模拟模式，不调用真实API
环境变量：API_FOOTBALL_KEY
"""
import argparse
import json
import os
import urllib.request
import urllib.parse
from datetime import datetime, timedelta

# --------------------------配置区--------------------------
LEAGUE_WHITELIST = [
    "Segunda Division",
    "Serie B",
    "Premier League Russia",
    "K League 1",
    "Brasileiro Serie B"
]
OUTPUT_HTML = "schedule.html"
# -----------------------------------------------------------

def get_api_key():
    key = os.environ.get("API_FOOTBALL_KEY", "")
    if not key:
        raise SystemExit("ERROR: 环境变量 API_FOOTBALL_KEY 未设置！")
    return key

def fetch_fixtures(date_str: str, api_key: str):
    """调用api‑sports fixtures?date=xxx 获取当日赛程"""
    url = f"https://v3.football.api-sports.io/fixtures?date={urllib.parse.quote(date_str)}"
    headers = {
        "x-apisports-key": api_key
    }
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=20) as resp:
        raw = resp.read().decode("utf-8")
        data = json.loads(raw)
    return data.get("response", [])

def utc_to_beijing(utc_iso_str: str):
    """
    api返回utc iso时间，转北京时间 UTC+8
    输入示例："2026-08-30T16:00:00Z"
    返回格式化字符串 "2026‑08‑30 24:00"
    """
    # 去掉末尾Z，解析UTC时间
    dt_utc = datetime.fromisoformat(utc_iso_str.replace("Z", ""))
    dt_beijing = dt_utc + timedelta(hours=8)
    return dt_beijing.strftime("%Y‑%m‑%d %H:%M")

def generate_html(match_list):
    """
    传入已经排序好的比赛列表，生成html字符串
    match_list: [{"kick_beijing":"xxx","league":"xxx","home":"xxx","away":"xxx"}, ...]
    """
    html_template = """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>白名单联赛赛程</title>
<style>
*{box-sizing:border-box;margin:0;padding:0;font-family:system-ui,sans-serif;}
body{{padding:16px;background:#f5f7fa;}}
h1{{text-align:center;margin-bottom:16px;font-size:20px;color:#222;}}
table{{width:100%;border-collapse:collapse;background:#fff;border-radius:8px;overflow:hidden;box-shadow:0 1px 6px #00000014;}}
th,td{{padding:12px 8px;text-align:left;border-bottom:1px solid #eee;font-size:14px;}}
th{{background:#2c3e50;color:#fff;}}
tr:nth-child(even){{background:#fafbfc;}}
.tip{{margin-top:12px;text-align:center;color:#666;font-size:13px;}}
</style>
</head>
<body>
    <h1>⚽ 白名单联赛赛程</h1>
    <table>
        <thead>
            <tr>
                <th>开球时间(北京时间)</th>
                <th>联赛</th>
                <th>主队</th>
                <th>客队</th>
            </tr>
        </thead>
        <tbody>
{table_rows}
        </tbody>
    </table>
    <div class="tip">仅包含西乙/意乙/俄超/韩K1/巴乙</div>
</body>
</html>
"""
    row_html = ""
    for m in match_list:
        row_html += (
            f"<tr>"
            f"<td>{m['kick_beijing']}</td>"
            f"<td>{m['league']}</td>"
            f"<td>{m['home']}</td>"
            f"<td>{m['away']}</td>"
            f"</tr>\n"
        )
    return html_template.format(table_rows=row_html)

def main():
    parser = argparse.ArgumentParser(description="fetch_schedule 获取指定日期白名单赛程并输出html")
    parser.add_argument("--date", type=str, help="查询日期，格式 YYYY‑MM‑DD，默认今天")
    parser.add_argument("--mock", action="store_true", help="模拟模式，不请求真实API，输出模拟schedule.html")
    args = parser.parse_args()

    # mock模式
    if args.mock:
        print("🔹 --mock 模拟模式运行，不调用API")
        mock_data = [
            {
                "kick_beijing":"2026‑08‑30 22:00",
                "league":"Segunda Division",
                "home":"主队A",
                "away":"客队B"
            },
            {
                "kick_beijing":"2026‑08‑30 23:15",
                "league":"Serie B",
                "home":"主队C",
                "away":"客队D"
            }
        ]
        html_text = generate_html(mock_data)
        with open(OUTPUT_HTML,"w",encoding="utf‑8") as f:
            f.write(html_text)
        print(f"✅模拟完成，已生成 {OUTPUT_HTML}")
        return

    # 获取查询日期，不传则取本地日期
    if args.date:
        query_date = args.date
    else:
        query_date = datetime.now().strftime("%Y‑%m‑%d")
    print(f"🔹正在查询日期: {query_date}")

    api_key = get_api_key()
    raw_matches = fetch_fixtures(query_date, api_key)

    parsed_list = []
    for item in raw_matches:
        league_name = item["league"]["name"]
        # 过滤白名单联赛
        if league_name not in LEAGUE_WHITELIST:
            continue
        kick_utc_str = item["fixture"]["date"]
        home_name = item["teams"]["home"]["name"]
        away_name = item["teams"]["away"]["name"]
        kick_beijing_str = utc_to_beijing(kick_utc_str)

        parsed_list.append({
            "kick_utc_raw": kick_utc_str,
            "kick_beijing": kick_beijing_str,
            "league": league_name,
            "home": home_name,
            "away": away_name
        })

    # 按照开球北京时间排序（底层用utc原始字符串排序即可）
    parsed_list.sort(key=lambda x:x["kick_utc_raw"])

    html_content = generate_html(parsed_list)
    with open(OUTPUT_HTML, "w", encoding="utf‑8") as f:
        f.write(html_content)

    print(f"✅处理完成，共筛选 {len(parsed_list)} 场白名单比赛，输出到 {OUTPUT_HTML}")

if __name__ == "__main__":
    main()
