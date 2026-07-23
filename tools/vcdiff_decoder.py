#!/usr/bin/env python3
"""Minimal safe VCDIFF/xdelta3 decoder used by Fragmenter's patch recipes."""

from __future__ import annotations

import argparse
import json
import lzma
import zlib
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable, Iterator


MAGIC = b"\xD6\xC3\xC4\x00"
VCD_DECOMPRESS = 0x01
VCD_CODETABLE = 0x02
VCD_APPHEADER = 0x04
VCD_SOURCE = 0x01
VCD_TARGET = 0x02
VCD_ADLER32 = 0x04
VCD_DATACOMP = 0x01
VCD_INSTCOMP = 0x02
VCD_ADDRCOMP = 0x04

NOOP = 0
ADD = 1
RUN = 2
COPY = 3


class VcdiffError(RuntimeError):
    """Raised when a VCDIFF stream is malformed, unsafe, or incompatible."""


@dataclass(frozen=True)
class Instruction:
    kind: int
    size: int
    mode: int = 0


@dataclass(frozen=True)
class WindowInfo:
    source_length: int
    source_position: int
    target_length: int
    compressed_sections: tuple[str, ...]
    checksum: str | None


@dataclass(frozen=True)
class VcdiffInfo:
    secondary_compressor: int | None
    application_header: str
    windows: tuple[WindowInfo, ...]
    target_size: int


class Reader:
    def __init__(self, data: bytes, label: str = "VCDIFF stream") -> None:
        self.data = data
        self.position = 0
        self.label = label

    @property
    def remaining(self) -> int:
        return len(self.data) - self.position

    def byte(self) -> int:
        if self.position >= len(self.data):
            raise VcdiffError(f"Unexpected end of {self.label}.")
        value = self.data[self.position]
        self.position += 1
        return value

    def take(self, length: int) -> bytes:
        if length < 0 or self.position + length > len(self.data):
            raise VcdiffError(f"Read exceeds {self.label}.")
        value = self.data[self.position : self.position + length]
        self.position += length
        return value

    def varint(self) -> int:
        value = 0
        for _ in range(10):
            byte = self.byte()
            if value > ((1 << 63) - 1) >> 7:
                raise VcdiffError(f"Integer overflow in {self.label}.")
            value = (value << 7) | (byte & 0x7F)
            if not byte & 0x80:
                return value
        raise VcdiffError(f"Overlong integer in {self.label}.")


def _default_code_table() -> tuple[tuple[Instruction, Instruction], ...]:
    noop = Instruction(NOOP, 0)
    rows: list[tuple[Instruction, Instruction]] = [
        (Instruction(RUN, 0), noop),
        (Instruction(ADD, 0), noop),
    ]
    rows.extend((Instruction(ADD, size), noop) for size in range(1, 18))
    for mode in range(9):
        rows.append((Instruction(COPY, 0, mode), noop))
        rows.extend(
            (Instruction(COPY, size, mode), noop) for size in range(4, 19)
        )
    for mode in range(6):
        for add_size in range(1, 5):
            for copy_size in range(4, 7):
                rows.append(
                    (
                        Instruction(ADD, add_size),
                        Instruction(COPY, copy_size, mode),
                    )
                )
    # RFC 3284 table rows 18-20 (indices 235-246): ADD sizes 1..4
    # followed by COPY size 4 for SAME modes 6..8.
    for mode in range(6, 9):
        for add_size in range(1, 5):
            rows.append(
                (
                    Instruction(ADD, add_size),
                    Instruction(COPY, 4, mode),
                )
            )
    # RFC 3284 row 21 (indices 247-255): COPY size 4 for every mode,
    # followed by ADD size 1.
    for mode in range(9):
        rows.append((Instruction(COPY, 4, mode), Instruction(ADD, 1)))
    if len(rows) != 256:
        raise AssertionError(f"Default VCDIFF code table has {len(rows)} entries")
    return tuple(rows)


DEFAULT_CODE_TABLE = _default_code_table()


class AddressCache:
    def __init__(self) -> None:
        self.near = [0, 0, 0, 0]
        self.same = [0] * (3 * 256)
        self.next_near = 0

    def decode(self, mode: int, here: int, reader: Reader) -> int:
        if mode == 0:
            address = reader.varint()
        elif mode == 1:
            distance = reader.varint()
            if distance > here:
                raise VcdiffError("HERE address points before the source segment.")
            address = here - distance
        elif 2 <= mode < 6:
            address = self.near[mode - 2] + reader.varint()
        elif 6 <= mode < 9:
            address = self.same[(mode - 6) * 256 + reader.byte()]
        else:
            raise VcdiffError(f"Unsupported COPY address mode {mode}.")
        if address < 0 or address >= here:
            raise VcdiffError(f"COPY address {address} is outside the available dictionary.")
        self.near[self.next_near] = address
        self.next_near = (self.next_near + 1) % len(self.near)
        self.same[address % len(self.same)] = address
        return address


