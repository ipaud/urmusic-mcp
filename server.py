"""
Servidor MCP personal sobre el historial de Spotify.
Envuelve taste.py / discover.py como tools invocables desde Claude.

Ejecutar:
  uv run server.py
o registrar en Claude Code:
  claude mcp add musica -- uv run --directory /ruta/a/musica-mcp server.py
"""

import sqlite3
import time
from pathlib import Path
from typing import Optional

import musicbrainzngs
from mcp.server.fastmcp import FastMCP, Image
from pydantic import BaseModel, Field

DB_PATH = Path(__file__).parent / "listening.db"  # ajusta a tu ruta real
mcp = FastMCP("musica-personal")

musicbrainzngs.set_useragent(
    "urmusic-mcp", "1.0", "https://github.com/ipaud/urmusic-mcp"
)
_last_mb_call = 0.0


def _mb_throttle():
    """MusicBrainz exige 1 req/seg. Sin esto te banean la IP."""
    global _last_mb_call
    elapsed = time.monotonic() - _last_mb_call
    if elapsed < 1.05:
        time.sleep(1.05 - elapsed)
    _last_mb_call = time.monotonic()


def _db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _cover_art(artist: str, album: Optional[str] = None) -> Optional[Image]:
    """Busca la carátula de un álbum (o la más relevante del artista si no se
    da álbum) vía MusicBrainz + Cover Art Archive. None si no hay match o
    el release-group no tiene carátula subida."""
    _mb_throttle()
    try:
        if album:
            search = musicbrainzngs.search_release_groups(artist=artist, releasegroup=album, limit=1)
        else:
            search = musicbrainzngs.search_release_groups(artist=artist, limit=1)
    except musicbrainzngs.MusicBrainzError:
        return None
    groups = search.get("release-group-list", [])
    if not groups:
        return None
    _mb_throttle()
    try:
        data = musicbrainzngs.get_release_group_image_front(groups[0]["id"], size=250)
    except musicbrainzngs.MusicBrainzError:
        return None
    fmt = "png" if data[:8] == b"\x89PNG\r\n\x1a\n" else "jpeg"
    return Image(data=data, format=fmt)


# ---------- Tools de exploración directa ----------

@mcp.tool()
def listening_schema() -> str:
    """Devuelve el esquema de la base de datos (tablas y columnas).
    Llama esto primero si vas a escribir SQL a mano con listening_query."""
    conn = _db()
    rows = conn.execute(
        "SELECT name, sql FROM sqlite_master WHERE type='table'"
    ).fetchall()
    conn.close()
    return "\n\n".join(f"-- {r['name']}\n{r['sql']}" for r in rows)


class QueryInput(BaseModel):
    sql: str = Field(
        description="Consulta SQL de solo lectura (SELECT). "
        "Usa listening_schema antes si no conoces las columnas."
    )


@mcp.tool()
def listening_query(params: QueryInput) -> str:
    """Ejecuta una consulta SQL de solo lectura contra el historial de escucha.
    Rechaza cualquier cosa que no empiece por SELECT."""
    sql = params.sql.strip()
    if not sql.lower().startswith("select"):
        return "Error: solo se permiten consultas SELECT."
    conn = _db()
    try:
        rows = conn.execute(sql).fetchall()
    except sqlite3.Error as e:
        return f"Error SQL: {e}. Revisa el esquema con listening_schema."
    finally:
        conn.close()
    if not rows:
        return "Sin resultados."
    cols = rows[0].keys()
    lines = [" | ".join(cols)]
    lines += [" | ".join(str(r[c]) for c in cols) for r in rows[:200]]
    return "\n".join(lines)


# ---------- Tools de descubrimiento (discover.py) ----------

class DormantInput(BaseModel):
    limit: int = Field(default=20, description="Número máximo de artistas a devolver")
    min_dormant_years: float = Field(
        default=5.0, description="Años mínimos desde la última escucha"
    )
    with_art: bool = Field(
        default=True,
        description="Incluir carátula por artista (2 llamadas a MusicBrainz "
        "por artista a 1 req/seg). Pon False para respuesta rápida sin imágenes.",
    )


@mcp.tool(structured_output=False)
def listening_find_dormant(params: DormantInput) -> list:
    """Encuentra artistas escuchados con atención (alta finalización, varios temas)
    y luego abandonados hace X años. El lead clásico de 'lo probé, me gustó, corté el hábito'."""
    conn = _db()
    rows = conn.execute(
        """
        SELECT artist, tracks, completion_rate, years_since_last
        FROM artists
        WHERE years_since_last >= ?
          AND completion_rate >= 0.85
          AND tracks >= 5
        ORDER BY completion_rate * tracks DESC
        LIMIT ?
        """,
        (params.min_dormant_years, params.limit),
    ).fetchall()
    conn.close()
    if not rows:
        return ["Sin candidatos con esos criterios."]
    text = "\n".join(
        f"{r['artist']} — {r['tracks']} temas, {r['completion_rate']*100:.0f}% completado, "
        f"dormido {r['years_since_last']:.1f} años"
        for r in rows
    )
    content: list = [text]
    if params.with_art:
        for r in rows:
            art = _cover_art(r["artist"])
            if art:
                content.append(art)
    return content


class ExpandInput(BaseModel):
    artist: str = Field(description="Nombre exacto del artista semilla")
    include_labels: bool = Field(
        default=False,
        description="True = incluye compañeros de sello (más candidatos, menos precisión). "
        "False = solo vínculos directos de membresía/colaboración.",
    )
    with_art: bool = Field(
        default=True,
        description="Incluir carátula por candidato (2 llamadas a MusicBrainz "
        "por candidato a 1 req/seg). Pon False para respuesta rápida sin imágenes.",
    )


