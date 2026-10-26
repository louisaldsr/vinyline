#!/usr/bin/env python3
"""Applique au CSV les changements exportés par tools/review.html.

    python3 scripts/apply_review.py ~/Downloads/review.csv

- delete     : supprime la carte (les autres IDs ne bougent pas)
- youtube_id : remplace la vidéo de la carte
- debut_s    : remplace le temps de départ
- oeuvre, morceau, artiste, annee, tags : remplacent les textes de la carte
- flag/note  : seulement affichés à la fin, pour traitement manuel
Les cartes corrigées (ou supprimées) sont retirées de data/signalements.csv.
"""
import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CSV = ROOT / "data" / "cartes.csv"
REPORTS = ROOT / "data" / "signalements.csv"


def main():
    if len(sys.argv) != 2:
        sys.exit("Usage : python3 scripts/apply_review.py review.csv")
    review = {r["id"]: r for r in csv.DictReader(open(sys.argv[1], encoding="utf-8"))}

    with CSV.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fields = reader.fieldnames
        rows = list(reader)

    applied, todo, deleted, kept = 0, [], [], []
    fixed = set()
    for row in rows:
        r = review.pop(row["id"], None)
        if not r:
            kept.append(row)
            continue
        if r.get("delete"):
            deleted.append(f'{row["id"]}  {row["oeuvre"]} / {row["morceau"]}')
            fixed.add(row["id"])
            continue
        before = applied
        kept.append(row)
        if r.get("youtube_id"):
            row["youtube_id"] = r["youtube_id"]
            row["debut_s"] = ""
            applied += 1
        if r.get("debut_s"):
            row["debut_s"] = r["debut_s"]
            applied += 1
        for k in ("oeuvre", "morceau", "artiste", "annee", "tags"):
            if r.get(k) and k in row:
                row[k] = r[k]
                applied += 1
        if applied > before:
            fixed.add(row["id"])
        if r.get("flag") or r.get("note"):
            todo.append(f'{row["id"]}  {row["oeuvre"]} / {row["morceau"]}  {"[FLAG] " if r.get("flag") else ""}{r.get("note", "")}')

    with CSV.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(kept)

    print(f"{applied} changements appliqués à {CSV.relative_to(ROOT)}")
    if REPORTS.exists() and fixed:
        with REPORTS.open(newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            rfields, reps = reader.fieldnames, list(reader)
        left = [r for r in reps if r["id"] not in fixed]
        with REPORTS.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=rfields)
            w.writeheader()
            w.writerows(left)
        print(f"{len(reps) - len(left)} signalements traités retirés, {len(left)} restants dans {REPORTS.relative_to(ROOT)}")
    if deleted:
        print(f"{len(deleted)} cartes supprimées :")
        print("\n".join("  " + d for d in deleted))
    if review:
        print(f"IDs inconnus ignorés : {', '.join(sorted(review))}")
    if todo:
        print("\nÀ traiter à la main :")
        print("\n".join(todo))
    print("\nEnsuite : python3 scripts/build_json.py")


if __name__ == "__main__":
    main()