class SecondaryState:
    def __init__(self, compressor: int | None) -> None:
        self.compressor = compressor
        self._streams: dict[str, lzma.LZMADecompressor] = {}

    def decode(self, data: bytes, label: str) -> bytes:
        if self.compressor != 2:
            raise VcdiffError(
                f"{label} uses unsupported VCDIFF secondary compressor {self.compressor!r}."
            )
        reader = Reader(data, f"compressed {label}")
        expected_size = reader.varint()
        try:
            # xdelta3 keeps one secondary stream per section type across windows.
            # Its LZMA stream omits the normal XZ footer, so eof=False is expected.
            decompressor = self._streams.get(label)
            if decompressor is None:
                decompressor = lzma.LZMADecompressor(format=lzma.FORMAT_AUTO)
                self._streams[label] = decompressor
            decoded = decompressor.decompress(reader.take(reader.remaining))
        except lzma.LZMAError as exc:
            raise VcdiffError(f"Could not decompress {label}: {exc}") from exc
        if len(decoded) != expected_size:
            raise VcdiffError(
                f"{label} decompressed to {len(decoded)} bytes; expected {expected_size}."
            )
        return decoded


def _section(data: bytes, compressed: bool, state: SecondaryState, label: str) -> bytes:
    if not compressed:
        return data
    return state.decode(data, label)


def _header(reader: Reader) -> tuple[int | None, bytes]:
    if reader.take(4) != MAGIC:
        raise VcdiffError("Not a VCDIFF stream (magic header mismatch).")
    indicator = reader.byte()
    if indicator & ~(VCD_DECOMPRESS | VCD_CODETABLE | VCD_APPHEADER):
        raise VcdiffError(f"Unsupported VCDIFF header flags 0x{indicator:02X}.")
    secondary = reader.byte() if indicator & VCD_DECOMPRESS else None
    if indicator & VCD_CODETABLE:
        length = reader.varint()
        reader.take(length)
        raise VcdiffError("Custom VCDIFF code tables are not supported.")
    app_header = reader.take(reader.varint()) if indicator & VCD_APPHEADER else b""
    return secondary, app_header


def _parse_window(
    reader: Reader, state: SecondaryState
) -> tuple[WindowInfo, bytes, bytes, bytes, int]:
    window_indicator = reader.byte()
    if window_indicator & ~(VCD_SOURCE | VCD_TARGET | VCD_ADLER32):
        raise VcdiffError(f"Unsupported VCDIFF window flags 0x{window_indicator:02X}.")
    if window_indicator & VCD_SOURCE and window_indicator & VCD_TARGET:
        raise VcdiffError("A VCDIFF window cannot use SOURCE and TARGET simultaneously.")
    source_length = source_position = 0
    if window_indicator & (VCD_SOURCE | VCD_TARGET):
        source_length = reader.varint()
        source_position = reader.varint()
    delta_length = reader.varint()
    delta_end = reader.position + delta_length
    if delta_end > len(reader.data):
        raise VcdiffError("VCDIFF delta window exceeds the patch stream.")
    target_length = reader.varint()
    delta_indicator = reader.byte()
    if delta_indicator & ~(VCD_DATACOMP | VCD_INSTCOMP | VCD_ADDRCOMP):
        raise VcdiffError(f"Unsupported VCDIFF delta flags 0x{delta_indicator:02X}.")
    data_length = reader.varint()
    instruction_length = reader.varint()
    address_length = reader.varint()
    checksum_value: int | None = None
    if window_indicator & VCD_ADLER32:
        checksum_value = int.from_bytes(reader.take(4), "big")
    data = reader.take(data_length)
    instructions = reader.take(instruction_length)
    addresses = reader.take(address_length)
    if reader.position != delta_end:
        raise VcdiffError(
            f"VCDIFF delta length mismatch: ended at {reader.position}, expected {delta_end}."
        )
    compressed: list[str] = []
    if delta_indicator & VCD_DATACOMP:
        compressed.append("data")
    if delta_indicator & VCD_INSTCOMP:
        compressed.append("instructions")
    if delta_indicator & VCD_ADDRCOMP:
        compressed.append("addresses")
    info = WindowInfo(
        source_length=source_length,
        source_position=source_position,
        target_length=target_length,
        compressed_sections=tuple(compressed),
        checksum=f"{checksum_value:08x}" if checksum_value is not None else None,
    )
    return (
        info,
        _section(data, bool(delta_indicator & VCD_DATACOMP), state, "data section"),
        _section(
            instructions,
            bool(delta_indicator & VCD_INSTCOMP),
            state,
            "instruction section",
        ),
        _section(
            addresses,
            bool(delta_indicator & VCD_ADDRCOMP),
            state,
            "address section",
        ),
        window_indicator,
    )


