import sys
import json
import argparse
import urllib.request
import urllib.parse
import urllib.error

# ==========================================
# 0. 推送配置与常量定义
# ==========================================
BARK_BASE_URL = "https://api.day.app/xZFcs4kMkNaRxVs3aXzzfM/"

# 【联赛波动等级硬编码字典】
VOLATILITY_DICT = {
    # 低波动（白名单）
    "西乙": "LOW",
    "意乙": "LOW",
    "巴乙": "LOW",
    "韩K1": "LOW",
    "俄超": "LOW",
    "解放者杯": "LOW",  # 配合过滤逻辑，淘汰赛需人工校验
    # 中波动（直接跳过）
    "中超": "MID",
    # 极高波动（黑名单，直接跳过）
    "荷甲": "HIGH",
    "荷乙": "HIGH",
    "奥甲": "HIGH",
    "土超": "HIGH",
    "沙特联": "HIGH",
    "澳超": "HIGH",
}

# 排除关键字（含杯赛、女足等，解放者杯除外）
EXCLUDE_KEYWORDS = ["女", "Women", "W", "杯", "Cup"]


# ==========================================
# 1. BARK 推送工具函数 (匹配指定 URL 格式)
# ==========================================
def send_bark_push(title: str, content: str, is_critical: bool = False):
    """
    发送 Bark 推送
    :param title: 消息标题（拼接到 URL 路径第一层）
    :param content: 消息内容（拼接到 URL 路径第二层）
    :param is_critical: True - 使用格式: https://api.day.app/xZFcs4kMkNaRxVs3aXzzfM/标题/内容?level=critical&call=1
                        False - 使用格式: https://api.day.app/xZFcs4kMkNaRxVs3aXzzfM/标题/内容?sound=minuet
    """
    encoded_title = urllib.parse.quote(title)
    encoded_content = urllib.parse.quote(content)
    
    if is_critical:
        # 模式 2：重注信号，30 秒持续响铃模式
        url = f"{BARK_BASE_URL}{encoded_title}/{encoded_content}?level=critical&call=1"
    else:
        # 模式 1：55分钟观察，普通响铃模式
        url = f"{BARK_BASE_URL}{encoded_title}/{encoded_content}?sound=minuet"

    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as response:
            print(f"[Bark 推送成功] Status: {response.status} | URL: {url}")
    except Exception as e:
        print(f"[Bark 推送失败] Exception: {e}")


# ==========================================
# 2. 模式 1：55分钟低波动比赛自动预警
# ==========================================
def run_mode_55m_auto(api_url: str):
    print("\n=== [模式 1] 运行 55分钟低波动比赛自动扫描 ===")
    
    # 1. 拉取 API 数据
    try:
        req = urllib.request.Request(api_url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=15) as response:
            raw_data = response.read().decode("utf-8")
            data = json.loads(raw_data)
    except Exception as e:
        print(f"[API 请求错误] 无法获取比赛数据: {e}")
        return

    matches = data.get("data", []) if isinstance(data, dict) else data
    if not isinstance(matches, list):
        print("[数据解析错误] 返回数据非预期列表")
        return

    # 2. 逐场校验与过滤
    for match in matches:
        league = str(match.get("league_name", "")).strip()
        minute = int(match.get("minute", 0))
        home_team = match.get("home_team", "主队")
        away_team = match.get("away_team", "客队")
        home_score = match.get("home_score", 0)
        away_score = match.get("away_score", 0)

        match_name = f"{home_team} vs {away_team}"

        # ----------------------------------------------------
        # ⚠️ 人工避雷注释提醒（代码无法判断的部分）：
        # 1. 避开【莫斯科斯巴达】等攻防剧烈/神经质球队
        # 2. 避开【争升班生死战】（最后几轮淘汰赛/附加赛，抢分期易失控）
        # 3. 避开【主场战意极强/魔鬼主场】的超频压制场次
        # ----------------------------------------------------

        # A. 校验联赛波动级别 (必须属于低波动白名单)
        matched_volatility = None
        for key, vol in VOLATILITY_DICT.items():
            if key in league:
                matched_volatility = vol
                break

        if matched_volatility != "LOW":
            continue  # 非低波动白名单（或属于中/高波动黑名单），跳过

        # B. 过滤杯赛（解放者杯淘汰赛除外）与女足
        is_libertadores = "解放者杯" in league
        if not is_libertadores and any(ex in league for ex in EXCLUDE_KEYWORDS):
            continue

        # C. 时间必须在 55-58 分钟
        if not (55 <= minute <= 58):
            continue

        # D. 触发普通响铃提醒
        title = "⏰ 55分钟低波动比赛提醒"
        content = (
            f"🏆 联赛: {league}\n"
            f"⚽ 比赛: {match_name}\n"
            f"⏱ 当前时间: {minute}分 | 比分: {home_score}-{away_score}\n"
            f"💡 请去雷速查看赛况，若符合重注口诀可手动输入推演！"
        )
        print(f"[触发预警] {league} - {match_name} ({minute}分)")
        send_bark_push(title, content, is_critical=False)


