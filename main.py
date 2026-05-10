from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from functools import wraps
from dotenv import load_dotenv
import os, json, ssl as _ssl, urllib.parse as _urlparse
import urllib.request as _urllib_req
import urllib.error as _urllib_err
from datetime import datetime

load_dotenv()
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-key")

_ALLOWED = [o.strip() for o in (os.environ.get("ALLOWED_ORIGINS") or "*").split(",") if o.strip()]
if _ALLOWED == ["*"]:
    CORS(app, resources={r"/api/*": {"origins": "*"}}, supports_credentials=False)
else:
    CORS(app, resources={r"/api/*": {"origins": _ALLOWED}}, supports_credentials=False)

_SB_URL = None
_SB_KEY = None
_SB_AUTH_KEY = None
_SB_CTX = None
_POINTS_LOADED = False


def _init():
    global _SB_URL, _SB_KEY, _SB_AUTH_KEY, _SB_CTX
    if _SB_URL:
        return
    _SB_URL = (os.environ.get("SUPABASE_URL") or "").rstrip("/")
    _SB_KEY = (
        os.environ.get("SUPABASE_SERVICE_KEY")
        or os.environ.get("SUPABASE_SECRET_KEY")
        or os.environ.get("SUPABASE_KEY")
        or ""
    )
    _SB_AUTH_KEY = (
        os.environ.get("SUPABASE_PUBLISHABLE_KEY")
        or os.environ.get("SUPABASE_ANON_KEY")
        or _SB_KEY
    )
    if not _SB_URL or not _SB_KEY:
        raise RuntimeError("SUPABASE_URL tai SUPABASE_SERVICE_KEY puuttuu ympäristömuuttujista")
    _SB_CTX = _ssl.create_default_context()


def _val(v):
    if isinstance(v, bool):
        return "true" if v else "false"
    if v is None:
        return "null"
    return str(v)


def _headers(token=None, api_key=None, extra=None):
    _init()
    k = api_key or _SB_KEY
    h = {
        "apikey": k,
        "Authorization": f"Bearer {token or k}",
        "Content-Type": "application/json",
    }
    if extra:
        h.update(extra)
    return h


def _query(eq=None, cols='*', order=None, limit=None):
    parts = [f"select={_urlparse.quote(cols, safe='*_,')}"]
    if eq:
        for k, v in eq.items():
            parts.append(f"{_urlparse.quote(str(k))}=eq.{_urlparse.quote(_val(v))}")
    if order:
        parts.append(f"order={_urlparse.quote(str(order))}")
    if limit is not None:
        parts.append(f"limit={int(limit)}")
    return '&'.join(parts)


def _req(method, url, body=None, token=None, api_key=None, headers=None, timeout=20):
    _init()
    data = json.dumps(body).encode('utf-8') if body is not None else None
    req = _urllib_req.Request(url, data=data, headers=_headers(token=token, api_key=api_key, extra=headers), method=method)
    try:
        with _urllib_req.urlopen(req, context=_SB_CTX, timeout=timeout) as resp:
            raw = resp.read().decode('utf-8')
            return resp.status, json.loads(raw) if raw else None
    except _urllib_err.HTTPError as e:
        raw = e.read().decode('utf-8')
        try:
            payload = json.loads(raw) if raw else {}
        except Exception:
            payload = {'message': raw}
        return e.code, payload
    except Exception as e:
        return 500, {'message': str(e)}


def sb_select(table, eq=None, cols='*', single=False, order=None, limit=None):
    qs = _query(eq=eq, cols=cols, order=order, limit=(1 if single and limit is None else limit))
    status, data = _req('GET', f"{_SB_URL}/rest/v1/{table}?{qs}")
    if status >= 400:
        raise RuntimeError((data or {}).get('message') or (data or {}).get('error_description') or f"Supabase virhe {status}")
    if single:
        return data[0] if isinstance(data, list) and data else None
    return data if isinstance(data, list) else []


def sb_insert(table, row):
    status, data = _req('POST', f"{_SB_URL}/rest/v1/{table}", body=row, headers={'Prefer':'return=representation'})
    if status >= 400:
        raise RuntimeError((data or {}).get('message') or (data or {}).get('error_description') or f"Supabase virhe {status}")
    return data


def sb_update(table, eq, updates):
    qs = _query(eq=eq)
    status, data = _req('PATCH', f"{_SB_URL}/rest/v1/{table}?{qs}", body=updates, headers={'Prefer':'return=representation'})
    if status >= 400:
        raise RuntimeError((data or {}).get('message') or (data or {}).get('error_description') or f"Supabase virhe {status}")
    return data


def sb_delete(table, eq):
    qs = _query(eq=eq)
    status, data = _req('DELETE', f"{_SB_URL}/rest/v1/{table}?{qs}")
    if status >= 400:
        raise RuntimeError((data or {}).get('message') or (data or {}).get('error_description') or f"Supabase virhe {status}")
    return True


def auth_signup(email, password):
    return _req('POST', f"{_SB_URL}/auth/v1/signup", body={'email': email, 'password': password}, api_key=_SB_AUTH_KEY, headers={'apikey': _SB_AUTH_KEY, 'Authorization': f'Bearer {_SB_AUTH_KEY}'})


def auth_login(email, password):
    return _req('POST', f"{_SB_URL}/auth/v1/token?grant_type=password", body={'email': email, 'password': password}, api_key=_SB_AUTH_KEY, headers={'apikey': _SB_AUTH_KEY, 'Authorization': f'Bearer {_SB_AUTH_KEY}'})


def auth_get_user(token):
    return _req('GET', f"{_SB_URL}/auth/v1/user", token=token, api_key=_SB_AUTH_KEY, headers={'apikey': _SB_AUTH_KEY, 'Authorization': f'Bearer {token}'})


def first(row, *keys, default=None):
    if not isinstance(row, dict):
        return default
    for k in keys:
        if k in row and row.get(k) is not None:
            return row.get(k)
    return default


def try_many(fn):
    last = None
    for attempt in fn:
        try:
            return attempt()
        except Exception as e:
            last = e
    if last:
        raise last
    return None


