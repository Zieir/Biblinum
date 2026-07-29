import os
os.environ["CUDA_LAUNCH_BLOCKING"] = "1"

import requests
import re
import time
import json
import logging
import warnings
import io
from pathlib import Path
from PIL import Image
import torch
from transformers import AutoProcessor, AutoModelForImageTextToText

# Configuration des logs et warnings
warnings.filterwarnings('ignore')
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; research-script/1.0)"}
BASE_API = "https://numaclay.universite-paris-saclay.fr/api"
ITEM_SET_ID = 134441

class Qwen8BTitlePageDetector:
    """Processeur basé sur Qwen3-VL-8B-Instruct pour détecter les pages de titre originales."""

    def __init__(self, device: str = "cuda" if torch.cuda.is_available() else "cpu"):
        self.device = device
        self.model_name = "Qwen/Qwen3-VL-8B-Instruct"
        self._load_model()

    def _load_model(self):
        try:
            logger.info(f"Chargement de {self.model_name} sur {self.device}")
            self.processor = AutoProcessor.from_pretrained(self.model_name, trust_remote_code=True)
            self.model = AutoModelForImageTextToText.from_pretrained(
                self.model_name,
                torch_dtype=torch.float16 if self.device == "cuda" else torch.float32,
                device_map=self.device,
                trust_remote_code=True,
                attn_implementation="sdpa"
            )
            self.model.eval()
            logger.info("Modèle chargé et prêt pour la détection.")
        except Exception as e:
            logger.error(f"Échec du chargement du modèle : {e}")
            raise

    @torch.no_grad()
    def is_title_page(self, image_bytes: bytes) -> tuple[bool, str]:
        """Vérifie si l'image est la page de titre principale du livre."""
        image = Image.open(io.BytesIO(image_bytes)).convert('RGB')

        # Prompt modifié pour cibler spécifiquement la page de titre (titre + auteur + éditeur)
        prompt = (
            "This is a scanned page from a historical book. "
            "Is this the main title page of the book? "
            "A main title page MUST prominently display the full title, and usually includes the author's name and the publisher's information (city, publisher name, year). "
            "Do NOT confuse it with a half-title page (faux-titre) which only shows a short title and nothing else, or a cover page, or a preface. "
            "Answer ONLY with: YES or NO, followed by one short reason."
        )

        messages = [
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "image": image,
                        "max_pixels": 2000000
                    },
                    {"type": "text", "text": prompt},
                ],
            }
        ]

        inputs = self.processor.apply_chat_template(
            messages,
            tokenize=True,
            add_generation_prompt=True,
            return_dict=True,
            return_tensors="pt",
        ).to(self.device)

        output_ids = self.model.generate(
            **inputs,
            max_new_tokens=60,
            do_sample=False
        )

        answer = self.processor.decode(
            output_ids[0][inputs["input_ids"].shape[1]:],
            skip_special_tokens=True
        ).strip()

        is_title = answer.upper().startswith("YES")
        return is_title, answer


def extract_title(item: dict) -> str:
    titles = item.get("dcterms:title", [])
    if titles and isinstance(titles, list):
        return titles[0].get("property_value", "Titre Inconnu")
    return "Titre Inconnu"


def extract_ark(item: dict) -> str | None:
    for id_entry in item.get("dcterms:identifier", []):
        url = id_entry.get("@id", "")
        match = re.search(r'ark:/12148/([a-zA-Z0-9]+)', url)
        if match:
            return match.group(1)

        val = id_entry.get("property_value", "")
        match_val = re.search(r'ark:/12148/([a-zA-Z0-9]+)', val)
        if match_val:
            return match_val.group(1)
    return None


def fetch_all_items_omega(item_set_id: int, max_items: int = 1000) -> list:
    items = []
    page = 1
    logger.info(f"Récupération des items de la collection {item_set_id} depuis Omeka S...")

    while len(items) < max_items:
        r = requests.get(
            f"{BASE_API}/items",
            params={"item_set_id": item_set_id, "per_page": 50, "page": page},
            headers=HEADERS,
            timeout=30
        )
        if r.status_code != 200:
            logger.warning(f"Erreur HTTP {r.status_code} à la page {page}")
            break

        data = r.json()
        if not data:
            break

        items.extend(data)
        logger.info(f"   -> Items récupérés : {len(items)}")
        page += 1
        time.sleep(0.3)

    return items[:max_items]


