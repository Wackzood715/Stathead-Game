import streamlit as st
st.set_page_config(layout="wide")

import json
import random
import pandas as pd
import re
import unicodedata
import os

# -----------------------
# Styling
# -----------------------
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
        top: calc(50% + 110px) !important;
        left: 50% !important;
        transform: translateX(-50%) !important;
        width: min(260px, 60vw) !important;
        z-index: 10000 !important;
        pointer-events: auto !important;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# -----------------------
# Load database
# -----------------------
@st.cache_data
def load_db(path: str):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

NBA_PATH = "nba_per_game_db.json"
MLB_PATH = "mlb.json"

nba_db = load_db(NBA_PATH) if os.path.exists(NBA_PATH) else {}
mlb_db = load_db(MLB_PATH) if os.path.exists(MLB_PATH) else {}

# -----------------------
# Fast metadata layer (speeds up filtering + list building)
# -----------------------
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
    # Prefer 'Yrs' summary
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
    # Prefer 'Yrs' summary
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

@st.cache_data
def build_nba_meta(path: str, file_mtime: float) -> pd.DataFrame:
    db_local = load_db(path)
    rows_out = []
    for pid, rec in db_local.items():
        name = rec.get("name")
        g = career_games_from_rows(rec.get("per_game", []))
        rows_out.append((pid, name, g))
    return pd.DataFrame(rows_out, columns=["player_id", "name", "career_games"])

@st.cache_data
def build_mlb_meta(path: str, file_mtime: float) -> pd.DataFrame:
    db_local = load_db(path)
    out = []
    for pid, rec in db_local.items():
        name = rec.get("name")
        rows = rec.get("per_game", [])
        is_pitch = has_ip_column(rows)
        if is_pitch:
            cip = career_ip_from_rows(rows)
            out.append((pid, name, "pitcher", None, cip))
        else:
            cg = career_games_from_rows(rows)
            out.append((pid, name, "hitter", cg, None))
    return pd.DataFrame(out, columns=["player_id", "name", "mlb_type", "career_g", "career_ip"])

nba_meta = build_nba_meta(NBA_PATH, os.path.getmtime(NBA_PATH)) if nba_db else pd.DataFrame(columns=["player_id","name","career_games"])
mlb_meta = build_mlb_meta(MLB_PATH, os.path.getmtime(MLB_PATH)) if mlb_db else pd.DataFrame(columns=["player_id","name","mlb_type","career_g","career_ip"])

