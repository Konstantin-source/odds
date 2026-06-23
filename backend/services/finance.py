"""
Yahoo Finance & Finnhub Wrapper mit Caching und technischen Indikatoren.
Wenn FINNHUB_API_KEY konfiguriert ist, wird Finnhub verwendet.
Ansonsten wird yfinance (mit User-Agent Session) verwendet.
"""

import asyncio
import logging
import time
from datetime import datetime, timedelta
from typing import Any

import httpx
import pandas as pd
import requests
import yfinance as yf
from cachetools import TTLCache
from ta.momentum import RSIIndicator
from ta.trend import SMAIndicator, EMAIndicator

from backend.config import get_settings

logger = logging.getLogger(__name__)

# In-Memory Caches für verschiedene Datenkategorien (lazy initialisiert)
_quote_cache: TTLCache | None = None
_history_cache: TTLCache | None = None
_fundamentals_cache: TTLCache | None = None
_technicals_cache: TTLCache | None = None
_search_cache: TTLCache | None = None

_session: requests.Session | None = None
_time_offset: float | None = None


# ---------------------------------------------------------------------------
# Caching Helpers (Multi-Tier Caching)
# ---------------------------------------------------------------------------

def _get_quote_cache() -> TTLCache:
    global _quote_cache
    if _quote_cache is None:
        # Default: 5 Minuten für Kursdaten (Echtzeitkurse)
        _quote_cache = TTLCache(maxsize=100, ttl=max(60, get_settings().CACHE_TTL))
    return _quote_cache


def _get_history_cache() -> TTLCache:
    global _history_cache
    if _history_cache is None:
        # 4 Stunden Cache für historische Kursdaten (ändern sich nur einmal am Tag)
        _history_cache = TTLCache(maxsize=100, ttl=14400)
    return _history_cache


def _get_fundamentals_cache() -> TTLCache:
    global _fundamentals_cache
    if _fundamentals_cache is None:
        # 12 Stunden Cache für fundamentale Unternehmenskennzahlen (KGV, Div, etc.)
        _fundamentals_cache = TTLCache(maxsize=100, ttl=43200)
    return _fundamentals_cache


def _get_technicals_cache() -> TTLCache:
    global _technicals_cache
    if _technicals_cache is None:
        # 4 Stunden Cache für berechnete technische Indikatoren (RSI, SMAs)
        _technicals_cache = TTLCache(maxsize=100, ttl=14400)
    return _technicals_cache


def _get_search_cache() -> TTLCache:
    global _search_cache
    if _search_cache is None:
        # 1 Stunde Cache für Aktiensuchen
        _search_cache = TTLCache(maxsize=100, ttl=3600)
    return _search_cache


def _get_session() -> requests.Session:
    """Session mit Browser-Header initialisieren, um Blocks von Yahoo zu verhindern."""
    global _session
    if _session is None:
        _session = requests.Session()
        _session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept-Language": "en-US,en;q=0.9",
        })
    return _session


def _get_real_now() -> int:
    """Gibt den aktuellen realen Zeitstempel zurück, basierend auf dem geladenen Offset."""
    local_now = time.time()
    if _time_offset is not None:
        return int(local_now + _time_offset)
    return int(local_now)


def _update_time_offset(real_ts: int):
    """Aktualisiert das Offset zwischen lokaler Zeit und Realzeit."""
    global _time_offset
    local_now = time.time()
    _time_offset = real_ts - local_now


# ---------------------------------------------------------------------------
# Finnhub API Client
# ---------------------------------------------------------------------------

async def _fetch_from_finnhub(endpoint: str, params: dict) -> dict:
    """Hilfsfunktion für Finnhub REST API Aufrufe."""
    settings = get_settings()
    api_key = settings.FINNHUB_API_KEY
    if not api_key:
        return {}

    url = f"https://finnhub.io/api/v1/{endpoint}"
    params["token"] = api_key

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(url, params=params, timeout=15.0)
            if response.status_code == 200:
                return response.json()
            else:
                logger.error("Finnhub API Fehler (%s) %s: %s", endpoint, response.status_code, response.text)
                return {}
    except Exception as e:
        logger.error("Finnhub Verbindungsfehler (%s): %s", endpoint, e)
        return {}


