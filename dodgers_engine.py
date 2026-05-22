"""
Dodgers Insider - 道奇队数据引擎 v2.1
基于MLB官方Stats API + RSS新闻聚合
动态阵容拉取 - 不再硬编码球员ID
v2.1 新增: 球员个人档案查询 (get_player_profile)
"""

import statsapi
import feedparser
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import urllib.request
import json

# ============ 常量 ============
DODGERS_ID = "119"
NL_WEST_DIVISION = "203"
NL_LEAGUE_ID = "104"
MLB_RSS = "https://www.mlb.com/dodgers/feeds/news/rss.xml"
PT_TIME = ZoneInfo("America/Los_Angeles")
BJ_TIME = ZoneInfo("Asia/Shanghai")
ROSTER_URL = "https://statsapi.mlb.com/api/v1/teams/119/roster?rosterType=active"

# 中文名映射（仅知名球员，其余自动用英文名）
PLAYER_CN_MAP = {
    660271: "大谷翔平", 518692: "Freddie Freeman", 605141: "Mookie Betts",
    571970: "Max Muncy", 669257: "Will Smith", 606192: "Teoscar Hernández",
    663656: "Kyle Tucker", 808967: "山本由伸", 808963: "佐佐木朗希",
    656945: "Tanner Scott", 808975: "金慧成",
}
PLAYER_NAMES_CN = PLAYER_CN_MAP  # 向后兼容


# ============ 阵容动态拉取 ============

def _fetch_json(url, timeout=20):
    """获取JSON数据（带重试）"""
    import time
    for attempt in range(2):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "DodgersInsider/1.0"})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read())
        except Exception as e:
            if attempt == 0:
                time.sleep(2)
                continue
            raise e


def get_active_roster():
    """从MLB API获取道奇当前active roster，返回 [{id, fullName, position, posAbbr}]"""
    data = _fetch_json(ROSTER_URL)
    players = []
    for p in data.get("roster", []):
        players.append({
            "id": p["person"]["id"],
            "fullName": p["person"]["fullName"],
            "position": p["position"]["abbreviation"],
            "posCode": p["position"]["code"],
        })
    return players


def is_position_player(pos_abbr):
    """判断是否为位置球员（非投手）"""
    return pos_abbr not in ("P",)


def is_pitcher(pos_abbr):
    """判断是否为投手"""
    return pos_abbr == "P"


def get_player_name_cn(player_id, fallback_name):
    """获取球员中文名或回退英文名"""
    return PLAYER_CN_MAP.get(player_id, fallback_name)


# ============ 全球员数据拉取 ============

def fetch_position_players_data():
    """获取所有位置球员的打击数据，按OPS排序"""
    roster = get_active_roster()
    result = []
    for p in roster:
        if not is_position_player(p["position"]):
            continue
        data = _safe_player_stat(p["id"], "hitting")
        if data and data.get("gamesPlayed", 0) >= 10:
            name = get_player_name_cn(p["id"], p["fullName"])
            data["_name"] = name
            data["_pos"] = p["position"]
            data["_id"] = p["id"]
            result.append(data)
    result.sort(key=lambda x: float(x.get("ops", 0)), reverse=True)
    return result


def fetch_pitchers_data():
    """获取所有投手的投球数据，按ERA排序"""
    roster = get_active_roster()
    result = []
    for p in roster:
        if not is_pitcher(p["position"]):
            continue
        data = _safe_player_stat(p["id"], "pitching")
        if data and data.get("inningsPitched") and _safe_float(data["inningsPitched"]) >= 5:
            name = get_player_name_cn(p["id"], p["fullName"])
            data["_name"] = name
            data["_pos"] = p["position"]
            data["_id"] = p["id"]
            result.append(data)
    result.sort(key=lambda x: _safe_float(x.get("era", 99)))
    return result


def _safe_float(val, default=0.0):
    """安全float转换"""
    try:
        return float(val.replace(",", "")) if isinstance(val, str) else float(val)
    except (ValueError, TypeError, AttributeError):
        return default


def _safe_player_stat(player_id, stat_type):
    """安全获取球员数据"""
    try:
        data = statsapi.player_stat_data(str(player_id), stat_type, "season")
        if data and data.get("stats"):
            return data["stats"][0]["stats"]
    except Exception:
        pass
    return None


# 向后兼容函数
def get_player_hitting(player_id):
    """获取赛季打击数据（旧版兼容）"""
    data = _safe_player_stat(player_id, "hitting")
    if data:
        try:
            lookup = statsapi.lookup_player(str(player_id))
            name = lookup[0]["fullName"] if lookup else str(player_id)
        except Exception:
            name = str(player_id)
        return {"name": name, "position": "", "stats": data}
    return None


def get_player_pitching(player_id):
    """获取赛季投球数据（旧版兼容）"""
    data = _safe_player_stat(player_id, "pitching")
    if data:
        try:
            lookup = statsapi.lookup_player(str(player_id))
            name = lookup[0]["fullName"] if lookup else str(player_id)
        except Exception:
            name = str(player_id)
        return {"name": name, "position": "", "stats": data}
    return None


def lookup_player(name):
    """模糊查找球员"""
    return statsapi.lookup_player(name)


# ============ 赛程 & 战绩 ============

def get_schedule(days=7):
    """获取道奇近N天赛程"""
    today = datetime.now(PT_TIME)
    start = (today - timedelta(days=days)).strftime("%m/%d/%Y")
    end = today.strftime("%m/%d/%Y")
    return statsapi.schedule(start_date=start, end_date=end, team=DODGERS_ID)


def get_today_schedule():
    """获取今日道奇赛程"""
    today = datetime.now(PT_TIME).strftime("%m/%d/%Y")
    return statsapi.schedule(date=today, team=DODGERS_ID)


