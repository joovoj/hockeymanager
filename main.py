#!/usr/bin/env python3
"""
Hockeymanager — backend (Flask + Supabase REST API)
"""

import os, json, ssl, urllib.request as _req
from datetime import datetime, timezone
from functools import wraps
from flask import Flask, jsonify, request, send_from_directory
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__, static_folder=".", static_url_path="")

# ── Supabase-asetukset ────────────────────────────────────────────────────────
_SB_URL = ""
_SB_KEY = ""
_SB_CTX = None

def _init():
    global _SB_URL, _SB_KEY, _SB_CTX
    if _SB_URL:
        return
    _SB_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
    _SB_KEY = (
        os.environ.get("SUPABASE_SERVICE_KEY") or
        os.environ.get("SUPABASE_SECRET_KEY") or
        os.environ.get("SUPABASE_KEY", "")
    )
    if not _SB_URL or not _SB_KEY:
        raise RuntimeError("SUPABASE_URL tai SUPABASE_KEY puuttuu ympäristömuuttujista")
    _SB_CTX = ssl.create_default_context()

def _headers(token=None):
    _init()
    return {
        "apikey":        _SB_KEY,
        "Content-Type":  "application/json",
        "Authorization": f"Bearer {token or _SB_KEY}",
    }

def _http(method, url, body=None, extra_headers=None):
    """Tee HTTP-pyyntö Supabaseen. Palauttaa (status, data)."""
    _init()
    h = {**_headers(), **(extra_headers or {})}
    data = json.dumps(body).encode() if body is not None else None
    r = _req.Request(url, data=data, headers=h, method=method)
    try:
        with _req.urlopen(r, context=_SB_CTX, timeout=12) as resp:
            raw = resp.read().decode()
            return resp.status, (json.loads(raw) if raw else None)
    except _req.HTTPError as e:
        raw = e.read().decode()
        return e.code, (json.loads(raw) if raw else {})

# ── Supabase Auth ─────────────────────────────────────────────────────────────

def sb_auth_signup(email, password):
    return _http("POST", f"{_SB_URL}/auth/v1/signup",
                 body={"email": email, "password": password},
                 extra_headers={"apikey": _SB_KEY, "Authorization": f"Bearer {_SB_KEY}"})

def sb_auth_login(email, password):
    return _http("POST", f"{_SB_URL}/auth/v1/token?grant_type=password",
                 body={"email": email, "password": password},
                 extra_headers={"apikey": _SB_KEY, "Authorization": f"Bearer {_SB_KEY}"})

def sb_auth_user(token):
    return _http("GET", f"{_SB_URL}/auth/v1/user",
                 extra_headers={"apikey": _SB_KEY, "Authorization": f"Bearer {token}"})

# ── Supabase DB ───────────────────────────────────────────────────────────────

def sb_select(table, eq=None, single=False):
    _init()
    qs = "&".join(f"{k}=eq.{v}" for k, v in (eq or {}).items())
    url = f"{_SB_URL}/rest/v1/{table}?{qs}"
    if single:
        url += "&limit=1"
    h = _headers()
    if single:
        h["Accept"] = "application/vnd.pgrst.object+json"
    status, data = _http("GET", url, extra_headers=h)
    if single:
        return data if status == 200 else None
    return data if isinstance(data, list) else []

def sb_insert(table, row):
    _init()
    return _http("POST", f"{_SB_URL}/rest/v1/{table}",
                 body=row,
                 extra_headers={"Prefer": "return=representation"})

def sb_update(table, eq, data):
    _init()
    qs = "&".join(f"{k}=eq.{v}" for k, v in eq.items())
    return _http("PATCH", f"{_SB_URL}/rest/v1/{table}?{qs}",
                 body=data,
                 extra_headers={"Prefer": "return=representation"})

def sb_delete(table, eq):
    _init()
    qs = "&".join(f"{k}=eq.{v}" for k, v in eq.items())
    return _http("DELETE", f"{_SB_URL}/rest/v1/{table}?{qs}")

def sb_count(table, eq):
    _init()
    qs = "&".join(f"{k}=eq.{v}" for k, v in eq.items())
    status, data = _http("GET", f"{_SB_URL}/rest/v1/{table}?{qs}&select=id",
                         extra_headers={"Prefer": "count=exact"})
    return len(data) if isinstance(data, list) else 0

# ── Auth middleware ───────────────────────────────────────────────────────────

def require_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get("Authorization", "").replace("Bearer ", "").strip()
        if not token:
            return jsonify({"error": "Kirjautuminen vaaditaan"}), 401
        status, data = sb_auth_user(token)
        if status != 200 or not data or not data.get("id"):
            return jsonify({"error": "Virheellinen tai vanhentunut istunto — kirjaudu uudelleen"}), 401
        request.user_id    = data["id"]
        request.user_email = data.get("email", "")
        return f(*args, **kwargs)
    return decorated

# ── Vakiot ────────────────────────────────────────────────────────────────────

BUDGET = 1000
ROSTER_MAX = 6   # max pelaajia joukkueessa
ROSTER_LIMITS = {"H": 3, "P": 2, "MV": 1}

# Vaihdot sulkeutuvat ensimmäiseen peliin
DEADLINE = datetime(2026, 5, 15, 17, 20, 0, tzinfo=timezone.utc)

