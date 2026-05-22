"""
Dodgers Insider API - FastAPI Backend
GPT Store Actions ready
Endpoints mirror dodgers_engine functions as REST API
"""

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel
from typing import Optional
import tempfile
import os

app = FastAPI(
    title="Dodgers Insider API",
    description="Los Angeles Dodgers real-time stats, schedules, standings, player profiles, and Sabermetrics. Free, powered by MLB official Stats API.",
    version="2.1.0",
)

# CORS - allow GPT Store and any frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ==================== MODELS ====================

class PlayerRequest(BaseModel):
    name_or_id: str


# ==================== ENDPOINTS ====================

@app.get("/")
def root():
    return {
        "service": "Dodgers Insider API",
        "version": "2.1.0",
        "team": "Los Angeles Dodgers",
        "endpoints": {
            "/schedule": "Today's game schedule",
            "/schedule/recent": "Recent game results (days param)",
            "/standings": "NL West standings",
            "/roster": "Active 26-man roster",
            "/roster/batting": "Position player stats (OPS sorted)",
            "/roster/pitching": "Pitcher stats (ERA sorted)",
            "/player/{name_or_id}": "Player profile (name or MLB ID)",
            "/report": "Full daily report",
            "/report/advanced": "Sabermetrics report",
            "/news": "Latest Dodgers news (count param)",
            "/poster": "Generate daily poster image (PNG)",
        },
        "docs": "/docs",
    }


@app.get("/schedule")
def schedule():
    """Today's Dodgers game schedule."""
    try:
        from dodgers_engine import get_today_schedule
        return {"data": get_today_schedule()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/schedule/recent")
def recent_schedule(
    days: int = Query(default=7, ge=1, le=30, description="Number of past days"),
):
    """Recent Dodgers game results."""
    try:
        from dodgers_engine import get_schedule, get_recent_record, format_recent_games
        games = get_schedule(days=days)
        record = get_recent_record(days=days)
        return {
            "data": {
                "games": games,
                "record": record,
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/standings")
def standings():
    """NL West division standings."""
    try:
        from dodgers_engine import get_standings, parse_dodgers_rank
        raw = get_standings()
        dodgers_rank = parse_dodgers_rank(raw)
        return {
            "data": {
                "standings": raw,
                "dodgers_rank": dodgers_rank,
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/roster")
def roster():
    """Current active 26-man roster."""
    try:
        from dodgers_engine import get_active_roster
        data = get_active_roster()
        return {"data": data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/roster/batting")
def batting_stats():
    """Position player batting stats sorted by OPS."""
    try:
        from dodgers_engine import fetch_position_players_data
        data = fetch_position_players_data()
        return {"data": data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/roster/pitching")
def pitching_stats():
    """Pitcher stats sorted by ERA."""
    try:
        from dodgers_engine import fetch_pitchers_data
        data = fetch_pitchers_data()
        return {"data": data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/player/{name_or_id}")
def player_profile(
    name_or_id: str,
    lang: str = Query(default="en", enum=["en", "zh"], description="Output language"),
):
    """Player profile by name or MLB ID. Returns structured JSON."""
    try:
        from dodgers_engine import get_player_profile
        profile = get_player_profile(name_or_id)
        if not profile:
            raise HTTPException(status_code=404, detail=f"Player '{name_or_id}' not found")
        return {"data": profile}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/report")
def daily_report(
    lang: str = Query(default="en", enum=["en", "zh"], description="Output language"),
):
    """Full daily report with schedule, standings, stats, and news."""
    try:
        from dodgers_engine import generate_daily_report
        report = generate_daily_report()
        return {"data": {"report": report, "lang": lang}}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/report/advanced")
def advanced_report():
    """Sabermetrics advanced analysis report."""
    try:
        from dodgers_engine import generate_advanced_report
        report = generate_advanced_report()
        return {"data": {"report": report}}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/news")
def news(
    count: int = Query(default=5, ge=1, le=20, description="Number of news items"),
):
    """Latest Dodgers news from MLB.com RSS."""
    try:
        from dodgers_engine import get_news
        articles = get_news(count=count)
        return {"data": articles}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/poster")
def poster():
    """Generate Dodgers daily report poster (1080x1920 PNG)."""
    try:
        from dodgers_poster import generate_poster
        tmp = tempfile.mktemp(suffix=".png")
        generate_poster(tmp)
        return FileResponse(
            tmp,
            media_type="image/png",
            filename="dodgers_daily_poster.png",
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ==================== HEALTH CHECK ====================

@app.get("/health")
def health():
    return {"status": "ok", "team": "Los Angeles Dodgers"}