@mcp.tool(structured_output=False)
def listening_expand_artist(params: ExpandInput) -> list:
    """Expande un artista semilla vía MusicBrainz: miembros, colaboradores y,
    opcionalmente, compañeros de sello. Para encontrar música nueva conectada
    a lo que ya te ha convencido, no solo lo que el algoritmo de Spotify sugiere."""
    _mb_throttle()
    try:
        search = musicbrainzngs.search_artists(artist=params.artist, limit=1)
    except musicbrainzngs.MusicBrainzError as e:
        return [f"Error MusicBrainz: {e}"]
    matches = search.get("artist-list", [])
    if not matches or matches[0]["name"].lower() != params.artist.lower():
        return [f"'{params.artist}' no tiene coincidencia exacta en MusicBrainz."]

    mbid = matches[0]["id"]
    _mb_throttle()
    rels = musicbrainzngs.get_artist_by_id(
        mbid, includes=["artist-rels"] + (["label-rels"] if params.include_labels else [])
    )
    names = []
    lines = []
    for rel in rels["artist"].get("artist-relation-list", []):
        target = rel.get("artist", {}).get("name")
        if target:
            names.append(target)
            lines.append(f"{target} — {rel.get('type', 'relacionado')} con {params.artist}")
    if not lines:
        return [f"Sin candidatos por relación directa para '{params.artist}'."]
    content: list = ["\n".join(lines)]
    if params.with_art:
        for name in names:
            art = _cover_art(name)
            if art:
                content.append(art)
    return content


class ProfileInput(BaseModel):
    artist: str


@mcp.tool(structured_output=False)
def listening_artist_profile(params: ProfileInput) -> list:
    """Perfil de escucha completo de un artista: plays, minutos, temas distintos,
    álbumes explorados, rango temporal, score de convicción y carátula del
    álbum más escuchado."""
    conn = _db()
    row = conn.execute(
        "SELECT * FROM artists WHERE artist = ?", (params.artist,)
    ).fetchone()
    if not row:
        conn.close()
        return [f"Sin datos para '{params.artist}'."]
    top_album = conn.execute(
        "SELECT album FROM plays WHERE artist = ? AND album IS NOT NULL "
        "GROUP BY album ORDER BY SUM(minutes) DESC LIMIT 1",
        (params.artist,),
    ).fetchone()
    conn.close()
    content: list = ["\n".join(f"{k}: {row[k]}" for k in row.keys())]
    if top_album:
        art = _cover_art(params.artist, top_album["album"])
        if art:
            content.append(art)
    return content


class YearInReviewInput(BaseModel):
    year: int = Field(description="Año a analizar, ej. 2019")
    limit: int = Field(default=15, description="Número máximo de artistas a devolver")
    with_art: bool = Field(
        default=True,
        description="Incluir carátula por artista (2 llamadas a MusicBrainz "
        "por artista a 1 req/seg). Pon False para respuesta rápida sin imágenes.",
    )


@mcp.tool(structured_output=False)
def listening_year_in_review(params: YearInReviewInput) -> list:
    """Top artistas de un año concreto por minutos escuchados, con temas distintos.
    Para ver qué dominó tu año o comparar la evolución entre años."""
    conn = _db()
    rows = conn.execute(
        """
        SELECT artist,
               COUNT(*) AS plays,
               ROUND(SUM(minutes), 1) AS minutes,
               COUNT(DISTINCT track) AS tracks
        FROM plays
        WHERE substantial = 1
          AND strftime('%Y', date) = ?
        GROUP BY artist
        ORDER BY minutes DESC
        LIMIT ?
        """,
        (str(params.year), params.limit),
    ).fetchall()
    conn.close()
    if not rows:
        return [f"Sin datos para {params.year}."]
    text = "\n".join(
        f"{r['artist']} — {r['minutes']} min, {r['plays']} plays, {r['tracks']} temas distintos"
        for r in rows
    )
    content: list = [text]
    if params.with_art:
        for r in rows:
            art = _cover_art(r["artist"])
            if art:
                content.append(art)
    return content


class TopAlbumsInput(BaseModel):
    limit: int = Field(default=15, description="Número máximo de álbumes a devolver")
    with_art: bool = Field(
        default=True,
        description="Incluir carátula por álbum (2 llamadas a MusicBrainz por "
        "álbum a 1 req/seg). Pon False para respuesta rápida sin imágenes.",
    )


@mcp.tool(structured_output=False)
def listening_top_albums(params: TopAlbumsInput) -> list:
    """Top álbumes por número de reproducciones, con minutos totales.
    Para responder 'qué disco he escuchado más', a diferencia de
    listening_year_in_review que agrupa por artista."""
    conn = _db()
    rows = conn.execute(
        """
        SELECT artist, album,
               COUNT(*) AS plays,
               ROUND(SUM(minutes), 1) AS minutes
        FROM plays
        WHERE substantial = 1 AND album IS NOT NULL
        GROUP BY artist, album
        ORDER BY plays DESC
        LIMIT ?
        """,
        (params.limit,),
    ).fetchall()
    conn.close()
    if not rows:
        return ["Sin datos de álbumes."]
    text = "\n".join(
        f"{r['album']} — {r['artist']} — {r['plays']} plays, {r['minutes']} min"
        for r in rows
    )
    content: list = [text]
    if params.with_art:
        for r in rows:
            art = _cover_art(r["artist"], r["album"])
            if art:
                content.append(art)
    return content


if __name__ == "__main__":
    mcp.run(transport="stdio")