BUDGET = 1000
ROSTER_LIMITS = {'H':3,'P':2,'MV':1}
PLAYERS = [
    {"id":1,  "name":"Connor McDavid",      "pos":"H",  "country":"CAN","price":300,"points":0},
    {"id":2,  "name":"Auston Matthews",     "pos":"H",  "country":"USA","price":290,"points":0},
    {"id":3,  "name":"Mikko Rantanen",      "pos":"H",  "country":"FIN","price":285,"points":0},
    {"id":4,  "name":"Nathan MacKinnon",    "pos":"H",  "country":"CAN","price":295,"points":0},
    {"id":5,  "name":"David Pastrnak",      "pos":"H",  "country":"CZE","price":270,"points":0},
    {"id":6,  "name":"Leon Draisaitl",      "pos":"H",  "country":"GER","price":280,"points":0},
    {"id":7,  "name":"Aleksander Barkov",   "pos":"H",  "country":"FIN","price":265,"points":0},
    {"id":8,  "name":"Kirill Kaprizov",     "pos":"H",  "country":"RUS","price":260,"points":0},
    {"id":9,  "name":"Brayden Point",       "pos":"H",  "country":"CAN","price":245,"points":0},
    {"id":10, "name":"Nikita Kucherov",     "pos":"H",  "country":"RUS","price":290,"points":0},
    {"id":11, "name":"Elias Pettersson",    "pos":"H",  "country":"SWE","price":240,"points":0},
    {"id":12, "name":"Filip Forsberg",      "pos":"H",  "country":"SWE","price":220,"points":0},
    {"id":13, "name":"William Nylander",    "pos":"H",  "country":"SWE","price":215,"points":0},
    {"id":14, "name":"Roope Hintz",         "pos":"H",  "country":"FIN","price":200,"points":0},
    {"id":15, "name":"Sebastian Aho",       "pos":"H",  "country":"FIN","price":210,"points":0},
    {"id":16, "name":"Patrik Laine",        "pos":"H",  "country":"FIN","price":195,"points":0},
    {"id":17, "name":"Jack Eichel",         "pos":"H",  "country":"USA","price":210,"points":0},
    {"id":18, "name":"Jason Robertson",     "pos":"H",  "country":"USA","price":230,"points":0},
    {"id":19, "name":"Brady Tkachuk",       "pos":"H",  "country":"CAN","price":225,"points":0},
    {"id":20, "name":"Mark Scheifele",      "pos":"H",  "country":"CAN","price":200,"points":0},
    {"id":21, "name":"Timo Meier",          "pos":"H",  "country":"SUI","price":200,"points":0},
    {"id":22, "name":"Nico Hischier",       "pos":"H",  "country":"SUI","price":185,"points":0},
    {"id":23, "name":"Kevin Fiala",         "pos":"H",  "country":"SUI","price":180,"points":0},
    {"id":24, "name":"Denis Malgin",        "pos":"H",  "country":"SUI","price":120,"points":0},
    {"id":25, "name":"Nino Niederreiter",   "pos":"H",  "country":"SUI","price":160,"points":0},
    {"id":26, "name":"Cole Caufield",       "pos":"H",  "country":"USA","price":175,"points":0},
    {"id":27, "name":"Dylan Larkin",        "pos":"H",  "country":"USA","price":180,"points":0},
    {"id":28, "name":"Artemi Panarin",      "pos":"H",  "country":"RUS","price":255,"points":0},
    {"id":29, "name":"Jake Guentzel",       "pos":"H",  "country":"USA","price":195,"points":0},
    {"id":30, "name":"Cale Makar",          "pos":"P",  "country":"CAN","price":280,"points":0},
    {"id":31, "name":"Quinn Hughes",        "pos":"P",  "country":"USA","price":260,"points":0},
    {"id":32, "name":"Roman Josi",          "pos":"P",  "country":"SUI","price":240,"points":0},
    {"id":33, "name":"Miro Heiskanen",      "pos":"P",  "country":"FIN","price":235,"points":0},
    {"id":34, "name":"Victor Hedman",       "pos":"P",  "country":"SWE","price":220,"points":0},
    {"id":35, "name":"Adam Fox",            "pos":"P",  "country":"USA","price":215,"points":0},
    {"id":36, "name":"Rasmus Dahlin",       "pos":"P",  "country":"SWE","price":210,"points":0},
    {"id":37, "name":"Erik Karlsson",       "pos":"P",  "country":"SWE","price":200,"points":0},
    {"id":38, "name":"Noah Dobson",         "pos":"P",  "country":"CAN","price":180,"points":0},
    {"id":39, "name":"John Carlson",        "pos":"P",  "country":"USA","price":175,"points":0},
    {"id":40, "name":"Jonas Siegenthaler",  "pos":"P",  "country":"SUI","price":120,"points":0},
    {"id":41, "name":"Mirco Mueller",       "pos":"P",  "country":"SUI","price":110,"points":0},
    {"id":42, "name":"Juuse Saros",         "pos":"MV", "country":"FIN","price":190,"points":0},
    {"id":43, "name":"Connor Hellebuyck",   "pos":"MV", "country":"USA","price":215,"points":0},
    {"id":44, "name":"Igor Shesterkin",     "pos":"MV", "country":"RUS","price":210,"points":0},
    {"id":45, "name":"Linus Ullmark",       "pos":"MV", "country":"SWE","price":185,"points":0},
    {"id":46, "name":"Reto Berra",          "pos":"MV", "country":"SUI","price":110,"points":0},
    {"id":47, "name":"Ukko-Pekka Luukkonen","pos":"MV", "country":"FIN","price":160,"points":0},
    {"id":48, "name":"Ville Husso",         "pos":"MV", "country":"FIN","price":140,"points":0},
    {"id":49, "name":"Samuel Ersson",       "pos":"MV", "country":"SWE","price":150,"points":0},
    {"id":50, "name":"Kevin Lankinen",      "pos":"MV", "country":"FIN","price":130,"points":0},    {"id":51 , "name":"Drew Commesso         ", "pos":"MV", "country":"USA","price":150,"points":0},
    {"id":52 , "name":"Devin Cooley          ", "pos":"MV", "country":"USA","price":120,"points":0},
    {"id":53 , "name":"Joseph Woll           ", "pos":"MV", "country":"USA","price":160,"points":0},
    {"id":54 , "name":"Justin Faulk          ", "pos":"P", "country":"USA","price":200,"points":0},
    {"id":55 , "name":"Ryan Lindgren         ", "pos":"P", "country":"USA","price":180,"points":0},
    {"id":56 , "name":"Mason Lohrei          ", "pos":"P", "country":"USA","price":190,"points":0},
    {"id":57 , "name":"Will Borgen           ", "pos":"P", "country":"USA","price":160,"points":0},
    {"id":58 , "name":"Connor Clifton        ", "pos":"P", "country":"USA","price":150,"points":0},
    {"id":59 , "name":"Wyatt Kaiser          ", "pos":"P", "country":"USA","price":155,"points":0},
    {"id":60 , "name":"Declan Carlile        ", "pos":"P", "country":"USA","price":130,"points":0},
    {"id":61 , "name":"Ryan Ufko             ", "pos":"P", "country":"USA","price":120,"points":0},
    {"id":62 , "name":"Matthew Tkachuk       ", "pos":"H", "country":"USA","price":300,"points":0},
    {"id":63 , "name":"James Hagens          ", "pos":"H", "country":"USA","price":250,"points":0},
    {"id":64 , "name":"Ryan Leonard          ", "pos":"H", "country":"USA","price":240,"points":0},
    {"id":65 , "name":"Matt Coronato         ", "pos":"H", "country":"USA","price":230,"points":0},
    {"id":66 , "name":"Isaac Howard          ", "pos":"H", "country":"USA","price":220,"points":0},
    {"id":67 , "name":"Oliver Moore          ", "pos":"H", "country":"USA","price":210,"points":0},
    {"id":68 , "name":"Tommy Novak           ", "pos":"H", "country":"USA","price":200,"points":0},
    {"id":69 , "name":"Paul Cotter           ", "pos":"H", "country":"USA","price":190,"points":0},
    {"id":70 , "name":"Max Sasson            ", "pos":"H", "country":"USA","price":170,"points":0},
    {"id":71 , "name":"Sam Lafferty          ", "pos":"H", "country":"USA","price":160,"points":0},
    {"id":72 , "name":"Danny Nelson          ", "pos":"H", "country":"USA","price":130,"points":0},
    {"id":73 , "name":"Ryker Lee             ", "pos":"H", "country":"USA","price":120,"points":0},
    {"id":74 , "name":"Mathieu Olivier       ", "pos":"H", "country":"USA","price":130,"points":0},
    {"id":75 , "name":"Max Plante            ", "pos":"H", "country":"USA","price":110,"points":0},
    {"id":76 , "name":"Bernd Bruckler        ", "pos":"MV", "country":"AUT","price":130,"points":0},
    {"id":77 , "name":"David Madlener        ", "pos":"MV", "country":"AUT","price":110,"points":0},
    {"id":78 , "name":"Stefan Ulmer          ", "pos":"P", "country":"AUT","price":130,"points":0},
    {"id":79 , "name":"Thomas Pock           ", "pos":"P", "country":"AUT","price":120,"points":0},
    {"id":80 , "name":"Nico Brunner          ", "pos":"P", "country":"AUT","price":110,"points":0},
    {"id":81 , "name":"Benjamin Baumgartner  ", "pos":"H", "country":"AUT","price":200,"points":0},
    {"id":82 , "name":"Marco Kasper          ", "pos":"H", "country":"AUT","price":220,"points":0},
    {"id":83 , "name":"Dominic Zwerger       ", "pos":"H", "country":"AUT","price":170,"points":0},
    {"id":84 , "name":"Michael Raffl         ", "pos":"H", "country":"AUT","price":160,"points":0},
    {"id":85 , "name":"Manuel Ganahl         ", "pos":"H", "country":"AUT","price":150,"points":0},
    {"id":86 , "name":"Peter Schneider       ", "pos":"H", "country":"AUT","price":130,"points":0},
    {"id":87 , "name":"Sam Montembeault      ", "pos":"MV", "country":"CAN","price":200,"points":0},
    {"id":88 , "name":"Tristan Jarry         ", "pos":"MV", "country":"CAN","price":180,"points":0},
    {"id":89 , "name":"Josh Morrissey        ", "pos":"P", "country":"CAN","price":240,"points":0},
    {"id":90 , "name":"Travis Sanheim        ", "pos":"P", "country":"CAN","price":200,"points":0},
    {"id":91 , "name":"Shea Theodore         ", "pos":"P", "country":"CAN","price":220,"points":0},
    {"id":92 , "name":"Dylan Cozens          ", "pos":"H", "country":"CAN","price":230,"points":0},
    {"id":93 , "name":"Nick Suzuki           ", "pos":"H", "country":"CAN","price":240,"points":0},
    {"id":94 , "name":"Nico Daws             ", "pos":"MV", "country":"CAN","price":150,"points":0},
    {"id":95 , "name":"Jiri Patera           ", "pos":"MV", "country":"CZE","price":160,"points":0},
    {"id":96 , "name":"Lukas Dostal          ", "pos":"MV", "country":"CZE","price":180,"points":0},
    {"id":97 , "name":"Radko Gudas           ", "pos":"P", "country":"CZE","price":190,"points":0},
    {"id":98 , "name":"Jakub Zboril          ", "pos":"P", "country":"CZE","price":160,"points":0},
    {"id":99 , "name":"Jakub Vrana           ", "pos":"H", "country":"CZE","price":200,"points":0},
    {"id":100, "name":"Tomas Hertl           ", "pos":"H", "country":"CZE","price":240,"points":0},
    {"id":101, "name":"Ondrej Palat          ", "pos":"H", "country":"CZE","price":210,"points":0},
    {"id":102, "name":"Martin Necas          ", "pos":"H", "country":"CZE","price":250,"points":0},
    {"id":103, "name":"Sebastian Dahm        ", "pos":"MV", "country":"DEN","price":150,"points":0},
    {"id":104, "name":"Mikkel Honore         ", "pos":"MV", "country":"DEN","price":120,"points":0},
    {"id":105, "name":"Oliver Bjorkstrand    ", "pos":"H", "country":"DEN","price":240,"points":0},
    {"id":106, "name":"Nikolaj Ehlers        ", "pos":"H", "country":"DEN","price":250,"points":0},
    {"id":107, "name":"Lars Eller            ", "pos":"H", "country":"DEN","price":180,"points":0},
    {"id":108, "name":"Markus Lauridsen      ", "pos":"P", "country":"DEN","price":160,"points":0},
    {"id":109, "name":"Stefan Lassen         ", "pos":"P", "country":"DEN","price":140,"points":0},
    {"id":110, "name":"Jesper Jensen         ", "pos":"H", "country":"DEN","price":150,"points":0},
    {"id":111, "name":"Kaapo Kakko           ", "pos":"H", "country":"FIN","price":240,"points":0},
    {"id":112, "name":"Mikael Granlund       ", "pos":"H", "country":"FIN","price":210,"points":0},
    {"id":113, "name":"Joel Armia            ", "pos":"H", "country":"FIN","price":180,"points":0},
    {"id":114, "name":"Olli Maatta           ", "pos":"P", "country":"FIN","price":180,"points":0},
    {"id":115, "name":"Esa Lindell           ", "pos":"P", "country":"FIN","price":200,"points":0},
    {"id":116, "name":"Henri Jokiharju       ", "pos":"P", "country":"FIN","price":190,"points":0},
    {"id":117, "name":"Philipp Grubauer      ", "pos":"MV", "country":"GER","price":190,"points":0},
    {"id":118, "name":"Thomas Greiss         ", "pos":"MV", "country":"GER","price":160,"points":0},
    {"id":119, "name":"Moritz Seider         ", "pos":"P", "country":"GER","price":260,"points":0},
    {"id":120, "name":"Nico Sturm            ", "pos":"H", "country":"GER","price":180,"points":0},
    {"id":121, "name":"Tim Stutzle           ", "pos":"H", "country":"GER","price":270,"points":0},
    {"id":122, "name":"JJ Peterka            ", "pos":"H", "country":"GER","price":240,"points":0},
    {"id":123, "name":"Ben Bowns             ", "pos":"MV", "country":"GBR","price":130,"points":0},
    {"id":124, "name":"Jackson Whistle       ", "pos":"MV", "country":"GBR","price":110,"points":0},
    {"id":125, "name":"David Phillips        ", "pos":"P", "country":"GBR","price":130,"points":0},
    {"id":126, "name":"Mark Richardson       ", "pos":"P", "country":"GBR","price":120,"points":0},
    {"id":127, "name":"Robert Dowd           ", "pos":"H", "country":"GBR","price":150,"points":0},
    {"id":128, "name":"Jonathan Phillips     ", "pos":"H", "country":"GBR","price":140,"points":0},
    {"id":129, "name":"Colin Shields         ", "pos":"H", "country":"GBR","price":130,"points":0},
    {"id":130, "name":"Adam Vay              ", "pos":"MV", "country":"HUN","price":130,"points":0},
    {"id":131, "name":"Bence Stipsicz        ", "pos":"MV", "country":"HUN","price":110,"points":0},
    {"id":132, "name":"Adam Jaros            ", "pos":"P", "country":"HUN","price":150,"points":0},
    {"id":133, "name":"Tamas Vas             ", "pos":"P", "country":"HUN","price":130,"points":0},
    {"id":134, "name":"Tamas Erdely          ", "pos":"H", "country":"HUN","price":140,"points":0},
    {"id":135, "name":"Daniel Fekete         ", "pos":"H", "country":"HUN","price":130,"points":0},
    {"id":136, "name":"Justin Fazio          ", "pos":"MV", "country":"ITA","price":140,"points":0},
    {"id":137, "name":"Andreas Bernard       ", "pos":"MV", "country":"ITA","price":130,"points":0},
    {"id":138, "name":"Stefano Marchetti     ", "pos":"P", "country":"ITA","price":130,"points":0},
    {"id":139, "name":"Alex Trivellato       ", "pos":"P", "country":"ITA","price":120,"points":0},
    {"id":140, "name":"Daniel Mantenuto      ", "pos":"H", "country":"ITA","price":150,"points":0},
    {"id":141, "name":"Luca Zanatta          ", "pos":"H", "country":"ITA","price":140,"points":0},
    {"id":142, "name":"Anthony Bardaro       ", "pos":"H", "country":"ITA","price":130,"points":0},
    {"id":143, "name":"Elvis Merzlikins      ", "pos":"MV", "country":"LAT","price":190,"points":0},
    {"id":144, "name":"Ervins Mustukovs      ", "pos":"MV", "country":"LAT","price":140,"points":0},
    {"id":145, "name":"Kristians Rubins      ", "pos":"P", "country":"LAT","price":160,"points":0},
    {"id":146, "name":"Sandis Vilmanis       ", "pos":"P", "country":"LAT","price":140,"points":0},
    {"id":147, "name":"Rodrigo Abols         ", "pos":"H", "country":"LAT","price":170,"points":0},
    {"id":148, "name":"Rihards Bukarts       ", "pos":"H", "country":"LAT","price":160,"points":0},
    {"id":149, "name":"Zemgus Girgensons     ", "pos":"H", "country":"LAT","price":190,"points":0},
    {"id":150, "name":"Rolands Kenins        ", "pos":"H", "country":"LAT","price":150,"points":0},
    {"id":151, "name":"Henrik Haukeland      ", "pos":"MV", "country":"NOR","price":160,"points":0},
    {"id":152, "name":"Lars Volden           ", "pos":"MV", "country":"NOR","price":120,"points":0},
    {"id":153, "name":"Jonas Holos           ", "pos":"P", "country":"NOR","price":150,"points":0},
    {"id":154, "name":"Andreas Martinsen     ", "pos":"H", "country":"NOR","price":160,"points":0},
    {"id":155, "name":"Patrick Thoresen      ", "pos":"H", "country":"NOR","price":170,"points":0},
    {"id":156, "name":"Mathis Olimb          ", "pos":"H", "country":"NOR","price":160,"points":0},
    {"id":157, "name":"Mats Zuccarello       ", "pos":"H", "country":"NOR","price":250,"points":0},
    {"id":158, "name":"Patrik Rybar          ", "pos":"MV", "country":"SVK","price":170,"points":0},
    {"id":159, "name":"Samuel Hlavaj         ", "pos":"MV", "country":"SVK","price":150,"points":0},
    {"id":160, "name":"Martin Gernat         ", "pos":"P", "country":"SVK","price":170,"points":0},
    {"id":161, "name":"Christos Sarris       ", "pos":"P", "country":"SVK","price":140,"points":0},
    {"id":162, "name":"Tomas Tatar           ", "pos":"H", "country":"SVK","price":220,"points":0},
    {"id":163, "name":"Pavol Regenda         ", "pos":"H", "country":"SVK","price":200,"points":0},
    {"id":164, "name":"Robert Lantosi        ", "pos":"H", "country":"SVK","price":170,"points":0},
    {"id":165, "name":"Libor Hudacek         ", "pos":"H", "country":"SVK","price":180,"points":0},
    {"id":166, "name":"Gasper Kroselj        ", "pos":"MV", "country":"SVN","price":160,"points":0},
    {"id":167, "name":"Luka Gracnar          ", "pos":"MV", "country":"SVN","price":130,"points":0},
    {"id":168, "name":"Ziga Pavlin           ", "pos":"P", "country":"SVN","price":140,"points":0},
    {"id":169, "name":"Bostjan Golicic       ", "pos":"P", "country":"SVN","price":130,"points":0},
    {"id":170, "name":"Anze Kopitar          ", "pos":"H", "country":"SVN","price":280,"points":0},
    {"id":171, "name":"Robert Sabolic        ", "pos":"H", "country":"SVN","price":180,"points":0},
    {"id":172, "name":"Rok Ticar             ", "pos":"H", "country":"SVN","price":160,"points":0},
    {"id":173, "name":"Jan Drozg             ", "pos":"H", "country":"SVN","price":170,"points":0},
    {"id":174, "name":"Jacob Markstrom       ", "pos":"MV", "country":"SWE","price":200,"points":0},
    {"id":175, "name":"Filip Gustavsson      ", "pos":"MV", "country":"SWE","price":190,"points":0},
    {"id":176, "name":"Gustav Forsling       ", "pos":"P", "country":"SWE","price":220,"points":0},
    {"id":177, "name":"Erik Brannstrom       ", "pos":"P", "country":"SWE","price":180,"points":0},
    {"id":178, "name":"Linus Sandin          ", "pos":"H", "country":"SWE","price":190,"points":0},
    {"id":179, "name":"Joel Eriksson Ek      ", "pos":"H", "country":"SWE","price":210,"points":0},
    {"id":180, "name":"Rickard Rakell        ", "pos":"H", "country":"SWE","price":200,"points":0},
    {"id":181, "name":"Akira Schmid          ", "pos":"MV", "country":"SUI","price":170,"points":0},
    {"id":182, "name":"Yannick Weber         ", "pos":"P", "country":"SUI","price":160,"points":0},
    {"id":183, "name":"Janis Moser           ", "pos":"P", "country":"SUI","price":200,"points":0},
    {"id":184, "name":"Sven Andrighetto      ", "pos":"H", "country":"SUI","price":190,"points":0},
    {"id":185, "name":"Damien Riat           ", "pos":"H", "country":"SUI","price":180,"points":0},
    {"id":186, "name":"Lian Bichsel          ", "pos":"H", "country":"SUI","price":170,"points":0},

]
PLAYERS_BY_ID = {int(p['id']): p for p in PLAYERS}


