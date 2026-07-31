# ================================================
# File: server/utils.py
# ================================================
import os
from typing import Any, Dict, Optional
from aiohttp import web

async def get_request_json(request):
    """Safely get JSON data from request."""
    try:
        return await request.json()
    except Exception as e:
        print(f"Error parsing request JSON: {e}")
        raise web.HTTPBadRequest(reason=f"Invalid JSON format: {e}")

def resolve_huggingface_api_key(payload: Optional[Dict[str, Any]] = None) -> Optional[str]:
    """
    Resolve API key priority:
    1) Explicit key from request payload (`api_key`)
    2) `HUGGINGFACE_TOKEN` environment variable
    """
    request_key = ""
    if isinstance(payload, dict):
        raw_key = payload.get("api_key", "")
        if isinstance(raw_key, str):
            request_key = raw_key.strip()

    if request_key:
        return request_key

    env_key = os.getenv("HUGGINGFACE_TOKEN", "").strip()
    if env_key:
        return env_key

    return None
