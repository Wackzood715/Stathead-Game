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
db = load_db(NBA_PATH)

# -----------------------
# Fast metadata layer (speeds up slider filtering)
# -----------------------
def _to_int(x):
    try:
        if x is None:
            return None
        s = str(x).replace(",", "").strip()
        if s.lower() in ["", "none", "nan"]:
            return None
        return int(float(s))
    except:
        return None

def career_games_from_rows(rows):
    # Prefer "Yrs" summary row
    for row in rows:
        season = str(row.get("Season", ""))
        if "Yrs" in season:
            g = _to_int(row.get("G"))
            if g is not None:
                return g

    # Fallback: sum season rows
    total = 0
    found = False
    for row in rows:
        season = str(row.get("Season", ""))
        if re.fullmatch(r"\d{4}-\d{2}", season):
            g = _to_int(row.get("G"))
            if g is not None:
                total += g
                found = True
    return total if found else None

@st.cache_data
def build_nba_meta(path: str, file_mtime: float) -> pd.DataFrame:
    """
    Cached by (path, file_mtime). Recomputes only when the JSON file changes.
    Avoids hashing the full db dict on every rerun.
    """
    db_local = load_db(path)
    rows = []
    for pid, rec in db_local.items():
        name = rec.get("name")
        g = career_games_from_rows(rec.get("per_game", []))
        if name and g is not None:
            rows.append((pid, name, g))
    return pd.DataFrame(rows, columns=["player_id", "name", "career_games"])

nba_mtime = os.path.getmtime(NBA_PATH)
nba_meta = build_nba_meta(NBA_PATH, nba_mtime)

# Build a name list for autocomplete (ALL players in the JSON) - now from meta (fast)
@st.cache_data
def all_player_names_from_meta(meta: pd.DataFrame):
    return sorted(meta["name"].dropna().unique().tolist())

ALL_NAMES = all_player_names_from_meta(nba_meta)

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

def get_new_player_id(pool):
    return random.choice(pool)

def begin_round(pool):
    st.session_state.player_id = get_new_player_id(pool)
    st.session_state.guesses_left = 3
    st.session_state.feedback = ""
    st.session_state.show_overlay = False
    # reset the selectbox each round
    st.session_state.guess_name = ""

def next_round(pool):
    st.session_state.round += 1
    begin_round(pool)

# -----------------------
# Sidebar slider (FAST)
# -----------------------
st.sidebar.header("Filters")

max_g = int(nba_meta["career_games"].max()) if len(nba_meta) else 1200
nba_min_games = st.sidebar.slider(
    "NBA minimum games played",
    min_value=0,
    max_value=max_g,
    value=0,
    step=10
)

eligible_ids = nba_meta.loc[nba_meta["career_games"] >= nba_min_games, "player_id"].tolist()

if len(eligible_ids) == 0:
    st.sidebar.error("No players match that filter.")
    st.stop()

st.sidebar.caption(f"Eligible NBA players: {len(eligible_ids)}")

# Reset round cleanly when slider changes (prevents stale player_id outside pool)
if "last_nba_min_games" not in st.session_state:
    st.session_state.last_nba_min_games = nba_min_games

if nba_min_games != st.session_state.last_nba_min_games:
    st.session_state.last_nba_min_games = nba_min_games
    st.session_state.score = 0
    st.session_state.streak = 0
    st.session_state.round = 1
    begin_round(eligible_ids)

# -----------------------
# Session state init
# -----------------------
if "round" not in st.session_state:
    st.session_state.score = 0
    st.session_state.streak = 0
    st.session_state.round = 1
    st.session_state.guess_name = ""
    begin_round(eligible_ids)

player_id = st.session_state.player_id
record = db[player_id]
answer_name = record["name"]

df = pd.DataFrame(record["per_game"])
df = df.replace("Did not play - other pro league", "Other pro league")
df = df.replace("None", pd.NA).dropna(how="all")
df = df.reset_index(drop=True)
df_height = calc_df_height(len(df))

# -----------------------
# UI
# -----------------------
st.title("🏀 Stathead Game")

c1, c2, c3, c4 = st.columns(4)
c1.metric("Round", st.session_state.round)
c2.metric("Score", st.session_state.score)
c3.metric("Streak", st.session_state.streak)
c4.metric("Guesses Left", st.session_state.guesses_left)

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
        next_round(eligible_ids)
        st.rerun()
    btn_holder.markdown("</div>", unsafe_allow_html=True)

    st.stop()

# -----------------------
# Controls (Autocomplete dropdown)
# -----------------------
guess_name = st.selectbox(
    "Guess the player (type to search)",
    options=[""] + ALL_NAMES,
    index=0,
    key="guess_name",
)

colA, colB = st.columns(2)
submit = colA.button("Submit Guess", use_container_width=True)
skip = colB.button("Skip", use_container_width=True)

if submit:
    if not guess_name:
        st.session_state.feedback = "Pick a name from the dropdown 🙂"
        st.rerun()

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
