from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from supabase import create_client, Client
from functools import wraps
from dotenv import load_dotenv
import os
from datetime import datetime

load_dotenv()

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-key-change-in-production")
CORS(app, supports_credentials=True, origins=["*"])

_supabase = None

def get_supabase():
    global _supabase
    if _supabase is None:
        url = os.environ.get("SUPABASE_URL", "")
        key = os.environ.get("SUPABASE_KEY", "")
        _supabase = create_client(url, key)
    return _supabase

BUDGET = 1000
ROSTER_LIMITS = {"H": 3, "P": 2, "MV": 1}

PLAYERS = [
    {"id": 1,  "name": "Connor McDavid",     "pos": "H",  "country": "CAN", "price": 300, "points": 148},
    {"id": 2,  "name": "Auston Matthews",    "pos": "H",  "country": "USA", "price": 290, "points": 140},
    {"id": 3,  "name": "Mikko Rantanen",     "pos": "H",  "country": "FIN", "price": 285, "points": 132},
    {"id": 4,  "name": "Nathan MacKinnon",   "pos": "H",  "country": "CAN", "price": 295, "points": 146},
    {"id": 5,  "name": "David Pastrnak",     "pos": "H",  "country": "CZE", "price": 270, "points": 124},
    {"id": 6,  "name": "Leon Draisaitl",     "pos": "H",  "country": "GER", "price": 280, "points": 128},
    {"id": 7,  "name": "Aleksander Barkov",  "pos": "H",  "country": "FIN", "price": 265, "points": 118},
    {"id": 8,  "name": "Kirill Kaprizov",    "pos": "H",  "country": "RUS", "price": 260, "points": 115},
    {"id": 9,  "name": "Cale Makar",         "pos": "P",  "country": "CAN", "price": 280, "points": 118},
    {"id": 10, "name": "Roman Josi",         "pos": "P",  "country": "SUI", "price": 240, "points": 101},
    {"id": 11, "name": "Miro Heiskanen",     "pos": "P",  "country": "FIN", "price": 235, "points": 96},
    {"id": 12, "name": "Victor Hedman",      "pos": "P",  "country": "SWE", "price": 220, "points": 89},
    {"id": 13, "name": "Adam Fox",           "pos": "P",  "country": "USA", "price": 215, "points": 85},
    {"id": 14, "name": "Rasmus Dahlin",      "pos": "P",  "country": "SWE", "price": 210, "points": 82},
    {"id": 15, "name": "Juuse Saros",        "pos": "MV", "country": "FIN", "price": 190, "points": 92},
    {"id": 16, "name": "Igor Shesterkin",    "pos": "MV", "country": "RUS", "price": 210, "points": 99},
    {"id": 17, "name": "Connor Hellebuyck",  "pos": "MV", "country": "USA", "price": 215, "points": 104},
    {"id": 18, "name": "Linus Ullmark",      "pos": "MV", "country": "SWE", "price": 185, "points": 88},
]


def require_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get("Authorization", "").replace("Bearer ", "")
        if not token:
            return jsonify({"error": "Ei kirjautunut"}), 401
        try:
            user = get_supabase().auth.get_user(token)
            request.user = user.user
        except Exception:
            return jsonify({"error": "Virheellinen token"}), 401
        return f(*args, **kwargs)
    return decorated


@app.route("/")
def index():
    return send_from_directory(".", "etusivu.html")

@app.route("/<path:filename>")
def serve_file(filename):
    return send_from_directory(".", filename)


# ── AUTH ────────────────────────────────────────────────────────────────────

