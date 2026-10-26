#!/usr/bin/env python3
"""Remplit la colonne youtube_id de data/cartes.csv en cherchant sur YouTube.

Pour chaque carte sans youtube_id, cherche le morceau, écarte les vidéos
trop longues ou dont la lecture intégrée est interdite, et garde le premier
résultat valable. Un rapport (data/verif_youtube.csv) liste le titre de la
vidéo retenue pour vérifier rapidement les choix douteux.

À lancer sur ton Mac (pas besoin de clé API) :
    pip3 install yt-dlp
    python3 scripts/find_youtube.py              # toutes les cartes sans ID
    python3 scripts/find_youtube.py --only 0047  # une ou plusieurs cartes
    python3 scripts/find_youtube.py --check      # revérifie les IDs existants

Pour corriger un mauvais choix : colle le bon ID dans le CSV, à la main.
"""
import argparse
import csv
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

try:
    from yt_dlp import YoutubeDL
except ImportError:
    raise SystemExit("Installe yt-dlp d'abord : pip3 install yt-dlp")

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
REPORT = DATA / "verif_youtube.csv"
MAX_DURATION = 15 * 60  # au-delà, c'est sûrement une compilation
N_RESULTS = 6


def embeddable(video_id):
    """True si la vidéo existe et peut être lue dans un lecteur intégré."""
    url = "https://www.youtube.com/oembed?format=json&url=" + urllib.parse.quote(
        f"https://www.youtube.com/watch?v={video_id}", safe=""
    )
    try:
        with urllib.request.urlopen(url, timeout=10) as r:
            json.load(r)
            return True
    except urllib.error.HTTPError:
        return False  # 401 = intégration désactivée, 404 = vidéo supprimée
    except urllib.error.URLError:
        return None  # réseau : on ne conclut pas


def query_for(row):
    morceau = row["morceau"].replace("(VF)", "").strip()
    q = f'{morceau} {row["artiste"]}'
    if row["type"] == "Music":
        # Carte musique : le titre est dans « oeuvre », on cherche l'enregistrement original
        old = int(row["annee"] or 0) < 1955  # avant, peu de chaînes « officielles » : on ajoute l'année
        return f'{row["oeuvre"]} {row["artiste"]} ' + (row["annee"] if old else "official audio")
    if row["artiste"] == "Disney" or "(VF)" in row["morceau"]:
        q = f'{morceau} {row["oeuvre"]} version française'
    elif row["type"] == "Game":
        q = f'{row["oeuvre"]} {morceau} OST'
    elif row["morceau"].lower() in ("main title", "main theme", "main title theme"):
        q = f'{row["oeuvre"]} {morceau} {row["artiste"]}'
    return q


def search(ydl, query):
    info = ydl.extract_info(f"ytsearch{N_RESULTS}:{query}", download=False)
    return info.get("entries") or []


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", nargs="*", help="IDs de cartes à traiter")
    ap.add_argument("--check", action="store_true", help="revérifier les IDs déjà remplis")
    args = ap.parse_args()
    only = set(args.only or [])

    ydl = YoutubeDL({"quiet": True, "extract_flat": True, "skip_download": True})
    report = []

    for path in [DATA / "cartes.csv"]:
        with path.open(newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            fields = reader.fieldnames
            rows = list(reader)

        changed = False
        for row in rows:
            num = row["id"]
            if only and num not in only:
                continue
            vid = row["youtube_id"].strip()

            if vid and args.check:
                ok = embeddable(vid)
                if ok is False:
                    print(f"{num} : {vid} n'est plus lisible, à remplacer")
                    report.append([num, row["oeuvre"], row["morceau"], vid, "ID CASSÉ", ""])
                continue
            if vid and not only:
                continue

            query = query_for(row)
            chosen = None
            try:
                for e in search(ydl, query):
                    dur = e.get("duration") or 0
                    if dur and dur > MAX_DURATION:
                        continue
                    if embeddable(e["id"]):
                        chosen = e
                        break
            except Exception as exc:  # recherche ratée, on passe à la suivante
                print(f"{num} : erreur de recherche ({exc})")

            if chosen:
                row["youtube_id"] = chosen["id"]
                changed = True
                title = chosen.get("title", "")
                chan = chosen.get("channel") or chosen.get("uploader") or ""
                print(f"{num} : {title} [{chan}]")
                report.append([num, row["oeuvre"], row["morceau"], chosen["id"], title, chan])
            else:
                print(f"{num} : rien trouvé pour « {query} »")
                report.append([num, row["oeuvre"], row["morceau"], "", "RIEN TROUVÉ", query])
            time.sleep(0.5)

        if changed:
            with path.open("w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=fields)
                w.writeheader()
                w.writerows(rows)
            print(f"→ {path.name} mis à jour")

    with REPORT.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["num", "oeuvre", "morceau", "youtube_id", "titre_video", "chaine_ou_requete"])
        w.writerows(report)
    print(f"Rapport : {REPORT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