# -----------------------
# Helpers
# -----------------------
def normalize_name(s: str) -> str:
    s = s.strip().lower()
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = re.sub(r"[^a-z\s]", "", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s

def calc_df_height(n_rows: int, row_px: int = 36, header_px: int = 40, min_px: int = 140, max_px: int = 650) -> int:
    h = header_px + n_rows * row_px
    return max(min_px, min(h, max_px))

def show_result_overlay(name: str, status: str):
    st.session_state.show_overlay = True
    st.session_state.overlay_name = name
    st.session_state.overlay_status = status

def get_new_pick(pool):
    return random.choice(pool)

def begin_round(pool):
    league, pid = get_new_pick(pool)
    st.session_state.league = league
    st.session_state.player_id = pid
    st.session_state.guesses_left = 3
    st.session_state.feedback = ""
    st.session_state.show_overlay = False
    st.session_state.guess_choice = ""

def next_round(pool):
    st.session_state.round += 1
    begin_round(pool)

# -----------------------
# Sidebar: league selection + filters
# -----------------------
st.sidebar.header("Leagues")

use_nba = st.sidebar.checkbox("NBA", value=True, disabled=not bool(nba_db))
use_mlb = st.sidebar.checkbox("MLB", value=bool(mlb_db), disabled=not bool(mlb_db))

if not use_nba and not use_mlb:
    st.sidebar.error("Select at least one league.")
    st.stop()

st.sidebar.divider()

# -----------------------
# NBA Filters
# -----------------------
if use_nba and len(nba_meta):
    st.sidebar.subheader("NBA Filters")

    nba_vals = pd.to_numeric(nba_meta["career_games"], errors="coerce").fillna(0)
    nba_median_g = int(nba_vals.median()) if len(nba_vals) else 0

    nba_min_games = st.sidebar.slider(
        "Minimum games played",
        min_value=0,
        max_value=max(0, nba_median_g),
        value=0,
        step=10,
        key="nba_games_slider"
    )
else:
    nba_min_games = 0


# -----------------------
# MLB Filters
# -----------------------
if use_mlb and len(mlb_meta):
    st.sidebar.subheader("MLB Filters")

    # ----- Hitters -----
    hitters = mlb_meta[mlb_meta["mlb_type"] == "hitter"].copy()
    hitters_vals = pd.to_numeric(hitters["career_g"], errors="coerce").fillna(0)
    hitters_median_g = int(hitters_vals.median()) if len(hitters_vals) else 0

    mlb_min_games_h = st.sidebar.slider(
        "Hitters: minimum games played",
        min_value=0,
        max_value=max(0, hitters_median_g),
        value=0,
        step=10,
        key="mlb_hitters_slider"
    )

    # ----- Pitchers -----
    pitchers = mlb_meta[mlb_meta["mlb_type"] == "pitcher"].copy()
    pitchers_vals = pd.to_numeric(pitchers["career_ip"], errors="coerce").fillna(0.0)
    pitchers_median_ip = float(pitchers_vals.median()) if len(pitchers_vals) else 0.0

    mlb_min_ip_p = st.sidebar.slider(
        "Pitchers: minimum innings pitched",
        min_value=0.0,
        max_value=max(0.0, pitchers_median_ip),
        value=0.0,
        step=10.0,
        key="mlb_pitchers_slider"
    )
else:
    mlb_min_games_h = 0
    mlb_min_ip_p = 0.0

st.sidebar.divider()
st.sidebar.header("Eligible Players")

# -----------------------
# Build eligible pool
# -----------------------
pool = []

if use_nba and len(nba_meta):
    nba_g = pd.to_numeric(nba_meta["career_games"], errors="coerce").fillna(0).astype(int)
    nba_ids = nba_meta.loc[nba_g >= nba_min_games, "player_id"].tolist()
    pool.extend([("NBA", pid) for pid in nba_ids])
    st.sidebar.caption(f"Eligible NBA players: {len(nba_ids)}")

if use_mlb and len(mlb_meta):
    hitters = mlb_meta[mlb_meta["mlb_type"] == "hitter"].copy()
    hitters_g = pd.to_numeric(hitters["career_g"], errors="coerce").fillna(0).astype(int)
    hitter_ids = hitters.loc[hitters_g >= mlb_min_games_h, "player_id"].tolist()

    pitchers = mlb_meta[mlb_meta["mlb_type"] == "pitcher"].copy()
    pitchers_ip = pd.to_numeric(pitchers["career_ip"], errors="coerce").fillna(0.0).astype(float)
    pitcher_ids = pitchers.loc[pitchers_ip >= mlb_min_ip_p, "player_id"].tolist()

    mlb_ids = hitter_ids + pitcher_ids
    pool.extend([("MLB", pid) for pid in mlb_ids])

    st.sidebar.caption(f"Eligible MLB hitters: {len(hitter_ids)}")
    st.sidebar.caption(f"Eligible MLB pitchers: {len(pitcher_ids)}")
    st.sidebar.caption(f"Eligible MLB total: {len(mlb_ids)}")

if not pool:
    st.sidebar.error("No players match your current filters.")
    st.stop()

# -----------------------
# Autocomplete options
# -----------------------
@st.cache_data
def build_name_options(nba_meta: pd.DataFrame, mlb_meta: pd.DataFrame):
    display_to_name = {}
    opts = []

    def add(meta: pd.DataFrame, league: str):
        for n in meta["name"].dropna().astype(str).tolist():
            disp = f"{n} ({league})"
            if disp not in display_to_name:
                display_to_name[disp] = n
                opts.append(disp)

    if len(nba_meta):
        add(nba_meta, "NBA")
    if len(mlb_meta):
        add(mlb_meta, "MLB")

    return sorted(opts), display_to_name

ALL_DISPLAY_OPTS, DISPLAY_TO_NAME = build_name_options(nba_meta, mlb_meta)

# If filters/leagues change, reset the game cleanly
current_settings_key = (use_nba, use_mlb, int(nba_min_games), int(mlb_min_games_h), float(mlb_min_ip_p))
if "last_settings_key" not in st.session_state:
    st.session_state.last_settings_key = current_settings_key

if current_settings_key != st.session_state.last_settings_key:
    st.session_state.last_settings_key = current_settings_key
    st.session_state.score = 0
    st.session_state.streak = 0
    st.session_state.round = 1
    begin_round(pool)

# -----------------------
# Session state init
# -----------------------
if "round" not in st.session_state:
    st.session_state.score = 0
    st.session_state.streak = 0
    st.session_state.round = 1
    begin_round(pool)

league = st.session_state.league
player_id = st.session_state.player_id

record = nba_db[player_id] if league == "NBA" else mlb_db[player_id]
answer_name = record.get("name", "")

df = pd.DataFrame(record.get("per_game", []))

# Cleanups
df = df.replace("Did not play - other pro league", "Other pro league")
df = df.replace("None", pd.NA).dropna(how="all")
df = df.reset_index(drop=True)
df_height = calc_df_height(len(df))

# -----------------------
# UI
# -----------------------
st.title("🏀⚾ Stathead Game")

c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("League", league)
c2.metric("Round", st.session_state.round)
c3.metric("Score", st.session_state.score)
c4.metric("Streak", st.session_state.streak)
c5.metric("Guesses Left", st.session_state.guesses_left)

st.dataframe(df, use_container_width=True, height=df_height, hide_index=True)

# -----------------------
# Overlay
# -----------------------
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

# -----------------------
# Controls (Autocomplete dropdown)
# -----------------------
guess_display = st.selectbox(
    "Guess the player (type to search)",
    options=[""] + ALL_DISPLAY_OPTS,
    index=0,
    key="guess_choice",
)

colA, colB = st.columns(2)
submit = colA.button("Submit Guess", use_container_width=True)
skip = colB.button("Skip", use_container_width=True)

if submit:
    if not guess_display:
        st.session_state.feedback = "Pick a name from the dropdown 🙂"
        st.rerun()

    guess_name = DISPLAY_TO_NAME.get(guess_display, guess_display)

    if normalize_name(guess_name) == normalize_name(answer_name):
        st.session_state.score += 1
        st.session_state.streak += 1
        show_result_overlay(answer_name, "correct")
        st.rerun()
    else:
        st.session_state.guesses_left -= 1
        st.session_state.streak = 0

        if st.session_state.guesses_left > 0:
            st.session_state.feedback = f"❌ Incorrect. ({st.session_state.guesses_left} left)"
            st.rerun()
        else:
            show_result_overlay(answer_name, "wrong")
            st.rerun()

if skip:
    st.session_state.streak = 0
    show_result_overlay(answer_name, "wrong")
    st.rerun()

if st.session_state.feedback:
    st.write(st.session_state.feedback)
