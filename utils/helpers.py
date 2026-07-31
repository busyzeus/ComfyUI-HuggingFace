# ================================================
# File: utils/helpers.py
# ================================================
import os
import urllib.parse
import re 
from pathlib import Path
from typing import Optional, List, Dict, Any

import folder_paths 

# Import config values needed here
from ..config import PLUGIN_ROOT, MODEL_TYPE_DIRS

# Canonical aliases for model type/folder names. Values are preferred folder names.
MODEL_TYPE_ALIASES = {
    "checkpoint": "checkpoints",
    "checkpoints": "checkpoints",
    "diffusionmodel": "diffusion_models",
    "diffusionmodels": "diffusion_models",
    "diffusion_model": "diffusion_models",
    "diffusion_models": "diffusion_models", # Wan 2.2 and similar go here
    "diffusers": "diffusers",  
    "unet": "unet",  # GGUF models go here
    "lora": "loras",
    "loras": "loras",
    "locon": "loras",
    "lycoris": "loras",
    "vae": "vae",
    "embedding": "embeddings",
    "embeddings": "embeddings",
    "textualinversion": "embeddings",
    "hypernetwork": "hypernetworks",
    "hypernetworks": "hypernetworks",
    "controlnet": "controlnet",
    "upscaler": "upscale_models",
    "upscalers": "upscale_models",
    "upscale_model": "upscale_models",
    "upscale_models": "upscale_models",
    "motionmodule": "motion_models",
    "motionmodules": "motion_models",
    "motion_model": "motion_models",
    "motion_models": "motion_models",
}

MODEL_TYPE_ALIASES_COMPACT = {
    re.sub(r'[^a-z0-9]', '', k): v for k, v in MODEL_TYPE_ALIASES.items()
}

def _get_models_dir() -> Optional[str]:
    """ComfyUI's main models/ directory, or None if it cannot be located."""
    models_dir = getattr(folder_paths, 'models_dir', None)
    if not models_dir:
        base = getattr(folder_paths, 'base_path', None)
        models_dir = os.path.join(base, 'models') if base else None
    return models_dir if models_dir and os.path.isdir(models_dir) else None

def _resolve_models_subdir(name: str) -> Optional[str]:
    """Return the real path of models/<name>, matching case-insensitively.

    The Model Type dropdown is built from the actual folder names under models/
    (see server/routes/GetModelTypes.py) but they reach us lowercased, so 'llm'
    still has to find the folder named 'LLM'.
    """
    models_dir = _get_models_dir()
    if not models_dir or not name:
        return None
    candidate = os.path.join(models_dir, name)
    if os.path.isdir(candidate):
        return candidate
    try:
        for entry in os.listdir(models_dir):
            if entry.lower() == name.lower() and os.path.isdir(os.path.join(models_dir, entry)):
                return os.path.join(models_dir, entry)
    except OSError:
        pass
    return None

def _comfy_folder_paths(model_type: str) -> List[str]:
    """folder_paths.get_folder_paths() without the exception handling at each call site."""
    try:
        return list(folder_paths.get_folder_paths(model_type) or [])
    except Exception:
        return []

def _normalize_model_type(model_type: str) -> str:
    """Normalize model type string to canonical form."""
    if not model_type:
        return "other"

    normalized = model_type.lower().strip()

    # Try exact match first
    if normalized in MODEL_TYPE_ALIASES:
        return MODEL_TYPE_ALIASES[normalized]

    # Try compact match (remove non-alphanumeric chars)
    compact = re.sub(r'[^a-z0-9]', '', normalized)
    if compact in MODEL_TYPE_ALIASES_COMPACT:
        return MODEL_TYPE_ALIASES_COMPACT[compact]

    # The alias table above predates most of ComfyUI's model folders
    # (text_encoders, clip_vision, audio_encoders, model_patches, ...). The type
    # dropdown offers every one of them, so accept anything ComfyUI registers or
    # that exists under models/ instead of diverting it to other_models.
    if _comfy_folder_paths(normalized) or _resolve_models_subdir(normalized):
        return normalized

    return "other"

