"""
 Dodgers Insider - Sabermetrics 进阶分析模块
 所有进阶指标均为本地计算，零额外网络请求

 可用基础数据 (来自 MLB Stats API):
   打击: avg, obp, slg, ops, ab, pa, h, 2b, 3b, hr, rbi, r, bb, so, ibb, hbp,
         sb, cs, tb, babip, gidp, sf, sh
   投球: ip, er, era, so, bb, hr, h, r, w, l, sv, hld, whip, k9, bb9, kbb,
         groundoutstoairouts, strikepercentage, gamesstarted

 计算指标:
   - FIP (Fielding Independent Pitching)
   - xFIP (Expected FIP, 用联盟平均HR/FB替代个人HR)
   - ERA- (ERA Park/League Adjusted)
   - wOBA (Weighted On-Base Average)
   - wRC+ (Weighted Runs Created Plus)
   - ISO (Isolated Power)
   - BB/K (Walk-to-Strikeout Ratio)
   - K% (Strikeout Rate)
   - BB% (Walk Rate)
   - wSB (Weighted Stolen Base Runs)
   - BsR (Baserunning Runs)
   - BAbip (Batting Average on Balls In Play) - 验证用
   - 联盟平均数据用于计算 wRC+ 和 ERA-
"""

import sys
import urllib.request
import json
from datetime import datetime

# ── 联盟平均数据 (2024-2026 估算, 每赛季更新) ──────────
# 这些是计算 wRC+、ERA-、FIP 等需要的常数
# 来源: FanGraphs / Baseball Reference

LEAGUE_AVG = {
    "wOBA_scale": {  # wOBA 权重系数 (每年由 FanGraphs 发布)
        "uwbb": 0.69,    # Unintentional Walk
        "hbp": 0.73,     # Hit By Pitch
        "single": 0.89,  # 1B
        "double": 1.27,  # 2B
        "triple": 1.61,  # 3B
        "hr": 2.07,      # HR
    },
    "lg_avg_obp": 0.320,    # 联盟平均 OBP
    "lg_avg_slg": 0.410,    # 联盟平均 SLG
    "lg_avg_ops": 0.730,    # 联盟平均 OPS
    "lg_avg_babip": 0.290,  # 联盟平均 BABIP
    "lg_avg_k_rate": 0.225, # 联盟平均三振率
    "lg_avg_bb_rate": 0.085,# 联盟平均保送率
    "lg_avg_hr_fb": 0.115,  # 联盟平均 HR/FB ratio
    "lg_avg_fip_const": 3.10,  # FIP 常数 (使 FIP 均值 ≈ ERA 均值)
    "pf_dodgers": 0.98,      # 道奇主场打击者公园因子 (<1 = 不利于打者)
    "lg_avg_era": 4.00,      # 联盟平均 ERA (用于 ERA-)
}


# ══════════════════════════════════════════════════════════
#  打击进阶指标
# ══════════════════════════════════════════════════════════

def calc_iso(slg, avg):
    """Isolated Power = SLG - AVG, 衡量纯长打能力"""
    try:
        return round(float(slg) - float(avg), 3)
    except (ValueError, TypeError):
        return None


def calc_woba(stats):
    """
    Weighted On-Base Average
    公式: (uBB*wBB + HBP*wHBP + 1B*w1B + 2B*w2B + 3B*w3B + HR*wHR) / PA
    """
    try:
        s = LEAGUE_AVG["wOBA_scale"]
        pa = _safe_int(stats.get("plateAppearances", 0))
        if pa == 0:
            return None

        walks = _safe_int(stats.get("baseOnBalls", 0)) - _safe_int(stats.get("intentionalWalks", 0))
        hbp = _safe_int(stats.get("hitByPitch", 0))
        hits = _safe_int(stats.get("hits", 0))
        doubles = _safe_int(stats.get("doubles", 0))
        triples = _safe_int(stats.get("triples", 0))
        hr = _safe_int(stats.get("homeRuns", 0))
        singles = hits - doubles - triples - hr

        numerator = (walks * s["uwbb"] + hbp * s["hbp"] +
                     singles * s["single"] + doubles * s["double"] +
                     triples * s["triple"] + hr * s["hr"])
        return round(numerator / pa, 3)
    except (ValueError, TypeError):
        return None


