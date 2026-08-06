"""
Downloads title pages from Gallica IIIF, using the "ark" and "page" fields
stored in each annotated JSON file.

Usage: python download_title_pages.py --json-dir ./manual --output-dir ./data/title_pages
"""

import json
import time
import argparse
import requests
from pathlib import Path

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; research-script/1.0)"}


def download_title_pages(json_dir: str, output_dir: str, size: str = "1000,", delay: float = 0.2):
    json_dir = Path(json_dir)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    json_files = list(json_dir.glob("*.json"))
    print(f"{len(json_files)} JSON files found in {json_dir}")

    downloaded, skipped, missing_info, failed = 0, 0, 0, 0

    for i, jf in enumerate(json_files, 1):
        try:
            with open(jf, "r", encoding="utf-8") as f:
                data = json.load(f)
        except json.JSONDecodeError:
            print(f"[{i}/{len(json_files)}] Invalid JSON: {jf.name}")
            failed += 1
            continue

        ark = data.get("ark")
        page_id = data.get("page")

        if not ark or not page_id:
            print(f"[{i}/{len(json_files)}] Missing ark or page: {jf.name}")
            missing_info += 1
            continue

        out_path = output_dir / f"{ark}_{page_id}.jpeg"
        if out_path.exists():
            skipped += 1
            continue

        img_url = f"https://gallica.bnf.fr/iiif/ark:/12148/{ark}/{page_id}/full/{size}/0/native.jpg"

        try:
            resp = requests.get(img_url, headers=HEADERS, timeout=15)
            if resp.status_code == 200 and resp.headers.get("Content-Type", "").startswith("image/"):
                with open(out_path, "wb") as f:
                    f.write(resp.content)
                print(f"[{i}/{len(json_files)}] OK: {ark} ({page_id})")
                downloaded += 1
            else:
                print(f"[{i}/{len(json_files)}] HTTP failure {resp.status_code}: {ark} ({page_id})")
                failed += 1
        except Exception as e:
            print(f"[{i}/{len(json_files)}] Error on {ark}: {e}")
            failed += 1

        time.sleep(delay)

    print(f"""
Done:
- Downloaded: {downloaded}
- Already present: {skipped}
- Missing info (ark/page): {missing_info}
- Failed: {failed}
""")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Download Gallica title pages from annotated JSON files.")
    parser.add_argument("--json-dir", default="./manual", help="Directory containing the JSON files")
    parser.add_argument("--output-dir", default="./data/title_pages", help="Output directory for images")
    parser.add_argument("--size", default="1000,", help="IIIF size (e.g. '1000,' or 'full')")
    parser.add_argument("--delay", type=float, default=0.2, help="Delay between requests (seconds)")
    args = parser.parse_args()

    download_title_pages(args.json_dir, args.output_dir, args.size, args.delay)