def iso_now():
    return datetime.utcnow().isoformat()


def get_profile(user_id):
    return sb_select('profiles', eq={'id': user_id}, single=True)


def ensure_profile(user_id, email, username=None):
    profile = get_profile(user_id)
    if profile:
        updates = {}
        if email and first(profile, 'email') != email:
            updates['email'] = email
        if username and not first(profile, 'username'):
            updates['username'] = username
        if updates:
            try:
                rows = sb_update('profiles', {'id': user_id}, updates)
                if rows:
                    profile = rows[0]
            except Exception:
                pass
        return profile
    username = username or (email.split('@')[0] if email else 'kayttaja')
    payloads = [
        {'id': user_id, 'username': username, 'email': email, 'transfers_left': 17, 'total_points': 0, 'team_name': '', 'team_confirmed': False, 'created_at': iso_now()},
        {'id': user_id, 'username': username, 'email': email, 'transfersleft': 17, 'totalpoints': 0, 'teamname': '', 'teamconfirmed': False, 'createdat': iso_now()},
    ]
    for payload in payloads:
        try:
            rows = sb_insert('profiles', payload)
            if rows:
                return rows[0]
        except Exception:
            continue
    return get_profile(user_id)


def profile_user(profile, fallback_email=''):
    return {
        'id': first(profile, 'id'),
        'email': first(profile, 'email', default=fallback_email),
        'username': first(profile, 'username', default=(fallback_email.split('@')[0] if fallback_email else 'kayttaja')),
        'transfers_left': first(profile, 'transfers_left', 'transfersleft', default=17),
        'total_points': first(profile, 'total_points', 'totalpoints', default=0),
        'team_name': first(profile, 'team_name', 'teamname', default=''),
        'team_confirmed': first(profile, 'team_confirmed', 'teamconfirmed', default=False),
    }


