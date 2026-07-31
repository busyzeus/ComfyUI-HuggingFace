# ================================================
# File: tests/test_search.py
# Exercises POST /api/huggingface/search against the live HuggingFace API.
# Requires network access.
#
# Run from anywhere with ComfyUI's python:
#   python_embeded/python.exe ComfyUI/custom_nodes/ComfyUI-HuggingFace/tests/test_search.py
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

search = importlib.import_module("ComfyUI-HuggingFace.server.routes.SearchModels")

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


def call(payload):
    response = asyncio.run(search.route_search_models(FakeRequest(payload)))
    return json.loads(response.body)


print("build_filters(): category and comfyui_only are ANDed")
check("comfyui only", search.build_filters("any", True), ["comfyui"])
check("category only", search.build_filters("gguf", False), ["gguf"])
check("both", search.build_filters("gguf", True), ["comfyui", "gguf"])
check("neither", search.build_filters("any", False), [])
check("unknown category is ignored", search.build_filters("nonsense", False), [])

print("SORT_VALUES: every option is one HuggingFace accepts")
check("only valid sort values",
      sorted(set(search.SORT_VALUES.values())),
      sorted(["createdAt", "downloads", "lastModified", "likes", "trendingScore"]))

print("route: a plain ComfyUI search returns usable rows")
body = call({"query": "flux", "comfyui_only": True, "limit": 5})
items = body.get("items") or []
check("a full page of items", len(items), 5)
check("metadata", body.get("metadata"), {"page": 1, "limit": 5, "has_more": True})

first = items[0]
check("id carries owner/name", "/" in first.get("id", ""), True)
check("name has no owner", "/" in first.get("name", ""), False)
check_true("author is populated", first.get("author"))
check_true("downloads is populated", first.get("downloads", 0) > 0)
check("tags exclude namespaced ones",
      any(":" in t for t in first.get("tags", [])), False)
check_true("updated is an ISO date", first.get("updated", "").startswith("20"))

print("route: comfyui_only actually narrows the results")
wide = call({"query": "flux", "comfyui_only": False, "limit": 50})
narrow = call({"query": "flux", "comfyui_only": True, "limit": 50})
wide_ids = {i["id"] for i in wide["items"]}
narrow_ids = {i["id"] for i in narrow["items"]}
check_true("comfyui results differ from unfiltered", wide_ids != narrow_ids)
check_true("narrow results are non-empty", len(narrow["items"]) > 0)
check_true("every comfyui result is tagged comfyui",
           all("comfyui" in i["tags"] for i in narrow["items"]))

print("route: a category narrows further")
gguf = call({"query": "wan", "comfyui_only": True, "category": "gguf", "limit": 10})
check_true("gguf results are non-empty", len(gguf["items"]) > 0)
check_true("gguf results are tagged gguf",
           all("gguf" in i["tags"] for i in gguf["items"]))

print("route: paging walks forward without repeating")
page1 = call({"query": "flux", "comfyui_only": True, "limit": 5, "page": 1})
page2 = call({"query": "flux", "comfyui_only": True, "limit": 5, "page": 2})
check("page 2 reports its number", page2["metadata"]["page"], 2)
check("pages do not overlap",
      {i["id"] for i in page1["items"]} & {i["id"] for i in page2["items"]}, set())

print("route: the last page reports has_more false")
tail = call({"query": "flux", "comfyui_only": True, "limit": 100, "page": 5})
check("no more results past the end", tail["metadata"]["has_more"], False)

print("route: every sort option is accepted by HuggingFace")
for label in search.SORT_VALUES:
    result = call({"query": "flux", "comfyui_only": True, "sort": label, "limit": 3})
    check(f"sort={label}", "error" in result, False)

print("route: an empty search is rejected")
try:
    call({"query": "", "comfyui_only": False, "category": "any"})
    check("empty search raises", False, True)
except Exception as e:
    check("empty search raises HTTPBadRequest", type(e).__name__, "HTTPBadRequest")

print()
if failures:
    print(f"{len(failures)} FAILED:")
    for name in failures:
        print(f"  - {name}")
    sys.exit(1)
print("all checks passed")
