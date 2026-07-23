#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from raw_audio_probe import write_region_reports
from scei_hd_bd import decode_bank_streams, load_inputs, parse_bank


def _candidate(workspace: Path, iso_path: str) -> Path | None:
    rel = Path(*iso_path.lower().split('/'))
    names = [rel, Path(iso_path), Path(iso_path).name, Path(iso_path).name.lower()]
    roots = [workspace / 'media_pipeline' / 'extracted' / 'top_level', workspace / 'media_pipeline' / 'extracted']
    for root in roots:
        for name in names:
            p = root / name
            if p.is_file():
                return p
    for p in (workspace / 'media_pipeline' / 'extracted').rglob(Path(iso_path).name):
        if p.is_file() and p.as_posix().lower().endswith(iso_path.lower()):
            return p
    return None


def decode_eff(workspace: Path) -> int:
    hd = _candidate(workspace, 'NETGUI/EFF.HD')
    bd = _candidate(workspace, 'NETGUI/EFF.BD')
    reports = workspace / 'reports'; reports.mkdir(parents=True, exist_ok=True)
    if not hd or not bd:
        (reports / 'eff_sound_bank_decode.json').write_text(json.dumps({'status': 'missing', 'required': ['NETGUI/EFF.HD', 'NETGUI/EFF.BD'], 'hd_path': str(hd) if hd else None, 'bd_path': str(bd) if bd else None}, indent=2), encoding='utf-8')
        return 2
    data, paired_bd_size, source = load_inputs(hd)
    bank = parse_bank(data, source, 0, paired_bd_size or bd.stat().st_size, len(data))
    rows = decode_bank_streams(bank, bd.read_bytes(), workspace / 'media_pipeline' / 'decoded', 'NETGUI_EFF')
    payload: dict[str, Any] = {'status': 'complete', 'scope': ['NETGUI/EFF.HD', 'NETGUI/EFF.BD'], 'hd_path': str(hd), 'bd_path': str(bd), 'bank': bank.as_dict(), 'decoded_streams': rows}
    (reports / 'eff_sound_bank_decode.json').write_text(json.dumps(payload, indent=2), encoding='utf-8')
    return 0


def map_bgm_food(workspace: Path) -> int:
    reports = workspace / 'reports'; reports.mkdir(parents=True, exist_ok=True)
    items = []
    status = 0
    for iso_path in ('VOICE/BGM.BIN', 'VOICE/FOOD.BIN'):
        path = _candidate(workspace, iso_path)
        if not path:
            items.append({'source_iso_path': iso_path, 'status': 'missing'})
            status = 2
            continue
        json_path, txt_path, region_map = write_region_reports(path.read_bytes(), path, None, reports)
        items.append({'source_iso_path': iso_path, 'status': 'mapped', 'path': str(path), 'json_path': str(json_path), 'text_path': str(txt_path), 'region_count': len(region_map.get('regions', []))})
    (reports / 'bgm_food_region_maps.json').write_text(json.dumps({'status': 'partial' if status else 'complete', 'scope': ['VOICE/BGM.BIN', 'VOICE/FOOD.BIN'], 'items': items}, indent=2), encoding='utf-8')
    return status


def main() -> int:
    ap = argparse.ArgumentParser(description='Focused audio prep steps for Fragmenter GUI RUN ALL.')
    sub = ap.add_subparsers(dest='command', required=True)
    for name in ('decode-eff-bank', 'map-bgm-food'):
        sp = sub.add_parser(name); sp.add_argument('--workspace', type=Path, required=True)
    args = ap.parse_args()
    if args.command == 'decode-eff-bank':
        return decode_eff(args.workspace)
    if args.command == 'map-bgm-food':
        return map_bgm_food(args.workspace)
    return 1

if __name__ == '__main__':
    raise SystemExit(main())
