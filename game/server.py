#!/usr/bin/env python3
"""Vinyline, version numérique : serveur de partie en local.

L'ordi lance le serveur, joue la musique et sert d'admin.
Chaque joueur rejoint depuis son téléphone (même Wi-Fi) et joue sur sa frise.

    python3 game/server.py              # port 8765 par défaut
    python3 game/server.py --port 9000

Aucune dépendance : uniquement la bibliothèque standard de Python.
Les actions admin ne sont acceptées que depuis l'ordi lui-même (localhost).
"""
import argparse
import csv
import json
import queue
import re
import unicodedata
import random
import secrets
import socket
import subprocess
import sys
import threading
import time
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parent.parent
CSV_PATH = ROOT / "data" / "cartes.csv"
STATIC = Path(__file__).resolve().parent / "static"
REPORTS_PATH = ROOT / "data" / "signalements.csv"
REPORT_FIELDS = ["date", "id", "oeuvre", "morceau", "raison", "note", "position_s", "youtube_id", "debut_s"]

COLORS = ["#e8b44a", "#5fb3e8", "#e86f5f", "#7bc47f", "#b48ae8", "#e88ac4",
          "#4fd1c5", "#f0a35e", "#9aa6b2", "#d4d45a"]


CATEGORIES = ["Manga/Anime", "Dessins animés", "Films", "Disney/Pixar", "Jeux vidéo", "Séries TV", "Musique"]


def decade_of(year):
    d = year // 10 * 10
    return f"{d % 100:02d}s" if d < 2000 else f"{d}s"


