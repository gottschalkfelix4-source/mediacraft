# Architektur

MediaCraft ist ein einzelner Prozess, der Filme und Serien gemeinsam verwaltet. Backend, Weboberfläche und
Hintergrundaufgaben laufen im selben Container; die Daten liegen in einer SQLite-Datenbank unter `/config`.

```
┌──────────────────────── Docker-Container (python:3.12-slim) ───────────────────────┐
│  Uvicorn / FastAPI                                                                 │
│  ├── /api/v1/*          eigene REST-API (API-Key oder Session)                     │
│  ├── /sonarr/api/v3/*   Sonarr-kompatible Teilmenge                                │
│  ├── /radarr/api/v3/*   Radarr-kompatible Teilmenge                                │
│  ├── /api/v1/feed/calendar.ics?apikey=…  iCal-Feed                                 │
│  └── /                  React-Oberfläche (statisch, im Image gebaut)               │
│                                                                                    │
│  Services:  Bibliothek · Suche/Entscheidung · Grab · Warteschlange/Import · RSS    │
│  Scheduler: Downloads prüfen, RSS-Sync, Indexer-Limits, Metadaten, Fehlende        │
│             suchen, Health-Check, Disk-Scan, Import-Listen, Backup, Aufräumen      │
│  Adapter:   metadata/* · indexers/* · downloadclients/* · notifications            │
│  SQLite (WAL) in /config/mediacraft.db                                             │
└────────────────────────────────────────────────────────────────────────────────────┘
        │ /config                │ /data (torrents, usenet, media → Hardlinks möglich)
```

## Funktionsvergleich mit Sonarr und Radarr

| Bereich | Sonarr / Radarr | MediaCraft |
|---|---|---|
| Bibliothek | getrennte Anwendungen für Serien und Filme | Filme **und** Serien in einer Datenbank mit gemeinsamen Root-Foldern, Tags und Profilen |
| Metadaten | Sonarr: TVDB, Radarr: TMDB | mehrere Provider gleichzeitig (TMDB, TheTVDB v4, TVmaze, OMDb, AniList) mit Reihenfolge, Fallback, Feld-Merge und ID-Abgleich |
| Qualität | Qualitätsdefinitionen, Profile, Cutoff, Upgrades | eigene Qualitätstabelle (SDTV bis Remux-2160p), Profile mit Reihenfolge, Cutoff, Upgrades, MB-pro-Minute-Grenzen |
| Custom Formats | Bedingungen mit Punktwertung | Bedingungen auf Titel-Regex, Gruppe, Quelle, Auflösung, Sprache, Codec und Größe (negierbar, Pflicht), Mindest- und Cutoff-Score |
| Sprachen | Radarr: Profilsprache, Sonarr v4: über Custom Formats | Profilsprachen inklusive Erkennung von „German DL“ und „ML“, Prüfung der echten Tonspuren per Mediainfo |
| Indexer | Newznab/Torznab, RSS, automatische und interaktive Suche | Newznab/Torznab mit Caps-Erkennung, ID-Suche (imdb/tmdb/tvdb), RSS-Sync, Prioritäten |
| Indexer-Limits | nur rudimentär in Prowlarr | Query- und Grab-Limits je Indexer, rollierend oder mit festem Reset, Reserve, Mindestabstand, Abgleich mit `newznab:apilimits`, automatisches Pausieren, Prognose |
| Downloadclients | qBittorrent, Transmission, Deluge, SABnzbd, NZBGet, Blackhole u. a. | qBittorrent, Transmission, Deluge, SABnzbd, NZBGet, Blackhole (Torrent/NZB) |
| Download-Handling | Überwachung, Import, Hardlink/Kopie, Umbenennen | zusätzlich Entpacken, Mediainfo-Prüfung, Papierkorb für ersetzte Dateien |
| API | REST v3 | eigene REST-API `/api/v1` und Kompatibilitätsschicht `/sonarr/api/v3` und `/radarr/api/v3` |

## Indexer-Limits