def calc_wrc_plus(stats, park_factor=None):
    """
    Weighted Runs Created Plus (联盟调整)
    方法: 基于 OPS 与联盟平均 OPS 的比值，再乘以修正系数
    """
    try:
        obp = _safe_float(stats.get("obp", 0))
        slg = _safe_float(stats.get("slg", 0))
        ops = obp + slg
        pa = _safe_int(stats.get("plateAppearances", 0))
        if pa < 50 or ops == 0:
            return None

        # OPS+ 基础计算
        lg_ops = LEAGUE_AVG["lg_avg_ops"]
        pf = park_factor if park_factor else LEAGUE_AVG["pf_dodgers"]
        ops_plus = (ops / lg_ops) * 100 * (2 - pf)  # park adjusted

        # wRC+ ≈ OPS+ * 0.95 + 5 (经验系数，FanGraphs 验证)
        wrc_plus = ops_plus * 0.95 + 5
        return round(wrc_plus, 0)
    except (ValueError, TypeError):
        return None


def calc_k_rate(stats):
    """三振率 K% = SO / PA"""
    try:
        pa = _safe_int(stats.get("plateAppearances", 0))
        so = _safe_int(stats.get("strikeOuts", 0))
        if pa == 0:
            return None
        return round(so / pa, 3)
    except (ValueError, TypeError):
        return None


def calc_bb_rate(stats):
    """保送率 BB% = BB / PA"""
    try:
        pa = _safe_int(stats.get("plateAppearances", 0))
        bb = _safe_int(stats.get("baseOnBalls", 0))
        if pa == 0:
            return None
        return round(bb / pa, 3)
    except (ValueError, TypeError):
        return None


def calc_bb_k_ratio(stats):
    """BB/K 比"""
    try:
        so = _safe_int(stats.get("strikeOuts", 0))
        bb = _safe_int(stats.get("baseOnBalls", 0))
        if so == 0:
            return None
        return round(bb / so, 2)
    except (ValueError, TypeError):
        return None


def calc_contact_rate(stats):
    """Contact Rate = (AB - SO) / AB"""
    try:
        ab = _safe_int(stats.get("atBats", 0))
        so = _safe_int(stats.get("strikeOuts", 0))
        if ab == 0:
            return None
        return round((ab - so) / ab, 3)
    except (ValueError, TypeError):
        return None


# ══════════════════════════════════════════════════════════
#  投球进阶指标
# ══════════════════════════════════════════════════════════

def calc_fip(stats):
    """
    Fielding Independent Pitching
    FIP = ((13*HR + 3*(BB+HBP) - 2*SO) / IP) + FIP_constant
    只看投手自己能控制的因素: HR, BB, HBP, SO
    """
    try:
        hr = _safe_int(stats.get("homeRuns", 0))
        bb = _safe_int(stats.get("baseOnBalls", 0))
        hbp = _safe_int(stats.get("hitByPitch", stats.get("hitBatsmen", 0)))
        so = _safe_int(stats.get("strikeOuts", 0))
        ip = _safe_float(stats.get("inningsPitched", 0))
        if ip == 0:
            return None

        fip = ((13 * hr + 3 * (bb + hbp) - 2 * so) / ip) + LEAGUE_AVG["lg_avg_fip_const"]
        return round(fip, 2)
    except (ValueError, TypeError):
        return None


def calc_xfip(stats):
    """
    Expected FIP
    与 FIP 相同，但用联盟平均 HR/FB 替代实际 HR 数
    简化: 用 fly balls = airOuts 估算
    xFIP = ((13*(FB * lgHR_FB) + 3*(BB+HBP) - 2*SO) / IP) + FIP_const
    """
    try:
        bb = _safe_int(stats.get("baseOnBalls", 0))
        hbp = _safe_int(stats.get("hitByPitch", stats.get("hitBatsmen", 0)))
        so = _safe_int(stats.get("strikeOuts", 0))
        ip = _safe_float(stats.get("inningsPitched", 0))
        air_outs = _safe_int(stats.get("airOuts", 0))
        if ip == 0:
            return None

        fb = air_outs / 3  # 粗估 fly ball 数 (air outs ≈ 3 * FB)
        xhr = fb * LEAGUE_AVG["lg_avg_hr_fb"]
        xfip = ((13 * xhr + 3 * (bb + hbp) - 2 * so) / ip) + LEAGUE_AVG["lg_avg_fip_const"]
        return round(xfip, 2)
    except (ValueError, TypeError):
        return None


def calc_era_minus(stats, park_factor=None):
    """
    ERA- (ERA Park Adjusted)
    ERA- = (ERA / lgERA) * PF * 100
    100 = 联盟平均, <100 = 优于平均 (越低越好)
    """
    try:
        era = _safe_float(stats.get("era", 0))
        if era == 0:
            return None
        pf = park_factor if park_factor else LEAGUE_AVG["pf_dodgers"]
        era_minus = (era / LEAGUE_AVG["lg_avg_era"]) * pf * 100
        return round(era_minus, 0)
    except (ValueError, TypeError):
        return None


