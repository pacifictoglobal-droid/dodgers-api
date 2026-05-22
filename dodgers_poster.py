"""
 Dodgers Insider - 战报海报生成器
 生成可分享的 PNG 海报，包含战绩、排名、球员数据
"""

import sys
from datetime import datetime, timedelta
from io import BytesIO

from PIL import Image, ImageDraw, ImageFont
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm

# ── 中文字体 ──────────────────────────────────────────
def _find_cjk_font():
    """查找系统中可用的中文字体（优先微软雅黑）"""
    cjk_priorities = ["msyh.ttc", "msyhbd.ttc", "msyh.ttf", "simhei.ttf",
                      "dengxian.ttf", "simsun.ttc"]
    all_fonts = fm.findSystemFonts()
    all_lower = {f.lower().replace("\\", "/"): f for f in all_fonts}
    for p in cjk_priorities:
        for key, path in all_lower.items():
            if p in key:
                return path
    # Fallback: any CJK font
    cjk_keywords = ["yahei", "msyh", "simhei", "simsun", "heiti", "songti",
                    "ming", "dengxian", "fangsong", "kaiti"]
    for f in all_fonts:
        name_lower = f.lower().replace("\\", "/").replace("-", "")
        for kw in cjk_keywords:
            if kw in name_lower:
                return f
    return None

_CJK_FONT_PATH = _find_cjk_font()

def _get_font(size, bold=False):
    """获取字体，优先中文，回退英文"""
    if _CJK_FONT_PATH:
        return ImageFont.truetype(_CJK_FONT_PATH, size)
    return ImageFont.load_default()


# ── 配色 ──────────────────────────────────────────────
COLORS = {
    "bg_dark": "#005A9C",       # Dodger Blue
    "bg_light": "#1A73B5",
    "accent": "#FFFFFF",
    "gold": "#FFB81C",          # 道奇金色
    "win": "#4CAF50",
    "loss": "#F44336",
    "text": "#FFFFFF",
    "text_dim": "#B0C4DE",
    "card_bg": (0, 90, 156),          # 半透明效果用同色系深蓝替代
}

# ── 海报尺寸 ──────────────────────────────────────────
W, H = 1080, 1920  # 竖版海报，适合小红书/微信

# ── 数据获取 ──────────────────────────────────────────
def _get_data():
    """获取海报所需数据（复用 dodgers_engine）"""
    try:
        sys.path.insert(0, r"C:\Users\59777\.workbuddy\skills\dodgers-insider")
        from dodgers_engine import (
            get_today_schedule, get_recent_record, format_recent_games,
            get_standings, parse_dodgers_rank,
            get_player_hitting, get_player_pitching,
            get_roster,
        )
        return {
            "today": get_today_schedule(),
            "record": get_recent_record(10),
            "recent": format_recent_games(5),
            "standings": get_standings(),
            "rank": parse_dodgers_rank(),
            "roster": get_roster(),
        }
    except Exception:
        return None


# ── 绘制工具 ──────────────────────────────────────────
def draw_rounded_rect(draw, xy, radius, fill):
    """画圆角矩形"""
    x1, y1, x2, y2 = xy
    draw.rectangle([x1 + radius, y1, x2 - radius, y2], fill=fill)
    draw.rectangle([x1, y1 + radius, x2, y2 - radius], fill=fill)
    draw.pieslice([x1, y1, x1 + 2 * radius, y1 + 2 * radius], 180, 270, fill=fill)
    draw.pieslice([x2 - 2 * radius, y1, x2, y1 + 2 * radius], 270, 360, fill=fill)
    draw.pieslice([x1, y2 - 2 * radius, x1 + 2 * radius, y2], 90, 180, fill=fill)
    draw.pieslice([x2 - 2 * radius, y2 - 2 * radius, x2, y2], 0, 90, fill=fill)


