# delorean-py

Procedural Blender model of a 1981 DeLorean DMC-12, built entirely from Python.
No sculpting, no manual mesh edits, no external assets. The repository *is* the model.

---

## 1. The build contract

`build.py` is the single entry point. Running it must produce a complete, identical
DeLorean every time, from any starting state.

```bash
blender -b -P build.py                 # headless, canonical
blender -b -P build.py -- --render     # headless + write renders/
```

Rules that follow from this:

- **Full reset first.** The build wipes every object, mesh, material, camera, light
  and collection before it starts. Nothing is incremental. Nothing reads prior state.
- **Headless is the source of truth.** If it does not work under `blender -b`, it is
  broken, regardless of how it looks in the GUI. An interactive Blender session is a
  viewer that re-execs the same entry point, never an authoring surface.
- **No manual edits.** If the model is wrong, the fix goes in the Python. A change made
  by hand in the viewport is lost on the next run and must never be relied on.
- **Deterministic.** No randomness without a fixed seed. No wall-clock, no file-order
  dependence, no floating scene state.

## 2. Version pin

Blender **5.2 LTS**. Asserted at startup with an explicit error.

The API moved across 4.x/5.x — `Mesh.use_auto_smooth` is gone, `shade_auto_smooth`
replaces it, Principled BSDF socket names changed (`Specular` -> `Specular IOR Level`,
`Transmission` -> `Transmission Weight`). Unpinned scripts rot silently.

## 3. Conventions

| | |
|---|---|
| Units | metres |
| Up | +Z |
| Nose | **-X** (the car faces -X) |
| Left | +Y |
| Ground plane | Z = 0, wheels contact it exactly |
| Origin | world centre, midway between the axles |

Ground truth dimensions (real DMC-12, millimetres):

| | |
|---|---|
| Length | 4267 |
| Width | 1988 |
| Height | 1140 |
| Wheelbase | 2413 |
| Front track / rear track | 1588 / 1605 |
| Front wheel | 195/60R14 (589.6 mm dia) |
| Rear wheel | 235/60R15 (663.0 mm dia) |

**Published dimensions are the hard ground truth. Reference photographs are shape
confirmation, not measurement.** None of the references is orthographic, so none of
them constrains proportion as tightly as the spec sheet. Where a photo and the spec
disagree, the spec wins.

## 4. Layout

```
build.py                 entry point, orchestration only
delorean/
  config.py              dimensions, RigConfig, BuildConfig
  mesh_utils.py          bmesh/pydata helpers, prisms, booleans, lofting
  materials.py           MaterialLibrary — procedural nodes only
  body.py                lofted cross-section shell, wheel arches, solidify
  doors.py               gullwing split + hinge rig
  glazing.py             windscreen, backlight, side and quarter glass
  wheels.py              tyres + turbine alloys
  lamps.py               head/tail/marker units
  trim.py                bumpers, louvres, mirrors, badges, exhaust
  interior.py            tub, seats, dash, wheel
  scene.py               camera, lights, render settings
  preview.py             isolated-object rendering for fast iteration
  validate.py            post-build assertions
metrics/                 standalone scoring, runs OUTSIDE Blender
references/              source photographs + solved cameras + masks
renders/                 build output (gitignored)
```

## 5. No external assets

Every material is procedural nodes. **No downloads, no HDRIs, no linked libraries.**
The repo must build on a clean machine with nothing but Blender and a `git clone`.

The one permitted image input is the committed reference photographs, used as a world
environment (`delorean/environment.py`). They ship with the repo, so this does not
break the clean-machine rule. Three caveats, all handled in that module:

- **LDR.** Highlights clip at white, so a photo cannot throw the speculars a true HDRI
  would. `highlight_boost` re-expands the top of the range.
- **Not a panorama.** A perspective photo mapped equirectangular puts the ground at the
  poles. It is blended against the procedural gradient, which supplies the correct
  vertical luminance structure while the photo supplies colour and variation.
- **It contains the car.** Downscaled and blended, this reads as surroundings rather
  than a copy of the subject.

`environment = "procedural"` gives a neutral, photo-free gradient. Metric renders must
use it — scoring against a photo while reflecting that same photo is circular.

## 6. Parameterise, don't hardcode

Anything a person might want to change is a field on `RigConfig` / `BuildConfig`:
door angle, steering angle, wheel spin, ride height, camera view. "Doors open at 52
degrees" is a call argument, never a magic number buried in geometry.

## 7. Validation

`delorean/validate.py` runs at the end of every build and raises on failure:

- overall bounding box within tolerance of the published dimensions
- wheels touch Z = 0, do not intersect the arches
- no zero-area faces, no loose vertices or edges
- every object carries at least one material
- expected object set present, names match convention

"Perfect every time" needs teeth. A boolean that silently no-ops must fail the build,
not produce a slightly wrong car.

## 8. Objective fidelity metrics

Scoring lives in `metrics/` and runs in **system Python** (numpy + opencv), never
inside Blender. Blender's bundled interpreter is not to be pip-polluted, and scoring
must run in CI without Blender.

Pipeline: render a clay pass from a solved camera -> edge/silhouette extraction on both
render and reference -> score.