def get_recent_record(days=10):
    """计算近N天胜负记录"""
    games = get_schedule(days)
    finished = []
    for g in games:
        if g.get("status") == "Final":
            is_home = g["home_name"] == "Los Angeles Dodgers"
            ds = g["home_score"] if is_home else g["away_score"]
            os_ = g["away_score"] if is_home else g["home_score"]
            finished.append(1 if ds > os_ else 0)

    wins = sum(finished)
    losses = len(finished) - wins

    # 连胜/连败
    streak, st = 0, None
    for v in reversed(finished):
        if st is None:
            st, streak = v, 1
        elif v == st:
            streak += 1
        else:
            break
    streak_text = f"{streak}连胜" if st == 1 and streak > 1 else f"{streak}连败" if st == 0 and streak > 1 else ""

    return {
        "wins": wins, "losses": losses, "total": wins + losses,
        "win_pct": round(wins / (wins + losses), 3) if (wins + losses) > 0 else 0,
        "streak": streak if st == 1 else -streak, "streak_text": streak_text,
    }


def format_recent_games(days=5):
    """格式化近N天比赛结果"""
    games = get_schedule(days)
    lines = []
    for g in reversed(games[-days:]):
        if g.get("status") != "Final":
            continue
        is_home = g["home_name"] == "Los Angeles Dodgers"
        opp = g["away_name"] if is_home else g["home_name"]
        ds = g["home_score"] if is_home else g["away_score"]
        os_ = g["away_score"] if is_home else g["home_score"]
        r = "胜" if ds > os_ else "负"
        def short(n): return n.split()[-1] if n and len(n.split()) > 1 else (n or "")
        ha = "vs" if is_home else "@"
        line = f"  {g['game_date'][:10]} {ha} {opp} {ds}-{os_} ({r})"
        wp = short(g.get("winning_pitcher", ""))
        lp = short(g.get("losing_pitcher", ""))
        if wp: line += f" | 胜: {wp}"
        if lp: line += f" / 败: {lp}"
        lines.append(line)
    return lines


# ============ 排名 ============

def get_standings():
    """获取国联西区排名"""
    return statsapi.standings(leagueId=NL_LEAGUE_ID, division=NL_WEST_DIVISION)


def parse_dodgers_rank():
    """解析道奇排名行"""
    text = get_standings()
    for line in text.split("\n"):
        if "Dodgers" in line:
            return line.strip()
    return None


# ============ 阵容 ============

def get_roster():
    """获取当前阵容（文本格式）"""
    return statsapi.roster(int(DODGERS_ID))


# ============ 新闻 ============

def get_news(count=5):
    """获取MLB.com道奇新闻"""
    d = feedparser.parse(MLB_RSS)
    return [{"title": e.get("title", ""), "link": e.get("link", ""), "published": e.get("published", "")} for e in d.entries[:count]]


# ============ 格式化工具 ============

def format_hitting_line(s):
    """格式化单行打击数据"""
    return (f"  打击率: {s.get('avg','-')} | OPS: {s.get('ops','-')} | "
            f"HR: {s.get('homeRuns',0)} | RBI: {s.get('rbi',0)} | "
            f"安打: {s.get('hits',0)} | 三振: {s.get('strikeOuts',0)} | "
            f"保送: {s.get('baseOnBalls',0)} | 盗垒: {s.get('stolenBases',0)} | "
            f"出赛: {s.get('gamesPlayed',0)}G")


def format_pitching_line(s):
    """格式化单行投球数据"""
    return (f"  ERA: {s.get('era','-')} | WHIP: {s.get('whip','-')} | "
            f"W-L: {s.get('wins',0)}-{s.get('losses',0)} | "
            f"局数: {s.get('inningsPitched','N/A')} | "
            f"三振: {s.get('strikeOuts',0)} | 保送: {s.get('baseOnBalls',0)} | "
            f"被HR: {s.get('homeRuns','N/A')}")


# ============ 每日战报 ============