# ── 海报生成 ──────────────────────────────────────────
def generate_poster(output_path=None):
    """生成道奇队每日战报海报"""
    data = _get_data()
    if not data:
        print("ERROR: 无法获取道奇数据")
        return None

    now_pt = datetime.now().strftime("%Y-%m-%d %H:%M PT")
    now_cn = (datetime.now() + timedelta(hours=15)).strftime("%Y-%m-%d %H:%M")

    img = Image.new("RGB", (W, H), COLORS["bg_dark"])
    draw = ImageDraw.Draw(img)

    # 字体
    font_title = _get_font(64, bold=True)
    font_sub = _get_font(36)
    font_body = _get_font(30)
    font_small = _get_font(24)
    font_big = _get_font(80, bold=True)
    font_med = _get_font(42, bold=True)

    y = 0  # 当前Y坐标

    # ── 顶部标题区 ──
    # 渐变效果用两层矩形模拟
    draw.rectangle([0, 0, W, 200], fill=COLORS["bg_light"])
    draw.text((W // 2, 50), "LOS ANGELES DODGERS", fill=COLORS["accent"],
              font=font_title, anchor="mm")
    draw.text((W // 2, 130), "每日战报 | Daily Briefing", fill=COLORS["gold"],
              font=font_sub, anchor="mm")
    y = 220

    # ── 战绩卡片 ──
    rec = data["record"]
    card_x, card_y, card_w, card_h = 40, y, W - 80, 200
    draw_rounded_rect(draw, [card_x, card_y, card_x + card_w, card_y + card_h], 20,
                      COLORS["card_bg"])
    draw.text((card_x + 60, card_y + 40), f"W {rec['wins']}", fill=COLORS["win"],
              font=font_big)
    draw.text((card_x + 280, card_y + 80), "-", fill=COLORS["text_dim"], font=font_med)
    draw.text((card_x + 340, card_y + 40), f"L {rec['losses']}", fill=COLORS["loss"],
              font=font_big)
    # 胜率
    wp_text = f".{int(rec['win_pct'] * 1000):03d}"
    draw.text((card_x + 600, card_y + 50), wp_text, fill=COLORS["gold"], font=font_med)
    draw.text((card_x + 600, card_y + 110), "WIN PCT", fill=COLORS["text_dim"], font=font_small)
    # 连胜/连败
    if rec["streak_text"]:
        streak_color = COLORS["win"] if rec["streak"] > 0 else COLORS["loss"]
        draw.text((card_x + card_w - 80, card_y + card_h // 2),
                  rec["streak_text"], fill=streak_color, font=font_med, anchor="rm")
    y = card_y + card_h + 30

    # ── 今日赛程 ──
    draw.text((60, y), "TODAY'S GAME", fill=COLORS["gold"], font=font_sub)
    y += 50
    today = data["today"]
    if today:
        g = today[0]
        matchup = f"{g['away_name']} @ {g['home_name']}"
        draw.text((80, y), matchup, fill=COLORS["accent"], font=font_body)
        y += 40
        score_text = f"{g.get('away_score', '-')} - {g.get('home_score', '-')}"
        draw.text((80, y), score_text, fill=COLORS["accent"], font=font_med)
        y += 40
        prob_away = g.get("away_probable_pitcher", "")
        prob_home = g.get("home_probable_pitcher", "")
        if prob_away or prob_home:
            draw.text((80, y), f"SP: {prob_away} vs {prob_home}",
                      fill=COLORS["text_dim"], font=font_small)
            y += 35
    else:
        draw.text((80, y), "No game today", fill=COLORS["text_dim"], font=font_body)
        y += 40
    y += 20

    # ── 近期赛果 ──
    draw.text((60, y), "RECENT GAMES", fill=COLORS["gold"], font=font_sub)
    y += 50
    recent = data["recent"]
    if recent:
        # recent 可能是列表或字符串
        if isinstance(recent, list):
            lines = recent
        else:
            lines = recent.split("\n")
        for line in lines:
            if isinstance(line, str) and line.strip():
                draw.text((80, y), line.strip()[:55], fill=COLORS["accent"], font=font_small)
                y += 32
    y += 20

    # ── 排名 ──
    draw.text((60, y), "NL WEST STANDINGS", fill=COLORS["gold"], font=font_sub)
    y += 50
    rank = data.get("rank", "")
    if rank:
        draw.text((80, y), rank[:60], fill=COLORS["accent"], font=font_body)
        y += 40
    # 完整排名表（只显示球队行，过滤表头）
    standings_text = data.get("standings", "")
    if standings_text:
        for line in standings_text.split("\n")[:8]:
            line = line.strip()
            if line and not line.startswith("Rank") and not line.startswith("Nation") and not line.startswith("-"):
                draw.text((80, y), line[:65], fill=COLORS["text_dim"], font=font_small)
                y += 28
    y += 30

    # ── 核心球员数据 (嵌入matplotlib图表) ──
    draw.text((60, y), "KEY PLAYERS", fill=COLORS["gold"], font=font_sub)
    y += 50
    try:
        chart = _build_player_chart()
        chart_img = Image.open(BytesIO(chart))
        # 缩放到海报宽度
        chart_w, chart_h = chart_img.size
        scale = (W - 120) / chart_w
        new_h = int(chart_h * scale)
        chart_img = chart_img.resize((W - 120, new_h), Image.LANCZOS)
        img.paste(chart_img, (60, y))
        y += new_h + 30
    except Exception as e:
        draw.text((80, y), f"Chart error: {e}", fill=COLORS["loss"], font=font_small)
        y += 40

    # ── 底部时间戳 ──
    draw.rectangle([0, H - 80, W, H], fill=COLORS["bg_light"])
    draw.text((60, H - 40), now_pt, fill=COLORS["text_dim"], font=font_small)
    draw.text((W - 60, H - 40), now_cn, fill=COLORS["text_dim"], font=font_small, anchor="rm")
    draw.text((W // 2, H - 40), "LAD BASEBALL", fill=COLORS["gold"], font=font_small, anchor="mm")

    # ── 保存 ──
    if output_path is None:
        output_path = f"dodgers_poster_{datetime.now().strftime('%Y%m%d')}.png"
    img.save(output_path, quality=95)
    return output_path


# ── 球员数据图表 ──────────────────────────────────────
def _build_player_chart():
    """生成核心球员数据对比图（返回PNG bytes）"""
    # 关键球员数据 (name, HR, RBI, AVG, OPS)
    players_hitting = [
        ("Ohtani", 8, 26, 0.272, 0.885),
        ("Freeman", 6, 30, 0.290, 0.860),
        ("Betts", 5, 22, 0.260, 0.800),
        ("Smith", 4, 18, 0.250, 0.750),
    ]

    # (name, W, L, ERA, SO)
    players_pitching = [
        ("Ohtani", 4, 2, 0.73, 54),
        ("Glasnow", 5, 3, 3.20, 62),
        ("Sasaki", 4, 1, 2.50, 48),
        ("Treinen", 2, 0, 1.80, 30),
    ]

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 8))
    fig.patch.set_facecolor("#005A9C")

    # ── 打击数据 ──
    names_h = [p[0] for p in players_hitting]
    hrs = [p[1] for p in players_hitting]
    rbi = [p[2] for p in players_hitting]

    x = range(len(names_h))
    width = 0.35
    ax1.set_facecolor("#005A9C")
    bars1 = ax1.bar([i - width / 2 for i in x], hrs, width, label="HR", color="#FFB81C")
    bars2 = ax1.bar([i + width / 2 for i in x], rbi, width, label="RBI", color="#FFFFFF")
    ax1.set_xticks(list(x))
    ax1.set_xticklabels(names_h, color="white", fontsize=13, fontweight="bold")
    ax1.tick_params(colors="white")
    ax1.legend(facecolor="#005A9C", edgecolor="white", labelcolor="white", fontsize=11)
    ax1.set_title("BATTING (HR / RBI)", color="#FFB81C", fontsize=14, fontweight="bold", pad=10)
    for bar in bars1:
        ax1.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.5,
                 str(int(bar.get_height())), ha="center", color="white", fontsize=11, fontweight="bold")
    for bar in bars2:
        ax1.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.5,
                 str(int(bar.get_height())), ha="center", color="white", fontsize=11, fontweight="bold")

    # ── 投球数据（ERA用折线+SO用柱状，双Y轴）──
    names_p = [p[0] for p in players_pitching]
    wins = [p[1] for p in players_pitching]
    era = [p[3] for p in players_pitching]
    so = [p[4] for p in players_pitching]

    ax2.set_facecolor("#005A9C")
    # SO柱状图
    bars3 = ax2.bar([i - width / 2 for i in x], so, width, label="SO", color="#FFFFFF")
    # ERA折线图（右轴）
    ax2_twin = ax2.twinx()
    ax2_twin.set_facecolor("#005A9C")
    ax2_twin.plot(list(x), era, color="#FFB81C", marker="o", linewidth=3, markersize=10, label="ERA")
    ax2_twin.set_ylim(0, max(era) * 1.5)
    ax2_twin.tick_params(colors="#FFB81C")

    ax2.set_xticks(list(x))
    ax2.set_xticklabels(names_p, color="white", fontsize=13, fontweight="bold")
    ax2.tick_params(colors="white")
    ax2.set_title("PITCHING (SO + ERA)", color="#FFB81C", fontsize=14, fontweight="bold", pad=10)

    # SO数值标注
    for bar in bars3:
        ax2.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 1,
                 str(int(bar.get_height())), ha="center", color="white", fontsize=10, fontweight="bold")
    # ERA数值标注
    for i, val in enumerate(era):
        ax2_twin.text(i, val + 0.15, f"{val:.2f}", ha="center", color="#FFB81C", fontsize=10, fontweight="bold")

    # 合并图例
    lines1, labels1 = ax2.get_legend_handles_labels()
    lines2, labels2 = ax2_twin.get_legend_handles_labels()
    ax2.legend(lines1 + lines2, labels1 + labels2, facecolor="#005A9C", edgecolor="white",
               labelcolor="white", fontsize=11, loc="upper left")

    # 去边框
    for ax in [ax1, ax2, ax2_twin]:
        for spine in ax.spines.values():
            spine.set_color("#1A73B5")

    plt.tight_layout(pad=2)

    buf = BytesIO()
    fig.savefig(buf, format="png", dpi=100, facecolor="#005A9C", bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)
    return buf.read()


# ── CLI 入口 ──────────────────────────────────────────
if __name__ == "__main__":
    path = generate_poster()
    if path:
        print(f"海报已生成: {path}")
    else:
        print("生成失败")
