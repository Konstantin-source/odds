"""
Aktien-Dashboard — FastAPI Backend
Hauptanwendung mit Auth, API-Routen und Static-File-Serving.
"""

import asyncio
import logging
import math
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional, Any

from fastapi import FastAPI, Request, Response, HTTPException, Depends, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from pydantic import BaseModel


def clean_nans(obj: Any) -> Any:
    """Rekursive Bereinigung von NaN- und Inf-Werten zu None (null)."""
    if isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return None
        return obj
    elif isinstance(obj, dict):
        return {k: clean_nans(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [clean_nans(v) for v in obj]
    elif isinstance(obj, tuple):
        return tuple(clean_nans(v) for v in obj)
    return obj


class SafeJSONResponse(JSONResponse):
    """JSONResponse die NaN/Inf Werte sicher zu null konvertiert."""
    def render(self, content: Any) -> bytes:
        clean_content = clean_nans(content)
        return super().render(clean_content)

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
    default_response_class=SafeJSONResponse,
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
# Debug Route
# ---------------------------------------------------------------------------
@app.get("/api/debug", dependencies=[Depends(require_auth)])
async def api_debug():
    """Debug-Endpunkt zum Testen von yfinance und Netzwerkkonnektivität."""
    import traceback
    import yfinance as yf
    
    results = {}
    
    # Test 1: yf.Search ohne session
    try:
        s = yf.Search("ama")
        results["search_no_session"] = {
            "success": True,
            "quotes_count": len(getattr(s, "quotes", []) or []),
        }
    except Exception as e:
        results["search_no_session"] = {
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc(),
        }
        
    # Test 2: yf.Search mit session
    try:
        from backend.services.finance import _get_session
        s = yf.Search("ama", session=_get_session())
        results["search_with_session"] = {
            "success": True,
            "quotes_count": len(getattr(s, "quotes", []) or []),
        }
    except Exception as e:
        results["search_with_session"] = {
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc(),
        }
        
    # Test 3: Ticker SAP.DE mit session
    try:
        from backend.services.finance import _get_session
        t = yf.Ticker("SAP.DE", session=_get_session())
        results["ticker_with_session"] = {
            "success": True,
            "info_keys_count": len(t.info) if t.info else 0,
            "price": t.info.get("regularMarketPrice") or t.info.get("currentPrice") if t.info else None,
        }
    except Exception as e:
        results["ticker_with_session"] = {
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc(),
        }
        
    # Test 4: DNS / Verbindung zu Yahoo direkt
    try:
        import httpx
        r = await httpx.AsyncClient().get("https://query2.finance.yahoo.com/v1/finance/search?q=ama")
        results["direct_yahoo_http_call"] = {
            "success": True,
            "status_code": r.status_code,
            "content_length": len(r.text),
        }
    except Exception as e:
        results["direct_yahoo_http_call"] = {
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc(),
        }
        
    # Test 5: Finnhub API Key und Verbindung
    settings = get_settings()
    results["finnhub_config"] = {
        "has_api_key": bool(settings.FINNHUB_API_KEY),
        "api_key_length": len(settings.FINNHUB_API_KEY) if settings.FINNHUB_API_KEY else 0,
    }
    if settings.FINNHUB_API_KEY:
        try:
            from backend.services.finance import _fetch_from_finnhub
            test_res = await _fetch_from_finnhub("quote", {"symbol": "SAP.DE"})
            results["finnhub_api_call"] = {
                "success": bool(test_res and test_res.get("c") is not None and test_res.get("c") != 0),
                "price": test_res.get("c"),
                "raw_response": test_res,
            }
        except Exception as e:
            results["finnhub_api_call"] = {
                "success": False,
                "error": str(e),
                "traceback": traceback.format_exc(),
            }
            
    return results


# ---------------------------------------------------------------------------
# Globaler Exception Handler
# ---------------------------------------------------------------------------
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Fängt unbehandelte Exceptions ab und gibt eine saubere Fehlermeldung zurück."""
    logger.error("Unbehandelter Fehler: %s", exc, exc_info=True)
    return SafeJSONResponse(
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