def generate_daily_report():
    """生成道奇每日战报（动态阵容版）"""
    now_pt = datetime.now(PT_TIME)
    now_bj = now_pt.astimezone(BJ_TIME)

    lines = []
    lines.append("=" * 55)
    lines.append("  洛杉矶道奇队 每日速报")
    lines.append(f"  太平洋时间: {now_pt.strftime('%Y-%m-%d %H:%M')} | 北京时间: {now_bj.strftime('%Y-%m-%d %H:%M')}")
    lines.append("=" * 55)

    # ---- 1. 今日赛程 ----
    lines.append("\n【今日赛程】")
    today_games = get_today_schedule()
    if today_games:
        for g in today_games:
            st = g.get("status", "")
            pa = g.get("away_probable_pitcher", "")
            ph = g.get("home_probable_pitcher", "")
            lines.append(f"  {g['away_name']} @ {g['home_name']}")
            if pa or ph:
                lines.append(f"  先发投手: {pa} vs {ph}")
            lines.append(f"  状态: {st}")
            if st == "Final":
                lines.append(f"  比分: {g.get('away_score','?')} - {g.get('home_score','?')}")
    else:
        lines.append("  今日无比赛 (休赛日)")

    # ---- 2. 近期战绩 ----
    lines.append("\n【近期战绩】")
    rec = get_recent_record(10)
    lines.append(f"  近10场: {rec['wins']}胜{rec['losses']}负 (胜率 {rec['win_pct']})")
    if rec["streak_text"]:
        lines.append(f"  当前走势: {rec['streak_text']}")
    recent = format_recent_games(6)
    if recent:
        lines.append("  近期比赛:")
        for r in recent:
            lines.append(r)

    # ---- 3. 分区排名 ----
    lines.append("\n【国联西区排名】")
    rank = parse_dodgers_rank()
    if rank:
        lines.append(f"  {rank}")

    # ---- 4. 全队打击数据（按OPS排序） ----
    lines.append("\n【打击排行榜 (按OPS)】")
    try:
        batters = fetch_position_players_data()
        if batters:
            lines.append(f"  {'球员':<20} {'位置':<4} {'AVG':>6} {'OPS':>6} {'HR':>3} {'RBI':>4} {'H':>4} {'K':>4} {'BB':>4} {'SB':>3}")
            lines.append("  " + "-" * 60)
            for s in batters[:12]:
                name = s.get("_name", "")[:18]
                lines.append(f"  {name:<20} {s.get('_pos',''):<4} {s.get('avg','-'):>6} {s.get('ops','-'):>6} "
                             f"{s.get('homeRuns',0):>3} {s.get('rbi',0):>4} {s.get('hits',0):>4} "
                             f"{s.get('strikeOuts',0):>4} {s.get('baseOnBalls',0):>4} {s.get('stolenBases',0):>3}")
        else:
            lines.append("  暂无数据")
    except Exception as e:
        lines.append(f"  [加载失败] {e}")

    # ---- 5. 全队投球数据（按ERA排序） ----
    lines.append("\n【投手排行榜 (按ERA)】")
    try:
        pitchers = fetch_pitchers_data()
        if pitchers:
            lines.append(f"  {'球员':<20} {'ERA':>6} {'WHIP':>6} {'W-L':>7} {'IP':>6} {'K':>4} {'BB':>4} {'HR':>4}")
            lines.append("  " + "-" * 55)
            for s in pitchers[:12]:
                name = s.get("_name", "")[:18]
                wl = f"{s.get('wins',0)}-{s.get('losses',0)}"
                lines.append(f"  {name:<20} {s.get('era','-'):>6} {s.get('whip','-'):>6} {wl:>7} "
                             f"{s.get('inningsPitched',''):>6} {s.get('strikeOuts',0):>4} {s.get('baseOnBalls',0):>4} {s.get('homeRuns',0):>4}")
        else:
            lines.append("  暂无数据")
    except Exception as e:
        lines.append(f"  [加载失败] {e}")

    # ---- 6. 最新新闻 ----
    lines.append("\n【最新新闻 (MLB.com)】")
    news = get_news(5)
    for i, n in enumerate(news, 1):
        lines.append(f"  {i}. {n['title']}")
        lines.append(f"     {n['link']}")

    # ---- 7. 阵容快照 ----
    lines.append("\n【当前阵容 (26人)】")
    try:
        roster_data = _fetch_json(ROSTER_URL)
        pos_list = []
        pitcher_list = []
        for p in roster_data.get("roster", []):
            name = p["person"]["fullName"]
            pos = p["position"]["abbreviation"]
            entry = f"{pos:>4} {name}"
            if pos == "P":
                pitcher_list.append(entry)
            else:
                pos_list.append(entry)
        lines.append(f"  位置球员 ({len(pos_list)}): {' | '.join(pos_list)}")
        lines.append(f"  投手 ({len(pitcher_list)}): {' | '.join(pitcher_list)}")
    except Exception as e:
        lines.append(f"  [加载失败] {e}")

    lines.append("\n" + "=" * 55)
    return "\n".join(lines)


# ============ Sabermetrics 进阶分析 ============

def generate_advanced_report():
    """生成道奇队进阶分析报告（动态阵容版）"""
    now_pt = datetime.now(PT_TIME)
    now_bj = now_pt.astimezone(BJ_TIME)

    lines = []
    lines.append("=" * 65)
    lines.append("  DODGERS SABERMETRICS REPORT - 道奇进阶数据分析")
    lines.append(f"  PT: {now_pt.strftime('%Y-%m-%d %H:%M')} | BJ: {now_bj.strftime('%Y-%m-%d %H:%M')}")
    lines.append("=" * 65)

    # --- BATTING ADVANCED ---
    lines.append("\n--- 打击进阶 (wRC+降序) ---")
    try:
        from sabermetrics import (calc_wrc_plus, calc_woba, calc_iso,
                                  calc_war_hitting_approx, rating_war)
        batters = fetch_position_players_data()
        advanced = []
        for s in batters:
            try:
                wrc = calc_wrc_plus(s)
                if wrc:
                    advanced.append({
                        "name": s["_name"],
                        "pos": s["_pos"],
                        "wrc": wrc,
                        "woba": calc_woba(s),
                        "iso": calc_iso(s.get("slg", 0), s.get("avg", 0)),
                        "war": calc_war_hitting_approx(s),
                        "war_r": rating_war(calc_war_hitting_approx(s)),
                        "avg": s.get("avg", ""),
                        "ops": s.get("ops", ""),
                        "hr": s.get("homeRuns", 0),
                    })
            except Exception:
                pass
        advanced.sort(key=lambda x: x["wrc"], reverse=True)
        for a in advanced[:12]:
            lines.append(f"  {a['name']:<18} {a['pos']:<4} wRC+:{a['wrc']:>4}% wOBA:{a.get('woba','-'):>5} "
                         f"ISO:{a.get('iso','-'):>5} WAR:{a.get('war',0):>4.1f} [{a.get('war_r','')}] "
                         f"AVG:{a['avg']:>5} OPS:{a['ops']:>5} HR:{a['hr']:>3}")
    except Exception as e:
        lines.append(f"  [加载失败] {e}")

    # --- PITCHING ADVANCED ---
    lines.append("\n--- 投球进阶 (FIP升序) ---")
    try:
        from sabermetrics import (calc_fip, calc_xfip, calc_era_minus,
                                  calc_fip_minus, calc_k_bb_plus,
                                  calc_war_pitching_approx, rating_war, _safe_float)
        pits = fetch_pitchers_data()
        advanced = []
        for s in pits:
            try:
                fip = calc_fip(s)
                if fip:
                    era = _safe_float(s.get("era", 0))
                    advanced.append({
                        "name": s["_name"],
                        "fip": fip,
                        "xfip": calc_xfip(s),
                        "era": era,
                        "era_minus": calc_era_minus(s),
                        "fip_minus": calc_fip_minus(s),
                        "k_bb": calc_k_bb_plus(s),
                        "war": calc_war_pitching_approx(s),
                        "war_r": rating_war(calc_war_pitching_approx(s)),
                    })
            except Exception:
                pass
        advanced.sort(key=lambda x: x["fip"])
        for a in advanced[:12]:
            lines.append(f"  {a['name']:<18} FIP:{a['fip']:>5.2f} xFIP:{a['xfip']:>5.2f} "
                         f"ERA:{a['era']:>5.2f} ERA-:{a.get('era_minus',0):>4} FIP-:{a.get('fip_minus',0):>4} "
                         f"K-BB%:{a.get('k_bb',0):>5.1f}% WAR:{a['war']:>4.1f} [{a['war_r']}]")
    except Exception as e:
        lines.append(f"  [加载失败] {e}")

    lines.append("\n" + "=" * 65)
    return "\n".join(lines)


