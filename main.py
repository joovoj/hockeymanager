from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from supabase import create_client, Client
from functools import wraps
from dotenv import load_dotenv
import os
from datetime import datetime

load_dotenv()

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-key")
CORS(app, supports_credentials=True, origins=["*"])

_supabase = None

def get_supabase():
    global _supabase
    if _supabase is None:
        url = os.environ.get("SUPABASE_URL", "")
        key = os.environ.get("SUPABASE_KEY", "")
        if not url or not key:
            raise Exception("SUPABASE_URL tai SUPABASE_KEY puuttuu ympäristömuuttujista")
        _supabase = create_client(url, key)
    return _supabase

BUDGET = 1000
ROSTER_LIMITS = {"H": 3, "P": 2, "MV": 1}

PLAYERS = [
    {"id": 1,  "name": "Connor McDavid",      "pos": "H",  "country": "CAN", "price": 300, "points": 0},
    {"id": 2,  "name": "Auston Matthews",      "pos": "H",  "country": "USA", "price": 290, "points": 0},
    {"id": 3,  "name": "Mikko Rantanen",       "pos": "H",  "country": "FIN", "price": 285, "points": 0},
    {"id": 4,  "name": "Nathan MacKinnon",     "pos": "H",  "country": "CAN", "price": 295, "points": 0},
    {"id": 5,  "name": "David Pastrnak",       "pos": "H",  "country": "CZE", "price": 270, "points": 0},
    {"id": 6,  "name": "Leon Draisaitl",       "pos": "H",  "country": "GER", "price": 280, "points": 0},
    {"id": 7,  "name": "Aleksander Barkov",    "pos": "H",  "country": "FIN", "price": 265, "points": 0},
    {"id": 8,  "name": "Kirill Kaprizov",      "pos": "H",  "country": "RUS", "price": 260, "points": 0},
    {"id": 9,  "name": "Cale Makar",           "pos": "P",  "country": "CAN", "price": 280, "points": 0},
    {"id": 10, "name": "Roman Josi",           "pos": "P",  "country": "SUI", "price": 240, "points": 0},
    {"id": 11, "name": "Miro Heiskanen",       "pos": "P",  "country": "FIN", "price": 235, "points": 0},
    {"id": 12, "name": "Victor Hedman",        "pos": "P",  "country": "SWE", "price": 220, "points": 0},
    {"id": 13, "name": "Adam Fox",             "pos": "P",  "country": "USA", "price": 215, "points": 0},
    {"id": 14, "name": "Rasmus Dahlin",        "pos": "P",  "country": "SWE", "price": 210, "points": 0},
    {"id": 15, "name": "Juuse Saros",          "pos": "MV", "country": "FIN", "price": 190, "points": 0},
    {"id": 16, "name": "Igor Shesterkin",      "pos": "MV", "country": "RUS", "price": 210, "points": 0},
    {"id": 17, "name": "Connor Hellebuyck",    "pos": "MV", "country": "USA", "price": 215, "points": 0},
    {"id": 18, "name": "Linus Ullmark",        "pos": "MV", "country": "SWE", "price": 185, "points": 0},
    {"id": 19, "name": "Roope Hintz",          "pos": "H",  "country": "FIN", "price": 200, "points": 0},
    {"id": 20, "name": "Patrik Laine",         "pos": "H",  "country": "FIN", "price": 195, "points": 0},
    {"id": 21, "name": "Sebastian Aho",        "pos": "H",  "country": "FIN", "price": 210, "points": 0},
    {"id": 22, "name": "Elias Pettersson",     "pos": "H",  "country": "SWE", "price": 240, "points": 0},
    {"id": 23, "name": "Filip Forsberg",       "pos": "H",  "country": "SWE", "price": 220, "points": 0},
    {"id": 24, "name": "William Nylander",     "pos": "H",  "country": "SWE", "price": 215, "points": 0},
    {"id": 25, "name": "Artemi Panarin",       "pos": "H",  "country": "RUS", "price": 255, "points": 0},
    {"id": 26, "name": "Jason Robertson",      "pos": "H",  "country": "USA", "price": 230, "points": 0},
    {"id": 27, "name": "Brady Tkachuk",        "pos": "H",  "country": "CAN", "price": 225, "points": 0},
    {"id": 28, "name": "Mark Scheifele",       "pos": "H",  "country": "CAN", "price": 200, "points": 0},
    {"id": 29, "name": "Nicklas Backstrom",    "pos": "H",  "country": "SWE", "price": 180, "points": 0},
    {"id": 30, "name": "Erik Karlsson",        "pos": "P",  "country": "SWE", "price": 200, "points": 0},
    {"id": 31, "name": "John Carlson",         "pos": "P",  "country": "USA", "price": 175, "points": 0},
    {"id": 32, "name": "Noah Dobson",          "pos": "P",  "country": "CAN", "price": 180, "points": 0},
    {"id": 33, "name": "Quinn Hughes",         "pos": "P",  "country": "USA", "price": 260, "points": 0},
    {"id": 34, "name": "Brayden Point",        "pos": "H",  "country": "CAN", "price": 245, "points": 0},
    {"id": 35, "name": "Nikita Kucherov",      "pos": "H",  "country": "RUS", "price": 290, "points": 0},
    {"id": 36, "name": "Jake Guentzel",        "pos": "H",  "country": "USA", "price": 195, "points": 0},
    {"id": 37, "name": "Timo Meier",           "pos": "H",  "country": "SUI", "price": 200, "points": 0},
    {"id": 38, "name": "Nico Hischier",        "pos": "H",  "country": "SUI", "price": 185, "points": 0},
    {"id": 39, "name": "Kevin Fiala",          "pos": "H",  "country": "SUI", "price": 180, "points": 0},
    {"id": 40, "name": "Denis Malgin",         "pos": "H",  "country": "SUI", "price": 120, "points": 0},
    {"id": 41, "name": "Gregory Hofmann",      "pos": "H",  "country": "SUI", "price": 115, "points": 0},
    {"id": 42, "name": "Mirco Mueller",        "pos": "P",  "country": "SUI", "price": 110, "points": 0},
    {"id": 43, "name": "Jonas Siegenthaler",   "pos": "P",  "country": "SUI", "price": 120, "points": 0},
    {"id": 44, "name": "Reto Berra",           "pos": "MV", "country": "SUI", "price": 110, "points": 0},
    {"id": 45, "name": "Nino Niederreiter",    "pos": "H",  "country": "SUI", "price": 160, "points": 0},
    {"id": 46, "name": "Patrick Kane",         "pos": "H",  "country": "USA", "price": 170, "points": 0},
    {"id": 47, "name": "Jack Eichel",          "pos": "H",  "country": "USA", "price": 210, "points": 0},
    {"id": 48, "name": "Trevor Zegras",        "pos": "H",  "country": "USA", "price": 160, "points": 0},
    {"id": 49, "name": "Cole Caufield",        "pos": "H",  "country": "USA", "price": 175, "points": 0},
    {"id": 50, "name": "Dylan Larkin",         "pos": "H",  "country": "USA", "price": 180, "points": 0},
]

