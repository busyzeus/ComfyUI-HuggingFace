# ================================================
# File: server/routes/SearchModels.py
# ================================================
import asyncio
import traceback
from itertools import islice
from aiohttp import web

import server  # ComfyUI server instance
from ..utils import get_request_json, resolve_huggingface_api_key

prompt_server = server.PromptServer.instance

# Each category maps to exactly one HuggingFace filter tag. There is deliberately
# no task category: Comfy-Org repos leave pipeline_tag empty, so filtering by
# task hides the repos this downloader exists for.
CATEGORY_FILTERS = {
    "any": None,
    "lora": "lora",
    "gguf": "gguf",
    "diffusers": "diffusers",
}

# huggingface_hub rejects any other sort value with BadRequestError
SORT_VALUES = {
    "Most Downloaded": "downloads",
    "Trending": "trendingScore",
    "Most Liked": "likes",
    "Recently Updated": "lastModified",
    "Newest": "createdAt",
}

COMFYUI_TAG = "comfyui"
DEFAULT_SORT = "downloads"
MAX_LIMIT = 100


def build_filters(category, comfyui_only):
    """The `filter` argument for list_models. The API ANDs the entries."""
    filters = []
    if comfyui_only:
        filters.append(COMFYUI_TAG)
    category_filter = CATEGORY_FILTERS.get((category or "any").strip().lower())
    if category_filter:
        filters.append(category_filter)
    return filters


def format_model(model):
    """One search result, in the shape searchRenderer.js consumes."""
    owner = model.id.split("/")[0]
    last_modified = getattr(model, "last_modified", None)
    return {
        "id": model.id,
        "name": model.id.split("/")[-1],
        "author": getattr(model, "author", None) or owner,
        "downloads": getattr(model, "downloads", 0) or 0,
        "likes": getattr(model, "likes", 0) or 0,
        "tags": [t for t in (getattr(model, "tags", None) or []) if ":" not in t],
        "updated": last_modified.isoformat() if last_modified else "",
        "gated": bool(getattr(model, "gated", False)),
    }


@prompt_server.routes.post("/api/huggingface/search")
async def route_search_models(request):
    """API Endpoint for searching models on HuggingFace."""
    try:
        data = await get_request_json(request)

        query = (data.get("query") or "").strip()
        category = data.get("category") or "any"
        comfyui_only = bool(data.get("comfyui_only", True))
        sort_label = data.get("sort") or "Most Downloaded"
        limit = max(1, min(MAX_LIMIT, int(data.get("limit", 20))))
        page = max(1, int(data.get("page", 1)))
        resolved_api_key = resolve_huggingface_api_key(data)

        filters = build_filters(category, comfyui_only)
        if not query and not filters:
            raise web.HTTPBadRequest(
                reason="Search needs a query, a category, or ComfyUI only.")

        try:
            from huggingface_hub import HfApi
            api = HfApi(token=resolved_api_key)

            kwargs = {
                "sort": SORT_VALUES.get(sort_label, DEFAULT_SORT),
                "direction": -1,
                # Without full=True, author and last_modified come back None
                "full": True,
            }
            if query:
                kwargs["search"] = query
            if filters:
                kwargs["filter"] = filters

            print(f"[Server Search] query={query!r} filters={filters} "
                  f"sort={kwargs['sort']} page={page} limit={limit}")

            # list_models has no offset, but it pages lazily, so islice only
            # walks as far as the requested page. Taking one extra item is how
            # we learn whether a next page exists without a count endpoint.
            #
            # list_models() is a synchronous, requests-backed generator, and
            # islice() drives it with blocking HTTP calls (one per page walked
            # to reach `offset`). Run it in a worker thread so it can't stall
            # the aiohttp event loop for the whole ComfyUI server.
            offset = (page - 1) * limit
            window = await asyncio.to_thread(
                lambda: list(islice(api.list_models(**kwargs), offset, offset + limit + 1)))
        except Exception as e:
            print(f"[Server Search] list_models failed: {e}")
            return web.json_response(
                {"error": "Search failed", "details": str(e)}, status=500)

        return web.json_response({
            "items": [format_model(m) for m in window[:limit]],
            "metadata": {
                "page": page,
                "limit": limit,
                "has_more": len(window) > limit,
            },
        })

    except web.HTTPException:
        raise
    except Exception as e:
        print(f"Error in search_models: {e}")
        traceback.print_exc()
        return web.json_response(
            {"error": "Internal Server Error", "details": str(e)}, status=500)
