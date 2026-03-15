import streamlit as st
st.set_page_config(layout="wide")

import json
import random
import pandas as pd
import re
import unicodedata
import os

# ============================================================
# Styling
# ============================================================
st.markdown(
    """
    <style>
    [data-testid="stDataFrame"] div { font-size: 12px; }

    .overlay {
        position: fixed;
        inset: 0;
        background: rgba(0,0,0,0.55);
        z-index: 9998;
        pointer-events: none;
    }

    .modal {
        position: fixed;
        top: 50%;
        left: 50%;
        transform: translate(-50%, -50%);
        border-radius: 14px;
        padding: 22px 26px 74px 26px;
        width: min(520px, 92vw);
        z-index: 9999;
        box-shadow: 0 12px 50px rgba(0,0,0,0.55);
        pointer-events: none;
        border: 1px solid rgba(0,0,0,0.15);
        color: black;
    }

    .modal-title {
        font-size: 14px;
        opacity: 0.75;
        margin-bottom: 10px;
        text-transform: uppercase;
        letter-spacing: 0.08em;
        text-align: center;
    }

    .modal-answer {
        font-size: 30px;
        font-weight: 800;
        text-align: center;
        margin: 10px 0 6px 0;
        line-height: 1.15;
    }

    .modal-sub {
        text-align: center;
        opacity: 0.85;
        margin-bottom: 10px;
    }

    div[data-testid="answer-next-btn"] {
        position: fixed !important;
        top: calc(50% + 120px) !important;
        left: 50% !important;
        transform: translateX(-50%) !important;
        width: min(260px, 60vw) !important;
        z-index: 10000 !important;
        pointer-events: auto !important;
    }

    .lives-wrap {
        display: flex;
        flex-direction: column;
        gap: 6px;
        padding-top: 4px;
    }

    .lives-label {
        font-size: 14px;
        opacity: 0.85;
    }

    .lives-hearts {
        font-size: 26px;
        line-height: 1;
        letter-spacing: 4px;
        user-select: none;
    }

    .skip-locked-note {
        font-size: 12px;
        opacity: 0.7;
        margin-top: 6px;
        text-align: center;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# ============================================================
# Allowed team codes
# ============================================================
ALLOWED_MLB_TEAMS = {
    "TOR", "NYY", "BOS", "TBR", "BAL",
    "CLE", "DET", "KCR", "MIN", "CHW",
    "SEA", "HOU", "TEX", "ATH", "OAK", "LAA",
    "PHI", "NYM", "MIA", "ATL", "WSN",
    "MIL", "CHC", "CIN", "STL", "PIT",
    "LAD", "SDP", "SFG", "ARI", "COL",
}

ALLOWED_NBA_TEAMS = {
    "DET", "BOS", "NYK", "CLE", "ORL",
    "MIA", "TOR", "ATL", "PHI", "CHO",
    "MIL", "CHI", "BRK", "WAS", "IND",
    "OKC", "SAS", "LAL", "HOU", "DEN",
    "MIN", "PHO", "LAC", "GSW", "POR",
    "MEM", "DAL", "NOP", "UTA", "SAC",
}

ALLOWED_NFL_TEAMS = {
    "NWE", "BUF", "MIA", "NYJ",
    "PIT", "BAL", "CIN", "CLE",
    "JAX", "HOU", "IND", "TEN",
    "DEN", "LAC", "KAN", "LVR",
    "PHI", "DAL", "WAS", "NYG",
    "CHI", "GNB", "MIN", "DET",
    "CAR", "TAM", "ATL", "NOR",
    "SEA", "LAR", "SFO", "ARI",
}

# ============================================================
# Load database
# ============================================================
@st.cache_data
def load_db(path: str):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

NBA_PATH = "nba_per_game_db.json"
MLB_PATH = "mlb.json"
NFL_PATH = "nfl.json"

nba_db = load_db(NBA_PATH) if os.path.exists(NBA_PATH) else {}
mlb_db = load_db(MLB_PATH) if os.path.exists(MLB_PATH) else {}
nfl_db = load_db(NFL_PATH) if os.path.exists(NFL_PATH) else {}

# ============================================================
# Fast metadata layer
# ============================================================
def _to_float(x):
    try:
        if x is None:
            return None
        s = str(x).replace(",", "").strip()
        if s.lower() in ["", "none", "nan"]:
            return None
        return float(s)
    except:
        return None

def _to_int(x):
    try:
        f = _to_float(x)
        return None if f is None else int(f)
    except:
        return None

def parse_ip(ip_val):
    """
    BRef IP uses .1/.2 as 1/3 and 2/3 innings.
    Accepts numeric or string.
    Returns float innings (e.g., 39.2 -> 39 + 2/3).
    """
    if ip_val is None:
        return None
    s = str(ip_val).strip()
    if s.lower() in ["", "none", "nan"]:
        return None
    s = s.replace(",", "")
    try:
        if "." not in s:
            return float(s)
        whole, frac = s.split(".", 1)
        whole_i = int(whole)
        if frac == "0":
            return float(whole_i)
        if frac == "1":
            return whole_i + (1.0 / 3.0)
        if frac == "2":
            return whole_i + (2.0 / 3.0)
        return float(s)
    except:
        return None

def has_ip_column(rows):
    if not rows:
        return False
    return "IP" in rows[0]

def career_games_from_rows(rows):
    for row in rows:
        season = str(row.get("Season", ""))
        if "Yrs" in season:
            g = _to_int(row.get("G"))
            if g is not None:
                return g

    total = 0
    found = False
    for row in rows:
        season = str(row.get("Season", "")).strip()
        if re.fullmatch(r"\d{4}", season) or re.fullmatch(r"\d{4}-\d{2}", season):
            g = _to_int(row.get("G"))
            if g is not None:
                total += g
                found = True
    return total if found else None

def career_ip_from_rows(rows):
    for row in rows:
        season = str(row.get("Season", ""))
        if "Yrs" in season:
            ip = parse_ip(row.get("IP"))
            if ip is not None:
                return ip

    total = 0.0
    found = False
    for row in rows:
        season = str(row.get("Season", "")).strip()
        if re.fullmatch(r"\d{4}", season):
            ip = parse_ip(row.get("IP"))
            if ip is not None:
                total += ip
                found = True
    return total if found else None

def is_valid_nfl_position(pos: str) -> bool:
    if pos is None:
        return False
    p = str(pos).strip().upper()
    if not p:
        return False
    if p == "POS":
        return False
    if "DID NOT PLAY" in p:
        return False
    return True

def normalize_team(team: str) -> str:
    if team is None:
        return ""
    return str(team).strip().upper()

def is_allowed_team(team: str, league: str) -> bool:
    t = normalize_team(team)
    if not t:
        return False

    if league == "NBA":
        return t in ALLOWED_NBA_TEAMS
    if league == "MLB":
        return t in ALLOWED_MLB_TEAMS
    if league == "NFL":
        return t in ALLOWED_NFL_TEAMS
    return False

def extract_positions_from_rows(rows):
    positions = []
    seen = set()

    for row in rows:
        pos_raw = str(row.get("Pos", "")).strip()
        if not pos_raw or pos_raw.lower() in ["none", "nan"]:
            continue

        parts = re.split(r"[/,]+", pos_raw)
        for p in parts:
            pos = p.strip().upper()
            if not is_valid_nfl_position(pos):
                continue
            if pos not in seen:
                seen.add(pos)
                positions.append(pos)

    return positions

def extract_teams_from_rows(rows, league: str):
    teams = []
    seen = set()

    for row in rows:
        team = normalize_team(row.get("Team", ""))

        if not is_allowed_team(team, league):
            continue

        if team not in seen:
            seen.add(team)
            teams.append(team)

    return teams

@st.cache_data
def build_nba_meta(path: str, file_mtime: float) -> pd.DataFrame:
    db_local = load_db(path)
    rows_out = []
    for pid, rec in db_local.items():
        name = rec.get("name")
        rows = rec.get("per_game", [])
        g = career_games_from_rows(rows)
        teams = extract_teams_from_rows(rows, "NBA")
        rows_out.append((pid, name, g, teams))
    return pd.DataFrame(rows_out, columns=["player_id", "name", "career_games", "teams"])

@st.cache_data
def build_mlb_meta(path: str, file_mtime: float) -> pd.DataFrame:
    db_local = load_db(path)
    out = []
    for pid, rec in db_local.items():
        name = rec.get("name")
        rows = rec.get("per_game", [])
        teams = extract_teams_from_rows(rows, "MLB")
        is_pitch = has_ip_column(rows)
        if is_pitch:
            cip = career_ip_from_rows(rows)
            out.append((pid, name, "pitcher", None, cip, teams))
        else:
            cg = career_games_from_rows(rows)
            out.append((pid, name, "hitter", cg, None, teams))
    return pd.DataFrame(out, columns=["player_id", "name", "mlb_type", "career_g", "career_ip", "teams"])

@st.cache_data
def build_nfl_meta(path: str, file_mtime: float) -> pd.DataFrame:
    db_local = load_db(path)
    out = []
    for pid, rec in db_local.items():
        name = rec.get("name")
        rows = rec.get("per_game", [])
        g = career_games_from_rows(rows)
        positions = extract_positions_from_rows(rows)
        teams = extract_teams_from_rows(rows, "NFL")
        primary_pos = positions[0] if positions else ""
        out.append((pid, name, g, positions, primary_pos, teams))
    return pd.DataFrame(out, columns=["player_id", "name", "career_games", "positions", "primary_pos", "teams"])

nba_meta = build_nba_meta(NBA_PATH, os.path.getmtime(NBA_PATH)) if nba_db else pd.DataFrame(columns=["player_id", "name", "career_games", "teams"])
mlb_meta = build_mlb_meta(MLB_PATH, os.path.getmtime(MLB_PATH)) if mlb_db else pd.DataFrame(columns=["player_id", "name", "mlb_type", "career_g", "career_ip", "teams"])
nfl_meta = build_nfl_meta(NFL_PATH, os.path.getmtime(NFL_PATH)) if nfl_db else pd.DataFrame(columns=["player_id", "name", "career_games", "positions", "primary_pos", "teams"])

# ============================================================
# Helpers
# ============================================================
MAX_LIVES = 5

def strip_accents(s: str) -> str:
    if s is None:
        return ""
    s = str(s)
    s = unicodedata.normalize("NFKD", s)
    return "".join(ch for ch in s if not unicodedata.combining(ch))

def normalize_name(s: str) -> str:
    s = strip_accents(s)
    s = s.strip().lower()
    s = re.sub(r"[^a-z\s]", "", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s

def calc_df_height(n_rows: int, row_px: int = 36, header_px: int = 40, min_px: int = 140, max_px: int = 650) -> int:
    h = header_px + n_rows * row_px
    return max(min_px, min(h, max_px))

def render_lives(lives: int, max_lives: int = MAX_LIVES):
    filled = "❤️" * max(0, lives)
    empty = "🤍" * max(0, max_lives - lives)
    st.markdown(
        f"""
        <div class="lives-wrap">
          <div class="lives-label">Lives:</div>
          <div class="lives-hearts">{filled}{empty}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

def show_result_overlay(name: str, status: str):
    st.session_state.show_overlay = True
    st.session_state.overlay_name = name
    st.session_state.overlay_status = status

def show_game_over_overlay():
    st.session_state.game_over = True
    st.session_state.show_overlay = False

def get_new_pick(pool):
    if not pool:
        return None
    return random.choice(pool)

def begin_round(pool):
    pick = get_new_pick(pool)
    if pick is None:
        st.session_state.player_id = None
        st.session_state.league = None
        return

    league, pid = pick
    st.session_state.league = league
    st.session_state.player_id = pid
    st.session_state.attempts_this_player = 0
    st.session_state.had_incorrect_this_player = False
    st.session_state.feedback = ""
    st.session_state.show_overlay = False
    st.session_state.overlay_name = ""
    st.session_state.overlay_status = ""
    st.session_state.guess_choice = ""

def next_round(pool):
    st.session_state.round += 1
    begin_round(pool)

def reset_game(pool):
    st.session_state.score = 0
    st.session_state.streak = 0
    st.session_state.round = 1
    st.session_state.lives = MAX_LIVES
    st.session_state.game_over = False
    begin_round(pool)

def render_checkbox_grid(container, values, key_prefix, selected_out, filters_locked, cols_per_row=4):
    for val in values:
        key = f"{key_prefix}_{val}"
        if key not in st.session_state:
            st.session_state[key] = True

    for i in range(0, len(values), cols_per_row):
        row_values = values[i:i + cols_per_row]
        cols = container.columns(cols_per_row)

        for j, val in enumerate(row_values):
            with cols[j]:
                checked = st.checkbox(
                    val,
                    key=f"{key_prefix}_{val}",
                    disabled=filters_locked,
                )
                if checked:
                    selected_out.append(val)

# ============================================================
# Session state init
# ============================================================
if "round" not in st.session_state:
    st.session_state.score = 0
    st.session_state.streak = 0
    st.session_state.round = 1
    st.session_state.lives = MAX_LIVES
    st.session_state.game_over = False
    st.session_state.feedback = ""
    st.session_state.show_overlay = False
    st.session_state.overlay_name = ""
    st.session_state.overlay_status = ""
    st.session_state.guess_choice = ""
    st.session_state.attempts_this_player = 0
    st.session_state.had_incorrect_this_player = False

# ============================================================
# Sidebar: league selection + filters
# ============================================================
filters_locked = st.session_state.get("round", 1) > 1

st.sidebar.header("Leagues")

default_use_nba = st.session_state.get("use_nba", True)
default_use_mlb = st.session_state.get("use_mlb", bool(mlb_db))
default_use_nfl = st.session_state.get("use_nfl", bool(nfl_db))

use_nba = st.sidebar.checkbox(
    "NBA",
    value=default_use_nba,
    key="use_nba",
    disabled=(not bool(nba_db)) or filters_locked,
)

use_mlb = st.sidebar.checkbox(
    "MLB",
    value=default_use_mlb,
    key="use_mlb",
    disabled=(not bool(mlb_db)) or filters_locked,
)

use_nfl = st.sidebar.checkbox(
    "NFL",
    value=default_use_nfl,
    key="use_nfl",
    disabled=(not bool(nfl_db)) or filters_locked,
)

if not use_nba and not use_mlb and not use_nfl:
    st.sidebar.error("Select at least one league.")
    st.stop()

if filters_locked:
    st.sidebar.info("Filters are locked during an active run. Finish the game or restart to change them.")

st.sidebar.divider()

# -----------------------
# NBA Filters
# -----------------------
nba_min_games = 0
selected_nba_teams = []

if use_nba and len(nba_meta):
    st.sidebar.subheader("NBA Filters")

    nba_vals = pd.to_numeric(nba_meta["career_games"], errors="coerce").fillna(0)
    nba_median_g = int(nba_vals.median()) if len(nba_vals) else 0
    nba_max = max(0, nba_median_g)

    if "nba_games_slider" in st.session_state:
        try:
            st.session_state["nba_games_slider"] = min(int(st.session_state["nba_games_slider"]), nba_max)
        except:
            st.session_state["nba_games_slider"] = 0

    nba_min_games = st.sidebar.slider(
        "Minimum games played",
        min_value=0,
        max_value=nba_max,
        value=int(st.session_state.get("nba_games_slider", 0)),
        step=10,
        key="nba_games_slider",
        disabled=filters_locked,
    )

    all_nba_teams = sorted(ALLOWED_NBA_TEAMS)

    nba_team_expander = st.sidebar.expander("Teams", expanded=False)
    with nba_team_expander:
        render_checkbox_grid(
            container=nba_team_expander,
            values=all_nba_teams,
            key_prefix="nba_team",
            selected_out=selected_nba_teams,
            filters_locked=filters_locked,
            cols_per_row=4,
        )

# -----------------------
# MLB Filters
# -----------------------
mlb_min_games_h = 0
mlb_min_ip_p = 0.0
selected_mlb_teams = []

if use_mlb and len(mlb_meta):
    st.sidebar.subheader("MLB Filters")

    hitters = mlb_meta[mlb_meta["mlb_type"] == "hitter"].copy()
    hitters_vals = pd.to_numeric(hitters["career_g"], errors="coerce").fillna(0)
    hitters_median_g = int(hitters_vals.median()) if len(hitters_vals) else 0
    hitters_max = max(0, hitters_median_g)

    if "mlb_hitters_slider" in st.session_state:
        try:
            st.session_state["mlb_hitters_slider"] = min(int(st.session_state["mlb_hitters_slider"]), hitters_max)
        except:
            st.session_state["mlb_hitters_slider"] = 0

    mlb_min_games_h = st.sidebar.slider(
        "Hitters: minimum games played",
        min_value=0,
        max_value=hitters_max,
        value=int(st.session_state.get("mlb_hitters_slider", 0)),
        step=10,
        key="mlb_hitters_slider",
        disabled=filters_locked,
    )

    pitchers = mlb_meta[mlb_meta["mlb_type"] == "pitcher"].copy()
    pitchers_vals = pd.to_numeric(pitchers["career_ip"], errors="coerce").fillna(0.0)
    pitchers_median_ip = float(pitchers_vals.median()) if len(pitchers_vals) else 0.0
    pitchers_max = float(max(0.0, pitchers_median_ip))

    if "mlb_pitchers_slider" in st.session_state:
        try:
            st.session_state["mlb_pitchers_slider"] = min(float(st.session_state["mlb_pitchers_slider"]), pitchers_max)
        except:
            st.session_state["mlb_pitchers_slider"] = 0.0

    mlb_min_ip_p = st.sidebar.slider(
        "Pitchers: minimum innings pitched",
        min_value=0.0,
        max_value=pitchers_max,
        value=float(st.session_state.get("mlb_pitchers_slider", 0.0)),
        step=10.0,
        key="mlb_pitchers_slider",
        disabled=filters_locked,
    )

    all_mlb_teams = sorted(ALLOWED_MLB_TEAMS)

    mlb_team_expander = st.sidebar.expander("Teams", expanded=False)
    with mlb_team_expander:
        render_checkbox_grid(
            container=mlb_team_expander,
            values=all_mlb_teams,
            key_prefix="mlb_team",
            selected_out=selected_mlb_teams,
            filters_locked=filters_locked,
            cols_per_row=4,
        )

# -----------------------
# NFL Filters
# -----------------------
nfl_min_games = 0
selected_nfl_positions = []
selected_nfl_teams = []

if use_nfl and len(nfl_meta):
    st.sidebar.subheader("NFL Filters")

    nfl_vals = pd.to_numeric(nfl_meta["career_games"], errors="coerce").fillna(0)
    nfl_median_g = int(nfl_vals.median()) if len(nfl_vals) else 0
    nfl_max = max(0, nfl_median_g)

    if "nfl_games_slider" in st.session_state:
        try:
            st.session_state["nfl_games_slider"] = min(int(st.session_state["nfl_games_slider"]), nfl_max)
        except:
            st.session_state["nfl_games_slider"] = 0

    nfl_min_games = st.sidebar.slider(
        "Minimum games played",
        min_value=0,
        max_value=nfl_max,
        value=int(st.session_state.get("nfl_games_slider", 0)),
        step=10,
        key="nfl_games_slider",
        disabled=filters_locked,
    )

    all_nfl_positions = sorted(
        {
            pos
            for pos_list in nfl_meta["positions"].tolist()
            for pos in (pos_list if isinstance(pos_list, list) else [])
            if is_valid_nfl_position(pos)
        }
    )

    all_nfl_teams = sorted(ALLOWED_NFL_TEAMS)

    nfl_pos_expander = st.sidebar.expander("Positions", expanded=False)
    with nfl_pos_expander:
        render_checkbox_grid(
            container=nfl_pos_expander,
            values=all_nfl_positions,
            key_prefix="nfl_pos",
            selected_out=selected_nfl_positions,
            filters_locked=filters_locked,
            cols_per_row=4,
        )

    nfl_team_expander = st.sidebar.expander("Teams", expanded=False)
    with nfl_team_expander:
        render_checkbox_grid(
            container=nfl_team_expander,
            values=all_nfl_teams,
            key_prefix="nfl_team",
            selected_out=selected_nfl_teams,
            filters_locked=filters_locked,
            cols_per_row=4,
        )

st.sidebar.divider()
st.sidebar.header("Eligible Players")

# ============================================================
# Build eligible pool
# ============================================================
pool = []

nba_ids = []
mlb_ids = []
nfl_ids = []

if use_nba and len(nba_meta):
    nba_work = nba_meta.copy()
    nba_work["career_games_num"] = pd.to_numeric(nba_work["career_games"], errors="coerce").fillna(0).astype(int)
    nba_work = nba_work[nba_work["career_games_num"] >= int(nba_min_games)]

    if selected_nba_teams:
        nba_work = nba_work[
            nba_work["teams"].apply(
                lambda x: any(team in selected_nba_teams for team in (x if isinstance(x, list) else []))
            )
        ]

    nba_ids = nba_work["player_id"].tolist()
    pool.extend([("NBA", pid) for pid in nba_ids])
    st.sidebar.caption(f"Eligible NBA players: {len(nba_ids)}")

if use_mlb and len(mlb_meta):
    mlb_work = mlb_meta.copy()

    if selected_mlb_teams:
        mlb_work = mlb_work[
            mlb_work["teams"].apply(
                lambda x: any(team in selected_mlb_teams for team in (x if isinstance(x, list) else []))
            )
        ]

    hitters = mlb_work[mlb_work["mlb_type"] == "hitter"].copy()
    hitters_g = pd.to_numeric(hitters["career_g"], errors="coerce").fillna(0).astype(int)
    hitter_ids = hitters.loc[hitters_g >= int(mlb_min_games_h), "player_id"].tolist()

    pitchers = mlb_work[mlb_work["mlb_type"] == "pitcher"].copy()
    pitchers_ip = pd.to_numeric(pitchers["career_ip"], errors="coerce").fillna(0.0).astype(float)
    pitcher_ids = pitchers.loc[pitchers_ip >= float(mlb_min_ip_p), "player_id"].tolist()

    mlb_ids = hitter_ids + pitcher_ids
    pool.extend([("MLB", pid) for pid in mlb_ids])

    st.sidebar.caption(f"Eligible MLB hitters: {len(hitter_ids)}")
    st.sidebar.caption(f"Eligible MLB pitchers: {len(pitcher_ids)}")
    st.sidebar.caption(f"Eligible MLB total: {len(mlb_ids)}")

if use_nfl and len(nfl_meta):
    nfl_work = nfl_meta.copy()
    nfl_work["career_games_num"] = pd.to_numeric(nfl_work["career_games"], errors="coerce").fillna(0).astype(int)
    nfl_work = nfl_work[nfl_work["career_games_num"] >= int(nfl_min_games)]

    if selected_nfl_positions:
        nfl_work = nfl_work[
            nfl_work["positions"].apply(
                lambda x: any(pos in selected_nfl_positions for pos in (x if isinstance(x, list) else []))
            )
        ]

    if selected_nfl_teams:
        nfl_work = nfl_work[
            nfl_work["teams"].apply(
                lambda x: any(team in selected_nfl_teams for team in (x if isinstance(x, list) else []))
            )
        ]

    nfl_ids = nfl_work["player_id"].tolist()
    pool.extend([("NFL", pid) for pid in nfl_ids])

    st.sidebar.caption(f"Eligible NFL players: {len(nfl_ids)}")

if not pool:
    st.sidebar.error("No players match your current filters.")
    st.stop()

# Ensure a valid current player exists
if "player_id" not in st.session_state or "league" not in st.session_state:
    begin_round(pool)
else:
    current_tuple = (st.session_state.get("league"), st.session_state.get("player_id"))
    if current_tuple not in pool:
        begin_round(pool)

if not st.session_state.get("player_id") or not st.session_state.get("league"):
    st.sidebar.error("No players match your current filters.")
    st.stop()

# ============================================================
# Autocomplete options
# ============================================================
@st.cache_data
def build_name_maps_from_ids(nba_meta: pd.DataFrame, mlb_meta: pd.DataFrame, nfl_meta: pd.DataFrame):
    nba_map = {}
    mlb_map = {}
    nfl_map = {}

    if len(nba_meta):
        nba_map = dict(zip(nba_meta["player_id"].astype(str), nba_meta["name"].astype(str)))
    if len(mlb_meta):
        mlb_map = dict(zip(mlb_meta["player_id"].astype(str), mlb_meta["name"].astype(str)))
    if len(nfl_meta):
        nfl_map = dict(zip(nfl_meta["player_id"].astype(str), nfl_meta["name"].astype(str)))

    return nba_map, mlb_map, nfl_map

NBA_ID_TO_NAME, MLB_ID_TO_NAME, NFL_ID_TO_NAME = build_name_maps_from_ids(nba_meta, mlb_meta, nfl_meta)

def build_display_opts_from_pool(pool_local):
    display_to_name = {}
    opts = []

    for lg, pid in pool_local:
        if lg == "NBA":
            raw = NBA_ID_TO_NAME.get(str(pid), "")
        elif lg == "MLB":
            raw = MLB_ID_TO_NAME.get(str(pid), "")
        else:
            raw = NFL_ID_TO_NAME.get(str(pid), "")

        n_clean = strip_accents(raw)
        disp = f"{n_clean} ({lg})"

        if disp not in display_to_name:
            display_to_name[disp] = n_clean
            opts.append(disp)

    return sorted(opts), display_to_name

ALL_DISPLAY_OPTS, DISPLAY_TO_NAME = build_display_opts_from_pool(pool)

# ============================================================
# Current record
# ============================================================
league = st.session_state.league
player_id = st.session_state.player_id

if league == "NBA":
    record = nba_db[player_id]
elif league == "MLB":
    record = mlb_db[player_id]
else:
    record = nfl_db[player_id]

answer_name_raw = record.get("name", "")
answer_name = strip_accents(answer_name_raw)

df = pd.DataFrame(record.get("per_game", []))
df = df.replace("Did not play - other pro league", "Other pro league")
df = df.replace("None", pd.NA).dropna(how="all")
df = df.reset_index(drop=True)
df_height = calc_df_height(len(df))

# ============================================================
# UI
# ============================================================
st.title("🏀⚾🏈 Stathead Game")

c1, c2, c3, c4, c5 = st.columns([1, 1, 1, 1, 1.4])
c1.metric("League", league)
c2.metric("Round", st.session_state.round)
c3.metric("Score", st.session_state.score)
c4.metric("Streak", st.session_state.streak)
with c5:
    render_lives(st.session_state.lives, MAX_LIVES)

st.dataframe(df, use_container_width=True, height=df_height, hide_index=True)

# ============================================================
# GAME OVER overlay
# ============================================================
if st.session_state.game_over:
    rounds_played = max(1, int(st.session_state.round))
    score = int(st.session_state.score)
    pct_correct = (score / rounds_played) * 100.0

    st.markdown('<div class="overlay"></div>', unsafe_allow_html=True)
    st.markdown(
        f"""
        <div class="modal" style="background: rgba(255, 255, 255, 0.98);">
          <div class="modal-title">Game Over</div>
          <div class="modal-answer">Final Score: {score}</div>
          <div class="modal-sub">Accuracy: {pct_correct:.1f}% ({score}/{rounds_played})</div>
          <div class="modal-sub">You ran out of lives.</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    btn_holder = st.container()
    btn_holder.markdown('<div data-testid="answer-next-btn">', unsafe_allow_html=True)
    if st.button("Play Again", use_container_width=True):
        reset_game(pool)
        st.rerun()
    btn_holder.markdown("</div>", unsafe_allow_html=True)
    st.stop()

# ============================================================
# Answer/Correct overlay
# ============================================================
if st.session_state.show_overlay:
    if st.session_state.overlay_status == "correct":
        bg = "rgba(46, 255, 12, 0.97)"
        title = "Correct"
        sub = "Nice. Click Next Player to continue."
    else:
        bg = "rgba(255, 53, 82, 0.97)"
        title = "Answer"
        sub = "Click Next Player to continue."

    st.markdown('<div class="overlay"></div>', unsafe_allow_html=True)
    st.markdown(
        f"""
        <div class="modal" style="background: {bg};">
          <div class="modal-title">{title}</div>
          <div class="modal-answer">{st.session_state.overlay_name}</div>
          <div class="modal-sub">{sub}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    btn_holder = st.container()
    btn_holder.markdown('<div data-testid="answer-next-btn">', unsafe_allow_html=True)
    if st.button("Next Player", use_container_width=True):
        next_round(pool)
        st.rerun()
    btn_holder.markdown("</div>", unsafe_allow_html=True)

    st.stop()

# ============================================================
# Controls
# ============================================================
guess_display = st.selectbox(
    "Guess the player (type to search)",
    options=[""] + ALL_DISPLAY_OPTS,
    index=0,
    key="guess_choice",
)

skip_allowed = bool(st.session_state.had_incorrect_this_player)
skip_label = "Skip" if skip_allowed else "🔒 Skip"

colA, colB = st.columns(2)
submit = colA.button("Submit Guess", use_container_width=True)
skip = colB.button(skip_label, use_container_width=True, disabled=not skip_allowed)

if not skip_allowed:
    colB.markdown('<div class="skip-locked-note">Unlocks after 1 wrong guess</div>', unsafe_allow_html=True)

if submit:
    if not guess_display:
        st.session_state.feedback = "Pick a name from the dropdown 🙂"
        st.rerun()

    st.session_state.attempts_this_player += 1
    guess_name = DISPLAY_TO_NAME.get(guess_display, guess_display)

    if normalize_name(guess_name) == normalize_name(answer_name):
        st.session_state.score += 1
        st.session_state.streak += 1
        show_result_overlay(answer_name, "correct")
        st.rerun()
    else:
        st.session_state.lives -= 1
        st.session_state.streak = 0
        st.session_state.had_incorrect_this_player = True

        if st.session_state.lives <= 0:
            show_game_over_overlay()
            st.rerun()
        else:
            st.session_state.feedback = f"❌ Incorrect. {st.session_state.lives} lives remaining."
            st.rerun()

if skip:
    st.session_state.streak = 0
    show_result_overlay(answer_name, "answer")
    st.rerun()

if st.session_state.feedback:
    st.write(st.session_state.feedback)