# ==========================================
# 3. 模式 2：重注信号（手动输入，严格口诀风控）
# ==========================================
def run_mode_heavy_manual():
    print("\n=== [模式 2] 运行 重注信号手动输入校验 ===")
    print("请依次输入比赛实时数据（严格按照雷速数据填写）：\n")

    try:
        league = input("1. 联赛名称 (如 西乙/俄超): ").strip()
        minute = int(input("2. 比赛分钟 (50-75): "))
        score_str = input("3. 当前比分 (如 0-0, 1-0, 0-1, 1-1): ").strip()
        reds = int(input("4. 全场红牌总数: "))
        yellows = int(input("5. 全场黄牌总数: "))
        total_shots_on_target = int(input("6. 全场总射正数: "))
        total_corners = int(input("7. 全场总角球数: "))
        leading_shots = int(input("8. 领先方射正数 (若平局请输入较多一方射正): "))
        trailing_shots = int(input("9. 落后方射正数 (若平局请输入较少一方射正): "))
        odds = float(input("10. 实时拟投盘口赔率 (1.30-1.65): "))
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
        "data": [
            {
                "league_name": "西班牙乙级联赛",
                "minute": 56,
                "home_team": "萨拉戈萨",
                "away_team": "希洪竞技",
                "home_score": 1,
                "away_score": 0
            },
            {
                "league_name": "荷兰乙级联赛",  # 极高波动，将被自动过滤
                "minute": 56,
                "home_team": "阿贾克斯青年队",
                "away_team": "埃因霍温FC",
                "home_score": 2,
                "away_score": 1
            }
        ]
    }
    
    print("1. 测试 55分钟观察预警推送 URL 格式...")
    for match in mock_data["data"]:
        league = match["league_name"]
        minute = match["minute"]
        if any(k in league for k in ["西乙", "西班牙乙级联赛"]) and 55 <= minute <= 58:
            title = "⏰ 55分钟低波动比赛提醒"
            content = f"🏆 {league}\n⚽ {match['home_team']} vs {match['away_team']}\n⏱ {minute}分"
            send_bark_push(title, content, is_critical=False)

    print("\n2. 测试 绝佳重注信号持续响铃推送 URL 格式...")
    title = "🚨🚨 绝佳重注信号"
    content = "🏆 西乙\n⏱ 62分 | 比分: 1-0\n🎯 赔率: 1.45\n💰 建议金额: 30元\n⚡ 模拟测试持续响铃"
    send_bark_push(title, content, is_critical=True)


# ==========================================
# 5. 主程序入口
# ==========================================
def main():
    parser = argparse.ArgumentParser(description="足球滚球 55分钟预警与重注信号系统")
    parser.add_argument("--manual", action="store_true", help="开启模式2：手动输入重注信号数据")
    parser.add_argument("--mock", action="store_true", help="运行 Mock 测试代码")
    args = parser.parse_args()

    if args.mock:
        run_mock_test()
        return

    if args.manual:
        run_mode_heavy_manual()
    else:
        # 默认模式 1：Actions / 自动轮询 55分钟预警
        api_url = "https://api.example.com/live_matches"  # 替换为你的实际 API 接口
        run_mode_55m_auto(api_url)


if __name__ == "__main__":
    main()
