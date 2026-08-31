import os
import sys
import json
import argparse
import urllib.request
import urllib.parse
import urllib.error

# ==========================================
# 0. 推送配置与翻译映射字典
# ==========================================
BARK_BASE_URL = "https://api.day.app/xZFcs4kMkNaRxVs3aXzzfM/"

# 联赛波动等级硬编码字典
VOLATILITY_DICT = {
    # 低波动（白名单）
    "西乙": "LOW",
    "Segunda División": "LOW",
    "意乙": "LOW",
    "Serie B": "LOW",
    "巴乙": "LOW",
    "Serie B - Brazil": "LOW",
    "韩K1": "LOW",
    "K League 1": "LOW",
    "俄超": "LOW",
    "Premier League - Russia": "LOW",
    "解放者杯": "LOW",
    "Copa Libertadores": "LOW",
    # 中波动（直接跳过）
    "中超": "MID",
    "Super League": "MID",
    # 极高波动（黑名单，直接跳过）
    "荷甲": "HIGH",
    "Eredivisie": "HIGH",
    "荷乙": "HIGH",
    "Eerste Divisie": "HIGH",
    "奥甲": "HIGH",
    "Bundesliga - Austria": "HIGH",
    "土超": "HIGH",
    "Süper Lig": "HIGH",
    "沙特联": "HIGH",
    "Pro League": "HIGH",
    "澳超": "HIGH",
    "A-League": "HIGH",
}

# 联赛名称中文翻译字典
LEAGUE_NAME_MAP = {
    "Segunda División": "西乙",
    "La Liga 2": "西乙",
    "Serie B": "意乙",
    "K League 1": "韩K1",
    "Premier League - Russia": "俄超",
    "Russian Premier League": "俄超",
    "Serie B - Brazil": "巴乙",
    "Copa Libertadores": "解放者杯",
}

