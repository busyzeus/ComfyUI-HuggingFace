# ================================================
# File: server/routes/DownloadModel.py
# ================================================
import asyncio
import os
import json
import traceback
import re
import urllib.parse
from aiohttp import web

import server # ComfyUI server instance
from ..utils import get_request_json, resolve_huggingface_api_key
from ...downloader.manager import manager as download_manager
from ...api.huggingface import HuggingFaceAPI
from ...utils.helpers import (
    get_model_dir, parse_huggingface_input, sanitize_filename, hf_ref_from_url,
    plan_split_layout,
)

prompt_server = server.PromptServer.instance


def _file_url(model_id: str, ref: str, file_path: str) -> str:
    return (f"https://huggingface.co/{model_id}/resolve/"
            f"{urllib.parse.quote(ref, safe='')}/{urllib.parse.quote(file_path)}")


def _queue_split_layout(plan, *, model_url_or_id, model_id, ref, model_info,
                        explicit_save_root, selected_subdir, num_connections,
                        force_redownload, api_key):
    """Queue one download per file, each into the folder its own path implies."""
    queued, skipped = [], []
    for file_path, dest_type in sorted(plan.items()):
        target_dir = get_model_dir(dest_type, explicit_save_root, selected_subdir)
        if not target_dir:
            print(f"[HF Download] No directory for '{dest_type}', skipping {file_path}")
            continue

        filename = os.path.basename(file_path)
        save_path = os.path.join(target_dir, filename)
        if os.path.exists(save_path) and not force_redownload:
            skipped.append(filename)
            continue

        url = _file_url(model_id, ref, file_path)
        download_id = download_manager.add_to_queue({
            "model_url_or_id": model_url_or_id,
            "save_path": save_path,
            "output_path": save_path,
            "url": url,
            "download_url": url,
            "filename": filename,
            "model_type": dest_type,
            "huggingface_model_info": model_info,
            "huggingface_filename": file_path,
            "num_connections": num_connections,
            "force_redownload": force_redownload,
            "api_key": api_key,
            "known_size": None,
            "thumbnail": None,
            "custom_filename": "",
            "huggingface_model_name": model_info.get("name"),
        })
        queued.append({"download_id": download_id, "filename": filename,
                       "model_type": dest_type, "save_path": save_path})
    return queued, skipped

