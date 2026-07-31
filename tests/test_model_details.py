# ================================================
# File: tests/test_model_details.py
# Exercises the /api/huggingface/get_model_details route end to end.
# Requires network access (reads a real public repo).
#
# Run from anywhere with ComfyUI's python:
#   python_embeded/python.exe ComfyUI/custom_nodes/ComfyUI-HuggingFace/tests/test_model_details.py
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


# The route modules bind to PromptServer.instance at import time, which only
# exists inside a running ComfyUI. Stub it so the decorators are no-ops.
class _FakeRoutes:
    def post(self, _path):
        return lambda fn: fn

    def get(self, _path):
        return lambda fn: fn


class _FakeServer:
    routes = _FakeRoutes()


import server  # noqa: E402
server.PromptServer.instance = _FakeServer()

details = importlib.import_module("ComfyUI-HuggingFace.server.routes.GetModelDetails")

REPO = "Comfy-Org/gemma-4"
GEMMA_FILE = "text_encoders/gemma4_e4b_it_fp8_scaled.safetensors"
GEMMA_BLOB = f"https://huggingface.co/{REPO}/blob/main/{GEMMA_FILE}"
GEMMA_FP8_BYTES = 9057782194

failures = []


def check(label, got, want):
    ok = got == want
    print(f"  [{'PASS' if ok else 'FAIL'}] {label}")
    if not ok:
        print(f"         got:  {got!r}")
        print(f"         want: {want!r}")
        failures.append(label)


def check_true(label, got):
    check(label, bool(got), True)


class FakeRequest:
    def __init__(self, payload):
        self._payload = payload

    async def json(self):
        return self._payload


def call_route(payload):
    response = asyncio.run(details.route_get_model_details(FakeRequest(payload)))
    return json.loads(response.body)


print("_strip_frontmatter(): drops the YAML block a model card starts with")
check("frontmatter removed",
      details._strip_frontmatter("---\nlicense: mit\n---\n\n# Title\nbody"),
      "# Title\nbody")
check("body without frontmatter is untouched",
      details._strip_frontmatter("# Title\nbody"), "# Title\nbody")
check("a lone --- is not treated as frontmatter",
      details._strip_frontmatter("---"), "---")

print("_infer_model_type(): maps the repo layout onto a models/ subfolder")
check("from the selected file",
      details._infer_model_type([{"path": "vae/a.safetensors"}], "text_encoders/b.safetensors"),
      "text_encoders")
check("from a single shared folder",
      details._infer_model_type([{"path": "text_encoders/a"}, {"path": "text_encoders/b"}], None),
      "text_encoders")
check("ambiguous layout gives no hint",
      details._infer_model_type([{"path": "vae/a"}, {"path": "text_encoders/b"}], None),
      None)
check("files at the repo root give no hint",
      details._infer_model_type([{"path": "a.safetensors"}], None), None)

print(f"route: a single-file URL for {REPO}")
result = call_route({"model_url_or_id": GEMMA_BLOB})
check("success", result.get("success"), True)
check("model_id", result.get("model_id"), REPO)
check("model_name", result.get("model_name"), "gemma-4")
check("creator_username", result.get("creator_username"), "Comfy-Org")
check("license", result.get("license"), "apache-2.0")
check("revision", result.get("revision"), "main")
check("selected_file", result.get("selected_file"), GEMMA_FILE)
check("model_type hint", result.get("model_type"), "text_encoders")
check("hf_url", result.get("hf_url"), f"https://huggingface.co/{REPO}")
check_true("description is populated", result.get("description"))
check_true("downloads stat", (result.get("stats") or {}).get("downloads", 0) > 0)

files = result.get("files") or []
paths = [f["path"] for f in files]
check("all 4 weight files listed", len(files), 4)
check_true("target file present", GEMMA_FILE in paths)
check("README.md excluded", "README.md" in paths, False)
check(".gitattributes excluded", ".gitattributes" in paths, False)
check("target file size", next((f["size"] for f in files if f["path"] == GEMMA_FILE), None),
      GEMMA_FP8_BYTES)

print(f"route: a bare repo id for {REPO} selects no file")
repo_result = call_route({"model_url_or_id": REPO})
check("success", repo_result.get("success"), True)
check("selected_file is None", repo_result.get("selected_file"), None)
# Every weight lives under text_encoders/, so the hint still resolves
check("model_type hint from layout", repo_result.get("model_type"), "text_encoders")

print("route: a repo that does not exist fails without raising")
missing = call_route({"model_url_or_id": "Comfy-Org/definitely-not-a-real-repo-xyz"})
check("success is False", missing.get("success"), False)
check_true("error message present", missing.get("error"))
check_true("error message is human readable, not a raw HTTP dump",
           "not accessible" in (missing.get("error") or "")
           and "Request ID" not in (missing.get("error") or ""))

print()
if failures:
    print(f"{len(failures)} FAILED:")
    for name in failures:
        print(f"  - {name}")
    sys.exit(1)
print("all checks passed")
