# Legacy Fragmenter command-line tools

These command-line entrypoints are retained for maintainer research and
historical workflows. They are not imported, launched, or packaged by the
Fragmenter 1.0 public application.

Run them from the repository root when a documented legacy workflow requires
one:

```bat
py maintainer\legacy_cli\fragmenter.py --help
py maintainer\legacy_cli\fragmenter_diagnostics.py --help
py maintainer\legacy_cli\fragmenter_wip.py --help
```

Their repository-root resolution is explicit, so moving them here does not
change their access to `tools/`.