PLAYERS = [
{"id":1,  "name":"Connor McDavid",  "pos":"H",  "country":"CAN","price":300,"points":0},
{"id":2,  "name":"Auston Matthews", "pos":"H",  "country":"USA","price":290,"points":0},
{"id":3,  "name":"Mikko Rantanen",  "pos":"H",  "country":"FIN","price":285,"points":0},
{"id":4,  "name":"Nathan MacKinnon","pos":"H",  "country":"CAN","price":295,"points":0},
{"id":5,  "name":"David Pastrnak",  "pos":"H",  "country":"CZE","price":270,"points":0},
{"id":6,  "name":"Leon Draisaitl",  "pos":"H",  "country":"GER","price":280,"points":0},
{"id":7,  "name":"Aleksander Barkov",   "pos":"H",  "country":"FIN","price":265,"points":0},
{"id":8,  "name":"Kirill Kaprizov", "pos":"H",  "country":"RUS","price":260,"points":0},
{"id":9,  "name":"Brayden Point",   "pos":"H",  "country":"CAN","price":245,"points":0},
{"id":10, "name":"Nikita Kucherov", "pos":"H",  "country":"RUS","price":290,"points":0},
{"id":11, "name":"Elias Pettersson","pos":"H",  "country":"SWE","price":240,"points":0},
{"id":12, "name":"Filip Forsberg",  "pos":"H",  "country":"SWE","price":220,"points":0},
{"id":13, "name":"William Nylander","pos":"H",  "country":"SWE","price":215,"points":0},
{"id":14, "name":"Roope Hintz", "pos":"H",  "country":"FIN","price":200,"points":0},
{"id":15, "name":"Sebastian Aho",   "pos":"H",  "country":"FIN","price":210,"points":0},
{"id":16, "name":"Patrik Laine","pos":"H",  "country":"FIN","price":195,"points":0},
{"id":17, "name":"Jack Eichel", "pos":"H",  "country":"USA","price":210,"points":0},
{"id":18, "name":"Jason Robertson", "pos":"H",  "country":"USA","price":230,"points":0},
{"id":19, "name":"Brady Tkachuk",   "pos":"H",  "country":"CAN","price":225,"points":0},
{"id":20, "name":"Mark Scheifele",  "pos":"H",  "country":"CAN","price":200,"points":0},
{"id":21, "name":"Timo Meier",  "pos":"H",  "country":"SUI","price":200,"points":0},
{"id":22, "name":"Nico Hischier",   "pos":"H",  "country":"SUI","price":185,"points":0},
{"id":23, "name":"Kevin Fiala", "pos":"H",  "country":"SUI","price":180,"points":0},
{"id":24, "name":"Denis Malgin","pos":"H",  "country":"SUI","price":120,"points":0},
{"id":25, "name":"Nino Niederreiter",   "pos":"H",  "country":"SUI","price":160,"points":0},
{"id":26, "name":"Cole Caufield",   "pos":"H",  "country":"USA","price":175,"points":0},
{"id":27, "name":"Dylan Larkin","pos":"H",  "country":"USA","price":180,"points":0},
{"id":28, "name":"Artemi Panarin",  "pos":"H",  "country":"RUS","price":255,"points":0},
{"id":29, "name":"Jake Guentzel",   "pos":"H",  "country":"USA","price":195,"points":0},
{"id":30, "name":"Cale Makar",  "pos":"P",  "country":"CAN","price":280,"points":0},
{"id":31, "name":"Quinn Hughes","pos":"P",  "country":"USA","price":260,"points":0},
{"id":32, "name":"Roman Josi",  "pos":"P",  "country":"SUI","price":240,"points":0},
{"id":33, "name":"Miro Heiskanen",  "pos":"P",  "country":"FIN","price":235,"points":0},
{"id":34, "name":"Victor Hedman",   "pos":"P",  "country":"SWE","price":220,"points":0},
{"id":35, "name":"Adam Fox","pos":"P",  "country":"USA","price":215,"points":0},
{"id":36, "name":"Rasmus Dahlin",   "pos":"P",  "country":"SWE","price":210,"points":0},
{"id":37, "name":"Erik Karlsson",   "pos":"P",  "country":"SWE","price":200,"points":0},
{"id":38, "name":"Noah Dobson", "pos":"P",  "country":"CAN","price":180,"points":0},
{"id":39, "name":"John Carlson","pos":"P",  "country":"USA","price":175,"points":0},
{"id":40, "name":"Jonas Siegenthaler",  "pos":"P",  "country":"SUI","price":120,"points":0},
{"id":41, "name":"Mirco Mueller",   "pos":"P",  "country":"SUI","price":110,"points":0},
{"id":42, "name":"Juuse Saros", "pos":"MV", "country":"FIN","price":190,"points":0},
{"id":43, "name":"Connor Hellebuyck",   "pos":"MV", "country":"USA","price":215,"points":0},
{"id":44, "name":"Igor Shesterkin", "pos":"MV", "country":"RUS","price":210,"points":0},
{"id":45, "name":"Linus Ullmark",   "pos":"MV", "country":"SWE","price":185,"points":0},
{"id":46, "name":"Reto Berra",  "pos":"MV", "country":"SUI","price":110,"points":0},
{"id":47, "name":"Ukko-Pekka Luukkonen","pos":"MV", "country":"FIN","price":160,"points":0},
{"id":48, "name":"Ville Husso", "pos":"MV", "country":"FIN","price":140,"points":0},
{"id":49, "name":"Samuel Ersson",   "pos":"MV", "country":"SWE","price":150,"points":0},
{"id":50, "name":"Kevin Lankinen",  "pos":"MV", "country":"FIN","price":130,"points":0},{"id":51 , "name":"Drew Commesso ", "pos":"MV", "country":"USA","price":150,"points":0},
{"id":52 , "name":"Devin Cooley  ", "pos":"MV", "country":"USA","price":120,"points":0},
{"id":53 , "name":"Joseph Woll   ", "pos":"MV", "country":"USA","price":160,"points":0},
{"id":54 , "name":"Justin Faulk  ", "pos":"P", "country":"USA","price":200,"points":0},
{"id":55 , "name":"Ryan Lindgren ", "pos":"P", "country":"USA","price":180,"points":0},
{"id":56 , "name":"Mason Lohrei  ", "pos":"P", "country":"USA","price":190,"points":0},
{"id":57 , "name":"Will Borgen   ", "pos":"P", "country":"USA","price":160,"points":0},
{"id":58 , "name":"Connor Clifton", "pos":"P", "country":"USA","price":150,"points":0},
{"id":59 , "name":"Wyatt Kaiser  ", "pos":"P", "country":"USA","price":155,"points":0},
{"id":60 , "name":"Declan Carlile", "pos":"P", "country":"USA","price":130,"points":0},
{"id":61 , "name":"Ryan Ufko ", "pos":"P", "country":"USA","price":120,"points":0},
{"id":62 , "name":"Matthew Tkachuk   ", "pos":"H", "country":"USA","price":300,"points":0},
{"id":63 , "name":"James Hagens  ", "pos":"H", "country":"USA","price":250,"points":0},
{"id":64 , "name":"Ryan Leonard  ", "pos":"H", "country":"USA","price":240,"points":0},
{"id":65 , "name":"Matt Coronato ", "pos":"H", "country":"USA","price":230,"points":0},
{"id":66 , "name":"Isaac Howard  ", "pos":"H", "country":"USA","price":220,"points":0},
{"id":67 , "name":"Oliver Moore  ", "pos":"H", "country":"USA","price":210,"points":0},
{"id":68 , "name":"Tommy Novak   ", "pos":"H", "country":"USA","price":200,"points":0},
{"id":69 , "name":"Paul Cotter   ", "pos":"H", "country":"USA","price":190,"points":0},
{"id":70 , "name":"Max Sasson", "pos":"H", "country":"USA","price":170,"points":0},
{"id":71 , "name":"Sam Lafferty  ", "pos":"H", "country":"USA","price":160,"points":0},
{"id":72 , "name":"Danny Nelson  ", "pos":"H", "country":"USA","price":130,"points":0},
{"id":73 , "name":"Ryker Lee ", "pos":"H", "country":"USA","price":120,"points":0},
{"id":74 , "name":"Mathieu Olivier   ", "pos":"H", "country":"USA","price":130,"points":0},
{"id":75 , "name":"Max Plante", "pos":"H", "country":"USA","price":110,"points":0},
{"id":76 , "name":"Bernd Bruckler", "pos":"MV", "country":"AUT","price":130,"points":0},
{"id":77 , "name":"David Madlener", "pos":"MV", "country":"AUT","price":110,"points":0},
{"id":78 , "name":"Stefan Ulmer  ", "pos":"P", "country":"AUT","price":130,"points":0},
{"id":79 , "name":"Thomas Pock   ", "pos":"P", "country":"AUT","price":120,"points":0},
{"id":80 , "name":"Nico Brunner  ", "pos":"P", "country":"AUT","price":110,"points":0},
{"id":81 , "name":"Benjamin Baumgartner  ", "pos":"H", "country":"AUT","price":200,"points":0},
{"id":82 , "name":"Marco Kasper  ", "pos":"H", "country":"AUT","price":220,"points":0},
{"id":83 , "name":"Dominic Zwerger   ", "pos":"H", "country":"AUT","price":170,"points":0},
{"id":84 , "name":"Michael Raffl ", "pos":"H", "country":"AUT","price":160,"points":0},
{"id":85 , "name":"Manuel Ganahl ", "pos":"H", "country":"AUT","price":150,"points":0},
{"id":86 , "name":"Peter Schneider   ", "pos":"H", "country":"AUT","price":130,"points":0},
{"id":87 , "name":"Sam Montembeault  ", "pos":"MV", "country":"CAN","price":200,"points":0},
{"id":88 , "name":"Tristan Jarry ", "pos":"MV", "country":"CAN","price":180,"points":0},
{"id":89 , "name":"Josh Morrissey", "pos":"P", "country":"CAN","price":240,"points":0},
{"id":90 , "name":"Travis Sanheim", "pos":"P", "country":"CAN","price":200,"points":0},
{"id":91 , "name":"Shea Theodore ", "pos":"P", "country":"CAN","price":220,"points":0},
{"id":92 , "name":"Dylan Cozens  ", "pos":"H", "country":"CAN","price":230,"points":0},
{"id":93 , "name":"Nick Suzuki   ", "pos":"H", "country":"CAN","price":240,"points":0},
{"id":94 , "name":"Nico Daws ", "pos":"MV", "country":"CAN","price":150,"points":0},
{"id":95 , "name":"Jiri Patera   ", "pos":"MV", "country":"CZE","price":160,"points":0},
{"id":96 , "name":"Lukas Dostal  ", "pos":"MV", "country":"CZE","price":180,"points":0},
{"id":97 , "name":"Radko Gudas   ", "pos":"P", "country":"CZE","price":190,"points":0},
{"id":98 , "name":"Jakub Zboril  ", "pos":"P", "country":"CZE","price":160,"points":0},
{"id":99 , "name":"Jakub Vrana   ", "pos":"H", "country":"CZE","price":200,"points":0},
{"id":100, "name":"Tomas Hertl   ", "pos":"H", "country":"CZE","price":240,"points":0},
{"id":101, "name":"Ondrej Palat  ", "pos":"H", "country":"CZE","price":210,"points":0},
{"id":102, "name":"Martin Necas  ", "pos":"H", "country":"CZE","price":250,"points":0},
{"id":103, "name":"Sebastian Dahm", "pos":"MV", "country":"DEN","price":150,"points":0},
{"id":104, "name":"Mikkel Honore ", "pos":"MV", "country":"DEN","price":120,"points":0},
{"id":105, "name":"Oliver Bjorkstrand", "pos":"H", "country":"DEN","price":240,"points":0},
{"id":106, "name":"Nikolaj Ehlers", "pos":"H", "country":"DEN","price":250,"points":0},
{"id":107, "name":"Lars Eller", "pos":"H", "country":"DEN","price":180,"points":0},
{"id":108, "name":"Markus Lauridsen  ", "pos":"P", "country":"DEN","price":160,"points":0},
{"id":109, "name":"Stefan Lassen ", "pos":"P", "country":"DEN","price":140,"points":0},
{"id":110, "name":"Jesper Jensen ", "pos":"H", "country":"DEN","price":150,"points":0},
{"id":111, "name":"Kaapo Kakko   ", "pos":"H", "country":"FIN","price":240,"points":0},
{"id":112, "name":"Mikael Granlund   ", "pos":"H", "country":"FIN","price":210,"points":0},
{"id":113, "name":"Joel Armia", "pos":"H", "country":"FIN","price":180,"points":0},
{"id":114, "name":"Olli Maatta   ", "pos":"P", "country":"FIN","price":180,"points":0},
{"id":115, "name":"Esa Lindell   ", "pos":"P", "country":"FIN","price":200,"points":0},
{"id":116, "name":"Henri Jokiharju   ", "pos":"P", "country":"FIN","price":190,"points":0},
{"id":117, "name":"Philipp Grubauer  ", "pos":"MV", "country":"GER","price":190,"points":0},
{"id":118, "name":"Thomas Greiss ", "pos":"MV", "country":"GER","price":160,"points":0},
{"id":119, "name":"Moritz Seider ", "pos":"P", "country":"GER","price":260,"points":0},
{"id":120, "name":"Nico Sturm", "pos":"H", "country":"GER","price":180,"points":0},
{"id":121, "name":"Tim Stutzle   ", "pos":"H", "country":"GER","price":270,"points":0},
{"id":122, "name":"JJ Peterka", "pos":"H", "country":"GER","price":240,"points":0},
{"id":123, "name":"Ben Bowns ", "pos":"MV", "country":"GBR","price":130,"points":0},
{"id":124, "name":"Jackson Whistle   ", "pos":"MV", "country":"GBR","price":110,"points":0},
{"id":125, "name":"David Phillips", "pos":"P", "country":"GBR","price":130,"points":0},
{"id":126, "name":"Mark Richardson   ", "pos":"P", "country":"GBR","price":120,"points":0},
{"id":127, "name":"Robert Dowd   ", "pos":"H", "country":"GBR","price":150,"points":0},
{"id":128, "name":"Jonathan Phillips ", "pos":"H", "country":"GBR","price":140,"points":0},
{"id":129, "name":"Colin Shields ", "pos":"H", "country":"GBR","price":130,"points":0},
{"id":130, "name":"Adam Vay  ", "pos":"MV", "country":"HUN","price":130,"points":0},
{"id":131, "name":"Bence Stipsicz", "pos":"MV", "country":"HUN","price":110,"points":0},
{"id":132, "name":"Adam Jaros", "pos":"P", "country":"HUN","price":150,"points":0},
{"id":133, "name":"Tamas Vas ", "pos":"P", "country":"HUN","price":130,"points":0},
{"id":134, "name":"Tamas Erdely  ", "pos":"H", "country":"HUN","price":140,"points":0},
{"id":135, "name":"Daniel Fekete ", "pos":"H", "country":"HUN","price":130,"points":0},
{"id":136, "name":"Justin Fazio  ", "pos":"MV", "country":"ITA","price":140,"points":0},
{"id":137, "name":"Andreas Bernard   ", "pos":"MV", "country":"ITA","price":130,"points":0},
{"id":138, "name":"Stefano Marchetti ", "pos":"P", "country":"ITA","price":130,"points":0},
{"id":139, "name":"Alex Trivellato   ", "pos":"P", "country":"ITA","price":120,"points":0},
{"id":140, "name":"Daniel Mantenuto  ", "pos":"H", "country":"ITA","price":150,"points":0},
{"id":141, "name":"Luca Zanatta  ", "pos":"H", "country":"ITA","price":140,"points":0},
{"id":142, "name":"Anthony Bardaro   ", "pos":"H", "country":"ITA","price":130,"points":0},
{"id":143, "name":"Elvis Merzlikins  ", "pos":"MV", "country":"LAT","price":190,"points":0},
{"id":144, "name":"Ervins Mustukovs  ", "pos":"MV", "country":"LAT","price":140,"points":0},
{"id":145, "name":"Kristians Rubins  ", "pos":"P", "country":"LAT","price":160,"points":0},
{"id":146, "name":"Sandis Vilmanis   ", "pos":"P", "country":"LAT","price":140,"points":0},
{"id":147, "name":"Rodrigo Abols ", "pos":"H", "country":"LAT","price":170,"points":0},
{"id":148, "name":"Rihards Bukarts   ", "pos":"H", "country":"LAT","price":160,"points":0},
{"id":149, "name":"Zemgus Girgensons ", "pos":"H", "country":"LAT","price":190,"points":0},
{"id":150, "name":"Rolands Kenins", "pos":"H", "country":"LAT","price":150,"points":0},
{"id":151, "name":"Henrik Haukeland  ", "pos":"MV", "country":"NOR","price":160,"points":0},
{"id":152, "name":"Lars Volden   ", "pos":"MV", "country":"NOR","price":120,"points":0},
{"id":153, "name":"Jonas Holos   ", "pos":"P", "country":"NOR","price":150,"points":0},
{"id":154, "name":"Andreas Martinsen ", "pos":"H", "country":"NOR","price":160,"points":0},
{"id":155, "name":"Patrick Thoresen  ", "pos":"H", "country":"NOR","price":170,"points":0},
{"id":156, "name":"Mathis Olimb  ", "pos":"H", "country":"NOR","price":160,"points":0},
{"id":157, "name":"Mats Zuccarello   ", "pos":"H", "country":"NOR","price":250,"points":0},
{"id":158, "name":"Patrik Rybar  ", "pos":"MV", "country":"SVK","price":170,"points":0},
{"id":159, "name":"Samuel Hlavaj ", "pos":"MV", "country":"SVK","price":150,"points":0},
{"id":160, "name":"Martin Gernat ", "pos":"P", "country":"SVK","price":170,"points":0},
{"id":161, "name":"Christos Sarris   ", "pos":"P", "country":"SVK","price":140,"points":0},
{"id":162, "name":"Tomas Tatar   ", "pos":"H", "country":"SVK","price":220,"points":0},
{"id":163, "name":"Pavol Regenda ", "pos":"H", "country":"SVK","price":200,"points":0},
{"id":164, "name":"Robert Lantosi", "pos":"H", "country":"SVK","price":170,"points":0},
{"id":165, "name":"Libor Hudacek ", "pos":"H", "country":"SVK","price":180,"points":0},
{"id":166, "name":"Gasper Kroselj", "pos":"MV", "country":"SVN","price":160,"points":0},
{"id":167, "name":"Luka Gracnar  ", "pos":"MV", "country":"SVN","price":130,"points":0},
{"id":168, "name":"Ziga Pavlin   ", "pos":"P", "country":"SVN","price":140,"points":0},
{"id":169, "name":"Bostjan Golicic   ", "pos":"P", "country":"SVN","price":130,"points":0},
{"id":170, "name":"Anze Kopitar  ", "pos":"H", "country":"SVN","price":280,"points":0},
{"id":171, "name":"Robert Sabolic", "pos":"H", "country":"SVN","price":180,"points":0},
{"id":172, "name":"Rok Ticar ", "pos":"H", "country":"SVN","price":160,"points":0},
{"id":173, "name":"Jan Drozg ", "pos":"H", "country":"SVN","price":170,"points":0},
{"id":174, "name":"Jacob Markstrom   ", "pos":"MV", "country":"SWE","price":200,"points":0},
{"id":175, "name":"Filip Gustavsson  ", "pos":"MV", "country":"SWE","price":190,"points":0},
{"id":176, "name":"Gustav Forsling   ", "pos":"P", "country":"SWE","price":220,"points":0},
{"id":177, "name":"Erik Brannstrom   ", "pos":"P", "country":"SWE","price":180,"points":0},
{"id":178, "name":"Linus Sandin  ", "pos":"H", "country":"SWE","price":190,"points":0},
{"id":179, "name":"Joel Eriksson Ek  ", "pos":"H", "country":"SWE","price":210,"points":0},
{"id":180, "name":"Rickard Rakell", "pos":"H", "country":"SWE","price":200,"points":0},
{"id":181, "name":"Akira Schmid  ", "pos":"MV", "country":"SUI","price":170,"points":0},
{"id":182, "name":"Yannick Weber ", "pos":"P", "country":"SUI","price":160,"points":0},
{"id":183, "name":"Janis Moser   ", "pos":"P", "country":"SUI","price":200,"points":0},
{"id":184, "name":"Sven Andrighetto  ", "pos":"H", "country":"SUI","price":190,"points":0},
{"id":185, "name":"Damien Riat   ", "pos":"H", "country":"SUI","price":180,"points":0},
{"id":186, "name":"Lian Bichsel  ", "pos":"H", "country":"SUI","price":170,"points":0},

]


