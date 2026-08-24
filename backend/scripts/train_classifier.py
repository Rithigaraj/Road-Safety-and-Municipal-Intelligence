"""Train the Random Forest tile classifier that powers the sklearn backend.

Generates a randomised synthetic dataset (jittered variants of the sample
generators), extracts patch features, trains a RandomForest and saves it to
data/models/tile_rf.joblib.

Usage:  python -m scripts.train_classifier
"""
from __future__ import annotations

import random
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageEnhance, ImageFilter

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.ml.features import TILE, extract_features  # noqa: E402

TILE_MODEL_PATH = (
    Path(__file__).resolve().parent.parent / "data" / "models" / "tile_rf.joblib"
)
GRID_STEP = 128          # non-overlapping labelling grid
VARIANTS_PER_CLASS = 70
BACKGROUND_VARIANTS = 40
RANDOM_SEED = 7

# nominal defect regions in the base 512x512 samples (x1, y1, x2, y2)
DEFECT_BOXES = {
    "pothole": (140, 140, 390, 340),
    "road_crack": (55, 55, 475, 465),
    "garbage": (120, 140, 390, 350),
    "water_leakage": (160, 130, 410, 340),
    "broken_streetlight": (220, 190, 380, 511),
    "damaged_traffic_sign": (140, 125, 430, 275),
    "blocked_drainage": (110, 315, 400, 511),
}

CLASSES = list(DEFECT_BOXES.keys()) + ["background"]


# ------------------------------------------------------------- augmentations

def _augment(img: Image.Image, rng: random.Random):
    """Random zoom/translate/flip/brightness/noise; returns (img, box_map_fn).

    box_map_fn maps a box from the original 512-space into the augmented one.
    """
    w, h = img.size
    zoom = rng.uniform(0.85, 1.25)
    cw, ch = int(w / zoom), int(h / zoom)
    ox = rng.randint(0, max(w - cw, 0))
    oy = rng.randint(0, max(h - ch, 0))
    flip = rng.random() < 0.5

    def map_box(box):
        x1, y1, x2, y2 = box
        nx1, ny1, nx2, ny2 = ((x1 - ox) * zoom, (y1 - oy) * zoom,
                              (x2 - ox) * zoom, (y2 - oy) * zoom)
        if flip:
            nx1, nx2 = w - nx2, w - nx1
        return [nx1, ny1, nx2, ny2]

    out = img.crop((ox, oy, ox + cw, oy + ch)).resize((w, h), Image.BILINEAR)
    if flip:
        out = out.transpose(Image.FLIP_LEFT_RIGHT)

    out = ImageEnhance.Brightness(out).enhance(rng.uniform(0.75, 1.25))
    out = ImageEnhance.Contrast(out).enhance(rng.uniform(0.75, 1.25))
    if rng.random() < 0.4:
        out = out.filter(ImageFilter.GaussianBlur(rng.uniform(0.3, 1.2)))

    arr = np.asarray(out).astype(np.float32)
    arr += np.random.default_rng().normal(0, rng.uniform(0, 10), arr.shape)
    return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8)), map_box


def _tile_labels(box_mapped) -> dict[tuple[int, int], float]:
    """Grid-cell -> overlap fraction with the mapped defect box."""
    x1, y1, x2, y2 = [max(v, 0) for v in box_mapped]
    labels = {}
    for gy in range((512 - GRID_STEP) // GRID_STEP + 1):
        for gx in range((512 - GRID_STEP) // GRID_STEP + 1):
            tx1, ty1 = gx * GRID_STEP, gy * GRID_STEP
            tx2, ty2 = tx1 + GRID_STEP, ty1 + GRID_STEP
            ix = max(0, min(x2, tx2) - max(x1, tx1))
            iy = max(0, min(y2, ty2) - max(y1, ty1))
            inter = ix * iy
            union = GRID_STEP * GRID_STEP
            labels[(gy, gx)] = inter / union
    return labels


def extract_rows():
    from scripts.generate_samples import GENERATORS

    rng = random.Random(RANDOM_SEED)
    rows_X, rows_y = [], []

    def add_tiles(img: Image.Image, cls: str, box=None):
        if box is not None:
            img_aug, map_box = _augment(img, rng)
            overlaps = _tile_labels(map_box(box))
        else:
            img_aug, _ = _augment(img, rng)
            overlaps = {}
        arr = np.asarray(img_aug)
        for gy in range((512 - TILE) // GRID_STEP + 1):
            for gx in range((512 - TILE) // GRID_STEP + 1):
                y, x = gy * GRID_STEP, gx * GRID_STEP
                tile = arr[y:y + TILE, x:x + TILE]
                if tile.shape[0] < TILE or tile.shape[1] < TILE:
                    continue
                frac = overlaps.get((gy, gx), None)
                if box is None:
                    label = cls                       # background tiles
                elif frac >= 0.45:
                    label = cls                       # clearly on-defect
                else:
                    continue                          # ambiguous -> drop
                rows_X.append(extract_features(tile))
                rows_y.append(label)

    # plain asphalt backgrounds (no defect)
    from scripts.generate_samples import _canvas, _texture

    print("generating dataset ...")
    for i in range(BACKGROUND_VARIANTS):
        base = _texture(_canvas((rng.randint(95, 135),) * 3), rng, scale=rng.uniform(0.3, 0.8))
        add_tiles(base.resize((512, 512)), "background")

    for cls, gen in GENERATORS.items():
        base_img = gen()
        nominal = DEFECT_BOXES.get(cls)
        for i in range(VARIANTS_PER_CLASS):
            add_tiles(base_img, cls, box=nominal)

    return np.stack(rows_X), np.array(rows_y)


def main() -> dict:
    X, y = extract_rows()
    print(f"dataset: {X.shape[0]} tiles x {X.shape[1]} features "
          f"({ {c: int((y == c).sum()) for c in sorted(set(y))} })")

    from sklearn.ensemble import RandomForestClassifier
    from sklearn.model_selection import cross_val_score, train_test_split
    from sklearn.metrics import classification_report

    Xtr, Xte, ytr, yte = train_test_split(X, y, test_size=0.2, stratify=y,
                                          random_state=RANDOM_SEED)
    model = RandomForestClassifier(
        n_estimators=220, max_depth=None, min_samples_leaf=2,
        n_jobs=-1, random_state=RANDOM_SEED,
    )

    cv = cross_val_score(model, Xtr, ytr, cv=3, n_jobs=-1)
    print(f"3-fold CV accuracy: {cv.mean():.3f} ± {cv.std():.3f}")

    model.fit(Xtr, ytr)
    report = classification_report(yte, model.predict(Xte), digits=3)
    print(report)

    import joblib

    TILE_MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump({"model": model, "version": "rf-tile-v1",
                 "classes": CLASSES}, TILE_MODEL_PATH)
    print(f"saved {TILE_MODEL_PATH}")
    return {"cv": round(float(cv.mean()), 4)}


if __name__ == "__main__":
    sys.exit(main())
