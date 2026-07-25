"""
Convierte el Extended Streaming History de Spotify (JSON) en la misma
listening.db que usa server.py. Corre 100% en local — el JSON de nadie
sale de su máquina.

Uso:
  uv run ingest.py ./carpeta_con_los_json
"""

import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

MIN_MS_SUBSTANTIAL = 30_000  # umbral de "escucha real" vs skip


def load_records(folder: Path):
    for f in sorted(folder.glob("Streaming_History_Audio*.json")):
        yield from json.loads(f.read_text(encoding="utf-8"))
    # algunos exports antiguos usan StreamingHistory*.json sin "Audio"
    for f in sorted(folder.glob("StreamingHistory*.json")):
        yield from json.loads(f.read_text(encoding="utf-8"))


def build_db(records, db_path: Path):
    if db_path.exists():
        db_path.unlink()
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE plays (
            artist TEXT NOT NULL,
            track TEXT,
            album TEXT,
            date TEXT NOT NULL,
            minutes REAL NOT NULL,
            substantial INTEGER NOT NULL
        )
        """
    )

    rows = []
    for r in records:
        artist = r.get("master_metadata_album_artist_name") or r.get("artistName")
        track = r.get("master_metadata_track_name") or r.get("trackName")
        album = r.get("master_metadata_album_album_name")
        ts = r.get("ts") or r.get("endTime")
        ms = r.get("ms_played") if "ms_played" in r else r.get("msPlayed")
        if not artist or not ts or ms is None:
            continue
        date = ts if "T" in ts else ts.replace(" ", "T") + ":00Z"
        rows.append(
            (
                artist,
                track,
                album,
                date,
                round(ms / 60000, 3),
                1 if ms >= MIN_MS_SUBSTANTIAL else 0,
            )
        )

    conn.executemany(
        "INSERT INTO plays (artist, track, album, date, minutes, substantial) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        rows,
    )
    conn.commit()

    # Tabla agregada por artista — AJUSTA la fórmula de conviction a la
    # que ya usa tu taste.py si difiere de esta.
    conn.execute(
        """
        CREATE TABLE artists AS
        SELECT
            artist,
            COUNT(*) AS plays,
            SUM(minutes) AS minutes,
            COUNT(DISTINCT track) AS tracks,
            COUNT(DISTINCT album) AS albums,
            (julianday('now') - julianday(MIN(date))) / 365.25 AS span_years,
            (julianday('now') - julianday(MAX(date))) / 365.25 AS years_since_last,
            AVG(substantial) AS completion_rate,
            -- conviction: pondera profundidad de catálogo + fidelidad temporal, no volumen bruto
            (COUNT(DISTINCT track) * 1.0)
                + (COUNT(DISTINCT album) * 2.0)
                + ((julianday('now') - julianday(MIN(date))) / 365.25)
                + (AVG(substantial) * 20)
                AS conviction
        FROM plays
        WHERE substantial = 1
        GROUP BY artist
        """
    )
    conn.commit()
    conn.close()


def main():
    if len(sys.argv) != 2:
        print("Uso: uv run ingest.py ./carpeta_con_los_json")
        sys.exit(1)

    folder = Path(sys.argv[1])
    if not folder.is_dir():
        print(f"'{folder}' no es una carpeta válida.")
        sys.exit(1)

    records = list(load_records(folder))
    if not records:
        print(
            "No se encontraron archivos Streaming_History_Audio*.json ni "
            "StreamingHistory*.json en esa carpeta."
        )
        sys.exit(1)

    db_path = Path(__file__).parent / "listening.db"
    build_db(records, db_path)
    print(f"{len(records)} reproducciones procesadas -> {db_path}")


if __name__ == "__main__":
    main()