# ── Pisteytys ─────────────────────────────────────────────────────────────────
# H/P: Maali=4p, Syöttö=2p, +/-=1p/-1p
# MV:  Voitto=4p, OT-tappio=2p, Nollapeli=4p, Torjuntaprosentti>90%=2p

# ── Static tiedostot ──────────────────────────────────────────────────────────

@app.route("/")
def index():
    return send_from_directory(".", "etusivu.html")

@app.route("/<path:filename>")
def static_files(filename):
    return send_from_directory(".", filename)

# ══════════════════════════════════════════════════════════════════════════════
#  AUTH ENDPOINTS
# ══════════════════════════════════════════════════════════════════════════════

@app.route("/api/auth/register", methods=["POST"])
def register():
    data     = request.get_json(force=True) or {}
    email    = data.get("email", "").strip().lower()
    password = data.get("password", "")
    username = data.get("username", "").strip()

    if not email or not password or not username:
        return jsonify({"error": "Täytä kaikki kentät"}), 400
    if len(password) < 6:
        return jsonify({"error": "Salasana liian lyhyt (min 6 merkkiä)"}), 400
    if len(username) < 2:
        return jsonify({"error": "Käyttäjänimi liian lyhyt (min 2 merkkiä)"}), 400

    status, resp = sb_auth_signup(email, password)
    if status not in (200, 201):
        raw = resp if isinstance(resp, dict) else {}
        err = (raw.get("msg") or raw.get("message") or
               raw.get("error_description") or raw.get("error") or
               "Rekisteröityminen epäonnistui")
        if "already" in str(err).lower():
            err = "Sähköposti on jo käytössä"
        elif "rate limit" in str(err).lower():
            err = "Liian monta yritystä – odota hetki"
        elif "invalid" in str(err).lower() and "email" in str(err).lower():
            err = "Virheellinen sähköpostiosoite"
        return jsonify({"error": str(err)}), 400

    uid = resp.get("id") or (resp.get("user") or {}).get("id")
    if uid:
        existing = sb_select("profiles", eq={"id": uid}, single=True)
        if not existing:
            sb_insert("profiles", {
                "id":             uid,
                "username":       username,
                "email":          email,
                "transfers_left": 17,
                "total_points":   0,
                "created_at":     datetime.now(timezone.utc).isoformat()
            })
        return jsonify({"message": "Tili luotu! Voit nyt kirjautua sisään."}), 201
    else:
        return jsonify({"message": "Tili luotu! Kirjaudu nyt sisään."}), 201


