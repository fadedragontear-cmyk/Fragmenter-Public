# Fragmenter ISO bridge

This small helper gives Fragmenter a complete PS2 UDF rebuild path for
replacement files that no longer fit in their original ISO extents. It is
intended to be published as a self-contained executable and called silently by
the Fragmenter GUI.

End users should not need to install .NET, Ps2IsoTools, ImgBurn, tellipatch, or
FragmentUpdater.

## Engine selection

Fragmenter uses two complementary paths:

1. `iso_patch_engine.py` handles byte edits and exact-size replacements in
   place. This preserves the original disc layout and is the preferred path.
2. `Fragmenter.IsoBridge` rebuilds the UDF image when a replacement file has
   changed size.

Both paths require the exact source ISO SHA-256 from the patch manifest, refuse
to overwrite the source image, write to a temporary file, and verify the
patched output before completing.

## Manifest

The bridge consumes the same schema-1 manifest used by the Python engine. It
supports `write_bytes` and `replace_file` operations. Unlike the
layout-preserving engine, a `replace_file` payload may have a different size
from the original ISO file.

A `replace_file` operation must be the only operation targeting that internal
file. Multiple non-overlapping `write_bytes` operations may target one file.

## Maintainer build

The release build should publish the bridge once per target architecture and
place the resulting executable in Fragmenter's bundled runtime directory.

```powershell
dotnet publish .\tools\iso_bridge\Fragmenter.IsoBridge.csproj `
  -c Release -r win-x64 --self-contained true `
  -p:PublishSingleFile=true
```

The current public target is Windows x64. A Windows x86 build can be added only
if the final Fragmenter release still supports 32-bit Windows.

## Direct invocation

```text
Fragmenter.IsoBridge.exe source.iso patch.json output.iso
```

Success and refusal results are emitted as JSON so the GUI can display a short,
human-readable result while retaining a detailed project log.

## Current integration status

The experimental V117 GUI exposes **Tools → Build Patched ISO...**. Its
dispatcher automatically uses the layout-preserving Python engine for
same-size changes and this bridge for resized replacements. The GUI runs the
work in the background and reports the verified output hash.

Release packaging is the remaining integration step. This environment does not
contain the .NET SDK, so the bridge has not yet been compiled here. The first
Windows acceptance build must publish the self-contained bridge, place it at
`runtime/Fragmenter.IsoBridge.exe`, and exercise a real resized-file patch.
