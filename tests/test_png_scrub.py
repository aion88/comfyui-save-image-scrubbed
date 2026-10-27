import importlib.util
import io
import json
import sys
from pathlib import Path

import pytest
from PIL import Image
from PIL.PngImagePlugin import PngInfo

from png_scrub import (
    REDACTED,
    ScrubFailed,
    find_leak,
    redact,
    scrub_metadata,
    scrub_text,
    verify_png,
)

ROOT = Path(__file__).resolve().parent.parent

# Built at runtime so no credential-shaped literal sits in the repository.
FAKE_GOOGLE = "AIza" + "Sy" + "FAKE" * 8 + "abc"[:1]  # 4 + 35 chars
FAKE_SK = "sk-" + "a" * 30
FAKE_GH = "ghp_" + "b" * 30
FAKE_SLACK = "xoxb-" + "1234567890" + "-abc"


def png_with_text(**chunks: str) -> bytes:
    info = PngInfo()
    for k, v in chunks.items():
        info.add_text(k, v)
    buf = io.BytesIO()
    Image.new("RGB", (2, 2)).save(buf, format="PNG", pnginfo=info)
    return buf.getvalue()


def test_fake_google_key_has_the_right_shape():
    assert len(FAKE_GOOGLE) == 39


def test_redacts_by_field_name():
    out = redact({"api_key": "hunter2", "nested": {"client_secret": "x", "password": "y"}})
    assert out == {"api_key": REDACTED, "nested": {"client_secret": REDACTED, "password": REDACTED}}


def test_field_name_only_applies_to_strings():
    out = redact({"max_tokens": 512, "api_key": "", "auth_token": 7})
    assert out == {"max_tokens": 512, "api_key": "", "auth_token": 7}


def test_redacts_by_value_shape_with_innocent_field_name():
    graph = {"3": {"inputs": {"text": f"call it with {FAKE_GOOGLE} please"}}}
    out = redact(graph)
    assert FAKE_GOOGLE not in json.dumps(out)
    assert out["3"]["inputs"]["text"] == f"call it with {REDACTED} please"


@pytest.mark.parametrize("secret", [FAKE_GOOGLE, FAKE_SK, FAKE_GH, FAKE_SLACK])
def test_every_value_shape_is_caught(secret):
    assert secret not in scrub_text(json.dumps({"note": secret}))


def test_non_json_text_is_scrubbed_by_shape():
    assert scrub_text(f"plain {FAKE_SK} text") == f"plain {REDACTED} text"


def test_graph_structure_survives_scrubbing():
    prompt = {
        "1": {"class_type": "EmptyImage", "inputs": {"width": 8, "height": 8}},
        "2": {"class_type": "SomeCloudNode", "inputs": {"api_key": FAKE_GOOGLE, "image": ["1", 0]}},
    }
    out = json.loads(scrub_metadata({"prompt": prompt})["prompt"])
    assert out["1"] == prompt["1"]
    assert out["2"]["class_type"] == "SomeCloudNode"
    assert out["2"]["inputs"]["image"] == ["1", 0]
    assert out["2"]["inputs"]["api_key"] == REDACTED


def test_scrub_metadata_accepts_python_values_and_strings():
    out = scrub_metadata({"a": {"api_key": "k"}, "b": json.dumps({"password": "p"})})
    assert json.loads(out["a"]) == {"api_key": REDACTED}
    assert json.loads(out["b"]) == {"password": REDACTED}


def test_verify_png_raises_on_leaky_text_chunk():
    with pytest.raises(ScrubFailed):
        verify_png(png_with_text(prompt=json.dumps({"x": FAKE_GOOGLE})))


def test_verify_png_raises_on_leak_in_raw_bytes():
    with pytest.raises(ScrubFailed):
        verify_png(png_with_text(note="harmless") + FAKE_SK.encode())


def test_verify_png_passes_clean_png_unchanged():
    blob = png_with_text(prompt=json.dumps({"1": {"inputs": {"api_key": REDACTED}}}))
    assert verify_png(blob) == blob
    assert find_leak(blob) is None


def test_scrubbed_metadata_round_trips_through_a_real_png():
    prompt = {"2": {"class_type": "Cloud", "inputs": {"api_key": FAKE_GOOGLE}}}
    scrubbed = scrub_metadata({"prompt": prompt})
    blob = verify_png(png_with_text(**scrubbed))
    assert FAKE_GOOGLE.encode() not in blob
    stored = Image.open(io.BytesIO(blob)).text["prompt"]
    assert json.loads(stored)["2"]["inputs"]["api_key"] == REDACTED


def load_package():
    spec = importlib.util.spec_from_file_location(
        "save_image_scrubbed_pkg", ROOT / "__init__.py", submodule_search_locations=[str(ROOT)]
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def test_package_exports_node_mappings():
    pkg = load_package()
    assert set(pkg.NODE_CLASS_MAPPINGS) == set(pkg.NODE_DISPLAY_NAME_MAPPINGS)
    assert pkg.NODE_DISPLAY_NAME_MAPPINGS["SaveImageScrubbed"] == "Save Image (scrubbed)"


def test_node_inputs_match_core_save_image_and_add_metadata_option():
    node = load_package().NODE_CLASS_MAPPINGS["SaveImageScrubbed"]
    spec = node.INPUT_TYPES()
    assert list(spec["required"]) == ["images", "filename_prefix"]
    assert spec["required"]["images"][0] == "IMAGE"
    assert spec["required"]["filename_prefix"][0] == "STRING"
    assert spec["optional"]["metadata"][0] == ["scrub", "drop"]
    assert spec["hidden"] == {"prompt": "PROMPT", "extra_pnginfo": "EXTRA_PNGINFO"}
    assert node.OUTPUT_NODE is True and node.RETURN_TYPES == ()
