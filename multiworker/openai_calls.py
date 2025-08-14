# File: multiworker/openai_calls.py
import asyncio
import re
import math
from typing import Dict, List
from openai import AsyncOpenAI

from . import config

# ---------- Retry telemetry (for Stats footer) ----------
_RETRY_COUNT = 0          # total number of retry attempts (sleeps)
_RETRY_EVENTS = 0         # number of requests that required at least one retry
_RETRY_DELAYS: list[float] = []  # seconds slept per retry


def get_retry_stats(reset: bool = False) -> dict:
    """Return aggregate retry telemetry. Optionally reset after reading."""
    global _RETRY_COUNT, _RETRY_EVENTS, _RETRY_DELAYS
    stats = {
        "retries_total": _RETRY_COUNT,
        "retry_events": _RETRY_EVENTS,
        "delays": list(_RETRY_DELAYS),
    }
    if reset:
        _RETRY_COUNT = 0
        _RETRY_EVENTS = 0
        _RETRY_DELAYS.clear()
    return stats


def _extract_output_text(resp) -> str:
    txt = getattr(resp, "output_text", None)
    if isinstance(txt, str) and txt.strip():
        return txt.strip()
    try:
        chunks = []
        for item in getattr(resp, "output", []):
            for block in getattr(item, "content", []):
                if getattr(block, "type", None) == "output_text":
                    chunks.append(getattr(block, "text", ""))
        if chunks:
            return "".join(chunks).strip()
    except Exception:
        pass
    return str(resp)


async def _request_with_retries(coro_factory):
    """
    Retry wrapper:
      - Up to config.RETRY_MAX times
      - Waits at least config.RETRY_DELAY_SEC between tries
      - If a 429/rate-limit suggests a wait (Retry-After header or 'try again in Xs'),
        sleep for max(RETRY_DELAY_SEC, suggested).
      - Records telemetry for Stats footer.
    """
    global _RETRY_COUNT, _RETRY_EVENTS, _RETRY_DELAYS

    last_err = None
    any_retry_this_call = False

    for attempt in range(1, config.RETRY_MAX + 1):
        try:
            return await coro_factory()
        except Exception as e:
            last_err = e

            # Base delay from config
            delay = float(config.RETRY_DELAY_SEC)

            # Respect Retry-After header if available
            try:
                resp = getattr(e, "response", None)
                if resp is not None:
                    ra = resp.headers.get("retry-after") or resp.headers.get("Retry-After")
                    if ra:
                        try:
                            delay = max(delay, float(ra))
                        except Exception:
                            pass
            except Exception:
                pass

            # Parse "... Please try again in 29.786s."
            try:
                msg = str(e)
                m = re.search(r"try again in\s+([0-9]+(?:\.[0-9]+)?)s", msg, re.IGNORECASE)
                if m:
                    suggested = float(m.group(1))
                    delay = max(delay, math.ceil(suggested))
            except Exception:
                pass

            if attempt < config.RETRY_MAX:
                # Telemetry
                if not any_retry_this_call:
                    _RETRY_EVENTS += 1
                    any_retry_this_call = True
                _RETRY_COUNT += 1
                _RETRY_DELAYS.append(delay)

                await asyncio.sleep(delay)
            else:
                raise last_err


async def call_worker(client: AsyncOpenAI, history: List[Dict[str, str]]) -> str:
    async def _do():
        return await client.responses.create(
            model=config.CURRENT_MODEL,
            instructions=config.WORKER_INSTRUCTION,
            input=history,
            reasoning=config.reasoning_dict(),
            text=config.text_dict(),
        )
    resp = await _request_with_retries(_do)
    return _extract_output_text(resp)


async def call_synth(client: AsyncOpenAI, history: List[Dict[str, str]], drafts: Dict[str, str]) -> str:
    stitched = "\n\n".join(f"### {name}\n{text.strip()}" for name, text in drafts.items())
    synth_input = history + [{"role": "assistant", "content": "WORKER DRAFTS:\n" + stitched}]
    async def _do():
        return await client.responses.create(
            model=config.CURRENT_MODEL,
            instructions=config.SYNTH_INSTRUCTION,
            input=synth_input,
            reasoning=config.reasoning_dict(),
            text=config.text_dict(),
        )
    resp = await _request_with_retries(_do)
    return _extract_output_text(resp)
