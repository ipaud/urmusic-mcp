# urmusic-mcp

Un MCP personal sobre tu propio historial de Spotify. Corre 100% en tu
máquina — tu JSON nunca sale de tu disco, nunca se sube a ningún servidor.

## 1. Pide tu historial a Spotify

1. Ve a [privacy.spotify.com/es/account/privacy](https://www.spotify.com/es/account/privacy/)
2. Baja hasta "Descarga tus datos" y marca **"Historial de streaming extendido"**
   (no el básico — ese solo trae el último año)
3. Confirma por email. Spotify tarda entre unos días y unas semanas en
   mandarte un ZIP.
4. Descomprime el ZIP en una carpeta — dentro verás varios
   `Streaming_History_Audio_*.json`.

## 2. Instala

Necesitas [uv](https://docs.astral.sh/uv/):

```bash
git clone https://github.com/ipaud/urmusic-mcp
cd urmusic-mcp
uv sync
```

## 3. Genera tu base de datos local

```bash
uv run ingest.py ./ruta/a/la/carpeta/descomprimida
```

Esto crea `listening.db` en el proyecto. Está en `.gitignore` — nunca la
subas a ningún sitio, es tu historial personal.

## 4. Conéctalo a Claude

Con Claude Code:

```bash
claude mcp add musica -- uv run --directory /ruta/absoluta/a/urmusic-mcp server.py
```

Con Claude Desktop, añade a tu config MCP:

```json
{
  "mcpServers": {
    "musica": {
      "command": "uv",
      "args": ["run", "--directory", "/ruta/absoluta/a/urmusic-mcp", "server.py"]
    }
  }
}
```

Reinicia y pregunta algo como:
- "¿Qué artistas escuché con atención y dejé tirados hace 5 años?"
- "Top 10 por convicción, no por reproducciones"
- "Recomiéndame música nueva basada en mis semillas de más convicción"

## Qué hace cada tool

| Tool | Qué hace |
|---|---|
| `listening_schema` | Esquema de la base de datos |
| `listening_query` | SQL de solo lectura sobre tu historial |
| `listening_find_dormant` | Artistas escuchados con atención y abandonados hace X años |
| `listening_expand_artist` | Candidatos nuevos vía MusicBrainz (miembros, colaboradores, sello) |
| `listening_artist_profile` | Perfil completo de un artista: plays, convicción, rango temporal |
| `listening_year_in_review` | Top artistas de un año por minutos escuchados |

## Privacidad

- Nada de esto llama a ningún servidor tuyo ni de terceros excepto
  MusicBrainz (solo nombres de artista, para buscar relaciones — nunca tu
  historial).
- `listening.db` vive solo en el disco de quien lo genera.
- Si compartes este repo, comparte el código — nunca tu `.db`.

## Licencia

[MIT](LICENSE)