# 常见球队名称中文翻译字典（涵盖西乙、意乙、俄超、韩K1、巴乙）
TEAM_NAME_MAP = {
    # --- 西乙 ---
    "Leganes": "莱加内斯",
    "Las Palmas": "拉斯帕尔马斯",
    "Real Zaragoza": "萨拉戈萨",
    "Sporting Gijon": "希洪竞技",
    "Espanyol": "西班牙人",
    "Eibar": "埃瓦尔",
    "Valladolid": "巴利亚多利德",
    "Oviedo": "奥维耶多",
    "Racing Santander": "桑坦德竞技",
    "Tenerife": "特内里费",
    "Albacete": "阿尔巴塞特",
    "Burgos": "布尔戈斯",
    "Levante": "莱万特",
    "Elche": "埃尔切",
    "Cartagena": "卡塔赫纳",
    "Huesca": "韦斯卡",
    "Mirandes": "米兰德斯",
    "Amorebieta": "阿莫雷比埃塔",
    "Andorra FC": "安道尔FC",
    "Alcorcon": "阿尔科孔",
    "Villarreal B": "比利亚雷亚尔B队",
    "Ferrol": "费罗尔竞技",

    # --- 意乙 ---
    "Parma": "帕尔马",
    "Venezia": "威尼斯",
    "Cremonese": "克雷莫内塞",
    "Como": "科莫",
    "Palermo": "巴勒莫",
    "Catanzaro": "卡坦扎罗",
    "Brescia": "布雷西亚",
    "Sampdoria": "桑普多利亚",
    "Cosenza": "科森扎",
    "Bari": "巴里",
    "Pisa": "比萨",
    "Reggiana": "雷吉亚纳",
    "Sudtirol": "苏蒂罗尔",
    "Modena": "摩德纳",
    "Spezia": "斯佩齐亚",
    "Ternana": "特尔纳纳",
    "Ascoli": "阿斯科利",
    "Feralpisalo": "费拉尔皮萨洛",
    "Lecco": "莱科",
    "FeralpiSalo": "费拉尔皮萨洛",

    # --- 俄超 ---
    "Zenit Saint Petersburg": "泽尼特",
    "Krasnodar": "克拉斯诺达尔",
    "Dynamo Moscow": "莫斯科 dynamically",
    "Spartak Moscow": "莫斯科斯巴达",
    "Lokomotiv Moscow": "莫斯科火车头",
    "CSKA Moscow": "莫斯科中央陆军",
    "Rostov": "罗斯托夫",
    "Krylya Sovetov": "苏维埃翼",
    "Rubin Kazan": "喀山红宝石",
    "Ural": "乌拉尔",
    "Fakel Voronezh": "沃罗涅日火炬",
    "Orenburg": "奥伦堡",
    "Nizhny Novgorod": "下诺夫哥罗德",
    "Pari NN": "下诺夫哥罗德",
    "Baltika": "波罗的海",
    "Sochi": "索契",
    "Akhmat Grozny": "阿赫马特",

    # --- 韩K1 ---
    "Ulsan Hyundai": "蔚山现代",
    "Ulsan HD": "蔚山HD",
    "Jeonbuk Motors": "全北现代",
    "Pohang Steelers": "浦项制铁",
    "Gwangju FC": "光州FC",
    "Incheon Utd": "仁川联",
    "Daegu FC": "大邱FC",
    "FC Seoul": "首尔FC",
    "Daejeon Citizen": "大田市民",
    "Jeju United": "济州联",
    "Suwon FC": "水原FC",
    "Gangwon FC": "江原FC",
    "Gimcheon Sangmu": "金泉尚武",

    # --- 巴乙 ---
    "Santos": "桑托斯",
    "America Mineiro": "美洲矿工",
    "Sport Recife": "力斯菲体育",
    "Ceara": "塞阿拉",
    "Goias": "戈亚斯",
    "Coritiba": "库里蒂巴",
    "Avaí": "阿瓦伊",
    "Avai": "阿瓦伊",
    "CRB": "CRB马塞约",
    "Vila Nova": "维拉诺瓦",
    "Novorizontino": "诺沃里宗蒂诺",
    "Ponte Preta": "蓬特普雷塔",
    "Operario-PR": "普利登斯",
    "Chapecoense": "沙佩科恩斯",
    "Guarani": "瓜拉尼",
    "Ituano": "伊图阿诺",
    "Botafogo SP": "博塔弗戈SP",
    "Paysandu": "派桑杜",
    "Bragantino": "布拉干蒂诺",
}

# 排除关键字（含杯赛、女足等，解放者杯除外）
EXCLUDE_KEYWORDS = ["女", "Women", "W", "杯", "Cup"]


# ==========================================
# 1. BARK 推送工具函数
# ==========================================
def send_bark_push(title: str, content: str, is_critical: bool = False):
    """
    发送 Bark 推送
    :param is_critical: True 使用持续响铃 30 秒 (level=critical&call=1)
                        False 使用普通响铃 (sound=minuet)
    """
    encoded_title = urllib.parse.quote(title)
    encoded_content = urllib.parse.quote(content)
    
    if is_critical:
        url = f"{BARK_BASE_URL}{encoded_title}/{encoded_content}?level=critical&call=1"
    else:
        url = f"{BARK_BASE_URL}{encoded_title}/{encoded_content}?sound=minuet"

    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as response:
            print(f"[Bark 推送成功] Status: {response.status} | URL: {url}")
    except Exception as e:
        print(f"[Bark 推送失败] Exception: {e}")


