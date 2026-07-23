#!/usr/bin/env python3
from __future__ import annotations

import argparse, json, traceback
from pathlib import Path
from iso9660 import Iso9660

TAG = "[ISO_INDEX]"

def emit(kind: str, msg: str):
    # Single-line, easy to parse from GUI
    print(f"{TAG} {kind} {msg}", flush=True)

def main() -> int:
    ap = argparse.ArgumentParser(description="Build an ISO file index (paths, size, LBA) with progress. Output is JSON.")
    ap.add_argument("iso_path", type=Path)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--every", type=int, default=500, help="Emit indexing progress every N files")
    ap.add_argument("--count_every", type=int, default=5000, help="Emit counting progress every N files")
    ap.add_argument("--max_files", type=int, default=400000, help="Safety cap; abort if ISO appears to contain more files than this")
    args = ap.parse_args()

    try:
        iso = Iso9660(args.iso_path).open()
        emit("PHASE", f"Detected layout: sector={iso.sector_size} offset={iso.data_offset} lba_off={getattr(iso,'lba_offset',0)} mode={iso.mode}")

        # Pass 1: count (so GUI can show %)
        emit("PHASE", "Counting files...")
        total = 0
        for _ in iso.iter_files():
            total += 1
            if total % args.count_every == 0:
                emit("PHASE", f"Counting files... ({total})")
            if total >= args.max_files:
                raise MemoryError(f"File count exceeded safety cap ({args.max_files}). This usually means a bad image layout or parse.")
        emit("TOTAL", str(total))

        # Pass 2: stream JSON output (constant memory)
        emit("PHASE", "Indexing files...")
        args.out.parent.mkdir(parents=True, exist_ok=True)

        done = 0
        with args.out.open("w", encoding="utf-8", newline="\n") as out:
            header = {
                "iso": str(args.iso_path),
                "mode": iso.mode,
                "layout": {"sector_size": iso.sector_size, "data_offset": iso.data_offset},
                "count": total,
            }
            out.write("{")
            out.write('"iso":')
            out.write(json.dumps(header["iso"]))
            out.write(',"mode":')
            out.write(json.dumps(header["mode"]))
            out.write(',"layout":')
            out.write(json.dumps(header["layout"]))
            out.write(',"count":')
            out.write(str(total))
            out.write(',"files":[')

            first = True
            for e in iso.iter_files():
                obj = {"path": e.path, "lba": e.lba, "size": e.size, "is_dir": bool(getattr(e, "is_dir", False))}
                if first:
                    first = False
                else:
                    out.write(",")
                out.write(json.dumps(obj, ensure_ascii=False))
                done += 1
                if done % args.every == 0 or done == total:
                    emit("PROGRESS", f"{done} {total} {e.path}")

            out.write("]}")
            out.write("\n")

        emit("PHASE", f"Done. Wrote: {args.out}")
        return 0

    except Exception as e:
        emit("ERROR", f"{type(e).__name__}: {e}")
        traceback.print_exc()
        return 2

if __name__ == "__main__":
    raise SystemExit(main())
