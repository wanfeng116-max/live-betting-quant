#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
滚球量化模拟交易系统 v3.0 — 两阶段流程
  阶段一(bet):   拉取实时比赛 → 规则过滤 → 模拟下注 → 保存 pending_bets.json
  阶段二(settle): 读取 pending_bets.json → 查询终场 → 结算盈亏 → 更新 balance.json

用法:
  python simulate_trading.py --phase bet       # 一阶段：下注
  python simulate_trading.py --phase settle    # 二阶段：结算
  python simulate_trading.py --phase bet --mock  # 用模拟数据测试
"""

import argparse
import json
import os
from datetime import datetime, timezone, timedelta
from typing import Optional

# ============================================================
# 配置区
# ============================================================
CONFIG = {
    "init_balance": 1000,
    "stake_per_bet": 100,
    "max_concurrent_bets": 10,
    "min_odds_under25": 1.60,
    "bet_window_min": 45,
    "bet_window_max": 75,
    "max_total_sot": 6,
    "max_total_corners": 6,
    "max_total_yellow": 6,
    "trailing_max_sot": 3,
    "trailing_max_corners": 4,
    "trailing_max_shots": 9,
}

HIGH_RISK_LEAGUES = {
    "荷甲", "荷乙", "Eredivisie", "Eerste Divisie",
    "奥甲", "Austrian Bundesliga",
    "土超", "Süper Lig", "Turkish Super Lig", "Turkish Super League",
    "沙特联", "Saudi Pro League", "SPL", "Saudi League",
    "澳超", "A-League", "A League", "Australian A-League",
}

LOW_RISK_LEAGUES = {
    "西乙", "意乙", "巴乙", "韩K超", "俄超", "中超", "解放者杯淘汰赛",
    "La Liga 2", "LaLiga 2", "Segunda División", "Segunda Division",
    "Serie B",
    "Brasileiro Série B", "Brasileiro Serie B",
    "K League 1", "K League",
    "Russian Premier League", "Premier League (Russia)",
    "Chinese Super League", "CSL",
    "Copa Libertadores",
}

# ============================================================
# 路径 & API 配置（API Key 通过 GitHub Secrets 注入）
# ============================================================
OUTPUT_DIR = "output"
PENDING_FILE = os.path.join(OUTPUT_DIR, "pending_bets.json")
BALANCE_FILE = os.path.join(OUTPUT_DIR, "balance.json")
HISTORY_FILE = os.path.join(OUTPUT_DIR, "bet_history.json")

API_BASE = os.environ.get("FOOTBALL_API_BASE", "https://v3.football.api-sports.io")
API_KEY = os.environ.get("FOOTBALL_API_KEY", "")
API_HOST = os.environ.get("FOOTBALL_API_HOST", "v3.football.api-sports.io")

BJ_TZ = timezone(timedelta(hours=8))

# ============================================================
# 工具函数
# ============================================================
def now_bj() -> str:
    return datetime.now(BJ_TZ).strftime("%Y-%m-%d %H:%M:%S")

def load_json(path, default):
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default

def save_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def print_line(char="=", length=78):
    print(char * length)

def normalize_league(name: str) -> str:
    name_lower = name.strip().lower()
    all_leagues = LOW_RISK_LEAGUES | HIGH_RISK_LEAGUES
    for std in all_leagues:
        if std.lower() == name_lower:
            return std
    for std in all_leagues:
        if std.lower() in name_lower or name_lower in std.lower():
            return std
    return name

def is_high_risk(league: str) -> bool:
    return normalize_league(league) in HIGH_RISK_LEAGUES

def is_low_risk(league: str) -> bool:
    return normalize_league(league) in LOW_RISK_LEAGUES

# ============================================================
# 数据提供者（封装 API 调用；无 API 时自动 mock）
# ============================================================
class DataProvider:
    def __init__(self, mock=False):
        self.mock = mock or (not API_KEY)
        if self.mock and not mock:
            print("  ⚠️ 未检测到 FOOTBALL_API_KEY，自动切换到模拟数据模式")

    def _request(self, endpoint: str, params: dict = None) -> dict:
        if self.mock:
            return {}
        import urllib.request, urllib.parse
        url = f"{API_BASE}/{endpoint}"
        if params:
            url += "?" + urllib.parse.urlencode(params)
        req = urllib.request.Request(url)
        req.add_header("x-apisports-key", API_KEY)
        req.add_header("x-rapidapi-host", API_HOST)
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            print(f"  ⚠️ API请求失败 {endpoint}: {e}")
            return {}

    def get_live_fixtures(self) -> list:
        if self.mock:
            return self._mock_live()
        data = self._request("fixtures", {"live": "all"})
        results = []
        for item in data.get("response", []):
            fix = item.get("fixture", {})
            league = item.get("league", {})
            teams = item.get("teams", {})
            goals = item.get("goals", {})
            results.append({
                "fixture_id": fix.get("id"),
                "league": league.get("name", ""),
                "home_team": teams.get("home", {}).get("name", ""),
                "away_team": teams.get("away", {}).get("name", ""),
                "home_score": goals.get("home") or 0,
                "away_score": goals.get("away") or 0,
                "minute": fix.get("status", {}).get("elapsed") or 0,
                "status": fix.get("status", {}).get("short", ""),
            })
        return results

    def get_statistics(self, fixture_id: int) -> dict:
        if self.mock:
            return self._mock_stats(fixture_id)
        data = self._request("fixtures/statistics", {"fixture": fixture_id})
        resp = data.get("response", [])
        if not resp or len(resp) < 2:
            return {}
        home_stats = {s["type"]: s["value"] for s in resp[0].get("statistics", [])}
        away_stats = {s["type"]: s["value"] for s in resp[1].get("statistics", [])}
        def _i(v):
            if v is None: return 0
            if isinstance(v, int): return v
            s = str(v).replace("%", "").split("-")[0].strip()
            return int(s) if s else 0
        return {
            "shots_on_target_h": _i(home_stats.get("Shots on Goal", 0)),
            "shots_on_target_a": _i(away_stats.get("Shots on Goal", 0)),
            "total_shots_h": _i(home_stats.get("Total Shots", 0)),
            "total_shots_a": _i(away_stats.get("Total Shots", 0)),
            "corners_h": _i(home_stats.get("Corner Kicks", 0)),
            "corners_a": _i(away_stats.get("Corner Kicks", 0)),
            "yellow_h": _i(home_stats.get("Yellow Cards", 0)),
            "yellow_a": _i(away_stats.get("Yellow Cards", 0)),
            "red_h": _i(home_stats.get("Red Cards", 0)),
            "red_a": _i(away_stats.get("Red Cards", 0)),
        }

    def get_odds_under25(self, fixture_id: int) -> Optional[float]:
        if self.mock:
            return 1.75
        data = self._request("odds", {"fixture": fixture_id})
        resp = data.get("response", [])
        if not resp:
            return None
        for bookmaker in resp[0].get("bookmakers", []):
            for bet in bookmaker.get("bets", []):
                if "over/under" in bet.get("name", "").lower():
                    for val in bet.get("values", []):
                        v = val.get("value", "")
                        if "under" in v.lower() and "2.5" in v:
                            try:
                                return float(val.get("odd", 0))
                            except (ValueError, TypeError):
                                pass
        return None

    def get_fixture_result(self, fixture_id: int) -> dict:
        """调用 fixtures?id= 查询终场比分"""
        if self.mock:
            return self._mock_result(fixture_id)
        data = self._request("fixtures", {"id": fixture_id})
        resp = data.get("response", [])
        if not resp:
            return {"finished": False}
        item = resp[0]
        fix = item.get("fixture", {})
        goals = item.get("goals", {})
        status = fix.get("status", {}).get("short", "")
        return {
            "finished": status in {"FT", "AET", "PEN", "FT_PEN"},
            "status": status,
            "home_score": goals.get("home") or 0,
            "away_score": goals.get("away") or 0,
            "home_team": item.get("teams", {}).get("home", {}).get("name", ""),
            "away_team": item.get("teams", {}).get("away", {}).get("name", ""),
        }

    # ---------- Mock 数据（无 API 时测试流程用） ----------
    def _mock_live(self):
        return [
            {"fixture_id": 1001, "league": "西乙", "home_team": "莱加内斯", "away_team": "安道尔CF",
             "home_score": 1, "away_score": 0, "minute": 58, "status": "LIVE"},
            {"fixture_id": 1002, "league": "意乙", "home_team": "帕尔马", "away_team": "威尼斯",
             "home_score": 0, "away_score": 0, "minute": 52, "status": "LIVE"},
            {"fixture_id": 1003, "league": "荷甲", "home_team": "阿贾克斯", "away_team": "埃因霍温",
             "home_score": 2, "away_score": 1, "minute": 60, "status": "LIVE"},
            {"fixture_id": 1004, "league": "韩K超", "home_team": "全北现代", "away_team": "蔚山现代",
             "home_score": 0, "away_score": 1, "minute": 65, "status": "LIVE"},
        ]

    def _mock_stats(self, fid):
        return {
            1001: {"shots_on_target_h":2,"shots_on_target_a":1,"total_shots_h":6,"total_shots_a":3,
                    "corners_h":3,"corners_a":1,"yellow_h":1,"yellow_a":2,"red_h":0,"red_a":0},
            1002: {"shots_on_target_h":1,"shots_on_target_a":1,"total_shots_h":4,"total_shots_a":3,
                    "corners_h":2,"corners_a":2,"yellow_h":0,"yellow_a":1,"red_h":0,"red_a":0},
            1003: {"shots_on_target_h":5,"shots_on_target_a":4,"total_shots_h":15,"total_shots_a":12,
                    "corners_h":6,"corners_a":5,"yellow_h":3,"yellow_a":2,"red_h":0,"red_a":0},
            1004: {"shots_on_target_h":3,"shots_on_target_a":2,"total_shots_h":8,"total_shots_a":5,
                    "corners_h":4,"corners_a":3,"yellow_h":2,"yellow_a":1,"red_h":0,"red_a":0},
        }.get(fid, {})

    def _mock_result(self, fid):
        return {
            1001: {"finished":True,"status":"FT","home_score":1,"away_score":0,
                    "home_team":"莱加内斯","away_team":"安道尔CF"},
            1002: {"finished":True,"status":"FT","home_score":0,"away_score":0,
                    "home_team":"帕尔马","away_team":"威尼斯"},
            1004: {"finished":True,"status":"FT","home_score":1,"away_score":1,
                    "home_team":"全北现代","away_team":"蔚山现代"},
        }.get(fid, {"finished": False})

# ============================================================
# 规则引擎（终极标准：低波动 + 小比分 + 落后队不拼命）
# ============================================================
class RuleEngine:
    def __init__(self):
        self.c = CONFIG

    def check(self, fixture, stats, odds):
        reasons = []
        passed = True
        confidence = 5
        league = fixture["league"]
        minute = fixture["minute"]
        h, a = fixture["home_score"], fixture["away_score"]
        diff = h - a

        # 1. 联赛过滤
        if is_high_risk(league):
            return {"passed":False,"confidence":0,"reasons":[f"❌ 高危联赛[{league}]，直接跳过"],
                    "score_at_bet":f"{h}-{a}","odds":odds or 1.70}
        if is_low_risk(league):
            confidence += 2; reasons.append(f"✅ 低波动联赛[{league}]")
        else:
            reasons.append(f"⚠️ 中性联赛[{league}]")

        # 2. 时间窗口 45-75
        if minute < self.c["bet_window_min"]:
            passed=False; reasons.append(f"❌ 时间过早({minute}分钟)")
        elif minute > self.c["bet_window_max"]:
            passed=False; reasons.append(f"❌ 时间过晚({minute}分钟)")
        else:
            confidence += 1; reasons.append(f"✅ 时间窗口({minute}分钟)")

        # 3. 比分只允许 0-0 / 1-0 / 0-1
        if (h, a) not in {(0,0),(1,0),(0,1)}:
            passed=False; reasons.append(f"❌ 比分{h}-{a}不在允许范围")
        else:
            confidence += 1; reasons.append(f"✅ 比分{h}-{a}符合小比分")

        # 4. 赛况过滤
        tot_sot = stats.get("shots_on_target_h",0)+stats.get("shots_on_target_a",0)
        tot_cor = stats.get("corners_h",0)+stats.get("corners_a",0)
        tot_yel = stats.get("yellow_h",0)+stats.get("yellow_a",0)
        tot_red = stats.get("red_h",0)+stats.get("red_a",0)

        if tot_red >= 1:
            passed=False; reasons.append(f"❌ 出现红牌({tot_red}张)")
        if tot_sot > self.c["max_total_sot"]:
            passed=False; reasons.append(f"❌ 总射正{tot_sot}次超阈值")
        else:
            if tot_sot <= 4: confidence += 1
            reasons.append(f"✅ 总射正{tot_sot}次")
        if tot_cor > self.c["max_total_corners"]:
            passed=False; reasons.append(f"❌ 总角球{tot_cor}个超阈值")
        else:
            if tot_cor <= 4: confidence += 1
            reasons.append(f"✅ 总角球{tot_cor}个")
        if tot_yel > self.c["max_total_yellow"]:
            reasons.append(f"⚠️ 黄牌{tot_yel}张偏激烈")
        else:
            reasons.append(f"✅ 黄牌{tot_yel}张平稳")

        # 5. 落后方行为判断
        if diff != 0:
            if diff > 0:
                t_sot=stats.get("shots_on_target_a",0); t_cor=stats.get("corners_a",0)
                t_shots=stats.get("total_shots_a",0); t_side="客队"
            else:
                t_sot=stats.get("shots_on_target_h",0); t_cor=stats.get("corners_h",0)
                t_shots=stats.get("total_shots_h",0); t_side="主队"
            if t_sot >= self.c["trailing_max_sot"]:
                passed=False; reasons.append(f"❌ {t_side}(落后)射正{t_sot}次玩命冲")
            if t_cor >= self.c["trailing_max_corners"]:
                passed=False; reasons.append(f"❌ {t_side}(落后)角球{t_cor}个持续压")
            if t_shots >= self.c["trailing_max_shots"]:
                passed=False; reasons.append(f"❌ {t_side}(落后)射门{t_shots}次全队前压")
            if passed:
                if t_sot <= 2 and t_cor <= 2:
                    confidence += 2; reasons.append(f"✅ {t_side}(落后)躺平不拼命")
                else:
                    confidence += 1; reasons.append(f"✅ {t_side}(落后)攻势可控")
        else:
            reasons.append("✅ 平局无落后方反扑")

        # 6. 赔率检查
        if odds is None:
            reasons.append("⚠️ 未获取赔率，默认1.70"); odds = 1.70
        elif odds < self.c["min_odds_under25"]:
            passed=False; reasons.append(f"❌ 赔率{odds:.2f}低于阈值{self.c['min_odds_under25']}")
        else:
            reasons.append(f"✅ 赔率{odds:.2f}达标")

        # 7. 信心门槛
        confidence = max(0, min(confidence, 10))
        if confidence < 7:
            passed=False; reasons.append(f"❌ 信心{confidence}<7不达标")

        return {"passed":passed,"confidence":confidence,"reasons":reasons,
                "score_at_bet":f"{h}-{a}","odds":odds}

# ============================================================
# 交易管理器（互斥 + 仓位 + 结算 + 全仓打印）
# ============================================================
class BetManager:
    def __init__(self):
        self.c = CONFIG
        self.pending = load_json(PENDING_FILE, [])
        self.balance_data = load_json(BALANCE_FILE, {
            "balance": self.c["init_balance"], "initial_balance": self.c["init_balance"],
            "total_pnl": 0.0, "total_bets": 0, "win_count": 0, "lose_count": 0,
            "last_update": now_bj(),
        })
        self.history = load_json(HISTORY_FILE, [])

    def save_all(self):
        save_json(PENDING_FILE, self.pending)
        save_json(BALANCE_FILE, self.balance_data)
        save_json(HISTORY_FILE, self.history)

    def _pending_ids(self):
        return {b["fixture_id"] for b in self.pending if b["status"] == "pending"}

    def available_slots(self):
        active = len([b for b in self.pending if b["status"] == "pending"])
        return max(0, self.c["max_concurrent_bets"] - active)

    def place_bet(self, fixture, result):
        if fixture["fixture_id"] in self._pending_ids():
            return None
        if self.available_slots() <= 0:
            return None
        stake = self.c["stake_per_bet"]
        if self.balance_data["balance"] < stake:
            return None
        bet = {
            "bet_id": f"bet_{datetime.now(BJ_TZ).strftime('%Y%m%d%H%M%S')}_{fixture['fixture_id']}",
            "fixture_id": fixture["fixture_id"], "league": fixture["league"],
            "home_team": fixture["home_team"], "away_team": fixture["away_team"],
            "bet_type": "under_2_5", "direction": "小2.5球",
            "stake": stake, "odds": result["odds"], "confidence": result["confidence"],
            "bet_time": now_bj(), "bet_minute": fixture["minute"],
            "score_at_bet": result["score_at_bet"], "status": "pending",
            "reasons": result["reasons"],
        }
        self.pending.append(bet)
        self.balance_data["balance"] -= stake
        self.balance_data["last_update"] = now_bj()
        return bet

    def settle_bet(self, bet, result):
        total = result["home_score"] + result["away_score"]
        stake, odds = bet["stake"], bet["odds"]
        if total <= 2:
            profit = round(stake * (odds - 1), 2)
            self.balance_data["balance"] += round(stake * odds, 2)
            self.balance_data["total_pnl"] += profit
            self.balance_data["win_count"] += 1
            tag = "WIN"
        else:
            profit = -stake
            self.balance_data["total_pnl"] += profit
            self.balance_data["lose_count"] += 1
            tag = "LOSE"
        self.balance_data["total_bets"] += 1
        self.balance_data["last_update"] = now_bj()
        settled = dict(bet)
        settled.update({
            "status": tag, "final_score": f"{result['home_score']}-{result['away_score']}",
            "total_goals": total, "profit": profit, "settle_time": now_bj(),
        })
        self.history.append(settled)
        return settled

    def settle_all(self, provider):
        settled, remaining = [], []
        for bet in self.pending:
            if bet["status"] != "pending":
                remaining.append(bet); continue
            result = provider.get_fixture_result(bet["fixture_id"])
            if not result.get("finished"):
                remaining.append(bet); continue
            settled.append(self.settle_bet(bet, result))
        self.pending = remaining
        return {"settled": settled, "remaining": len(remaining)}

    def print_portfolio(self):
        print_line()
        print("  💰 全仓账户总览")
        print_line()
        b = self.balance_data
        pnl = b["total_pnl"]
        wr = f"{(b['win_count']/b['total_bets']*100):.1f}%" if b["total_bets"] > 0 else "N/A"
        rows = [
            ("初始资金", f"{b['initial_balance']:.2f}"),
            ("当前余额", f"{b['balance']:.2f}"),
            ("累计盈亏", f"{'✅' if pnl>=0 else '❌'} {pnl:+.2f}"),
            ("总下注笔数", b["total_bets"]),
            ("赢 / 输", f"{b['win_count']} / {b['lose_count']}"),
            ("胜率", wr),
            ("待结算挂单", len([x for x in self.pending if x["status"]=="pending"])),
            ("最后更新", b["last_update"]),
        ]
        for k, v in rows:
            print(f"  {k:<10} : {v}")

        active = [b for b in self.pending if b["status"] == "pending"]
        if active:
            print_line("-"); print("  📋 待结算挂单"); print_line("-")
            for i, bet in enumerate(active, 1):
                print(f"  #{i} [{bet['league']}] {bet['home_team']} vs {bet['away_team']}")
                print(f"      下注时 {bet['bet_time']}  分钟{bet['bet_minute']}  比分{bet['score_at_bet']}")
                print(f"      方向 {bet['direction']}  赔率 {bet['odds']}  金额 {bet['stake']}  信心 {bet['confidence']}")

        if self.history:
            print_line("-"); print("  📜 结算历史（最近10条）"); print_line("-")
            for i, bet in enumerate(reversed(self.history[-10:]), 1):
                tag = "✅赢" if bet["status"] == "WIN" else "❌输"
                print(f"  {tag} [{bet['league']}] {bet['home_team']} vs {bet['away_team']}  "
                      f"终场{bet['final_score']}(总{bet['total_goals']}球)  盈亏{bet['profit']:+.2f}")
        print_line()

# ============================================================
# 两阶段主流程
# ============================================================
def phase_bet(provider):
    print_line()
    print(f"  🎯 阶段一：模拟下注  [{now_bj()}]")
    print_line()
    manager = BetManager()
    engine = RuleEngine()

    print("\n  📡 正在获取实时比赛...")
    fixtures = provider.get_live_fixtures()
    print(f"  获取到 {len(fixtures)} 场正在进行的比赛")
    if not fixtures:
        print("  ⚠️ 当前没有正在进行的比赛"); manager.save_all(); manager.print_portfolio(); return

    avail = manager.available_slots()
    print(f"  可用仓位: {avail}/{CONFIG['max_concurrent_bets']}  余额: {manager.balance_data['balance']:.2f}\n")

    new_bets = []
    for fx in fixtures:
        if avail <= 0:
            print("  ⚠️ 仓位已满，停止扫描"); break
        fid, league, minute = fx["fixture_id"], fx["league"], fx["minute"]
        score = f"{fx['home_score']}-{fx['away_score']}"
        print(f"  ── [{league}] {fx['home_team']} vs {fx['away_team']}  分钟{minute}  比分{score}")
        if is_high_risk(league):
            print("     ❌ 高危联赛，跳过\n"); continue
        stats = provider.get_statistics(fid)
        if not stats:
            print("     ⚠️ 无统计数据，跳过\n"); continue
        odds = provider.get_odds_under25(fid)
        result = engine.check(fx, stats, odds)
        for r in result["reasons"]:
            print(f"     {r}")
        if result["passed"]:
            bet = manager.place_bet(fx, result)
            if bet:
                new_bets.append(bet); avail -= 1
                print(f"     ✅✅✅ 下注成功! 信心{result['confidence']} 赔率{result['odds']} 金额{CONFIG['stake_per_bet']}")
            else:
                print("     ⚠️ 下注失败(仓位/余额/重复)")
        else:
            print(f"     ❌ 未通过(信心{result['confidence']})")
        print()

    manager.save_all()
    print_line(); print("  📊 本次下注汇总"); print_line()
    if new_bets:
        for i, bet in enumerate(new_bets, 1):
            print(f"  #{i} [{bet['league']}] {bet['home_team']} vs {bet['away_team']}")
            print(f"      方向{bet['direction']} 赔率{bet['odds']} 金额{bet['stake']} 信心{bet['confidence']} 下注时比分{bet['score_at_bet']}")
    else:
        print("  本次无新增下注")
    manager.print_portfolio()

def phase_settle(provider):
    print_line()
    print(f"  🏁 阶段二：结算盈亏  [{now_bj()}]")
    print_line()
    manager = BetManager()
    pending = len([b for b in manager.pending if b["status"] == "pending"])
    print(f"\n  待结算挂单: {pending} 笔")
    if pending == 0:
        print("  ⚠️ 没有待结算挂单"); manager.print_portfolio(); return

    result = manager.settle_all(provider)
    manager.save_all()

    print_line(); print("  📋 本次结算明细"); print_line()
    if result["settled"]:
        for i, bet in enumerate(result["settled"], 1):
            tag = "✅ 赢" if bet["status"] == "WIN" else "❌ 输"
            print(f"  #{i} {tag} [{bet['league']}] {bet['home_team']} vs {bet['away_team']}")
            print(f"      下注时 {bet['score_at_bet']}({bet['bet_minute']}分钟)  终场 {bet['final_score']}(总{bet['total_goals']}球)")
            print(f"      方向 {bet['direction']} 赔率 {bet['odds']} 金额 {bet['stake']}  盈亏 {bet['profit']:+.2f}")
    else:
        print("  本次无已结束比赛（仍在进行，保留到下次结算）")
    print(f"\n  剩余待结算: {result['remaining']} 笔")
    manager.print_portfolio()

def main():
    parser = argparse.ArgumentParser(description="滚球量化模拟交易系统")
    parser.add_argument("--phase", choices=["bet", "settle"], required=True)
    parser.add_argument("--mock", action="store_true", help="模拟数据测试")
    args = parser.parse_args()
    provider = DataProvider(mock=args.mock)
    if args.phase == "bet":
        phase_bet(provider)
    else:
        phase_settle(provider)

if __name__ == "__main__":
    main()