def teams_for_user(user_id):
    return try_many([
        lambda: sb_select('teams', eq={'user_id': user_id}),
        lambda: sb_select('teams', eq={'userid': user_id}),
    ]) or []


def teams_insert(user_id, player_id):
    return try_many([
        lambda: sb_insert('teams', {'user_id': user_id, 'player_id': player_id, 'added_at': iso_now()}),
        lambda: sb_insert('teams', {'userid': user_id, 'playerid': player_id, 'addedat': iso_now()}),
    ])


def teams_delete(user_id, player_id):
    return try_many([
        lambda: sb_delete('teams', {'user_id': user_id, 'player_id': player_id}),
        lambda: sb_delete('teams', {'userid': user_id, 'playerid': player_id}),
    ])


def league_members_for_user(user_id):
    return try_many([
        lambda: sb_select('league_members', eq={'user_id': user_id}),
        lambda: sb_select('league_members', eq={'userid': user_id}),
    ]) or []


def league_members_for_league(league_id):
    return try_many([
        lambda: sb_select('league_members', eq={'league_id': league_id}),
        lambda: sb_select('league_members', eq={'leagueid': league_id}),
    ]) or []


def league_member_exists(league_id, user_id):
    return try_many([
        lambda: sb_select('league_members', eq={'league_id': league_id, 'user_id': user_id}),
        lambda: sb_select('league_members', eq={'leagueid': league_id, 'userid': user_id}),
    ]) or []


