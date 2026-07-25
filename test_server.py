import sqlite3

import server
from server import YearInReviewInput, listening_year_in_review


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
    lines = result.splitlines()
    assert len(lines) == 2
    assert lines[0].startswith("Burial")  # más minutos que Radiohead en 2019
    assert "Radiohead" in lines[1]
