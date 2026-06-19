"""
LLM-Integration für die Aktienanalyse.
Verwendet eine OpenAI-kompatible Chat-Completions API (z.B. Ollama, vLLM, RH-Köln).
"""

import json
import logging
from typing import Any

import httpx

from backend.config import get_settings
from backend.services.finance import get_full_stock_data

logger = logging.getLogger(__name__)


def build_analysis_prompt(stock_data: dict) -> tuple[str, str]:
    """
    Erzeugt System- und User-Prompt für die Aktienanalyse.

    Returns:
        (system_prompt, user_prompt)
    """
    system_prompt = """Du bist ein erfahrener Finanzanalyst mit über 20 Jahren Erfahrung an den Aktienmärkten.
Du analysierst Aktien auf Basis von Fundamentaldaten, technischen Indikatoren und Marktbedingungen.

Deine Analyse muss folgendes enthalten:
1. **Empfehlung**: Genau eines von: "Kaufen", "Halten" oder "Verkaufen"
2. **Konfidenz**: Eine Zahl zwischen 0.0 und 1.0 (wie sicher bist du dir?)
3. **Begründung**: Eine ausführliche Begründung in 3-5 Sätzen
4. **Risiken**: Genau 3 wesentliche Risiken als Liste
5. **Chancen**: Genau 3 wesentliche Chancen als Liste

Antworte AUSSCHLIESSLICH im folgenden JSON-Format, ohne zusätzlichen Text:
{
    "empfehlung": "Kaufen" | "Halten" | "Verkaufen",
    "konfidenz": 0.0 - 1.0,
    "begruendung": "...",
    "risiken": ["Risiko 1", "Risiko 2", "Risiko 3"],
    "chancen": ["Chance 1", "Chance 2", "Chance 3"]
}

Wichtig:
- Antworte auf Deutsch
- Sei objektiv und berücksichtige sowohl positive als auch negative Faktoren
- Beziehe dich konkret auf die bereitgestellten Kennzahlen
- Antworte NUR mit dem JSON-Objekt, kein Markdown, keine Erklärungen drumherum"""

    # Daten für den User-Prompt aufbereiten
    quote = stock_data.get("quote", {})
    fundamentals = stock_data.get("fundamentals", {})
    technicals = stock_data.get("technicals", {})

    context = {
        "ticker": stock_data.get("ticker", "Unbekannt"),
        "name": quote.get("name", "Unbekannt"),
        "aktueller_kurs": quote.get("price"),
        "waehrung": quote.get("currency", "USD"),
        "tagesveraenderung_prozent": quote.get("change_percent"),
        "volumen": quote.get("volume"),
        "kennzahlen": {
            "marktkapitalisierung": fundamentals.get("market_cap"),
            "kgv": fundamentals.get("pe_ratio"),
            "forward_kgv": fundamentals.get("forward_pe"),
            "dividendenrendite": fundamentals.get("dividend_yield"),
            "beta": fundamentals.get("beta"),
            "52w_hoch": fundamentals.get("fifty_two_week_high"),
            "52w_tief": fundamentals.get("fifty_two_week_low"),
            "sektor": fundamentals.get("sector"),
            "branche": fundamentals.get("industry"),
        },
        "technische_indikatoren": {
            "rsi_14": technicals.get("rsi"),
            "rsi_signal": technicals.get("rsi_signal"),
            "sma_50": technicals.get("sma_50"),
            "sma_200": technicals.get("sma_200"),
            "sma_signal": technicals.get("sma_signal"),
            "ema_20": technicals.get("ema_20"),
            "ema_signal": technicals.get("ema_signal"),
        },
    }

    user_prompt = f"Analysiere folgende Aktie und gib deine Einschätzung ab:\n\n{json.dumps(context, indent=2, ensure_ascii=False)}"

    return system_prompt, user_prompt