def league_member_insert(league_id, user_id):
    return try_many([
        lambda: sb_insert('league_members', {'league_id': league_id, 'user_id': user_id, 'joined_at': iso_now()}),
        lambda: sb_insert('league_members', {'leagueid': league_id, 'userid': user_id, 'joinedat': iso_now()}),
    ])


def league_member_delete(league_id, user_id):
    return try_many([
        lambda: sb_delete('league_members', {'league_id': league_id, 'user_id': user_id}),
        lambda: sb_delete('league_members', {'leagueid': league_id, 'userid': user_id}),
    ])


def create_league_row(data):
    return try_many([
        lambda: sb_insert('leagues', {'name': data['name'], 'type': data['type'], 'max_members': data['max_members'], 'created_by': data['created_by'], 'created_at': data['created_at'], 'join_code': data.get('join_code')}),
        lambda: sb_insert('leagues', {'name': data['name'], 'type': data['type'], 'maxmembers': data['max_members'], 'createdby': data['created_by'], 'createdat': data['created_at'], 'joincode': data.get('join_code')}),
    ])


def player_points_rows():
    return try_many([
        lambda: sb_select('player_points'),
        lambda: [],
    ]) or []


def player_points_insert(pid, pts, game_date):
    return try_many([
        lambda: sb_insert('player_points', {'player_id': pid, 'points': pts, 'game_date': game_date, 'created_at': iso_now()}),
        lambda: sb_insert('player_points', {'playerid': pid, 'points': pts, 'gamedate': game_date, 'createdat': iso_now()}),
    ])