# 保留旧版函数签名（Sabermetrics格式化）供外部调用
def format_hitting_saber_advanced(name, stats):
    """格式化打击进阶面板（旧版兼容）"""
    try:
        from sabermetrics import (calc_iso, calc_woba, calc_wrc_plus,
                                  calc_war_hitting_approx, rating_war,
                                  calc_k_rate, calc_bb_rate, calc_bb_k_ratio, calc_contact_rate)
        iso = calc_iso(stats.get("slg", 0), stats.get("avg", 0))
        woba = calc_woba(stats)
        wrc_plus = calc_wrc_plus(stats)
        war = calc_war_hitting_approx(stats)
        war_r = rating_war(war)
        k_rate = calc_k_rate(stats)
        bb_rate = calc_bb_rate(stats)
        bb_k = calc_bb_k_ratio(stats)
        contact = calc_contact_rate(stats)
        notes = []
        if wrc_plus and wrc_plus >= 160: notes.append("MVP-caliber")
        elif wrc_plus and wrc_plus >= 130: notes.append("All-Star")
        if iso and iso >= 0.250: notes.append("elite power")
        if bb_k and bb_k >= 0.80: notes.append("great eye")
        note_str = f"  >> {' | '.join(notes)}" if notes else ""
        return (f"  {name}\n"
                f"    wOBA:{woba or '-':>5} wRC+:{int(wrc_plus or 0):>4}% WAR:{war or '-':>4.1f} ISO:{iso or '-':>5} BB/K:{bb_k or '-':>5}\n"
                f"    K%:{(k_rate or 0):>5.1%} BB%:{(bb_rate or 0):>5.1%} Contact:{(contact or 0):>6.1%}  [{war_r}]\n"
                f"{note_str}")
    except Exception:
        return f"  {name}: Sabermetrics unavailable"


def format_pitching_saber_advanced(name, stats):
    """格式化投球进阶面板（旧版兼容）"""
    try:
        from sabermetrics import (calc_fip, calc_xfip, calc_era_minus, calc_fip_minus,
                                  calc_k_bb_plus, calc_war_pitching_approx, rating_war, _safe_float)
        fip = calc_fip(stats)
        xfip = calc_xfip(stats)
        era_minus = calc_era_minus(stats)
        fip_minus = calc_fip_minus(stats)
        k_bb = calc_k_bb_plus(stats)
        war = calc_war_pitching_approx(stats)
        war_r = rating_war(war)
        era = _safe_float(stats.get("era", 0))
        era_fip = round(era - (fip or 0), 2)
        notes = []
        if k_bb and k_bb >= 15: notes.append("elite K-BB%")
        if era_minus and era_minus <= 70: notes.append("Cy Young level ERA-")
        if era_fip and era_fip <= -1.0: notes.append("outperforming FIP")
        elif era_fip and era_fip >= 1.0: notes.append("underperforming FIP")
        note_str = f"  >> {' | '.join(notes)}" if notes else ""
        return (f"  {name}\n"
                f"    ERA:{era:>5.2f} FIP:{fip or '-':>5.2f} xFIP:{xfip or '-':>5.2f} "
                f"ERA-:{int(era_minus or 0):>3} FIP-:{int(fip_minus or 0):>3}\n"
                f"    K-BB%:{k_bb or '-':>5.1f}% WAR:{war or '-':>4.1f} ERA-FIP:{era_fip:>+5.1f}  [{war_r}]\n"
                f"{note_str}")
    except Exception:
        return f"  {name}: Sabermetrics unavailable"


# ============ 球员个人档案 (v2.1 新增) ============

def _resolve_player_id(name_or_id):
    """将球员名或ID解析为(player_id, full_name)。name_or_id可以是数字ID或姓名字符串"""
    if str(name_or_id).isdigit():
        pid = int(name_or_id)
        # 尝试从 roster 获取名称
        try:
            roster = get_active_roster()
            for r in roster:
                if r["id"] == pid:
                    return pid, r["fullName"]
        except Exception:
            pass
        return pid, str(pid)
    else:
        # 按姓名查找
        results = statsapi.lookup_player(str(name_or_id))
        if not results:
            # 模糊匹配：尝试在当前阵容中搜索
            try:
                roster = get_active_roster()
                target = str(name_or_id).lower()
                for r in roster:
                    fn = r["fullName"].lower()
                    if target in fn or fn in target:
                        return r["id"], r["fullName"]
            except Exception:
                pass
            return None, None
        # 优先匹配道奇球员
        for r in results:
            team = r.get("currentTeam", {})
            if team and team.get("id") == 119:
                return r["id"], r["fullName"]
        return results[0]["id"], results[0]["fullName"]


