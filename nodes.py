"""ComfyUI node: Save Image (scrubbed)."""

from __future__ import annotations

import io
import json
import os

from .png_scrub import scrub_metadata, verify_png

MODES = ["scrub", "drop"]


class SaveImageScrubbed:
    """Same inputs as core SaveImage, but credentials never reach the PNG."""

    def __init__(self):
        self.type = "output"
        self.compress_level = 4

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "images": ("IMAGE", {"tooltip": "The images to save."}),
                "filename_prefix": (
                    "STRING",
                    {
                        "default": "ComfyUI",
                        "tooltip": "The prefix for the file to save. Same rules as the core Save Image node.",
                    },
                ),
            },
            "optional": {
                "metadata": (
                    MODES,
                    {
                        "default": "scrub",
                        "tooltip": "scrub: keep the prompt and workflow, redact credentials. "
                        "drop: write no metadata at all.",
                    },
                ),
            },
            "hidden": {"prompt": "PROMPT", "extra_pnginfo": "EXTRA_PNGINFO"},
        }

    RETURN_TYPES = ()
    FUNCTION = "save_images"
    OUTPUT_NODE = True
    CATEGORY = "image"
    DESCRIPTION = (
        "Saves PNGs like Save Image, but removes API keys and other credentials "
        "from the embedded prompt and workflow, and refuses to write if one survives."
    )

    def save_images(
        self, images, filename_prefix="ComfyUI", metadata="scrub", prompt=None, extra_pnginfo=None
    ):
        # Imported here so the module loads (and its schema can be tested) without ComfyUI.
        import folder_paths
        import numpy as np
        from PIL import Image
        from PIL.PngImagePlugin import PngInfo

        if metadata not in MODES:
            raise ValueError(f"metadata must be one of {MODES}, got {metadata!r}")

        output_dir = folder_paths.get_output_directory()
        full_output_folder, filename, counter, subfolder, _ = folder_paths.get_save_image_path(
            filename_prefix, output_dir, images[0].shape[1], images[0].shape[0]
        )

        pnginfo = None
        if metadata == "scrub":
            raw = {}
            if prompt is not None:
                raw["prompt"] = json.dumps(prompt)
            for key, value in (extra_pnginfo or {}).items():
                raw[key] = json.dumps(value)
            pnginfo = PngInfo()
            for key, text in scrub_metadata(raw).items():
                pnginfo.add_text(key, text)

        results = []
        for batch_number, image in enumerate(images):
            arr = 255.0 * image.cpu().numpy()
            img = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))
            buf = io.BytesIO()
            img.save(buf, format="PNG", pnginfo=pnginfo, compress_level=self.compress_level)
            blob = verify_png(buf.getvalue())  # raises ScrubFailed, nothing is written

            name = filename.replace("%batch_num%", str(batch_number))
            file = f"{name}_{counter:05}_.png"
            with open(os.path.join(full_output_folder, file), "wb") as fh:
                fh.write(blob)
            results.append({"filename": file, "subfolder": subfolder, "type": self.type})
            counter += 1

        return {"ui": {"images": results}}


NODE_CLASS_MAPPINGS = {"SaveImageScrubbed": SaveImageScrubbed}
NODE_DISPLAY_NAME_MAPPINGS = {"SaveImageScrubbed": "Save Image (scrubbed)"}
