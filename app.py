import streamlit as st
import spotipy
from spotipy.oauth2 import SpotifyOAuth
import requests
import pandas as pd
import time
from datetime import datetime

# --- CONFIGURACIÓ ---
st.set_page_config(page_title="Rastrejador de Novetats", page_icon="🎛️", layout="wide")

# Inicialització de claus des de Streamlit Secrets
try:
    CLIENT_ID = st.secrets["SPOTIFY_CLIENT_ID"]
    CLIENT_SECRET = st.secrets["SPOTIFY_CLIENT_SECRET"]
    GROQ_KEY = st.secrets["GROQ_KEY"]
    GROQ_URL = st.secrets["GROQ_URL"]
    DISCOGS_TOKEN = st.secrets["DISCOGS_TOKEN"]
    REDIRECT_URI = "https://share.streamlit.io/" # URL obligatòria per al núvol
except Exception as e:
    st.error("Error: Falten claus als 'Secrets' de Streamlit.")
    st.stop()

# --- CONSOLA ---
if 'console_logs' not in st.session_state: st.session_state.console_logs = []

def log(msg, level="info"):
    timestamp = datetime.now().strftime("%H:%M:%S")
    st.session_state.console_logs.append({"time": timestamp, "level": level.upper(), "msg": str(msg)})

# (Aquí mantindries les teves funcions: ia_identifica_artistes_i_generes, 
# cercar_spotify_artista, cercar_discogs_artista, etc., tal com les tenies)
# NOMÉS cal que t'asseguris que no utilitzin os.path ni rutes D:\

# --- INTERFÍCIE ---
st.title("🎛️ Rastrejador de Novetats")

# Autenticació Spotify
sp = spotipy.Spotify(auth_manager=SpotifyOAuth(
    client_id=CLIENT_ID, client_secret=CLIENT_SECRET,
    redirect_uri=REDIRECT_URI, scope="playlist-modify-public"
))

# --- DUES COLUMNES ---
col_filtres, col_resultats = st.columns([1, 2])

with col_filtres:
    st.subheader("Filtres")
    estil = st.text_input("Estil / Gènere:", "Mákina")
    any_triat = st.text_input("Any / Rang:", "2025/2026")
    quantitat = st.number_input("Nombre de cançons:", 10, 200, 100)
    
    if st.button("🚀 Començar Rastreig"):
        log(f"Iniciant cerca: {estil}")
        # Aquí crides la teva lògica de FASE 1 a FASE 6
        st.rerun()

with col_resultats:
    st.subheader("Consola")
    for entry in reversed(st.session_state.console_logs[-20:]):
        st.text(f"[{entry['time']}] {entry['level']}: {entry['msg']}")