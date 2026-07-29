import os
import json

folder = r"./annotated_data"
fields = [
    "metadata.authors",
    "metadata.publisher",
    "metadata.date",
    "metadata.publication_place"
]

counts = {field: 0 for field in fields}
all_four_absent = 0

for filename in os.listdir(folder):
    if not filename.endswith(".json"):
        continue

    path = os.path.join(folder, filename)

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    annotations = data.get("_annotations", {})

    missing_fields = []

    for field in fields:
        annotation = annotations.get(field, {})

        is_absent = (
            annotation.get("lisibilite") == "Non lisible"
            and annotation.get("cause") == "absent"
        )

        if is_absent:
            counts[field] += 1
            missing_fields.append(field)

    # Les 4 champs absents en même temps
    if len(missing_fields) == 4:
        all_four_absent += 1

print("=== Champs absents individuellement ===")
for field, count in counts.items():
    print(f"{field} : {count}")

print("\n=== Les 4 absents en même temps ===")
print(all_four_absent)