@prompt_server.routes.post("/api/huggingface/download")
async def route_download_model(request):
    """API Endpoint to initiate a download."""
    try:
        data = await get_request_json(request)

        model_url_or_id = data.get("model_url_or_id")
        model_type_value = data.get("model_type", "checkpoint")
        explicit_save_root = (data.get("save_root") or "").strip()
        custom_filename_input = data.get("custom_filename", "").strip()
        selected_subdir = (data.get("subdir") or "").strip()
        num_connections = int(data.get("num_connections", 4))
        force_redownload = bool(data.get("force_redownload", False))
        resolved_api_key = resolve_huggingface_api_key(data)

        if not model_url_or_id:
            raise web.HTTPBadRequest(reason="Missing 'model_url_or_id'")

        print(f"[HF Download] Request: {model_url_or_id}, SaveType: {model_type_value}")
        
        # Parse HuggingFace URL/ID
        parsed_model_id, parsed_filename = parse_huggingface_input(model_url_or_id)
        
        if not parsed_model_id:
            raise web.HTTPBadRequest(reason=f"Could not parse HuggingFace model ID from: {model_url_or_id}")
        
        target_model_id = parsed_model_id
        print(f"[HF Download] Parsed Model ID: {target_model_id}")
        
        # Initialize API
        api = HuggingFaceAPI(resolved_api_key)
        
        if parsed_filename:
            # Direct download from URL - skip API calls
            target_filename = parsed_filename
            # Try to get model name from the model_id itself
            model_name = target_model_id.split('/')[-1] if target_model_id else "Unknown Model"
            model_info = {"id": target_model_id, "name": model_name}
            print(f"[HF Download] Direct download file: {target_filename}")
            print(f"[HF Download] Using extracted model name: {model_name}")
        else:
            # Skip API calls for public repos, use only huggingface_hub
            if resolved_api_key:
                # For private repos, try API calls to get model info
                api = HuggingFaceAPI(resolved_api_key)
                model_info = api.get_model_info(target_model_id)
                
                if not model_info or "error" in model_info:
                    print(f"[HF Download] Model info failed, using huggingface_hub directly")
                    target_filename = parsed_filename if parsed_filename else None
                    model_info = {"id": target_model_id, "name": target_model_id.split('/')[-1]}
                else:
                    # For private repos, still use huggingface_hub for download
                    target_filename = parsed_filename if parsed_filename else None
            else:
                # For public repos, skip API calls entirely
                print(f"[HF Download] Public repo, using huggingface_hub directly")
                target_filename = parsed_filename if parsed_filename else None
                model_info = {"id": target_model_id, "name": target_model_id.split('/')[-1]}
        
        if not target_filename:
            print(f"[HF Download] No specific file found, letting huggingface_hub auto-detect")
            target_filename = None
        
        print(f"[HF Download] Target file: {target_filename}")

        ref_name = hf_ref_from_url(model_url_or_id)

        # A repo laid out the way ComfyUI wants (split_files/text_encoders/...)
        # has no single correct save location, so send each file to its own.
        if target_filename is None:
            plan = None
            try:
                from huggingface_hub import HfApi
                # Synchronous and requests-backed, so it runs off the event
                # loop - otherwise every whole-repo download freezes ComfyUI
                # until HuggingFace answers.
                repo_info = await asyncio.to_thread(
                    lambda: HfApi(token=resolved_api_key).model_info(
                        target_model_id, revision=ref_name))
                plan = plan_split_layout([s.rfilename for s in (repo_info.siblings or [])])
            except Exception as e:
                print(f"[HF Download] Could not inspect {target_model_id} for a split layout: {e}")

            if plan:
                print(f"[HF Download] Split layout: routing {len(plan)} files individually")
                queued, skipped = _queue_split_layout(
                    plan,
                    model_url_or_id=model_url_or_id, model_id=target_model_id,
                    ref=ref_name, model_info=model_info,
                    explicit_save_root=explicit_save_root,
                    selected_subdir=selected_subdir,
                    num_connections=num_connections,
                    force_redownload=force_redownload,
                    api_key=resolved_api_key,
                )
                if not queued:
                    raise web.HTTPBadRequest(
                        reason=f"All {len(skipped)} files already exist. "
                               f"Tick Force Re-download to replace them.")
                return web.json_response({
                    "status": "queued",
                    "per_file_destinations": True,
                    "queued": queued,
                    "skipped": skipped,
                    "huggingface_model_id": target_model_id,
                    "details": {
                        "filename": f"{len(queued)} files from {target_model_id}",
                    },
                })

        # Determine save directory
        target_dir = get_model_dir(model_type_value, explicit_save_root, selected_subdir)
        if not target_dir:
            raise web.HTTPBadRequest(reason=f"Invalid model type: {model_type_value}")

        # Determine filename
        if custom_filename_input:
            final_filename = sanitize_filename(custom_filename_input)
        elif target_filename is None:
            # For repo downloads, use model name as folder
            final_filename = model_info.get("name", target_model_id.split('/')[-1])
        else:
            final_filename = os.path.basename(target_filename)
        
        save_path = os.path.join(target_dir, final_filename)

        # Check if file exists
        if os.path.exists(save_path) and not force_redownload:
            raise web.HTTPBadRequest(reason=f"File already exists: {final_filename}")

        # Start download
        if target_filename is None:
            # For repo downloads, don't construct URL - let huggingface_hub handle it
            download_url = None
        else:
            # Keep the branch/commit the user pasted instead of assuming 'main'
            download_url = _file_url(target_model_id, ref_name, target_filename)
        
        download_info = {
            "model_url_or_id": model_url_or_id,
            "save_path": save_path,
            "output_path": save_path,  # Add this for ChunkDownloader
            "url": download_url,  # Add this for ChunkDownloader
            "filename": final_filename,
            "model_type": model_type_value,
            "download_url": download_url,
            "huggingface_model_info": model_info,
            "huggingface_filename": target_filename,
            "num_connections": num_connections,
            "force_redownload": force_redownload,
            # Add missing fields to prevent warnings
            "api_key": resolved_api_key,
            "known_size": None,
            "thumbnail": None,
            "custom_filename": custom_filename_input,
            "huggingface_model_name": model_info.get("name", target_model_id.split('/')[-1])
        }

        download_id = download_manager.add_to_queue(download_info)
        
        # Extract model name from model_info if available, otherwise from model_id
        print(f"[DEBUG] model_info: {model_info}")
        print(f"[DEBUG] target_model_id: {target_model_id}")
        
        # Try to parse model_info as JSON if it's a string
        parsed_model_info = None
        if isinstance(model_info, str):
            try:
                import json
                parsed_model_info = json.loads(model_info)
                print(f"[DEBUG] Parsed model_info from JSON: {parsed_model_info}")
            except:
                print(f"[DEBUG] Failed to parse model_info as JSON")
                parsed_model_info = None
        else:
            parsed_model_info = model_info
        
        if parsed_model_info and isinstance(parsed_model_info, dict) and parsed_model_info.get('name'):
            model_display_name = parsed_model_info['name']
            print(f"[DEBUG] Using parsed model_info name: {model_display_name}")
        elif model_info and isinstance(model_info, dict) and model_info.get('name'):
            model_display_name = model_info['name']
            print(f"[DEBUG] Using model_info name: {model_display_name}")
        else:
            model_display_name = target_model_id.split('/')[-1] if target_model_id else "Unknown Model"
            print(f"[DEBUG] Using parsed name: {model_display_name}")
        
        print(f"[DEBUG] Final model_display_name: {model_display_name}")
        
        response_data = {
            "download_id": download_id,
            "huggingface_model_id": target_model_id,
            "huggingface_model_name": model_display_name,  # Add model name
            "huggingface_filename": target_filename,
            "huggingface_model_info": model_info,
            "save_path": save_path,
            "filename": final_filename,
            "status": "queued"  # Changed from "started" to "queued" to match frontend expectation
        }
        
        print(f"[DEBUG] Response data huggingface_model_name: {response_data['huggingface_model_name']}")

        return web.json_response(response_data)

    except web.HTTPException:
        raise
    except Exception as e:
        print(f"--- Unhandled Error in /huggingface/download ---")
        traceback.print_exc()
        raise web.HTTPInternalServerError(reason=str(e))