def download_numaclay_title_pages(output_dir="./data/dataset_numaclay_titlepages", max_results=1000):
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    rejected_dir = output_path / "rejected_pages"
    rejected_dir.mkdir(exist_ok=True)

    # Gestion de la reprise après interruption (timeout Slurm)
    catalogue_path = output_path / "catalogue.json"
    catalogue = []

    if catalogue_path.exists():
        try:
            with open(catalogue_path, "r", encoding="utf-8") as f:
                catalogue = json.load(f)
            logger.info(f"Reprise du traitement : Catalogue existant chargé ({len(catalogue)} entrées).")
        except json.JSONDecodeError:
            logger.warning("Catalogue existant corrompu. Il sera écrasé par les nouvelles données.")

    existing_found_files = list(output_path.glob("*.jpeg"))
    found_arks = {f.stem.split('_')[0] for f in existing_found_files}

    existing_rejected_files = list(rejected_dir.glob("*.jpeg"))
    rejected_pages_set = {f.name for f in existing_rejected_files}

    logger.info(f"État de la reprise : {len(found_arks)} arks avec page de titre et {len(rejected_pages_set)} pages ignorées déjà traités.")

    items = fetch_all_items_omega(ITEM_SET_ID, max_items=max_results)
    logger.info(f"Total : {len(items)} items uniques chargés depuis l'API.")

    detector = Qwen8BTitlePageDetector()

    logger.info("Début de l'inspection des pages IIIF et extraction avec Qwen3-VL...")

    downloaded, rejected = 0, 0

    for i, item in enumerate(items, 1):
        title = extract_title(item)
        ark = extract_ark(item)

        if not ark:
            logger.warning(f"[{i}/{len(items)}] ARK introuvable pour : {title[:60]}")
            continue

        if ark in found_arks:
            logger.info(f"[{i}/{len(items)}] Ignoré : L'ARK {ark} possède déjà sa page de titre extraite.")
            continue

        # MODIFICATION ICI : On cherche entre la page 2 et 10 incluses (range 2 à 11)
        for page_num in range(1, 2):
            page_id = f"f{page_num}"
            filename = f"{ark}_{page_id}.jpeg"

            if filename in rejected_pages_set:
                logger.info(f"[{i}/{len(items)}] Ignoré : Page {page_id} de l'ARK {ark} déjà analysée (non pertinente).")
                continue

            img_url = f"https://gallica.bnf.fr/iiif/ark:/12148/{ark}/{page_id}/full/1000,/0/native.jpg"

            try:
                img_response = requests.get(img_url, timeout=15, headers=HEADERS)

                if img_response.status_code == 200 and img_response.headers.get("Content-Type", "").startswith("image/"):

                    is_title, reason = detector.is_title_page(img_response.content)

                    if is_title:
                        img_path = output_path / filename

                        with open(img_path, 'wb') as f:
                            f.write(img_response.content)

                        logger.info(f"[{i}/{len(items)}] PAGE DE TITRE DÉTECTÉE ({page_id}) : {ark} — {title[:40]}")
                        downloaded += 1

                        catalogue.append({
                            "ark": ark,
                            "page": page_id,
                            "title": title,
                            "image_filename": filename,
                            "image_path": str(img_path),
                            "qwen_reason": reason
                        })

                        with open(catalogue_path, "w", encoding="utf-8") as f:
                            json.dump(catalogue, f, ensure_ascii=False, indent=2)

                        break # On a trouvé la page de titre, on passe au livre suivant
                    else:
                        filename_rejected = rejected_dir / filename
                        with open(filename_rejected, 'wb') as f:
                            f.write(img_response.content)

                        logger.info(f"[{i}/{len(items)}] Page non retenue ({page_id}) : {ark} — {reason}")
                        rejected += 1
                else:
                    break # Plus d'images disponibles sur cet ARK

                time.sleep(0.2)

            except Exception as e:
                logger.error(f"[{i}/{len(items)}] Erreur sur la page {page_id} pour l'ARK {ark} : {e}")
                if "CUDA" in str(e):
                    torch.cuda.empty_cache()
                break

    logger.info(f"""
Traitement terminé.
- Nouvelles pages de titre extraites : {downloaded}
- Pages ignorées (rejected_pages/) : {rejected}
- Chemin du catalogue : {catalogue_path}
""")

if __name__ == "__main__":
    # N'hésitez pas à augmenter max_results selon vos besoins
    download_numaclay_title_pages(max_results=1000)