# Extensions this downloader exists for. Anything else in a repo (scripts,
# configs, licences) is noise in a "file to download" list.
WEIGHT_EXTENSIONS = {
    ".safetensors", ".sft", ".ckpt", ".pt", ".pth", ".bin", ".gguf", ".onnx", ".pkl",
}

def infer_model_type_from_path(file_path: str) -> Optional[str]:
    """The ComfyUI models/ subfolder a repo path implies, or None.

    Repos routinely nest weights under a wrapper directory, as in
    split_files/text_encoders/qwen_3_4b_fp8_mixed.safetensors, so scan every
    directory segment and take the most specific one that names a real model
    folder. Looking only at the first segment would yield 'split_files'.
    """
    if not file_path:
        return None
    segments = [s for s in re.split(r'[\\/]+', str(file_path))[:-1] if s]
    for segment in reversed(segments):
        normalized = _normalize_model_type(segment)
        # "other" is the unknown sentinel unless the segment really says "other"
        if normalized == "other" and segment.lower() != "other":
            continue
        return normalized
    return None

def plan_split_layout(file_paths: List[str]) -> Optional[Dict[str, str]]:
    """Map every weight file to its own models/ folder, or None.

    Repos like Comfy-Org/z_image_turbo lay their weights out the way ComfyUI
    wants them (split_files/text_encoders/..., split_files/vae/...), so
    downloading the repo into one folder is always wrong - each file has its
    own destination.

    Returns None when the repo is not that shape, which covers diffusers repos
    (stabilityai/sdxl-turbo keeps loose weights at the root next to unet/ and
    vae/) and anything else that has to stay intact. Those still download whole.
    """
    weights = [p for p in file_paths
               if os.path.splitext(p)[1].lower() in WEIGHT_EXTENSIONS]
    if not weights:
        return None
    plan = {p: infer_model_type_from_path(p) for p in weights}
    if any(dest is None for dest in plan.values()):
        return None
    return plan

def _append_subdir(base_path: str, selected_subdir: str) -> str:
    """Append a user-selected subfolder, refusing to escape base_path."""
    if not selected_subdir:
        return base_path
    parts = [p for p in re.split(r'[\\/]+', selected_subdir) if p and p not in ('.', '..')]
    return os.path.join(base_path, *parts) if parts else base_path

def get_model_dir(model_type: str, explicit_save_root: str = "", selected_subdir: str = "") -> Optional[str]:
    """Get the directory path for a given model type, including any subfolder."""
    try:
        # An explicit root overrides the model type entirely
        if explicit_save_root:
            return _append_subdir(explicit_save_root, selected_subdir)

        normalized_type = _normalize_model_type(model_type)
        raw_type = (model_type or "").lower().strip()
        other_models = os.path.join(PLUGIN_ROOT, "other_models")

        if normalized_type == "other" and raw_type != "other":
            # "other" is _normalize_model_type()'s "I don't know" sentinel, so an
            # unrecognised type must not be resolved against a real models/other
            # folder. Keep it inside the plugin rather than guessing.
            base_dir = other_models
        else:
            # Ask ComfyUI first: it honours extra_model_paths.yaml and the legacy
            # aliases (e.g. diffusion_models resolving to models/unet).
            paths = _comfy_folder_paths(normalized_type)
            base_dir = paths[0] if paths else _resolve_models_subdir(normalized_type)
            if not base_dir:
                base_dir = other_models

        return _append_subdir(base_dir, selected_subdir)

    except Exception as e:
        print(f"Error getting model directory for {model_type}: {e}")
        return None

def sanitize_filename(filename: str) -> str:
    """Sanitize filename for safe file system usage."""
    if not filename:
        return "unnamed_file"
    
    # Remove invalid characters
    sanitized = re.sub(r'[<>:"/\\|?*]', '_', filename)
    
    # Remove control characters
    sanitized = re.sub(r'[\x00-\x1f\x7f]', '', sanitized)
    
    # Limit length
    if len(sanitized) > 255:
        name, ext = os.path.splitext(sanitized)
        sanitized = name[:255-len(ext)] + ext
    
    return sanitized.strip()

