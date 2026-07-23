# Celdra application assets

Celdra PNG and GIF files are bundled application resources. They should be committed to the same branch as Fragmenter so a clone, ZIP download, or packaged Windows build contains the artwork automatically. End users must not be asked to copy image files into the application after installation.

Git supports binary PNG/GIF files normally. The GitHub connector used by ChatGPT can edit text but cannot author binary diffs; binary artwork can still be uploaded through GitHub's web interface, GitHub Desktop, or normal `git add` / `git commit` / `git push`.

## Discovery

Fragmenter scans this directory recursively for:

- `.png` files
- animated `.gif` files
- numbered PNG sequences such as `01.png` through `70.png`
- state-prefixed sequences such as `talk_000.png`, `talk_001.png`
- large dragongirl emote/sprite sheets

A numbered sequence is grouped by directory and filename prefix. The longest suitable sequence can be used as the baby-dragon idle animation until a manifest assigns states explicitly.

## Suggested layout

```text
assets/celdra/
├── manifest.json
├── baby_dragon/
│   ├── 01.png
│   ├── 02.png
│   └── ...
├── dragongirl/
│   ├── emotes_01.png
│   └── emotes_02.png
└── generated_emotes/
    ├── happy/
    ├── smirk/
    └── thinking/
```

The built-in programmatic pixel egg/hatching animation always remains available. Missing or malformed external artwork cannot prevent Fragmenter from starting.

## Emote separator / classifier

The temporary **Celdra Test** tab contains a non-destructive emote-sheet workbench:

1. Select a bundled PNG or GIF in the asset inventory.
2. Press **Use selected Celdra asset**.
3. Drag a rectangle around one pose. The displayed image may be downscaled, but the tool converts the selection back to original-image coordinates.
4. Assign a state, pose name, and optional tags.
5. Press **Add / Update** to store the definition in `manifest.json`.
6. Use **Preview**, **Show in Celdra viewport**, or **Export selected PNG** to verify the result.

The original sheet is never changed. Exported crops are written only when explicitly requested and go under `generated_emotes/<state>/`.

For evenly arranged sheets, the grid candidate generator accepts row/column counts, edge padding, and horizontal/vertical gaps. It creates `unclassified` entries that can be reviewed and renamed individually.

**Copy selected JSON** and **Copy all definitions JSON** provide an easy handoff when crop coordinates and labels need to be reviewed outside the application.

## Manifest

`manifest.json` may assign frame sequences and classified emote crops:

```json
{
  "version": 1,
  "states": {
    "idle": {
      "frames": [
        "baby_dragon/01.png",
        "baby_dragon/02.png"
      ]
    }
  },
  "emotes": [
    {
      "id": "emotes-01-smirk-side-eye-x0-y0-w128-h128",
      "state": "smirk",
      "pose": "side-eye",
      "source": "dragongirl/emotes_01.png",
      "crop": {"x": 0, "y": 0, "width": 128, "height": 128},
      "tags": ["sarcastic", "reaction"],
      "notes": "",
      "output": "generated_emotes/smirk/emotes-01-smirk-side-eye-x0-y0-w128-h128.png",
      "enabled": true
    }
  ]
}
```

Crop definitions are now persistent classifier data. Automatic use of those classified poses in the scripted Celdra timeline remains a separate integration step after the rectangles and labels are reviewed.