def _parse_llm_response(text: str) -> dict:
    """
    Parst die LLM-Antwort und extrahiert das JSON-Objekt.
    Robust gegen Markdown-Code-Blöcke und zusätzlichen Text.
    """
    # Versuche direkt zu parsen
    text = text.strip()

    # Entferne eventuelle Markdown-Code-Blöcke
    if text.startswith("```"):
        # Finde den Code-Block
        lines = text.split("\n")
        json_lines = []
        in_block = False
        for line in lines:
            if line.startswith("```") and not in_block:
                in_block = True
                continue
            elif line.startswith("```") and in_block:
                break
            elif in_block:
                json_lines.append(line)
        text = "\n".join(json_lines)

    # Versuche JSON zu finden, wenn der Text nicht direkt JSON ist
    if not text.startswith("{"):
        # Suche nach dem ersten { und letzten }
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            text = text[start:end + 1]

    try:
        data = json.loads(text)
        return {
            "recommendation": data.get("empfehlung", "Halten"),
            "confidence": float(data.get("konfidenz", 0.5)),
            "reasoning": data.get("begruendung", ""),
            "risks": data.get("risiken", []),
            "opportunities": data.get("chancen", []),
        }
    except (json.JSONDecodeError, ValueError) as e:
        logger.warning("LLM-Antwort konnte nicht als JSON geparst werden: %s", e)
        # Fallback: Rohtext als Begründung verwenden
        return {
            "recommendation": "Halten",
            "confidence": 0.5,
            "reasoning": text[:1000] if text else "Analyse konnte nicht verarbeitet werden.",
            "risks": [],
            "opportunities": [],
        }


async def get_recommendation(ticker: str) -> dict:
    """
    Vollständige Analyse-Pipeline:
    1. Finanzdaten laden
    2. Prompt bauen
    3. LLM API aufrufen
    4. Antwort parsen und zurückgeben
    """
    settings = get_settings()

    # Prüfe ob LLM konfiguriert ist
    if not settings.LLM_API_KEY:
        logger.info("Kein LLM API-Key konfiguriert — Fallback")
        return {
            "recommendation": "",
            "confidence": 0,
            "reasoning": "",
            "risks": [],
            "opportunities": [],
            "error": "Kein LLM-Endpunkt konfiguriert. Bitte setze LLM_API_KEY in der .env Datei.",
            "configured": False,
        }

    # 1. Daten laden
    logger.info("Lade Finanzdaten für %s ...", ticker)
    stock_data = await get_full_stock_data(ticker)

    if stock_data.get("quote", {}).get("error"):
        return {
            "recommendation": "",
            "confidence": 0,
            "reasoning": "",
            "risks": [],
            "opportunities": [],
            "error": f"Keine Daten für {ticker} verfügbar.",
        }

    # 2. Prompt bauen
    system_prompt, user_prompt = build_analysis_prompt(stock_data)

    # 3. LLM API aufrufen
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {settings.LLM_API_KEY}",
    }

    payload = {
        "model": settings.LLM_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.3,
        "max_tokens": 1500,
    }

    try:
        logger.info("Sende Analyse-Anfrage an LLM (%s) ...", settings.LLM_MODEL)
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(
                settings.LLM_API_URL,
                headers=headers,
                json=payload,
            )
            response.raise_for_status()
            data = response.json()

        # Antwort extrahieren (OpenAI-kompatibles Format)
        choices = data.get("choices", [])
        if not choices:
            logger.error("Keine Antwort vom LLM erhalten: %s", data)
            return {
                "recommendation": "Halten",
                "confidence": 0.5,
                "reasoning": "Das LLM hat keine Antwort generiert.",
                "risks": [],
                "opportunities": [],
            }

        content = choices[0].get("message", {}).get("content", "")
        logger.info("LLM-Antwort erhalten (%d Zeichen)", len(content))

        # 4. Parsen
        result = _parse_llm_response(content)
        result["ticker"] = ticker
        result["model"] = settings.LLM_MODEL
        return result

    except httpx.TimeoutException:
        logger.error("LLM-Anfrage Timeout nach 120s für %s", ticker)
        return {
            "recommendation": "",
            "confidence": 0,
            "reasoning": "",
            "risks": [],
            "opportunities": [],
            "error": "LLM-Anfrage Timeout. Der Server hat nicht rechtzeitig geantwortet.",
        }
    except httpx.HTTPStatusError as e:
        logger.error("LLM API Fehler %d: %s", e.response.status_code, e.response.text[:500])
        return {
            "recommendation": "",
            "confidence": 0,
            "reasoning": "",
            "risks": [],
            "opportunities": [],
            "error": f"LLM API Fehler (HTTP {e.response.status_code}). Bitte prüfe die Konfiguration.",
        }
    except Exception as e:
        logger.error("Unerwarteter Fehler bei LLM-Anfrage: %s", e)
        return {
            "recommendation": "",
            "confidence": 0,
            "reasoning": "",
            "risks": [],
            "opportunities": [],
            "error": f"Unerwarteter Fehler: {str(e)}",
        }