def get_player_profile(name_or_id):
    """
    获取球员完整个人档案
    参数: name_or_id - 球员ID(数字) 或 姓名(字符串)
    返回: dict 包含以下模块:
      - basic: 个人基本信息（出生日期、身高体重、打击投球手、位置等）
      - team: 当前球队信息
      - social: 社交媒体链接
      - draft: 选秀信息
      - career_highlights: 职业生涯高光（各赛季摘要）
      - season_stats: 当前赛季数据
      - cn_name: 中文名（如有）
    """
    pid, full_name = _resolve_player_id(name_or_id)
    if pid is None:
        return None

    # 从 People API 获取完整资料
    url = f"https://statsapi.mlb.com/api/v1/people/{pid}?hydrate=currentTeam,team,stats(group=[hitting,pitching],type=[yearByYear,season],sportIds=1)"
    data = _fetch_json(url)
    if not data or not data.get("people"):
        return None

    p = data["people"][0]
    profile = {}

    # === 1. 基本信息 ===
    pos = p.get("primaryPosition", {})
    bats = p.get("batSide", {})
    throws = p.get("pitchHand", {})
    team = p.get("currentTeam", {})
    cn = get_player_name_cn(pid, p.get("fullName", ""))

    # 计算大联盟年资（从首秀到现在的完整赛季数）
    debut = p.get("mlbDebutDate", "")
    mlb_years = ""
    if debut:
        try:
            debut_year = int(debut[:4])
            current_year = datetime.now().year
            mlb_years = f"{debut_year}-Present"
        except Exception:
            mlb_years = debut

    profile["basic"] = {
        "id": pid,
        "fullName": p.get("fullName", ""),
        "cnName": cn,
        "firstName": p.get("firstName", ""),
        "middleName": p.get("middleName", ""),
        "lastName": p.get("lastName", ""),
        "nickName": p.get("nickName", ""),
        "birthDate": p.get("birthDate", ""),
        "birthCity": p.get("birthCity", ""),
        "birthState": p.get("birthStateProvince", ""),
        "birthCountry": p.get("birthCountry", ""),
        "age": p.get("currentAge", ""),
        "height": p.get("height", ""),
        "weight": f"{p.get('weight', '')} lbs",
        "bats": bats.get("description", ""),
        "throws": throws.get("description", ""),
        "position": pos.get("description", ""),
        "positionAbbr": pos.get("abbreviation", ""),
        "jerseyNumber": p.get("primaryNumber", ""),
        "mlbDebut": debut,
        "mlbYears": mlb_years,
        "draftYear": p.get("draftYear", ""),
        "active": p.get("active", False),
        "isVerified": p.get("isVerified", False),
        "gender": p.get("gender", ""),
        "slug": p.get("nameSlug", ""),
    }

    # === 2. 球队信息 ===
    profile["team"] = {
        "id": team.get("id", ""),
        "name": team.get("name", ""),
        "abbreviation": team.get("abbreviation", ""),
        "locationName": team.get("locationName", ""),
        "venue": (team.get("venue") or {}).get("name", ""),
        "league": (team.get("league") or {}).get("name", ""),
        "division": (team.get("division") or {}).get("name", ""),
        "firstYearOfPlay": team.get("firstYearOfPlay", ""),
    } if team.get("id") else {}

    # === 3. 社交媒体 ===
    profile["social"] = []
    for s in p.get("social", []):
        profile["social"].append({
            "platform": s.get("platform", ""),
            "url": s.get("url", ""),
            "followers": s.get("followers", ""),
        })

    # === 4. 选秀信息 ===
    profile["draft"] = []
    for d in p.get("draft", []):
        profile["draft"].append({
            "year": d.get("year", ""),
            "round": d.get("round", ""),
            "pick": d.get("pickOverall", ""),
            "teamName": (d.get("team") or {}).get("name", ""),
        })

    # === 5. 职业生涯各赛季摘要 ===
    career_hitting = []
    career_pitching = []

    if p.get("stats"):
        for sg in p["stats"]:
            gname = sg.get("group", {}).get("displayName", "")
            stype = sg.get("type", {}).get("displayName", "")

            if stype == "yearByYear":
                for split in sg.get("splits", []):
                    s = split["stat"]
                    season = split.get("season", "") or s.get("season", "")
                    t = split.get("team", {})
                    # team 可能缺少 abbreviation，用 name 推断
                    team_name = t.get("name", "")
                    team_abbr = t.get("abbreviation", "")
                    if not team_abbr and team_name:
                        parts = team_name.split()
                        team_abbr = "".join(p[0].upper() for p in parts) if parts else team_name[:3]
                    entry = {
                        "season": season,
                        "team": team_name,
                        "teamAbbr": team_abbr,
                        "gamesPlayed": s.get("gamesPlayed", 0),
                    }

                    if gname == "hitting":
                        entry.update({
                            "avg": s.get("avg", ""),
                            "obp": s.get("obp", ""),
                            "slg": s.get("slg", ""),
                            "ops": s.get("ops", ""),
                            "homeRuns": s.get("homeRuns", 0),
                            "rbi": s.get("rbi", 0),
                            "runs": s.get("runs", 0),
                            "hits": s.get("hits", 0),
                            "atBats": s.get("atBats", 0),
                            "doubles": s.get("doubles", 0),
                            "triples": s.get("triples", 0),
                            "stolenBases": s.get("stolenBases", 0),
                            "strikeOuts": s.get("strikeOuts", 0),
                            "baseOnBalls": s.get("baseOnBalls", 0),
                        })
                        career_hitting.append(entry)
                    elif gname == "pitching":
                        entry.update({
                            "era": s.get("era", ""),
                            "whip": s.get("whip", ""),
                            "wins": s.get("wins", 0),
                            "losses": s.get("losses", 0),
                            "saves": s.get("saves", 0),
                            "inningsPitched": s.get("inningsPitched", ""),
                            "strikeOuts": s.get("strikeOuts", 0),
                            "baseOnBalls": s.get("baseOnBalls", 0),
                            "homeRuns": s.get("homeRuns", 0),
                            "gamesStarted": s.get("gamesStarted", 0),
                        })
                        career_pitching.append(entry)

    # 倒序（最新赛季在前）
    career_hitting.sort(key=lambda x: x.get("season", "0000"), reverse=True)
    career_pitching.sort(key=lambda x: x.get("season", "0000"), reverse=True)

    profile["career_hitting"] = career_hitting
    profile["career_pitching"] = career_pitching

    # === 6. 当前赛季数据 ===
    season_stats = {}
    if p.get("stats"):
        for sg in p["stats"]:
            stype = sg.get("type", {}).get("displayName", "")
            if stype == "season":
                gname = sg.get("group", {}).get("displayName", "")
                for split in sg.get("splits", []):
                    season_stats[gname] = split["stat"]
    profile["season_stats"] = season_stats

    # === 7. 职业生涯累计 ===
    # 从 yearByYear 汇总
    def _sum_field(entries, field):
        return sum(e.get(field, 0) for e in entries)

    if career_hitting:
        total_gp = _sum_field(career_hitting, "gamesPlayed")
        total_hr = _sum_field(career_hitting, "homeRuns")
        total_rbi = _sum_field(career_hitting, "rbi")
        total_hits = _sum_field(career_hitting, "hits")
        total_r = _sum_field(career_hitting, "runs")
        total_sb = _sum_field(career_hitting, "stolenBases")
        total_so = _sum_field(career_hitting, "strikeOuts")
        total_bb = _sum_field(career_hitting, "baseOnBalls")
        total_ab = _sum_field(career_hitting, "atBats")
        avg = f"{total_hits / total_ab:.3f}" if total_ab > 0 else ""
        profile["career_totals_hitting"] = {
            "seasons": len(career_hitting),
            "gamesPlayed": total_gp,
            "avg": avg,
            "hits": total_hits,
            "homeRuns": total_hr,
            "rbi": total_rbi,
            "runs": total_r,
            "stolenBases": total_sb,
            "strikeOuts": total_so,
            "baseOnBalls": total_bb,
        }
    else:
        profile["career_totals_hitting"] = {}

    if career_pitching:
        total_gp = _sum_field(career_pitching, "gamesPlayed")
        total_w = _sum_field(career_pitching, "wins")
        total_l = _sum_field(career_pitching, "losses")
        total_sv = _sum_field(career_pitching, "saves")
        total_so = _sum_field(career_pitching, "strikeOuts")
        total_bb = _sum_field(career_pitching, "baseOnBalls")
        total_gs = _sum_field(career_pitching, "gamesStarted")
        profile["career_totals_pitching"] = {
            "seasons": len(career_pitching),
            "gamesPlayed": total_gp,
            "gamesStarted": total_gs,
            "record": f"{total_w}-{total_l}",
            "saves": total_sv,
            "strikeOuts": total_so,
            "baseOnBalls": total_bb,
        }
    else:
        profile["career_totals_pitching"] = {}

    profile["cn_name"] = cn
    return profile


