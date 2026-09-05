# delorean-py

A 1981 **DeLorean DMC-12**, modelled entirely in Python. No sculpting, no manual mesh
edits, no external assets — the repository *is* the model. Run one script, get a car.

```bash
blender -b -P build.py
```

---

## What this is

Every panel, wheel, lamp and material in this model is generated from code. The body is
lofted from hand-authored cross-sections, the gullwing doors are boolean-split out of the
finished shell so they fit their own aperture exactly, and the brushed stainless steel is
a procedural node graph rather than a texture map.

Dimensions come from the real car, not from eyeballing photographs:

| | |
|---|---|
| Length | 4267 mm |
| Width | 1988 mm |
| Height | 1140 mm |
| Wheelbase | 2413 mm |
| Front wheels | 195/60R14 |
| Rear wheels | 235/60R15 |

## Requirements

- **Blender 5.2 LTS** (pinned — the Python API moved across 4.x/5.x)
- Python 3.10+ with `numpy` and `opencv-python-headless`, for the metrics suite only

```bash
pip install -r requirements.txt
```

Blender's bundled interpreter needs nothing extra. The metrics run outside it.

## Usage

```bash
# optional: fetch CC0 HDRI environments (not committed)
python tools/fetch_hdri.py

# build the model, headless
blender -b -P build.py

# build and write renders to renders/
blender -b -P build.py -- --render

# build with the doors open and the wheels turned
blender -b -P build.py -- --doors 52 --steer 12

# hero render in a real HDRI environment
blender -b -P build.py -- --engine cycles --environment hdri --hdri warehouse     --render --views hero_front_left

# write a self-contained delorean.blend (gitignored build output)
blender -b -P build.py -- --engine cycles --environment hdri --save

# score the current build against the reference photographs
python -m metrics.score
```

HDRI presets: `studio`, `autoshop`, `warehouse`, `dusk`, `outdoor`. Rotate one with
`--hdri-rotation`.

To work on it interactively, open Blender and re-exec `build.py` from the scripting
workspace. The script fully resets the scene on every run, so there is no stale state to
clear first.

## How it fits together

```
build.py            entry point — orchestration only, no geometry
delorean/
  config.py         dimensions, RigConfig, BuildConfig
  mesh_utils.py     lofting, prisms, booleans, bmesh helpers
  materials.py      procedural node graphs
  body.py           cross-section shell, wheel arches, panel thickness
  doors.py          gullwing split and hinge rig
  glazing.py        windscreen, backlight, side and quarter glass
  wheels.py         tyres and turbine alloys
  lamps.py          head, tail and marker units
  trim.py           bumpers, louvres, mirrors, badges, exhaust
  interior.py       tub, seats, dash, steering wheel
  scene.py          camera, lighting, render settings
  preview.py        isolated-object rendering for fast iteration
  validate.py       post-build assertions
metrics/            fidelity scoring — runs outside Blender
references/         source photographs, solved cameras, masks
```

## Objective fidelity

The model is not "done when it looks right". It is scored against the reference
photographs and the numbers are committed.

Renders a clay pass from a camera solved to match each photograph, then compares:

| Metric | Purpose |
|---|---|
| **Silhouette IoU** | the gate — is this the right shape |
| Chamfer distance | mean edge displacement, in pixels |
| Boundary F-score | separates missing features from invented ones |
| PSNR / MSE | reported for familiarity, not a gate |

Edge maps are sparse and binary, so a uniform two-pixel offset wrecks PSNR on a shape
that is actually correct. IoU is the honest number; the rest are diagnostics.

Baselines live in `metrics/baseline.json` and are measured, not invented — set from what
an honest build actually scores, then ratcheted upward.

## Design notes

**Why lofted cross-sections.** The DMC-12 is a wedge with hard creases, not a set of
blended primitives. Twenty-one hand-authored sections, each eight points from the
underbody centreline over the sill, past the swage crease, across the shoulder and over
the roof, reproduce Giugiaro's folded-paper surfacing far better than any amount of
subdivision.

**Why the doors are boolean-split.** Modelling a door separately means fighting to make
it fit its aperture. Cutting it out of a finished shell means the gap is exactly the gap
you asked for, everywhere, by construction.

**Why no textures.** Brushed stainless is anisotropic reflection plus fine directional
bump. That is four nodes. A texture map would be larger than this entire repository.

## Contributing

Fixes go in the Python. A change made by hand in the viewport is lost on the next run.

See [CLAUDE.md](CLAUDE.md) for the full build contract, coordinate conventions and
validation rules.

## Licence

Model code is Apache 2.0 (see [LICENSE](LICENSE)). Reference photographs are the
property of their respective owners and are included for shape comparison only.
