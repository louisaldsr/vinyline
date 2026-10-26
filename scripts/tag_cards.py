#!/usr/bin/env python3
"""Ajoute la colonne `tags` à data/cartes.csv et remplit les tags manquants.

Une carte a une catégorie principale parmi :
    Manga/Anime | Dessins animés | Films | Disney/Pixar | Jeux vidéo | Séries TV | Musique
Les cartes « Musique » peuvent avoir en plus un ou plusieurs styles (Rap, Disco, Jazz…),
séparés par « ; ». Exemple : Musique;Disco. La décennie est calculée depuis l'année.

Les tags déjà remplis ne sont jamais modifiés : on peut relancer le script sans risque
après avoir ajouté des cartes.

    python3 scripts/tag_cards.py
"""
import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CSV = ROOT / "data" / "cartes.csv"

CATEGORIES = ["Manga/Anime", "Dessins animés", "Films", "Disney/Pixar", "Jeux vidéo", "Séries TV", "Musique"]

# Les films Ghibli/Miyazaki et Your Name sont rangés dans « Films » (voir guess)
GHIBLI = {
    "Castle in the Sky", "Howl's Moving Castle", "Kiki's Delivery Service", "My Neighbor Totoro",
    "Nausicaä of the Valley of the Wind", "Ponyo", "Porco Rosso", "Princess Mononoke", "Spirited Away",
    "The Castle of Cagliostro", "The Wind Rises", "The Boy and the Heron", "Your Name.",
}

ANIME = {
    # Films
    "Akira", "Demon Slayer: Mugen Train", "Ghost in the Shell", "Paprika", "Suzume", "Weathering with You",
    # Séries
    "Attack on Titan", "Bleach", "Cat's Eye", "Chainsaw Man", "City Hunter", "Code Geass", "Cowboy Bebop",
    "Cyberpunk: Edgerunners", "Dandadan", "Death Note", "Demon Slayer", "Detective Conan", "Digimon Adventure",
    "Doraemon", "Dragon Ball", "Dragon Ball GT", "Dragon Ball Z", "Fairy Tail", "Fist of the North Star",
    "Frieren: Beyond Journey's End", "Fullmetal Alchemist: Brotherhood", "Ghost in the Shell: Stand Alone Complex",
    "Haikyu!!", "Hunter x Hunter", "JoJo's Bizarre Adventure", "Jujutsu Kaisen", "Lupin III Part II", "Mashle",
    "Mob Psycho 100", "My Hero Academia", "Naruto", "Naruto Shippuden", "Neon Genesis Evangelion", "One Piece",
    "One Punch Man", "Oshi no Ko", "Pokémon", "Sailor Moon", "Saint Seiya", "Samurai Champloo", "Slam Dunk",
    "Solo Leveling", "Spy x Family", "Steins;Gate", "Sword Art Online", "Tokyo Ghoul", "UFO Robo Grendizer",
    "Vinland Saga",
}

DISNEY = {
    "Aladdin", "Beauty and the Beast", "Cars", "Cinderella", "Coco", "Encanto", "Finding Nemo", "Frozen",
    "Hercules", "Inside Out", "Lilo & Stitch", "Mary Poppins", "Moana", "Monsters, Inc.", "Mulan", "Pocahontas",
    "Ratatouille", "Robin Hood", "Snow White and the Seven Dwarfs", "Soul", "Tangled", "Tarzan", "The Aristocats",
    "The Incredibles", "The Jungle Book", "The Lion King", "The Little Mermaid", "The Nightmare Before Christmas",
    "Toy Story", "Up", "WALL-E", "Zootopia",
    # Séries animées Disney
    "DuckTales", "Chip 'n Dale: Rescue Rangers", "Kim Possible", "Phineas and Ferb", "Gravity Falls",
}

CARTOON = {
    # Films
    "Anastasia", "Despicable Me 2", "How to Train Your Dragon", "KPop Demon Hunters", "Kung Fu Panda",
    "Les Triplettes de Belleville", "Madagascar", "Shrek", "Spider-Man: Into the Spider-Verse", "The Lego Movie",
    "The Prince of Egypt", "The Wrong Trousers",
    # Séries
    "Adventure Time", "Animaniacs", "Arcane", "Avatar: The Last Airbender", "Bluey", "BoJack Horseman",
    "Code Lyoko", "Family Guy", "Futurama", "He-Man and the Masters of the Universe", "Inspector Gadget",
    "Over the Garden Wall", "Pinky and the Brain", "Rick and Morty", "Rugrats", "Scooby-Doo, Where Are You!",
    "South Park", "SpongeBob SquarePants", "Teenage Mutant Ninja Turtles", "The Bugs Bunny Show", "The Flintstones",
    "The Jetsons", "The Powerpuff Girls", "The Simpsons", "The Transformers", "ThunderCats",
    "X-Men: The Animated Series",
}

BY_TYPE = {"Movie": "Films", "TV Series": "Séries TV", "Game": "Jeux vidéo", "Music": "Musique"}


def guess(row):
    title = row["oeuvre"]
    if row["type"] == "Game":
        return "Jeux vidéo"
    if title in GHIBLI:
        return "Films"
    if title in ANIME:
        return "Manga/Anime"
    if title in DISNEY:
        return "Disney/Pixar"
    if title in CARTOON:
        return "Dessins animés"
    return BY_TYPE.get(row["type"], "")


def main():
    with CSV.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fields = list(reader.fieldnames)
        rows = list(reader)
    if "tags" not in fields:
        fields.insert(fields.index("type") + 1, "tags")
    filled = 0
    for r in rows:
        if not (r.get("tags") or "").strip():
            r["tags"] = guess(r)
            filled += 1
    with CSV.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
    counts = {}
    for r in rows:
        for t in r["tags"].split(";"):
            if t:
                counts[t] = counts.get(t, 0) + 1
    print(f"{filled} cartes taguées.")
    for k in CATEGORIES + sorted(set(counts) - set(CATEGORIES)):
        if k in counts:
            print(f"  {k} : {counts[k]}")


if __name__ == "__main__":
    main()
