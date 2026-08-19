"""FastAPI backend for the For Dirt song list."""
import os
import urllib.parse
from pathlib import Path

import psycopg
import requests
from psycopg.rows import dict_row
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel

DATABASE_URL = os.environ["DATABASE_URL"]
FRONTEND_DIR = Path(__file__).parent

YOUTUBE_API_KEY = os.environ.get("YOUTUBE_API_KEY", "")
GENIUS_API_KEY = os.environ.get("GENIUS_API_KEY", "")
GETSONGBPM_API_KEY = os.environ.get("GETSONGBPM_API_KEY", "")

app = FastAPI(title="For Dirt Song List")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_conn():
    return psycopg.connect(DATABASE_URL, row_factory=dict_row)


@app.on_event("startup")
def init_db():
    with get_conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS songs (
                id SERIAL PRIMARY KEY,
                title TEXT NOT NULL,
                artist TEXT NOT NULL DEFAULT '',
                key TEXT NOT NULL DEFAULT '',
                audio TEXT NOT NULL DEFAULT '',
                chart TEXT NOT NULL DEFAULT '',
                created_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
            """
        )
        row = conn.execute("SELECT count(*) AS c FROM songs").fetchone()
        if row["c"] == 0:
            conn.execute(
                "INSERT INTO songs (title, artist, key, audio, chart) VALUES (%s, %s, %s, %s, %s)",
                ("Come Thou Fount", "Traditional", "G",
                 "https://www.youtube.com/results?search_query=come+thou+fount", ""),
            )


class SongIn(BaseModel):
    title: str
    artist: str = ""
    key: str = ""
    audio: str = ""
    chart: str = ""


@app.get("/api/songs")
def list_songs():
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT id, title, artist, key, audio, chart FROM songs ORDER BY title"
        ).fetchall()
        return rows


@app.post("/api/songs")
def create_song(song: SongIn):
    if not song.title.strip():
        raise HTTPException(400, "Title is required")
    with get_conn() as conn:
        row = conn.execute(
            """
            INSERT INTO songs (title, artist, key, audio, chart)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id, title, artist, key, audio, chart
            """,
            (song.title.strip(), song.artist.strip(), song.key.strip(),
             song.audio.strip(), song.chart.strip()),
        ).fetchone()
        return row


@app.put("/api/songs/{song_id}")
def update_song(song_id: int, song: SongIn):
    if not song.title.strip():
        raise HTTPException(400, "Title is required")
    with get_conn() as conn:
        row = conn.execute(
            """
            UPDATE songs SET title=%s, artist=%s, key=%s, audio=%s, chart=%s
            WHERE id=%s
            RETURNING id, title, artist, key, audio, chart
            """,
            (song.title.strip(), song.artist.strip(), song.key.strip(),
             song.audio.strip(), song.chart.strip(), song_id),
        ).fetchone()
        if not row:
            raise HTTPException(404, "Song not found")
        return row


@app.delete("/api/songs/{song_id}")
def delete_song(song_id: int):
    with get_conn() as conn:
        row = conn.execute(
            "DELETE FROM songs WHERE id=%s RETURNING id", (song_id,)
        ).fetchone()
        if not row:
            raise HTTPException(404, "Song not found")
        return {"status": "deleted"}


# ── Song info auto-fill (audio / chart / key lookup) ─────────────────────────
def _youtube_search(query: str) -> str:
    if not YOUTUBE_API_KEY:
        return ""
    try:
        resp = requests.get(
            "https://www.googleapis.com/youtube/v3/search",
            params={
                "part": "snippet",
                "q": query,
                "type": "video",
                "maxResults": 1,
                "key": YOUTUBE_API_KEY,
            },
            timeout=5,
        )
        items = resp.json().get("items", [])
        if items:
            video_id = items[0]["id"]["videoId"]
            return f"https://www.youtube.com/watch?v={video_id}"
    except Exception:
        pass
    return ""


def _genius_search(query: str) -> str:
    if not GENIUS_API_KEY:
        return ""
    try:
        resp = requests.get(
            "https://api.genius.com/search",
            params={"q": query},
            headers={"Authorization": f"Bearer {GENIUS_API_KEY}"},
            timeout=5,
        )
        hits = resp.json().get("response", {}).get("hits", [])
        if hits:
            return hits[0]["result"]["url"]
    except Exception:
        pass
    return ""


def _getsongbpm_key(title: str, artist: str) -> str:
    if not GETSONGBPM_API_KEY:
        return ""
    try:
        lookup = f"song:{title}"
        if artist:
            lookup += f" artist:{artist}"
        resp = requests.get(
            "https://api.getsongbpm.com/search/",
            params={
                "api_key": GETSONGBPM_API_KEY,
                "type": "song",
                "lookup": lookup,
                "limit": 1,
            },
            timeout=5,
        )
        results = resp.json().get("search", [])
        if results and isinstance(results, list):
            return results[0].get("key_of", "") or ""
    except Exception:
        pass
    return ""


def _fallback_links(title: str, artist: str) -> dict:
    query = f"{title} {artist}".strip()
    return {
        "audio": f"https://www.youtube.com/results?search_query={urllib.parse.quote_plus(query)}",
        "chart": f"https://www.google.com/search?q={urllib.parse.quote_plus(query + ' chords')}",
    }


@app.get("/api/lookup")
def lookup_song(title: str, artist: str = ""):
    title = title.strip()
    artist = artist.strip()
    if not title:
        raise HTTPException(400, "Title is required")

    query = f"{title} {artist}".strip()
    fallback = _fallback_links(title, artist)

    audio = _youtube_search(query) or fallback["audio"]
    chart = _genius_search(query) or fallback["chart"]
    key = _getsongbpm_key(title, artist)

    return {
        "audio": audio,
        "chart": chart,
        "key": key,
        "sources": {
            "audio": "youtube" if YOUTUBE_API_KEY else "search",
            "chart": "genius" if GENIUS_API_KEY else "search",
            "key": "getsongbpm" if GETSONGBPM_API_KEY else "",
        },
    }


# ── Serve the frontend ───────────────────────────────────────────────────────
@app.get("/")
def index():
    return FileResponse(str(FRONTEND_DIR / "index.html"))
