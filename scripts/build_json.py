#!/usr/bin/env python3
"""Génère docs/cartes.json à partir de data/cartes.csv.

Le JSON ne contient que ce dont la page a besoin pour jouer :
l'ID YouTube et le temps de départ. Aucun titre, pour ne rien
dévoiler à quelqu'un qui ouvrirait le fichier.

Usage : python3 scripts/build_json.py
"""
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CSV = ROOT / "data" / "cartes.csv"
OUT = ROOT / "docs" / "cartes.json"


def main():
    cartes = {}
    manquants = []
    with CSV.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            num = row["id"].strip()
            if num in cartes:
                sys.exit(f"ID en double : {num}")
            vid = (row.get("youtube_id") or "").strip()
            if not vid:
                manquants.append(num)
                continue
            debut = (row.get("debut_s") or "").strip()
            cartes[num] = {"v": vid, "s": int(float(debut)) if debut else 0}

    OUT.write_text(json.dumps(cartes, separators=(",", ":"), sort_keys=True), encoding="utf-8")
    print(f"{len(cartes)} cartes écrites dans {OUT.relative_to(ROOT)}")
    if manquants:
        apercu = ", ".join(manquants[:10]) + (" ..." if len(manquants) > 10 else "")
        print(f"{len(manquants)} cartes sans youtube_id : {apercu}")


if __name__ == "__main__":
    main()
