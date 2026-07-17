import streamlit as st
import spotipy
from spotipy.oauth2 import SpotifyOAuth
import os
import re
import requests
import pandas as pd
import time
import json
from datetime import datetime

# --- 1. CONFIGURACIO ---
st.set_page_config(page_title="Rastrejador de Novetats Reals", page_icon="🎛️", layout="wide")

# --- LECTURA DE CREDENCIALS ---
def carregar_credencials():
    """Carrega credencials des de st.secrets (Cloud)"""
    creds = {
        "CLIENT_ID": st.secrets.get("SPOTIFY_CLIENT_ID", ""),
        "CLIENT_SECRET": st.secrets.get("SPOTIFY_CLIENT_SECRET", ""),
        "GROQ_KEY": st.secrets.get("GROQ_KEY", ""),
        "GROQ_URL": st.secrets.get("GROQ_URL", ""),
        "DISCOGS_TOKEN": st.secrets.get("DISCOGS_TOKEN", "")
    }
    return creds

CREDS = carregar_credencials()
CLIENT_ID = CREDS["CLIENT_ID"]
CLIENT_SECRET = CREDS["CLIENT_SECRET"]
GROQ_KEY = CREDS["GROQ_KEY"]
GROQ_URL = CREDS["GROQ_URL"]
DISCOGS_TOKEN = CREDS["DISCOGS_TOKEN"]

# --- DICCIONARI D'ESTILS ---
DICCIONARI_ESTILS = {
    "makina": {
        "noms": ["makina", "mákina", "spanish hardcore", "bakalao", "hardcore", "gabber", "hardtek", "rave"],
        "artistes_clau": ["Pont Aeri", "Pastis & Buenri", "Ruboy", "Xavi Metralla", "Skudero", "DJ Nau"],
        "descripcio": "Musica electronica rapida (150-200 BPM)."
    }
}

# --- 2. SISTEMA DE LOGS ---
def init_console():
    if 'console_logs' not in st.session_state:
        st.session_state.console_logs = []

def log(msg, level="info"):
    init_console()
    timestamp = datetime.now().strftime("%H:%M:%S")
    colors = {"info": "#3b82f6", "success": "#10b981", "warning": "#f59e0b", "error": "#ef4444", "debug": "#6b7280"}
    icons = {"info": "🔵", "success": "✅", "warning": "⚠️", "error": "❌", "debug": "🔍"}
    
    st.session_state.console_logs.append({
        "time": timestamp,
        "icon": icons.get(level, "⚪"),
        "level": level.upper(),
        "msg": str(msg),
        "color": colors.get(level, "#6b7280")
    })
    
    if len(st.session_state.console_logs) > 200:
        st.session_state.console_logs = st.session_state.console_logs[-200:]

def render_console_permanent():
    init_console()
    html_lines = []
    for entry in st.session_state.console_logs[-20:]:
        line = f'<div style="font-family: \'Courier New\', monospace; font-size: 11px; padding: 2px 4px; border-left: 2px solid {entry["color"]}; margin-bottom: 1px;">'
        line += f'<span style="color: #888;">[{entry["time"]}]</span> '
        line += f'<span style="color: {entry["color"]}; font-weight: bold;">{entry["icon"]} {entry["level"]}</span> '
        line += f'<span style="color: #e0e0e0;">{entry["msg"]}</span></div>'
        html_lines.append(line)
    
    html = '<div style="background: #0a0a0a; border: 2px solid #333; border-radius: 8px; padding: 10px; height: 280px; overflow-y: auto;">'
    html += "".join(html_lines) + '</div>'
    st.markdown(html, unsafe_allow_html=True)

# --- 3. FUNCIONS IA I CERCA (Resumides per brevetat) ---
def identificar_artistes_reals_genere(estil):
    if not GROQ_KEY: return []
    # Aquí aniria la teva lògica de crida a l'API de Groq
    return ["Exemple Artista 1", "Exemple Artista 2"]

# --- 4. EXECUCIO PRINCIPAL ---
st.title("🎛️ Rastrejador de Novetats")
render_console_permanent()

if st.button("Prova Log"):
    log("Prova de sistema correcta", "success")
    st.rerun()