def recalculate_profile_totals():
    teams = try_many([
        lambda: sb_select('teams'),
        lambda: [],
    ]) or []
    totals = {}
    for row in teams:
        uid = first(row, 'user_id', 'userid')
        pid = first(row, 'player_id', 'playerid')
        try:
            pid = int(pid)
        except Exception:
            continue
        totals[uid] = totals.get(uid, 0) + PLAYERS_BY_ID.get(pid, {}).get('points', 0)
    for prof in sb_select('profiles'):
        uid = first(prof, 'id')
        total = totals.get(uid, 0)
        try:
            sb_update('profiles', {'id': uid}, {'total_points': total})
        except Exception:
            try:
                sb_update('profiles', {'id': uid}, {'totalpoints': total})
            except Exception:
                pass


def ensure_points_loaded():
    global _POINTS_LOADED
    if _POINTS_LOADED:
        return
    for p in PLAYERS:
        p['points'] = 0
    for row in player_points_rows():
        pid = first(row, 'player_id', 'playerid')
        pts = first(row, 'points', default=0)
        try:
            pid = int(pid); pts = int(pts)
        except Exception:
            continue
        if pid in PLAYERS_BY_ID:
            PLAYERS_BY_ID[pid]['points'] += pts
    recalculate_profile_totals()
    _POINTS_LOADED = True


def get_token():
    auth = request.headers.get('Authorization', '').strip()
    if not auth.lower().startswith('bearer '):
        return None
    return auth.split(' ', 1)[1].strip()


def require_auth(fn):
    @wraps(fn)
    def wrapped(*args, **kwargs):
        token = get_token()
        if not token:
            return jsonify({'error':'Ei kirjautunut'}), 401
        status, user = auth_get_user(token)
        if status != 200 or not isinstance(user, dict) or not user.get('id'):
            return jsonify({'error':'Virheellinen token'}), 401
        request.user_id = user.get('id')
        request.user_email = user.get('email', '')
        return fn(*args, **kwargs)
    return wrapped


@app.route('/')
def index():
    return send_from_directory(BASE_DIR, 'etusivu.html')


@app.route('/<path:filename>')
def static_files(filename):
    return send_from_directory(BASE_DIR, filename)


@app.route('/api/auth/register', methods=['POST'])
def register():
    data = request.get_json(force=True) or {}
    email = str(data.get('email', '')).strip().lower()
    password = str(data.get('password', ''))
    username = str(data.get('username', '')).strip()
    if not email or not password or not username:
        return jsonify({'error':'Täytä kaikki kentät'}), 400
    status, resp = auth_signup(email, password)
    if status not in (200, 201):
        msg = (resp or {}).get('msg') or (resp or {}).get('message') or (resp or {}).get('error_description') or (resp or {}).get('error') or 'Rekisteröityminen epäonnistui'
        return jsonify({'error': str(msg)}), 400
    uid = (resp.get('user') or {}).get('id') if isinstance(resp, dict) else None
    if uid:
        ensure_profile(uid, email, username)
    return jsonify({'message':'Tili luotu! Voit nyt kirjautua sisään.'}), 201


@app.route('/api/auth/login', methods=['POST'])
def login():
    data = request.get_json(force=True) or {}
    email = str(data.get('email', '')).strip().lower()
    password = str(data.get('password', ''))
    if not email or not password:
        return jsonify({'error':'Täytä kaikki kentät'}), 400
    status, resp = auth_login(email, password)
    if status != 200 or not isinstance(resp, dict) or not resp.get('access_token'):
        raw = (resp or {}).get('error_description') or (resp or {}).get('message') or 'Kirjautuminen epäonnistui'
        return jsonify({'error': str(raw)}), 401
    user = resp.get('user') or {}
    profile = ensure_profile(user.get('id'), user.get('email', email), (user.get('email', email).split('@')[0] if user.get('email', email) else 'kayttaja'))
    return jsonify({'access_token': resp.get('access_token'), 'user': profile_user(profile, fallback_email=user.get('email', email))}), 200


@app.route('/api/auth/logout', methods=['POST'])
@require_auth
def logout():
    return jsonify({'message':'Kirjauduttu ulos'}), 200


@app.route('/api/auth/me', methods=['GET'])
@require_auth
def me():
    profile = ensure_profile(request.user_id, request.user_email)
    return jsonify(profile_user(profile, fallback_email=request.user_email)), 200