# ── AUTH DECORATOR ────────────────────────────────────────────────────────────
def require_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get("Authorization", "").replace("Bearer ", "")
        if not token:
            return jsonify({"error": "Ei kirjautunut"}), 401
        try:
            user = get_supabase().auth.get_user(token)
            request.user = user.user
        except Exception as e:
            return jsonify({"error": "Virheellinen token"}), 401
        return f(*args, **kwargs)
    return decorated

# ── STATIC FILES ──────────────────────────────────────────────────────────────
@app.route("/")
def index():
    return send_from_directory(".", "etusivu.html")

@app.route("/<path:filename>")
def serve_file(filename):
    return send_from_directory(".", filename)

# ── AUTH ──────────────────────────────────────────────────────────────────────
@app.route("/api/auth/register", methods=["POST"])
def register():
    data = request.get_json()
    email = data.get("email", "").strip()
    password = data.get("password", "")
    username = data.get("username", "").strip()
    if not email or not password or not username:
        return jsonify({"error": "Täytä kaikki kentät"}), 400
    if len(password) < 6:
        return jsonify({"error": "Salasana on liian lyhyt (min 6 merkkiä)"}), 400
    try:
        sb = get_supabase()
        res = sb.auth.sign_up({"email": email, "password": password})
        if not res.user:
            return jsonify({"error": "Rekisteröityminen epäonnistui"}), 400
        uid = res.user.id
        sb.table("profiles").insert({
            "id": uid, "username": username, "email": email,
            "transfers_left": 17, "total_points": 0,
            "created_at": datetime.utcnow().isoformat()
        }).execute()
        return jsonify({"message": "Rekisteröityminen onnistui! Tarkista sähköpostisi vahvistusviesti.", "user_id": uid}), 201
    except Exception as e:
        err = str(e)
        if "already registered" in err or "already been registered" in err:
            return jsonify({"error": "Sähköposti on jo käytössä"}), 400
        return jsonify({"error": err}), 400