# ==========================================
# 2. 模式 1：55分钟低波动比赛自动预警 (带中文翻译)
# ==========================================
def run_mode_55m_auto():
    print("\n=== [模式 1] 运行 55分钟低波动比赛自动扫描 ===")
    
    api_key = os.getenv("API_FOOTBALL_KEY", "").strip()
    if not api_key:
        print("[错误] 未配置环境变量 API_FOOTBALL_KEY，请在 GitHub Secrets 中配置！")
        return

    url = "https://v3.football.api-sports.io/fixtures?live=all"
    headers = {
        "User-Agent": "Mozilla/5.0",
        "x-apisports-key": api_key
    }

    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=15) as response:
            raw_data = response.read().decode("utf-8")
            data = json.loads(raw_data)
    except Exception as e:
        print(f"[API 请求错误] 无法获取比赛数据: {e}")
        return

    matches = data.get("response", [])
    if not isinstance(matches, list):
        print("[数据解析错误] API 返回 response 非预期列表")
        return

    print(f"当前实时抓取到 {len(matches)} 场比赛，正在分析...")

    # 逐场校验与过滤
    for item in matches:
        try:
            raw_league = str(item.get("league", {}).get("name", "")).strip()
            minute = item.get("fixture", {}).get("status", {}).get("elapsed")
            
            if minute is None:
                continue
            minute = int(minute)

            raw_home_team = str(item.get("teams", {}).get("home", {}).get("name", "主队")).strip()
            raw_away_team = str(item.get("teams", {}).get("away", {}).get("name", "客队")).strip()
            
            goals = item.get("goals", {})
            home_score = goals.get("home", 0) if goals.get("home") is not None else 0
            away_score = goals.get("away", 0) if goals.get("away") is not None else 0

            # ----------------------------------------------------
            # ⚠️ 人工避雷注释提醒（代码无法判断的部分）：
            # 1. 避开【莫斯科斯巴达】等攻防剧烈/神经质球队
            # 2. 避开【争升班生死战】（最后几轮淘汰赛/附加赛，抢分期易失控）
            # 3. 避开【主场战意极强/魔鬼主场】的超频压制场次
            # ----------------------------------------------------

            # A. 校验联赛波动级别 (必须属于低波动白名单)
            matched_volatility = None
            for key, vol in VOLATILITY_DICT.items():
                if key.lower() in raw_league.lower():
                    matched_volatility = vol
                    break

            if matched_volatility != "LOW":
                continue  # 非低波动白名单（或属于中/高波动黑名单），跳过

            # B. 过滤杯赛（解放者杯淘汰赛除外）与女足
            is_libertadores = "解放者杯" in raw_league or "Libertadores" in raw_league
            if not is_libertadores and any(ex in raw_league for ex in EXCLUDE_KEYWORDS):
                continue

            # C. 时间必须在 55-58 分钟
            if not (55 <= minute <= 58):
                continue

            # D. 执行中文名称转换 (未查到映射则使用原始英文)
            league_cn = LEAGUE_NAME_MAP.get(raw_league, raw_league)
            home_team_cn = TEAM_NAME_MAP.get(raw_home_team, raw_home_team)
            away_team_cn = TEAM_NAME_MAP.get(raw_away_team, raw_away_team)
            match_name_cn = f"{home_team_cn} vs {away_team_cn}"

            # E. 触发普通响铃提醒
            title = "⏰ 55分钟低波动比赛提醒"
            content = (
                f"🏆 联赛: {league_cn}\n"
                f"⚽ 比赛: {match_name_cn}\n"
                f"⏱ 当前时间: {minute}分 | 比分: {home_score}-{away_score}\n"
                f"💡 请去雷速查看赛况，若符合重注口诀可手动输入推演！"
            )
            print(f"[触发预警] {league_cn} ({raw_league}) - {match_name_cn} ({minute}分)")
            send_bark_push(title, content, is_critical=False)

        except Exception as e:
            print(f"[数据处理异常] 忽略异常单场比赛: {e}")
            continue