@app.route('/api/players', methods=['GET'])
def players():
    ensure_points_loaded()
    pos = request.args.get('pos', '')
    country = request.args.get('country', '')
    q = request.args.get('q', '').lower()
    sort = request.args.get('sort', 'price')
    result = PLAYERS[:]
    if pos:
        result = [p for p in result if p['pos'] == pos]
    if country:
        result = [p for p in result if p['country'] == country]
    if q:
        result = [p for p in result if q in p['name'].lower()]
    if sort == 'name':
        result.sort(key=lambda p: p['name'].lower())
    else:
        result.sort(key=lambda p: p.get(sort, 0), reverse=True)
    return jsonify(result), 200


@app.route('/api/team', methods=['GET'])
@require_auth
def get_team():
    ensure_points_loaded()
    rows = teams_for_user(request.user_id)
    ids = []
    for r in rows:
        try:
            ids.append(int(first(r, 'player_id', 'playerid')))
        except Exception:
            pass
    team_players = [PLAYERS_BY_ID[i] for i in ids if i in PLAYERS_BY_ID]
    profile = ensure_profile(request.user_id, request.user_email)
    return jsonify({
        'players': team_players,
        'total_price': sum(p['price'] for p in team_players),
        'budget_left': BUDGET - sum(p['price'] for p in team_players),
        'total_points': sum(p.get('points', 0) for p in team_players),
        'team_name': first(profile, 'team_name', 'teamname', default=''),
        'transfers_left': first(profile, 'transfers_left', 'transfersleft', default=17),
        'team_confirmed': first(profile, 'team_confirmed', 'teamconfirmed', default=False),
    }), 200


@app.route('/api/team/add', methods=['POST'])
@require_auth
def add_player():
    ensure_points_loaded()
    data = request.get_json(force=True) or {}
    try:
        pid = int(data.get('player_id'))
    except Exception:
        return jsonify({'error':'Virheellinen player_id'}), 400
    player = PLAYERS_BY_ID.get(pid)
    if not player:
        return jsonify({'error':'Pelaajaa ei löydy'}), 404
    rows = teams_for_user(request.user_id)
    cur_ids = []
    for r in rows:
        try:
            cur_ids.append(int(first(r, 'player_id', 'playerid')))
        except Exception:
            pass
    if pid in cur_ids:
        return jsonify({'error':'Pelaaja on jo joukkueessasi'}), 400
    if len(cur_ids) >= 6:
        return jsonify({'error':'Joukkue on täynnä'}), 400
    cur_players = [PLAYERS_BY_ID[i] for i in cur_ids if i in PLAYERS_BY_ID]
    if sum(1 for p in cur_players if p['pos'] == player['pos']) >= ROSTER_LIMITS[player['pos']]:
        return jsonify({'error':f"Liikaa {player['pos']}-pelaajia"}), 400
    if sum(p['price'] for p in cur_players) + player['price'] > BUDGET:
        return jsonify({'error':'Budjetti ylittyy'}), 400
    prof = ensure_profile(request.user_id, request.user_email)
    transfers = int(first(prof, 'transfers_left', 'transfersleft', default=17))
    if len(cur_ids) > 0 and transfers <= 0:
        return jsonify({'error':'Ei vaihtoja jäljellä'}), 400
    teams_insert(request.user_id, pid)
    if len(cur_ids) > 0:
        try:
            sb_update('profiles', {'id': request.user_id}, {'transfers_left': transfers - 1})
        except Exception:
            try:
                sb_update('profiles', {'id': request.user_id}, {'transfersleft': transfers - 1})
            except Exception:
                pass
    recalculate_profile_totals()
    return jsonify({'message': f"{player['name']} lisätty joukkueeseen"}), 200


@app.route('/api/team/remove', methods=['POST'])
@require_auth
def remove_player():
    data = request.get_json(force=True) or {}
    try:
        pid = int(data.get('player_id'))
    except Exception:
        return jsonify({'error':'Virheellinen player_id'}), 400
    teams_delete(request.user_id, pid)
    recalculate_profile_totals()
    return jsonify({'message':'Pelaaja poistettu'}), 200


@app.route('/api/team/name', methods=['POST'])
@require_auth
def team_name():
    data = request.get_json(force=True) or {}
    name = str(data.get('name', '')).strip()[:40]
    if not name:
        return jsonify({'error':'Anna joukkueelle nimi'}), 400
    ensure_profile(request.user_id, request.user_email)
    try:
        sb_update('profiles', {'id': request.user_id}, {'team_name': name})
    except Exception:
        sb_update('profiles', {'id': request.user_id}, {'teamname': name})
    return jsonify({'message':'Joukkueen nimi tallennettu', 'name': name}), 200


@app.route('/api/team/confirm', methods=['POST'])
@require_auth
def confirm_team():
    rows = teams_for_user(request.user_id)
    ids = []
    for r in rows:
        try: ids.append(int(first(r, 'player_id', 'playerid')))
        except Exception: pass
    team_players = [PLAYERS_BY_ID[i] for i in ids if i in PLAYERS_BY_ID]
    if len(team_players) != 6:
        return jsonify({'error':'Joukkueessa täytyy olla tasan 6 pelaajaa'}), 400
    for pos, lim in ROSTER_LIMITS.items():
        if sum(1 for p in team_players if p['pos'] == pos) != lim:
            return jsonify({'error':f'Väärä määrä {pos}-pelaajia'}), 400
    try:
        sb_update('profiles', {'id': request.user_id}, {'team_confirmed': True, 'confirmed_at': iso_now()})
    except Exception:
        sb_update('profiles', {'id': request.user_id}, {'teamconfirmed': True, 'confirmedat': iso_now()})
    return jsonify({'message':'Joukkue vahvistettu!'}), 200


@app.route('/api/leagues', methods=['GET'])
def leagues():
    rows = sb_select('leagues') or []
    for l in rows:
        lid = first(l, 'id')
        l['member_count'] = len(league_members_for_league(lid))
    return jsonify(rows), 200