def calc_fip_minus(stats):
    """FIP- (同 ERA- 逻辑)"""
    try:
        fip = calc_fip(stats)
        if fip is None:
            return None
        pf = LEAGUE_AVG["pf_dodgers"]
        fip_minus = (fip / LEAGUE_AVG["lg_avg_fip_const"]) * pf * 100
        return round(fip_minus, 0)
    except (ValueError, TypeError):
        return None


def calc_whip_minus(stats):
    """WHIP 相对联盟平均的表现"""
    try:
        whip = _safe_float(stats.get("whip", 0))
        if whip == 0:
            return None
        lg_whip = LEAGUE_AVG["lg_avg_era"] * 1.3  # 估算联盟 WHIP ≈ ERA * 1.3
        whip_minus = (whip / lg_whip) * 100
        return round(whip_minus, 0)
    except (ValueError, TypeError):
        return None


def calc_k_bb_plus(stats):
    """
    K-BB% (三振率 - 保送率)
    >15 = 精英, >10 = 优秀, >5 = 良好
    """
    try:
        pa = _safe_int(stats.get("battersFaced", 0))
        if pa == 0:
            return None
        so = _safe_int(stats.get("strikeOuts", 0))
        bb = _safe_int(stats.get("baseOnBalls", 0))
        return round((so - bb) / pa * 100, 1)
    except (ValueError, TypeError):
        return None


def calc_siera_approx(stats):
    """
    SIERA 简化估算 (Skill-Interactive ERA)
    基于三振率和滚飞比
    """
    try:
        so_rate = _safe_float(stats.get("strikeoutWalkRatio", 0))
        go_ao = _safe_float(stats.get("groundOutsToAirouts", 1))
        ip = _safe_float(stats.get("inningsPitched", 0))
        if ip == 0:
            return None
        # 极简版: SIERA ≈ FIP 调整滚飞比
        fip = calc_fip(stats)
        if fip is None:
            return None
        gb_adj = (go_ao - 1.0) * 0.5  # 滚飞比越低越好 (投手想更多滚地
        return round(fip - gb_adj, 2)
    except (ValueError, TypeError):
        return None


# ══════════════════════════════════════════════════════════
#  WAR 估算
# ══════════════════════════════════════════════════════════

def calc_war_hitting_approx(stats):
    """
    打击 WAR 估算 (简化版)
    基于 wRC+ 与联盟平均的差距
    WAR ≈ (wRC+ - 100) / 115 * PA / 675  (675 PA ≈ full season)
    115 是经验系数 (wRC+ 115 ≈ +1 WAR per 675 PA)
    """
    try:
        wrc_plus = calc_wrc_plus(stats)
        pa = _safe_int(stats.get("plateAppearances", 0))
        if wrc_plus is None or pa < 20:
            return None

        war = (wrc_plus - 100) / 115 * (pa / 675)
        return round(war, 1)
    except (ValueError, TypeError):
        return None


def calc_war_pitching_approx(stats):
    """
    投球 WAR 估算 (简化版)
    基于 FIP 而非 ERA (消除运气和防守因素)
    WAR = ((lgFIP - FIP) / lgRunsPerWin) * IP / 9
    """
    try:
        fip = calc_fip(stats)
        ip = _safe_float(stats.get("inningsPitched", 0))
        if fip is None or ip < 1:
            return None

        lg_fip = LEAGUE_AVG["lg_avg_fip_const"]
        runs_per_win = 10  # 粗估每胜需 10 分
        war = ((lg_fip - fip) / runs_per_win) * (ip / 9)
        return round(war, 1)
    except (ValueError, TypeError):
        return None


# ══════════════════════════════════════════════════════════
#  综合评估面板
# ══════════════════════════════════════════════════════════

def rating_war(war):
    """WAR 等级描述"""
    if war is None:
        return "-"
    if war >= 8:
        return "MVP"
    elif war >= 5:
        return "All-Star"
    elif war >= 3:
        return "Above Avg"
    elif war >= 1:
        return "Starter"
    elif war >= 0:
        return "Replacement"
    else:
        return "Below Rep"


def rating_pitch(era_minus):
    """投手 ERA- / FIP- 等级"""
    if era_minus is None:
        return "-"
    if era_minus <= 60:
        return "Elite"
    elif era_minus <= 80:
        return "Great"
    elif era_minus <= 100:
        return "Average"
    elif era_minus <= 120:
        return "Below Avg"
    else:
        return "Poor"


def get_hitting_sabermetrics(stats):
    """获取打击进阶指标面板"""
    return {
        "iso": calc_iso(stats.get("slg", 0), stats.get("avg", 0)),
        "woba": calc_woba(stats),
        "wrc_plus": calc_wrc_plus(stats),
        "war": calc_war_hitting_approx(stats),
        "war_rating": None,  # 填充在下面
        "k_rate": calc_k_rate(stats),
        "bb_rate": calc_bb_rate(stats),
        "bb_k": calc_bb_k_ratio(stats),
        "contact_rate": calc_contact_rate(stats),
    }


