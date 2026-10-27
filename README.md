# Save Image (scrubbed)

A ComfyUI custom node that saves PNGs like the core Save Image node, but removes API keys and other credentials from the metadata it embeds.

## Why it exists

ComfyUI's core `SaveImage` writes the entire API-format graph it was handed into every PNG, as a `prompt` text chunk, plus the editor graph as `workflow`. Any graph with a cloud-inference node takes an `api_key` input, so the key ends up inside the image. I found API keys embedded in ComfyUI PNG metadata in my own output folder. ComfyUI does this on the server side, so the fix has to happen where the file is written.

## What it does

- Same inputs as core Save Image: `images`, `filename_prefix`. One optional extra: `metadata`.
- `metadata = scrub` (default): keeps the prompt and workflow, so the image still reloads as a graph, and redacts credentials in two ways:
  - by field name (`api_key`, `secret`, `password`, `token`, `bearer`, ...), string values only, so `max_tokens: 512` survives;
  - by value shape (`AIza...`, `sk-...`, `ghp_...`, `xox...`), which catches a key pasted into a prompt string.
- `metadata = drop`: writes no metadata at all.
- Before the file is written, the final PNG bytes are scanned again. If a credential-shaped string is still present, the node raises `ScrubFailed` and nothing is written.

## Install

```
cd ComfyUI/custom_nodes
git clone https://github.com/aion88/comfyui-save-image-scrubbed
```

Restart ComfyUI. The node is under `image` as "Save Image (scrubbed)". No extra dependencies: it uses what ComfyUI already ships (Pillow, numpy).

## Usage

Replace Save Image with Save Image (scrubbed) in your graph. In an API graph:

```json
"9": {
  "class_type": "SaveImageScrubbed",
  "inputs": { "images": ["8", 0], "filename_prefix": "render", "metadata": "scrub" }
}
```

## Tested

Unit tests cover the scrub logic without ComfyUI (`uv run pytest`, 17 tests). I also installed it in a local ComfyUI (CPU), ran `EmptyImage -> Save Image (scrubbed)` through `/prompt` with a fake key-shaped value in an unconnected node's input and another in the workflow's `api_key` field. The saved PNG kept both graphs, the workflow's `api_key` read `[redacted]`, and the fake key was absent from the file bytes. With `metadata = drop` the PNG had no text chunks.

## Limitations

- It cannot find a secret it cannot recognise. A custom field name outside the list holding a token with an unfamiliar shape passes through. The list lives in `png_scrub.py`; extend it for your vendors.
- The editor `workflow` stores widget values by position, without field names, so a key there is caught only by its value shape.
- Only PNGs written by this node are scrubbed. Other save nodes (video, preview, third party) are not touched.
- Scrubbing rewrites metadata, not pixels. Pixel data is untouched.

MIT license.
