import sqlite3

import server
from server import TopAlbumsInput, YearInReviewInput, listening_top_albums, listening_year_in_review


def test_year_in_review_filters_by_year_and_sorts_by_minutes(tmp_path, monkeypatch):
    # Arrange
    db_path = tmp_path / "listening.db"
    conn = sqlite3.connect(db_path)
    conn.execute(
        "CREATE TABLE plays (artist TEXT, track TEXT, album TEXT, date TEXT, "
        "minutes REAL, substantial INTEGER)"
    )
    conn.executemany(
        "INSERT INTO plays (artist, track, album, date, minutes, substantial) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        [
            ("Burial", "Archangel", "Untrue", "2019-03-02T00:00:00Z", 4.5, 1),
            ("Radiohead", "Idioteque", "Kid A", "2019-03-01T00:00:00Z", 4.0, 1),
            ("Radiohead", "Airbag", "OK Computer", "2018-01-01T00:00:00Z", 5.0, 1),
        ],
    )
    conn.commit()
    conn.close()
    monkeypatch.setattr(server, "DB_PATH", db_path)

    # Act
    result = listening_year_in_review(YearInReviewInput(year=2019))

    # Assert
    assert len(result) == 1  # with_art=False -> solo el bloque de texto
    lines = result[0].splitlines()
    assert len(lines) == 2
    assert lines[0].startswith("Burial")  # más minutos que Radiohead en 2019
    assert "Radiohead" in lines[1]


def test_top_albums_groups_by_album_and_sorts_by_plays(tmp_path, monkeypatch):
    # Arrange
    db_path = tmp_path / "listening.db"
    conn = sqlite3.connect(db_path)
    conn.execute(
        "CREATE TABLE plays (artist TEXT, track TEXT, album TEXT, date TEXT, "
        "minutes REAL, substantial INTEGER)"
    )
    conn.executemany(
        "INSERT INTO plays (artist, track, album, date, minutes, substantial) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        [
            ("Mad Caddies", "t1", "Dirty Rice", "2019-01-01T00:00:00Z", 3.0, 1),
            ("Mad Caddies", "t2", "Dirty Rice", "2019-01-02T00:00:00Z", 3.0, 1),
            ("Manolo García", "t3", "Arena En Los Bolsillos", "2018-01-01T00:00:00Z", 4.0, 1),
        ],
    )
    conn.commit()
    conn.close()
    monkeypatch.setattr(server, "DB_PATH", db_path)

    # Act
    result = listening_top_albums(TopAlbumsInput())

    # Assert
    assert len(result) == 1  # with_art=False -> solo texto
    lines = result[0].splitlines()
    assert lines[0].startswith("Dirty Rice")  # 2 plays > 1 play
    assert "Arena En Los Bolsillos" in lines[1]


def test_cover_art_returns_none_when_no_release_group_matches(monkeypatch):
    monkeypatch.setattr(server, "_mb_throttle", lambda: None)
    monkeypatch.setattr(
        server.musicbrainzngs,
        "search_release_groups",
        lambda **kwargs: {"release-group-list": []},
    )

    assert server._cover_art("Artista Inexistente") is None


def test_cover_art_detects_png_vs_default_jpeg(monkeypatch):
    monkeypatch.setattr(server, "_mb_throttle", lambda: None)
    monkeypatch.setattr(
        server.musicbrainzngs,
        "search_release_groups",
        lambda **kwargs: {"release-group-list": [{"id": "rg-123"}]},
    )
    monkeypatch.setattr(
        server.musicbrainzngs,
        "get_release_group_image_front",
        lambda rgid, size=None: b"\x89PNG\r\n\x1a\n" + b"resto-de-bytes",
    )

    art = server._cover_art("Radiohead", "Kid A")

    assert art is not None
    assert art._mime_type == "image/png"
