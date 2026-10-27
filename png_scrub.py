"""Strip credentials out of ComfyUI image metadata.

ComfyUI's core `SaveImage` embeds the whole API-format graph it was handed, every
`api_key` input included, into each PNG as a `prompt` tEXt chunk, and the editor
graph as a `workflow` chunk. A graph with any cloud-inference node therefore writes
a live credential into the image bytes. This module is the pure logic (no ComfyUI
import) so it can be unit tested on its own.

Two checks, neither enough alone:

  * by FIELD NAME (`api_key`, `secret`, `token`, ...), restricted to string values
    so honest numeric provenance such as `max_tokens: 512` survives;
  * by VALUE SHAPE (`AIza...`, `sk-...`, `ghp_...`, `xox...`), which catches a key
    interpolated into a prompt string where no field name gives it away.

After redaction `find_leak` re-scans the final bytes, and the node raises if a
credential-shaped string survived.
"""

from __future__ import annotations

import json
import re
import struct
import zlib

REDACTED = "[redacted]"

PNG_SIG = b"\x89PNG\r\n\x1a\n"

# Field names whose STRING values are credentials.
_CREDENTIAL_FIELD_RE = re.compile(
    r"api[-_]?key|apikey|secret|passw(?:or)?d|credential|bearer"
    r"|private[-_]?key|session[-_]?key|auth[-_]?token"
    r"|(?:^|[-_])tokens?(?:$|[-_])",
    re.I,
)

# Values that are credential-shaped wherever they appear.
_CREDENTIAL_VALUE_RE = re.compile(
    r"AIza[0-9A-Za-z_\-]{35}"
    r"|sk-(?:ant-)?[A-Za-z0-9_\-]{20,}"
    r"|gh[pousr]_[A-Za-z0-9]{20,}"
    r"|xox[abprs]-[A-Za-z0-9-]{10,}"
)


class ScrubFailed(Exception):
    """The bytes still carry a credential after scrubbing, so they must not be written."""


def redact(node):
    """Strip credential-named fields and credential-shaped values, recursively."""
    if isinstance(node, dict):
        out = {}
        for k, v in node.items():
            named = isinstance(k, str) and _CREDENTIAL_FIELD_RE.search(k)
            out[k] = REDACTED if (named and isinstance(v, str) and v) else redact(v)
        return out
    if isinstance(node, list):
        return [redact(v) for v in node]
    if isinstance(node, str):
        return _CREDENTIAL_VALUE_RE.sub(REDACTED, node)
    return node


def scrub_text(raw: str) -> str:
    """Redact one metadata payload: JSON structurally, anything else by shape."""
    try:
        decoded = json.loads(raw)
    except ValueError:
        return _CREDENTIAL_VALUE_RE.sub(REDACTED, raw)
    # Re-serialise, then sweep the flat text too, so a shape that survived inside
    # a key name or a non-string position is still removed.
    return _CREDENTIAL_VALUE_RE.sub(REDACTED, json.dumps(redact(decoded)))


def scrub_metadata(metadata: dict[str, object]) -> dict[str, str]:
    """Map {chunk_name: python value or JSON string} to {chunk_name: scrubbed JSON string}."""
    out: dict[str, str] = {}
    for key, value in metadata.items():
        raw = value if isinstance(value, str) else json.dumps(value)
        out[key] = scrub_text(raw)
    return out


def png_text_payloads(blob: bytes) -> list[bytes]:
    """Return the decoded text of every tEXt, zTXt and iTXt chunk in a PNG."""
    payloads: list[bytes] = []
    i = len(PNG_SIG)
    while i + 12 <= len(blob):
        (length,) = struct.unpack(">I", blob[i : i + 4])
        ctype = blob[i + 4 : i + 8]
        data = blob[i + 8 : i + 8 + length]
        if ctype == b"tEXt":
            payloads.append(data.partition(b"\x00")[2])
        elif ctype == b"zTXt":
            rest = data.partition(b"\x00")[2]
            try:
                payloads.append(zlib.decompress(rest[1:]))
            except zlib.error:
                payloads.append(b"")
        elif ctype == b"iTXt":
            rest = data.partition(b"\x00")[2]
            compressed, rest = rest[:1] == b"\x01", rest[2:]
            _, _, rest = rest.partition(b"\x00")
            _, _, text = rest.partition(b"\x00")
            if compressed:
                try:
                    text = zlib.decompress(text)
                except zlib.error:
                    text = b""
            payloads.append(text)
        i += 12 + length
        if ctype == b"IEND":
            break
    return payloads


def find_leak(blob: bytes) -> str | None:
    """The last word before bytes are written: a description of the leak, or None."""
    if _CREDENTIAL_VALUE_RE.search(blob.decode("latin-1")):
        return "a credential-shaped string"
    for payload in png_text_payloads(blob):
        if _CREDENTIAL_VALUE_RE.search(payload.decode("latin-1")):
            return "a credential-shaped string in a text chunk"
    return None


def verify_png(blob: bytes) -> bytes:
    """Return `blob` unchanged if it is clean, else raise ScrubFailed."""
    leak = find_leak(blob)
    if leak is not None:
        raise ScrubFailed(f"refusing to write PNG: it still carries {leak}")
    return blob