# ==========================================
# 3. 模式 2：重注信号（支持终端交互或 Actions 环境变量传参）
# ==========================================
def run_mode_heavy_manual():
    print("\n=== [模式 2] 运行 重注信号数据校验 ===")

    # 优先检测环境变量
    def get_val(env_key, prompt_text, default_val=None):
        val = os.getenv(env_key)
        if val is not None and val.strip() != "":
            print(f"读取到环境变量 [{env_key}]: {val}")
            return val.strip()
        
        if not sys.stdin.isatty():
            if default_val is not None:
                print(f"非交互模式下使用默认值 [{env_key}]: {default_val}")
                return str(default_val)
            else:
                print(f"❌ [错误] CI/Actions 环境下缺少必填环境变量: {env_key}")
                sys.exit(1)
        
        return input(prompt_text).strip()

    try:
        league = get_val("PARAM_LEAGUE", "1. 联赛名称 (如 西乙/俄超): ")
        minute = int(get_val("PARAM_MINUTE", "2. 比赛分钟 (50-75): "))
        score_str = get_val("PARAM_SCORE", "3. 当前比分 (如 0-0, 1-0, 0-1, 1-1): ")
        reds = int(get_val("PARAM_REDS", "4. 全场红牌总数: "))
        yellows = int(get_val("PARAM_YELLOWS", "5. 全场黄牌总数: "))
        total_shots_on_target = int(get_val("PARAM_SHOTS", "6. 全场总射正数: "))
        total_corners = int(get_val("PARAM_CORNERS", "7. 全场总角球数: "))
        leading_shots = int(get_val("PARAM_LEADING_SHOTS", "8. 领先方射正数 (若平局请输入较多一方射正): "))
        trailing_shots = int(get_val("PARAM_TRAILING_SHOTS", "9. 落后方射正数 (若平局请输入较少一方射正): "))
        odds = float(get_val("PARAM_ODDS", "10. 实时拟投盘口赔率 (1.30-1.65): "))
    except ValueError as e:
        print(f"\n❌ [输入错误] 数据格式不合法: {e}")
        return

    # 拆分比分
    try:
        home_s, away_s = map(int, score_str.split("-"))
    except Exception:
        print("\n❌ [拒绝重注] 比分格式输入错误！")
        return

    print("\n正在根据【重注口诀风控模型】执行严密推演...")

    # ================= 口诀与条件硬性拦截 =================

    # 条件 1：时间 50-75 分钟
    if not (50 <= minute <= 75):
        print(f"❌ [拒绝重注] 时间不在 50-75 分钟窗口 (当前: {minute}分)")
        return

    # 条件 2：比分严格限制为 0-0, 1-0, 0-1, 1-1
    if (home_s, away_s) not in [(0, 0), (1, 0), (0, 1), (1, 1)]:
        print(f"❌ [拒绝重注] 比分不符合规范 (当前: {score_str}，只允许 0-0, 1-0, 0-1, 1-1)")
        return

    # 条件 3：红牌必须为 0，黄牌 ≤ 2
    if reds > 0:
        print(f"❌ [拒绝重注] 存在红牌隐患 (红牌: {reds}张)")
        return
    if yellows > 2:
        print(f"❌ [拒绝重注] 黄牌过多，容易破牌出红 (黄牌: {yellows}张)")
        return

    # 条件 4：口诀硬性要求
    # 4a. 总射正 ≤ 5
    if total_shots_on_target > 5:
        print(f"❌ [拒绝重注] 射正狂狂！总射正过高 (当前: {total_shots_on_target} > 5)")
        return

    # 4b. 总角球 ≤ 6
    if total_corners > 6:
        print(f"❌ [拒绝重注] 角球堆积！两队进攻节奏过快 (当前: {total_corners} > 6)")
        return

    # 4c. 禁止落后方玩命冲 (落后方射正必须 ≤ 2)
    if trailing_shots > 2:
        print(f"❌ [拒绝重注] 拒绝落后全队往前冲！落后方射正过多 (当前: {trailing_shots} > 2)")
        return

    # 4d. 领先后敢缩守 (若非平局，领先方射正必须大于落后方)
    if home_s != away_s:
        if leading_shots <= trailing_shots:
            print(f"❌ [拒绝重注] 领先方未能掌控局势或被死死压制！(领先射正:{leading_shots} <= 落后射正:{trailing_shots})")
            return

    # 条件 5：赔率必须在 1.30 - 1.65 之间
    if not (1.30 <= odds <= 1.65):
        print(f"❌ [拒绝重注] 赔率不在 1.30-1.65 容错低赔区间 (当前赔率: {odds})")
        return

    # 条件 6：默认最大下注金额为 30元 (占 300元本金的 10%)
    max_stake = 30.0

    # ================= 全部通过，触发 30秒持续响铃重注信号 =================
    title = "🚨🚨 绝佳重注信号"
    content = (
        f"🏆 联赛: {league}\n"
        f"⏱ 时间: {minute}分 | 比分: {score_str}\n"
        f"🎯 选定赔率: {odds}\n"
        f"💰 建议投注金额: {max_stake:.1f}元 (严格风控上限)\n"
        f"📊 口诀风控完全通过: 射正{total_shots_on_target}次|角球{total_corners}个|落后方射正{trailing_shots}次|黄牌{yellows}张\n"
        f"⚡ 请即刻复核盘口下注！"
    )
    
    print("\n✅ [校验全部通过] 符合重注标准！正在发送 30秒持续响铃推送...")
    send_bark_push(title, content, is_critical=True)