def inspect_vcdiff(patch: bytes) -> VcdiffInfo:
    reader = Reader(patch)
    secondary, application_header = _header(reader)
    state = SecondaryState(secondary)
    windows: list[WindowInfo] = []
    while reader.remaining:
        info, _data, _instructions, _addresses, _indicator = _parse_window(
            reader, state
        )
        windows.append(info)
    if not windows:
        raise VcdiffError("VCDIFF stream contains no windows.")
    return VcdiffInfo(
        secondary_compressor=secondary,
        application_header=application_header.decode("utf-8", errors="replace"),
        windows=tuple(windows),
        target_size=sum(window.target_length for window in windows),
    )


def _execute_window(
    source_segment: bytes,
    target_length: int,
    data_bytes: bytes,
    instruction_bytes: bytes,
    address_bytes: bytes,
) -> bytes:
    data = Reader(data_bytes, "VCDIFF data section")
    instructions = Reader(instruction_bytes, "VCDIFF instruction section")
    addresses = Reader(address_bytes, "VCDIFF address section")
    address_cache = AddressCache()
    target = bytearray()

    while instructions.remaining and len(target) < target_length:
        code = instructions.byte()
        for instruction in DEFAULT_CODE_TABLE[code]:
            if instruction.kind == NOOP:
                continue
            size = instruction.size or instructions.varint()
            if size < 0 or len(target) + size > target_length:
                raise VcdiffError("Instruction exceeds the declared target window size.")
            if instruction.kind == ADD:
                target.extend(data.take(size))
            elif instruction.kind == RUN:
                target.extend(data.take(1) * size)
            elif instruction.kind == COPY:
                here = len(source_segment) + len(target)
                address = address_cache.decode(instruction.mode, here, addresses)
                remaining = size
                position = address
                if position < len(source_segment):
                    take = min(remaining, len(source_segment) - position)
                    target.extend(source_segment[position : position + take])
                    position += take
                    remaining -= take
                target_position = position - len(source_segment)
                while remaining:
                    available = len(target) - target_position
                    if available <= 0:
                        raise VcdiffError("COPY instruction references unavailable target data.")
                    take = min(remaining, available)
                    target.extend(target[target_position : target_position + take])
                    remaining -= take
            else:
                raise VcdiffError(f"Unsupported VCDIFF instruction {instruction.kind}.")

    if len(target) != target_length:
        raise VcdiffError(
            f"Decoded target window has {len(target)} bytes; expected {target_length}."
        )
    if instructions.remaining or data.remaining or addresses.remaining:
        raise VcdiffError(
            "VCDIFF window contains unused instruction, data, or address bytes."
        )
    return bytes(target)


def iter_decode_vcdiff(
    patch: bytes,
    source_size: int,
    read_source: Callable[[int, int], bytes],
    *,
    verify_checksum: bool = True,
) -> Iterator[tuple[int, bytes]]:
    """Decode a patch one target window at a time.

    The callback keeps large source files (notably DATA.BIN) out of memory.  The
    Tellipatch assets use only VCD_SOURCE windows; VCD_TARGET is deliberately
    refused here because safely streaming an arbitrary previous-target
    dictionary requires a separate random-access target store.
    """
    reader = Reader(patch)
    secondary, _application_header = _header(reader)
    state = SecondaryState(secondary)
    target_position = 0
    while reader.remaining:
        info, data, instructions, addresses, indicator = _parse_window(reader, state)
        if indicator & VCD_SOURCE:
            end = info.source_position + info.source_length
            if end > source_size:
                raise VcdiffError("VCDIFF source segment exceeds the supplied source file.")
            source_segment = read_source(info.source_position, info.source_length)
            if len(source_segment) != info.source_length:
                raise VcdiffError("VCDIFF source callback returned a short segment.")
        elif indicator & VCD_TARGET:
            raise VcdiffError("Streaming VCD_TARGET dictionaries are not supported.")
        else:
            source_segment = b""
        window = _execute_window(
            source_segment,
            info.target_length,
            data,
            instructions,
            addresses,
        )
        if verify_checksum and info.checksum is not None:
            expected = int(info.checksum, 16)
            actual = zlib.adler32(window) & 0xFFFFFFFF
            if actual != expected:
                raise VcdiffError(
                    f"VCDIFF checksum mismatch: expected {expected:08x}, found {actual:08x}."
                )
        yield target_position, window
        target_position += len(window)
    if target_position == 0:
        raise VcdiffError("VCDIFF stream contains no target data.")


def decode_vcdiff(patch: bytes, source: bytes, *, verify_checksum: bool = True) -> bytes:
    return b"".join(
        window
        for _offset, window in iter_decode_vcdiff(
            patch,
            len(source),
            lambda position, length: source[position : position + length],
            verify_checksum=verify_checksum,
        )
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("patch", type=Path)
    parser.add_argument("--source", type=Path)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args(argv)
    try:
        patch = args.patch.read_bytes()
        if args.source is None:
            print(json.dumps(asdict(inspect_vcdiff(patch)), indent=2))
            return 0
        if args.out is None:
            parser.error("--out is required with --source")
        decoded = decode_vcdiff(patch, args.source.read_bytes())
        args.out.write_bytes(decoded)
    except (OSError, VcdiffError) as exc:
        print(f"VCDIFF refused: {exc}")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
