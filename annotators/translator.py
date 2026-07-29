import json
import sys
from pathlib import Path

READABILITY_MAP = {
    "Lisible": "Readable",
    "Non lisible": "Not readable",
}

CAUSE_MAP = {
    "absent": "absent",
    "qualite": "quality",
    "recouvert": "covered",
    "manuscrit": "handwritten",
}

def translate_annotations_block(annotations):
    """annotations = the dict under '_annotations' in each JSON file."""
    new_annotations = {}
    for field_path, entry in annotations.items():
        new_field_path = "language" if field_path == "langue" else field_path

        if field_path == "_note" or not isinstance(entry, dict):
            # leave free-text notes / anything unexpected untouched
            new_annotations[new_field_path] = entry
            continue

        new_entry = {}
        for k, v in entry.items():
            if k == "lisibilite":
                new_entry["readability"] = READABILITY_MAP.get(v, v)
            elif k == "cause":
                new_entry["cause"] = CAUSE_MAP.get(v, v)
            else:
                # "correction" and anything else: leave as-is, it's real content
                new_entry[k] = v
        new_annotations[new_field_path] = new_entry
    return new_annotations

def process_folder(folder):
    folder = Path(folder)
    files = list(folder.glob("*.json"))
    count = 0
    for f in files:
        with open(f, "r", encoding="utf-8") as fh:
            data = json.load(fh)

        changed = False

        if "langue" in data:
            data["language"] = data.pop("langue")
            changed = True

        if "_annotations" in data and isinstance(data["_annotations"], dict):
            data["_annotations"] = translate_annotations_block(data["_annotations"])
            changed = True

        if changed:
            with open(f, "w", encoding="utf-8") as fh:
                json.dump(data, fh, ensure_ascii=False, indent=2)
            count += 1
    print(f"Modified {count}/{len(files)} files in {folder}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python translate_annotations.py /path/to/folder")
        sys.exit(1)
    process_folder(sys.argv[1])