@app.route("/api/auth/register", methods=["POST"])
def register():
    data = request.get_json()
    email    = data.get("email", "").strip()
    password = data.get("password", "")
    username = data.get("username", "").strip()
    if not email or not password or not username:
        return jsonify({"error": "Tayta kaikki kentat"}), 400
    if len(password) < 6:
        return jsonify({"error": "Salasana on liian lyhyt (min 6 merkkia)"}), 400
    try:
        res = get_supabase().auth.sign_up({"email": email, "password": password})
        uid = res.user.id
        get_supabase().table("profiles").insert({
            "id": uid, "username": username, "email": email,
            "transfers_left": 17, "total_points": 0,
            "team_name": "", "captain_id": None,
            "team_confirmed": False,
            "created_at": datetime.utcnow().isoformat()
        }).execute()
        return jsonify({"message": "Rekisteroityminen onnistui", "user_id": uid}), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app.route("/api/auth/login", methods=["POST"])
def login():
    data = request.get_json()
    email    = data.get("email", "").strip()
    password = data.get("password", "")
    if not email or not password:
        return jsonify({"error": "Tayta kaikki kentat"}), 400
    try:
        res     = get_supabase().auth.sign_in_with_password({"email": email, "password": password})
        profile = get_supabase().table("profiles").select("*").eq("id", res.user.id).single().execute()
        return jsonify({
            "access_token": res.session.access_token,
            "user": {
                "id":             res.user.id,
                "email":          res.user.email,
                "username":       profile.data["username"],
                "transfers_left": profile.data["transfers_left"],
                "total_points":   profile.data["total_points"],
            }
        }), 200
    except Exception:
        return jsonify({"error": "Vaara sahkoposti tai salasana"}), 401


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


# ── PLAYERS ─────────────────────────────────────────────────────────────────

@app.route("/api/players", methods=["GET"])
def get_players():
    pos     = request.args.get("pos", "")
    country = request.args.get("country", "")
    q       = request.args.get("q", "").lower()
    sort    = request.args.get("sort", "points")
    result  = PLAYERS[:]
    if pos:     result = [p for p in result if p["pos"] == pos]
    if country: result = [p for p in result if p["country"] == country]
    if q:       result = [p for p in result if q in p["name"].lower()]
    if sort in ("points", "price", "name"):
        result = sorted(result, key=lambda p: p[sort], reverse=(sort != "name"))
    return jsonify(result), 200


@app.route("/api/players/<int:player_id>", methods=["GET"])
def get_player(player_id):
    player = next((p for p in PLAYERS if p["id"] == player_id), None)
    if not player:
        return jsonify({"error": "Pelaajaa ei loydy"}), 404
    return jsonify(player), 200


# ── TEAM ─────────────────────────────────────────────────────────────────────

@app.route("/api/team", methods=["GET"])
@require_auth
def get_team():
    try:
        res        = get_supabase().table("teams").select("*").eq("user_id", request.user.id).execute()
        profile    = get_supabase().table("profiles").select(
            "team_name, captain_id, team_confirmed, transfers_left"
        ).eq("id", request.user.id).single().execute()

        player_ids   = [row["player_id"] for row in res.data]
        team_players = [p for p in PLAYERS if p["id"] in player_ids]
        total_price  = sum(p["price"] for p in team_players)
        total_points = sum(p["points"] for p in team_players)

        pd = profile.data or {}
        return jsonify({
            "players":        team_players,
            "total_price":    total_price,
            "budget_left":    BUDGET - total_price,
            "total_points":   total_points,
            "team_name":      pd.get("team_name") or "",
            "captain_id":     pd.get("captain_id"),
            "team_confirmed": pd.get("team_confirmed") or False,
            "transfers_left": pd.get("transfers_left", 0),
        }), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app.route("/api/team/add", methods=["POST"])
