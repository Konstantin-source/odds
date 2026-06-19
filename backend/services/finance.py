"""
Yahoo Finance Wrapper mit Caching und technischen Indikatoren.
Alle yfinance-Aufrufe werden in asyncio.to_thread() gekapselt,
da yfinance synchron arbeitet.
"""

import asyncio
import logging
from typing import Any

import pandas as pd
import requests
import yfinance as yf
from cachetools import TTLCache
from ta.momentum import RSIIndicator
from ta.trend import SMAIndicator, EMAIndicator

from backend.config import get_settings

logger = logging.getLogger(__name__)

# In-Memory Cache: maxsize=200 Einträge, TTL aus Konfiguration
_cache: TTLCache | None = None
_session: requests.Session | None = None


def _get_cache() -> TTLCache:
    """Cache lazy initialisieren (Settings könnten noch nicht geladen sein)."""
    global _cache
    if _cache is None:
        _cache = TTLCache(maxsize=200, ttl=get_settings().CACHE_TTL)
    return _cache


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


def _cached(key: str):
    """Einfacher Cache-Lookup."""
    cache = _get_cache()
    return cache.get(key)


def _set_cache(key: str, value: Any):
    """Wert im Cache speichern."""
    cache = _get_cache()
    cache[key] = value


# ---------------------------------------------------------------------------
# Synchrone yfinance Helfer (werden in Threads ausgeführt)
# ---------------------------------------------------------------------------

def _fetch_ticker_info(ticker: str) -> dict:
    """Holt die .info-Daten eines Tickers."""
    try:
        t = yf.Ticker(ticker, session=_get_session())
        info = t.info or {}
        return info
    except Exception as e:
        logger.error("Fehler beim Abruf von %s info: %s", ticker, e)
        return {}


def _fetch_history(ticker: str, period: str = "6mo") -> pd.DataFrame:
    """Holt historische Kursdaten."""
    try:
        t = yf.Ticker(ticker, session=_get_session())
        hist = t.history(period=period)
        return hist
    except Exception as e:
        logger.error("Fehler beim Abruf von %s History (%s): %s", ticker, period, e)
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
        logger.error("Fehler bei der Suche nach '%s': %s", query, e)
        return []


# ---------------------------------------------------------------------------
# Async Public API
# ---------------------------------------------------------------------------

async def get_stock_quote(ticker: str) -> dict:
    """
    Aktueller Kurs, Tagesveränderung, Volumen.
    Gibt ein standardisiertes Dict zurück.
    """
    cache_key = f"quote:{ticker}"
    cached = _cached(cache_key)
    if cached is not None:
        return cached

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
        "name": info.get("shortName") or info.get("longName", ticker),
        "price": price,
        "previous_close": prev_close,
        "change": round(change, 4),
        "change_percent": round(change_pct, 4),
        "day_high": info.get("dayHigh") or info.get("regularMarketDayHigh"),
        "day_low": info.get("dayLow") or info.get("regularMarketDayLow"),
        "volume": info.get("volume") or info.get("regularMarketVolume"),
        "currency": info.get("currency", "USD"),
    }

    _set_cache(cache_key, result)
    return result


async def get_fundamentals(ticker: str) -> dict:
    """KGV, Dividendenrendite, Marktkapitalisierung, 52W-Hoch/Tief."""
    cache_key = f"fundamentals:{ticker}"
    cached = _cached(cache_key)
    if cached is not None:
        return cached

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

    _set_cache(cache_key, result)
    return result


async def get_technical_indicators(ticker: str) -> dict:
    """
    Berechnet RSI(14), SMA(50), SMA(200), EMA(20)
    auf Basis von 1 Jahr täglicher Daten.
    """
    cache_key = f"technicals:{ticker}"
    cached = _cached(cache_key)
    if cached is not None:
        return cached

    hist = await asyncio.to_thread(_fetch_history, ticker, "1y")

    if hist.empty or len(hist) < 20:
        return {"error": "Nicht genug Daten für technische Analyse"}

    close = hist["Close"]

    # Wenn Close eine Multi-Level-Column hat (z.B. bei neueren yfinance-Versionen)
    if isinstance(close, pd.DataFrame):
        close = close.iloc[:, 0]

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

    _set_cache(cache_key, result)
    return result


async def get_history(ticker: str, period: str = "6mo") -> list[dict]:
    """Historische Kursdaten für Sparkline-Charts."""
    cache_key = f"history:{ticker}:{period}"
    cached = _cached(cache_key)
    if cached is not None:
        return cached

    hist = await asyncio.to_thread(_fetch_history, ticker, period)

    if hist.empty:
        return []

    records = []
    for date, row in hist.iterrows():
        # Handle multi-level columns
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

    _set_cache(cache_key, records)
    return records


async def search_stocks(query: str) -> list[dict]:
    """Aktiensuche via yfinance."""
    if not query or len(query) < 1:
        return []

    cache_key = f"search:{query.lower()}"
    cached = _cached(cache_key)
    if cached is not None:
        return cached

    results = await asyncio.to_thread(_search_tickers, query)
    _set_cache(cache_key, results)
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