@app.route('/api/leagues', methods=['POST'])
@require_auth
def create_league():
    data = request.get_json(force=True) or {}
    name = str(data.get('name', '')).strip()
    league_type = str(data.get('type', 'public'))
    try: max_members = int(data.get('max_members', 20))
    except Exception: max_members = 20
    if not name:
        return jsonify({'error':'Anna liigalle nimi'}), 400
    if league_type not in ('public','private'):
        return jsonify({'error':'Virheellinen liigan tyyppi'}), 400
    import secrets
    payload = {'name': name, 'type': league_type, 'max_members': max_members, 'created_by': request.user_id, 'created_at': iso_now()}
    if league_type == 'private':
        payload['join_code'] = secrets.token_hex(4).upper()
    rows = create_league_row(payload)
    league = rows[0] if rows else None
    if league:
        league_member_insert(first(league, 'id'), request.user_id)
    return jsonify({'message':'Liiga luotu!', 'league_id': first(league, 'id') if league else None, 'join_code': first(league, 'join_code', 'joincode')}), 201


@app.route('/api/leagues/<league_id>/join', methods=['POST'])
@require_auth
def join_league(league_id):
    data = request.get_json(force=True) or {}
    league = sb_select('leagues', eq={'id': league_id}, single=True)
    if not league:
        return jsonify({'error':'Liigaa ei löydy'}), 404
    if first(league, 'type') == 'private':
        provided = str(data.get('join_code', '')).strip().upper()
        if provided != str(first(league, 'join_code', 'joincode', default='')).upper():
            return jsonify({'error':'Väärä liittymiskoodi'}), 403
    if league_member_exists(league_id, request.user_id):
        return jsonify({'error':'Olet jo tässä liigassa'}), 400
    if len(league_members_for_league(league_id)) >= int(first(league, 'max_members', 'maxmembers', default=20)):
        return jsonify({'error':'Liiga on täynnä'}), 400
    league_member_insert(league_id, request.user_id)
    return jsonify({'message':'Liittyminen onnistui!'}), 200


@app.route('/api/leagues/<league_id>/leave', methods=['POST'])
@require_auth
def leave_league(league_id):
    league_member_delete(league_id, request.user_id)
    return jsonify({'message':'Poistuttu liigasta'}), 200


@app.route('/api/leagues/mine', methods=['GET'])
@require_auth
def my_leagues():
    result = []
    for m in league_members_for_user(request.user_id):
        lid = first(m, 'league_id', 'leagueid')
        league = sb_select('leagues', eq={'id': lid}, single=True)
        if league:
            league['member_count'] = len(league_members_for_league(lid))
            result.append(league)
    return jsonify(result), 200


@app.route('/api/leagues/<league_id>/standings', methods=['GET'])
def league_standings(league_id):
    ensure_points_loaded()
    result = []
    for m in league_members_for_league(league_id):
        uid = first(m, 'user_id', 'userid')
        prof = get_profile(uid)
        if prof:
            result.append({'username': first(prof, 'username', default='kayttaja'), 'points': first(prof, 'total_points', 'totalpoints', default=0)})
    result.sort(key=lambda x: x['points'], reverse=True)
    for i, r in enumerate(result, start=1):
        r['rank'] = i
    return jsonify(result), 200


@app.route('/api/points/leaderboard', methods=['GET'])
def leaderboard():
    ensure_points_loaded()
    profiles = sb_select('profiles') or []
    rows = [{'username': first(p, 'username', default='kayttaja'), 'points': first(p, 'total_points', 'totalpoints', default=0)} for p in profiles]
    rows.sort(key=lambda x: x['points'], reverse=True)
    for i, r in enumerate(rows[:50], start=1):
        r['rank'] = i
    return jsonify(rows[:50]), 200


@app.route('/api/points/update', methods=['POST'])
def points_update():
    if request.headers.get('X-Admin-Secret', '') != os.environ.get('ADMIN_SECRET', ''):
        return jsonify({'error':'Ei oikeuksia'}), 403
    ensure_points_loaded()
    data = request.get_json(force=True) or {}
    events = data.get('events', [])
    rules = {'H':{'goal':4,'assist':2,'plus':1,'minus':-1,'minor':-1,'gm':-5},'P':{'goal':6,'assist':4,'plus':2,'minus':-2,'minor':-1,'gm':-5},'MV':{'win':2,'loss':-2,'shutout':8,'ga':-1,'minor':-1,'gm':-5}}
    def save_points(n):
        if n <= 0: return 0
        if n <= 10: return 1
        if n <= 15: return 3
        if n <= 20: return 5
        if n <= 25: return 7
        if n <= 30: return 9
        return 9 + ((n - 30)//5)*2
    for ev in events:
        try: pid = int(ev.get('player_id') or ev.get('playerid'))
        except Exception: continue
        player = PLAYERS_BY_ID.get(pid)
        if not player: continue
        pts = 0
        if player['pos'] in ('H','P'):
            r = rules[player['pos']]
            pts += int(ev.get('goals', 0)) * r['goal']
            pts += int(ev.get('assists', 0)) * r['assist']
            pts += int(ev.get('plus', 0)) * r['plus']
            pts += int(ev.get('minus', 0)) * r['minus']
            pts += int(ev.get('minor_penalties', ev.get('minorpenalties', 0))) * r['minor']
            pts += int(ev.get('game_misconducts', ev.get('gamemisconducts', 0))) * r['gm']
        else:
            r = rules['MV']
            pts += int(ev.get('wins', 0)) * r['win']
            pts += int(ev.get('losses', 0)) * r['loss']
            pts += int(ev.get('shutouts', 0)) * r['shutout']
            pts += int(ev.get('goals_against', ev.get('goalsagainst', 0))) * r['ga']
            pts += save_points(int(ev.get('saves', 0)))
            pts += int(ev.get('minor_penalties', ev.get('minorpenalties', 0))) * r['minor']
            pts += int(ev.get('game_misconducts', ev.get('gamemisconducts', 0))) * r['gm']
        player_points_insert(pid, pts, ev.get('game_date') or ev.get('gamedate') or datetime.utcnow().date().isoformat())
        player['points'] = player.get('points', 0) + pts
    recalculate_profile_totals()
    return jsonify({'message':'Pisteet päivitetty'}), 200


@app.route('/api/health', methods=['GET'])
def health():
    try:
        _init()
        return jsonify({'status':'ok','version':'3.1.0-compat'}), 200
    except Exception as e:
        return jsonify({'status':'error','detail':str(e)}), 500


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
