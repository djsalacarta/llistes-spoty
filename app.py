import streamlit as st
import spotipy
from spotipy.oauth2 import SpotifyOAuth
import requests
import pandas as pd
import time
from datetime import datetime

# --- CONFIGURACIÓ ---
st.set_page_config(page_title="Rastrejador de Novetats", page_icon="🎛️", layout="wide")

# Funció per carregar claus des del núvol
def get_secret(key):
    return st.secrets.get(key, None)

CLIENT_ID = get_secret("SPOTIFY_CLIENT_ID")
CLIENT_SECRET = get_secret("SPOTIFY_CLIENT_SECRET")
GROQ_KEY = get_secret("GROQ_KEY")
GROQ_URL = get_secret("GROQ_URL")
DISCOGS_TOKEN = get_secret("DISCOGS_TOKEN")
REDIRECT_URI = "https://share.streamlit.io/" # URL estàndard de Streamlit

# --- CONSOLA ---
def init_console():
    if 'console_logs' not in st.session_state: st.session_state.console_logs = []

def log(msg, level="info"):
    init_console()
    st.session_state.console_logs.append({
        "time": datetime.now().strftime("%H:%M:%S"),
        "level": level.upper(),
        "msg": str(msg)
    })

def render_console():
    init_console()
    for entry in st.session_state.console_logs[-20:]:
        color = "#3b82f6" if entry["level"] == "INFO" else "#10b981"
        st.markdown(f'<div style="font-family:monospace;font-size:11px;color:{color}">[{entry["time"]}] {entry["level"]}: {entry["msg"]}</div>', unsafe_allow_html=True)

# --- IA I RESTA DE FUNCIONS ---
# (Pots mantenir les teves funcions ia_identifica_artistes_i_generes, cercar_spotify, etc., tal qual les tenies)
# NOMÉS substitueix les referències a RUTA_API_SPOTIFY per les variables CLIENT_ID/SECRET directament.

# --- INTERFÍCIE ---
st.title("🎛️ Rastrejador de Novetats")
render_console()

if not CLIENT_ID:
    st.error("Error: Les claus no estan configurades als 'Secrets' de Streamlit.")
else:
    # Aquesta és l'estructura on posaries els teus menús
    estil = st.sidebar.text_input("Estil", "Mákina")
    if st.sidebar.button("Executar"):
        log("Cerca iniciada...", "info")
        # Aquí crides la teva lògica
        st.rerun()