def format_player_profile(profile):
    """将球员档案格式化为可读文本"""
    if not profile:
        return "[未找到该球员]"

    b = profile["basic"]
    t = profile.get("team", {})
    cn = b.get("cnName", "")
    display = f"{cn}" if cn and cn != b["fullName"] else b["fullName"]

    lines = []
    lines.append("=" * 60)
    lines.append(f"  {display}  #{b.get('jerseyNumber', '?')}  {b.get('position', '')}")
    lines.append("=" * 60)

    # 基本信息
    lines.append("\n[基本信息]")
    lines.append(f"  全名: {b.get('fullName', '')}")
    if b.get("middleName"):
        lines.append(f"  中间名: {b.get('middleName', '')}")
    if b.get("nickName"):
        lines.append(f"  昵称: {b.get('nickName', '')}")
    lines.append(f"  出生日期: {b.get('birthDate', '')}  (年龄: {b.get('age', '?')})")
    lines.append(f"  出生地: {b.get('birthCity', '')}, {b.get('birthState', '')} {b.get('birthCountry', '')}")
    lines.append(f"  身高: {b.get('height', '')}  体重: {b.get('weight', '')}")
    lines.append(f"  打击: {b.get('bats', '')}  投球: {b.get('throws', '')}")
    lines.append(f"  MLB首秀: {b.get('mlbDebut', '')}")
    if b.get("mlbYears"):
        lines.append(f"  大联盟年资: {b.get('mlbYears', '')}")
    if b.get("draftYear"):
        lines.append(f"  选秀年份: {b.get('draftYear', '')}")

    # 球队
    if t:
        lines.append("\n[当前球队]")
        lines.append(f"  {t.get('name', '')} ({t.get('abbreviation', '')})")
        if t.get("venue"):
            lines.append(f"  主场: {t.get('venue', '')}")
        lines.append(f"  联盟: {t.get('league', '')}  分区: {t.get('division', '')}")
        if t.get("firstYearOfPlay"):
            lines.append(f"  建队年份: {t.get('firstYearOfPlay', '')}")

    # 社交媒体
    if profile.get("social"):
        lines.append("\n[社交媒体]")
        for s in profile["social"]:
            lines.append(f"  {s['platform']}: {s['url']}")

    # 选秀
    if profile.get("draft"):
        lines.append("\n[选秀记录]")
        for d in profile["draft"]:
            lines.append(f"  {d['year']}年 第{d.get('round', '?')}轮 第{d.get('pick', '?')}顺位  {d.get('teamName', '')}")

    # 职业生涯累计
    ct = profile.get("career_totals_hitting", {})
    ctp = profile.get("career_totals_pitching", {})
    if ct or ctp:
        lines.append("\n[职业生涯累计]")
        if ct:
            lines.append(f"  打击: {ct.get('seasons', 0)}个赛季  {ct.get('gamesPlayed', 0)}场  "
                         f"AVG {ct.get('avg', '-')}  "
                         f"HR {ct.get('homeRuns', 0)}  RBI {ct.get('rbi', 0)}  "
                         f"安打 {ct.get('hits', 0)}  盗垒 {ct.get('stolenBases', 0)}  "
                         f"三振 {ct.get('strikeOuts', 0)}  保送 {ct.get('baseOnBalls', 0)}")
        if ctp:
            lines.append(f"  投球: {ctp.get('seasons', 0)}个赛季  {ctp.get('gamesPlayed', 0)}场 "
                         f"(先发{ctp.get('gamesStarted', 0)}场)  "
                         f"战绩 {ctp.get('record', '')}  救援 {ctp.get('saves', 0)}  "
                         f"三振 {ctp.get('strikeOuts', 0)}  保送 {ctp.get('baseOnBalls', 0)}")

    # 当前赛季
    ss = profile.get("season_stats", {})
    if ss:
        lines.append("\n[当前赛季数据]")
        if "hitting" in ss:
            s = ss["hitting"]
            lines.append(f"  打击: AVG {s.get('avg', '-')}  OBP {s.get('obp', '-')}  SLG {s.get('slg', '-')}  "
                         f"OPS {s.get('ops', '-')}  HR {s.get('homeRuns', 0)}  RBI {s.get('rbi', 0)}  "
                         f"安打 {s.get('hits', 0)}  三振 {s.get('strikeOuts', 0)}  保送 {s.get('baseOnBalls', 0)}  "
                         f"盗垒 {s.get('stolenBases', 0)}  出赛 {s.get('gamesPlayed', 0)}G")
        if "pitching" in ss:
            s = ss["pitching"]
            lines.append(f"  投球: ERA {s.get('era', '-')}  WHIP {s.get('whip', '-')}  "
                         f"战绩 {s.get('wins', 0)}-{s.get('losses', 0)}  救援 {s.get('saves', 0)}  "
                         f"局数 {s.get('inningsPitched', '-')}  三振 {s.get('strikeOuts', 0)}  "
                         f"保送 {s.get('baseOnBalls', 0)}  被HR {s.get('homeRuns', 0)}")

    # 各赛季历程
    ch = profile.get("career_hitting", [])
    cpi = profile.get("career_pitching", [])

    if ch:
        lines.append("\n[打击 - 各赛季历程]")
        lines.append(f"  {'赛季':<8} {'球队':<24} {'G':>4} {'AVG':>6} {'HR':>4} {'RBI':>5} {'H':>4} {'OPS':>6} {'SB':>3} {'K':>4} {'BB':>4}")
        lines.append("  " + "-" * 78)
        for e in ch:
            lines.append(f"  {e['season']:<8} {e['teamAbbr']:<24} {e['gamesPlayed']:>4} {e.get('avg','-'):>6} "
                         f"{e['homeRuns']:>4} {e['rbi']:>5} {e['hits']:>4} {e.get('ops','-'):>6} "
                         f"{e['stolenBases']:>3} {e['strikeOuts']:>4} {e['baseOnBalls']:>4}")

    if cpi:
        lines.append("\n[投球 - 各赛季历程]")
        lines.append(f"  {'赛季':<8} {'球队':<24} {'G':>4} {'GS':>4} {'W-L':>7} {'ERA':>6} {'WHIP':>6} {'IP':>6} {'K':>4} {'BB':>4} {'SV':>3}")
        lines.append("  " + "-" * 84)
        for e in cpi:
            wl = f"{e['wins']}-{e['losses']}"
            lines.append(f"  {e['season']:<8} {e['teamAbbr']:<24} {e['gamesPlayed']:>4} {e.get('gamesStarted',0):>4} "
                         f"{wl:>7} {e.get('era','-'):>6} {e.get('whip','-'):>6} "
                         f"{e.get('inningsPitched','-'):>6} {e['strikeOuts']:>4} {e['baseOnBalls']:>4} {e.get('saves',0):>3}")

    lines.append("\n" + "=" * 60)
    return "\n".join(lines)


