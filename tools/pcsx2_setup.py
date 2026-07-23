#!/usr/bin/env python3
"""Small, conservative PCSX2 setup helpers for .hack//Fragment."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import os
import re
import shutil
import sys
import tempfile
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable


class Pcsx2SetupError(RuntimeError):
    """Raised when a PCSX2 setup change cannot be made safely."""


USB_SECTION = "USB1"
USB_TYPE_KEY = "Type"
FRAGMENT_KEYBOARD_TYPE = "hidkbd"
NETWORK_SECTION = "DEV9/Eth"
NETWORK_ENABLE_KEY = "EthEnable"
RAW_PS2_CARD_PAGE_SIZE = 528
RAW_PS2_CARD_MIB_SIZE = 1024 * RAW_PS2_CARD_PAGE_SIZE * 2
SUPPORTED_CARD_SIZES = {
    size_mib * RAW_PS2_CARD_MIB_SIZE for size_mib in (8, 16, 32, 64)
}
BUNDLED_CARD_RESOURCE_NAME = "Fragment-Network.ps2.gz"
BUNDLED_CARD_RAW_NAME = "Fragment-Network.ps2"
BUNDLED_CARD_RAW_SIZE = 8 * RAW_PS2_CARD_MIB_SIZE
BUNDLED_CARD_RAW_SHA256 = (
    "ba1bcad1cc7b9b16800b821605d2784f74fa2ef560cc9c5c7d874853006de140"
)


@dataclass(frozen=True)
class KeyboardStatus:
    config_path: str
    current_type: str | None
    configured: bool
    encoding: str


@dataclass(frozen=True)
class KeyboardSetupReport:
    status: str
    config_path: str
    previous_type: str | None
    current_type: str
    backup_path: str | None


@dataclass(frozen=True)
class FragmentPcsx2SetupReport:
    status: str
    config_path: str
    previous_keyboard_type: str | None
    previous_network_enabled: str | None
    keyboard_type: str
    network_enabled: str
    backup_path: str | None


@dataclass(frozen=True)
class MemoryCardInfo:
    source_path: str
    size: int
    size_mib: int | None
    sha256: str
    supported_raw_size: bool


@dataclass(frozen=True)
class MemoryCardInstallReport:
    status: str
    source_path: str
    destination_path: str
    size: int
    sha256: str


def _decode_ini(data: bytes) -> tuple[str, str, bytes]:
    if data.startswith(b"\xef\xbb\xbf"):
        return data.decode("utf-8-sig"), "utf-8-sig", b"\xef\xbb\xbf"
    if data.startswith(b"\xff\xfe"):
        return data.decode("utf-16"), "utf-16-le", b"\xff\xfe"
    if data.startswith(b"\xfe\xff"):
        return data.decode("utf-16"), "utf-16-be", b"\xfe\xff"
    try:
        return data.decode("utf-8"), "utf-8", b""
    except UnicodeDecodeError:
        # Legacy Windows PCSX2 builds could leave ANSI comments in their INI.
        return data.decode("cp1252"), "cp1252", b""


def _encode_ini(text: str, encoding: str, bom: bytes) -> bytes:
    if encoding == "utf-8-sig":
        return bom + text.encode("utf-8")
    if encoding == "utf-16-le":
        return bom + text.encode("utf-16-le")
    if encoding == "utf-16-be":
        return bom + text.encode("utf-16-be")
    return text.encode(encoding)


def _read_ini(path: Path) -> tuple[str, str, bytes]:
    try:
        data = path.read_bytes()
    except OSError as exc:
        raise Pcsx2SetupError(f"Could not read PCSX2 settings: {exc}") from exc
    if not data:
        raise Pcsx2SetupError("The selected PCSX2 settings file is empty.")
    return _decode_ini(data)


def _section_ranges(lines: list[str], name: str) -> list[tuple[int, int]]:
    wanted = name.casefold()
    headers: list[tuple[int, str]] = []
    for index, line in enumerate(lines):
        match = re.match(r"^\s*\[([^]\r\n]+)\]\s*(?:[;#].*)?(?:\r?\n)?$", line)
        if match:
            headers.append((index, match.group(1).strip()))
    ranges: list[tuple[int, int]] = []
    for pos, (start, section_name) in enumerate(headers):
        if section_name.casefold() != wanted:
            continue
        end = headers[pos + 1][0] if pos + 1 < len(headers) else len(lines)
        ranges.append((start, end))
    return ranges


def _setting_value(text: str, section: str, key: str) -> str | None:
    lines = text.splitlines(keepends=True)
    ranges = _section_ranges(lines, section)
    if len(ranges) > 1:
        raise Pcsx2SetupError(f"PCSX2.ini contains more than one [{section}] section.")
    if not ranges:
        return None
    start, end = ranges[0]
    value: str | None = None
    for line in lines[start + 1 : end]:
        match = re.match(r"^\s*([^=;#]+?)\s*=\s*(.*?)\s*(?:\r?\n)?$", line)
        if match and match.group(1).strip().casefold() == key.casefold():
            if value is not None:
                raise Pcsx2SetupError(f"[{section}] contains more than one {key} setting.")
            value = match.group(2).strip()
    return value


def _usb_type(text: str) -> str | None:
    return _setting_value(text, USB_SECTION, USB_TYPE_KEY)


def inspect_keyboard_config(config_path: str | Path) -> KeyboardStatus:
    path = Path(config_path).expanduser().resolve()
    if not path.is_file():
        raise Pcsx2SetupError(f"PCSX2 settings file was not found: {path}")
    text, encoding, _bom = _read_ini(path)
    current = _usb_type(text)
    return KeyboardStatus(
        config_path=str(path),
        current_type=current,
        configured=(current or "").casefold() == FRAGMENT_KEYBOARD_TYPE,
        encoding=encoding,
    )


def _replace_setting(text: str, section: str, key: str, value: str) -> tuple[str, str | None]:
    newline = "\r\n" if "\r\n" in text else "\n"
    lines = text.splitlines(keepends=True)
    ranges = _section_ranges(lines, section)
    if len(ranges) > 1:
        raise Pcsx2SetupError(f"PCSX2.ini contains more than one [{section}] section.")
    previous = _setting_value(text, section, key)

    if not ranges:
        separator = "" if not text or text.endswith(("\n", "\r")) else newline
        prefix = newline if text and not text.endswith((newline + newline,)) else ""
        return (
            text + separator + prefix + f"[{section}]{newline}{key} = {value}{newline}",
            previous,
        )

    start, end = ranges[0]
    key_indexes: list[int] = []
    for index in range(start + 1, end):
        match = re.match(r"^(\s*)([^=;#]+?)(\s*=\s*)(.*?)(\r?\n)?$", lines[index])
        if match and match.group(2).strip().casefold() == key.casefold():
            key_indexes.append(index)
            lines[index] = (
                f"{match.group(1)}{match.group(2)}{match.group(3)}"
                f"{value}{match.group(5) or ''}"
            )
    if len(key_indexes) > 1:
        raise Pcsx2SetupError(f"[{section}] contains more than one {key} setting.")
    if not key_indexes:
        lines.insert(start + 1, f"{key} = {value}{newline}")
    return "".join(lines), previous


def _replace_usb_type(text: str) -> tuple[str, str | None]:
    return _replace_setting(
        text, USB_SECTION, USB_TYPE_KEY, FRAGMENT_KEYBOARD_TYPE
    )


def _unique_backup(path: Path) -> Path:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    candidate = path.with_name(f"{path.name}.fragmenter-backup-{stamp}")
    counter = 2
    while candidate.exists():
        candidate = path.with_name(f"{path.name}.fragmenter-backup-{stamp}-{counter}")
        counter += 1
    return candidate


def _atomic_write(path: Path, data: bytes) -> None:
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temp_path = Path(temp_name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
    except Exception:
        try:
            temp_path.unlink(missing_ok=True)
        except OSError:
            pass
        raise


def configure_fragment_keyboard(
    config_path: str | Path, *, dry_run: bool = False
) -> KeyboardSetupReport:
    path = Path(config_path).expanduser().resolve()
    if not path.is_file():
        raise Pcsx2SetupError(f"PCSX2 settings file was not found: {path}")
    text, encoding, bom = _read_ini(path)
    updated, previous = _replace_usb_type(text)
    if (previous or "").casefold() == FRAGMENT_KEYBOARD_TYPE and updated == text:
        return KeyboardSetupReport(
            status="already-configured",
            config_path=str(path),
            previous_type=previous,
            current_type=FRAGMENT_KEYBOARD_TYPE,
            backup_path=None,
        )
    if dry_run:
        return KeyboardSetupReport(
            status="would-configure",
            config_path=str(path),
            previous_type=previous,
            current_type=FRAGMENT_KEYBOARD_TYPE,
            backup_path=None,
        )

    backup = _unique_backup(path)
    try:
        shutil.copy2(path, backup)
        _atomic_write(path, _encode_ini(updated, encoding, bom))
    except OSError as exc:
        raise Pcsx2SetupError(f"Could not update PCSX2 settings: {exc}") from exc
    return KeyboardSetupReport(
        status="configured",
        config_path=str(path),
        previous_type=previous,
        current_type=FRAGMENT_KEYBOARD_TYPE,
        backup_path=str(backup),
    )


def configure_fragment_pcsx2(
    config_path: str | Path, *, dry_run: bool = False
) -> FragmentPcsx2SetupReport:
    """Enable the Fragment USB keyboard and PCSX2 Ethernet in one transaction."""
    path = Path(config_path).expanduser().resolve()
    if not path.is_file():
        raise Pcsx2SetupError(f"PCSX2 settings file was not found: {path}")
    text, encoding, bom = _read_ini(path)
    keyboard_text, previous_keyboard = _replace_setting(
        text, USB_SECTION, USB_TYPE_KEY, FRAGMENT_KEYBOARD_TYPE
    )
    updated, previous_network = _replace_setting(
        keyboard_text, NETWORK_SECTION, NETWORK_ENABLE_KEY, "true"
    )
    changed = updated != text
    if not changed:
        status = "already-configured"
    elif dry_run:
        status = "would-configure"
    else:
        status = "configured"
    backup: Path | None = None
    if changed and not dry_run:
        backup = _unique_backup(path)
        try:
            shutil.copy2(path, backup)
            _atomic_write(path, _encode_ini(updated, encoding, bom))
        except OSError as exc:
            raise Pcsx2SetupError(f"Could not update PCSX2 settings: {exc}") from exc
    return FragmentPcsx2SetupReport(
        status=status,
        config_path=str(path),
        previous_keyboard_type=previous_keyboard,
        previous_network_enabled=previous_network,
        keyboard_type=FRAGMENT_KEYBOARD_TYPE,
        network_enabled="true",
        backup_path=str(backup) if backup else None,
    )


def discover_pcsx2_ini(extra_roots: Iterable[str | Path] = ()) -> list[Path]:
    candidates: list[Path] = []
    appdata = os.environ.get("APPDATA")
    documents = os.environ.get("USERPROFILE")
    roots = [Path(value).expanduser() for value in extra_roots]
    if appdata:
        roots.append(Path(appdata) / "PCSX2")
    if documents:
        roots.extend((Path(documents) / "Documents" / "PCSX2", Path(documents) / "PCSX2"))
    for root in roots:
        if root.suffix.casefold() == ".exe":
            root = root.parent
        for candidate in (root / "inis" / "PCSX2.ini", root / "PCSX2.ini"):
            if candidate.is_file() and candidate not in candidates:
                candidates.append(candidate.resolve())
    return candidates


def inspect_memory_card(source_path: str | Path) -> MemoryCardInfo:
    source = Path(source_path).expanduser().resolve()
    if not source.is_file():
        raise Pcsx2SetupError(f"Memory-card file was not found: {source}")
    if source.suffix.casefold() != ".ps2":
        raise Pcsx2SetupError("Choose a PCSX2 raw memory-card file ending in .ps2.")
    size = source.stat().st_size
    digest = hashlib.sha256()
    with source.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    size_mib = size // RAW_PS2_CARD_MIB_SIZE if size % RAW_PS2_CARD_MIB_SIZE == 0 else None
    return MemoryCardInfo(
        source_path=str(source),
        size=size,
        size_mib=size_mib,
        sha256=digest.hexdigest(),
        supported_raw_size=size in SUPPORTED_CARD_SIZES,
    )


def install_memory_card(
    source_path: str | Path,
    memcards_folder: str | Path,
    *,
    destination_name: str = "Fragment-Network.ps2",
) -> MemoryCardInstallReport:
    info = inspect_memory_card(source_path)
    if not info.supported_raw_size:
        raise Pcsx2SetupError(
            "The card is not a standard PCSX2 8/16/32/64 MiB raw .ps2 image."
        )
    folder = Path(memcards_folder).expanduser().resolve()
    if not folder.is_dir():
        raise Pcsx2SetupError(f"PCSX2 memcards folder was not found: {folder}")
    name = Path(destination_name).name
    if not name.casefold().endswith(".ps2"):
        name += ".ps2"
    destination = folder / name
    if destination.exists():
        raise Pcsx2SetupError(
            f"A memory card already exists at {destination}. Choose another name; nothing was overwritten."
        )
    try:
        shutil.copy2(info.source_path, destination)
    except OSError as exc:
        raise Pcsx2SetupError(f"Could not install the memory card: {exc}") from exc
    copied = inspect_memory_card(destination)
    if copied.sha256 != info.sha256:
        destination.unlink(missing_ok=True)
        raise Pcsx2SetupError("Memory-card verification failed; the incomplete copy was removed.")
    return MemoryCardInstallReport(
        status="installed",
        source_path=info.source_path,
        destination_path=str(destination),
        size=info.size,
        sha256=info.sha256,
    )


def bundled_memory_card_path() -> Path:
    if getattr(sys, "frozen", False):
        root = Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent))
    else:
        root = Path(__file__).resolve().parents[1]
    return root / "resources" / BUNDLED_CARD_RESOURCE_NAME


def install_bundled_memory_card(
    memcards_folder: str | Path,
    *,
    destination_name: str = BUNDLED_CARD_RAW_NAME,
    resource_path: str | Path | None = None,
) -> MemoryCardInstallReport:
    """Install the verified clean Fragment network card from the app bundle."""
    resource = (
        Path(resource_path).expanduser().resolve()
        if resource_path is not None
        else bundled_memory_card_path()
    )
    if not resource.is_file():
        raise Pcsx2SetupError(
            "The included Fragment network card is missing from this build."
        )
    folder = Path(memcards_folder).expanduser().resolve()
    if not folder.is_dir():
        raise Pcsx2SetupError(f"PCSX2 memcards folder was not found: {folder}")
    name = Path(destination_name).name
    if not name.casefold().endswith(".ps2"):
        name += ".ps2"
    destination = folder / name
    if destination.exists():
        raise Pcsx2SetupError(
            f"A memory card already exists at {destination}. Choose another name; nothing was overwritten."
        )

    fd, temp_name = tempfile.mkstemp(
        prefix=f".{destination.name}.", suffix=".tmp", dir=folder
    )
    temp_path = Path(temp_name)
    digest = hashlib.sha256()
    size = 0
    try:
        with os.fdopen(fd, "wb") as output, gzip.open(resource, "rb") as source:
            for chunk in iter(lambda: source.read(1024 * 1024), b""):
                output.write(chunk)
                digest.update(chunk)
                size += len(chunk)
            output.flush()
            os.fsync(output.fileno())
        actual_hash = digest.hexdigest()
        if size != BUNDLED_CARD_RAW_SIZE or actual_hash != BUNDLED_CARD_RAW_SHA256:
            raise Pcsx2SetupError(
                "The included network card failed integrity verification. Nothing was installed."
            )
        if destination.exists():
            raise Pcsx2SetupError(
                f"A memory card appeared at {destination} while installing. Nothing was overwritten."
            )
        os.replace(temp_path, destination)
    except (OSError, EOFError, gzip.BadGzipFile) as exc:
        raise Pcsx2SetupError(f"Could not install the included memory card: {exc}") from exc
    finally:
        try:
            temp_path.unlink(missing_ok=True)
        except OSError:
            pass
    return MemoryCardInstallReport(
        status="installed",
        source_path=str(resource),
        destination_path=str(destination),
        size=size,
        sha256=BUNDLED_CARD_RAW_SHA256,
    )


def _print_dataclass(value: object) -> None:
    for key, item in asdict(value).items():
        print(f"{key}: {item}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    inspect_parser = subparsers.add_parser("inspect-keyboard")
    inspect_parser.add_argument("config", type=Path)
    keyboard_parser = subparsers.add_parser("enable-keyboard")
    keyboard_parser.add_argument("config", type=Path)
    keyboard_parser.add_argument("--dry-run", action="store_true")
    setup_parser = subparsers.add_parser("setup-fragment")
    setup_parser.add_argument("config", type=Path)
    setup_parser.add_argument("--dry-run", action="store_true")
    card_parser = subparsers.add_parser("inspect-card")
    card_parser.add_argument("card", type=Path)
    install_parser = subparsers.add_parser("install-card")
    install_parser.add_argument("card", type=Path)
    install_parser.add_argument("memcards_folder", type=Path)
    install_parser.add_argument("--name", default="Fragment-Network.ps2")
    bundled_parser = subparsers.add_parser("install-bundled-card")
    bundled_parser.add_argument("memcards_folder", type=Path)
    bundled_parser.add_argument("--name", default=BUNDLED_CARD_RAW_NAME)
    bundled_parser.add_argument("--resource", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == "inspect-keyboard":
            result = inspect_keyboard_config(args.config)
        elif args.command == "enable-keyboard":
            result = configure_fragment_keyboard(args.config, dry_run=args.dry_run)
        elif args.command == "setup-fragment":
            result = configure_fragment_pcsx2(args.config, dry_run=args.dry_run)
        elif args.command == "inspect-card":
            result = inspect_memory_card(args.card)
        elif args.command == "install-card":
            result = install_memory_card(args.card, args.memcards_folder, destination_name=args.name)
        else:
            result = install_bundled_memory_card(
                args.memcards_folder,
                destination_name=args.name,
                resource_path=args.resource,
            )
    except Pcsx2SetupError as exc:
        parser.error(str(exc))
    _print_dataclass(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