@app.route("/api/auth/login", methods=["POST"])
def login():
    data     = request.get_json(force=True) or {}
    email    = data.get("email", "").strip()
    password = data.get("password", "")

    if not email or not password:
        return jsonify({"error": "Täytä kaikki kentät"}), 400

    status, resp = sb_auth_login(email, password)
    if status != 200 or not resp.get("access_token"):
        err_msg = "Väärä sähköposti tai salasana"
        if isinstance(resp, dict):
            raw = resp.get("error_description") or resp.get("message") or resp.get("error") or ""
            if "confirm" in str(raw).lower() or "not confirmed" in str(raw).lower():
                err_msg = "Vahvista sähköpostiosoitteesi ennen kirjautumista"
        return jsonify({"error": err_msg}), 401

    uid            = resp["user"]["id"]
    uname_fallback = email.split("@")[0]
    profile        = sb_select("profiles", eq={"id": uid}, single=True)

    if not profile:
        # Luo profiili automaattisesti jos puuttuu
        sb_insert("profiles", {
            "id":             uid,
            "username":       uname_fallback,
            "email":          email,
            "transfers_left": 17,
            "total_points":   0,
            "created_at":     datetime.now(timezone.utc).isoformat()
        })
        profile = {"username": uname_fallback, "transfers_left": 17, "total_points": 0, "team_name": ""}

    return jsonify({
        "access_token": resp["access_token"],
        "user": {
            "id":             uid,
            "email":          resp["user"]["email"],
            "username":       profile.get("username") or uname_fallback,
            "transfers_left": profile.get("transfers_left", 17),
            "total_points":   profile.get("total_points", 0),
            "team_name":      profile.get("team_name") or "",
        }
    }), 200


