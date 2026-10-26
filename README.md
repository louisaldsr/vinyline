<p align="center">
  <img src="docs/logo.svg" alt="Logo Vinyline" width="160">
</p>

<h1 align="center">Vinyline</h1>

<p align="center">
  <b>Jeu de frise chronologique en musique</b><br>
  On écoute un extrait (film, série, jeu vidéo ou chanson) et on le place dans sa frise selon son année.<br>
  Premier à 10 cartes.
</p>

---

## Jouer

Double-clique sur **Vinyline.app** (ou son icône dans le Dock) : le serveur démarre et la page admin s'ouvre.
Les joueurs scannent le QR code affiché (même Wi-Fi, VPN coupé). Bouton « Éteindre » en haut de l'admin pour arrêter,
sinon le serveur s'arrête seul après 30 minutes sans personne.

Sans l'app :

```bash
python3 game/server.py
```

puis http://localhost:8765/host

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
