# 📈 Aktien-Dashboard

> Selbstgehostetes Aktien-Dashboard mit Echtzeit-Kursen, technischer Analyse und KI-gestützten Empfehlungen.

![Python](https://img.shields.io/badge/Python-3.12-blue?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688?logo=fastapi&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-Ready-2496ED?logo=docker&logoColor=white)
![License](https://img.shields.io/badge/Lizenz-MIT-green)

---

## ✨ Features

- 📊 **Echtzeit-Aktienkurse** — Live-Daten via Yahoo Finance API
- 📋 **Persönliche Watchlist** — Aktien hinzufügen, entfernen & persistent speichern (SQLite)
- 📈 **Technische Indikatoren** — RSI, SMA (20/50), EMA (12/26) mit visueller Darstellung
- 🤖 **KI-gestützte Aktienanalyse** — Intelligente Bewertungen via Mistral Large 3
- 🔒 **Passwortgeschützter Zugang** — Session-basierte Authentifizierung
- 🐳 **Ein-Befehl Deployment** — Docker Compose für sofortiges Setup
- 🌙 **Premium Dark-Mode Design** — Modernes Glassmorphism-UI mit Animationen
- ⚡ **Intelligenter Cache** — Konfigurierbares Caching für optimale Performance

---

## 🚀 Schnellstart

### Voraussetzungen

| Komponente         | Version     | Erforderlich |
| ------------------ | ----------- | ------------ |
| Docker             | ≥ 20.10     | ✅ Ja        |
| Docker Compose     | ≥ 2.0       | ✅ Ja        |
| LLM API Zugang     | —           | ❌ Optional  |

### Installation

```bash
# 1. Repository klonen
git clone https://github.com/dein-user/stock-dashboard.git
cd stock-dashboard

# 2. Umgebungsvariablen konfigurieren
cp .env.example .env
nano .env  # Passwort und optionale Werte anpassen

# 3. Container bauen und starten
docker compose up -d --build

# 4. Dashboard öffnen
# → http://localhost:8501
```

> [!TIP]
> Beim ersten Start wird die SQLite-Datenbank automatisch erstellt. Die Watchlist bleibt über Container-Neustarts hinweg erhalten dank Docker Volume.

### Container verwalten

```bash
# Status prüfen
docker compose ps

# Logs anzeigen
docker compose logs -f stock-dashboard

# Stoppen
docker compose down

# Stoppen und Daten löschen
docker compose down -v
```

---

## ⚙️ Konfiguration

Alle Einstellungen werden über Umgebungsvariablen in der `.env`-Datei gesteuert:

| Variable             | Beschreibung                                  | Standard                              | Erforderlich |
| -------------------- | --------------------------------------------- | ------------------------------------- | ------------ |
| `DASHBOARD_PASSWORD` | Passwort für den Dashboard-Zugang             | —                                     | ✅ Ja        |
| `LLM_API_URL`        | URL der LLM-API für KI-Analyse               | `https://api.ai.rh-koeln.de/v1/...`  | ❌ Nein      |
| `LLM_MODEL`          | Modellname für die KI-Analyse                 | `mistral-large-3-675b-instruct-2512` | ❌ Nein      |
| `LLM_API_KEY`        | API-Schlüssel für die LLM-API                 | —                                     | ❌ Nein      |
| `SESSION_SECRET`     | Secret für Session-Verschlüsselung            | *Auto-generiert*                      | ❌ Nein      |
| `DB_PATH`            | Pfad zur SQLite-Datenbank                     | `/app/data/watchlist.db`              | ❌ Nein      |
| `CACHE_TTL`          | Cache-Dauer in Sekunden                       | `300` (5 Min.)                        | ❌ Nein      |

---

## 🤖 KI-Integration (LLM)

Das Dashboard kann optional eine KI-gestützte Aktienanalyse durchführen. Dafür wird ein OpenAI-kompatibler API-Endpunkt benötigt.

### Einrichtung

1. **API-Schlüssel** in der `.env`-Datei setzen:
   ```env
   LLM_API_URL=https://api.ai.rh-koeln.de/v1/chat/completions
   LLM_MODEL=mistral-large-3-675b-instruct-2512
   LLM_API_KEY=dein_api_key_hier
   ```

2. **Container neu starten**:
   ```bash
   docker compose restart
   ```

3. Im Dashboard den **„KI-Analyse"**-Button bei einer Aktie klicken.

### Funktionsweise

Die KI erhält aktuelle Kursdaten und technische Indikatoren und liefert:
- 📊 **Technische Einschätzung** — Analyse der aktuellen Chartlage
- 🎯 **Kursziel** — Geschätztes Preisziel basierend auf technischen Signalen
- ⚖️ **Empfehlung** — Kaufen / Halten / Verkaufen mit Begründung
- ⚠️ **Risikofaktoren** — Potenzielle Risiken und Gegenargumente

> [!IMPORTANT]
> KI-Analysen sind keine Anlageberatung. Alle Empfehlungen basieren auf technischen Indikatoren und sollten als ergänzende Information betrachtet werden.

---

## 🏗️ Technologie-Stack

| Kategorie      | Technologie                          | Zweck                              |
| -------------- | ------------------------------------ | ---------------------------------- |
| **Backend**    | FastAPI + Uvicorn                    | REST-API & statische Dateien       |
| **Frontend**   | Vanilla HTML/CSS/JS                  | Premium Dark-Mode UI               |
| **Daten**      | yfinance                            | Echtzeit-Aktienkurse               |
| **Datenbank**  | SQLite (aiosqlite)                   | Persistente Watchlist              |
| **KI**         | Mistral Large 3 (OpenAI-kompatibel) | Aktienanalyse & Empfehlungen       |
| **Auth**       | Session-Cookies (itsdangerous)       | Passwortgeschützter Zugang         |
| **Deployment** | Docker & Docker Compose              | Container-basiertes Deployment     |
| **Cache**      | In-Memory (cachetools)               | Performance-Optimierung            |

---

## 📁 Projektstruktur

```
stock-dashboard/
├── backend/
│   ├── main.py              # FastAPI App & Routen
│   ├── config.py            # Konfiguration & Umgebungsvariablen
│   ├── auth.py              # Authentifizierung & Sessions
│   ├── stock_service.py     # Aktiendaten & Indikatoren
│   ├── llm_service.py       # KI-Analyse Integration
│   ├── database.py          # SQLite Watchlist-Verwaltung
│   └── requirements.txt     # Python-Abhängigkeiten
├── frontend/
│   ├── index.html           # Dashboard UI
│   ├── styles.css           # Premium Dark-Mode Styles
│   └── app.js               # Client-Logik & API-Calls
├── Dockerfile               # Container-Build
├── docker-compose.yml       # Orchestrierung
├── .env.example             # Konfigurationsvorlage
└── README.md                # Diese Datei
```

---

## 🔒 Sicherheitshinweise

- **Passwort ändern**: Verwende ein starkes, einzigartiges Passwort in der `.env`-Datei.
- **Nicht öffentlich exponieren**: Das Dashboard ist für den privaten/lokalen Einsatz konzipiert. Für öffentlichen Zugang einen Reverse-Proxy (z.B. Nginx) mit HTTPS verwenden.
- **`.env`-Datei schützen**: Niemals die `.env`-Datei in ein Git-Repository committen.
- **API-Schlüssel**: LLM API-Schlüssel sicher aufbewahren und regelmäßig rotieren.

---

## 🐛 Fehlerbehebung

<details>
<summary><strong>Container startet nicht</strong></summary>

```bash
# Logs prüfen
docker compose logs stock-dashboard

# Häufige Ursache: .env-Datei fehlt
cp .env.example .env
```
</details>

<details>
<summary><strong>Port 8501 bereits belegt</strong></summary>

In `docker-compose.yml` den Port ändern:
```yaml
ports:
  - "9090:8501"  # Externer Port anpassen
```
</details>

<details>
<summary><strong>KI-Analyse funktioniert nicht</strong></summary>

1. API-URL, Modell und API-Key in `.env` prüfen
2. Netzwerkverbindung zum LLM-Endpunkt testen
3. Container neu starten: `docker compose restart`
</details>

<details>
<summary><strong>Watchlist-Daten verloren</strong></summary>

Stelle sicher, dass das Docker Volume korrekt eingebunden ist:
```bash
docker volume ls | grep dashboard_data
```
</details>

---

## 📄 Lizenz

Dieses Projekt steht unter der [MIT-Lizenz](LICENSE).

---

<p align="center">
  <sub>Erstellt mit ❤️ für den privaten Einsatz • Keine Anlageberatung</sub>
</p>