**Gate on silhouette IoU.** Report the rest.

| Metric | Purpose |
|---|---|
| Silhouette IoU | primary gate — is this the right shape |
| Chamfer distance (px) | mean edge displacement, in units you can reason about |
| Boundary F-score (~2-3 px slack) | separates *missing* features from *invented* ones |
| PSNR / MSE on edge maps | reported for familiarity, **not** a gate |

Why IoU and not MSE: edge maps are sparse and binary. A uniform 2 px offset destroys
PSNR on a shape that is actually correct, and PSNR saturates once edges are merely
near each other. It is not a shape metric.

### Camera solve is a prerequisite

MSE against a photograph measures *camera mismatch* until focal length and pose match.
Each reference carries a committed `references/<name>.camera.json` holding solved
intrinsics, extrinsics and the `RigConfig` that matches that photo (four of the six
references have the doors open — scoring a closed-door model against them is noise).

### Masks

Backgrounds dominate Canny — foliage, stone, gravel, rust. Every scored reference has
a committed car mask. Without one the metric mostly measures trees.

### Clay, not materials

Shape metrics must be invariant to shading: flat grey, fixed lights, fixed resolution,
fixed seed. Never score a beauty render.

### Thresholds are measured, not invented

Baselines live in `metrics/baseline.json`. Set targets from what an honest build
actually scores, then ratchet. Do not invent "IoU >= 0.95" up front.

### Running it

```bash
python tools/make_masks.py                                    # car masks
blender -b -P metrics/solve_camera.py -- --reference <stem>   # solve the camera
blender -b -P metrics/render_solved.py -- --reference <stem>  # clay render
python -m metrics.score                                       # scorecard + overlays
```

**Current status: the camera solve is not converging.** It optimises an IoU that
is deliberately blind to framing (bounding-box cropped, width-normalised), and
on a three-quarter reference that objective is maximised by a near-side-on
telephoto pose. Until it optimises true in-frame IoU after fitting distance, the
scores measure camera mismatch rather than model fidelity, and must not be
quoted as a fidelity figure. `metrics/baseline.json` records this.

### Reference triage

| File | Use |
|---|---|
| `front-quarter-left-gravel.jpg` | **scored** — clean, doors closed, trustworthy |
| `studio-front-quarter-door-open.jpg` | **scored** — studio, plain background |
| `rear-quarter-right-doors-open.jpg` | **scored** — clear rear geometry |
| `rear-quarter-left-doors-open.png` | shape reference |
| `front-quarter-left-night-doors-open.jpg` | shape reference — EV conversion, extra decals |
| `front-quarter-right-doors-open.jpg` | **excluded** — AI-generated/retouched: badge reads "VENS", grille and door cut lines inconsistent |

## 9. Visual unit tests

`tests/` is the primary iteration loop. **Every function or class that generates
geometry gets a test that renders what it produced.**

```bash
blender -b -P tests/run_tests.py
blender -b -P tests/run_tests.py -- --only wheel
```

Each test does two things:

1. **Asserts** what can be asserted — bounding box against published dimensions, no
   loose vertices or edges, no zero-area faces, a material on every object, parts
   inside their expected envelope. These fail the run.
2. **Renders** the part in isolation, tightly framed, into `renders/tests/`. These are
   for the eye. A geometry bug is almost never visible in a number and almost always
   obvious in a picture.

Rules for tests:

- **Build into a fresh scene.** `harness.fresh_scene()` wipes everything, so a test
  exercises the real construction path rather than poking at an already-built car.
- **Render from the side the part is meant to be seen from.** A wheel's face points
  +Y; the hero views all sit on -Y and would show its back. Use the `part_*` views.
- **Blueprint-blue backdrop.** Dark parts on a black field are unreadable. The backdrop
  is applied to camera rays only, so the part is still lit and reflects the full studio
  environment (`Environment(backdrop=...)`).
- **Small and fast.** 760 px, 24 samples. The whole wheel suite runs in ~3 seconds.
  If a test takes longer than a couple of seconds, shrink it.
- **Pair each test with its reference crop.** `references/parts/<group>/<name>.png`,
  generated from the committed spec by `tools/crop_references.py`. Compare the render
  against the crop, not against the whole-car photo.

## 10. Iteration discipline

Use **isolated rendering** (`delorean/preview.py`) when working on one part — the
scripted equivalent of local view. Rendering the whole car to check a tail lamp wastes
minutes per iteration. Isolate, render small, render fast.

Per-part reference crops live in `references/parts/`, driven by `references/crops.json`
so they are reproducible. Add a crop when you add a part.

## 11. Repository hygiene

- `delorean.blend` and `renders/` are **build outputs** and are gitignored. The .blend
  is not source; committing it means multi-MB binary diffs on every run.
- Push to `main`. Conventional commit messages. Commit at each working milestone.
- Split code into functions, classes and modules. `build.py` orchestrates and holds no
  geometry.

## 12. Out of scope

Clean quad topology (booleans leave ngons/tris — fine for rendering, bad for
subdivision), armatures, animation, UV unwrapping (procedural materials use generated
and object coordinates).