def format_player_profile_en(profile):
    """Format player profile in English"""
    if not profile:
        return "[Player not found]"

    b = profile["basic"]
    t = profile.get("team", {})

    lines = []
    lines.append("=" * 60)
    lines.append(f"  {b.get('fullName', '')}  #{b.get('jerseyNumber', '?')}  {b.get('position', '')}")
    lines.append("=" * 60)

    # Basic info
    lines.append("\n[Personal Info]")
    lines.append(f"  Full Name: {b.get('fullName', '')}")
    if b.get("middleName"):
        lines.append(f"  Middle Name: {b.get('middleName', '')}")
    if b.get("nickName"):
        lines.append(f"  Nickname: {b.get('nickName', '')}")
    lines.append(f"  Born: {b.get('birthDate', '')}  (Age: {b.get('age', '?')})")
    birth_loc = f"{b.get('birthCity', '')}"
    if b.get("birthState"):
        birth_loc += f", {b.get('birthState', '')}"
    if b.get("birthCountry"):
        birth_loc += f" {b.get('birthCountry', '')}"
    lines.append(f"  Birthplace: {birth_loc}")
    lines.append(f"  Height: {b.get('height', '')}  Weight: {b.get('weight', '')}")
    lines.append(f"  Bats: {b.get('bats', '')}  Throws: {b.get('throws', '')}")
    lines.append(f"  MLB Debut: {b.get('mlbDebut', '')}")
    if b.get("mlbYears"):
        lines.append(f"  MLB Service: {b.get('mlbYears', '')}")
    if b.get("draftYear"):
        lines.append(f"  Draft Year: {b.get('draftYear', '')}")

    # Team
    if t:
        lines.append("\n[Current Team]")
        lines.append(f"  {t.get('name', '')} ({t.get('abbreviation', '')})")
        if t.get("venue"):
            lines.append(f"  Ballpark: {t.get('venue', '')}")
        lines.append(f"  League: {t.get('league', '')}  Division: {t.get('division', '')}")
        if t.get("firstYearOfPlay"):
            lines.append(f"  Founded: {t.get('firstYearOfPlay', '')}")

    # Social media
    if profile.get("social"):
        lines.append("\n[Social Media]")
        for s in profile["social"]:
            lines.append(f"  {s['platform']}: {s['url']}")

    # Draft
    if profile.get("draft"):
        lines.append("\n[Draft History]")
        for d in profile["draft"]:
            lines.append(f"  {d['year']} - Round {d.get('round', '?')}, Pick {d.get('pick', '?')}  {d.get('teamName', '')}")

    # Career totals
    ct = profile.get("career_totals_hitting", {})
    ctp = profile.get("career_totals_pitching", {})
    if ct or ctp:
        lines.append("\n[Career Totals]")
        if ct:
            lines.append(f"  Batting: {ct.get('seasons', 0)} seasons  {ct.get('gamesPlayed', 0)}G  "
                         f"AVG {ct.get('avg', '-')}  "
                         f"HR {ct.get('homeRuns', 0)}  RBI {ct.get('rbi', 0)}  "
                         f"H {ct.get('hits', 0)}  SB {ct.get('stolenBases', 0)}  "
                         f"SO {ct.get('strikeOuts', 0)}  BB {ct.get('baseOnBalls', 0)}")
        if ctp:
            lines.append(f"  Pitching: {ctp.get('seasons', 0)} seasons  {ctp.get('gamesPlayed', 0)}G "
                         f"({ctp.get('gamesStarted', 0)}GS)  "
                         f"Record {ctp.get('record', '')}  SV {ctp.get('saves', 0)}  "
                         f"SO {ctp.get('strikeOuts', 0)}  BB {ctp.get('baseOnBalls', 0)}")

    # Current season
    ss = profile.get("season_stats", {})
    if ss:
        lines.append("\n[2025 Season]")
        if "hitting" in ss:
            s = ss["hitting"]
            lines.append(f"  Batting: AVG {s.get('avg', '-')}  OBP {s.get('obp', '-')}  SLG {s.get('slg', '-')}  "
                         f"OPS {s.get('ops', '-')}  HR {s.get('homeRuns', 0)}  RBI {s.get('rbi', 0)}  "
                         f"H {s.get('hits', 0)}  SO {s.get('strikeOuts', 0)}  BB {s.get('baseOnBalls', 0)}  "
                         f"SB {s.get('stolenBases', 0)}  GP {s.get('gamesPlayed', 0)}")
        if "pitching" in ss:
            s = ss["pitching"]
            lines.append(f"  Pitching: ERA {s.get('era', '-')}  WHIP {s.get('whip', '-')}  "
                         f"Record {s.get('wins', 0)}-{s.get('losses', 0)}  SV {s.get('saves', 0)}  "
                         f"IP {s.get('inningsPitched', '-')}  SO {s.get('strikeOuts', 0)}  "
                         f"BB {s.get('baseOnBalls', 0)}  HR {s.get('homeRuns', 0)}")

    # Year-by-year
    ch = profile.get("career_hitting", [])
    cpi = profile.get("career_pitching", [])

    if ch:
        lines.append("\n[Batting - Year by Year]")
        lines.append(f"  {'Year':<8} {'Team':<24} {'G':>4} {'AVG':>6} {'HR':>4} {'RBI':>5} {'H':>4} {'OPS':>6} {'SB':>3} {'K':>4} {'BB':>4}")
        lines.append("  " + "-" * 78)
        for e in ch:
            lines.append(f"  {e['season']:<8} {e['teamAbbr']:<24} {e['gamesPlayed']:>4} {e.get('avg','-'):>6} "
                         f"{e['homeRuns']:>4} {e['rbi']:>5} {e['hits']:>4} {e.get('ops','-'):>6} "
                         f"{e['stolenBases']:>3} {e['strikeOuts']:>4} {e['baseOnBalls']:>4}")

    if cpi:
        lines.append("\n[Pitching - Year by Year]")
        lines.append(f"  {'Year':<8} {'Team':<24} {'G':>4} {'GS':>4} {'W-L':>7} {'ERA':>6} {'WHIP':>6} {'IP':>6} {'K':>4} {'BB':>4} {'SV':>3}")
        lines.append("  " + "-" * 84)
        for e in cpi:
            wl = f"{e['wins']}-{e['losses']}"
            lines.append(f"  {e['season']:<8} {e['teamAbbr']:<24} {e['gamesPlayed']:>4} {e.get('gamesStarted',0):>4} "
                         f"{wl:>7} {e.get('era','-'):>6} {e.get('whip','-'):>6} "
                         f"{e.get('inningsPitched','-'):>6} {e['strikeOuts']:>4} {e['baseOnBalls']:>4} {e.get('saves',0):>3}")

    lines.append("\n" + "=" * 60)
    return "\n".join(lines)