@app.route("/api/auth/login", methods=["POST"])
def login():
    data = request.get_json()
    email = data.get("email", "").strip()
    password = data.get("password", "")
    if not email or not password:
        return jsonify({"error": "Täytä kaikki kentät"}), 400
    try:
        sb = get_supabase()
        res = sb.auth.sign_in_with_password({"email": email, "password": password})
        profile = sb.table("profiles").select("*").eq("id", res.user.id).single().execute()
        return jsonify({
            "access_token": res.session.access_token,
            "user": {
                "id": res.user.id,
                "email": res.user.email,
                "username": profile.data["username"],
                "transfers_left": profile.data["transfers_left"],
                "total_points": profile.data["total_points"]
            }
        }), 200
    except Exception as e:
        err = str(e)
        if "Invalid login" in err or "invalid" in err.lower():
            return jsonify({"error": "Väärä sähköposti tai salasana"}), 401
        return jsonify({"error": err}), 401

@app.route("/api/auth/logout", methods=["POST"])
@require_auth
def logout():
    try:
        get_supabase().auth.sign_out()
        return jsonify({"message": "Kirjauduttu ulos"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 400

@app.route("/api/auth/me", methods=["GET"])
@require_auth
def me():
    try:
        profile = get_supabase().table("profiles").select("*").eq("id", request.user.id).single().execute()
        return jsonify(profile.data), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 400

# ── PLAYERS ───────────────────────────────────────────────────────────────────
@app.route("/api/players", methods=["GET"])
def get_players():
    pos = request.args.get("pos", "")
    country = request.args.get("country", "")
    q = request.args.get("q", "").lower()
    sort = request.args.get("sort", "price")
    filtered = PLAYERS
    if pos:
        filtered = [p for p in filtered if p["pos"] == pos]
    if country:
        filtered = [p for p in filtered if p["country"] == country]
    if q:
        filtered = [p for p in filtered if q in p["name"].lower()]
    if sort in ("points", "price", "name"):
        filtered = sorted(filtered, key=lambda p: p[sort], reverse=(sort != "name"))
    return jsonify(filtered), 200

@app.route("/api/players/<int:player_id>", methods=["GET"])
def get_player(player_id):
    player = next((p for p in PLAYERS if p["id"] == player_id), None)
    if not player:
        return jsonify({"error": "Pelaajaa ei löydy"}), 404
    return jsonify(player), 200

# ── TEAM ───────────────────��──────────────────────────────────────────────────
@app.route("/api/team", methods=["GET"])
@require_auth
def get_team():
    try:
        sb = get_supabase()
        res = sb.table("teams").select("*").eq("user_id", request.user.id).execute()
        player_ids = [row["player_id"] for row in res.data]
        team_players = [p for p in PLAYERS if p["id"] in player_ids]
        total_price = sum(p["price"] for p in team_players)
        total_points = sum(p["points"] for p in team_players)
        return jsonify({
            "players": team_players,
            "total_price": total_price,
            "budget_left": BUDGET - total_price,
            "total_points": total_points
        }), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 400

@app.route("/api/team/add", methods=["POST"])
@require_auth
def add_player():
    data = request.get_json()
    player_id = data.get("player_id")
    player = next((p for p in PLAYERS if p["id"] == player_id), None)
    if not player:
        return jsonify({"error": "Pelaajaa ei löydy"}), 404
    try:
        sb = get_supabase()
        existing = sb.table("teams").select("*").eq("user_id", request.user.id).execute()
        current_ids = [row["player_id"] for row in existing.data]
        if player_id in current_ids:
            return jsonify({"error": "Pelaaja on jo joukkueessasi"}), 400
        if len(current_ids) >= 6:
            return jsonify({"error": "Joukkue on täynnä (max 6 pelaajaa)"}), 400
        current_players = [p for p in PLAYERS if p["id"] in current_ids]
        if sum(1 for p in current_players if p["pos"] == player["pos"]) >= ROSTER_LIMITS[player["pos"]]:
            return jsonify({"error": f"Liikaa {player['pos']}-pelaajia"}), 400
        if sum(p["price"] for p in current_players) + player["price"] > BUDGET:
            return jsonify({"error": "Budjetti ylittyy"}), 400
        profile = sb.table("profiles").select("transfers_left").eq("id", request.user.id).single().execute()
        if len(current_ids) > 0 and profile.data["transfers_left"] <= 0:
            return jsonify({"error": "Ei vaihtoja jäljellä"}), 400
        sb.table("teams").insert({
            "user_id": request.user.id, "player_id": player_id,
            "added_at": datetime.utcnow().isoformat()
        }).execute()
        if len(current_ids) > 0:
            sb.table("profiles").update({
                "transfers_left": profile.data["transfers_left"] - 1
            }).eq("id", request.user.id).execute()
        return jsonify({"message": f"{player['name']} lisätty joukkueeseen"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 400

@app.route("/api/team/remove", methods=["POST"])
@require_auth
def remove_player():
    data = request.get_json()
    player_id = data.get("player_id")
    try:
        get_supabase().table("teams").delete().eq("user_id", request.user.id).eq("player_id", player_id).execute()
        return jsonify({"message": "Pelaaja poistettu joukkueesta"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 400

@app.route("/api/team/confirm", methods=["POST"])
@require_auth
def confirm_team():
    try:
        sb = get_supabase()
        res = sb.table("teams").select("*").eq("user_id", request.user.id).execute()
        player_ids = [row["player_id"] for row in res.data]
        players = [p for p in PLAYERS if p["id"] in player_ids]
        if len(players) != 6:
            return jsonify({"error": "Joukkueessa täytyy olla tasan 6 pelaajaa"}), 400
        for pos, limit in ROSTER_LIMITS.items():
            if sum(1 for p in players if p["pos"] == pos) != limit:
                return jsonify({"error": f"Väärä määrä {pos}-pelaajia"}), 400
        sb.table("profiles").update({
            "team_confirmed": True,
            "confirmed_at": datetime.utcnow().isoformat()
        }).eq("id", request.user.id).execute()
        return jsonify({"message": "Joukkue vahvistettu!"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 400

# ── LEAGUES ───────────────────────────────────────────────────────────────────
@app.route("/api/leagues", methods=["GET"])
def get_leagues():
    type_filter = request.args.get("type", "")
    q = request.args.get("q", "").lower()
    try:
        sb = get_supabase()
        query = sb.table("leagues").select("*")
        if type_filter in ("public", "private"):
            query = query.eq("type", type_filter)
        leagues = query.execute().data
        if q:
            leagues = [l for l in leagues if q in l["name"].lower()]
        for league in leagues:
            members = sb.table("league_members").select("id").eq("league_id", league["id"]).execute()
            league["member_count"] = len(members.data)
        return jsonify(leagues), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 400

@app.route("/api/leagues", methods=["POST"])
@require_auth
def create_league():
    data = request.get_json()
    name = data.get("name", "").strip()
    league_type = data.get("type", "public")
    max_members = int(data.get("max_members", 20))
    if not name:
        return jsonify({"error": "Anna liigalle nimi"}), 400
    if league_type not in ("public", "private"):
        return jsonify({"error": "Virheellinen liigan tyyppi"}), 400
    if not 2 <= max_members <= 500:
        return jsonify({"error": "Max jäsenmäärä täytyy olla 2-500"}), 400
    try:
        sb = get_supabase()
        res = sb.table("leagues").insert({
            "name": name, "type": league_type, "max_members": max_members,
            "created_by": request.user.id, "created_at": datetime.utcnow().isoformat()
        }).execute()
        league_id = res.data[0]["id"]
        sb.table("league_members").insert({
            "league_id": league_id, "user_id": request.user.id,
            "joined_at": datetime.utcnow().isoformat()
        }).execute()
        return jsonify({"message": "Liiga luotu!", "league_id": league_id}), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 400

@app.route("/api/leagues/<league_id>/join", methods=["POST"])
@require_auth
def join_league(league_id):
    try:
        sb = get_supabase()
        league = sb.table("leagues").select("*").eq("id", league_id).single().execute()
        if not league.data:
            return jsonify({"error": "Liigaa ei löydy"}), 404
        members = sb.table("league_members").select("*").eq("league_id", league_id).execute()
        if len(members.data) >= league.data["max_members"]:
            return jsonify({"error": "Liiga on täynnä"}), 400
        already = sb.table("league_members").select("*").eq("league_id", league_id).eq("user_id", request.user.id).execute()
        if already.data:
            return jsonify({"error": "Olet jo tässä liigassa"}), 400
        sb.table("league_members").insert({
            "league_id": league_id, "user_id": request.user.id,
            "joined_at": datetime.utcnow().isoformat()
        }).execute()
        return jsonify({"message": "Liittyminen onnistui!"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 400

@app.route("/api/leagues/<league_id>/leave", methods=["POST"])
@require_auth
def leave_league(league_id):
    try:
        get_supabase().table("league_members").delete().eq("league_id", league_id).eq("user_id", request.user.id).execute()
        return jsonify({"message": "Poistuttu liigasta"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 400

@app.route("/api/leagues/<league_id>/standings", methods=["GET"])
def league_standings(league_id):
    try:
        sb = get_supabase()
        members = sb.table("league_members").select("user_id").eq("league_id", league_id).execute()
        standings = []
        for m in members.data:
            profile = sb.table("profiles").select("username, total_points").eq("id", m["user_id"]).single().execute()
            if profile.data:
                standings.append({"user_id": m["user_id"], "username": profile.data["username"], "points": profile.data["total_points"]})
        standings.sort(key=lambda x: x["points"], reverse=True)
        for i, s in enumerate(standings):
            s["rank"] = i + 1
        return jsonify(standings), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 400

@app.route("/api/leagues/mine", methods=["GET"])
@require_auth
def my_leagues():
    try:
        sb = get_supabase()
        memberships = sb.table("league_members").select("league_id").eq("user_id", request.user.id).execute()
        leagues = []
        for m in memberships.data:
            league = sb.table("leagues").select("*").eq("id", m["league_id"]).single().execute()
            if league.data:
                members = sb.table("league_members").select("id").eq("league_id", m["league_id"]).execute()
                league.data["member_count"] = len(members.data)
                leagues.append(league.data)
        return jsonify(leagues), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 400

# ── POINTS ────────────────────────────────────────────────────────────────────
@app.route("/api/points/update", methods=["POST"])
def update_points():
    if request.headers.get("X-Admin-Secret", "") != os.environ.get("ADMIN_SECRET", ""):
        return jsonify({"error": "Ei oikeuksia"}), 403
    data = request.get_json()
    player_events = data.get("events", [])
    point_rules = {
        "H":  {"goal": 4,  "assist": 2, "plus": 1,  "minus": -1, "minor_penalty": -1, "game_misconduct": -5},
        "P":  {"goal": 6,  "assist": 4, "plus": 2,  "minus": -2, "minor_penalty": -1, "game_misconduct": -5},
        "MV": {"win": 2, "loss": -2, "shutout": 8, "goal_against": -1, "minor_penalty": -1, "game_misconduct": -5},
    }
    def saves_points(saves):
        if saves <= 10: return 1
        elif saves <= 15: return 3
        elif saves <= 20: return 5
        elif saves <= 25: return 7
        elif saves <= 30: return 9
        else: return 9 + ((saves - 30) // 5) * 2
    try:
        sb = get_supabase()
        for event in player_events:
            pid = event.get("player_id")
            player = next((p for p in PLAYERS if p["id"] == pid), None)
            if not player:
                continue
            pts = 0
            rules = point_rules[player["pos"]]
            if player["pos"] in ("H", "P"):
                pts += rules["goal"]  * event.get("goals", 0)
                pts += rules["assist"] * event.get("assists", 0)
                pts += rules["plus"]  * event.get("plus", 0)
                pts += rules["minus"] * event.get("minus", 0)
                pts += rules["minor_penalty"] * event.get("minor_penalties", 0)
                pts += rules["game_misconduct"] * event.get("game_misconducts", 0)
            elif player["pos"] == "MV":
                pts += rules["win"]  * event.get("wins", 0)
                pts += rules["loss"] * event.get("losses", 0)
                pts += rules["shutout"] * event.get("shutouts", 0)
                pts += rules["goal_against"] * event.get("goals_against", 0)
                pts += saves_points(event.get("saves", 0))
                pts += rules["minor_penalty"] * event.get("minor_penalties", 0)
                pts += rules["game_misconduct"] * event.get("game_misconducts", 0)
            sb.table("player_points").insert({
                "player_id": pid, "points": pts,
                "game_date": event.get("game_date", datetime.utcnow().date().isoformat()),
                "created_at": datetime.utcnow().isoformat()
            }).execute()
            player["points"] = player.get("points", 0) + pts
        all_users = sb.table("teams").select("user_id, player_id").execute()
        user_map = {}
        for row in all_users.data:
            user_map.setdefault(row["user_id"], []).append(row["player_id"])
        updated_ids = {e["player_id"] for e in player_events}
        for uid, pids in user_map.items():
            gained = sum(
                next((e.get("points_gained", 0) for e in player_events if e["player_id"] == p["id"]), 0)
                for p in PLAYERS if p["id"] in pids and p["id"] in updated_ids
            )
            if gained:
                profile = sb.table("profiles").select("total_points").eq("id", uid).single().execute()
                new_total = (profile.data["total_points"] or 0) + gained
                sb.table("profiles").update({"total_points": new_total}).eq("id", uid).execute()
        return jsonify({"message": "Pisteet päivitetty"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 400

@app.route("/api/points/leaderboard", methods=["GET"])
def leaderboard():
    try:
        profiles = get_supabase().table("profiles").select("username, total_points").order("total_points", desc=True).limit(50).execute()
        result = [{"rank": i+1, "username": p["username"], "points": p["total_points"]} for i, p in enumerate(profiles.data)]
        return jsonify(result), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 400

# ── HEALTH ────────────────────────────────────────────────────────────────────
@app.route("/api/health", methods=["GET"])
def health():
    try:
        sb = get_supabase()
        return jsonify({"status": "ok", "version": "1.1.0", "supabase": "connected"}), 200
    except Exception as e:
        return jsonify({"status": "error", "detail": str(e)}), 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
