import argparse
import copy
import getpass
import json
import os
import secrets
import threading
import traceback
import zipfile
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit
from xml.sax.saxutils import escape


ROOT = Path(__file__).resolve().parent
PUBLIC = ROOT / "public"
EMPTY_STATE = {
    "players": [],
    "matches": [],
    "historicalMatchCount": 0,
    "historicalStats": {},
    "lastUpdated": None,
}
STAT_FIELDS = ("appearances", "goals", "assists", "ownGoals", "mvp", "wins", "losses", "draws")
INITIAL_HISTORICAL_MATCH_COUNT = 8


def new_statistics():
    return dict.fromkeys(STAT_FIELDS, 0)


def historical_statistics(state):
    stored = state.get("historicalStats", {})
    return {
        str(player["id"]): {
            field: int(stored.get(str(player["id"]), {}).get(field, 0))
            for field in STAT_FIELDS
        }
        for player in state["players"]
    }


def player_statistics(state):
    statistics = historical_statistics(state)
    for match in state["matches"]:
        score_a = int(match["scoreA"])
        score_b = int(match["scoreB"])
        for entry in match["entries"]:
            stats = statistics.get(str(entry["playerId"]))
            if stats is None:
                continue
            stats["appearances"] += 1
            stats["goals"] += int(entry["goals"])
            stats["assists"] += int(entry["assists"])
            stats["ownGoals"] += int(entry["ownGoals"])
            if entry["mvp"]:
                stats["mvp"] += 1
            if score_a == score_b:
                stats["draws"] += 1
            elif (score_a > score_b and entry["team"] == "A") or (
                score_b > score_a and entry["team"] == "B"
            ):
                stats["wins"] += 1
            else:
                stats["losses"] += 1
    for stats in statistics.values():
        stats["totalScore"] = 3 * stats["wins"] + 2 * stats["mvp"] + stats["draws"]
    return statistics


def client_data(state):
    statistics = player_statistics(state)
    historical = historical_statistics(state)
    players_by_id = {str(player["id"]): player for player in state["players"]}
    players = [
        {
            "id": player["id"],
            "firstName": player["firstName"],
            "lastName": player["lastName"],
            "statistics": statistics[str(player["id"])],
            "historicalStatistics": historical[str(player["id"])],
        }
        for player in state["players"]
    ]
    matches = []
    for match in state["matches"]:
        entries = []
        for entry in match["entries"]:
            player = players_by_id.get(str(entry["playerId"]))
            name = (
                "{} {}".format(player["firstName"], player["lastName"])
                if player
                else "Giocatore rimosso"
            )
            entries.append(
                {
                    "playerId": entry["playerId"],
                    "playerName": name,
                    "team": entry["team"],
                    "goals": int(entry["goals"]),
                    "assists": int(entry["assists"]),
                    "ownGoals": int(entry["ownGoals"]),
                    "mvp": bool(entry["mvp"]),
                }
            )
        matches.append(
            {
                "id": match["id"],
                "date": match["date"],
                "scoreA": int(match["scoreA"]),
                "scoreB": int(match["scoreB"]),
                "entries": entries,
            }
        )
    return {
        "players": players,
        "matches": matches,
        "historicalMatchCount": int(state.get("historicalMatchCount", 0)),
        "lastUpdated": state["lastUpdated"],
    }


def excel_column(number):
    name = ""
    while number:
        number, remainder = divmod(number - 1, 26)
        name = chr(65 + remainder) + name
    return name


def worksheet_xml(rows):
    cells = []
    for row_index, row in enumerate(rows, 1):
        row_cells = []
        for column_index, value in enumerate(row, 1):
            reference = "{}{}".format(excel_column(column_index), row_index)
            if isinstance(value, bool):
                row_cells.append(
                    '<c r="{}" t="b"><v>{}</v></c>'.format(reference, 1 if value else 0)
                )
            elif isinstance(value, (int, float)):
                row_cells.append('<c r="{}"><v>{}</v></c>'.format(reference, value))
            else:
                text = "" if value is None else str(value)
                row_cells.append(
                    '<c r="{}" t="inlineStr"><is><t xml:space="preserve">{}</t>'
                    "</is></c>".format(reference, escape(text))
                )
        cells.append('<row r="{}">{}</row>'.format(row_index, "".join(row_cells)))
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        "<sheetData>{}</sheetData></worksheet>".format("".join(cells))
    )


