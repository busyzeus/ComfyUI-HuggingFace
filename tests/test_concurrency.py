# ================================================
# File: tests/test_concurrency.py
# Checks that routes doing network I/O do not stall ComfyUI's event loop.
#
# ComfyUI serves everything - the web UI, the websocket, prompt dispatch - from
# one aiohttp loop. A route that calls a synchronous, requests-backed
# huggingface_hub function directly inside `async def` freezes all of it for
# the duration of the call. This test is the only thing that catches that:
# the route still returns correct data either way, so unit tests pass happily.
#
# Requires a RUNNING ComfyUI that has been restarted since the last Python
# change, plus network access.
#
# Run from anywhere with ComfyUI's python:
#   python_embeded/python.exe ComfyUI/custom_nodes/ComfyUI-HuggingFace/tests/test_concurrency.py
#
# Never exercises /api/huggingface/download - that would queue a real
# multi-gigabyte download.
# ================================================
import json
import sys
import threading
import time
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:8188"
PROBE_PATH = "/api/huggingface/status"

# A blocked loop shows up as probe latency matching the slow call's duration,
# so hundreds of milliseconds. A responsive loop answers in single-digit ms.
# 0.25s sits far from both, and well clear of ordinary scheduling jitter.
MAX_PROBE_SECONDS = 0.25

failures = []


def check(label, got, want):
    ok = got == want
    print(f"  [{'PASS' if ok else 'FAIL'}] {label}")
    if not ok:
        print(f"         got:  {got!r}")
        print(f"         want: {want!r}")
        failures.append(label)


def post(path, payload, timeout=180):
    request = urllib.request.Request(
        BASE + path,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.load(response)


def probe_while(call):
    """Run `call`, hammering a cheap endpoint meanwhile.

    Returns (slowest probe in seconds, probe count, error count). The probes
    share the server's single event loop, so if `call` blocks it, they cannot
    be answered until it finishes.
    """
    latencies, errors = [], 0
    stop = threading.Event()

    def probe():
        nonlocal errors
        while not stop.is_set():
            started = time.perf_counter()
            try:
                urllib.request.urlopen(BASE + PROBE_PATH, timeout=60).read()
            except Exception:
                errors += 1
            else:
                latencies.append(time.perf_counter() - started)
            time.sleep(0.05)

    thread = threading.Thread(target=probe, daemon=True)
    thread.start()
    try:
        call()
    finally:
        stop.set()
        thread.join(timeout=10)

    return (max(latencies) if latencies else None), len(latencies), errors


def assert_responsive(label, call):
    slowest, count, errors = probe_while(call)
    print(f"    {count} probes during the call, slowest {slowest and round(slowest, 3)}s, {errors} errors")
    check(f"{label}: probes answered", count > 0, True)
    check(f"{label}: no probe errors", errors, 0)
    check(f"{label}: loop stayed responsive (< {MAX_PROBE_SECONDS}s)",
          slowest is not None and slowest < MAX_PROBE_SECONDS, True)


try:
    urllib.request.urlopen(BASE + PROBE_PATH, timeout=10).read()
except Exception as e:
    print(f"ComfyUI is not answering on {BASE}: {e}")
    print("Start it, or restart it if the Python under test has changed.")
    sys.exit(2)

print("search: paging walks several HuggingFace pages per request")
assert_responsive(
    "search",
    lambda: post("/api/huggingface/search",
                 {"query": "model", "comfyui_only": False, "limit": 20, "page": 30}),
)

print("get_model_details: one repo lookup plus a README fetch")
assert_responsive(
    "get_model_details",
    lambda: post("/api/huggingface/get_model_details",
                 {"model_url_or_id": "Comfy-Org/z_image_turbo"}),
)

print()
if failures:
    print(f"{len(failures)} FAILED:")
    for name in failures:
        print(f"  - {name}")
    sys.exit(1)
print("all checks passed")
