# ================================================
# File: config.py
# ================================================
import os
import folder_paths # Use ComfyUI's folder_paths

# --- Configuration ---
MAX_CONCURRENT_DOWNLOADS = 3
DEFAULT_CHUNK_SIZE = 1024 * 1024  # 1MB
DEFAULT_CONNECTIONS = 4
DOWNLOAD_HISTORY_LIMIT = 100
DOWNLOAD_TIMEOUT = 60 # Timeout for individual download chunks/requests (seconds)
HEAD_REQUEST_TIMEOUT = 25 # Timeout for initial HEAD request (seconds)

# --- Paths ---
# The root directory of *this specific plugin/extension*
# Calculated based on the location of this config.py file
PLUGIN_ROOT = os.path.dirname(os.path.realpath(__file__))

# Construct web paths relative to the plugin's root directory
WEB_DIRECTORY = os.path.join(PLUGIN_ROOT, "web")
JAVASCRIPT_PATH = os.path.join(WEB_DIRECTORY, "js")
CSS_PATH = os.path.join(WEB_DIRECTORY, "css")
# Corrected path construction to avoid issues with leading slashes
PLACEHOLDER_IMAGE_PATH = os.path.join(WEB_DIRECTORY, "images", "placeholder.jpg")

# Get ComfyUI directories using folder_paths
COMFYUI_ROOT_DIR = folder_paths.base_path
# MODELS_DIR removed; resolve per-type via folder_paths

# --- Model Types ---
# Maps the internal key (lowercase) to a tuple: (display_name, folder_paths_type)
# The folder_paths_type is used by ComfyUI's folder_paths.get_directory_by_type().
MODEL_TYPE_DIRS = {
    "checkpoint": ("Checkpoint", "checkpoints"),
    "diffusionmodels": ("Diffusion Models", "diffusion_models"),  # Wan 2.2 and similar
    "diffusers": ("diffusers"), #Diffusers Models
    "unet": ("Unet", "unet"),  # GGUF models
    "lora": ("Lora", "loras"),
    "locon": ("LoCon", "loras"),
    "lycoris": ("LyCORIS", "loras"),
    "vae": ("VAE", "vae"),
    "embedding": ("Embedding", "embeddings"),
    "hypernetwork": ("Hypernetwork", "hypernetworks"),
    "controlnet": ("ControlNet", "controlnet"),
    "upscaler": ("Upscaler", "upscale_models"),
    "motionmodule": ("Motion Module", "motion_models"),
    "poses": ("Poses", "poses"),
    "wildcards": ("Wildcards", "wildcards"),
    # 'other' will save to a dedicated folder inside the HuggingFace extension directory
    "other": ("Other", None)
}

# --- Log Initial Paths for Verification ---
print("-" * 30)
print("[HuggingFace Config Initialized]")
print(f"  - Plugin Root: {PLUGIN_ROOT}")
print(f"  - Web Directory: {WEB_DIRECTORY}")
print(f"  - ComfyUI Base Path: {COMFYUI_ROOT_DIR}")
print("-" * 30)
