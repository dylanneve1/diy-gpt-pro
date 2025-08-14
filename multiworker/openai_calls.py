# File: multiworker/openai_calls.py
import asyncio
from typing import Dict, List
from openai import AsyncOpenAI

from . import config

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
    last_err = None
    for attempt in range(1, config.RETRY_MAX + 1):
        try:
            return await coro_factory()
        except Exception as e:
            last_err = e
            if attempt < config.RETRY_MAX:
                await asyncio.sleep(config.RETRY_DELAY_SEC)
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