@app.route("/api/auth/me", methods=["GET"])
@require_auth
def me():
    profile = sb_select("profiles", eq={"id": request.user_id}, single=True)
    if not profile:
        uname = request.user_email.split("@")[0]
        sb_insert("profiles", {
            "id":             request.user_id,
            "username":       uname,
            "email":          request.user_email,
            "transfers_left": 17,
            "total_points":   0,
            "created_at":     datetime.now(timezone.utc).isoformat()
        })
        profile = {"username": uname, "transfers_left": 17, "total_points": 0, "team_name": ""}
    return jsonify({
        "id":             request.user_id,
        "email":          request.user_email,
        "username":       profile.get("username", ""),
        "transfers_left": profile.get("transfers_left", 17),
        "total_points":   profile.get("total_points", 0),
        "team_name":      profile.get("team_name") or "",
    }), 200


# ══════════════════════════════════════════════════════════════════════════════
#  PLAYERS ENDPOINT
# ══════════════════════════════════════════════════════════════════════════════

@app.route("/api/players", methods=["GET"])
def get_players():
    country = request.args.get("country", "").upper()
    pos     = request.args.get("pos", "").upper()
    q       = request.args.get("q", "").lower()
    result  = PLAYERS
    if country:
        result = [p for p in result if p["country"] == country]
    if pos:
        result = [p for p in result if p["pos"] == pos]
    if q:
        result = [p for p in result if q in p["name"].lower()]
    return jsonify(result), 200


