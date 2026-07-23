# Final 3D and visual-classification checkpoint — 2026-07-15

This checkpoint closes the manual visual classification, 3D-preview stabilization, and implementation pass. Remaining format questions are documented rather than patched speculatively. Active development returns to audio after V37 acceptance.

## Final canonical classification snapshot

- 3,274 manually classified assets
- 12 categories
- 55 retained review notes
- 33 flagged assets/report references
- 45 saved camera views
- 89 assets with retained notes, flags, reports, default poses, or camera state

Category totals:

- Profile Pictures: 2,234
- Character / NPC: 360
- Weapon: 356
- Monster / Boss: 152
- Wallpaper: 58
- Unknown CCSF: 49
- Food: 16
- Environment / Field: 15
- Objects: 11
- Summon / Statue / Entity candidate: 11
- UI / System: 7
- Effects: 5

The repository snapshot is fallback data. Existing project settings, the latest portable ledger, and the immediate review sidecar remain newer authorities and are not overwritten by canonical defaults.

### Report-backed corrections retained

- `particle.ccs`: `Environment / Field` → `Effects`
- `xeffect.ccs`: `Environment / Field` → `Effects`
- `xp_text.ccs`: `Environment / Field` → `UI / System`

The final ledger also adds the reviewed Objects family and corrects the distinction between `cw*` character-body packages and actual `cw*` weapon families.

## Accepted orientation and reference view

`ca1ab_bl.ccs` remains the accepted upright reference:

- Euler component map: `ZYX`
- Euler order: `ZYX`
- Local signs: `+-+`
- Hierarchy: `L×P`

Its saved default pose, camera basis, free-fly position, notes, and flagged report are retained in the canonical state snapshot.

## Reports that do not show a remaining generic decoder failure

The following packages contain decoded geometry and/or textures. Their remaining questions concern asset purpose, selected clump, animation state, or display semantics rather than a safe universal parser correction:

- `titleo.ccs`
- `xdhhack.ccs`
- `xp_text.ccs`
- `xeffect.ccs`
- `particle.ccs`
- `ede1.ccs`
- `str8800e.ccs`

`ede1.ccs` identifies its deformable resource as a wing model, so a wings-only preview is consistent with the file contents.

## Deferred research

No speculative renderer or geometry changes were made for these files:

- `sd1.ccs`, `sdba.ccs`: geometry and textures decode; visibility requires PS2 material/alpha semantics research.
- `sfzair1.ccs`: decoded texture alpha is fully transparent; blend/test behavior requires research.
- `str8000.ccs`: many clumps/material references but no local renderable model/texture payload.
- `x7404cam.ccs`: camera/control animation data without renderable geometry.
- `x02.ccs`, `str7400e.ccs`, `xnote.ccs`: no safely recoverable renderable model structure in the supplied reports.

These remain archived research items rather than active 3D work.

## Final UI disposition

- Exactly one top-level Research tab is retained after all normal tabs finish building.
- Classification Report, Audit X-Series, and Texture Mapping Audit live in Research.
- Texture Mapping Audit writes its result into the Research workspace.
- Selecting a TEX node in CCSF Contents decodes that one texture and displays it as a read-only 2D PNG on the existing preview canvas.
- Wireframe or Textured mode returns from the 2D texture view.
- The accepted renderer, animation, camera, Euler, clump, notes, and classification controls otherwise remain unchanged.