def write_workbook(path, state):
    players = state["players"]
    matches = state["matches"]
    statistics = player_statistics(state)
    summary_rows = [
        ["Nome", "Cognome", "Presenze", "Gol", "Assist", "Autogol", "MVP", "Vittorie", "Sconfitte", "Pareggi", "Punteggio totale"]
    ]
    for player in players:
        stats = statistics[str(player["id"])]
        summary_rows.append(
            [
                player["firstName"],
                player["lastName"],
                stats["appearances"],
                stats["goals"],
                stats["assists"],
                stats["ownGoals"],
                stats["mvp"],
                stats["wins"],
                stats["losses"],
                stats["draws"],
                stats["totalScore"],
            ]
        )

    match_rows = [["Data", "Risultato Squadra A", "Risultato Squadra B"]]
    if state.get("historicalMatchCount", 0):
        match_rows.append(
            [
                "Partite pregresse aggregate",
                "",
                "{} partite senza dettaglio".format(state["historicalMatchCount"]),
            ]
        )
    detail_rows = [["Data", "Giocatore", "Squadra", "Gol", "Assist", "Autogol", "MVP"]]
    players_by_id = {str(player["id"]): player for player in players}
    for match in matches:
        match_rows.append([match["date"], int(match["scoreA"]), int(match["scoreB"])])
        for entry in match["entries"]:
            player = players_by_id.get(str(entry["playerId"]))
            name = (
                "{} {}".format(player["firstName"], player["lastName"])
                if player
                else "Giocatore rimosso"
            )
            detail_rows.append(
                [
                    match["date"],
                    name,
                    "Squadra {}".format(entry["team"]),
                    int(entry["goals"]),
                    int(entry["assists"]),
                    int(entry["ownGoals"]),
                    bool(entry["mvp"]),
                ]
            )

    content_types = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
        '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        '<Override PartName="/xl/worksheets/sheet2.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        '<Override PartName="/xl/worksheets/sheet3.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        "</Types>"
    )
    root_rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
        "</Relationships>"
    )
    workbook = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        '<sheets><sheet name="Statistiche" sheetId="1" r:id="rId1"/>'
        '<sheet name="Partite" sheetId="2" r:id="rId2"/>'
        '<sheet name="Dettaglio" sheetId="3" r:id="rId3"/></sheets></workbook>'
    )
    workbook_rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>'
        '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet2.xml"/>'
        '<Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet3.xml"/>'
        "</Relationships>"
    )
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", content_types)
        archive.writestr("_rels/.rels", root_rels)
        archive.writestr("xl/workbook.xml", workbook)
        archive.writestr("xl/_rels/workbook.xml.rels", workbook_rels)
        archive.writestr("xl/worksheets/sheet1.xml", worksheet_xml(summary_rows))
        archive.writestr("xl/worksheets/sheet2.xml", worksheet_xml(match_rows))
        archive.writestr("xl/worksheets/sheet3.xml", worksheet_xml(detail_rows))


