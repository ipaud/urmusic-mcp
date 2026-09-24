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


def test_build_db_completion_rate_counts_skips_and_span_is_first_to_last(tmp_path):
    # Arrange: 3 escuchas reales separadas 2 años + 1 skip
    records = [
        {"master_metadata_album_artist_name": "Burial", "master_metadata_track_name": "Archangel",
         "master_metadata_album_album_name": "Untrue", "ts": "2010-01-01T00:00:00Z", "ms_played": 200_000},
        {"master_metadata_album_artist_name": "Burial", "master_metadata_track_name": "Near Dark",
         "master_metadata_album_album_name": "Untrue", "ts": "2011-01-01T00:00:00Z", "ms_played": 200_000},
        {"master_metadata_album_artist_name": "Burial", "master_metadata_track_name": "Etched Headplate",
         "master_metadata_album_album_name": "Untrue", "ts": "2012-01-01T00:00:00Z", "ms_played": 200_000},
        {"master_metadata_album_artist_name": "Burial", "master_metadata_track_name": "Ghost Hardware",
         "master_metadata_album_album_name": "Untrue", "ts": "2020-01-01T00:00:00Z", "ms_played": 3_000},
    ]
    db_path = tmp_path / "listening.db"

    # Act
    build_db(records, db_path)

    # Assert
    import sqlite3

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    artist = conn.execute("SELECT * FROM artists WHERE artist = 'Burial'").fetchone()
    conn.close()

    assert artist["plays"] == 3
    assert artist["tracks"] == 3  # el skip no cuenta como tema explorado
    assert artist["completion_rate"] == 0.75  # 3 de 4, el skip sí cuenta aquí
    assert abs(artist["span_years"] - 2.0) < 0.01  # 2010 -> 2012, ignora el skip de 2020


def test_build_db_excludes_artists_with_only_skips(tmp_path):
    records = [
        {"master_metadata_album_artist_name": "Skipped", "master_metadata_track_name": "t",
         "master_metadata_album_album_name": "a", "ts": "2015-01-01T00:00:00Z", "ms_played": 1_000},
    ]
    db_path = tmp_path / "listening.db"

    build_db(records, db_path)

    import sqlite3

    conn = sqlite3.connect(db_path)
    assert conn.execute("SELECT COUNT(*) FROM artists").fetchone()[0] == 0
    conn.close()
