# Vinyline

<img src="docs/logo.svg" alt="" width="96">

Jeu de frise chronologique en musique : on écoute un extrait (film, série, jeu vidéo ou chanson) et on le place dans sa frise selon son année. Premier à 10 cartes.

## Jouer

```bash
python3 game/server.py
```

Ouvre http://localhost:8765/host sur l'ordi (même Wi-Fi que les joueurs, VPN coupé). Les joueurs scannent le QR code affiché.

## Trouver les vidéos des nouvelles cartes

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -U yt-dlp
python scripts/find_youtube.py
```

## Relire et corriger les cartes

```bash
python3 -m http.server 8000
```

Ouvre http://localhost:8000/tools/review.html, exporte `review.csv`, puis :

```bash
python3 scripts/apply_review.py ~/Downloads/review.csv
```

## Cartes imprimées (optionnel)

```bash
python3 scripts/build_json.py
python3 scripts/make_cards.py --de 1 --a 500
```
