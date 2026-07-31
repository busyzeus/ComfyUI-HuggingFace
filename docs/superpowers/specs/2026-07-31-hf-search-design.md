# HuggingFace Search — design

Date: 2026-07-31
Status: approved, not yet implemented

## Problem

The Search tab is the last part of this fork still shaped like the Civitai
downloader it was converted from. It does not work, for three separate reasons.

**The backend and the renderer disagree on the data.** `SearchModels.py` returns
`{id, name, creator: {username}, downloads, likes, tags: [str], stats: {...}}`.
`searchRenderer.js` reads `hit.user.username`, `hit.metrics`, `hit.type`,
`hit.tags.map(t => t.name)`, `hit.images`, `hit.nsfwLevel`, `hit.publishedAt`
and `hit.versions`. Almost nothing lines up: `tags.map(t => t.name)` yields
`[undefined, ...]`, every stat renders as 0, and because `hit.versions` is
absent the per-version download buttons are never emitted — so a result cannot
be acted on at all.

**The filters cannot match anything.** The Type dropdown maps through
`HUGGINGFACE_API_TYPE_MAP`, whose values are Civitai type names
(`Checkpoint`, `LORA`, `TextualInversion`), lowercased and passed to HF as
tags. The Base Model dropdown is filled from `AVAILABLE_MEILI_BASE_MODELS`
(`SD 1.5`, `Pony`, ...) and its value is concatenated into the free-text query
as `base_model:SD 1.5`.

**Four of the eight sort options do not exist on HuggingFace.** Highest Rated,
Most Discussed, Most Collected and Most Buzz all map to `None` and are
silently ignored.

## What the HuggingFace API actually offers

Measured against the live API on 2026-07-31 with `huggingface_hub` 0.36.2.

`HfApi.list_models` accepts `search`, `tags`, `pipeline_tag`, `author`,
`filter`, `sort`, `direction` and `limit`. There is **no offset or page
parameter**; it returns a generator that pages lazily, so `itertools.islice`
gives us offsets at the cost of walking earlier pages.

Valid `sort` values: `downloads`, `likes`, `lastModified`, `createdAt`,
`trendingScore`. `author` raises `BadRequestError`.

Both `library=` and `tags=` are deprecated and will be removed in
`huggingface_hub` 1.0. `filter=` is the replacement and returns identical
results: `filter='comfyui'` and `filter=['comfyui', 'gguf']` were verified
against `tags=` equivalents. **Use `filter`.**

Findings that drive the filter design:

- `filter=comfyui` is the single highest-signal filter. `search=flux` plus it
  returns 66 models led by `Comfy-Org/flux2-dev` and `Comfy-Org/flux1-dev`.
- **`pipeline_tag` is not used at all.** HuggingFace labels a model two ways:
  free-form tags, and one `pipeline_tag` naming its task. Comfy-Org repos set
  only the former — `Comfy-Org/gemma-4` and `Comfy-Org/z_image_turbo` both
  have `pipeline_tag=None`. Adding `pipeline_tag='text-to-image'` to the flux
  search above cuts it from 66 hits to 23 and drops both Comfy-Org repos out
  of the results entirely. A task filter would hide exactly the repos this
  tool exists for, so the Category dropdown offers no task options.
- `filter=lora` and `filter=gguf` on their own are dominated by unrelated LLM
  repos (`Qwopus3.6-35B-A3B-Coder-MTP-GGUF`, `mxbai-embed-large-v1`). They are
  only useful ANDed with `comfyui`.

## Design

### Search route

`POST /api/huggingface/search` takes
`{query, category, comfyui_only, sort, limit, page, api_key}` and calls
`list_models` with `direction=-1`.

Filters are ANDed: `category` contributes at most one entry to `filter`, and
`comfyui_only` adds `comfyui`. Nothing sets `pipeline_tag`.

Paging uses `islice(generator, offset, offset + limit + 1)`. Fetching one extra
item is how the route knows whether more results exist, without a count API.

The response is exactly what the renderer consumes:

```
{
  "items": [
    {"id", "name", "author", "downloads", "likes", "tags", "updated", "gated"}
  ],
  "metadata": {"page", "limit", "has_more"}
}
```

`items[].name` is the repo name without the owner; `id` keeps `owner/name`.
`updated` is an ISO string or `""`. `tags` excludes namespaced tags
(anything containing `:`), matching what GetModelDetails already does.

A search with no query and no filters is rejected with 400, as today.

### Filters

| Category (UI) | HuggingFace filter |
|---|---|
| Any | none |
| LoRA | `filter=lora` |
| GGUF | `filter=gguf` |
| Diffusers | `filter=diffusers` |

`ComfyUI only`, a checkbox defaulting to checked, ANDs `comfyui` onto whatever
is selected.

There is deliberately no task/pipeline category. See the pipeline_tag finding
above: it removes the Comfy-Org repos.

Sort options, in UI order: Most Downloaded (`downloads`), Trending
(`trendingScore`), Most Liked (`likes`), Recently Updated (`lastModified`),
Newest (`createdAt`).

### Result rows and hand-off

Each row shows `owner/name`, downloads, likes, last-updated date, up to five
tags, and one `Open in Download tab` button. The button writes the repo id into
`#huggingface-model-url`, switches to the Download tab and triggers the preview
fetch, which already lists files with sizes and preselects a save location.

Nothing downloads from the Search tab. Sending the user to the Download tab
means they see the file picker and the size warning before committing, which
matters when a repo like `z_image_turbo` is 55 GB.

Removed from the renderer: the placeholder thumbnail, version buttons, the
"All versions" expander, NSFW blurring, and rating/buzz stats.

### Paging UI

A `Load more` button below the results, shown only when `metadata.has_more`.
It refetches with `page + 1` and **appends** rows. A new search resets to page
1 and replaces them. The existing prev/next pagination widget and
`renderSearchPagination` are removed.

### Dead code removed alongside

- `server/routes/GetBaseModels.py` and its route
- `AVAILABLE_MEILI_BASE_MODELS` and `HUGGINGFACE_API_TYPE_MAP` in `config.py`
- `HuggingFaceAPI.search_models_meili`, which POSTs to
  `https://huggingface.co/multi-search`, a Civitai endpoint that does not exist
  on HuggingFace
- Settings: "Hide mature in search" and the NSFW blur threshold, together with
  the `hideMatureInSearch` / `nsfwBlurMinLevel` settings they write

### Error handling

A failed `list_models` call returns `{"error", "details"}` with status 500 and
the handler shows the message, as it does today. Repo-level failures are
reported as a sentence rather than a raw HTTP dump, matching what
`GetModelDetails` now does.

Empty results distinguish two cases, as the current renderer already tries to:
no query and no filters gives "Enter a query or choose a filter"; a real search
that matched nothing gives "No models found matching your criteria."

### Testing

`tests/test_search.py`, following `test_download_routing.py`: stub
`PromptServer.instance`, call the route directly, and assert against the live
API that

- the response shape matches the contract above
- `comfyui_only` narrows results (`flux` + comfyui yields fewer than `flux`)
- category filters change the result set
- `has_more` is true on page 1 and paging returns different ids
- every sort value is accepted

`tests/e2e_search.mjs`, following `e2e_preview.mjs`: search for `flux`, assert
rows render with a download count, click `Open in Download tab`, and assert the
Download tab is active with the URL filled and the file picker populated.

## Out of scope

The `.cminfo.json` metadata and `.preview.jpeg` sidecar files written after
every download are still Civitai-shaped and mostly `None` on HuggingFace.
That is a separate change.
