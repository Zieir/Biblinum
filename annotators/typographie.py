"""
Ajoute une classification typographique a chaque JSON deja corrige (jsons_corriges/),
en interrogeant Gemma (vision) via l'API OpenAI-compatible Aristote sur l'image associee.

Usage:
    python ajouter_typographie.py
    python ajouter_typographie.py --force        # re-genere meme si deja present
    python ajouter_typographie.py --key typographie

Variables d'environnement attendues (memes que le reste du pipeline) :
    ARISTOTE_API_KEY   -> cle API
    ARISTOTE_BASE_URL  -> URL de base de l'API (ex: https://.../v1)
"""

import os
import json
import base64
import argparse
from openai import OpenAI

IMAGE_DIR  = "images"
OUTPUT_DIR = "annotated_data"
MODEL_NAME = "gemma-4-31b"

PROMPT = """You are a typography expert.
Given the name, image, or sample of a typeface or script, identify what kind of writing style it belongs to.
Return:
- Primary category (e.g., Serif/Roman, Sans-serif, Blackletter, Script, Monospace, Display, etc.)
- More specific subtype if applicable (e.g., Fraktur, Textura, Old Style, Didone, Humanist, Slab Serif, Copperplate, etc.)
Format your answer as:
Category: <major category>
Subtype: <specific subtype or "None">
Explanation: <brief explanation>
Example:
Input: Fraktur
Category: Blackletter
Subtype: Fraktur"""


def encode_image(path):
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def find_image_for(base_name):
    for ext in (".png", ".jpg", ".jpeg", ".PNG", ".JPG", ".JPEG"):
        candidate = os.path.join(IMAGE_DIR, base_name + ext)
        if os.path.exists(candidate):
            return candidate
    return None


def parse_response(text):
    """Extrait Category / Subtype / Explanation depuis la reponse texte du modele."""
    result = {"category": None, "subtype": None, "explanation": None, "raw": text}
    for line in text.splitlines():
        line = line.strip()
        low = line.lower()
        if low.startswith("category:"):
            result["category"] = line.split(":", 1)[1].strip()
        elif low.startswith("subtype:"):
            result["subtype"] = line.split(":", 1)[1].strip()
        elif low.startswith("explanation:"):
            result["explanation"] = line.split(":", 1)[1].strip()
    return result


def call_gemma(client, image_path):
    b64 = encode_image(image_path)
    ext = os.path.splitext(image_path)[1].lstrip(".").lower()
    mime = "jpeg" if ext in ("jpg", "jpeg") else ext

    response = client.chat.completions.create(
        model=MODEL_NAME,
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": PROMPT},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/{mime};base64,{b64}"},
                    },
                ],
            }
        ],
        max_tokens=300,
        temperature=0,
    )
    return response.choices[0].message.content


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true",
                         help="Re-genere la classification meme si deja presente.")
    parser.add_argument("--key", default="typographie",
                         help="Nom de la cle ajoutee au JSON (defaut: 'typographie').")
    args = parser.parse_args()

    client = OpenAI(
        api_key="sk-liHtE9YhCh7ABbTPNmw5ag",
        base_url="https://llm.aristote.education/v1",
    )

    json_files = sorted(f for f in os.listdir(OUTPUT_DIR) if f.endswith(".json"))
    if not json_files:
        print(f"Aucun JSON trouve dans {OUTPUT_DIR}/")
        return

    for json_name in json_files:
        json_path = os.path.join(OUTPUT_DIR, json_name)
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        if args.key in data and not args.force:
            print(f"[skip] {json_name} (deja annote)")
            continue

        base_name = os.path.splitext(json_name)[0]
        image_path = find_image_for(base_name)
        if image_path is None:
            print(f"[warn] Image introuvable pour {json_name}, ignore.")
            continue

        try:
            raw_answer = call_gemma(client, image_path)
            data[args.key] = parse_response(raw_answer)
        except Exception as e:
            print(f"[error] {json_name}: {e}")
            continue

        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)

        print(f"[ok]   {json_name} -> {data[args.key]['category']} / {data[args.key]['subtype']}")


if __name__ == "__main__":
    main()