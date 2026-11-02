# MediaCraft – Architektur & Plan

MediaCraft ist ein vollständig eigenständig entwickelter All-in-One-Medienmanager, der die
Funktionen von Sonarr (Serien) und Radarr (Filme) in **einem** Docker-Container vereint.
Kein Code aus Sonarr/Radarr wird verwendet – alles (Release-Parser, Entscheidungs-Engine,
Indexer-, Downloadclient- und Metadaten-Anbindungen, UI) ist neu geschrieben.

## 1. Recherche: Funktionsumfang von Sonarr/Radarr → MediaCraft

| Bereich | Sonarr / Radarr | MediaCraft |
|---|---|---|
| Bibliothek | Serien (Staffeln/Episoden) bzw. Filme, Monitoring, Root-Folder, Tags | Filme **und** Serien in einer DB, gemeinsame Root-Folder/Tags/Profile |
| Metadaten | Sonarr: TVDB (über SkyHook), Radarr: TMDB (über eigene API) | **Mehrere Provider gleichzeitig**: TMDB, TVDB v4, TVmaze (ohne Key), OMDb, AniList; Prioritäten, Fallback, Feld-Merge, ID-Cross-Mapping (tvdb/tmdb/imdb/tvmaze/anilist) |
| Qualität | Quality-Definitionen, Profile, Cutoff, Upgrades, Größenlimits | Eigene Quality-Tabelle (SDTV…Remux-2160p), Profile mit Reihenfolge, Cutoff, Upgrade, MB/Minute-Limits |
| Custom Formats | Regex/Quelle/Auflösung/Sprache/Gruppe mit Score | Eigene CF-Engine (Bedingungen: Titel-Regex, Gruppe, Quelle, Auflösung, Sprache, Codec, Größe; Negate/Required), Score pro Profil, Min-Score & Cutoff-Score |
| Sprachen | Radarr: Profil-Sprache; Sonarr v4: CF-basiert | Profil-Sprache(n) inkl. „German DL“/„ML“-Erkennung |
| Indexer | Newznab/Torznab, RSS, Auto-/Interaktive Suche, Prioritäten | Newznab/Torznab-Client, Caps-Erkennung, ID-Suche (imdb/tmdb/tvdb), RSS-Sync, Priorität |
| **Indexer-Limits** | nur in Prowlarr rudimentär (Query/Grab-Limit) | **Usage-Tracking**: Query- & Grab-Limits je Indexer, *rollierendes* Fenster (z. B. TreasureMaps: 400 Grabs / 24 h rolling) oder fester Reset-Zeitpunkt, Reserve für manuelle Grabs, Mindestabstand zwischen Requests, Abgleich mit `newznab:apilimits` der Indexer-Antwort, Fehlercodes 500/501/429 → automatisches Pausieren, Prognose „nächster freier Slot“, Stundenhistogramm |
| Downloadclients | qBittorrent, Transmission, Deluge, SABnzbd, NZBGet, Blackhole … | qBittorrent, Transmission, Deluge, SABnzbd, NZBGet, Blackhole (Torrent/NZB) |
| Completed Download Handling | Queue-Überwachung, Import, Hardlink/Copy, Umbenennen | Queue-Tracking, Remote-Path-Mappings, Hardlink→Copy-Fallback, Sample-Erkennung, Umbenennen, Upgrade (alte Datei → Papierkorb) |
| Fehlgeschlagene Downloads | Blocklist + Neusuche | Blocklist + automatische Neusuche |
| Wanted | Missing / Cutoff Unmet | beide, Massen-Suche (limit-bewusst) |
| Kalender | ja, iCal | ja + iCal-Feed |
| Bibliotheksimport | Ordner scannen und zuordnen | Root-Folder-Scan, Ordnername-Parsing, Vorschläge über alle Provider |
| Benachrichtigungen | viele | Webhook, Discord, Gotify, ntfy, Telegram, Jellyfin/Emby- & Plex-Library-Refresh |
| API | v3 REST | eigene REST-API `/api/v1` **+ Kompatibilitätsschicht** `/sonarr/api/v3` & `/radarr/api/v3` für Jellyseerr/Overseerr, Prowlarr (Indexer-Sync), Homepage-Widgets |

## 2. Architektur

