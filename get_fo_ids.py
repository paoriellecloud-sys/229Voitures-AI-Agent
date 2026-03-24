import json
import re
import requests

SITEMAPS = [
    "https://www.forceoccasion.ca/fr/sitemap.xml",
    "https://www.forceoccasion.ca/fr/sitemap_newinventory.xml",
    "https://www.forceoccasion.ca/fr/sitemap_demo.xml",
]
OUTPUT = "fo_vehicle_ids.json"

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept-Language": "fr-CA,fr;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

all_ids = set()

for sitemap_url in SITEMAPS:
    print(f"📄 Chargement de {sitemap_url} ...")
    try:
        resp = requests.get(sitemap_url, headers=headers, timeout=30)
        resp.raise_for_status()
        ids = re.findall(r'-id(\d+)', resp.text)
        unique = set(ids)
        print(f"   → {len(unique)} IDs trouvés")
        all_ids.update(unique)
    except Exception as e:
        print(f"   ⚠️ Erreur : {e}")

vehicle_ids = sorted(all_ids, key=lambda x: int(x))

with open(OUTPUT, "w", encoding="utf-8") as f:
    json.dump(vehicle_ids, f, ensure_ascii=False, indent=2)

print(f"\n✅ Total : {len(vehicle_ids)} IDs uniques → sauvegardés dans {OUTPUT}")
