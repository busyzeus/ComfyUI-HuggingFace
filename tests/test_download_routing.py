# ================================================
# File: tests/test_download_routing.py
# Checks what /api/huggingface/download would queue, with the download manager
# stubbed out so nothing is actually fetched.
# Requires network access (reads real public repos).
#
# Run from anywhere with ComfyUI's python:
#   python_embeded/python.exe ComfyUI/custom_nodes/ComfyUI-HuggingFace/tests/test_download_routing.py
# ================================================
import asyncio
import importlib
import json
import os
import sys

PLUGIN_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
CUSTOM_NODES_DIR = os.path.dirname(PLUGIN_DIR)
COMFY_ROOT = os.path.dirname(CUSTOM_NODES_DIR)

sys.path.insert(0, COMFY_ROOT)
sys.path.insert(0, CUSTOM_NODES_DIR)


class _FakeRoutes:
    def post(self, _path):
        return lambda fn: fn

    def get(self, _path):
        return lambda fn: fn


class _FakeServer:
    routes = _FakeRoutes()


import server  # noqa: E402
server.PromptServer.instance = _FakeServer()

route = importlib.import_module("ComfyUI-HuggingFace.server.routes.DownloadModel")
helpers = importlib.import_module("ComfyUI-HuggingFace.utils.helpers")


class RecordingManager:
    """Stands in for the real DownloadManager so nothing hits the network."""

    def __init__(self):
        self.queued = []

    def add_to_queue(self, download_info):
        self.queued.append(download_info)
        return f"dl_{len(self.queued)}"


class FakeRequest:
    def __init__(self, payload):
        self._payload = payload

    async def json(self):
        return self._payload


def call_download(payload):
    recorder = RecordingManager()
    original = route.download_manager
    route.download_manager = recorder
    try:
        response = asyncio.run(route.route_download_model(FakeRequest(payload)))
        return recorder.queued, json.loads(response.body)
    finally:
        route.download_manager = original


failures = []


def check(label, got, want):
    ok = got == want
    print(f"  [{'PASS' if ok else 'FAIL'}] {label}")
    if not ok:
        print(f"         got:  {got!r}")
        print(f"         want: {want!r}")
        failures.append(label)


SPLIT_REPO = "Comfy-Org/z_image_turbo"
DIFFUSERS_REPO = "stabilityai/sdxl-turbo"

print(f"{SPLIT_REPO}: every file is routed to the folder its path implies")
queued, body = call_download({"model_url_or_id": SPLIT_REPO, "model_type": "checkpoints",
                              "force_redownload": True})
check("response says it routed per file", body.get("per_file_destinations"), True)
check("one queue entry per weight file", len(queued), 8)

by_name = {item["filename"]: item for item in queued}
expected_types = {
    "z_image_turbo_bf16.safetensors": "diffusion_models",
    "z_image_turbo_int8_convrot.safetensors": "diffusion_models",
    "z_image_turbo_nvfp4.safetensors": "diffusion_models",
    "z_image_turbo_distill_patch_lora_bf16.safetensors": "loras",
    "qwen_3_4b.safetensors": "text_encoders",
    "qwen_3_4b_fp4_mixed.safetensors": "text_encoders",
    "qwen_3_4b_fp8_mixed.safetensors": "text_encoders",
    "ae.safetensors": "vae",
}
check("filenames queued", sorted(by_name), sorted(expected_types))
for name, want_type in sorted(expected_types.items()):
    item = by_name.get(name) or {}
    check(f"{name} -> {want_type}", item.get("model_type"), want_type)
    # The chosen Model Type in the form must be ignored, not applied to all files
    check(f"{name} lands in the {want_type} folder",
          os.path.dirname(item.get("output_path", "")),
          helpers.get_model_dir(want_type))

check("files are flattened, not nested under split_files/",
      any("split_files" in item["output_path"] for item in queued), False)
check("each entry downloads its own file, not the repo",
      all(item["url"] and item["url"].startswith(
          f"https://huggingface.co/{SPLIT_REPO}/resolve/main/split_files/") for item in queued),
      True)
check("the .py helper script is not queued",
      any(item["filename"].endswith(".py") for item in queued), False)

print(f"{DIFFUSERS_REPO}: has to stay intact, so it downloads whole")
queued, body = call_download({"model_url_or_id": DIFFUSERS_REPO, "model_type": "diffusers",
                              "force_redownload": True})
check("not routed per file", body.get("per_file_destinations"), None)
check("a single queue entry", len(queued), 1)
check("no URL, so the manager snapshots the repo", queued[0]["url"], None)
check("saved under the chosen model type",
      os.path.dirname(queued[0]["output_path"]), helpers.get_model_dir("diffusers"))

print("a single-file URL is unaffected by the routing change")
GEMMA_FILE = "text_encoders/gemma4_e4b_it_fp8_scaled.safetensors"
queued, body = call_download({
    "model_url_or_id": f"https://huggingface.co/Comfy-Org/gemma-4/blob/main/{GEMMA_FILE}",
    "model_type": "checkpoints", "force_redownload": True})
check("a single queue entry", len(queued), 1)
# An explicitly chosen file honours the form's Model Type, which stays enabled
check("saved under the chosen model type",
      os.path.dirname(queued[0]["output_path"]), helpers.get_model_dir("checkpoints"))
check("downloads that exact file", queued[0]["url"],
      f"https://huggingface.co/Comfy-Org/gemma-4/resolve/main/{GEMMA_FILE}")

print()
if failures:
    print(f"{len(failures)} FAILED:")
    for name in failures:
        print(f"  - {name}")
    sys.exit(1)
print("all checks passed")
