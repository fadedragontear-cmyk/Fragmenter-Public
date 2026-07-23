# Fragmenter setup resources

## Fragment-Network.ps2.gz

This is a deterministic gzip copy of a clean 8 MiB PCSX2 raw memory card set up
only with .hack//Fragment's network configuration. It was supplied and approved
for inclusion by the Fragmenter project owner.

- Installed filename: `Fragment-Network.ps2`
- Raw size: `8,650,752` bytes
- Raw SHA-256: `ba1bcad1cc7b9b16800b821605d2784f74fa2ef560cc9c5c7d874853006de140`
- Gzip SHA-256: `a4908186919267885d6080193356439a30b786e65aca97fe258282a7339e511b`
- Visible save directory: `BISLPS-25527DOTHACK`
- Visible configuration file: `BWNETCNF`

The installer expands the resource into a temporary file inside the selected
PCSX2 `memcards` directory, verifies the exact raw size and SHA-256, and only
then installs it. Existing memory cards are never overwritten.

## Bundled English and Fragment 4.0 resources

`game_setup/` contains the exact verified resources used by the one-step
**Build Fragment 4.0 English** transaction. They are stored as Base64 text so
the repository connector and Windows portable pack preserve their binary bytes
exactly; Fragmenter decodes them into its application-data cache and verifies
their hashes before use.

The English patch resource reconstructs the exact official Tellipatch v3.8
`patches.zip`:

- Size: `994,064` bytes.
- SHA-256:
  `9ae767029f7c1c724ceaaf62882fd36f10e34e254d70e26761b747558c7b9eb9`
- Exactly seven expected XDelta filenames.
- Every ZIP member passes CRC validation.

The Fragment 4.0 completion resource contains only verified differing ranges,
not either source ISO or complete game files:

- Encoded source: `Fragment-4.0-completion.zip.b64`
- Decoded size: `288,070` bytes.
- Decoded SHA-256:
  `46ee3644fca9023695a092ab829a16bd03a73dc252586130297e41731e792de1`
- Eight source-hash-bound and target-hash-bound logical files.
- Every payload member passes size, SHA-256, range, and final-target checks.

The original Tellipatch installer, patcher executables, credentials, .NET
runtime, ImgBurn, source ISO, and reference 4.0 ISO are not bundled or run.

## Tellipatch-gamelines.csv.gz

This is a deterministic gzip (`gzip -n -9`) copy of the supplied live
translation sheet export.

- Raw CSV size: `1,423,897` bytes
- Raw CSV SHA-256:
  `8be9895ae5a53442f66874debd3fcd3b3607e94f40d3c3bc46cd79f0b26244ab`
- Gzip size: `612,419` bytes
- Gzip SHA-256:
  `b6dacbab4b6e10829b81821ab62cde69f9f1cfe60116d4a2a7ead7dd0739c56d`
- Rows: `7,953` total; `5,768` marked `Translated`

The native applicator preserves embedded line breaks and intentionally blank
translations, encodes text as CP932, enforces every original field length, and
applies rows in sheet order.