# ---------------------------------------------------------------------------
# Synchrone yfinance Helfer (werden in Threads ausgeführt)
# ---------------------------------------------------------------------------

def _fetch_ticker_info(ticker: str) -> dict:
    """Holt die .info-Daten eines Tickers via yfinance."""
    try:
        t = yf.Ticker(ticker, session=_get_session())
        info = t.info or {}
        return info
    except Exception as e:
        logger.error("Fehler beim Abruf von %s info via yfinance: %s", ticker, e)
        return {}


def _fetch_history(ticker: str, period: str = "6mo") -> pd.DataFrame:
    """Holt historische Kursdaten via yfinance."""
    try:
        t = yf.Ticker(ticker, session=_get_session())
        hist = t.history(period=period)
        return hist
    except Exception as e:
        logger.error("Fehler beim Abruf von %s History (%s) via yfinance: %s", ticker, period, e)
        return pd.DataFrame()


def _search_tickers(query: str) -> list[dict]:
    """Sucht nach Aktien via yfinance."""
    try:
        results = []
        search = yf.Search(query, session=_get_session())
        quotes = getattr(search, "quotes", []) or []
        for q in quotes[:10]:
            results.append({
                "ticker": q.get("symbol", ""),
                "name": q.get("shortname") or q.get("longname", ""),
                "exchange": q.get("exchange", ""),
                "type": q.get("quoteType", ""),
            })
        return results
    except Exception as e:
        logger.error("Fehler bei der Suche nach '%s' via yfinance: %s", query, e)
        return []


# ---------------------------------------------------------------------------
# Async Public API
# ---------------------------------------------------------------------------

async def get_stock_quote(ticker: str) -> dict:
    """
    Aktueller Kurs, Tagesveränderung, Volumen.
    Gibt ein standardisiertes Dict zurück.
    """
    cache = _get_quote_cache()
    cached = cache.get(ticker.upper())
    if cached is not None:
        return cached

    # Finnhub API Fallback
    if get_settings().FINNHUB_API_KEY:
        logger.info("Rufe Kursdaten ab für %s via Finnhub", ticker)
        q_task = _fetch_from_finnhub("quote", {"symbol": ticker.upper()})
        p_task = _fetch_from_finnhub("stock/profile2", {"symbol": ticker.upper()})

        q_data, p_data = await asyncio.gather(q_task, p_task)

        if q_data and q_data.get("t"):
            _update_time_offset(q_data["t"])

        if not q_data or q_data.get("c") is None or q_data.get("c") == 0:
            return {"error": f"Keine Kursdaten für {ticker} bei Finnhub gefunden"}

        price = q_data.get("c") or 0
        prev_close = q_data.get("pc") or 0
        change = q_data.get("d") or 0
        change_pct = q_data.get("dp") or 0

        result = {
            "symbol": ticker.upper(),
            "name": p_data.get("name") or p_data.get("ticker") or ticker.upper(),
            "price": price,
            "previous_close": prev_close,
            "change": round(change, 4),
            "change_percent": round(change_pct, 4),
            "day_high": q_data.get("h"),
            "day_low": q_data.get("l"),
            "volume": 0,
            "currency": p_data.get("currency") or "USD",
        }
        cache[ticker.upper()] = result
        return result

    # Ansonsten yfinance
    logger.info("Rufe Kursdaten ab für %s via yfinance", ticker)
    info = await asyncio.to_thread(_fetch_ticker_info, ticker)

    if not info:
        return {"error": f"Keine Daten für {ticker} gefunden"}

    price = (
        info.get("regularMarketPrice")
        or info.get("currentPrice")
        or info.get("previousClose")
        or 0
    )
    prev_close = info.get("regularMarketPreviousClose") or info.get("previousClose") or 0
    change = price - prev_close if prev_close else 0
    change_pct = (change / prev_close * 100) if prev_close else 0

    result = {
        "symbol": info.get("symbol", ticker),
        "name": info.get("shortName") or info.get("longName") or ticker,
        "price": price,
        "previous_close": prev_close,
        "change": round(change, 4),
        "change_percent": round(change_pct, 4),
        "day_high": info.get("dayHigh") or info.get("regularMarketDayHigh"),
        "day_low": info.get("dayLow") or info.get("regularMarketDayLow"),
        "volume": info.get("volume") or info.get("regularMarketVolume"),
        "currency": info.get("currency", "USD"),
    }

    cache[ticker.upper()] = result
    return result


