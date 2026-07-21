import streamlit as st
import spotipy
from spotipy.oauth2 import SpotifyOAuth
import os
import re
import requests
import pandas as pd
import json
import sqlite3
import time
from datetime import datetime

# ============================================================
# 1. CONFIGURACIO
# ============================================================
RUTA_API_SPOTIFY = r"D:\Programa llistes Spoty\api.txt"
RUTA_CONFIG_JSON = r"D:\Programa llistes Spoty\configuracio_api.json"
RUTA_DB = r"D:\Programa llistes Spoty\musica_db.sqlite"
REDIRECT_URI = "http://127.0.0.1:8501"

st.set_page_config(page_title="Rastrejador de Novetats Reals v2.0.0", page_icon="🎛️", layout="wide")

# ============================================================
# 2. BASE DE DADES SQLITE (NETA, SENSE DUPLICATS)
# ============================================================
def init_db():
    conn = sqlite3.connect(RUTA_DB)
    cursor = conn.cursor()

    cursor.execute('''
    CREATE TABLE IF NOT EXISTS artistes_confirmats (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nom TEXT NOT NULL,
        genere TEXT NOT NULL,
        subgenere TEXT,
        font TEXT DEFAULT 'IA',
        confiança TEXT DEFAULT 'probable',
        data_afegit TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        cerca_count INTEGER DEFAULT 1,
        UNIQUE(nom, genere)
    )
    ''')

    cursor.execute('''
    CREATE TABLE IF NOT EXISTS artistes_rebutjats (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nom TEXT NOT NULL,
        genere TEXT NOT NULL,
        motiu TEXT,
        data_rebutjat TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(nom, genere)
    )
    ''')

    cursor.execute('''
    CREATE TABLE IF NOT EXISTS cancons_confirmades (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        titol TEXT NOT NULL,
        artista TEXT NOT NULL,
        genere TEXT NOT NULL,
        any_ll INTEGER,
        bpm REAL,
        clau TEXT,
        popularitat INTEGER,
        font TEXT DEFAULT 'Spotify',
        spotify_uri TEXT,
        data_afegit TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(titol, artista, genere)
    )
    ''')

    cursor.execute('''
    CREATE TABLE IF NOT EXISTS generes_inteligents (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nom_genere TEXT NOT NULL UNIQUE,
        estils TEXT DEFAULT '',
        seeds TEXT DEFAULT '',
        color TEXT DEFAULT '#00ff88',
        icona TEXT DEFAULT '🎵',
        data_creat TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')

    cursor.execute('''
    CREATE TABLE IF NOT EXISTS generes_apresos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nom_genere TEXT NOT NULL UNIQUE,
        descripcio TEXT,
        artistes_clau TEXT,
        subgeneres TEXT,
        total_artistes INTEGER DEFAULT 0,
        total_cancons INTEGER DEFAULT 0,
        ultima_actualitzacio TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')

    conn.commit()
    conn.close()

def db_conn():
    return sqlite3.connect(RUTA_DB)

