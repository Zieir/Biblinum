import os
import json
from datetime import datetime

source_folder = r"C:\Users\zieir\Desktop\gitlab_biblinum\data\groundtruth_numaclay\separated_groundtruth_titlepages_numaclay"
target_folder = r"C:\Users\zieir\Desktop\dataset\ground_truth"

for filename in os.listdir(source_folder):
    if not filename.endswith(".json"):
        continue

    source_path = os.path.join(source_folder, filename)
    target_path = os.path.join(target_folder, filename)

    if not os.path.isfile(target_path):
        print(f"Absent : {filename}")
        continue

    # Date de création du fichier source (Windows)
    creation_time = os.path.getctime(source_path)
    creation_date = datetime.fromtimestamp(creation_time).isoformat()

    # Lire le JSON cible
    with open(target_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Ajouter la date
    data["creation_date"] = creation_date

    # Sauvegarder
    with open(target_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

    print(f"Ajouté : {filename}")

print("Terminé.")