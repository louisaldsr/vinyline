# Vinyline

<img src="docs/logo.svg" alt="" width="96">

Jeu de frise chronologique en musique : films, séries, jeux vidéo et morceaux de toutes les décennies.
On écoute un extrait, on le place dans sa frise selon son année.
Chaque carte a un QR code qui ouvre une page web jouant le morceau via YouTube, sans rien afficher (ni titre, ni miniature).

## Structure

```
data/cartes.csv          liste de toutes les cartes
docs/index.html          page de lecture, servie par GitHub Pages
docs/cartes.json         généré : ID de carte → ID YouTube + départ
scripts/find_youtube.py  remplit les IDs YouTube automatiquement
scripts/build_json.py    génère docs/cartes.json depuis les CSV
scripts/make_cards.py    génère le PDF des cartes à imprimer
fonts/                   polices DejaVu (licence libre) pour le PDF
```

Colonnes du CSV : `id, oeuvre, type, tags, morceau, artiste, annee, youtube_id, debut_s`.
`tags` : une catégorie parmi Manga/Anime, Dessins animés, Films, Disney/Pixar, Jeux vidéo, Séries TV, Musique.
Pour la musique, ajoute des styles séparés par « ; » (ex. `Musique;Disco`) ; la décennie vient de l'année.
Cartes musique (type `Music`) : le titre de la chanson va dans `oeuvre`, `morceau` reste vide, l'interprète dans `artiste`,
l'année est celle de l'enregistrement original. Si une chanson existe aussi en carte film (Eye of the Tiger…), une partie
qui mélange films et musique ne garde que la carte film.
`python3 scripts/tag_cards.py` remplit les tags vides des nouvelles cartes (type `Music` → Musique).
Tag `Reprise` (ex. `Films;Reprise`) : la chanson existait avant l'œuvre (Fight Club / Where Is My Mind?).
Pendant le tour, le jeu affiche alors « Chanson reprise : c'est l'année de l'œuvre qui compte ».
`id` sur 4 chiffres (0001, 0002...) : les nouvelles cartes continuent la numérotation. `oeuvre` en titre original (ou titre international anglais).
`debut_s` est le temps de départ en secondes (vide = début du morceau).

## Mise en place (une fois)

```bash
pip3 install yt-dlp reportlab
```

GitHub : Settings > Pages > Source « Deploy from a branch », branche `main`, dossier `/docs`.
La page est alors en ligne sur https://louisaldsr.github.io/vinyline/

## Cycle pour un nouveau lot de cartes

```bash
python3 scripts/find_youtube.py          # 1. cherche les vidéos (quelques minutes)
#                                          2. vérifie data/verif_youtube.csv, corrige les IDs douteux dans le CSV
python3 scripts/build_json.py            # 3. met à jour docs/cartes.json
git add -A && git commit -m "Cartes 0131-0260" && git push   # 4. publie
python3 scripts/make_cards.py --test     # 5. une planche test à imprimer
python3 scripts/make_cards.py --de 131 --a 260   # 6. le PDF du lot
```

Tester une carte sans l'imprimer : https://louisaldsr.github.io/vinyline/?c=0001

## Jouer en numérique (sans cartes imprimées)

```bash
python3 game/server.py
```

- Sur l'ordi, ouvre http://localhost:8765/host : la musique sort de l'ordi, c'est la page admin.
- Les joueurs scannent le QR code affiché (même Wi-Fi) et choisissent un pseudo.
- macOS peut demander d'autoriser les connexions entrantes pour Python : accepte.

Règles : chacun démarre avec une carte et 2 jetons. À son tour, le joueur place la musique dans sa frise
et valide. Les autres ont alors 10 secondes pour contester avec un jeton sur un autre emplacement (un
emplacement par joueur, premier arrivé premier servi). À la fin du chrono (ou dès que plus personne ne peut
contester), la carte est révélée : bien placé, la carte va au joueur ; sinon le
premier jeton bien placé la remporte ; sinon elle est perdue. Un jeton est dépensé même si la
contestation est fausse. À son tour, avant de valider, le joueur peut dépenser un jeton pour changer
de musique (bouton sur son téléphone, deux appuis pour confirmer) : la carte abandonnée est révélée,
puis il rejoue sur une nouvelle musique. Après chaque révélation, le joueur du tour ou le suivant lance
la suite depuis son téléphone (ou « Tour suivant » sur l'admin). L'admin donne ou retire des jetons à la main (+ / −). Premier à 10 cartes.
Réglages modifiables sur la page admin.

Seules les cartes avec un `youtube_id` sont jouées.

## Relire les cartes (page d'admin locale)

```bash
python3 -m http.server 8000      # depuis la racine du projet
```

Ouvre http://localhost:8000/tools/review.html : titre, année et vidéo visibles, navigation carte par carte
(flèches du clavier), remplacement de vidéo, temps de départ, signalement. Exporte `review.csv` puis :

```bash
python3 scripts/apply_review.py ~/Downloads/review.csv
python3 scripts/build_json.py
```

Pendant une partie, le bouton « Signaler ⚑ » de la page admin note la musique en cours dans
`data/signalements.csv` (raison, précision, moment de la vidéo). La page de relecture s'ouvre alors sur le filtre
« Reported in game » : cliquer un signalement saute au moment noté. `apply_review.py` retire ensuite des
signalements les cartes corrigées.

Cette page n'est pas publiée : elle lit `data/cartes.csv` en local, donc les réponses ne sont pas en ligne.

## Corriger une carte

Pas besoin de réimprimer : change `youtube_id` ou `debut_s` dans le CSV, relance `build_json.py`, push.
`find_youtube.py --check` repère les vidéos devenues illisibles.

## Impression

- Papier 250 à 350 g, recto/verso **bord long**.
- Le verso est inversé automatiquement pour tomber en face du recto.
- Imprime d'abord une planche test et vérifie l'alignement à contre-jour.
- Couper le long des traits gris dans les marges.
