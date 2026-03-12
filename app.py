import streamlit as st

st.set_page_config(layout="wide")

import json
import random
import pandas as pd
import re
import unicodedata

# -----------------------
# Styling
# -----------------------
st.markdown(
    """
    <style>
    [data-testid="stDataFrame"] div { font-size: 12px; }

    /* Overlay background */
    .overlay {
        position: fixed;
        inset: 0;
        background: rgba(0,0,0,0.55);
        z-index: 9998;
        pointer-events: none;
    }

    /* Modal box (visual) */
    .modal {
        position: fixed;
        top: 50%;
        left: 50%;
        transform: translate(-50%, -50%);
        border-radius: 14px;
        padding: 22px 26px 74px 26px; /* bottom padding for button area */
        width: min(520px, 92vw);
        z-index: 9999;
        box-shadow: 0 12px 50px rgba(0,0,0,0.55);
        pointer-events: none; /* visual only */
        border: 1px solid rgba(0,0,0,0.15);
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

    /* Position the Streamlit button over the modal */
    div[data-testid="answer-next-btn"] {
        position: fixed !important;
        top: calc(50% + 110px) !important;  /* tweak if needed */
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
def load_db():
    with open("nba_per_game_db.json", "r", encoding="utf-8") as f:
        return json.load(f)

db = load_db()

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

def get_new_player_id():
    return random.choice(list(db.keys()))

def begin_round():
    st.session_state.player_id = get_new_player_id()
    st.session_state.guesses_left = 3
    st.session_state.feedback = ""
    st.session_state.show_overlay = False
    st.session_state.overlay_name = ""
    st.session_state.overlay_status = ""  # "correct" or "wrong"

def next_round():
    st.session_state.round += 1
    begin_round()

def calc_df_height(n_rows: int, row_px: int = 36, header_px: int = 40, min_px: int = 140, max_px: int = 650) -> int:
    h = header_px + n_rows * row_px
    return max(min_px, min(h, max_px))

def show_result_overlay(name: str, status: str):
    """
    status: "correct" or "wrong"
    """
    st.session_state.show_overlay = True
    st.session_state.overlay_name = name
    st.session_state.overlay_status = status

# -----------------------
# Session State init
# -----------------------
if "round" not in st.session_state:
    st.session_state.score = 0
    st.session_state.streak = 0
    st.session_state.round = 1
    begin_round()

player_id = st.session_state.player_id
record = db[player_id]
answer_name = record["name"]

df = pd.DataFrame(record["per_game"])
df = df.replace("Did not play - other pro league", "Other pro league")
df = df.reset_index(drop=True)
df_height = calc_df_height(len(df))

# -----------------------
# UI header
# -----------------------
st.title("🏀 Stathead Game")

c1, c2, c3, c4 = st.columns(4)
c1.metric("Round", st.session_state.round)
c2.metric("Score", st.session_state.score)
c3.metric("Streak", st.session_state.streak)
c4.metric("Guesses Left", st.session_state.guesses_left)

try:
    st.dataframe(df, use_container_width=True, height=df_height, hide_index=True)
except TypeError:
    st.dataframe(df, use_container_width=True, height=df_height)

# -----------------------
# Result Overlay (Correct/Wrong)
# -----------------------
if st.session_state.show_overlay:
    status = st.session_state.overlay_status

    # Light green for correct, light red for wrong
    if status == "correct":
        bg = "rgb(46, 255, 12, 0.97)"  # light green
        title = "Correct"
        sub = "Nice. Click Next Player to continue."
    else:
        bg = "rgb(255, 53, 82, 0.97)"  # light red
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
        next_round()
        st.rerun()
    btn_holder.markdown("</div>", unsafe_allow_html=True)

    st.stop()

# -----------------------
# Controls
# -----------------------
with st.form("guess_form", clear_on_submit=True):
    guess = st.text_input("Guess the player")
    submitted = st.form_submit_button("Submit Guess", use_container_width=True)

skip = st.button("Skip", use_container_width=True)

if submitted:
    if not guess.strip():
        st.session_state.feedback = "Type a guess first 🙂"
        st.rerun()

    if normalize_name(guess) == normalize_name(answer_name):
        st.session_state.score += 1
        st.session_state.streak += 1
        show_result_overlay(answer_name, "correct")
        st.rerun()
    else:
        st.session_state.guesses_left -= 1
        st.session_state.streak = 0

        if st.session_state.guesses_left > 0:
            st.session_state.feedback = f"❌ Incorrect. Try again. ({st.session_state.guesses_left} left)"
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
