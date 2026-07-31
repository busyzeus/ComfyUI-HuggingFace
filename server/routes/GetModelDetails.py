# ================================================
# File: server/routes/GetModelDetails.py
# ================================================
import os
import re
import traceback
from aiohttp import web

import server # ComfyUI server instance
from ..utils import get_request_json, resolve_huggingface_api_key
from ...utils.helpers import parse_huggingface_input, hf_ref_from_url

prompt_server = server.PromptServer.instance

# Files that are never a model weight worth previewing as a download target
_NON_MODEL_FILES = {".gitattributes", "README.md", ".gitignore"}
DESCRIPTION_LIMIT = 4000


def _iso(value):
    """Datetimes from huggingface_hub are not JSON serialisable."""
    return value.isoformat() if hasattr(value, "isoformat") else (value or "")


def _strip_frontmatter(text: str) -> str:
    """Remove a model card's leading YAML frontmatter block."""
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end != -1:
            text = text[end + 4:]
    return text.lstrip()


def _fetch_description(model_id: str, ref: str, api_key) -> str:
    """The model card body as plain text.

    ModelCard.load() raises on some repos (KeyError on Comfy-Org/gemma-4, for
    one), so read the raw README instead and let the frontend escape it.
    """
    import requests
    url = f"https://huggingface.co/{model_id}/raw/{ref}/README.md"
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    try:
        response = requests.get(url, headers=headers, timeout=15)
        if response.status_code != 200:
            return ""
        text = _strip_frontmatter(response.text)
        return text[:DESCRIPTION_LIMIT] + ("\n..." if len(text) > DESCRIPTION_LIMIT else "")
    except Exception as e:
        print(f"[GetModelDetails] Could not read README for {model_id}: {e}")
        return ""


def _infer_model_type(files, selected_file):
    """Guess the ComfyUI models/ subfolder from the repo layout.

    HuggingFace has no equivalent of Civitai's model type, but Comfy-Org repos
    put weights in a folder named after the ComfyUI folder they belong in
    (text_encoders/, diffusion_models/, vae/, ...), which is a good enough hint
    for pre-selecting the save location.
    """
    if selected_file and "/" in selected_file:
        return selected_file.split("/")[0]
    folders = {f["path"].split("/")[0] for f in files if "/" in f["path"]}
    return folders.pop() if len(folders) == 1 else None


@prompt_server.routes.post("/api/huggingface/get_model_details")
async def route_get_model_details(request):
    """API Endpoint to fetch model details from a HuggingFace repo."""
    try:
        data = await get_request_json(request)
        model_url_or_id = data.get("model_url_or_id")
        resolved_api_key = resolve_huggingface_api_key(data)

        if not model_url_or_id:
            raise web.HTTPBadRequest(reason="Missing 'model_url_or_id'")

        parsed_model_id, parsed_filename = parse_huggingface_input(model_url_or_id)
        if not parsed_model_id:
            raise web.HTTPBadRequest(
                reason=f"Could not parse HuggingFace model ID from: {model_url_or_id}")

        ref = hf_ref_from_url(model_url_or_id)

        try:
            from huggingface_hub import HfApi
            info = HfApi(token=resolved_api_key).model_info(
                parsed_model_id, revision=ref, files_metadata=True)
        except Exception as e:
            print(f"[GetModelDetails] model_info failed for {parsed_model_id}: {e}")
            # HuggingFace answers 401 for both private and non-existent repos,
            # so don't guess which - and don't dump the raw traceback in the panel.
            status = getattr(getattr(e, "response", None), "status_code", None)
            if status in (401, 403, 404):
                message = (f"'{parsed_model_id}' is not accessible - it may not exist, "
                           f"or it may be private or gated. A token in Settings may help.")
            else:
                message = f"Could not read '{parsed_model_id}': {type(e).__name__}"
            return web.json_response({
                "success": False,
                "model_id": parsed_model_id,
                "error": message,
            })

        files = sorted(
            ({"path": s.rfilename, "size": getattr(s, "size", None)}
             for s in (info.siblings or [])
             if os.path.basename(s.rfilename) not in _NON_MODEL_FILES),
            key=lambda f: f["path"],
        )

        card_data = getattr(info, "cardData", None) or {}
        base_model = card_data.get("base_model") or []
        if isinstance(base_model, str):
            base_model = [base_model]

        return web.json_response({
            "success": True,
            "model_id": parsed_model_id,
            "model_name": parsed_model_id.split("/")[-1],
            "creator_username": getattr(info, "author", None) or parsed_model_id.split("/")[0],
            "description": _fetch_description(parsed_model_id, ref, resolved_api_key),
            "license": card_data.get("license") or "Unknown",
            "tags": [t for t in (getattr(info, "tags", None) or []) if ":" not in t],
            "base_model": base_model,
            "revision": ref,
            "files": files,
            "selected_file": parsed_filename,
            "model_type": _infer_model_type(files, parsed_filename),
            "hf_url": f"https://huggingface.co/{parsed_model_id}",
            "stats": {
                "downloads": getattr(info, "downloads", 0) or 0,
                "likes": getattr(info, "likes", 0) or 0,
                "created_at": _iso(getattr(info, "created_at", None)),
                "modified_at": _iso(getattr(info, "lastModified", None)),
            },
        })

    except web.HTTPException:
        raise
    except Exception as e:
        print(f"Error in get_model_details: {e}")
        traceback.print_exc()
        return web.json_response({"error": "Internal Server Error", "details": str(e)}, status=500)