@require_auth
def add_player():
    data      = request.get_json()
    player_id = data.get("player_id")
    player    = next((p for p in PLAYERS if p["id"] == player_id), None)
    if not player:
        return jsonify({"error": "Pelaajaa ei loydy"}), 404
    try:
        existing     = get_supabase().table("teams").select("*").eq("user_id", request.user.id).execute()
        current_ids  = [row["player_id"] for row in existing.data]
        if player_id in current_ids:
            return jsonify({"error": "Pelaaja on jo joukkueessasi"}), 400
        if len(current_ids) >= 6:
            return jsonify({"error": "Joukkue on taynna (max 6 pelaajaa)"}), 400
        current_players   = [p for p in PLAYERS if p["id"] in current_ids]
        current_pos_count = sum(1 for p in current_players if p["pos"] == player["pos"])
        if current_pos_count >= ROSTER_LIMITS[player["pos"]]:
            return jsonify({"error": f"Liikaa {player['pos']}-pelaajia"}), 400
        current_cost = sum(p["price"] for p in current_players)
        if current_cost + player["price"] > BUDGET:
            return jsonify({"error": "Budjetti ylittyy"}), 400
        profile = get_supabase().table("profiles").select("transfers_left").eq("id", request.user.id).single().execute()
        if len(current_ids) > 0 and profile.data["transfers_left"] <= 0:
            return jsonify({"error": "Ei vaihtoja jaljella"}), 400
        get_supabase().table("teams").insert({
            "user_id": request.user.id, "player_id": player_id,
            "added_at": datetime.utcnow().isoformat()
        }).execute()
        if len(current_ids) > 0:
            get_supabase().table("profiles").update({
                "transfers_left": profile.data["transfers_left"] - 1
            }).eq("id", request.user.id).execute()
        return jsonify({"message": f"{player['name']} lisatty joukkueeseen"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app.route("/api/team/remove", methods=["POST"])
@require_auth
def remove_player():
    data      = request.get_json()
    player_id = data.get("player_id")
    try:
        get_supabase().table("teams").delete().eq("user_id", request.user.id).eq("player_id", player_id).execute()
        return jsonify({"message": "Pelaaja poistettu joukkueesta"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app.route("/api/team/save", methods=["POST"])
@require_auth
def save_team_meta():
    """Tallentaa joukkueen nimen ja kapteenin – ei vahvista."""
    data       = request.get_json()
    team_name  = (data.get("name") or "").strip()
    captain_id = data.get("captain_id")
    if not team_name:
        return jsonify({"error": "Anna joukkueelle nimi"}), 400
    try:
        update = {"team_name": team_name}
        if captain_id is not None:
            update["captain_id"] = int(captain_id)
        get_supabase().table("profiles").update(update).eq("id", request.user.id).execute()
        return jsonify({"message": "Tallennettu"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app.route("/api/team/confirm", methods=["POST"])
@require_auth
def confirm_team():
    data       = request.get_json() or {}
    team_name  = (data.get("name") or "").strip()
    captain_id = data.get("captain_id")

    if not team_name:
        return jsonify({"error": "Anna joukkueelle nimi ennen vahvistusta"}), 400
    try:
        res        = get_supabase().table("teams").select("*").eq("user_id", request.user.id).execute()
        player_ids = [row["player_id"] for row in res.data]
        players    = [p for p in PLAYERS if p["id"] in player_ids]
        if len(players) != 6:
            return jsonify({"error": "Joukkueessa taytyy olla tasan 6 pelaajaa"}), 400
        for pos, limit in ROSTER_LIMITS.items():
            count = sum(1 for p in players if p["pos"] == pos)
            if count != limit:
                return jsonify({"error": f"Vaara maara {pos}-pelaajia"}), 400
        update = {
            "team_confirmed": True,
            "confirmed_at":   datetime.utcnow().isoformat(),
            "team_name":      team_name,
        }
        if captain_id is not None:
            update["captain_id"] = int(captain_id)
        get_supabase().table("profiles").update(update).eq("id", request.user.id).execute()
        return jsonify({"message": "Joukkue vahvistettu!"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 400


# ── LEAGUES ─────────────────────────────────────────────────────────────────

@app.route("/api/leagues", methods=["GET"])
def get_leagues():
    type_filter = request.args.get("type", "")
    q           = request.args.get("q", "").lower()
    try:
        query = get_supabase().table("leagues").select("*")
        if type_filter in ("public", "private"):
            query = query.eq("type", type_filter)
        res     = query.execute()
        leagues = res.data
        if q:
            leagues = [l for l in leagues if q in l["name"].lower()]
        for league in leagues:
            members = get_supabase().table("league_members").select("id").eq("league_id", league["id"]).execute()
            league["member_count"] = len(members.data)
        return jsonify(leagues), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app.route("/api/leagues", methods=["POST"])
@require_auth
def create_league():
    data        = request.get_json()
    name        = data.get("name", "").strip()
    league_type = data.get("type", "public")
    max_members = int(data.get("max_members", 20))
    if not name:
        return jsonify({"error": "Anna liigalle nimi"}), 400
    if league_type not in ("public", "private"):
        return jsonify({"error": "Virheellinen liigan tyyppi"}), 400
    if max_members < 2 or max_members > 500:
        return jsonify({"error": "Max jassenmaara taytyy olla 2-500"}), 400
    try:
        res       = get_supabase().table("leagues").insert({
            "name": name, "type": league_type, "max_members": max_members,
            "created_by": request.user.id, "created_at": datetime.utcnow().isoformat()
        }).execute()
        league_id = res.data[0]["id"]
        get_supabase().table("league_members").insert({
            "league_id": league_id, "user_id": request.user.id,
            "joined_at": datetime.utcnow().isoformat()
        }).execute()
        return jsonify({"message": "Liiga luotu!", "league_id": league_id}), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app.route("/api/leagues/<int:league_id>/join", methods=["POST"])
@require_auth
def join_league(league_id):
    try:
        league = get_supabase().table("leagues").select("*").eq("id", league_id).single().execute()
        if not league.data:
            return jsonify({"error": "Liigaa ei loydy"}), 404
        members = get_supabase().table("league_members").select("*").eq("league_id", league_id).execute()
        if len(members.data) >= league.data["max_members"]:
            return jsonify({"error": "Liiga on taynna"}), 400
        already = get_supabase().table("league_members").select("*").eq("league_id", league_id).eq("user_id", request.user.id).execute()
        if already.data:
            return jsonify({"error": "Olet jo tassa liigassa"}), 400
        get_supabase().table("league_members").insert({
            "league_id": league_id, "user_id": request.user.id,
            "joined_at": datetime.utcnow().isoformat()
        }).execute()
        return jsonify({"message": "Liittyminen onnistui!"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app.route("/api/leagues/<int:league_id>/leave", methods=["POST"])
@require_auth
def leave_league(league_id):
    try:
        get_supabase().table("league_members").delete().eq("league_id", league_id).eq("user_id", request.user.id).execute()
        return jsonify({"message": "Poistuttu liigasta"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app.route("/api/leagues/<int:league_id>/standings", methods=["GET"])
def league_standings(league_id):
    try:
        members  = get_supabase().table("league_members").select("user_id").eq("league_id", league_id).execute()
        user_ids = [m["user_id"] for m in members.data]
        standings = []
        for uid in user_ids:
            profile = get_supabase().table("profiles").select(
                "username, total_points, team_name"
            ).eq("id", uid).single().execute()
            if profile.data:
                standings.append({
                    "user_id":   uid,
                    "username":  profile.data["username"],
                    "team_name": profile.data.get("team_name") or "",
                    "points":    profile.data["total_points"],
                })
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
        memberships = get_supabase().table("league_members").select("league_id").eq("user_id", request.user.id).execute()
        league_ids  = [m["league_id"] for m in memberships.data]
        leagues     = []
        for lid in league_ids:
            league = get_supabase().table("leagues").select("*").eq("id", lid).single().execute()
            if league.data:
                members = get_supabase().table("league_members").select("id").eq("league_id", lid).execute()
                league.data["member_count"] = len(members.data)
                leagues.append(league.data)
        return jsonify(leagues), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 400


# ── POINTS ──────────────────────────────────────────────────────────────────

@app.route("/api/points/update", methods=["POST"])
def update_points():
    secret = request.headers.get("X-Admin-Secret", "")
    if secret != os.environ.get("ADMIN_SECRET", ""):
        return jsonify({"error": "Ei oikeuksia"}), 403
    data          = request.get_json()
    player_events = data.get("events", [])
    point_rules   = {
        "H":  {"goal": 4,  "assist": 2,  "plus": 1,  "minus": -1, "minor_penalty": -1, "game_misconduct": -5},
        "P":  {"goal": 6,  "assist": 4,  "plus": 2,  "minus": -2, "minor_penalty": -1, "game_misconduct": -5},
        "MV": {"win": 2,   "loss": -2,   "shutout": 8, "goal_against": -1, "minor_penalty": -1, "game_misconduct": -5},
    }
    def saves_points(saves):
        if saves <= 10:  return 1
        if saves <= 15:  return 3
        if saves <= 20:  return 5
        if saves <= 25:  return 7
        if saves <= 30:  return 9
        return 9 + ((saves - 30) // 5) * 2
    try:
        for event in player_events:
            pid    = event.get("player_id")
            player = next((p for p in PLAYERS if p["id"] == pid), None)
            if not player:
                continue
            pts   = 0
            rules = point_rules[player["pos"]]
            if player["pos"] in ("H", "P"):
                pts += rules["goal"]           * event.get("goals", 0)
                pts += rules["assist"]         * event.get("assists", 0)
                pts += rules["plus"]           * event.get("plus", 0)
                pts += rules["minus"]          * event.get("minus", 0)
                pts += rules["minor_penalty"]  * event.get("minor_penalties", 0)
                pts += rules["game_misconduct"]* event.get("game_misconducts", 0)
            elif player["pos"] == "MV":
                pts += rules["win"]            * event.get("wins", 0)
                pts += rules["loss"]           * event.get("losses", 0)
                pts += rules["shutout"]        * event.get("shutouts", 0)
                pts += rules["goal_against"]   * event.get("goals_against", 0)
                pts += saves_points(event.get("saves", 0))
                pts += rules["minor_penalty"]  * event.get("minor_penalties", 0)
                pts += rules["game_misconduct"]* event.get("game_misconducts", 0)
            get_supabase().table("player_points").insert({
                "player_id":  pid,
                "points":     pts,
                "game_date":  event.get("game_date", datetime.utcnow().date().isoformat()),
                "created_at": datetime.utcnow().isoformat()
            }).execute()
            player["points"] = player.get("points", 0) + pts
        all_users  = get_supabase().table("teams").select("user_id, player_id").execute()
        user_map   = {}
        for row in all_users.data:
            user_map.setdefault(row["user_id"], []).append(row["player_id"])
        updated_ids = [e["player_id"] for e in player_events]
        for uid, pids in user_map.items():
            gained = sum(
                next((e.get("points_gained", 0) for e in player_events if e["player_id"] == p["id"]), 0)
                for p in PLAYERS if p["id"] in pids and p["id"] in updated_ids
            )
            if gained:
                profile  = get_supabase().table("profiles").select("total_points").eq("id", uid).single().execute()
                new_total = (profile.data["total_points"] or 0) + gained
                get_supabase().table("profiles").update({"total_points": new_total}).eq("id", uid).execute()
        return jsonify({"message": "Pisteet paivitetty"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app.route("/api/points/leaderboard", methods=["GET"])
def leaderboard():
    try:
        profiles = get_supabase().table("profiles").select(
            "username, total_points, team_name"
        ).order("total_points", desc=True).limit(50).execute()
        result = [
            {"rank": i+1, "username": p["username"], "team_name": p.get("team_name",""), "points": p["total_points"]}
            for i, p in enumerate(profiles.data)
        ]
        return jsonify(result), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app.route("/api/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "version": "2.0.0"}), 200


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