# ==========================================
# 4. MOCK 测试模式
# ==========================================
def run_mock_test():
    print("\n=== [MOCK 测试模式] ===")
    mock_data = {
        "response": [
            {
                "league": {"name": "Segunda División"},
                "fixture": {"status": {"elapsed": 56}},
                "teams": {"home": {"name": "Real Zaragoza"}, "away": {"name": "Sporting Gijon"}},
                "goals": {"home": 1, "away": 0}
            },
            {
                "league": {"name": "Eerste Divisie"},
                "fixture": {"status": {"elapsed": 56}},
                "teams": {"home": {"name": "Jong Ajax"}, "away": {"name": "FC Eindhoven"}},
                "goals": {"home": 2, "away": 1}
            }
        ]
    }
    
    print("1. 测试中文翻译及 55分钟观察预警推送...")
    for item in mock_data["response"]:
        raw_league = item["league"]["name"]
        minute = item["fixture"]["status"]["elapsed"]
        if "Segunda" in raw_league and 55 <= minute <= 58:
            raw_home = item["teams"]["home"]["name"]
            raw_away = item["teams"]["away"]["name"]
            
            league_cn = LEAGUE_NAME_MAP.get(raw_league, raw_league)
            home_cn = TEAM_NAME_MAP.get(raw_home, raw_home)
            away_cn = TEAM_NAME_MAP.get(raw_away, raw_away)
            
            title = "⏰ 55分钟低波动比赛提醒"
            content = f"🏆 {league_cn}\n⚽ {home_cn} vs {away_cn}\n⏱ {minute}分"
            send_bark_push(title, content, is_critical=False)

    print("\n2. 测试 绝佳重注信号持续响铃推送...")
    title = "🚨🚨 绝佳重注信号"
    content = "🏆 西乙\n⏱ 62分 | 比分: 1-0\n🎯 赔率: 1.45\n💰 建议金额: 30元\n⚡ 模拟测试持续响铃"
    send_bark_push(title, content, is_critical=True)


# ==========================================
# 5. 主程序入口
# ==========================================
def main():
    parser = argparse.ArgumentParser(description="足球滚球 55分钟预警与重注信号系统")
    parser.add_argument("--manual", action="store_true", help="开启模式2：重注信号数据校验")
    parser.add_argument("--mock", action="store_true", help="运行 Mock 测试代码")
    args = parser.parse_args()

    if args.mock:
        run_mock_test()
        return

    if args.manual:
        run_mode_heavy_manual()
    else:
        # 默认模式 1：Actions / 自动轮询 55分钟预警
        run_mode_55m_auto()


if __name__ == "__main__":
    main()
