# ================================================
# File: tests/test_helpers.py
# Path/URL resolution tests for utils/helpers.py
#
# Run from anywhere with ComfyUI's python:
#   python_embeded/python.exe ComfyUI/custom_nodes/ComfyUI-HuggingFace/tests/test_helpers.py
# ================================================
import importlib
import os
import sys

PLUGIN_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
CUSTOM_NODES_DIR = os.path.dirname(PLUGIN_DIR)
COMFY_ROOT = os.path.dirname(CUSTOM_NODES_DIR)

sys.path.insert(0, COMFY_ROOT)        # so `import folder_paths` works
sys.path.insert(0, CUSTOM_NODES_DIR)  # so the dashed package name is importable

import folder_paths  # noqa: E402

helpers = importlib.import_module("ComfyUI-HuggingFace.utils.helpers")

MODELS_DIR = folder_paths.models_dir

GEMMA_BLOB = ("https://huggingface.co/Comfy-Org/gemma-4/blob/main/"
              "text_encoders/gemma4_e4b_it_fp8_scaled.safetensors")
GEMMA_RESOLVE = GEMMA_BLOB.replace("/blob/", "/resolve/")
GEMMA_FILE = "text_encoders/gemma4_e4b_it_fp8_scaled.safetensors"

failures = []


def check(label, got, want):
    ok = got == want
    print(f"  [{'PASS' if ok else 'FAIL'}] {label}")
    if not ok:
        print(f"         got:  {got!r}")
        print(f"         want: {want!r}")
        failures.append(label)


# The Model Type dropdown is built from every folder under models/ (GetModelTypes.py),
# so every one of those folders must resolve to that same folder on the backend.
print("get_model_dir(): UI-offered types resolve to the real ComfyUI folder")
for model_type in ["text_encoders", "checkpoints", "loras", "vae",
                   "clip_vision", "controlnet", "upscale_models"]:
    check(f"get_model_dir({model_type!r})",
          helpers.get_model_dir(model_type),
          os.path.join(MODELS_DIR, model_type))

print("get_model_dir(): Save Subfolder applies without an explicit root")
check("get_model_dir('text_encoders', '', 'gemma')",
      helpers.get_model_dir("text_encoders", "", "gemma"),
      os.path.join(MODELS_DIR, "text_encoders", "gemma"))
check("get_model_dir('checkpoints', '', 'sdxl/turbo') normalizes separators",
      helpers.get_model_dir("checkpoints", "", "sdxl/turbo"),
      os.path.join(MODELS_DIR, "checkpoints", "sdxl", "turbo"))
check("get_model_dir('vae', '', '../../escape') cannot escape the base dir",
      helpers.get_model_dir("vae", "", "../../escape"),
      os.path.join(MODELS_DIR, "vae", "escape"))

print("get_model_dir(): an explicit root still wins")
check("get_model_dir('vae', 'D:/models', 'sub')",
      helpers.get_model_dir("vae", "D:/models", "sub"),
      os.path.join("D:/models", "sub"))

print("get_model_dir(): a genuinely unknown type stays inside the plugin")
check("get_model_dir('not_a_real_model_folder')",
      helpers.get_model_dir("not_a_real_model_folder"),
      os.path.join(helpers.PLUGIN_ROOT, "other_models"))
# 'other' is the unknown-type sentinel, but models/other is also a real folder,
# so asking for it by name must not be mistaken for "unrecognised".
check("get_model_dir('other') when models/other exists",
      helpers.get_model_dir("other"),
      os.path.join(MODELS_DIR, "other"))

# A /blob/ URL is what the HuggingFace web UI puts on your clipboard. Losing the
# filename here makes DownloadModel fall back to snapshot_download(), i.e. the
# whole repo instead of the one file that was asked for.
print("parse_huggingface_input(): single-file URLs keep their file path")
check("blob URL", helpers.parse_huggingface_input(GEMMA_BLOB),
      ("Comfy-Org/gemma-4", GEMMA_FILE))
check("resolve URL", helpers.parse_huggingface_input(GEMMA_RESOLVE),
      ("Comfy-Org/gemma-4", GEMMA_FILE))
check("resolve URL on a non-main ref",
      helpers.parse_huggingface_input(
          "https://huggingface.co/Comfy-Org/gemma-4/resolve/deadbeef/config.json"),
      ("Comfy-Org/gemma-4", "config.json"))

print("parse_huggingface_input(): repo references still mean 'whole repo'")
check("repo root URL",
      helpers.parse_huggingface_input("https://huggingface.co/Comfy-Org/gemma-4"),
      ("Comfy-Org/gemma-4", None))
check("repo root URL with trailing slash",
      helpers.parse_huggingface_input("https://huggingface.co/Comfy-Org/gemma-4/"),
      ("Comfy-Org/gemma-4", None))
check("plain repo id",
      helpers.parse_huggingface_input("Comfy-Org/gemma-4"),
      ("Comfy-Org/gemma-4", None))
check("tree URL (folder listing, not a file)",
      helpers.parse_huggingface_input(
          "https://huggingface.co/Comfy-Org/gemma-4/tree/main/text_encoders"),
      ("Comfy-Org/gemma-4", None))

print("hf_ref_from_url(): the branch/commit in the URL is preserved")
check("blob URL -> main", helpers.hf_ref_from_url(GEMMA_BLOB), "main")
check("sha URL -> sha",
      helpers.hf_ref_from_url(
          "https://huggingface.co/Comfy-Org/gemma-4/resolve/deadbeef/config.json"),
      "deadbeef")
check("repo root -> main",
      helpers.hf_ref_from_url("https://huggingface.co/Comfy-Org/gemma-4"), "main")
check("plain repo id -> main", helpers.hf_ref_from_url("Comfy-Org/gemma-4"), "main")

print()
if failures:
    print(f"{len(failures)} FAILED:")
    for name in failures:
        print(f"  - {name}")
    sys.exit(1)
print("all checks passed")