```
┌──────────────────────── Docker-Container (python:3.12-slim) ───────────────────────┐
│  Uvicorn / FastAPI                                                                 │
│  ├── /api/v1/*          eigene REST-API (API-Key oder Session)                     │
│  ├── /sonarr/api/v3/*   Sonarr-kompatible Teilmenge                                │
│  ├── /radarr/api/v3/*   Radarr-kompatible Teilmenge                                │
│  ├── /api/v1/feed/calendar.ics?apikey=…  iCal                                      │
│  └── /                  React-SPA (statisch, im Image gebaut)                      │
│                                                                                    │
│  Services: Library · Search/Decision · Grab · Queue/Import · RSS · DiskScan        │
│  Scheduler (Threads): RSS-Sync, Downloads prüfen, Metadaten-Refresh, Health,       │
│                       Housekeeping, Wanted-Suche (optional)                         │
│  Adapter: metadata/* · indexers/* · downloadclients/* · notifications              │
│  SQLite (WAL) in /config/mediacraft.db                                             │
└────────────────────────────────────────────────────────────────────────────────────┘
        │ /config           │ /data (torrents, usenet, media → Hardlinks möglich)
```

### Gemeinsame Indexer-Basis
Weil Filme und Serien im selben Prozess laufen, teilen sie sich **einen** Limit-Zähler pro
Indexer. Pushen Prowlarr-„Sonarr“- und „Radarr“-Apps denselben Indexer, wird er anhand
URL+API-Key zusammengeführt (TV- und Film-Kategorien im selben Datensatz).

### Indexer-Usage-Tracking (Kernfeature)
* Jede Anfrage (`query`, `rss`, `caps`) und jeder Download einer NZB/Torrent-Datei (`grab`)
  wird als Event mit Zeitstempel gespeichert.
* Pro Indexer konfigurierbar: `query_limit`, `grab_limit`, `limit_window_hours`,
  `limit_mode` (`rolling` | `fixed`), `limit_reset_hour` (bei fixed), `grab_reserve`
  (Grabs, die nur manuell genutzt werden dürfen), `min_request_interval` (Sekunden).
* *Rolling*: verbraucht = Events in `[jetzt − Fenster, jetzt]`; nächster freier Slot =
  ältestes Event im Fenster + Fenster.
* Liefert der Indexer `newznab:apilimits`, werden die Remote-Zähler übernommen
  (`max(lokal, remote)`), damit auch Zugriffe anderer Tools (z. B. Handy-App) zählen.
* Fehlercodes 500 (Request limit), 501 (Download limit), HTTP 429 → Indexer bis zum
  nächsten freien Slot pausiert; sonstige Fehler → exponentielles Backoff.
* Automatische Suchen/RSS überspringen erschöpfte Indexer; interaktive Grabs zeigen
  Warnung und können die Reserve nutzen.

### Metadaten-Strategie
* Pro Medientyp eine Provider-Reihenfolge (z. B. Serien: TVDB → TMDB → TVmaze,
  Filme: TMDB → OMDb). Der erste verfügbare liefert die Struktur (Episodenliste),
  die übrigen füllen fehlende Felder (Übersetzung, Poster, IDs, Ratings, Alternativtitel).
* Suche fragt alle aktiven Provider parallel ab und dedupliziert über Cross-IDs.
* Antwort-Cache in der DB (TTL) schont API-Kontingente.
* Ohne API-Keys funktionieren TVmaze (Serien) und AniList (Anime) sofort.

## 3. Projektstruktur

```
backend/app/
  main.py, config.py, db.py, models.py
  core/        qualities, parser, languages, customformats, naming, decision, bencode, scheduler, logbuffer
  metadata/    base, tmdb, tvdb, tvmaze, omdb, anilist, manager
  indexers/    newznab, usage
  downloadclients/ base, qbittorrent, transmission, deluge, sabnzbd, nzbget, blackhole
  services/    library, search, grab, queue, importer, diskscan, libraryimport, rss, health, notifications
  api/         deps, routes/*, compat
frontend/      React + Vite SPA
Dockerfile, docker-compose.yml, docker/entrypoint.sh
```

## 4. Integration in einen bestehenden Mediastack
* Gleiche `/data`-Struktur wie TRaSH-Guides empfehlen → Hardlinks statt Kopien.
* Container ins bestehende Docker-Netz hängen (`networks: external`).
* Jellyseerr/Overseerr: Radarr-Server `mediacraft:7979` mit URL-Base `/radarr`,
  Sonarr-Server `mediacraft:7979` mit URL-Base `/sonarr`, gleicher API-Key.
* Prowlarr: Apps „Sonarr“ (`http://mediacraft:7979/sonarr`) und „Radarr“
  (`http://mediacraft:7979/radarr`) anlegen → Indexer werden automatisch synchronisiert.
* Jellyfin/Emby/Plex: Benachrichtigung „Library Refresh“ nach Import.
