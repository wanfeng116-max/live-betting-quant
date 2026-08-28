import os
import requests
import time
# 从环境变量读取 API Key（这是绝对安全的做法，不会泄露密钥）
api_key = os.environ.get('API_FOOTBALL_KEY')

if not api_key:
    print("错误：未找到 API_FOOTBALL_KEY 环境变量")
    exit()

# 请求当前正在进行的比赛
url = "https://v3.football.api-sports.io/fixtures?live=all"
headers = {
    'x-apisports-key': api_key
}

# 发送请求
response = requests.get(url, headers=headers)

# 检查是否请求成功
if response.status_code == 200:
    data = response.json()
    if data['response']:
        print("找到以下正在进行的比赛：")
        for match in data['response']:
            # 提取关键信息：比赛ID、主队名、客队名、当前比分
            match_id = match['fixture']['id']
            home_team = match['teams']['home']['name']
            away_team = match['teams']['away']['name']
            home_goals = match['goals']['home']
            away_goals = match['goals']['away']
            
            # 打印结果
            print(f"比赛ID: {match_id} | {home_team} {home_goals} - {away_goals} {away_team}")
    else:
        print("当前没有正在进行的比赛。")
else:
    print(f"API请求失败，状态码: {response.status_code}")