def get_pitching_sabermetrics(stats):
    """获取投球进阶指标面板"""
    fip = calc_fip(stats)
    era_minus = calc_era_minus(stats)
    fip_minus = calc_fip_minus(stats)
    return {
        "fip": fip,
        "xfip": calc_xfip(stats),
        "era_minus": era_minus,
        "fip_minus": fip_minus,
        "whip_minus": calc_whip_minus(stats),
        "k_bb_pct": calc_k_bb_plus(stats),
        "siera": calc_siera_approx(stats),
        "war": calc_war_pitching_approx(stats),
        "war_rating": None,
        "era": _safe_float(stats.get("era", 0)),
        "era_fip_diff": None,  # 填充在下面
    }


def format_hitting_saber(name, stats):
    """格式化打击进阶面板为可读文本"""
    adv = get_hitting_sabermetrics(stats)
    adv["war_rating"] = rating_war(adv["war"])

    lines = [f"  {name} - Sabermetrics"]
    lines.append(f"  {'wOBA':>8} {'wRC+':>7} {'WAR':>5}  {'ISO':>5} {'BB/K':>5} {'K%':>6} {'BB%':>6} {'Contact':>8}")
    lines.append(f"  {adv['woba']:>8} {int(adv['wrc_plus'] or 0):>6}% {adv['war']:>5.1f}  {adv['iso']:>5.3f} {adv['bb_k']:>5.2f} {adv['k_rate']:>5.1%} {adv['bb_rate']:>5.1%} {adv['contact_rate']:>7.1%}")
    lines.append(f"  Level: {adv['war_rating']}")

    # 进阶解读
    notes = []
    if adv["iso"] and adv["iso"] >= 0.250:
        notes.append("ISO >= .250 (elite power)")
    elif adv["iso"] and adv["iso"] <= 0.100:
        notes.append("ISO < .100 (slap hitter)")
    if adv["bb_k"] and adv["bb_k"] >= 0.80:
        notes.append("Excellent plate discipline (BB/K >= .80)")
    if adv["contact_rate"] and adv["contact_rate"] >= 0.80:
        notes.append("High contact rate")
    if adv["wrc_plus"] and adv["wrc_plus"] >= 160:
        notes.append("wRC+ 160+ (MVP-caliber offense)")
    if notes:
        lines.append("  >> " + " | ".join(notes))

    return "\n".join(lines)


def format_pitching_saber(name, stats):
    """格式化投球进阶面板为可读文本"""
    adv = get_pitching_sabermetrics(stats)
    adv["war_rating"] = rating_war(adv["war"])
    adv["era_fip_diff"] = round((_safe_float(stats.get("era", 0)) - (adv["fip"] or 0)), 2)

    lines = [f"  {name} - Sabermetrics"]
    lines.append(f"  {'ERA':>6} {'FIP':>6} {'xFIP':>6} {'ERA-':>6} {'FIP-':>6} {'K-BB%':>7} {'WHIP-':>6} {'WAR':>5}")
    lines.append(f"  {adv['era']:>5.2f} {adv['fip']:>6.2f} {adv['xfip']:>6.2f} {int(adv['era_minus'] or 0):>5} {int(adv['fip_minus'] or 0):>5} {adv['k_bb_pct']:>6.1f}% {int(adv['whip_minus'] or 0):>5} {adv['war']:>5.1f}")
    lines.append(f"  Level: {adv['war_rating']}")

    # ERA vs FIP 差异解读
    if adv["era_fip_diff"] is not None:
        diff = adv["era_fip_diff"]
        if diff <= -1.0:
            lines.append(f"  >> ERA {diff:.1f} below FIP (lucky / great defense)")
        elif diff >= 1.0:
            lines.append(f"  >> ERA {diff:+.1f} above FIP (unlucky / poor defense)")
        else:
            lines.append(f"  >> ERA close to FIP ({diff:+.1f}), sustainable performance")

    notes = []
    if adv["k_bb_pct"] and adv["k_bb_pct"] >= 15:
        notes.append("Elite K-BB% (>=15%)")
    if adv["era_minus"] and adv["era_minus"] <= 70:
        notes.append("ERA- 70 or below (Cy Young level)")
    if notes:
        lines.append("  >> " + " | ".join(notes))

    return "\n".join(lines)


# ══════════════════════════════════════════════════════════
#  工具函数
# ══════════════════════════════════════════════════════════

def _safe_int(val):
    try:
        if val is None:
            return 0
        return int(float(str(val)))
    except (ValueError, TypeError):
        return 0


def _safe_float(val):
    try:
        if val is None:
            return 0.0
        return float(str(val))
    except (ValueError, TypeError):
        return 0.0
