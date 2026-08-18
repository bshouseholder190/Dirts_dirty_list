"""FastAPI backend for the For Dirt song list."""
import os
from pathlib import Path

import psycopg
from psycopg.rows import dict_row
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel

DATABASE_URL = os.environ["DATABASE_URL"]
FRONTEND_DIR = Path(__file__).parent

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


# ── Serve the frontend ───────────────────────────────────────────────────────
@app.get("/")
def index():
    return FileResponse(str(FRONTEND_DIR / "index.html"))