async def get_fundamentals(ticker: str) -> dict:
    """KGV, Dividendenrendite, Marktkapitalisierung, 52W-Hoch/Tief."""
    cache = _get_fundamentals_cache()
    cached = cache.get(ticker.upper())
    if cached is not None:
        return cached

    # Finnhub API Fallback
    if get_settings().FINNHUB_API_KEY:
        logger.info("Rufe Fundamentaldaten ab für %s via Finnhub", ticker)
        p_task = _fetch_from_finnhub("stock/profile2", {"symbol": ticker.upper()})
        m_task = _fetch_from_finnhub("stock/metric", {"symbol": ticker.upper(), "metric": "all"})

        p_data, m_data = await asyncio.gather(p_task, m_task)
        metrics = m_data.get("metric", {}) if m_data else {}

        market_cap = None
        if p_data.get("marketCapitalization"):
            market_cap = float(p_data["marketCapitalization"]) * 1000000  # Finnhub returns in Millions
        else:
            market_cap = metrics.get("marketCapitalization")

        result = {
            "market_cap": market_cap,
            "pe_ratio": metrics.get("peNormalized") or metrics.get("peTrailing"),
            "forward_pe": metrics.get("peForward"),
            "dividend_yield": (metrics.get("dividendYieldIndicatedAnnual") or metrics.get("dividendYield5Y")),
            "beta": metrics.get("beta"),
            "fifty_two_week_high": metrics.get("52WeekHigh"),
            "fifty_two_week_low": metrics.get("52WeekLow"),
            "sector": p_data.get("finnhubIndustry") or "",
            "industry": p_data.get("finnhubIndustry") or "",
            "description": f"Unternehmen: {p_data.get('name', ticker.upper())}. Branche: {p_data.get('finnhubIndustry', 'N/A')}. IPO: {p_data.get('ipo', 'N/A')}.",
        }
        cache[ticker.upper()] = result
        return result

    # Ansonsten yfinance
    logger.info("Rufe Fundamentaldaten ab für %s via yfinance", ticker)
    info = await asyncio.to_thread(_fetch_ticker_info, ticker)

    if not info:
        return {"error": f"Keine Fundamentaldaten für {ticker}"}

    result = {
        "market_cap": info.get("marketCap"),
        "pe_ratio": info.get("trailingPE"),
        "forward_pe": info.get("forwardPE"),
        "dividend_yield": info.get("dividendYield"),
        "beta": info.get("beta"),
        "fifty_two_week_high": info.get("fiftyTwoWeekHigh"),
        "fifty_two_week_low": info.get("fiftyTwoWeekLow"),
        "sector": info.get("sector", ""),
        "industry": info.get("industry", ""),
        "description": info.get("longBusinessSummary", ""),
    }

    cache[ticker.upper()] = result
    return result


