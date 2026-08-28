#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
滚球量化模拟交易系统 v4.0 — 三盘口版
支持盘口：胜平负(1X2) / 大小球(OverUnder) / 让球(Handicap)

阶段一(bet):   拉取实时比赛 → 三盘口规则过滤 → 模拟下注 → 保存 pending_bets.json
阶段二(settle): 读取 pending_bets.json → 查询终场 → 按盘口结算盈亏 → 更新 balance.json

用法:
  python simulate_trading.py --phase bet
  python simulate_trading.py --phase settle
  python simulate_trading.py --phase bet --mock
"""

import argparse
import json
import os
import time
import urllib.request
import urllib.parse
import urllib.error
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any

# ============================================================
# 配置区
# ============================================================
CONFIG = {
    "init_balance": 1000,
    "stake_per_bet": 100,
    "max_concurrent_bets": 10,
    "min_odds": 1.50,           # 所有盘口最低赔率门槛
    "max_odds": 3.50,           # 赔率上限，太高说明不稳
    "bet_window_min": 45,
    "bet_window_max": 75,
    "max_total_sot": 8,
    "max_total_corners": 10,
    "max_total_yellow": 8,
    "trailing_max_sot": 4,
    "trailing_max_corners": 5,
    "trailing_max_shots": 12,
    # 开启哪些盘口（true=扫描，false=跳过）
    "enable_1x2": True,
    "enable_overunder": True,
    "enable_handicap": True,
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

# 联赛别名映射（精确匹配，杜绝子串误命中）
LEAGUE_ALIAS_MAP = {
    "la liga 2": "西乙", "laliga 2": "西乙", "segunda división": "西乙",
    "serie b": "意乙",
    "brasileiro série b": "巴乙", "brasileiro serie b": "巴乙",
    "k league 1": "韩K超", "k league": "韩K超",
    "copa libertadores": "解放者杯淘汰赛",
    "chinese super league": "中超", "csl": "中超",
}

# ============================================================
# 路径 & API 配置
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
    """精确匹配 + 别名映射，删除危险的双向子串in匹配"""
    if not name:
        return ""
    raw = name.strip()
    name_lower = raw.lower()
    if name_lower in LEAGUE_ALIAS_MAP:
        return LEAGUE_ALIAS_MAP[name_lower]
    all_std = HIGH_RISK_LEAGUES.union(LOW_RISK_LEAGUES)
    std_lower_map = {s.lower(): s for s in all_std}
    if name_lower in std_lower_map:
        return std_lower_map[name_lower]
    return raw

def is_high_risk(league: str) -> bool:
    return normalize_league(league) in HIGH_RISK_LEAGUES

def is_low_risk(league: str) -> bool:
    return normalize_league(league) in LOW_RISK_LEAGUES

def _safe_int(v):
    """安全转int，处理 None / N/A / 空字符串 / 百分比"""
    if v is None or v == "N/A" or v == "":
        return 0
    if isinstance(v, (int, float)):
        return int(v)
    s = str(v).replace("%", "").split("-")[0].strip()
    try:
        return int(float(s))
    except (ValueError, TypeError):
        return 0

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
        url = f"{API_BASE}/{endpoint}"
        if params:
            url += "?" + urllib.parse.urlencode(params)
        req = urllib.request.Request(url)
        req.add_header("x-apisports-key", API_KEY)
        req.add_header("x-rapidapi-host", API_HOST)
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                if resp.status != 200:
                    print(f"  ⚠️ API HTTP异常 status={resp.status} {endpoint}")
                    return {}
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as he:
            print(f"  ⚠️ API HTTP错误 {endpoint} code:{he.code}")
            return {}
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
                "status": fix.get("status", {}).get("short", "UNKNOWN"),
            })
        return results

    def get_statistics(self, fixture_id: int) -> dict:
        if self.mock:
            return self._mock_stats(fixture_id)
        data = self._request("fixtures/statistics", {"fixture": fixture_id})
        time.sleep(1.2)
        resp = data.get("response", [])
        if not resp or len(resp) < 2:
            return {}
        home_stats = {s["type"]: s["value"] for s in resp[0].get("statistics", [])}
        away_stats = {s["type"]: s["value"] for s in resp[1].get("statistics", [])}
        return {
            "shots_on_target_h": _safe_int(home_stats.get("Shots on Goal", 0)),
            "shots_on_target_a": _safe_int(away_stats.get("Shots on Goal", 0)),
            "total_shots_h": _safe_int(home_stats.get("Total Shots", 0)),
            "total_shots_a": _safe_int(away_stats.get("Total Shots", 0)),
            "corners_h": _safe_int(home_stats.get("Corner Kicks", 0)),
            "corners_a": _safe_int(away_stats.get("Corner Kicks", 0)),
            "yellow_h": _safe_int(home_stats.get("Yellow Cards", 0)),
            "yellow_a": _safe_int(away_stats.get("Yellow Cards", 0)),
            "red_h": _safe_int(home_stats.get("Red Cards", 0)),
            "red_a": _safe_int(away_stats.get("Red Cards", 0)),
        }

    def get_odds_all(self, fixture_id: int) -> Dict[str, Any]:
        """
        一次性拉取三个盘口赔率：胜平负 / 大小球 / 让球
        返回结构:
        {
          "1x2": {"home": 1.85, "draw": 3.40, "away": 4.20},
          "overunder": {"line": 2.5, "over": 1.90, "under": 1.90},
          "handicap": {"line": -0.5, "home": 1.95, "away": 1.85}
        }
        """
        if self.mock:
            return self._mock_odds(fixture_id)
        data = self._request("odds", {"fixture": fixture_id})
        time.sleep(1.2)
        resp = data.get("response", [])
        if not resp:
            return {}
        odds_out = {"1x2": {}, "overunder": {}, "handicap": {}}
        for bookmaker in resp[0].get("bookmakers", []):
            for bet in bookmaker.get("bets", []):
                bname = bet.get("name", "").lower()
                # 胜平负 Match Winner
                if "match winner" in bname or bname == "1x2":
                    for val in bet.get("values", []):
                        v = val.get("value", "").lower()
                        odd = float(val.get("odd", 0) or 0)
                        if v in ("home", "1"): odds_out["1x2"]["home"] = odd
                        elif v in ("draw", "x"): odds_out["1x2"]["draw"] = odd
                        elif v in ("away", "2"): odds_out["1x2"]["away"] = odd
                # 大小球 Over/Under
                elif "over/under" in bname:
                    for val in bet.get("values", []):
                        v = val.get("value", "")
                        odd = float(val.get("odd", 0) or 0)
                        vl = v.lower()
                        if "2.5" in v:
                            if "over" in vl: odds_out["overunder"]["over"] = odd
                            elif "under" in vl: odds_out["overunder"]["under"] = odd
                            odds_out["overunder"]["line"] = 2.5
                # 让球 Asian Handicap
                elif "asian handicap" in bname or "handicap" in bname:
                    for val in bet.get("values", []):
                        v = val.get("value", "")
                        odd = float(val.get("odd", 0) or 0)
                        # 取 -0.5 / 0.5 附近的让球盘
                        try:
                            line = float(v)
                        except (ValueError, TypeError):
                            continue
                        if abs(line) == 0.5:
                            if line < 0:
                                odds_out["handicap"]["home"] = odd
                                odds_out["handicap"]["line"] = line
                            else:
                                odds_out["handicap"]["away"] = odd
                                odds_out["handicap"]["line"] = line
        return odds_out

    def get_fixture_result(self, fixture_id: int) -> dict:
        if self.mock:
            return self._mock_result(fixture_id)
        data = self._request("fixtures", {"id": fixture_id})
        time.sleep(1.2)
        resp = data.get("response", [])
        if not resp:
            return {"finished": False, "cancelled": False}
        item = resp[0]
        fix = item.get("fixture", {})
        goals = item.get("goals", {})
        status = fix.get("status", {}).get("short", "")
        return {
            "finished": status in {"FT", "AET", "PEN", "FT_PEN"},
            "cancelled": status in {"Abandoned", "Postponed", "Cancelled", "CANC", "POST"},
            "status": status,
            "home_score": goals.get("home") or 0,
            "away_score": goals.get("away") or 0,
            "home_team": item.get("teams", {}).get("home", {}).get("name", ""),
            "away_team": item.get("teams", {}).get("away", {}).get("name", ""),
        }

    # ---------- Mock 数据 ----------
    def _mock_live(self):
        return [
            {"fixture_id": 1001, "league": "西乙", "home_team": "莱加内斯", "away_team": "安道尔CF",
             "home_score": 1, "away_score": 0, "minute": 58, "status": "2H"},
            {"fixture_id": 1002, "league": "意乙", "home_team": "帕尔马", "away_team": "威尼斯",
             "home_score": 0, "away_score": 0, "minute": 52, "status": "2H"},
            {"fixture_id": 1003, "league": "荷甲", "home_team": "阿贾克斯", "away_team": "埃因霍温",
             "home_score": 2, "away_score": 1, "minute": 60, "status": "2H"},
            {"fixture_id": 1004, "league": "韩K超", "home_team": "全北现代", "away_team": "蔚山现代",
             "home_score": 0, "away_score": 1, "minute": 65, "status": "2H"},
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

    def _mock_odds(self, fid):
        return {
            1001: {"1x2":{"home":1.85,"draw":3.40,"away":4.20},
                   "overunder":{"line":2.5,"over":2.10,"under":1.70},
                   "handicap":{"line":-0.5,"home":1.95,"away":1.85}},
            1002: {"1x2":{"home":2.30,"draw":2.90,"away":3.10},
                   "overunder":{"line":2.5,"over":2.30,"under":1.55},
                   "handicap":{"line":0.0,"home":1.90,"away":1.90}},
            1004: {"1x2":{"home":2.80,"draw":3.10,"away":2.50},
                   "overunder":{"line":2.5,"over":1.95,"under":1.85},
                   "handicap":{"line":0.5,"home":1.80,"away":2.00}},
        }.get(fid, {})

    def _mock_result(self, fid):
        return {
            1001: {"finished":True,"cancelled":False,"status":"FT","home_score":1,"away_score":0,
                    "home_team":"莱加内斯","away_team":"安道尔CF"},
            1002: {"finished":True,"cancelled":False,"status":"FT","home_score":0,"away_score":0,
                    "home_team":"帕尔马","away_team":"威尼斯"},
            1004: {"finished":True,"cancelled":False,"status":"FT","home_score":1,"away_score":1,
                    "home_team":"全北现代","away_team":"蔚山现代"},
        }.get(fid, {"finished": False, "cancelled": False})

# ============================================================
# 规则引擎（三盘口：胜平负 / 大小球 / 让球）
# ============================================================
class RuleEngine:
    def __init__(self):
        self.c = CONFIG

    def _base_filter(self, fixture, stats) -> Dict[str, Any]:
        """公共过滤：联赛、时间、比分、场上数据，返回 passed/confidence/reasons"""
        reasons = []
        passed = True
        confidence = 5
        league = fixture["league"]
        minute = fixture["minute"]
        fixture_status = fixture.get("status", "")
        h, a = fixture["home_score"], fixture["away_score"]
        diff = h - a

        # 1. 联赛过滤
        if is_high_risk(league):
            return {"passed":False,"confidence":0,"reasons":[f"❌ 高危联赛[{league}]，直接跳过"]}
        if is_low_risk(league):
            confidence += 2; reasons.append(f"✅ 低波动联赛[{league}]")
        else:
            reasons.append(f"⚠️ 中性联赛[{league}]")

        # 2. 时间窗口 45-75，必须下半场
        if fixture_status == "1H":
            passed=False; reasons.append(f"❌ 仍在上半场({minute}分钟)")
        elif minute < self.c["bet_window_min"]:
            passed=False; reasons.append(f"❌ 时间过早({minute}分钟)")
        elif minute > self.c["bet_window_max"]:
            passed=False; reasons.append(f"❌ 时间过晚({minute}分钟)")
        else:
            confidence += 1; reasons.append(f"✅ 时间窗口({minute}分钟)")

        # 3. 比分范围（允许0-0/1-0/0-1/1-1，三盘口比纯小球放宽）
        if (h, a) not in {(0,0),(1,0),(0,1),(1,1)}:
            passed=False; reasons.append(f"❌ 比分{h}-{a}波动过大")
        else:
            confidence += 1; reasons.append(f"✅ 比分{h}-{a}平稳")

        # 4. 赛况过滤
        tot_sot = stats.get("shots_on_target_h",0)+stats.get("shots_on_target_a",0)
        tot_cor = stats.get("corners_h",0)+stats.get("corners_a",0)
        tot_yel = stats.get("yellow_h",0)+stats.get("yellow_a",0)
        tot_red = stats.get("red_h",0)+stats.get("red_a",0)

        if tot_red >= 1:
            passed=False; reasons.append(f"❌ 出现红牌({tot_red}张)")
        if tot_sot > self.c["max_total_sot"]:
            passed=False; reasons.append(f"❌ 总射正{tot_sot}超阈值")
        else:
            if tot_sot <= 5: confidence += 1
            reasons.append(f"✅ 总射正{tot_sot}")
        if tot_cor > self.c["max_total_corners"]:
            passed=False; reasons.append(f"❌ 总角球{tot_cor}超阈值")
        else:
            if tot_cor <= 6: confidence += 1
            reasons.append(f"✅ 总角球{tot_cor}")
        if tot_yel > self.c["max_total_yellow"]:
            reasons.append(f"⚠️ 黄牌{tot_yel}偏激烈")
        else:
            reasons.append(f"✅ 黄牌{tot_yel}平稳")

        # 5. 落后方行为
        if diff != 0:
            if diff > 0:
                t_sot=stats.get("shots_on_target_a",0); t_cor=stats.get("corners_a",0)
                t_shots=stats.get("total_shots_a",0); t_side="客队"
            else:
                t_sot=stats.get("shots_on_target_h",0); t_cor=stats.get("corners_h",0)
                t_shots=stats.get("total_shots_h",0); t_side="主队"
            if t_sot >= self.c["trailing_max_sot"]:
                passed=False; reasons.append(f"❌ {t_side}(落后)射正{t_sot}玩命冲")
            if t_cor >= self.c["trailing_max_corners"]:
                passed=False; reasons.append(f"❌ {t_side}(落后)角球{t_cor}持续压")
            if t_shots >= self.c["trailing_max_shots"]:
                passed=False; reasons.append(f"❌ {t_side}(落后)射门{t_shots}全队前压")
            if passed:
                if t_sot <= 2 and t_cor <= 2:
                    confidence += 2; reasons.append(f"✅ {t_side}(落后)躺平不拼命")
                else:
                    confidence += 1; reasons.append(f"✅ {t_side}(落后)攻势可控")
        else:
            reasons.append("✅ 平局无落后方反扑")

        confidence = max(0, min(confidence, 10))
        return {"passed":passed,"confidence":confidence,"reasons":reasons}

    def _check_odds_range(self, odds: float) -> bool:
        return self.c["min_odds"] <= odds <= self.c["max_odds"]

    def evaluate_1x2(self, fixture, stats, odds_all) -> Optional[Dict[str, Any]]:
        """胜平负盘口：选当前领先方或平局方，赔率在合理区间"""
        if not self.c["enable_1x2"]:
            return None
        odds_1x2 = odds_all.get("1x2", {})
        if not odds_1x2:
            return None
        base = self._base_filter(fixture, stats)
        if not base["passed"]:
            return None
        h, a = fixture["home_score"], fixture["away_score"]
        # 选方向：主队领先→主胜；客队领先→客胜；平局→平局
        if h > a:
            direction = "home"; odd = odds_1x2.get("home", 0); label = "主胜"
        elif a > h:
            direction = "away"; odd = odds_1x2.get("away", 0); label = "客胜"
        else:
            direction = "draw"; odd = odds_1x2.get("draw", 0); label = "平局"
        if not odd or not self._check_odds_range(odd):
            return None
        confidence = base["confidence"]
        if confidence < 7:
            return None
        reasons = base["reasons"] + [f"✅ 胜平负方向:{label} 赔率{odd:.2f}"]
        return {"bet_type":"1x2","direction":direction,"direction_label":label,
                "odds":odd,"confidence":confidence,"reasons":reasons,
                "score_at_bet":f"{h}-{a}","handicap_line":None}

    def evaluate_overunder(self, fixture, stats, odds_all) -> Optional[Dict[str, Any]]:
        """大小球盘口：低射正低角球→小2.5；高射正高角球→大2.5"""
        if not self.c["enable_overunder"]:
            return None
        ou = odds_all.get("overunder", {})
        if not ou or ou.get("line") != 2.5:
            return None
        base = self._base_filter(fixture, stats)
        if not base["passed"]:
            return None
        tot_sot = stats.get("shots_on_target_h",0)+stats.get("shots_on_target_a",0)
        tot_cor = stats.get("corners_h",0)+stats.get("corners_a",0)
        h, a = fixture["home_score"], fixture["away_score"]
        current_goals = h + a
        # 决策：当前进球<=1 且 射正<=5 且 角球<=6 → 小2.5
        # 当前进球>=2 且 射正>=6 → 大2.5
        if current_goals <= 1 and tot_sot <= 5 and tot_cor <= 6:
            direction = "under"; odd = ou.get("under", 0); label = "小2.5"
        elif current_goals >= 2 and tot_sot >= 6:
            direction = "over"; odd = ou.get("over", 0); label = "大2.5"
        else:
            return None
        if not odd or not self._check_odds_range(odd):
            return None
        confidence = base["confidence"]
        if confidence < 7:
            return None
        reasons = base["reasons"] + [f"✅ 大小球方向:{label} 赔率{odd:.2f}"]
        return {"bet_type":"overunder","direction":direction,"direction_label":label,
                "odds":odd,"confidence":confidence,"reasons":reasons,
                "score_at_bet":f"{h}-{a}","handicap_line":2.5}

    def evaluate_handicap(self, fixture, stats, odds_all) -> Optional[Dict[str, Any]]:
        """让球盘口：领先方让0.5，跟随领先方；平局选让球方低赔一侧"""
        if not self.c["enable_handicap"]:
            return None
        hc = odds_all.get("handicap", {})
        if not hc or "line" not in hc:
            return None
        base = self._base_filter(fixture, stats)
        if not base["passed"]:
            return None
        h, a = fixture["home_score"], fixture["away_score"]
        line = hc.get("line", 0)
        # 主队让球(line<0)且主队领先/平局→主队让球胜
        # 客队让球(line>0)且客队领先/平局→客队让球胜
        if line < 0 and h >= a:
            direction = "home"; odd = hc.get("home", 0); label = f"主让{abs(line)}胜"
        elif line > 0 and a >= h:
            direction = "away"; odd = hc.get("away", 0); label = f"客让{abs(line)}胜"
        else:
            return None
        if not odd or not self._check_odds_range(odd):
            return None
        confidence = base["confidence"]
        if confidence < 7:
            return None
        reasons = base["reasons"] + [f"✅ 让球方向:{label} 赔率{odd:.2f}"]
        return {"bet_type":"handicap","direction":direction,"direction_label":label,
                "odds":odd,"confidence":confidence,"reasons":reasons,
                "score_at_bet":f"{h}-{a}","handicap_line":line}

    def evaluate_all(self, fixture, stats, odds_all) -> list:
        """对一场比赛同时评估三个盘口，返回所有通过的投注选项"""
        candidates = []
        for fn in (self.evaluate_1x2, self.evaluate_overunder, self.evaluate_handicap):
            try:
                r = fn(fixture, stats, odds_all)
                if r:
                    candidates.append(r)
            except Exception as e:
                print(f"     ⚠️ 盘口评估异常: {e}")
        # 按信心降序，同信心按赔率降序
        candidates.sort(key=lambda x: (x["confidence"], x["odds"]), reverse=True)
        return candidates

# ============================================================
# 交易管理器（三盘口结算）
# ============================================================
class BetManager:
    def __init__(self):
        self.c = CONFIG
        self.pending = load_json(PENDING_FILE, [])
        self.balance_data = load_json(BALANCE_FILE, {
            "balance": self.c["init_balance"], "initial_balance": self.c["init_balance"],
            "total_pnl": 0.0, "total_bets": 0, "win_count": 0, "lose_count": 0,
            "push_count": 0, "last_update": now_bj(),
        })
        self.history = load_json(HISTORY_FILE, [])

    def save_all(self):
        save_json(PENDING_FILE, self.pending)
        save_json(BALANCE_FILE, self.balance_data)
        save_json(HISTORY_FILE, self.history)

    def _pending_keys(self):
        # 同一场比赛同一盘口只下一单
        return {(b["fixture_id"], b["bet_type"]) for b in self.pending if b["status"] == "pending"}

    def available_slots(self):
        active = len([b for b in self.pending if b["status"] == "pending"])
        return max(0, self.c["max_concurrent_bets"] - active)

    def place_bet(self, fixture, candidate):
        key = (fixture["fixture_id"], candidate["bet_type"])
        if key in self._pending_keys():
            return None
        if self.available_slots() <= 0:
            return None
        stake = self.c["stake_per_bet"]
        if self.balance_data["balance"] < stake:
            return None
        bet = {
            "bet_id": f"bet_{datetime.now(BJ_TZ).strftime('%Y%m%d%H%M%S')}_{fixture['fixture_id']}_{candidate['bet_type']}",
            "fixture_id": fixture["fixture_id"], "league": fixture["league"],
            "home_team": fixture["home_team"], "away_team": fixture["away_team"],
            "bet_type": candidate["bet_type"],
            "bet_type_label": {"1x2":"胜平负","overunder":"大小球","handicap":"让球"}.get(candidate["bet_type"], candidate["bet_type"]),
            "direction": candidate["direction"],
            "direction_label": candidate["direction_label"],
            "stake": stake, "odds": candidate["odds"], "confidence": candidate["confidence"],
            "handicap_line": candidate.get("handicap_line"),
            "bet_time": now_bj(), "bet_minute": fixture["minute"],
            "score_at_bet": candidate["score_at_bet"], "status": "pending",
            "reasons": candidate["reasons"],
        }
        self.pending.append(bet)
        self.balance_data["balance"] -= stake
        self.balance_data["last_update"] = now_bj()
        return bet

    def _settle_1x2(self, bet, result):
        h, a = result["home_score"], result["away_score"]
        if h > a: actual = "home"
        elif a > h: actual = "away"
        else: actual = "draw"
        win = (bet["direction"] == actual)
        return win, None  # None=无走水

    def _settle_overunder(self, bet, result):
        total = result["home_score"] + result["away_score"]
        line = bet.get("handicap_line", 2.5)
        if total > line: actual = "over"
        elif total < line: actual = "under"
        else: return None, True  # 走水退款
        win = (bet["direction"] == actual)
        return win, False

    def _settle_handicap(self, bet, result):
        h, a = result["home_score"], result["away_score"]
        line = bet.get("handicap_line", 0)
        # line<0 主队让球；line>0 客队让球
        if line < 0:
            adj_h = h + line  # 主队减去让球
            adj_a = a
        else:
            adj_h = h
            adj_a = a - line  # 客队减去让球
        if adj_h > adj_a: actual = "home"
        elif adj_a > adj_h: actual = "away"
        else: return None, True  # 让球后平局=走水
        win = (bet["direction"] == actual)
        return win, False

    def settle_bet(self, bet, result):
        stake, odds = bet["stake"], bet["odds"]
        bt = bet["bet_type"]
        if bt == "1x2":
            win, push = self._settle_1x2(bet, result)
        elif bt == "overunder":
            win, push = self._settle_overunder(bet, result)
        elif bt == "handicap":
            win, push = self._settle_handicap(bet, result)
        else:
            win, push = False, False

        if push:
            self.balance_data["balance"] += stake
            self.balance_data["push_count"] += 1
            tag = "PUSH"
            profit = 0.0
        elif win:
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
            "status": tag,
            "final_score": f"{result['home_score']}-{result['away_score']}",
            "total_goals": result["home_score"] + result["away_score"],
            "profit": profit, "settle_time": now_bj(),
        })
        self.history.append(settled)
        return settled

    def _refund_bet(self, bet):
        stake = bet["stake"]
        self.balance_data["balance"] += stake
        self.balance_data["last_update"] = now_bj()
        settled = dict(bet)
        settled.update({
            "status":"REFUND","final_score":"-","total_goals":0,
            "profit":0.0,"settle_time":now_bj(),"note":"比赛取消/延期，全额退款"
        })
        self.history.append(settled)
        return settled

    def settle_all(self, provider):
        settled, remaining = [], []
        for bet in self.pending:
            if bet["status"] != "pending":
                remaining.append(bet); continue
            result = provider.get_fixture_result(bet["fixture_id"])
            if result.get("cancelled"):
                settled.append(self._refund_bet(bet)); continue
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
            ("赢 / 输 / 走水", f"{b['win_count']} / {b['lose_count']} / {b.get('push_count',0)}"),
            ("胜率", wr),
            ("待结算挂单", len([x for x in self.pending if x["status"]=="pending"])),
            ("最后更新", b["last_update"]),
        ]
        for k, v in rows:
            print(f"  {k:<12} : {v}")

        active = [b for b in self.pending if b["status"] == "pending"]
        if active:
            print_line("-"); print("  📋 待结算挂单"); print_line("-")
            for i, bet in enumerate(active, 1):
                print(f"  #{i} [{bet['bet_type_label']}] [{bet['league']}] {bet['home_team']} vs {bet['away_team']}")
                print(f"      方向:{bet['direction_label']} 赔率:{bet['odds']} 金额:{bet['stake']} 信心:{bet['confidence']}")
                print(f"      下注时:{bet['bet_time']} 分钟:{bet['bet_minute']} 比分:{bet['score_at_bet']}")

        if self.history:
            print_line("-"); print("  📜 结算历史（最近10条）"); print_line("-")
            for i, bet in enumerate(reversed(self.history[-10:]), 1):
                tag_map = {"WIN":"✅赢","LOSE":"❌输","PUSH":"➖走水","REFUND":"↩️退款"}
                tag = tag_map.get(bet["status"], bet["status"])
                print(f"  {tag} [{bet['bet_type_label']}] {bet['home_team']} vs {bet['away_team']}  "
                      f"终场{bet['final_score']}(总{bet['total_goals']}球)  盈亏{bet['profit']:+.2f}")
        print_line()

# ============================================================
# 两阶段主流程
# ============================================================
def phase_bet(provider):
    print_line()
    print(f"  🎯 阶段一：模拟下注（三盘口） [{now_bj()}]")
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
        odds_all = provider.get_odds_all(fid)
        if not odds_all:
            print("     ⚠️ 无赔率数据，跳过\n"); continue
        candidates = engine.evaluate_all(fx, stats, odds_all)
        if not candidates:
            print("     ❌ 三盘口均未通过筛选\n"); continue
        # 每场比赛最多下1个盘口（取信心最高的）
        best = candidates[0]
        print(f"     🎯 最优盘口: [{best['bet_type']}] {best['direction_label']} 赔率{best['odds']:.2f} 信心{best['confidence']}")
        for r in best["reasons"]:
            print(f"     {r}")
        bet = manager.place_bet(fx, best)
        if bet:
            new_bets.append(bet); avail -= 1
            print(f"     ✅✅✅ 下注成功! [{bet['bet_type_label']}] {bet['direction_label']} 赔率{bet['odds']}")
        else:
            print("     ⚠️ 下注失败(仓位/余额/重复)")
        print()

    manager.save_all()
    print_line(); print("  📊 本次下注汇总"); print_line()
    if new_bets:
        for i, bet in enumerate(new_bets, 1):
            print(f"  #{i} [{bet['bet_type_label']}] {bet['home_team']} vs {bet['away_team']}")
            print(f"      方向:{bet['direction_label']} 赔率:{bet['odds']} 金额:{bet['stake']} 信心:{bet['confidence']} 比分:{bet['score_at_bet']}")
    else:
        print("  本次无新增下注")
    manager.print_portfolio()

def phase_settle(provider):
    print_line()
    print(f"  🏁 阶段二：结算盈亏（三盘口） [{now_bj()}]")
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
            tag_map = {"WIN":"✅ 赢","LOSE":"❌ 输","PUSH":"➖ 走水","REFUND":"↩️ 退款"}
            tag = tag_map.get(bet["status"], bet["status"])
            print(f"  #{i} {tag} [{bet['bet_type_label']}] {bet['home_team']} vs {bet['away_team']}")
            print(f"      方向:{bet['direction_label']} 赔率:{bet['odds']} 金额:{bet['stake']}")
            print(f"      下注时:{bet['score_at_bet']}({bet['bet_minute']}分钟)  终场:{bet['final_score']}(总{bet['total_goals']}球)  盈亏:{bet['profit']:+.2f}")
    else:
        print("  本次无已结束比赛（仍在进行，保留到下次结算）")
    print(f"\n  剩余待结算: {result['remaining']} 笔")
    manager.print_portfolio()

def main():
    parser = argparse.ArgumentParser(description="滚球量化模拟交易系统 v4.0 三盘口版")
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