# ══════════════════════════════════════════════════════════════════════════════
#  TEAM ENDPOINTS
# ══════════════════════════════════════════════════════════════════════════════

@app.route("/api/team", methods=["GET"])
@require_auth
def get_team():
    rows    = sb_select("teams", eq={"user_id": request.user_id})
    profile = sb_select("profiles", eq={"id": request.user_id}, single=True)
    ids     = [int(r["player_id"]) for r in (rows or [])]
    players = [p for p in PLAYERS if p["id"] in ids]
    spent   = sum(p["price"] for p in players)
    return jsonify({
        "players":       players,
        "budget_left":   BUDGET - spent,
        "budget_total":  BUDGET,
        "team_name":     (profile or {}).get("team_name") or "",
        "confirmed":     (profile or {}).get("team_confirmed", False),
        "transfers_left": (profile or {}).get("transfers_left", 17),
    }), 200


@app.route("/api/team/add", methods=["POST"])
@require_auth
def team_add():
    data      = request.get_json(force=True) or {}
    player_id = data.get("player_id")
    if not player_id:
        return jsonify({"error": "player_id puuttuu"}), 400
    try:
        player_id = int(player_id)
    except (ValueError, TypeError):
        return jsonify({"error": "Virheellinen player_id"}), 400

    player = next((p for p in PLAYERS if p["id"] == player_id), None)
    if not player:
        return jsonify({"error": "Pelaajaa ei löydy"}), 404

    rows    = sb_select("teams", eq={"user_id": request.user_id})
    cur_ids = [int(r["player_id"]) for r in (rows or [])]
    cur_players = [p for p in PLAYERS if p["id"] in cur_ids]

    if player_id in cur_ids:
        return jsonify({"error": "Pelaaja on jo joukkueessa"}), 400
    if len(cur_ids) >= ROSTER_MAX:
        return jsonify({"error": f"Joukkue on täynnä (max {ROSTER_MAX} pelaajaa)"}), 400

    # Positiorajoitus
    pos_count = sum(1 for p in cur_players if p["pos"] == player["pos"])
    if pos_count >= ROSTER_LIMITS.get(player["pos"], 99):
        pos_names = {"H": "hyökkääjää", "P": "puolustajaa", "MV": "maalivahtia"}
        return jsonify({"error": f"Liian monta {pos_names.get(player['pos'], 'pelaajaa')} (max {ROSTER_LIMITS[player['pos']]})"}), 400

    # Budjettitarkistus
    spent = sum(p["price"] for p in cur_players)
    if spent + player["price"] > BUDGET:
        return jsonify({"error": f"Budjetti ylittyy (jäljellä {BUDGET - spent}M€)"}), 400

    sb_insert("teams", {"user_id": request.user_id, "player_id": player_id})
    new_spent = spent + player["price"]
    return jsonify({
        "message":     f"{player['name']} lisätty!",
        "budget_left": BUDGET - new_spent,
        "player":      player,
    }), 200