async def get_technical_indicators(ticker: str) -> dict:
    """
    Berechnet RSI(14), SMA(50), SMA(200), EMA(20)
    auf Basis von 1 Jahr täglicher Daten.
    """
    cache = _get_technicals_cache()
    cached = cache.get(ticker.upper())
    if cached is not None:
        return cached

    # Greift auf das einheitliche get_history zurück
    history_records = await get_history(ticker, "1y")

    if not history_records or len(history_records) < 20:
        return {"error": "Nicht genug Daten für technische Analyse"}

    close_prices = [r["close"] for r in history_records]
    close = pd.Series(close_prices)

    current_price = float(close.iloc[-1])

    # RSI (14)
    rsi_val = None
    try:
        rsi = RSIIndicator(close=close, window=14)
        rsi_series = rsi.rsi()
        rsi_val = float(rsi_series.dropna().iloc[-1]) if not rsi_series.dropna().empty else None
    except Exception as e:
        logger.warning("RSI-Berechnung fehlgeschlagen für %s: %s", ticker, e)

    # SMA 50
    sma50_val = None
    try:
        if len(close) >= 50:
            sma50 = SMAIndicator(close=close, window=50)
            sma50_series = sma50.sma_indicator()
            sma50_val = float(sma50_series.dropna().iloc[-1]) if not sma50_series.dropna().empty else None
    except Exception as e:
        logger.warning("SMA50-Berechnung fehlgeschlagen für %s: %s", ticker, e)

    # SMA 200
    sma200_val = None
    try:
        if len(close) >= 200:
            sma200 = SMAIndicator(close=close, window=200)
            sma200_series = sma200.sma_indicator()
            sma200_val = float(sma200_series.dropna().iloc[-1]) if not sma200_series.dropna().empty else None
    except Exception as e:
        logger.warning("SMA200-Berechnung fehlgeschlagen für %s: %s", ticker, e)

    # EMA 20
    ema20_val = None
    try:
        ema20 = EMAIndicator(close=close, window=20)
        ema20_series = ema20.ema_indicator()
        ema20_val = float(ema20_series.dropna().iloc[-1]) if not ema20_series.dropna().empty else None
    except Exception as e:
        logger.warning("EMA20-Berechnung fehlgeschlagen für %s: %s", ticker, e)

    # Signale
    rsi_signal = "neutral"
    if rsi_val is not None:
        if rsi_val < 30:
            rsi_signal = "bullish"  # Überverkauft
        elif rsi_val > 70:
            rsi_signal = "bearish"  # Überkauft

    sma_signal = "neutral"
    if sma50_val is not None and sma200_val is not None:
        sma_signal = "bullish" if sma50_val > sma200_val else "bearish"

    ema_signal = "neutral"
    if ema20_val is not None:
        ema_signal = "bullish" if current_price > ema20_val else "bearish"

    result = {
        "current_price": round(current_price, 4),
        "rsi": round(rsi_val, 2) if rsi_val is not None else None,
        "rsi_signal": rsi_signal,
        "sma_50": round(sma50_val, 4) if sma50_val is not None else None,
        "sma_200": round(sma200_val, 4) if sma200_val is not None else None,
        "sma_signal": sma_signal,
        "ema_20": round(ema20_val, 4) if ema20_val is not None else None,
        "ema_signal": ema_signal,
    }

    cache[ticker.upper()] = result
    return result