def load_cards():
    cards = []
    with CSV_PATH.open(newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            vid = (r.get("youtube_id") or "").strip()
            year = (r.get("annee") or "").strip()
            if not vid or not year.isdigit():
                continue
            debut = (r.get("debut_s") or "").strip()
            tags = [t.strip() for t in (r.get("tags") or "").split(";") if t.strip()]
            category = next((t for t in tags if t in CATEGORIES), tags[0] if tags else "")
            cards.append({
                "category": category,
                "styles": [t for t in tags if t != category],
                "decade": decade_of(int(year)),
                "id": r["id"],
                "year": int(year),
                "title": r["oeuvre"],
                "type": r["type"],
                "song": r["morceau"],
                "artist": r["artiste"],
                "video": vid,
                "start": int(float(debut)) if debut else 0,
                "key": song_key(r["morceau"] or r["oeuvre"], r["artiste"]),
            })
    return cards


def song_key(title, artist):
    """Clé morceau + interprète, pour repérer une chanson présente en film ET en musique."""
    s = unicodedata.normalize("NFKD", f"{title}|{artist}".lower())
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    return re.sub(r"[^a-z0-9|]", "", re.sub(r"\(.*?\)", "", s))


def public_card(c):
    return {k: c[k] for k in ("id", "year", "title", "type", "song", "artist", "category")}


def slot_ok(timeline, slot, year):
    """Vrai si la carte de cette année est bien placée à cet emplacement de la frise."""
    left = timeline[slot - 1]["year"] if slot > 0 else None
    right = timeline[slot]["year"] if slot < len(timeline) else None
    return (left is None or left <= year) and (right is None or year <= right)


class Game:
    def __init__(self, cards):
        self.lock = threading.RLock()
        self.all_cards = cards
        self.clients = []  # (queue, role, pid)
        self.settings = {"target": 10, "start_tokens": 2, "max_tokens": 5, "challenge_seconds": 10}
        # Tags choisis pour la partie : tout est décoché au départ
        self.filters = {"categories": [], "decades": [], "styles": []}
        self.players = []
        self.timer = None
        self.deadline = None
        self.reported = self.load_reported()
        self.reset()

    # ---------- Signalements (musiques à corriger plus tard) ----------

    @staticmethod
    def load_reported():
        if not REPORTS_PATH.exists():
            return set()
        with REPORTS_PATH.open(newline="", encoding="utf-8") as f:
            return {r["id"] for r in csv.DictReader(f)}

    def report(self, reason, note, position):
        c = self.current
        if not c:
            raise ValueError("Aucune musique à signaler")
        new = not REPORTS_PATH.exists()
        with REPORTS_PATH.open("a", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=REPORT_FIELDS)
            if new:
                w.writeheader()
            w.writerow({
                "date": datetime.now().strftime("%Y-%m-%d %H:%M"), "id": c["id"], "oeuvre": c["title"],
                "morceau": c["song"], "raison": reason or "", "note": note or "",
                "position_s": int(position) if position is not None else "", "youtube_id": c["video"], "debut_s": c["start"],
            })
        self.reported.add(c["id"])
        print(f"Signalement : {c['id']} {c['title']} / {c['song']} ({reason}{', ' + note if note else ''})")

    # ---------- Cycle de partie ----------

    def reset(self, keep_players=True):
        self.cancel_timer()
        self.phase = "lobby"
        self.deck = []
        self.turn = 0
        self.current = None
        self.placement = None
        self.challenges = []
        self.result = None
        self.winner = None
        self.same_player = False  # après un changement de musique, le même joueur rejoue
        self.card_no = 0
        self.message = ""
        self.play_seq = 0  # incrémenté à chaque nouvelle musique, pour le lecteur de l'ordi
        if keep_players:
            for p in self.players:
                p["timeline"] = []
                p["tokens"] = 0

    def player(self, pid):
        return next((p for p in self.players if p["id"] == pid), None)

    def active(self):
        if not self.players:
            return None
        return self.players[self.turn % len(self.players)]

    def pool(self):
        """Cartes qui correspondent aux tags choisis par l'admin."""
        f = self.filters
        out = []
        for c in self.all_cards:
            if c["category"] not in f["categories"]:
                continue
            if c["category"] == "Musique":
                if f["decades"] and c["decade"] not in f["decades"]:
                    continue
                if f["styles"] and not set(c["styles"]) & set(f["styles"]):
                    continue
            out.append(c)
        # Une chanson à la fois en film et en musique (Eye of the Tiger…) : on garde la carte film
        film_keys = {c["key"] for c in out if c["category"] != "Musique"}
        return [c for c in out if c["category"] != "Musique" or c["key"] not in film_keys]

    def tag_info(self):
        cats = {k: 0 for k in CATEGORIES}
        decades, styles = {}, {}
        for c in self.all_cards:
            cats[c["category"]] = cats.get(c["category"], 0) + 1
            if c["category"] == "Musique":
                decades[c["decade"]] = decades.get(c["decade"], 0) + 1
                for st in c["styles"]:
                    styles[st] = styles.get(st, 0) + 1
        order = lambda d: int(d[:-1]) + (1900 if len(d) == 3 else 0)
        return {
            "categories": [[k, v] for k, v in cats.items() if k],
            "decades": [[d, decades.get(d, 0)] for d in sorted(set(decades) | {"60s", "70s", "80s", "90s", "2000s", "2010s", "2020s"}, key=order)],
            "styles": sorted(([k, v] for k, v in styles.items()), key=lambda x: x[0].lower()),
        }

    def draw(self):
        if not self.deck:
            used = {c["id"] for p in self.players for c in p["timeline"]}
            self.deck = [c for c in self.pool() if c["id"] not in used]
            random.shuffle(self.deck)
        if not self.deck:
            return None
        return self.deck.pop()

    def start(self):
        if not self.players:
            raise ValueError("Aucun joueur")
        pool = self.pool()
        if len(pool) < len(self.players) + 1:
            raise ValueError("Sélectionne au moins un thème avec assez de cartes")
        self.reset()
        self.deck = list(pool)
        random.shuffle(self.deck)
        random.shuffle(self.players)
        for p in self.players:
            p["tokens"] = self.settings["start_tokens"]
            first = self.draw()
            p["timeline"] = [first] if first else []
        self.turn = 0
        self.new_card("C'est parti !")

    def new_card(self, message=""):
        self.cancel_timer()
        self.current = self.draw()
        if not self.current:
            self.phase = "over"
            self.message = "Plus de cartes disponibles."
            return
        self.card_no += 1
        self.play_seq += 1
        self.placement = None
        self.challenges = []
        self.result = None
        self.same_player = False
        self.phase = "placing"
        self.message = message

    def next_turn(self):
        if self.phase in ("over", "lobby"):
            raise ValueError("Pas de partie en cours")
        if not self.same_player:
            self.turn = (self.turn + 1) % len(self.players)
        self.new_card()

    def next_player(self):
        """Joueur qui jouera au prochain tour (le même s'il vient de changer de musique)."""
        if not self.players:
            return None
        return self.active() if self.same_player else self.players[(self.turn + 1) % len(self.players)]

    def player_next(self, pid):
        """Le joueur qui vient de jouer ou le suivant lance le tour suivant depuis son téléphone."""
        if self.phase != "reveal":
            raise ValueError("Le tour n'est pas terminé")
        a, n = self.active(), self.next_player()
        if pid not in {a["id"] if a else None, n["id"] if n else None}:
            raise ValueError("Seuls le joueur du tour et le suivant peuvent continuer")
        self.next_turn()

    # ---------- Actions joueur ----------

    def place(self, pid, slot):
        a = self.active()
        if self.phase != "placing" or not a or a["id"] != pid:
            raise ValueError("Ce n'est pas ton tour de placer")
        if not (0 <= slot <= len(a["timeline"])):
            raise ValueError("Emplacement invalide")
        self.placement = slot

    def confirm(self, pid):
        a = self.active()
        if self.phase != "placing" or not a or a["id"] != pid:
            raise ValueError("Ce n'est pas ton tour")
        if self.placement is None:
            raise ValueError("Choisis d'abord un emplacement")
        self.phase = "challenge"
        if not self.can_anyone_challenge():
            self.reveal()  # personne ne peut contester : inutile d'attendre
            return
        secs = self.settings.get("challenge_seconds", 10)
        if secs > 0:
            self.deadline = time.time() + secs
            card_no = self.card_no
            self.timer = threading.Timer(secs, self._expire, args=(card_no,))
            self.timer.daemon = True
            self.timer.start()

    # ---------- Chrono de contestation ----------

    def cancel_timer(self):
        if getattr(self, "timer", None):
            self.timer.cancel()
        self.timer = None
        self.deadline = None

    def _expire(self, card_no):
        with self.lock:
            if self.phase != "challenge" or self.card_no != card_no:
                return
            self.reveal()
        self.broadcast()

    def can_anyone_challenge(self):
        a = self.active()
        if not a:
            return False
        taken = {self.placement} | {c["slot"] for c in self.challenges}
        if len(taken) >= len(a["timeline"]) + 1:
            return False
        done = {c["pid"] for c in self.challenges}
        return any(p["id"] != a["id"] and p["tokens"] > 0 and p["id"] not in done for p in self.players)

    def challenge(self, pid, slot):
        a = self.active()
        p = self.player(pid)
        if self.phase != "challenge" or not a or not p:
            raise ValueError("Pas de contestation possible maintenant")
        if p["id"] == a["id"]:
            raise ValueError("Tu ne peux pas contester ton propre placement")
        if p["tokens"] < 1:
            raise ValueError("Tu n'as plus de jeton")
        if any(c["pid"] == pid for c in self.challenges):
            raise ValueError("Tu as déjà contesté")
        if not (0 <= slot <= len(a["timeline"])):
            raise ValueError("Emplacement invalide")
        if slot == self.placement or any(c["slot"] == slot for c in self.challenges):
            raise ValueError("Emplacement déjà pris")
        p["tokens"] -= 1
        self.challenges.append({"pid": pid, "slot": slot, "t": time.time()})
        if not self.can_anyone_challenge():
            self.reveal()  # tout le monde a joué son jeton : on révèle sans attendre la fin du chrono

    # ---------- Actions admin ----------

    def reveal(self):
        if self.phase not in ("placing", "challenge"):
            raise ValueError("Rien à révéler")
        self.cancel_timer()
        a = self.active()
        y = self.current["year"]
        tl = a["timeline"]
        correct = [s for s in range(len(tl) + 1) if slot_ok(tl, s, y)]
        winner, how = None, None
        if self.placement is not None and slot_ok(tl, self.placement, y):
            winner, how = a, "active"
        else:
            for c in sorted(self.challenges, key=lambda c: c["t"]):
                if slot_ok(tl, c["slot"], y):
                    winner, how = self.player(c["pid"]), "challenge"
                    break
        if winner:
            wt = winner["timeline"]
            pos = next((i for i in range(len(wt) + 1) if slot_ok(wt, i, y)), len(wt))
            wt.insert(pos, self.current)
        self.result = {
            "winner": winner["id"] if winner else None,
            "how": how,
            "correct": correct,
            "placed": self.placement,
        }
        self.phase = "reveal"
        if winner and len(winner["timeline"]) >= self.settings["target"]:
            self.winner = winner["id"]
            self.phase = "over"

    def tokens(self, pid, delta):
        p = self.player(pid)
        if not p:
            raise ValueError("Joueur inconnu")
        p["tokens"] = max(0, min(self.settings["max_tokens"], p["tokens"] + delta))

    def refund_challenges(self):
        if self.phase == "challenge":
            for c in self.challenges:
                p = self.player(c["pid"])
                if p:
                    p["tokens"] += 1
        self.challenges = []

    def swap_with_token(self, pid):
        """Le joueur actif dépense un jeton pour changer de musique (avant de valider)."""
        a = self.active()
        if self.phase != "placing" or not a or a["id"] != pid:
            raise ValueError("Tu ne peux changer de musique qu'à ton tour, avant de valider")
        if a["tokens"] < 1:
            raise ValueError("Il te faut un jeton pour changer de musique")
        a["tokens"] -= 1
        # On révèle d'abord la carte abandonnée, puis le même joueur rejoue avec une nouvelle musique
        tl, y = a["timeline"], self.current["year"]
        self.result = {"winner": None, "how": "swap", "by": a["id"],
                       "correct": [s for s in range(len(tl) + 1) if slot_ok(tl, s, y)], "placed": None}
        self.placement = None
        self.phase = "reveal"
        self.same_player = True
        self.message = f"{a['name']} a changé de musique avec un jeton."

    def skip_card(self, reason):
        if self.phase not in ("placing", "challenge"):
            raise ValueError("Pas de musique en cours")
        self.refund_challenges()
        self.new_card(reason)

    def skip_turn(self):
        if self.phase in ("lobby", "over"):
            raise ValueError("Pas de tour en cours")
        self.refund_challenges()
        self.same_player = False
        self.next_turn()

    def kick(self, pid):
        p = self.player(pid)
        if not p:
            return
        a = self.active()
        was_active = bool(a and a["id"] == pid)
        idx = self.players.index(p)
        self.players.remove(p)
        self.challenges = [c for c in self.challenges if c["pid"] != pid]
        if not self.players:
            self.reset()
            return
        if self.phase == "lobby":
            return
        if was_active:
            self.turn = idx % len(self.players)
            if self.phase in ("placing", "challenge", "reveal"):
                self.refund_challenges()
                self.new_card(f"{p['name']} a quitté la partie.")
        else:
            self.turn = self.players.index(a)

    # ---------- Vues envoyées aux écrans ----------

    def view(self, role, pid=None):
        a = self.active()
        names = {p["id"]: p["name"] for p in self.players}
        v = {
            "phase": self.phase,
            "settings": self.settings,
            "cardNo": self.card_no,
            "deckLeft": len(self.deck),
            "message": self.message,
            "activeId": a["id"] if a and self.phase != "lobby" else None,
            "placement": self.placement,
            "challenges": [{"pid": c["pid"], "name": names.get(c["pid"], "?"), "slot": c["slot"]}
                           for c in self.challenges],
            "result": self.result,
            "winner": self.winner,
            "nextId": (self.next_player() or {}).get("id") if self.phase == "reveal" else None,
            "players": [{
                "id": p["id"], "name": p["name"], "color": p["color"], "tokens": p["tokens"],
                "online": p["online"] > 0,
                "timeline": [public_card(c) for c in p["timeline"]],
            } for p in self.players],
            "revealed": public_card(self.current) if self.current and self.phase in ("reveal", "over") and self.result else None,
            "deadline": int(self.deadline * 1000) if self.deadline and self.phase == "challenge" else None,
            # Indice visible pendant le tour : le thème, et si la chanson existait avant l'œuvre
            "clue": {"category": self.current["category"], "reprise": "Reprise" in self.current["styles"]}
                    if self.current and self.phase in ("placing", "challenge") else None,
            "now": int(time.time() * 1000),
        }
        if role == "host":
            v["host"] = {
                "video": self.current["video"] if self.current else None,
                "start": self.current["start"] if self.current else 0,
                "seq": self.play_seq,
                "totalCards": len(self.all_cards),
                "filters": self.filters,
                "tagInfo": self.tag_info(),
                "poolSize": len(self.pool()),
                "cardId": self.current["id"] if self.current else None,
                "reported": bool(self.current and self.current["id"] in self.reported),
            }
        else:
            v["me"] = pid
        return v

    def broadcast(self):
        with self.lock:
            for q, role, pid in list(self.clients):
                q.put(json.dumps(self.view(role, pid)))


def lan_ips():
    """Adresses IPv4 de l'ordi sur le réseau local, la plus probable en premier.

    Sur Mac, l'interface Wi-Fi (en0) passe avant tout le reste : un VPN ou une
    autre interface peut sinon être choisi, et les téléphones ne le joignent pas.
    """
    found = []
    if sys.platform == "darwin":
        for itf in ("en0", "en1", "en2"):
            try:
                out = subprocess.run(["ipconfig", "getifaddr", itf], capture_output=True,
                                     text=True, timeout=2).stdout.strip()
            except Exception:
                out = ""
            if out:
                found.append(out)
    for target in ("192.168.255.255", "10.255.255.255", "172.31.255.255"):
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect((target, 1))
            found.append(s.getsockname()[0])
        except OSError:
            pass
        finally:
            s.close()
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            found.append(info[4][0])
    except OSError:
        pass

    def rank(ip):
        if ip.startswith("192.168."):
            return 0
        if ip.startswith("10."):
            return 1
        if ip.startswith("172."):
            return 2
        return 3

    out = []
    for ip in found:
        if ip not in out and not ip.startswith(("127.", "169.254.", "0.")):
            out.append(ip)
    first = out[:1] if sys.platform == "darwin" and out else []
    rest = sorted(out[len(first):], key=rank)
    return (first + rest) or ["127.0.0.1"]


SEEN = set()


GAME = None


class QuietServer(ThreadingHTTPServer):
    """N'affiche pas les déconnexions normales (téléphone verrouillé, page rechargée…)."""
    daemon_threads = True

    def handle_error(self, request, client_address):
        import sys as _sys
        err = _sys.exc_info()[1]
        if isinstance(err, (ConnectionResetError, BrokenPipeError, ConnectionAbortedError, TimeoutError)):
            return
        super().handle_error(request, client_address)


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *args):
        pass

    def is_local(self):
        return self.client_address[0] in ("127.0.0.1", "::1", "::ffff:127.0.0.1")

    def send_json(self, code, obj):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def send_file(self, path, ctype):
        body = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        u = urlparse(self.path)
        ip = self.client_address[0]
        if not self.is_local() and ip not in SEEN:
            SEEN.add(ip)
            print(f"Nouvel appareil connecté : {ip}", flush=True)
        if u.path == "/":
            return self.send_file(STATIC / "play.html", "text/html; charset=utf-8")
        if u.path == "/host":
            if not self.is_local():
                return self.send_json(403, {"error": "La page admin ne s'ouvre que sur l'ordi qui lance le serveur."})
            return self.send_file(STATIC / "host.html", "text/html; charset=utf-8")
        if u.path in ("/logo.svg", "/favicon.ico"):
            return self.send_file(STATIC / "logo.svg", "image/svg+xml")
        if u.path == "/info":
            port = self.server.server_port
            urls = [f"http://{ip}:{port}/" for ip in lan_ips()]
            return self.send_json(200, {"url": urls[0], "others": urls[1:]})
        if u.path == "/events":
            return self.events(parse_qs(u.query))
        self.send_json(404, {"error": "not found"})

    def events(self, qs):
        role = "host" if qs.get("host") and self.is_local() else "player"
        pid = None
        if role == "player":
            pid = (qs.get("pid") or [None])[0]
            sec = (qs.get("secret") or [None])[0]
            p = GAME.player(pid)
            if not p or p["secret"] != sec:
                return self.send_json(401, {"error": "unknown player"})
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "keep-alive")
        self.end_headers()
        q = queue.Queue()
        with GAME.lock:
            GAME.clients.append((q, role, pid))
            if pid:
                GAME.player(pid)["online"] += 1
            q.put(json.dumps(GAME.view(role, pid)))
        if pid:
            GAME.broadcast()
        try:
            while True:
                try:
                    msg = q.get(timeout=15)
                    self.wfile.write(f"data: {msg}\n\n".encode())
                except queue.Empty:
                    self.wfile.write(b": ping\n\n")
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass
        finally:
            with GAME.lock:
                GAME.clients = [c for c in GAME.clients if c[0] is not q]
                p = GAME.player(pid) if pid else None
                if p:
                    p["online"] = max(0, p["online"] - 1)
            if pid:
                GAME.broadcast()

    def do_POST(self):
        u = urlparse(self.path)
        length = int(self.headers.get("Content-Length") or 0)
        try:
            data = json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError:
            return self.send_json(400, {"error": "JSON invalide"})
        try:
            with GAME.lock:
                if u.path == "/api/join":
                    out = self.join(data)
                elif u.path == "/api/action":
                    out = self.player_action(data)
                elif u.path == "/api/host":
                    if not self.is_local():
                        return self.send_json(403, {"error": "Réservé à l'ordi"})
                    out = self.host_action(data)
                else:
                    return self.send_json(404, {"error": "not found"})
        except ValueError as e:
            return self.send_json(400, {"error": str(e)})
        GAME.broadcast()
        self.send_json(200, out or {"ok": True})

    def join(self, data):
        name = str(data.get("name") or "").strip()[:20]
        if not name:
            raise ValueError("Choisis un pseudo")
        if any(p["name"].lower() == name.lower() for p in GAME.players):
            raise ValueError("Ce pseudo est déjà pris")
        if len(GAME.players) >= len(COLORS):
            raise ValueError("Partie complète")
        used = {p["color"] for p in GAME.players}
        p = {
            "id": secrets.token_hex(4),
            "secret": secrets.token_hex(12),
            "name": name,
            "color": next(c for c in COLORS if c not in used),
            "timeline": [],
            "tokens": 0,
            "online": 0,
        }
        GAME.players.append(p)
        if GAME.phase != "lobby":
            # Arrivée en cours de partie : une carte de départ et les jetons de départ
            p["tokens"] = GAME.settings["start_tokens"]
            first = GAME.draw()
            p["timeline"] = [first] if first else []
        return {"pid": p["id"], "secret": p["secret"]}

    def player_action(self, data):
        p = GAME.player(data.get("pid"))
        if not p or p["secret"] != data.get("secret"):
            raise ValueError("Joueur inconnu, rejoins la partie à nouveau")
        t = data.get("type")
        if t == "place":
            GAME.place(p["id"], int(data.get("slot")))
        elif t == "confirm":
            GAME.confirm(p["id"])
        elif t == "challenge":
            GAME.challenge(p["id"], int(data.get("slot")))
        elif t == "next":
            GAME.player_next(p["id"])
        elif t == "swap":
            GAME.swap_with_token(p["id"])
        elif t == "ping":
            pass
        elif t == "leave":
            GAME.kick(p["id"])
        else:
            raise ValueError("Action inconnue")

    def host_action(self, data):
        t = data.get("type")
        if t == "start":
            GAME.start()
        elif t == "reveal":
            GAME.reveal()
        elif t == "next":
            GAME.next_turn()
        elif t == "skip":
            # Musique injouable ou déjà connue : nouvelle carte pour le même joueur
            GAME.skip_card(data.get("reason") or "Nouvelle musique.")
        elif t == "report":
            pos = data.get("position")
            GAME.report(str(data.get("reason") or "")[:60], str(data.get("note") or "")[:300],
                        float(pos) if isinstance(pos, (int, float)) else None)
        elif t == "skipTurn":
            GAME.skip_turn()
        elif t == "tokens":
            GAME.tokens(data.get("pid"), int(data.get("delta", 0)))
        elif t == "kick":
            GAME.kick(data.get("pid"))
        elif t == "reset":
            GAME.reset()
        elif t == "settings":
            for k in ("target", "start_tokens", "max_tokens", "challenge_seconds"):
                if k in data:
                    GAME.settings[k] = max(0, min(50, int(data[k])))
        elif t == "filters":
            for k in ("categories", "decades", "styles"):
                if k in data and isinstance(data[k], list):
                    GAME.filters[k] = [str(x)[:40] for x in data[k]][:50]
        elif t == "reload":
            GAME.all_cards = load_cards()
            return {"cards": len(GAME.all_cards)}
        else:
            raise ValueError("Action inconnue")


def main():
    global GAME
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8765)
    args = ap.parse_args()

    cards = load_cards()
    if not cards:
        raise SystemExit("Aucune carte jouable (il faut un youtube_id et une année) dans data/cartes.csv")
    GAME = Game(cards)

    server = QuietServer(("0.0.0.0", args.port), Handler)
    ips = lan_ips()
    print(f"{len(cards)} cartes jouables chargées.")
    print(f"Admin (sur cet ordi) : http://localhost:{args.port}/host")
    print(f"Joueurs (même Wi-Fi) : http://{ips[0]}:{args.port}/")
    for ip in ips[1:]:
        print(f"  autre adresse possible : http://{ip}:{args.port}/")
    print("Si un téléphone se connecte, son adresse s'affiche ici.")
    print("Ctrl+C pour arrêter.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServeur arrêté.")


if __name__ == "__main__":
    main()
