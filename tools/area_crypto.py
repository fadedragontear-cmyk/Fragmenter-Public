#!/usr/bin/env python3
"""Area Server payload encryption helpers.

Encrypted files are laid out as a 16-byte file key followed by a payload
transformed with the per-install area key from ``data/area_crypto.json``.
"""

from __future__ import annotations

import argparse
import json
import string
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AREA_CRYPTO_JSON = ROOT / "data" / "area_crypto.json"
FILEKEY_SIZE = 16
AREAKEY_SIZE = 256
PREVIEW_SIZE = 512


def load_area_key(path: Path = AREA_CRYPTO_JSON) -> bytes:
    """Load and validate the 256-byte area key."""
    with path.open("r", encoding="utf-8") as fh:
        data = json.load(fh)
    raw_key = data.get("areakey")
    if not isinstance(raw_key, list):
        raise ValueError(f"area key in {path} must be a list")
    try:
        key = bytes(raw_key)
    except ValueError as exc:
        raise ValueError(f"area key in {path} must contain byte values") from exc
    if len(key) != AREAKEY_SIZE:
        raise ValueError(f"area key in {path} must parse to exactly {AREAKEY_SIZE} bytes, got {len(key)}")
    return key


def _validate_filekey(filekey: bytes) -> None:
    if len(filekey) != FILEKEY_SIZE:
        raise ValueError(f"filekey must be exactly {FILEKEY_SIZE} bytes, got {len(filekey)}")


def decrypt_payload(filekey: bytes, cipher: bytes) -> bytes:
    """Decrypt payload bytes using the stored file key and area key."""
    _validate_filekey(filekey)
    areakey = load_area_key()
    return bytes(filekey[i % FILEKEY_SIZE] ^ ((byte + areakey[i % AREAKEY_SIZE]) & 0xFF) for i, byte in enumerate(cipher))


def encrypt_payload(filekey: bytes, plain: bytes) -> bytes:
    """Encrypt payload bytes using the stored file key and area key."""
    _validate_filekey(filekey)
    areakey = load_area_key()
    return bytes(((filekey[i % FILEKEY_SIZE] ^ byte) - areakey[i % AREAKEY_SIZE]) & 0xFF for i, byte in enumerate(plain))


def _preview_density(data: bytes) -> float:
    if not data:
        return 0.0
    printable = set(bytes(string.printable, "ascii"))
    return sum(1 for byte in data if byte in printable) / len(data)


def _likely_encrypted(size: int, density: float) -> str:
    if size < FILEKEY_SIZE + 1:
        return "no"
    if density >= 0.55:
        return "yes"
    if density <= 0.25:
        return "no"
    return "uncertain"


def _read_encrypted(path: Path) -> tuple[bytes, bytes]:
    data = path.read_bytes()
    if len(data) < FILEKEY_SIZE + 1:
        raise ValueError(f"{path} is shorter than {FILEKEY_SIZE + 1} bytes")
    return data[:FILEKEY_SIZE], data[FILEKEY_SIZE:]


def _refuse_overwrite_input(input_path: Path, out_path: Path) -> None:
    try:
        if input_path.resolve() == out_path.resolve():
            raise ValueError("refusing to overwrite the input path")
    except FileNotFoundError:
        if input_path.absolute() == out_path.absolute():
            raise ValueError("refusing to overwrite the input path")


def _parse_filekey_hex(value: str) -> bytes:
    if len(value) != FILEKEY_SIZE * 2:
        raise ValueError("--filekey-hex must be exactly 32 hex characters")
    try:
        return bytes.fromhex(value)
    except ValueError as exc:
        raise ValueError("--filekey-hex must contain only hex characters") from exc


def cmd_identify(args: argparse.Namespace) -> int:
    path = Path(args.file)
    data = path.read_bytes()
    filekey = data[:FILEKEY_SIZE] if len(data) >= FILEKEY_SIZE else b""
    if len(data) >= FILEKEY_SIZE + 1:
        preview = decrypt_payload(filekey, data[FILEKEY_SIZE:FILEKEY_SIZE + PREVIEW_SIZE])
        density = _preview_density(preview)
    else:
        density = 0.0
    print(f"file size: {len(data)}")
    print(f"filekey hex: {filekey.hex() if filekey else '(unavailable)'}")
    print(f"decrypted preview string density: {density:.3f}")
    print(f"likely encrypted: {_likely_encrypted(len(data), density)}")
    return 0


def cmd_decrypt(args: argparse.Namespace) -> int:
    path = Path(args.file)
    out = Path(args.out)
    _refuse_overwrite_input(path, out)
    filekey, cipher = _read_encrypted(path)
    out.write_bytes(decrypt_payload(filekey, cipher))
    return 0


def cmd_encrypt(args: argparse.Namespace) -> int:
    plain_path = Path(args.plain)
    out = Path(args.out)
    _refuse_overwrite_input(plain_path, out)
    if args.key_from:
        key_from = Path(args.key_from)
        _refuse_overwrite_input(key_from, out)
        filekey, _ = _read_encrypted(key_from)
    else:
        filekey = _parse_filekey_hex(args.filekey_hex)
    out.write_bytes(filekey + encrypt_payload(filekey, plain_path.read_bytes()))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Encrypt/decrypt .hack//fragment Area Server payloads")
    sub = parser.add_subparsers(dest="command", required=True)

    identify = sub.add_parser("identify", help="Inspect a possibly encrypted file")
    identify.add_argument("file")
    identify.set_defaults(func=cmd_identify)

    decrypt = sub.add_parser("decrypt", help="Decrypt file payload to --out")
    decrypt.add_argument("file")
    decrypt.add_argument("--out", required=True)
    decrypt.set_defaults(func=cmd_decrypt)

    encrypt = sub.add_parser("encrypt", help="Encrypt a plain payload to --out")
    encrypt.add_argument("plain")
    group = encrypt.add_mutually_exclusive_group(required=True)
    group.add_argument("--key-from", dest="key_from")
    group.add_argument("--filekey-hex")
    encrypt.add_argument("--out", required=True)
    encrypt.set_defaults(func=cmd_encrypt)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except ValueError as exc:
        parser.error(str(exc))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