async def get_history(ticker: str, period: str = "6mo") -> list[dict]:
    """Historische Kursdaten für Sparkline-Charts."""
    cache_key = f"{ticker.upper()}:{period}"
    cache = _get_history_cache()
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    # Finnhub API Fallback
    if get_settings().FINNHUB_API_KEY:
        logger.info("Rufe Historie ab für %s (%s) via Finnhub", ticker, period)
        
        global _time_offset
        if _time_offset is None:
            try:
                # Schnelle Abfrage um Realzeit-Offset zu kalibrieren
                temp_q = await _fetch_from_finnhub("quote", {"symbol": ticker.upper()})
                if temp_q and temp_q.get("t"):
                    _update_time_offset(temp_q["t"])
            except Exception:
                pass

        to_ts = _get_real_now()
        
        if period == "1mo":
            days = 30
        elif period == "3mo":
            days = 90
        elif period == "6mo":
            days = 180
        elif period == "1y":
            days = 365
        elif period == "5y":
            days = 5 * 365
        else:
            days = 180

        from_ts = to_ts - (days * 24 * 60 * 60)

        candles = await _fetch_from_finnhub("stock/candle", {
            "symbol": ticker.upper(),
            "resolution": "D",
            "from": from_ts,
            "to": to_ts
        })

        if not candles or candles.get("s") != "ok":
            # WICHTIG: Auf dem Free-Tier von Finnhub ist /stock/candle gesperrt (403).
            # Wir fallen in diesem Fall auf yfinance für die historischen Daten zurück,
            # da yfinance auf lokalen IPs meist wieder funktioniert, sobald die Sperre abgelaufen ist.
            logger.warning("Finnhub /stock/candle fehlgeschlagen (evtl. Free-Tier Limit). Versuche yfinance Fallback.")
        else:
            records = []
            timestamps = candles.get("t", [])
            opens = candles.get("o", [])
            highs = candles.get("h", [])
            lows = candles.get("l", [])
            closes = candles.get("c", [])
            volumes = candles.get("v", [])

            for i in range(len(timestamps)):
                dt = datetime.fromtimestamp(timestamps[i])
                records.append({
                    "date": dt.strftime("%Y-%m-%d"),
                    "open": round(float(opens[i]), 4) if i < len(opens) else 0.0,
                    "high": round(float(highs[i]), 4) if i < len(highs) else 0.0,
                    "low": round(float(lows[i]), 4) if i < len(lows) else 0.0,
                    "close": round(float(closes[i]), 4) if i < len(closes) else 0.0,
                    "volume": int(volumes[i]) if i < len(volumes) else 0,
                })

            cache[cache_key] = records
            return records

    # Ansonsten yfinance
    logger.info("Rufe Historie ab für %s (%s) via yfinance", ticker, period)
    hist = await asyncio.to_thread(_fetch_history, ticker, period)

    if hist.empty:
        return []

    records = []
    for date, row in hist.iterrows():
        close = row["Close"]
        if hasattr(close, "iloc"):
            close = close.iloc[0]
        open_val = row["Open"]
        if hasattr(open_val, "iloc"):
            open_val = open_val.iloc[0]
        high = row["High"]
        if hasattr(high, "iloc"):
            high = high.iloc[0]
        low = row["Low"]
        if hasattr(low, "iloc"):
            low = low.iloc[0]
        volume = row["Volume"]
        if hasattr(volume, "iloc"):
            volume = volume.iloc[0]

        records.append({
            "date": date.strftime("%Y-%m-%d"),
            "open": round(float(open_val), 4),
            "high": round(float(high), 4),
            "low": round(float(low), 4),
            "close": round(float(close), 4),
            "volume": int(volume) if pd.notna(volume) else 0,
        })

    cache[cache_key] = records
    return records


async def search_stocks(query: str) -> list[dict]:
    """Aktiensuche via yfinance oder Finnhub mit Fallback-Logik."""
    if not query or len(query) < 1:
        return []

    cache_key = query.lower()
    cache = _get_search_cache()
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    # Finnhub API Fallback
    if get_settings().FINNHUB_API_KEY:
        logger.info("Suche Aktien für '%s' via Finnhub", query)
        data = await _fetch_from_finnhub("search", {"q": query})
        results = []
        for r in data.get("result", [])[:10]:
            results.append({
                "ticker": r.get("symbol", ""),
                "name": r.get("description") or r.get("symbol", ""),
                "exchange": "",
                "type": r.get("type", ""),
            })
        if results:
            cache[cache_key] = results
            return results
        else:
            logger.warning("Finnhub returned empty results for %s, falling back to yfinance", query)

    # Ansonsten yfinance (oder Rückfall wenn Finnhub leer)
    logger.info("Suche Aktien für '%s' via yfinance", query)
    results = await asyncio.to_thread(_search_tickers, query)
    cache[cache_key] = results
    return results


async def get_full_stock_data(ticker: str) -> dict:
    """
    Kombiniert Quote + Fundamentals + Technicals in ein Dict.
    Wird vom LLM-Service für den Analyse-Prompt verwendet.
    """
    quote, fundamentals, technicals = await asyncio.gather(
        get_stock_quote(ticker),
        get_fundamentals(ticker),
        get_technical_indicators(ticker),
    )

    return {
        "ticker": ticker,
        "quote": quote,
        "fundamentals": fundamentals,
        "technicals": technicals,
    }