# URL segments that mean "this points at a path inside the repo".
# 'blob' is what the HuggingFace web UI shows in the address bar, 'resolve' is
# the raw-download form, 'tree' is a folder listing (a repo reference, not a file).
_HF_FILE_MARKERS = ("resolve", "blob", "raw")
_HF_PATH_MARKERS = _HF_FILE_MARKERS + ("tree",)

def _split_hf_url(url: str) -> tuple[str | None, str | None, str | None, str | None]:
    """Split a huggingface.co URL into (model_id, marker, ref, path).

    marker/ref/path are None when the URL only identifies a repo.
    """
    try:
        parsed = urllib.parse.urlparse(url)
    except Exception as e:
        print(f"Warning: Could not parse HF URL '{url}': {e}")
        return None, None, None, None

    if "huggingface.co" not in parsed.netloc.lower():
        return None, None, None, None

    parts = [p for p in parsed.path.split('/') if p]
    if len(parts) < 2:
        return None, None, None, None

    model_id = "/".join(parts[:2])
    if len(parts) >= 4 and parts[2] in _HF_PATH_MARKERS:
        # /<owner>/<repo>/<marker>/<ref>/<path...>
        return model_id, parts[2], urllib.parse.unquote(parts[3]), "/".join(parts[4:])
    return model_id, None, None, None

def parse_huggingface_input(url_or_id: str) -> tuple[str | None, str | None]:
    """
    Parses HuggingFace URL or ID string.
    Returns: (model_id, filename) tuple. Both can be None.

    filename is None when the input names a whole repo, which makes the caller
    download every file in it - so single-file URLs must be recognised here.
    Handles:
    - https://huggingface.co/Comfy-Org/gemma-4/blob/main/text_encoders/model.safetensors
    - https://huggingface.co/Comfy-Org/gemma-4/resolve/main/text_encoders/model.safetensors
    - https://huggingface.co/Comfy-Org/gemma-4
    - Comfy-Org/gemma-4
    """
    if not url_or_id:
        return None, None

    url_or_id = str(url_or_id).strip()

    # Plain "owner/repo", no scheme
    if "/" in url_or_id and not url_or_id.startswith("http"):
        parts = [p for p in url_or_id.split("/") if p]
        if len(parts) >= 2:
            model_id = "/".join(parts[0:2])
            print(f"Parsed HF model ID: {model_id}")
            return model_id, None
        return None, None

    model_id, marker, _ref, path = _split_hf_url(url_or_id)
    if not model_id:
        print(f"Input '{url_or_id}' is not a recognizable HF model ID or URL.")
        return None, None

    if marker in _HF_FILE_MARKERS and path:
        print(f"Parsed HF file URL - Model: {model_id}, File: {path}")
        return model_id, path

    print(f"Parsed HF URL - Model: {model_id}")
    return model_id, None

def hf_ref_from_url(url_or_id: str) -> str:
    """The branch/tag/commit a HuggingFace file URL points at. Defaults to 'main'."""
    if not url_or_id:
        return "main"
    url_or_id = str(url_or_id).strip()
    if not url_or_id.startswith("http"):
        return "main"
    _model_id, marker, ref, _path = _split_hf_url(url_or_id)
    if marker in _HF_FILE_MARKERS and ref:
        return ref
    return "main"

def get_model_folder_paths(model_type: str) -> List[str]:
    """Get all folder paths for a given model type."""
    try:
        normalized_type = _normalize_model_type(model_type)
        return folder_paths.get_folder_paths(normalized_type)
    except:
        return []

def get_model_type_folder_name(model_type: str) -> str:
    """Get the standard folder name for a model type."""
    return _normalize_model_type(model_type)
