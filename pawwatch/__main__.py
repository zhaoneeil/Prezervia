"""Self-test / demo. Run: python -m pawwatch"""

from . import load_animals, find, check_alarm


def main() -> None:
    animals = load_animals()
    species = sorted({a.species for a in animals})
    print(f"Loaded {len(animals)} animal profiles across {len(species)} species.")
    dogs = sorted({a.breed_or_type for a in animals if a.species == "Dog"})
    cats = sorted({a.breed_or_type for a in animals if a.species == "Cat"})
    print(f"Dog breeds: {len(dogs)} — {', '.join(dogs)}")
    print(f"Cat breeds: {len(cats)} — {', '.join(cats)}")

    lab = find("Dog", "Labrador Retriever", "1-6", animals)
    print("\nLabrador (1-6 yr) ranges:")
    print(f"  heart {lab.hr} bpm  breath {lab.resp} br/min  temp {lab.temp_c} C")

    print("\nAlarm test (dog in distress):")
    result = check_alarm(lab, {"hr": 150, "resp": 40, "temp": 40.0, "movement": 10})
    print(f"  alarm={result.alarm}  abnormal={result.abnormal}")


if __name__ == "__main__":
    main()
