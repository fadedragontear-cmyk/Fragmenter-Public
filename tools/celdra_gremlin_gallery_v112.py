#!/usr/bin/env python3
"""Create compact animated GIF portraits for the V112 completed Gremlin gallery."""
from __future__ import annotations

import base64
from pathlib import Path

from celdra_gremlin_memory_v1 import KNOWN_GREMLINS

_TEMPLATE_GIF = (
    "R0lGODlhMAAwAIEAAAcUJgdQamTY/730/yH/C05FVFNDQVBFMi4wAwEAAAAh+QQIEgAAACwAAAAAMAAwAAAI/wABCBxIsKDBgwgT"
    "KlzIsKHDhxAjSpxIsaLFixgzagQw4GHHjQMHfFwoEiTBkgpRmhQocqTBlitPqpTpMmbLmjdj0lR5sybEAA57cszZEKjBAEhJ9lz"
    "qsyBSo0efQj0poKrVq1abSp3qdOvUAVjDXnXplWvXsmDFqhUwoGxShW7TrlXbtuzCuHPX1vXKEO1YuX/H2u3rVe5NrIer7pXq"
    "sHDWjoDZDs3Kt/FWwCLFZqa89aHjvJorW34aGbTizj+llja92CxhpKt7hn46EWpkppuzDnQNETPu3JI1Gv7dUrfwx8QNg0ybfH"
    "PTi617Xo6JVuRgkG4DtGaM3S2A7CuvXxM3iXo3d53o06tfz769+/fw0QcEACH5BAgSAAAALAAAAAAwADAAgQcUJgdQamTY/730"
    "/wj/AAEIHEiwoMGDCBMqXMiwocOHECNKnEixosWLGDNq3GhxwEOPHAUOALlwZMiBJhWmPAlgJEmDLlmiXEkwpkyRNmfSZOlyZc+"
    "XEQM4/Nmyp0OhBgMoLfmzKdCkSw8qnXpwgICrWLNifQpgalSpXr+21Eo268uwYqGiDWC1rFsBA9amVRu27Vu3cdculGv3Ltm8aB"
    "mu7TuybOGtegWjtdtTa+OrgL0erbvVY1+4RRGHfbjY7GXIhANP9vrZL2TRo5WWNh0ZKWfSpg1vDjq19E/ZVCW6vuz08NaBrikS"
    "7u0bs0bGxF3+Pl45OWOObZ0f5nqx9c+6LAePTMxRLlvvIcGDFQ+Pmjv53MAl31zPvr379/Djy5cYEAAh+QQIEgAAACwAAAAAMAA"
    "wAIEHFCYHUGpk2P+99P8I/wABCBxIsKDBgwgTKlzIsKHDhxAjSpxIsaLFixgzagQw4GHHjQMHfFwoEiTBkgpRmhQocqTBlitPqp"
    "TpMmbLmjdj0lR5sybEAA57cszZEKjBAEhJ9lzqsyBSo0efQj0poKrVq1abSp3qdOvUAVjDXnXplWvXsmDFqhUwoGxShW7TrlXb"
    "tuzCuHPX1vXKEG1eunb7epX7d2xgwVLlEsS6uOrepw8HFw77+G3RrYQns+UbObFmw1IjYv6cdatEz5Rvin08EWpmpiKxjjQbkTD"
    "slmM3yr2t2rHurLxj+/7NNnjaphcr98QcE63IwxvdBqgcGqR0ANdNHoZuvfpA0zrDiwsfT768+fPo04sPCAAh+QQIEgAAACwAAA"
    "AAMAAwAIEHFCYHUGpk2P+99P8I/wABCBxIsKDBgwgTKlzIsKHDhxAjSpxIsaLFixgJDni4MWPBAR0XgvRocKRCkyQ1oiy5MqVA"
    "kCFVxnT5EuZHmzRlooTZEmIAhzw3BnX402CAoyKDKp1pFOnBo1APDhBAtarVqkwBQHX6dCtXAFOvisVK0OvXpmYDhB3LdkDas2i"
    "9rmXb9u3Ct3PpinWblmHauSDHBsba16/ZtTyvJqbK1ytRuViFKgaL2OzDw1YHKwZs+fHWvHozd/Z8FHRoxo59fj4tOLXq0oIXK9"
    "46sSjYzUsnC7RNEfBSmJlJIv4tO2vvyMQ1Gz8uIDnw5jQbl+YpN+dfkIVTvlW73WX37t5HZxUPH7Us7Zzo06tfz769+/fw48tP"
    "GBAAOw=="
)

_PALETTES = {
    "BYTE": ("07506a", "64d8ff", "bdf4ff"),
    "HEX": ("4b246f", "b87cff", "ead7ff"),
    "CACHE": ("70420b", "ffbf63", "ffe8bf"),
    "LOOP": ("781b51", "ff78bc", "ffd0e9"),
    "PING": ("0b6550", "63f0c8", "caffef"),
    "PATCH": ("7b5b00", "ffe06e", "fff6c3"),
    "ROOT": ("173b79", "4c9cff", "c8ddff"),
    "NULL": ("4d5966", "d4e3f1", "ffffff"),
    "GLITCH": ("781522", "ff596f", "ffd1d7"),
}

_TEMPLATE_PALETTE = bytes.fromhex("07142607506a64d8ffbdf4ff")


def _rgb(value: str) -> bytes:
    return bytes.fromhex(value)


def gallery_root_v112() -> Path:
    return Path(__file__).resolve().parents[1] / "assets" / "celdra" / "gremlins" / "v112"


def ensure_gremlin_gif_v112(name: str) -> Path | None:
    """Materialize one real animated GIF in the V112 gallery asset folder."""
    folded = str(name or "").upper()
    palette = _PALETTES.get(folded)
    if palette is None:
        return None
    source = base64.b64decode(_TEMPLATE_GIF)
    replacement = bytes.fromhex("071426") + _rgb(palette[0]) + _rgb(palette[1]) + _rgb(palette[2])
    # The optimized template repeats its four-color table for later frames. Replace
    # every occurrence so the loop never flashes back to BYTE's template palette.
    data = source.replace(_TEMPLATE_PALETTE, replacement)
    root = gallery_root_v112()
    root.mkdir(parents=True, exist_ok=True)
    target = root / f"{folded.casefold()}.gif"
    if not target.is_file() or target.read_bytes() != data:
        temporary = target.with_suffix(".gif.tmp")
        temporary.write_bytes(data)
        temporary.replace(target)
    return target


def materialize_gremlin_gallery_v112() -> tuple[Path, ...]:
    output: list[Path] = []
    for name in KNOWN_GREMLINS:
        path = ensure_gremlin_gif_v112(name)
        if path is not None:
            output.append(path)
    return tuple(output)


if __name__ == "__main__":
    raise SystemExit("Imported by the V112 Celdra gallery.")
