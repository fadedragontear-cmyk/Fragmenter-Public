# Celdra avatar frames

Place transparent PNG keyframes in this folder. Fragmenter V49 loads them at startup and groups them by the text before the first underscore.

Recommended names:

- `idle_000.png`, `idle_001.png`, ...
- `talk_000.png`, `talk_001.png`, ...
- `thinking_000.png`, `thinking_001.png`, ...
- `smirk_000.png`, `smirk_001.png`, ...
- `boot_000.png`, `boot_001.png`, ...

Guidelines:

- Use the same canvas dimensions for every frame.
- A transparent background is supported by Tk 8.6 PNG loading.
- 256×256 or 320×320 is a practical target. Larger frames are integer-subsampled for display.
- Keep the character centered so state changes do not jump.
- The files are presentation assets only; missing frames never block extraction.
- When a requested state has no frames, Fragmenter falls back to `idle`, then to a text placeholder.

The first pass uses a fixed frame interval. A later manifest may add per-frame timing, mouth cues, or stage-specific sequences.
