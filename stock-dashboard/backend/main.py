"""
Aktien-Dashboard — FastAPI Backend
Hauptanwendung mit Auth, API-Routen und Static-File-Serving.
"""

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Request, Response, HTTPException, Depends, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from pydantic import BaseModel

from backend.config import get_settings
from backend.database import init_db, get_watchlist, add_stock, remove_stock
from backend.services.finance import (
    get_stock_quote,
    get_fundamentals,
    get_technical_indicators,
    get_history,
    search_stocks,
)
from backend.services.llm import get_recommendation

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Lifespan (Startup / Shutdown)
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Datenbank beim Start initialisieren."""
    await init_db()
    logger.info("Aktien-Dashboard gestartet 🚀")
    yield
    logger.info("Aktien-Dashboard heruntergefahren.")


# ---------------------------------------------------------------------------
# FastAPI App
# ---------------------------------------------------------------------------
app = FastAPI(
    title="Aktien Dashboard API",
    description="Selbstgehostetes Aktien-Dashboard mit Watchlist, Technischer Analyse und KI-Empfehlungen",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS — für lokale Entwicklung alle Origins erlauben
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Auth Helpers
# ---------------------------------------------------------------------------
COOKIE_NAME = "session_token"
COOKIE_MAX_AGE = 86400  # 24 Stunden


def _get_serializer() -> URLSafeTimedSerializer:
    """Serializer für signierte Session-Cookies."""
    return URLSafeTimedSerializer(get_settings().SESSION_SECRET)


def _create_session_token() -> str:
    """Erzeugt einen signierten Session-Token."""
    serializer = _get_serializer()
    return serializer.dumps({"authenticated": True})


def _verify_session_token(token: str) -> bool:
    """Prüft ob ein Session-Token gültig ist (max 24h alt)."""
    serializer = _get_serializer()
    try:
        data = serializer.loads(token, max_age=COOKIE_MAX_AGE)
        return data.get("authenticated", False)
    except (BadSignature, SignatureExpired):
        return False


async def require_auth(request: Request):
    """Dependency — prüft ob der Request authentifiziert ist."""
    token = request.cookies.get(COOKIE_NAME)
    if not token or not _verify_session_token(token):
        raise HTTPException(status_code=401, detail="Nicht authentifiziert")


# ---------------------------------------------------------------------------
# Request Models
# ---------------------------------------------------------------------------
class LoginRequest(BaseModel):
    password: str


class WatchlistAddRequest(BaseModel):
    ticker: str
    name: str = ""


# ---------------------------------------------------------------------------
# Auth Routen
# ---------------------------------------------------------------------------
@app.post("/api/login")
async def login(body: LoginRequest, response: Response):
    """Login mit Passwort — setzt einen Session-Cookie."""
    settings = get_settings()
    if body.password != settings.DASHBOARD_PASSWORD:
        raise HTTPException(status_code=401, detail="Falsches Passwort")

    token = _create_session_token()
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        max_age=COOKIE_MAX_AGE,
        httponly=True,
        samesite="lax",
    )
    logger.info("Erfolgreicher Login")
    return {"status": "ok", "message": "Erfolgreich angemeldet"}


@app.post("/api/logout")
async def logout(response: Response):
    """Logout — löscht den Session-Cookie."""
    response.delete_cookie(key=COOKIE_NAME)
    logger.info("Logout")
    return {"status": "ok", "message": "Abgemeldet"}


@app.get("/api/auth/status")
async def auth_status(request: Request):
    """Prüft den aktuellen Authentifizierungsstatus."""
    token = request.cookies.get(COOKIE_NAME)
    authenticated = bool(token and _verify_session_token(token))
    return {"authenticated": authenticated}


# ---------------------------------------------------------------------------
# Watchlist Routen
# ---------------------------------------------------------------------------
@app.get("/api/watchlist", dependencies=[Depends(require_auth)])
async def api_get_watchlist():
    """Watchlist mit aktuellen Kursdaten abrufen."""
    watchlist = await get_watchlist()

    # Kurse für alle Einträge parallel laden
    async def enrich_item(item: dict) -> dict:
        try:
            quote = await get_stock_quote(item["ticker"])
            item["price"] = quote.get("price")
            item["change"] = quote.get("change")
            item["change_percent"] = quote.get("change_percent")
            item["currency"] = quote.get("currency", "USD")
        except Exception as e:
            logger.warning("Kurs-Abruf fehlgeschlagen für %s: %s", item["ticker"], e)
            item["price"] = None
            item["change_percent"] = None
        return item

    if watchlist:
        enriched = await asyncio.gather(*[enrich_item(item) for item in watchlist])
        return {"watchlist": enriched}

    return {"watchlist": []}


@app.post("/api/watchlist", dependencies=[Depends(require_auth)])
async def api_add_to_watchlist(body: WatchlistAddRequest):
    """Aktie zur Watchlist hinzufügen."""
    ticker = body.ticker.upper().strip()
    name = body.name.strip()

    if not ticker:
        raise HTTPException(status_code=400, detail="Ticker darf nicht leer sein")

    # Wenn kein Name angegeben, versuche ihn über yfinance zu holen
    if not name:
        try:
            quote = await get_stock_quote(ticker)
            name = quote.get("name", ticker)
        except Exception:
            name = ticker

    result = await add_stock(ticker, name)

    if result["status"] == "already_exists":
        raise HTTPException(status_code=409, detail=f"{ticker} ist bereits in der Watchlist")

    return result


@app.delete("/api/watchlist/{ticker}", dependencies=[Depends(require_auth)])
async def api_remove_from_watchlist(ticker: str):
    """Aktie aus der Watchlist entfernen."""
    result = await remove_stock(ticker)

    if result["status"] == "not_found":
        raise HTTPException(status_code=404, detail=f"{ticker} nicht in der Watchlist")

    return result


# ---------------------------------------------------------------------------
# Aktien-Daten Routen
# ---------------------------------------------------------------------------
@app.get("/api/search", dependencies=[Depends(require_auth)])
async def api_search(q: str = Query(default="", min_length=1, description="Suchbegriff")):
    """Aktiensuche."""
    results = await search_stocks(q)
    return {"results": results}


@app.get("/api/stock/{ticker}", dependencies=[Depends(require_auth)])
async def api_get_stock(
    ticker: str,
    period: str = Query(default="6mo", description="Zeitraum (1mo, 3mo, 6mo, 1y, 5y)"),
):
    """Kursdaten, Kennzahlen und Indikatoren für eine Aktie."""
    # Alle Daten parallel laden
    quote_task = get_stock_quote(ticker)
    fundamentals_task = get_fundamentals(ticker)
    technicals_task = get_technical_indicators(ticker)
    history_task = get_history(ticker, period)

    quote, fundamentals, technicals, history = await asyncio.gather(
        quote_task, fundamentals_task, technicals_task, history_task,
        return_exceptions=True,
    )

    # Exceptions in leere Dicts umwandeln
    if isinstance(quote, Exception):
        logger.error("Quote-Fehler für %s: %s", ticker, quote)
        quote = {"error": str(quote)}
    if isinstance(fundamentals, Exception):
        logger.error("Fundamentals-Fehler für %s: %s", ticker, fundamentals)
        fundamentals = {"error": str(fundamentals)}
    if isinstance(technicals, Exception):
        logger.error("Technicals-Fehler für %s: %s", ticker, technicals)
        technicals = {"error": str(technicals)}
    if isinstance(history, Exception):
        logger.error("History-Fehler für %s: %s", ticker, history)
        history = []

    return {
        "ticker": ticker.upper(),
        "quote": quote,
        "fundamentals": fundamentals,
        "technicals": technicals,
        "history": history,
    }


# ---------------------------------------------------------------------------
# LLM Analyse Route
# ---------------------------------------------------------------------------
@app.post("/api/analysis/{ticker}", dependencies=[Depends(require_auth)])
async def api_get_analysis(ticker: str):
    """LLM-gestützte Aktienanalyse anfordern."""
    logger.info("Analyse angefordert für %s", ticker)
    result = await get_recommendation(ticker)
    return result


# ---------------------------------------------------------------------------
# Globaler Exception Handler
# ---------------------------------------------------------------------------
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Fängt unbehandelte Exceptions ab und gibt eine saubere Fehlermeldung zurück."""
    logger.error("Unbehandelter Fehler: %s", exc, exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "Interner Serverfehler. Bitte versuche es später erneut."},
    )


# ---------------------------------------------------------------------------
# Static Files (Frontend) — MUSS als letztes gemountet werden!
# ---------------------------------------------------------------------------
_frontend_path = Path(__file__).parent.parent / "frontend"
if _frontend_path.exists():
    app.mount("/", StaticFiles(directory=str(_frontend_path), html=True), name="frontend")
    logger.info("Frontend gemountet von: %s", _frontend_path)
else:
    logger.warning("Frontend-Verzeichnis nicht gefunden: %s", _frontend_path)