@app.route("/api/team/remove", methods=["POST"])
@require_auth
def team_remove():
    data      = request.get_json(force=True) or {}
    player_id = data.get("player_id")
    try:
        player_id = int(player_id)
    except (ValueError, TypeError):
        return jsonify({"error": "Virheellinen player_id"}), 400
    sb_delete("teams", {"user_id": request.user_id, "player_id": player_id})
    return jsonify({"message": "Pelaaja poistettu"}), 200


@app.route("/api/team/name", methods=["POST"])
@require_auth
def team_name():
    data = request.get_json(force=True) or {}
    name = data.get("team_name", "").strip()
    if not name:
        return jsonify({"error": "Anna joukkueelle nimi"}), 400
    if len(name) > 40:
        return jsonify({"error": "Nimi liian pitkä (max 40 merkkiä)"}), 400
    sb_update("profiles", {"id": request.user_id}, {"team_name": name})
    return jsonify({"message": "Joukkueen nimi tallennettu!", "team_name": name}), 200


@app.route("/api/team/confirm", methods=["POST"])
@require_auth
def team_confirm():
    rows = sb_select("teams", eq={"user_id": request.user_id})
    if not rows or len(rows) < 1:
        return jsonify({"error": "Lisää pelaajia ennen tallentamista"}), 400
    sb_update("profiles", {"id": request.user_id}, {"team_confirmed": True})
    return jsonify({"message": "Joukkue tallennettu!"}), 200


# ══════════════════════════════════════════════════════════════════════════════
#  LEAGUE ENDPOINTS
# ══════════════════════════════════════════════════════════════════════════════

@app.route("/api/leagues", methods=["GET"])
def get_leagues():
    type_f = request.args.get("type", "")
    q      = request.args.get("q", "").lower()
    rows   = sb_select("leagues") or []
    if type_f in ("public", "private"):
        rows = [l for l in rows if l.get("type") == type_f]
    if q:
        rows = [l for l in rows if q in l.get("name", "").lower()]
    for l in rows:
        l["member_count"] = sb_count("league_members", {"league_id": l["id"]})
        # Piilota join_code julkisessa listassa
        if l.get("type") == "private":
            l.pop("join_code", None)
    return jsonify(rows), 200