Weil Filme und Serien im selben Prozess laufen, teilen sie sich **einen** Zähler pro Indexer. Überträgt Prowlarr
denselben Indexer an die „Sonarr“- und die „Radarr“-Schnittstelle, wird er anhand von URL und API-Key zu einem
Datensatz mit TV- und Film-Kategorien zusammengeführt.

- Jede Anfrage (`query`, `rss`, `caps`) und jeder Download einer NZB- oder Torrent-Datei (`grab`) wird als Ereignis
  mit Zeitstempel gespeichert.
- Pro Indexer einstellbar: `query_limit`, `grab_limit`, `limit_window_hours`, `limit_mode` (`rolling` oder `fixed`),
  `limit_reset_hour` (bei `fixed`), `grab_reserve` (nur für manuelle Grabs) und `min_request_interval` in Sekunden.
- **Rollierend:** Verbrauch = Ereignisse im Zeitraum `[jetzt − Fenster, jetzt]`; der nächste freie Slot ergibt sich
  aus dem ältesten Ereignis im Fenster plus Fensterlänge.
- Liefert der Indexer `newznab:apilimits`, gilt der höhere Wert aus eigener Zählung und dem gemeldeten Wert plus
  den eigenen Zugriffen seit dieser Meldung. So zählen auch Zugriffe anderer Tools oder der Website mit.
- Fehlercodes 500 (Request-Limit), 501 (Download-Limit) und HTTP 429 pausieren den Indexer bis zum nächsten freien
  Slot; andere Fehler führen zu exponentiellem Backoff.
- Automatische Suchen und RSS überspringen erschöpfte Indexer. Interaktive Grabs zeigen eine Warnung und dürfen
  die Reserve nutzen.

## Metadaten

- Pro Medientyp gibt es eine Provider-Reihenfolge, z. B. Serien: TheTVDB → TMDB → TVmaze, Filme: TMDB → OMDb.
  Der erste verfügbare Provider liefert die Struktur (z. B. die Episodenliste), die übrigen ergänzen fehlende
  Felder wie Übersetzungen, Poster, IDs, Bewertungen und Alternativtitel.
- Die Suche fragt alle aktiven Provider parallel ab und entfernt Duplikate über gemeinsame IDs.
- Ein Antwort-Cache in der Datenbank schont die API-Kontingente.
- Ohne API-Keys funktionieren TVmaze (Serien) und AniList (Anime) sofort.

## Projektstruktur

```
backend/app/
  main.py, config.py, db.py, models.py
  core/             parser, qualities, customformats, decision, naming, mediainfo, scheduler,
                    settings, migrations, events, seed, bencode
  metadata/         base, tmdb, tvdb, tvmaze, omdb, anilist, manager
  indexers/         newznab, usage
  downloadclients/  base, torrent, usenet, manager
  services/         library, search, grab, queue, importer, unpack, rss, delay, importlists,
                    notifications, backup, recycle, maintenance, commands, updates
  api/
    routes/         media, lists, config, stats, system
    compat/         Sonarr-/Radarr-Kompatibilität (sonarr, radarr, resources, arrconfig)
backend/tests/      pytest
frontend/src/       React + Vite (pages, components, types)
docker/             entrypoint.sh (PUID/PGID/UMASK)
unraid/             Template und Icon
```

## Integration in einen bestehenden Mediastack

- Gleiche `/data`-Struktur wie in den TRaSH-Guides empfohlen, damit Hardlinks statt Kopien möglich sind.
- Container ins bestehende Docker-Netz hängen (`networks: … external: true`).
- Jellyseerr/Overseerr: Radarr-Server `mediacraft:7979` mit URL-Base `/radarr`, Sonarr-Server `mediacraft:7979`
  mit URL-Base `/sonarr`, jeweils mit demselben API-Key.
- Prowlarr: Apps „Sonarr“ (`http://mediacraft:7979/sonarr`) und „Radarr“ (`http://mediacraft:7979/radarr`)
  anlegen; die Indexer werden automatisch synchronisiert.
- Jellyfin/Emby/Plex: Benachrichtigung „Library-Refresh“ nach jedem Import.
