# Prezervia — animal vital-range data model

Background data engine for the Prezervia abnormal-activity tracker.
Dependency-free. The dataset (`animal_vitals.csv`) ships inside the package.

## Install

```bash
pip install -e .
```

## Use it in your app

```python
from prezervia import load_animals, find, check_alarm

animals = load_animals()                 # every animal profile
lab = find("Dog", "Labrador Retriever", "1-6")   # one profile

# A live sensor reading comes in from the collar:
result = check_alarm(lab, {"hr": 150, "resp": 40, "temp": 40.0, "movement": 10})
print(result.alarm)       # True  -> raise the alert in the UI
print(result.abnormal)    # ['hr=150 (HIGH)', 'resp=40 (HIGH)', ...]
```

## What is in the data

- 66 animal profiles across 18 species.
- Priority targets: **Dog** (24 breed/age rows) and **Cat** (14 breeds).
- Groups: `Pet`, `Farm`, `Zoo`.
- Per profile: heart rate, breathing, body temp (°C), a 0–100 movement score,
  height in cm, age range in years, and typical lifespan.

## Signals

| signal key | meaning | unit |
|---|---|---|
| `hr` | heart rate | beats / minute |
| `resp` | breathing | breaths / minute |
| `temp` | body temperature | °C |
| `movement` | activity proxy | 0–100 |

`movement` is an activity stand-in, not a clinical vital. A real collar builds
it from a motion sensor.

## Self-test

```bash
python -m prezervia
```

Data source: Merck Veterinary Manual, VCA, Cornell Feline Health, zoo-vet refs.