@app.route("/api/leagues", methods=["POST"])
@require_auth
def create_league():
    data        = request.get_json(force=True) or {}
    name        = data.get("name", "").strip()
    league_type = data.get("type", "public")
    max_members = data.get("max_members", 20)

    if not name:
        return jsonify({"error": "Anna liigalle nimi"}), 400
    if league_type not in ("public", "private"):
        return jsonify({"error": "Virheellinen liigan tyyppi"}), 400
    try:
        max_members = int(max_members)
        if not 2 <= max_members <= 500:
            raise ValueError
    except (ValueError, TypeError):
        return jsonify({"error": "Jäsenmäärä 2–500"}), 400

    join_code = None
    if league_type == "private":
        import secrets
        join_code = secrets.token_hex(4).upper()

    row = {
        "name":        name,
        "type":        league_type,
        "max_members": max_members,
        "created_by":  request.user_id,
        "created_at":  datetime.now(timezone.utc).isoformat(),
    }
    if join_code:
        row["join_code"] = join_code

    status, res = sb_insert("leagues", row)
    if status not in (200, 201):
        return jsonify({"error": "Liigan luonti epäonnistui"}), 500

    lid = res[0]["id"] if isinstance(res, list) and res else None
    if lid:
        sb_insert("league_members", {
            "league_id": lid,
            "user_id":   request.user_id,
            "joined_at": datetime.now(timezone.utc).isoformat()
        })

    resp = {"message": "Liiga luotu!", "league_id": lid}
    if join_code:
        resp["join_code"] = join_code
    return jsonify(resp), 201


@app.route("/api/leagues/<int:league_id>/join", methods=["POST"])
@require_auth
def join_league(league_id):
    data      = request.get_json(force=True) or {}
    join_code = data.get("join_code", "").strip().upper()

    league = sb_select("leagues", eq={"id": league_id}, single=True)
    if not league:
        return jsonify({"error": "Liigaa ei löydy"}), 404

    # Tarkista onko jo jäsen
    existing = sb_select("league_members",
                         eq={"league_id": league_id, "user_id": request.user_id},
                         single=True)
    if existing:
        return jsonify({"error": "Olet jo tässä liigassa"}), 400

    # Jäsenmäärätarkistus
    count = sb_count("league_members", {"league_id": league_id})
    if count >= league.get("max_members", 20):
        return jsonify({"error": "Liiga on täynnä"}), 400

    # Yksityinen liiga — tarkista koodi
    if league.get("type") == "private":
        if not join_code:
            return jsonify({"error": "Anna liittymiskoodi"}), 400
        if join_code != (league.get("join_code") or "").upper():
            return jsonify({"error": "Väärä liittymiskoodi"}), 403

    sb_insert("league_members", {
        "league_id": league_id,
        "user_id":   request.user_id,
        "joined_at": datetime.now(timezone.utc).isoformat()
    })
    return jsonify({"message": f"Liitytty liigaan {league['name']}!"}), 200


@app.route("/api/leagues/<int:league_id>", methods=["GET"])
def get_league(league_id):
    league = sb_select("leagues", eq={"id": league_id}, single=True)
    if not league:
        return jsonify({"error": "Liigaa ei löydy"}), 404
    members_rows = sb_select("league_members", eq={"league_id": league_id}) or []
    members = []
    for m in members_rows:
        profile = sb_select("profiles", eq={"id": m["user_id"]}, single=True)
        if profile:
            members.append({
                "user_id":      m["user_id"],
                "username":     profile.get("username", ""),
                "total_points": profile.get("total_points", 0),
                "team_name":    profile.get("team_name") or "",
            })
    members.sort(key=lambda x: x["total_points"], reverse=True)
    league.pop("join_code", None)
    league["members"] = members
    league["member_count"] = len(members)
    return jsonify(league), 200


# ══════════════════════════════════════════════════════════════════════════════
#  SCHEDULE / DEADLINE ENDPOINT
# ══════════════════════════════════════════════════════════════════════════════

@app.route("/api/deadline", methods=["GET"])
def get_deadline():
    now = datetime.now(timezone.utc)
    diff = (DEADLINE - now).total_seconds()
    return jsonify({
        "deadline":   DEADLINE.isoformat(),
        "seconds_left": max(0, int(diff)),
        "is_open":    diff > 0,
    }), 200


# ══════════════════════════════════════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════════════════════════════════════


# ══════════════════════════════════════════════════════════════════════════════
#  STANDINGS ENDPOINT
# ══════════════════════════════════════════════════════════════════════════════

@app.route("/api/standings", methods=["GET"])
def get_standings():
    """Palauttaa kaikki käyttäjät pisteiden mukaan järjestettynä."""
    rows = sb_select("profiles") or []
    rows.sort(key=lambda x: x.get("total_points", 0), reverse=True)
    result = [{
        "user_id":      r.get("id"),
        "username":     r.get("username",""),
        "team_name":    r.get("team_name") or "",
        "total_points": r.get("total_points", 0),
    } for r in rows]
    return jsonify(result), 200


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