class App:
    def __init__(self, data_directory, admin_password):
        self.data_directory = Path(data_directory).resolve()
        self.data_directory.mkdir(parents=True, exist_ok=True)
        self.json_path = self.data_directory / "partite.json"
        self.excel_path = self.data_directory / "statistiche_partite.xlsx"
        self.admin_password = admin_password
        self.tokens = set()
        self.lock = threading.RLock()
        existing_data = self.json_path.exists()
        if existing_data:
            raw_state = self.json_path.read_text(encoding="utf-8")
            self.state = json.loads(raw_state) if raw_state.strip() else copy.deepcopy(EMPTY_STATE)
        else:
            self.state = copy.deepcopy(EMPTY_STATE)
        if not isinstance(self.state, dict):
            raise ValueError("Il file dei dati deve contenere un oggetto JSON.")
        self.state.setdefault("players", [])
        self.state.setdefault("matches", [])
        self.state.setdefault("lastUpdated", None)
        if "historicalMatchCount" not in self.state:
            self.state["historicalMatchCount"] = (
                INITIAL_HISTORICAL_MATCH_COUNT if existing_data and self.state["players"] else 0
            )
        self.state.setdefault("historicalStats", {})
        if not isinstance(self.state["players"], list) or not isinstance(self.state["matches"], list):
            raise ValueError("Il file dei dati contiene un formato non valido.")
        if not isinstance(self.state["historicalStats"], dict):
            raise ValueError("I totali pregressi nel file dei dati non sono validi.")

    def save_state(self, candidate):
        candidate["lastUpdated"] = (
            datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
        )
        json_temp = self.json_path.with_name(self.json_path.name + ".tmp")
        excel_temp = self.excel_path.with_name(self.excel_path.name + ".tmp")
        try:
            json_temp.write_text(
                json.dumps(candidate, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            write_workbook(excel_temp, candidate)
            os.replace(json_temp, self.json_path)
            os.replace(excel_temp, self.excel_path)
        except Exception:
            for path in (json_temp, excel_temp):
                try:
                    path.unlink()
                except FileNotFoundError:
                    pass
            raise


def parse_non_negative_integer(value):
    if isinstance(value, bool):
        raise ValueError("Il valore deve essere un numero intero non negativo.")
    number = int(str(value).strip())
    if number < 0:
        raise ValueError("Il valore deve essere un numero intero non negativo.")
    return number


def make_handler(app):
    class RequestHandler(BaseHTTPRequestHandler):
        def send_json(self, status, value):
            body = json.dumps(value, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def read_json(self):
            length = int(self.headers.get("Content-Length", "0"))
            return json.loads(self.rfile.read(length).decode("utf-8"))

        def is_admin(self):
            token = self.headers.get("X-Admin-Token", "")
            return bool(token) and token in app.tokens

        def send_static(self, relative_path):
            file_path = PUBLIC / relative_path
            if not file_path.is_file():
                self.send_json(404, {"error": "Risorsa non trovata."})
                return
            content_types = {
                ".html": "text/html; charset=utf-8",
                ".css": "text/css; charset=utf-8",
                ".js": "text/javascript; charset=utf-8",
            }
            body = file_path.read_bytes()
            self.send_response(200)
            self.send_header(
                "Content-Type", content_types.get(file_path.suffix, "application/octet-stream")
            )
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            try:
                with app.lock:
                    path = urlsplit(self.path).path
                    if path == "/api/data":
                        self.send_json(200, client_data(app.state))
                    elif path == "/":
                        self.send_static("index.html")
                    elif path in ("/app.js", "/style.css"):
                        self.send_static(path.lstrip("/"))
                    else:
                        self.send_json(404, {"error": "Risorsa non trovata."})
            except Exception as error:
                self.report_failure(error)

        def do_POST(self):
            try:
                with app.lock:
                    path = urlsplit(self.path).path
                    if path == "/api/login":
                        body = self.read_json()
                        if not isinstance(body, dict) or body.get("password") != app.admin_password:
                            self.send_json(401, {"error": "Password non corretta."})
                            return
                        token = secrets.token_hex(16)
                        app.tokens.add(token)
                        self.send_json(200, {"token": token})
                        return

                    if path not in ("/api/players", "/api/matches", "/api/historical"):
                        self.send_json(404, {"error": "Risorsa non trovata."})
                        return
                    if not self.is_admin():
                        self.send_json(401, {"error": "Accesso amministratore richiesto."})
                        return
                    body = self.read_json()
                    if not isinstance(body, dict):
                        self.send_json(400, {"error": "Richiesta non valida."})
                        return
                    if path == "/api/players":
                        self.add_player(body)
                    elif path == "/api/historical":
                        self.save_historical_totals(body)
                    else:
                        self.add_match(body)
            except Exception as error:
                self.report_failure(error)

        def do_PUT(self):
            try:
                with app.lock:
                    path = urlsplit(self.path).path
                    match_prefix = "/api/matches/"
                    if not path.startswith(match_prefix) or not path[len(match_prefix):]:
                        self.send_json(404, {"error": "Risorsa non trovata."})
                        return
                    if not self.is_admin():
                        self.send_json(401, {"error": "Accesso amministratore richiesto."})
                        return
                    body = self.read_json()
                    if not isinstance(body, dict):
                        self.send_json(400, {"error": "Richiesta non valida."})
                        return
                    self.update_match(body, unquote(path[len(match_prefix):]))
            except Exception as error:
                self.report_failure(error)

        def save_historical_totals(self, body):
            try:
                match_count = parse_non_negative_integer(body.get("matchCount"))
            except (TypeError, ValueError):
                self.send_json(
                    400, {"error": "Il numero di partite pregresse deve essere un intero non negativo."}
                )
                return

            submitted_players = body.get("players")
            if not isinstance(submitted_players, list):
                self.send_json(400, {"error": "I totali per giocatore non sono validi."})
                return

            known_players = {str(player["id"]) for player in app.state["players"]}
            historical = {}
            try:
                for player in submitted_players:
                    if not isinstance(player, dict):
                        raise ValueError("I totali per giocatore non sono validi.")
                    player_id = str(player.get("playerId") or "")
                    if player_id not in known_players:
                        raise ValueError("Giocatore non valido nei totali pregressi.")
                    if player_id in historical:
                        raise ValueError("Un giocatore è presente più di una volta nei totali.")
                    historical[player_id] = {
                        field: parse_non_negative_integer(player.get(field))
                        for field in STAT_FIELDS
                    }
                    stats = historical[player_id]
                    if stats["appearances"] != stats["wins"] + stats["losses"] + stats["draws"]:
                        player_name = next(
                            "{} {}".format(item["firstName"], item["lastName"])
                            for item in app.state["players"]
                            if str(item["id"]) == player_id
                        )
                        raise ValueError(
                            "Le presenze di {} devono coincidere con vittorie, sconfitte e pareggi.".format(
                                player_name
                            )
                        )
            except (TypeError, ValueError) as error:
                self.send_json(400, {"error": str(error)})
                return

            if set(historical) != known_players:
                self.send_json(
                    400, {"error": "Inserisci i totali pregressi per tutti i giocatori."}
                )
                return

            candidate = copy.deepcopy(app.state)
            candidate["historicalMatchCount"] = match_count
            candidate["historicalStats"] = historical
            app.save_state(candidate)
            app.state = candidate
            self.send_json(200, client_data(app.state))

        def add_player(self, body):
            first_name = str(body.get("firstName") or "").strip()
            last_name = str(body.get("lastName") or "").strip()
            if not first_name or not last_name:
                self.send_json(400, {"error": "Nome e cognome sono obbligatori."})
                return
            if any(
                player["firstName"] == first_name and player["lastName"] == last_name
                for player in app.state["players"]
            ):
                self.send_json(409, {"error": "Questo giocatore è già presente."})
                return
            candidate = copy.deepcopy(app.state)
            candidate["players"].append(
                {
                    "id": secrets.token_hex(16),
                    "firstName": first_name,
                    "lastName": last_name,
                }
            )
            app.save_state(candidate)
            app.state = candidate
            self.send_json(201, client_data(app.state))

        def add_match(self, body):
            self.save_match(body)

        def update_match(self, body, match_id):
            self.save_match(body, match_id)

        def save_match(self, body, match_id=None):
            match_index = None
            if match_id is not None:
                match_index = next(
                    (
                        index for index, match in enumerate(app.state["matches"])
                        if match["id"] == match_id
                    ),
                    None,
                )
                if match_index is None:
                    self.send_json(404, {"error": "Partita non trovata."})
                    return

            date = body.get("date")
            try:
                parsed_date = datetime.strptime(str(date), "%Y-%m-%d")
                if parsed_date.strftime("%Y-%m-%d") != date:
                    raise ValueError
            except (TypeError, ValueError):
                self.send_json(400, {"error": "La data della partita non è valida."})
                return
            try:
                score_a = parse_non_negative_integer(body.get("scoreA"))
                score_b = parse_non_negative_integer(body.get("scoreB"))
            except (TypeError, ValueError):
                self.send_json(
                    400, {"error": "Inserisci un risultato valido (numeri non negativi)."}
                )
                return
            entries = body.get("entries")
            if not isinstance(entries, list) or not entries:
                self.send_json(400, {"error": "Seleziona almeno un giocatore presente."})
                return
            if sum(1 for entry in entries if isinstance(entry, dict) and entry.get("mvp")) > 1:
                self.send_json(
                    400, {"error": "È possibile assegnare un solo MVP per partita."}
                )
                return

            players_by_id = {str(player["id"]): player for player in app.state["players"]}
            seen = set()
            clean_entries = []
            try:
                for entry in entries:
                    if not isinstance(entry, dict):
                        raise ValueError("Giocatore non valido.")
                    player_id = str(entry.get("playerId") or "")
                    if player_id not in players_by_id:
                        raise ValueError("Giocatore non valido.")
                    if player_id in seen:
                        raise ValueError("Un giocatore non può essere inserito più di una volta.")
                    seen.add(player_id)
                    team = entry.get("team")
                    if team not in ("A", "B"):
                        raise ValueError("Seleziona una squadra valida per ogni giocatore.")
                    values = [
                        parse_non_negative_integer(entry.get(field))
                        for field in ("goals", "assists", "ownGoals")
                    ]
                    clean_entries.append(
                        {
                            "playerId": player_id,
                            "team": team,
                            "goals": values[0],
                            "assists": values[1],
                            "ownGoals": values[2],
                            "mvp": bool(entry.get("mvp")),
                        }
                    )
            except (TypeError, ValueError) as error:
                self.send_json(400, {"error": str(error)})
                return

            candidate = copy.deepcopy(app.state)
            match = {
                "id": match_id or secrets.token_hex(16),
                "date": parsed_date.strftime("%Y-%m-%d"),
                "scoreA": score_a,
                "scoreB": score_b,
                "entries": clean_entries,
            }
            if match_index is None:
                candidate["matches"].append(match)
            else:
                candidate["matches"][match_index] = match
            app.save_state(candidate)
            app.state = candidate
            self.send_json(200 if match_id is not None else 201, client_data(app.state))

        def report_failure(self, error):
            traceback.print_exception(type(error), error, error.__traceback__)
            try:
                self.send_json(
                    500, {"error": "Errore durante l'elaborazione della richiesta."}
                )
            except OSError:
                pass

        def log_message(self, format_string, *args):
            print("{} - {}".format(self.address_string(), format_string % args))

    return RequestHandler


def main():
    parser = argparse.ArgumentParser(description="Server locale dell'app Tabellino.")
    parser.add_argument("--listen-url", default="http://localhost:8765/")
    parser.add_argument("--data-directory", default=str(ROOT / "data"))
    args = parser.parse_args()

    password = os.environ.get("FOOTBALL_ADMIN_PASSWORD")
    if not password or not password.strip():
        password = getpass.getpass("Imposta la password amministratore: ")
    if not password or not password.strip():
        parser.error("La password amministratore non può essere vuota.")

    parsed_url = urlsplit(args.listen_url)
    if parsed_url.scheme != "http" or not parsed_url.hostname or not parsed_url.port:
        parser.error("--listen-url deve essere un URL HTTP con host e porta, ad esempio http://localhost:8765/")
    host = "" if parsed_url.hostname in ("+", "*") else parsed_url.hostname
    app = App(args.data_directory, password)
    server = ThreadingHTTPServer((host, parsed_url.port), make_handler(app))
    print("App attiva su {}".format(args.listen_url))
    print("File Excel: {}".format(app.excel_path))
    print("Premi Ctrl+C per arrestare.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nArresto del server.")
    finally:
        server.server_close()

def dispatch_request(app, method, raw_path, headers, body_bytes):
    path = urlsplit(raw_path).path
    method = method.upper()
    norm_headers = {k.lower(): v for k, v in headers.items()}

    def json_response(status, payload):
        raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        return status, [("Content-Type", "application/json; charset=utf-8")], raw

    def static_response(rel_name):
        file_path = (PUBLIC / rel_name).resolve()
        if PUBLIC.resolve() not in file_path.parents or not file_path.is_file():
            return json_response(404, {"error": "Risorsa non trovata."})
        mime_types = {
            ".html": "text/html; charset=utf-8",
            ".css": "text/css; charset=utf-8",
            ".js": "text/javascript; charset=utf-8",
        }
        ctype = mime_types.get(file_path.suffix, "application/octet-stream")
        return 200, [("Content-Type", ctype)], file_path.read_bytes()

    try:
        with app.lock:
            if method == "GET":
                if path == "/api/data":
                    return json_response(200, client_data(app.state))
                if path == "/":
                    return static_response("index.html")
                if path in ("/app.js", "/style.css"):
                    return static_response(path.lstrip("/"))
                return json_response(404, {"error": "Risorsa non trovata."})

            if method == "POST":
                if path == "/api/login":
                    data = json.loads(body_bytes.decode("utf-8"))
                    if not isinstance(data, dict) or data.get("password") != app.admin_password:
                        return json_response(401, {"error": "Password non corretta."})
                    token = secrets.token_hex(16)
                    app.tokens.add(token)
                    return json_response(200, {"token": token})

                if path not in ("/api/players", "/api/matches", "/api/historical"):
                    return json_response(404, {"error": "Risorsa non trovata."})

                token = norm_headers.get("x-admin-token", "")
                if not token or token not in app.tokens:
                    return json_response(401, {"error": "Accesso amministratore richiesto."})

                data = json.loads(body_bytes.decode("utf-8"))
                if not isinstance(data, dict):
                    return json_response(400, {"error": "Richiesta non valida."})

                captured = {}
                helper_cls = make_handler(app)
                handler_obj = object.__new__(helper_cls)
                handler_obj.send_json = lambda status, value: captured.update(
                    {"resp": json_response(status, value)}
                )

                if path == "/api/players":
                    handler_obj.add_player(data)
                elif path == "/api/historical":
                    handler_obj.save_historical_totals(data)
                elif path == "/api/matches":
                    handler_obj.add_match(data)

                return captured.get(
                    "resp", json_response(500, {"error": "Errore imprevisto."})
                )

            if method == "PUT":
                match_prefix = "/api/matches/"
                if not path.startswith(match_prefix) or not path[len(match_prefix):]:
                    return json_response(404, {"error": "Risorsa non trovata."})

                token = norm_headers.get("x-admin-token", "")
                if not token or token not in app.tokens:
                    return json_response(401, {"error": "Accesso amministratore richiesto."})

                data = json.loads(body_bytes.decode("utf-8"))
                if not isinstance(data, dict):
                    return json_response(400, {"error": "Richiesta non valida."})

                captured = {}
                helper_cls = make_handler(app)
                handler_obj = object.__new__(helper_cls)
                handler_obj.send_json = lambda status, value: captured.update(
                    {"resp": json_response(status, value)}
                )

                match_id = unquote(path[len(match_prefix):])
                handler_obj.update_match(data, match_id)

                return captured.get(
                    "resp", json_response(500, {"error": "Errore imprevisto."})
                )

            return json_response(405, {"error": "Metodo non consentito."})

    except Exception as error:
        traceback.print_exception(type(error), error, error.__traceback__)
        return json_response(500, {"error": "Errore durante l'elaborazione della richiesta."})


def create_wsgi_app(data_directory, admin_password):
    app_instance = App(data_directory, admin_password)

    def application(environ, start_response):
        method = environ.get("REQUEST_METHOD", "GET")
        path_info = environ.get("PATH_INFO", "/")
        query_string = environ.get("QUERY_STRING", "")
        full_path = f"{path_info}?{query_string}" if query_string else path_info

        try:
            length = int(environ.get("CONTENT_LENGTH") or "0")
        except ValueError:
            length = 0
        body_bytes = environ["wsgi.input"].read(length) if length > 0 else b""

        headers = {}
        for key, value in environ.items():
            if key.startswith("HTTP_"):
                header_name = key[5:].replace("_", "-").lower()
                headers[header_name] = value

        status, resp_headers, body = dispatch_request(
            app_instance, method, full_path, headers, body_bytes
        )
        status_text = {
            200: "200 OK",
            201: "201 Created",
            400: "400 Bad Request",
            401: "401 Unauthorized",
            404: "404 Not Found",
            405: "405 Method Not Allowed",
            409: "409 Conflict",
            500: "500 Internal Server Error",
        }.get(status, f"{status} Status")

        final_headers = list(resp_headers) + [("Content-Length", str(len(body)))]
        start_response(status_text, final_headers)
        return [body]

    return application

if __name__ == "__main__":
    main()
