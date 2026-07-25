import json
from pathlib import Path

from ingest import build_db, load_records


def test_build_db_aggregates_plays_into_artist_stats(tmp_path):
    # Arrange
    export_dir = tmp_path / "export"
    export_dir.mkdir()
    records = [
        {
            "master_metadata_album_artist_name": "Radiohead",
            "master_metadata_track_name": "Idioteque",
            "master_metadata_album_album_name": "Kid A",
            "ts": "2015-01-01T00:00:00Z",
            "ms_played": 240_000,
        },
        {
            "master_metadata_album_artist_name": "Radiohead",
            "master_metadata_track_name": "Idioteque",
            "master_metadata_album_album_name": "Kid A",
            "ts": "2015-01-02T00:00:00Z",
            "ms_played": 5_000,  # below substantial threshold, excluded from artists table
        },
    ]
    (export_dir / "Streaming_History_Audio_0.json").write_text(json.dumps(records))

    db_path = tmp_path / "listening.db"

    # Act
    loaded = list(load_records(export_dir))
    build_db(loaded, db_path)

    # Assert
    import sqlite3

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    plays = conn.execute("SELECT * FROM plays").fetchall()
    artist = conn.execute("SELECT * FROM artists WHERE artist = 'Radiohead'").fetchone()
    conn.close()

    assert len(plays) == 2
    assert artist["plays"] == 1  # only the substantial play counts
    assert artist["tracks"] == 1
