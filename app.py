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
# 2. BASE DE DADES SQLITE (APRENENTATGE)
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

def consultar_artistes_db(genere, min_confiança="probable"):
    conn = db_conn()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT nom, subgenere, confiança, cerca_count 
        FROM artistes_confirmats 
        WHERE LOWER(genere) = LOWER(?) 
        ORDER BY 
            CASE confiança WHEN 'segur' THEN 1 WHEN 'probable' THEN 2 ELSE 3 END,
            cerca_count DESC
    ''', (genere,))
    resultats = cursor.fetchall()
    conn.close()
    mapping = {'segur': 1, 'probable': 2, 'dubtos': 3}
    min_nivell = mapping.get(min_confiança, 2)
    filtrats = []
    for nom, sub, conf, count in resultats:
        nivell = mapping.get(conf, 3)
        if nivell <= min_nivell:
            filtrats.append((nom, sub or "desconegut", conf))
    return filtrats

def consultar_rebutjats_db(genere):
    conn = db_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT nom FROM artistes_rebutjats WHERE LOWER(genere) = LOWER(?)", (genere,))
    resultats = {r[0] for r in cursor.fetchall()}
    conn.close()
    return resultats

def guardar_artista_confirmat(nom, genere, subgenere=None, font="IA", confiança="probable"):
    conn = db_conn()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO artistes_confirmats (nom, genere, subgenere, font, confiança, cerca_count)
        VALUES (?, ?, ?, ?, ?, 1)
        ON CONFLICT(nom, genere) DO UPDATE SET
            cerca_count = cerca_count + 1,
            confiança = CASE WHEN excluded.confiança = 'segur' THEN 'segur' ELSE artistes_confirmats.confiança END,
            data_afegit = CURRENT_TIMESTAMP
    ''', (nom, genere, subgenere, font, confiança))
    conn.commit()
    conn.close()

def guardar_artista_rebutjat(nom, genere, motiu="No es del genere"):
    conn = db_conn()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT OR IGNORE INTO artistes_rebutjats (nom, genere, motiu)
        VALUES (?, ?, ?)
    ''', (nom, genere, motiu))
    conn.commit()
    conn.close()

def guardar_canco_confirmada(titol, artista, genere, any_ll, bpm=None, clau=None, popularitat=None, font="Spotify", spotify_uri=None):
    conn = db_conn()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT OR IGNORE INTO cancons_confirmades (titol, artista, genere, any_ll, bpm, clau, popularitat, font, spotify_uri)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (titol, artista, genere, any_ll, bpm, clau, popularitat, font, spotify_uri))
    conn.commit()
    conn.close()

def actualitzar_estadistiques_genere(genere):
    conn = db_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM artistes_confirmats WHERE genere = ?", (genere,))
    total_art = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM cancons_confirmades WHERE genere = ?", (genere,))
    total_can = cursor.fetchone()[0]
    cursor.execute('''
        INSERT INTO generes_apresos (nom_genere, total_artistes, total_cancons)
        VALUES (?, ?, ?)
        ON CONFLICT(nom_genere) DO UPDATE SET
            total_artistes = excluded.total_artistes,
            total_cancons = excluded.total_cancons,
            ultima_actualitzacio = CURRENT_TIMESTAMP
    ''', (genere, total_art, total_can))
    conn.commit()
    conn.close()

def obtenir_estadistiques_db():
    conn = db_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM artistes_confirmats")
    total_conf = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM artistes_rebutjats")
    total_reb = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM cancons_confirmades")
    total_can = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM generes_apresos")
    total_gen = cursor.fetchone()[0]
    cursor.execute("SELECT nom_genere, total_artistes, total_cancons FROM generes_apresos ORDER BY total_artistes DESC LIMIT 5")
    top_generes = cursor.fetchall()
    conn.close()
    return {
        "artistes_confirmats": total_conf, "artistes_rebutjats": total_reb,
        "cancons_confirmades": total_can, "generes_apresos": total_gen,
        "top_generes": top_generes
    }

def obtenir_tots_generes_db():
    conn = db_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT DISTINCT LOWER(nom_genere) as genere_lower, nom_genere FROM generes_apresos ORDER BY nom_genere")
    generes = cursor.fetchall()
    cursor.execute("SELECT DISTINCT LOWER(genere) as genere_lower, genere FROM artistes_confirmats ORDER BY genere")
    artistes_generes = cursor.fetchall()
    conn.close()

    tots = {}
    for g_lower, g_original in generes:
        tots[g_lower] = g_original
    for g_lower, g_original in artistes_generes:
        if g_lower not in tots:
            tots[g_lower] = g_original

    return sorted(tots.values(), key=str.lower)

def obtenir_artistes_per_genere(genere):
    conn = db_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT nom, subgenere, confiança, cerca_count FROM artistes_confirmats WHERE LOWER(genere) = LOWER(?) ORDER BY nom", (genere,))
    resultats = cursor.fetchall()
    conn.close()
    return resultats

init_db()

# ============================================================
# FUNCIONS INTEL·LIGENTS PER GÈNERES
# ============================================================
def guardar_genere_inteligent(nom_genere, estils="", seeds="", color="#00ff88", icona="🎵"):
    conn = db_conn()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO generes_inteligents (nom_genere, estils, seeds, color, icona)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(nom_genere) DO UPDATE SET
            estils = excluded.estils,
            seeds = excluded.seeds,
            color = excluded.color,
            icona = excluded.icona
    """, (nom_genere.lower().strip(), estils, seeds, color, icona))
    conn.commit()
    conn.close()

def obtenir_generes_inteligents():
    conn = db_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT nom_genere, estils, seeds, color, icona FROM generes_inteligents ORDER BY nom_genere")
    resultats = cursor.fetchall()
    conn.close()
    return resultats

def obtenir_genere_inteligent(nom_genere):
    conn = db_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT nom_genere, estils, seeds, color, icona FROM generes_inteligents WHERE LOWER(nom_genere) = LOWER(?)", (nom_genere,))
    resultat = cursor.fetchone()
    conn.close()
    return resultat

def esborrar_genere_inteligent(nom_genere):
    conn = db_conn()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM generes_inteligents WHERE LOWER(nom_genere) = LOWER(?)", (nom_genere,))
    conn.commit()
    conn.close()

ESTILS_PREDEFINITS = {
    "makina": {"estils": "Makina, Hardcore espanyol, Pont Aeri, Xque", "seeds": "Pont Aeri, Pastis & Buenri, Ruboy, Xavi Metralla, Javi Boss, Skudero, DJ Nau, Xque, Sissu, Chimo Bayo", "color": "#ff0066", "icona": "🔥"},
    "mákina": {"estils": "Makina, Hardcore espanyol, Pont Aeri, Xque", "seeds": "Pont Aeri, Pastis & Buenri, Ruboy, Xavi Metralla, Javi Boss, Skudero, DJ Nau, Xque, Sissu, Chimo Bayo", "color": "#ff0066", "icona": "🔥"},
    "techno": {"estils": "Techno, Detroit Techno, Minimal Techno, Industrial Techno, Acid Techno", "seeds": "Adam Beyer, Charlotte de Witte, Amelie Lens, Nina Kraviz, Carl Cox, Jeff Mills, Robert Hood, Ben Klock", "color": "#00d4ff", "icona": "🌀"},
    "hardcore": {"estils": "Hardcore, Gabber, Frenchcore, Happy Hardcore, UK Hardcore", "seeds": "Neophyte, Korsakoff, Rotterdam Terror Corps, DJ Paul, The Stunned Guys, Tommyknocker, Mad Dog", "color": "#ff3300", "icona": "💀"},
    "house": {"estils": "House, Deep House, Tech House, Progressive House, Electro House", "seeds": "David Guetta, Calvin Harris, Swedish House Mafia, Disclosure, Duke Dumont, MK, Fisher", "color": "#ffcc00", "icona": "🏠"},
    "trance": {"estils": "Trance, Psytrance, Uplifting Trance, Tech Trance, Vocal Trance", "seeds": "Armin van Buuren, Tiësto, Above & Beyond, Paul van Dyk, Ferry Corsten, Aly & Fila, Vini Vici", "color": "#cc66ff", "icona": "✨"},
    "drum and bass": {"estils": "Drum and Bass, Liquid DnB, Neurofunk, Jump Up, Jungle", "seeds": "Andy C, Noisia, Pendulum, High Contrast, Goldie, Sub Focus, Chase & Status", "color": "#ff6600", "icona": "🥁"},
    "dubstep": {"estils": "Dubstep, Brostep, Riddim, Melodic Dubstep, Tearout", "seeds": "Skrillex, Excision, Zeds Dead, Virtual Riot, Marauda, Subtronics", "color": "#9900ff", "icona": "⚡"},
    "edm": {"estils": "EDM, Big Room, Future Bass, Trap, Electro House", "seeds": "Martin Garrix, Hardwell, Dimitri Vegas & Like Mike, Steve Aoki, Tiësto, David Guetta", "color": "#ff0099", "icona": "🎉"},
}

def detectar_estils_genere(nom_genere):
    nom_lower = nom_genere.lower().strip()
    for clau, info in ESTILS_PREDEFINITS.items():
        if clau in nom_lower or nom_lower in clau:
            return info

    if GROQ_KEY and GROQ_URL:
        try:
            headers = {"Authorization": f"Bearer {GROQ_KEY}", "Content-Type": "application/json"}
            prompt = f"""Ets un expert musical. Per al gènere "{nom_genere}", dona'm:
1. 5 subgèneres/estils relacionats (separats per comes)
2. 10 artistes representatius (separats per comes)
3. Un color hex (#RRGGBB) que representi aquest gènere
4. Una icona emoji que el representi

FORMAT OBLIGATORI (una línia per camp):
ESTILS: subgenere1, subgenere2, subgenere3, subgenere4, subgenere5
SEEDS: artista1, artista2, artista3, artista4, artista5, artista6, artista7, artista8, artista9, artista10
COLOR: #RRGGBB
ICONA: emoji"""

            data = {"model": MODEL_IA, "messages": [{"role": "user", "content": prompt}], "temperature": 0.3, "max_tokens": 500}
            res = requests.post(GROQ_URL, headers=headers, json=data, timeout=15)

            if res.status_code == 200:
                resposta = res.json()["choices"][0]["message"]["content"].strip()
                estils = ""
                seeds = ""
                color = "#00ff88"
                icona = "🎵"

                for linia in resposta.splitlines():
                    linia = linia.strip()
                    if linia.startswith("ESTILS:"):
                        estils = linia.replace("ESTILS:", "").strip()
                    elif linia.startswith("SEEDS:"):
                        seeds = linia.replace("SEEDS:", "").strip()
                    elif linia.startswith("COLOR:"):
                        color = linia.replace("COLOR:", "").strip()
                        if not color.startswith("#") or len(color) != 7:
                            color = "#00ff88"
                    elif linia.startswith("ICONA:"):
                        icona = linia.replace("ICONA:", "").strip()

                return {"estils": estils, "seeds": seeds, "color": color, "icona": icona}
        except Exception as e:
            pass

    return {"estils": nom_genere, "seeds": "", "color": "#00ff88", "icona": "🎵"}

LLISTA_NEGRA = ["tuyo", "rimsky-korsakov", "mussorgsky", "modest mussorgsky", "nikolai rimsky-korsakov"]

SEEDS_GENERE = {
    "makina": ["Pont Aeri", "Pastis & Buenri", "Ruboy", "Xavi Metralla", "Javi Boss", "Skudero", "DJ Nau", "Xque", "Sissu", "Chimo Bayo", "Cesar Almena", "M-Project", "DJ Soto"],
    "mákina": ["Pont Aeri", "Pastis & Buenri", "Ruboy", "Xavi Metralla", "Javi Boss", "Skudero", "DJ Nau", "Xque", "Sissu", "Chimo Bayo", "Cesar Almena", "M-Project", "DJ Soto"],
    "hardcore": ["Neophyte", "Korsakoff", "Rotterdam Terror Corps", "DJ Paul", "The Stunned Guys", "Tommyknocker", "Mad Dog", "Noize Suppressor"],
    "techno": ["Adam Beyer", "Charlotte de Witte", "Amelie Lens", "Nina Kraviz", "Carl Cox", "Jeff Mills", "Robert Hood"],
    "house": ["David Guetta", "Calvin Harris", "Swedish House Mafia", "Disclosure", "Duke Dumont", "MK"],
    "trance": ["Armin van Buuren", "Tiësto", "Above & Beyond", "Paul van Dyk", "Ferry Corsten", "Aly & Fila"],
    "drum and bass": ["Andy C", "Noisia", "Pendulum", "High Contrast", "Goldie", "Sub Focus"],
}

MESES = {
    "gener": 1, "febrer": 2, "març": 3, "abril": 4, "maig": 5, "juny": 6,
    "juliol": 7, "agost": 8, "setembre": 9, "octubre": 10, "novembre": 11, "desembre": 12
}

MESES_NOMS = ["Indiferent", "Gener", "Febrer", "Març", "Abril", "Maig", "Juny",
              "Juliol", "Agost", "Setembre", "Octubre", "Novembre", "Desembre"]

ANYS_DISPONIBLES = ["Indiferent"] + [str(a) for a in range(1950, 2027)]

def parsejar_any_mes(any_input, mes_input):
    any_actual = datetime.now().year

    if any_input == "Indiferent":
        any_min = 1950
        any_max = any_actual
    elif "/" in any_input:
        parts = any_input.split("/")
        try:
            any_min = int(parts[0].strip())
            any_max = int(parts[1].strip())
        except:
            any_min = any_max = any_actual
    else:
        try:
            any_min = any_max = int(any_input.strip())
        except:
            any_min = any_max = any_actual

    if mes_input == "Indiferent":
        return any_min, any_max, None, None

    mes_num = None
    mes_lower = mes_input.lower().strip()
    if mes_lower in MESES:
        mes_num = MESES[mes_lower]
    else:
        try:
            mes_num = int(mes_input)
            if mes_num < 1 or mes_num > 12:
                mes_num = None
        except:
            mes_num = None

    if mes_num:
        return any_min, any_max, mes_num, mes_num

    return any_min, any_max, None, None

def obtenir_seeds_genere(estil):
    estil_lower = estil.lower().strip()
    for clau, artistes in SEEDS_GENERE.items():
        if clau in estil_lower or estil_lower in clau:
            return artistes
    return []

def parsejar_llista_artistes(text_artistes):
    if not text_artistes or not text_artistes.strip():
        return []
    artistes = []
    for linia in text_artistes.splitlines():
        linia = linia.strip()
        if not linia:
            continue
        if "," in linia:
            for part in linia.split(","):
                nom = part.strip()
                if nom and len(nom) > 1:
                    artistes.append(nom)
        else:
            if len(linia) > 1:
                artistes.append(linia)
    vistos = set()
    unics = []
    for a in artistes:
        a_lower = a.lower()
        if a_lower not in vistos:
            vistos.add(a_lower)
            unics.append(a)
    return unics

def guardar_llista_artistes_confirmats(artistes, genere):
    count = 0
    for artista in artistes:
        guardar_artista_confirmat(artista, genere, subgenere=None, font="usuari", confiança="segur")
        count += 1
    return count

# ============================================================
# 3. SISTEMA DE LOGS (TEMPS REAL)
# ============================================================
def init_console():
    if 'console_logs' not in st.session_state:
        st.session_state.console_logs = []
    if 'console_html' not in st.session_state:
        st.session_state.console_html = ""

def log(msg, level="info"):
    init_console()
    timestamp = datetime.now().strftime("%H:%M:%S")
    colors = {"info": "#3b82f6", "success": "#10b981", "warning": "#f59e0b", "error": "#ef4444", "debug": "#6b7280"}
    icons = {"info": "🔵", "success": "✅", "warning": "⚠️", "error": "❌", "debug": "🔍"}
    color = colors.get(level, "#6b7280")
    icon = icons.get(level, "⚪")
    st.session_state.console_logs.append({"time": timestamp, "icon": icon, "level": level.upper(), "msg": str(msg), "color": color})
    if len(st.session_state.console_logs) > 200:
        st.session_state.console_logs = st.session_state.console_logs[-200:]
    html_lines = []
    for entry in st.session_state.console_logs[-10:]:
        html_lines.append(
            f'<div style="font-family: Courier New, monospace; font-size: 11px; padding: 2px 4px; border-left: 2px solid {entry["color"]}; margin-bottom: 1px;">'
            f'<span style="color: #888;">[{entry["time"]}]</span> '
            f'<span style="color: {entry["color"]}; font-weight: bold;">{entry["icon"]} {entry["level"]}</span> '
            f'<span style="color: #e0e0e0;">{entry["msg"]}</span></div>'
        )
    st.session_state.console_html = "\n".join(html_lines)

def clear_console():
    st.session_state.console_logs = []
    st.session_state.console_html = ""

def render_console():
    init_console()
    html = st.session_state.console_html or '<div style="color: #666; font-family: monospace; padding: 20px; text-align: center;">⏳ Esperant operacions...</div>'
    st.markdown(f"""
    <div style="background: #0a0a0a; border: 1px solid #333; border-radius: 8px; padding: 10px; height: 220px; overflow-y: auto; font-family: Courier New, monospace; box-shadow: 0 0 10px rgba(0, 255, 136, 0.05); width: 100%; box-sizing: border-box;">
        <div style="position: sticky; top: 0; background: #1a1a1a; padding: 5px 10px; border-bottom: 1px solid #333; margin-bottom: 10px; border-radius: 4px; display: flex; justify-content: space-between; align-items: center;">
            <span style="color: #00ff88; font-weight: bold; font-size: 12px;">🖥️ CONSOLA</span>
            <span style="color: #888; font-size: 11px;">{len(st.session_state.console_logs)} registres</span>
        </div>
        {html}
    </div>
    """, unsafe_allow_html=True)

# ============================================================
# 4. CREDENCIALS
# ============================================================
def carregar_credencials():
    creds = {"CLIENT_ID": "", "CLIENT_SECRET": "", "GROQ_KEY": "", "GROQ_URL": "", "DISCOGS_TOKEN": ""}
    try:
        if "spotify" in st.secrets:
            creds["CLIENT_ID"] = st.secrets["spotify"].get("client_id", "")
            creds["CLIENT_SECRET"] = st.secrets["spotify"].get("client_secret", "")
        if "groq" in st.secrets:
            creds["GROQ_KEY"] = st.secrets["groq"].get("key", "")
            creds["GROQ_URL"] = st.secrets["groq"].get("url", "")
        if "discogs" in st.secrets:
            creds["DISCOGS_TOKEN"] = st.secrets["discogs"].get("token", "")
    except Exception:
        pass

    if not creds["CLIENT_ID"] and os.path.exists(RUTA_API_SPOTIFY):
        try:
            with open(RUTA_API_SPOTIFY, "r", encoding="utf-8") as f:
                claus = re.findall(r'[a-f0-9]{32}', f.read())
            if len(claus) >= 2:
                creds["CLIENT_ID"] = claus[0]
                creds["CLIENT_SECRET"] = claus[1]
        except Exception:
            pass
            
    if not creds["GROQ_KEY"] and os.path.exists(RUTA_CONFIG_JSON):
        try:
            with open(RUTA_CONFIG_JSON, "r", encoding="utf-8") as f:
                config = json.load(f)
            creds["GROQ_KEY"] = config.get("GROQ_KEY", "")
            creds["GROQ_URL"] = config.get("GROQ_URL", "")
            creds["DISCOGS_TOKEN"] = config.get("DISCOGS_TOKEN", "")
        except Exception:
            pass
            
    return creds

CREDS = carregar_credencials()
CLIENT_ID = CREDS["CLIENT_ID"]
CLIENT_SECRET = CREDS["CLIENT_SECRET"]
GROQ_KEY = CREDS["GROQ_KEY"]
GROQ_URL = CREDS["GROQ_URL"]
DISCOGS_TOKEN = CREDS["DISCOGS_TOKEN"]

# ============================================================
# 5. MODEL IA
# ============================================================
def obtenir_model_ia():
    if not GROQ_URL or not GROQ_KEY:
        return "llama-3.3-70b-versatile"
    try:
        url_models = GROQ_URL.replace("/chat/completions", "/models")
        headers = {"Authorization": f"Bearer {GROQ_KEY}"}
        resposta = requests.get(url_models, headers=headers, timeout=5)
        if resposta.status_code == 200:
            models_data = resposta.json().get("data", [])
            ids = [m.get("id") for m in models_data if m.get("status") == "active" or not m.get("status")]
            for m_id in ids:
                if "llama" in m_id.lower() and "70b" in m_id.lower():
                    return m_id
            if ids: return ids[0]
    except Exception:
        pass
    return "llama-3.3-70b-versatile"

MODEL_IA = obtenir_model_ia() if GROQ_KEY else None

# ============================================================
# 6. DETECTAR TIPUS DE CERCA
# ============================================================
def detectar_tipus_cerca(any_triat, mes_triat="Indiferent"):
    any_actual = datetime.now().year

    if any_triat == "Indiferent":
        return "classics"

    if "/" in any_triat:
        parts = any_triat.split("/")
        try:
            any_max = int(parts[1].strip())
        except:
            any_max = any_actual
    else:
        try:
            any_max = int(any_triat.strip())
        except:
            any_max = any_actual

    if mes_triat != "Indiferent":
        return "novetats"

    if any_max >= any_actual - 1:
        return "novetats"
    else:
        return "classics"

# ============================================================
# 7. IA: TROBAR ARTISTES
# ============================================================
def trobar_artistes_passada1(estil, any_triat, referencia=""):
    if not GROQ_KEY or not GROQ_URL:
        artistes_db = consultar_artistes_db(estil, min_confiança="probable")
        if artistes_db:
            return [(nom, sub) for nom, sub, conf in artistes_db]
        return []

    tipus_cerca = detectar_tipus_cerca(any_triat)
    artistes_db = consultar_artistes_db(estil, min_confiança="probable")
    rebutjats_db = consultar_rebutjats_db(estil)

    headers = {"Authorization": f"Bearer {GROQ_KEY}", "Content-Type": "application/json"}
    context_db = ""
    if artistes_db:
        context_db = "ARTISTES JA CONEGUTS A LA BASE DE DADES:\n"
        for nom, sub, conf in artistes_db[:15]:
            context_db += f"- {nom} ({sub}) [{conf}]\n"
    if rebutjats_db:
        context_db += "\nARTISTES REBUTJATS (NO els incloguis):\n"
        for nom in list(rebutjats_db)[:10]:
            context_db += f"- {nom}\n"

    if tipus_cerca == "novetats":
        instruccions_any = f"L'usuari busca NOVETATS de l'any {any_triat}. Troba artistes actius que publiquin musica nova."
    else:
        instruccions_any = f"L'usuari busca CLASSICS/TOP de l'any {any_triat}. Troba artistes classics i emblematics."

    context_ref = ""
    if referencia.strip():
        context_ref = f"\nATENCIÓ! L'usuari ha indicat una REFERÈNCIA CLAU: '{referencia}'. És OBLIGATORI trobar productors/artistes que facin EXACTAMENT aquest mateix so musical.\n"

    prompt = f"""Ets un expert musical purista. L'usuari busca musica EXACTA de l'estil: "{estil}"
{context_ref}
{context_db}

{instruccions_any}

REGLAS ESTRICTES:
1. Respon NOMES amb noms d'ARTISTES REALS, un per linia.
2. FORMAT OBLIGATORI per cada linia: NOM_ARTISTE | GENERE_PRINCIPAL
3. NO escriguis frases explicatives ni numeros de llista.
4. DESCARTA AUTOMATICAMENT qualsevol artista que no toqui aquest subgenere exacte.
5. Maxim 50 artistes."""

    data = {"model": MODEL_IA, "messages": [{"role": "user", "content": prompt}], "temperature": 0.2, "max_tokens": 1500}

    try:
        res = requests.post(GROQ_URL, headers=headers, json=data, timeout=20)
        if res.status_code == 200:
            resposta = res.json()["choices"][0]["message"]["content"].strip()

            if "SENSE_RESULTATS" in resposta or len(resposta) < 10:
                if artistes_db:
                    return [(nom, sub) for nom, sub, conf in artistes_db]
                seeds = obtenir_seeds_genere(estil)
                if seeds:
                    return [(s, "seed") for s in seeds]
                return []

            artistes = []
            for linia in resposta.splitlines():
                linia = linia.strip()
                if not linia or len(linia) > 60:
                    continue
                if linia.startswith(("-", "*", ">")):
                    continue

                if "|" in linia:
                    parts = linia.split("|")
                    if len(parts) >= 2:
                        nom = parts[0].strip()
                        genere = parts[1].strip()
                        if nom and 2 < len(nom) < 50 and nom not in rebutjats_db:
                            artistes.append((nom, genere))

            if artistes:
                noms_nous = {a[0].lower() for a in artistes}
                for nom, sub, conf in artistes_db:
                    if nom.lower() not in noms_nous:
                        artistes.insert(0, (nom, sub))
                return artistes
        return []
    except Exception as e:
        if artistes_db:
            return [(nom, sub) for nom, sub, conf in artistes_db]
        seeds = obtenir_seeds_genere(estil)
        if seeds:
            return [(s, "seed") for s in seeds]
        return []

def validar_artistes_passada2(artistes, estil, any_triat):
    if not artistes or not GROQ_KEY or not GROQ_URL:
        return [(nom, gen, "probable") for nom, gen in artistes]

    headers = {"Authorization": f"Bearer {GROQ_KEY}", "Content-Type": "application/json"}
    llista_text = "\n".join([f"{i+1}. {nom} ({genere})" for i, (nom, genere) in enumerate(artistes)])
    tipus_cerca = detectar_tipus_cerca(any_triat)
    context_any = "novetats recents" if tipus_cerca == "novetats" else f"classics del periode {any_triat}"

    prompt = f"""Ets un expert musical. Revisa aquesta llista d'artistes per l'estil "{estil}" ({context_any}).

LLISTA:
{llista_text}

REGLAS ESTRICTES:
1. Descarta qualsevol que NO toqui realment l'estil "{estil}".
2. FORMAT OBLIGATORI per cada linia: NOM_ARTISTE | GENERE | CONFIANCA
3. CONFIANCA pot ser: segur o probable
4. NO escriguis frases explicatives, introduccions ni conclusions.
5. NO escriguis numeros de llista."""

    data = {"model": MODEL_IA, "messages": [{"role": "user", "content": prompt}], "temperature": 0.1, "max_tokens": 1500}

    try:
        res = requests.post(GROQ_URL, headers=headers, json=data, timeout=20)
        if res.status_code == 200:
            resposta = res.json()["choices"][0]["message"]["content"].strip()

            if "CAP_VALID" in resposta or len(resposta) < 10:
                return [(nom, gen, "probable") for nom, gen in artistes]

            artistes_validats = []
            for linia in resposta.splitlines():
                linia = linia.strip()
                if not linia or len(linia) > 60:
                    continue
                if "|" in linia:
                    parts = linia.split("|")
                    if len(parts) >= 3:
                        nom = parts[0].strip()
                        genere = parts[1].strip()
                        conf = parts[2].strip().lower()
                        if nom and 2 < len(nom) < 50:
                            artistes_validats.append((nom, genere, conf))
                    elif len(parts) == 2:
                        nom = parts[0].strip()
                        genere = parts[1].strip()
                        if nom and 2 < len(nom) < 50:
                            artistes_validats.append((nom, genere, "probable"))

            if artistes_validats:
                return artistes_validats
        return [(nom, gen, "probable") for nom, gen in artistes]
    except Exception:
        return [(nom, gen, "probable") for nom, gen in artistes]

# ============================================================
# 8. VALIDACIO DE SEGURETAT
# ============================================================
def validar_artista_seguretat(artista_nom):
    a_lower = artista_nom.lower()
    for neg in LLISTA_NEGRA:
        if neg in a_lower:
            return False
    return True

def validar_canco_seguretat(canco, artista_nom):
    artista_canco = canco["artista"].lower()
    a_lower = artista_nom.lower()
    for neg in LLISTA_NEGRA:
        if neg in artista_canco:
            return False
    if a_lower in artista_canco or artista_canco in a_lower:
        return True
    if len(artista_nom) <= 4:
        if artista_canco == a_lower:
            return True
        return False
    return True

# ============================================================
# 9. CERCA SPOTIFY / DISCOGS / DEEZER AMB FILTRES DE MES
# ============================================================
def obtenir_audio_features(sp, track_ids):
    # Apaguem la petició a Spotify per evitar l'error 403 i que l'app es pengi
    return {}

def obtenir_bpm_hibrid(artista, titol):
    """Motor híbrid per trobar el BPM esquivant el bloqueig de Spotify"""
    # 1. Intent Deezer
    try:
        url_search = f"https://api.deezer.com/search?q=artist:\"{artista}\" track:\"{titol}\"&limit=1"
        res = requests.get(url_search, timeout=2)
        if res.status_code == 200:
            data = res.json().get("data", [])
            if data:
                track_id = data[0]["id"]
                url_track = f"https://api.deezer.com/track/{track_id}"
                res_track = requests.get(url_track, timeout=2)
                if res_track.status_code == 200:
                    bpm = res_track.json().get("bpm", 0)
                    if bpm > 0:
                        return round(bpm, 1)
    except Exception:
        pass

    # 2. Intent iTunes API
    try:
        url_itunes = f"https://itunes.apple.com/search?term={requests.utils.quote(artista + ' ' + titol)}&entity=song&limit=1"
        res = requests.get(url_itunes, timeout=2)
        if res.status_code == 200:
            results = res.json().get("results", [])
            if results and "bpm" in results[0]:
                return round(results[0]["bpm"], 1)
    except Exception:
        pass
        
    return "N/D"

def key_to_string(key_num, mode_num):
    keys = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
    if key_num is None or key_num < 0 or key_num > 11:
        return "N/D"
    key_str = keys[key_num]
    if mode_num == 0:
        key_str += "m"
    return key_str

def cercar_spotify(sp, artista_nom, any_min, any_max, mes_min=None, mes_max=None, limit=20, tipus_cerca="novetats"):
    cancons = []
    if tipus_cerca == "classics":
        limit = max(limit, 50)
    track_ids = []
    cancons_temp = []
    try:
        query = f'artist:"{artista_nom}" year:{any_min}-{any_max}'
        resultats = sp.search(q=query, type="track", limit=limit)
        for track in resultats.get("tracks", {}).get("items", []):
            try:
                release_date = track.get("album", {}).get("release_date", "")
                parts_data = release_date.split("-")
                any_ll = int(parts_data[0])
                if any_min <= any_ll <= any_max:
                    if mes_min is not None and mes_max is not None and len(parts_data) > 1:
                        try:
                            mes_ll = int(parts_data[1])
                            if not (mes_min <= mes_ll <= mes_max):
                                continue
                        except:
                            pass
                    track_id = track["id"]
                    track_ids.append(track_id)
                    cancons_temp.append({
                        "artista": track["artists"][0]["name"],
                        "titol": track["name"],
                        "bpm": "N/D", "clau": "N/D", "any": any_ll,
                        "popularitat": track.get("popularity", 0),
                        "durada_ms": track.get("duration_ms", 0),
                        "spotify_uri": track["uri"],
                        "spotify_link": track["external_urls"]["spotify"],
                        "spotify_id": track_id,
                        "font": "Spotify"
                    })
            except:
                pass
    except Exception as e:
        log(f"Error Spotify {artista_nom}: {e}", "error")
    
    if track_ids:
        features = obtenir_audio_features(sp, track_ids)
        for canco in cancons_temp:
            tid = canco.get("spotify_id")
            if tid and tid in features:
                f = features[tid]
                canco["bpm"] = f["bpm"] if f["bpm"] else "N/D"
                canco["clau"] = key_to_string(f["key"], f["mode"])
                canco["energy"] = round(f["energy"], 2) if f["energy"] else "N/D"
                canco["danceability"] = round(f["danceability"], 2) if f["danceability"] else "N/D"
            if validar_canco_seguretat(canco, artista_nom):
                cancons.append(canco)
    return cancons

def cercar_discogs(artista_nom, any_min, any_max, mes_min=None, mes_max=None, limit=20, tipus_cerca="novetats"):
    cancons = []
    if tipus_cerca == "classics":
        limit = max(limit, 50)
    headers = {"User-Agent": "SuperDJBuscadorApp/1.0.0", "Accept": "application/json"}
    if DISCOGS_TOKEN:
        headers["Authorization"] = f"Discogs token={DISCOGS_TOKEN}"
    for any_actual in range(any_min, any_max + 1):
        try:
            url = f"https://api.discogs.com/database/search?artist={requests.utils.quote(artista_nom)}&year={any_actual}&type=master&per_page={limit}"
            resposta = requests.get(url, headers=headers, timeout=5)
            if resposta.status_code == 200:
                for r in resposta.json().get("results", [])[:limit]:
                    year = r.get("year")
                    if year and any_min <= year <= any_max:
                        canco = {
                            "artista": r.get("artist", artista_nom), "titol": r.get("title", ""),
                            "bpm": "N/D", "clau": "N/D", "any": year,
                            "popularitat": "N/D", "durada_ms": "N/D",
                            "spotify_uri": None, "spotify_link": None,
                            "discogs_link": r.get("resource_url", ""), "font": "Discogs"
                        }
                        if validar_canco_seguretat(canco, artista_nom):
                            cancons.append(canco)
            time.sleep(0.5)
        except Exception:
            pass
    return cancons

def cercar_musicbrainz(artista_nom, any_min, any_max, mes_min=None, mes_max=None, limit=20, tipus_cerca="novetats"):
    cancons = []
    if tipus_cerca == "classics":
        limit = max(limit, 50)
    headers = {"User-Agent": "SuperDJBuscadorApp/1.0.0", "Accept": "application/json"}
    try:
        url = f"https://musicbrainz.org/ws/2/artist/?query=artist:{requests.utils.quote(artista_nom)}&fmt=json"
        res = requests.get(url, headers=headers, timeout=5)
        if res.status_code == 200:
            artistes = res.json().get("artists", [])
            if artistes:
                artista_id = artistes[0].get("id")
                url2 = f"https://musicbrainz.org/ws/2/recording/?query=arid:{artista_id} AND date:[{any_min} TO {any_max}]&fmt=json&limit={limit}"
                res2 = requests.get(url2, headers=headers, timeout=5)
                if res2.status_code == 200:
                    for grav in res2.json().get("recordings", []):
                        try:
                            date = grav.get("first-release-date", "")
                            any_grav = int(date.split("-")[0]) if date else any_min
                            if any_min <= any_grav <= any_max:
                                canco = {
                                    "artista": artista_nom, "titol": grav.get("title", ""),
                                    "bpm": "N/D", "clau": "N/D", "any": any_grav,
                                    "popularitat": "N/D", "durada_ms": "N/D",
                                    "spotify_uri": None, "spotify_link": None, "font": "MusicBrainz"
                                }
                                if validar_canco_seguretat(canco, artista_nom):
                                    cancons.append(canco)
                        except:
                            pass
                time.sleep(1)
    except Exception:
        pass
    return cancons

def cercar_deezer(artista_nom, any_min, any_max, mes_min=None, mes_max=None, limit=20, tipus_cerca="novetats"):
    cancons = []
    if tipus_cerca == "classics":
        limit = max(limit, 50)
    try:
        url = f"https://api.deezer.com/search/track?q=artist:{requests.utils.quote(artista_nom)}&limit={limit}"
        res = requests.get(url, timeout=5)
        if res.status_code == 200:
            for track in res.json().get("data", []):
                try:
                    release_date = track.get("album", {}).get("release_date", "")
                    parts_data = release_date.split("-")
                    any_ll = int(parts_data[0])
                    if any_min <= any_ll <= any_max:
                        if mes_min is not None and mes_max is not None and len(parts_data) > 1:
                            try:
                                mes_ll = int(parts_data[1])
                                if not (mes_min <= mes_ll <= mes_max):
                                    continue
                            except:
                                pass
                        canco = {
                            "artista": track["artist"]["name"], "titol": track["title"],
                            "bpm": "N/D", "clau": "N/D", "any": any_ll,
                            "popularitat": track.get("rank", "N/D"), "durada_ms": track.get("duration", 0) * 1000,
                            "spotify_uri": None, "spotify_link": None,
                            "deezer_link": track.get("link", ""), "font": "Deezer"
                        }
                        if validar_canco_seguretat(canco, artista_nom):
                            cancons.append(canco)
                except:
                    pass
    except Exception:
        pass
    return cancons

# ============================================================
# 10. UTILITATS AVANÇADES
# ============================================================
def eliminar_duplicats(cancons):
    vistes = set()
    uniques = []
    for c in cancons:
        clau = f"{c['artista'].lower().strip()}|{c['titol'].lower().strip()}"
        if clau not in vistes:
            vistes.add(clau)
            uniques.append(c)
    return uniques

def limitar_cancons_per_artista(cancons, max_per_artista=3):
    contador = {}
    resultat = []
    cancons_ordenades = sorted(cancons, key=lambda x: x.get("popularitat", 0) if isinstance(x.get("popularitat"), (int, float)) else 0, reverse=True)
    for canco in cancons_ordenades:
        artista = canco["artista"].lower().strip()
        contador[artista] = contador.get(artista, 0) + 1
        if contador[artista] <= max_per_artista:
            resultat.append(canco)
    return resultat

def ordenar_cancons_intelligent(cancons, criteri="popularitat"):
    if criteri == "popularitat":
        return sorted(cancons, key=lambda x: x.get("popularitat", 0) if isinstance(x.get("popularitat"), (int, float)) else 0, reverse=True)
    elif criteri == "bpm":
        return sorted(cancons, key=lambda x: x.get("bpm", 0) if isinstance(x.get("bpm"), (int, float)) else 999)
    elif criteri == "any":
        return sorted(cancons, key=lambda x: x.get("any", 0), reverse=True)
    elif criteri == "aleatori":
        import random
        random.shuffle(cancons)
        return cancons
    else:
        return cancons

def verificar_uris(sp, cancons):
    verificades = []
    for c in cancons:
        if c.get("spotify_uri"):
            verificades.append(c)
            continue
        try:
            resultats = sp.search(q=f"track:{c['titol']} artist:{c['artista']}", type="track", limit=1)
            tracks = resultats.get("tracks", {}).get("items", [])
            if tracks:
                track = tracks[0]
                c["spotify_uri"] = track["uri"]
                c["spotify_link"] = track["external_urls"]["spotify"]
                if c.get("popularitat") == "N/D" or c.get("popularitat") == 0:
                    c["popularitat"] = track.get("popularity", 0)
                verificades.append(c)
        except Exception:
            pass
        time.sleep(0.1)
    return verificades

# ============================================================
# 11. SESSION STATE
# ============================================================
if 'cancons_reals' not in st.session_state:
    st.session_state.cancons_reals = []
if 'uris_spotify' not in st.session_state:
    st.session_state.uris_spotify = []
if 'text_copiar' not in st.session_state:
    st.session_state.text_copiar = ""
if 'titol_playlist' not in st.session_state:
    st.session_state.titol_playlist = "Nova Playlist"
if 'input_estil' not in st.session_state:
    st.session_state.input_estil = "Makina"
if 'genere_aprendre_seleccionat' not in st.session_state:
    st.session_state.genere_aprendre_seleccionat = "Makina"
if 'artistes_aprendre_text' not in st.session_state:
    st.session_state.artistes_aprendre_text = ""
if 'artistes_processats_feedback' not in st.session_state:
    st.session_state.artistes_processats_feedback = set()
if 'feedback_timestamp' not in st.session_state:
    st.session_state.feedback_timestamp = 0
if 'artistes_ultima_cerca' not in st.session_state:
    st.session_state.artistes_ultima_cerca = []

# ============================================================
# 12. INTERFICIE PRINCIPAL AMB PESTANYES
# ============================================================
if CLIENT_ID and CLIENT_SECRET:
    try:
        sp = spotipy.Spotify(auth_manager=SpotifyOAuth(
            client_id=CLIENT_ID, client_secret=CLIENT_SECRET,
            redirect_uri=REDIRECT_URI, scope="playlist-modify-public"
        ))
        usuari_sp = sp.current_user()

        st.markdown(f"""
        <div style="display: flex; align-items: center; gap: 15px; margin-bottom: 20px; padding: 15px; background: linear-gradient(90deg, #1a1a2e 0%, #16213e 100%); border-radius: 10px; border: 1px solid #333;">
            <div style="font-size: 32px;">🎛️</div>
            <div>
                <div style="font-size: 24px; font-weight: bold; color: #00ff88;">Rastrejador de Novetats Reals</div>
                <div style="font-size: 14px; color: #888;">Spotify: <span style="color: #1DB954;">●</span> {usuari_sp['display_name']} | IA: {MODEL_IA or "No disponible"} | Discogs: {"Actiu" if DISCOGS_TOKEN else "Sense token"}</div>
            </div>
            <div style="margin-left: auto; background: #0a0a0a; padding: 5px 15px; border-radius: 20px; border: 1px solid #333;">
                <span style="color: #00ff88; font-weight: bold; font-size: 12px;">📦 v2.0.0</span>
            </div>
        </div>
        """, unsafe_allow_html=True)

        tab_cercar, tab_aprendre = st.tabs(["🔍 Cercar Cançons", "🎓 Aprendre"])

        # ========================================================
        # PESTANYA 1: APRENDRE
        # ========================================================
        with tab_aprendre:
            def actualitzar_estil_aprendre():
                if st.session_state.sel_genere_guardat != "-- Nou --":
                    st.session_state.input_genere_aprendre = st.session_state.sel_genere_guardat

            st.header("🎓 Ensenyar Artistes al Programa")
            st.write("Introdueix una llista d'artistes d'un estil concret. El programa els guardarà a la base de dades.")

            col_a1, col_a2 = st.columns([2, 1])

            with col_a1:
                tots_generes = obtenir_tots_generes_db()
                genere_actual = st.session_state.get("input_genere_aprendre", "Makina")
                info_actual = obtenir_genere_inteligent(genere_actual)
                color_act = info_actual[3] if info_actual else "#00ff88"
                icona_act = info_actual[4] if info_actual else "🎵"

                col_gen1, col_gen2, col_gen3 = st.columns([2, 1, 1])
                
                with col_gen1:
                    genere_aprendre = st.text_input("Genere / Estil:", key="input_genere_aprendre")
                
                with col_gen2:
                    if tots_generes:
                        genere_seleccionat = st.selectbox("Guardats:", ["-- Nou --"] + tots_generes, key="sel_genere_guardat", on_change=actualitzar_estil_aprendre)
                        if genere_seleccionat != "-- Nou --":
                            genere_aprendre = genere_seleccionat

                with col_gen3:
                    st.markdown(f"""
                    <style>
                    div[data-testid="stVerticalBlock"] div[data-testid="stHorizontalBlock"] div:nth-child(3) button[kind="secondary"] {{
                        background-color: {color_act}22 !important;
                        border: 2px solid {color_act} !important;
                        color: {color_act} !important;
                        font-weight: bold !important;
                    }}
                    </style>
                    """, unsafe_allow_html=True)
                    if st.button(f"{icona_act} Carregar", key="btn_genere_dynamic", use_container_width=True):
                        artistes_gen = obtenir_artistes_per_genere(genere_actual)
                        if artistes_gen:
                            st.session_state.artistes_aprendre_text = "\n".join([a[0] for a in artistes_gen])
                        else:
                            st.session_state.artistes_aprendre_text = info_actual[2].replace(", ", "\n") if (info_actual and info_actual[2]) else ""
                        st.rerun()

                artistes_text = st.text_area(
                    "Llista d'artistes (un per linia):",
                    value=st.session_state.artistes_aprendre_text,
                    height=300,
                    key="ta_artistes_aprendre"
                )

                col_btn1, col_btn2, col_btn3 = st.columns(3)

                with col_btn1:
                    if st.button("💾 Guardar a la DB", key="btn_guardar_aprendre", use_container_width=True):
                        if artistes_text.strip() and genere_aprendre.strip():
                            artistes_parsed = parsejar_llista_artistes(artistes_text)
                            if artistes_parsed:
                                count = guardar_llista_artistes_confirmats(artistes_parsed, genere_aprendre)
                                info_genere = detectar_estils_genere(genere_aprendre)
                                seeds_text = ", ".join(artistes_parsed[:15]) if artistes_parsed else info_genere["seeds"]
                                guardar_genere_inteligent(genere_aprendre, estils=info_genere["estils"], seeds=seeds_text, color=info_genere["color"], icona=info_genere["icona"])
                                st.success(f"✅ {count} artistes guardats a la base de dades!")
                                st.session_state.artistes_aprendre_text = artistes_text
                                st.balloons()
                            else:
                                st.warning("No s'han trobat noms d'artistes.")
                        else:
                            st.warning("Introdueix un genere i artistes.")

                with col_btn2:
                    if st.button("📋 Veure Guardats", key="btn_veure_aprendre", use_container_width=True):
                        artistes_db = consultar_artistes_db(genere_aprendre, min_confiança="probable")
                        if artistes_db:
                            st.info(f"**Artistes per \"{genere_aprendre}\":**\n\n" + "\n".join([f"• {a} ({g}) [{c}]" for a, g, c in artistes_db]))
                        else:
                            st.info(f"No hi ha artistes guardats per \"{genere_aprendre}\".")

                with col_btn3:
                    if st.button("🗑️ Esborrar Genere", key="btn_esborrar_aprendre", use_container_width=True):
                        conn = db_conn()
                        cursor = conn.cursor()
                        cursor.execute("DELETE FROM artistes_confirmats WHERE LOWER(genere) = LOWER(?)", (genere_aprendre,))
                        cursor.execute("DELETE FROM artistes_rebutjats WHERE LOWER(genere) = LOWER(?)", (genere_aprendre,))
                        cursor.execute("DELETE FROM cancons_confirmades WHERE LOWER(genere) = LOWER(?)", (genere_aprendre,))
                        cursor.execute("DELETE FROM generes_apresos WHERE LOWER(nom_genere) = LOWER(?)", (genere_aprendre,))
                        conn.commit()
                        conn.close()
                        st.warning(f"🗑️ Genere \"{genere_aprendre}\" esborrat.")

            with col_a2:
                st.subheader("📊 Estadistiques")
                stats = obtenir_estadistiques_db()
                st.metric("Artistes Confirmats", stats["artistes_confirmats"])
                st.metric("Artistes Rebutjats", stats["artistes_rebutjats"])
                st.metric("Cançons Confirmades", stats["cancons_confirmades"])
                st.metric("Generes Apresos", stats["generes_apresos"])

        # ========================================================
        # PESTANYA 2: CERCAR CANÇONS
        # ========================================================
        with tab_cercar:
            def actualitzar_estil_cerca():
                if st.session_state.sel_genere_cercar != "-- Manual --":
                    st.session_state.input_estil = st.session_state.sel_genere_cercar

            col_esquerra, col_dreta = st.columns([1, 2])

            with col_esquerra:
                st.markdown("""
                <div style="background: #1a1a2e; padding: 10px 15px; border-radius: 8px; margin-bottom: 15px; border-left: 3px solid #00ff88;">
                    <span style="color: #00ff88; font-weight: bold; font-size: 16px;">🔍 Controls de Cerca</span>
                </div>
                """, unsafe_allow_html=True)

                generes_guardats_cercar = obtenir_tots_generes_db()
                if generes_guardats_cercar:
                    col_estil1, col_estil2 = st.columns([2, 1])
                    with col_estil1:
                        estil_triat = st.text_input("Estil / Genere:", key="input_estil")
                    with col_estil2:
                        genere_cercar_sel = st.selectbox("Guardats:", ["-- Manual --"] + generes_guardats_cercar, key="sel_genere_cercar", on_change=actualitzar_estil_cerca)
                        if genere_cercar_sel != "-- Manual --":
                            estil_triat = genere_cercar_sel
                else:
                    estil_triat = st.text_input("Estil / Genere:", key="input_estil")

                referencia_triada = st.text_input("🎯 Referència clau (Artista o Cançó):", key="input_referencia", placeholder="Ex: Charlotte de Witte, Pont Aeri...")

                col_mes, col_any = st.columns(2)
                with col_mes:
                    mes_triat = st.selectbox("Mes:", MESES_NOMS, index=0, key="sel_mes")
                with col_any:
                    any_triat = st.selectbox("Any:", ANYS_DISPONIBLES, index=len(ANYS_DISPONIBLES)-2, key="sel_any")
                    any_manual = st.text_input("O rang (Ex: 2025/2026):", "", key="input_any_manual")
                    if any_manual.strip():
                        any_triat = any_manual.strip()

                tipus_detectat = detectar_tipus_cerca(any_triat, mes_triat)
                if tipus_detectat == "novetats":
                    st.info("🔴 Mode NOVETATS actiu")
                else:
                    st.info("🟢 Mode CLASSICS actiu")

                st.markdown("**Filtres Físics (Anti-Morralla):**")
                col_bpm1, col_bpm2, col_q = st.columns(3)
                with col_bpm1:
                    bpm_min = st.number_input("BPM Mínim:", min_value=60, max_value=250, value=140, step=1, key="input_bpm_min")
                with col_bpm2:
                    bpm_max = st.number_input("BPM Màxim:", min_value=60, max_value=250, value=170, step=1, key="input_bpm_max")
                with col_q:
                    quantitat = st.number_input("Cançons objectiu:", min_value=10, max_value=300, value=100, step=10, key="input_quantitat")
                
                max_per_artista = st.number_input("Max cançons per artista:", min_value=1, max_value=15, value=5, step=1, key="input_max_artista")
                
                ordenacio = st.selectbox("Ordenar per:", ["popularitat", "bpm", "any", "aleatori"], index=0, key="sel_ordenacio")
                min_conf = st.selectbox("Min confiança DB:", ["segur", "probable", "dubtos"], index=1, key="sel_conf")

                col_rastreig, col_refrescar = st.columns(2)
                with col_rastreig:
                    btn_rastreig = st.button("🔍 Comencar Rastreig", key="btn_rastreig", use_container_width=True)
                with col_refrescar:
                    if st.button("🔄 Refrescar DB", key="btn_refrescar_db", use_container_width=True):
                        artistes_db = consultar_artistes_db(estil_triat, min_confiança=min_conf)
                        if artistes_db:
                            st.session_state.artistes_ultima_cerca = [(nom, sub, conf) for nom, sub, conf in artistes_db]
                            st.success(f"🔄 {len(artistes_db)} artistes carregats!")
                        else:
                            st.warning("Sense artistes a la DB.")
                            st.session_state.artistes_ultima_cerca = []
                        st.rerun()

                # === ESPAI DINÀMIC PER A LA CONSOLA (Matrix Style) ===
                consola_placeholder = st.empty()
                with consola_placeholder:
                    render_console()
                    
                if st.button("Netejar Consola", key="btn_netejar"):
                    clear_console()
                    st.rerun()

                if btn_rastreig:
                    any_min_r, any_max_r, mes_min_r, mes_max_r = parsejar_any_mes(any_triat, mes_triat)
                    tipus_cerca = detectar_tipus_cerca(any_triat, mes_triat)

                    with st.status("🚀 Iniciant rastreig musical...", expanded=True) as status:
                        
                        status.update(label="🧠 1/4: Consultant IA per trobar artistes...", state="running")
                        artistes_passada1 = trobar_artistes_passada1(estil_triat, any_triat, referencia_triada)
                        
                        if not artistes_passada1:
                            status.update(label="❌ Error: La IA no ha trobat artistes.", state="error")
                            st.error("La IA no ha pogut identificar artistes.")
                        else:
                            artistes_validats = validar_artistes_passada2(artistes_passada1, estil_triat, any_triat)
                            
                            st.session_state.artistes_processats_feedback = set()
                            st.session_state.feedback_timestamp = time.time()

                            status.update(label=f"🌐 2/4: Rastrejant {len(artistes_validats)} artistes a les bases de dades...", state="running")
                            totes_cancons = []
                            for artista_nom, artista_genere, confiança in artistes_validats:
                                if not validar_artista_seguretat(artista_nom):
                                    continue

                                cancons_spotify = cercar_spotify(sp, artista_nom, any_min_r, any_max_r, mes_min_r, mes_max_r, limit=15, tipus_cerca=tipus_cerca)
                                cancons_discogs = cercar_discogs(artista_nom, any_min_r, any_max_r, mes_min_r, mes_max_r, limit=15, tipus_cerca=tipus_cerca)
                                cancons_mb = cercar_musicbrainz(artista_nom, any_min_r, any_max_r, mes_min_r, mes_max_r, limit=15, tipus_cerca=tipus_cerca)
                                cancons_deezer = cercar_deezer(artista_nom, any_min_r, any_max_r, mes_min_r, mes_max_r, limit=15, tipus_cerca=tipus_cerca)

                                totes_cancons.extend(cancons_spotify + cancons_discogs + cancons_mb + cancons_deezer)

                            cancons_uniques = eliminar_duplicats(totes_cancons)
                            cancons_limitades = limitar_cancons_per_artista(cancons_uniques, max_per_artista)
                            cancons_ordenades = ordenar_cancons_intelligent(cancons_limitades, ordenacio)
                            
                            status.update(label=f"⚙️ 3/4: Analitzant BPMs i filtrant (Motor Híbrid Anti-Ban)...", state="running")
                            
                            barra_progres = st.progress(0)
                            text_progres = st.empty()
                            
                            cancons_100x100_pures = []
                            mida_lot = 10 
                            
                            for i in range(0, len(cancons_ordenades), mida_lot):
                                if len(cancons_100x100_pures) >= quantitat:
                                    break
                                    
                                lot_actual = cancons_ordenades[i:i + mida_lot]
                                
                                for c in lot_actual:
                                    if len(cancons_100x100_pures) >= quantitat:
                                        break
                                        
                                    percentatge_actual = int((len(cancons_100x100_pures) / quantitat) * 100)
                                    text_progres.markdown(f"**Progrés:** {percentatge_actual}% - 🔍 Analitzant: *{c['artista']} - {c['titol']}*")
                                    
                                    # Extracció Híbrida i Log Dinàmic
                                    if c["bpm"] == "N/D":
                                        c["bpm"] = obtenir_bpm_hibrid(c["artista"], c["titol"])
                                        
                                        if c["bpm"] != "N/D":
                                            log(f"⚡ BPM Trobat: {c['artista']} - {c['titol']} -> {c['bpm']}", "info")
                                        
                                        with consola_placeholder:
                                            render_console()
                                        
                                    if c["bpm"] != "N/D":
                                        try:
                                            if bpm_min <= float(c["bpm"]) <= bpm_max:
                                                cancons_100x100_pures.append(c)
                                                log(f"✅ Afegida (Pur): {c['artista']} - {c['bpm']} BPM", "success")
                                            else:
                                                log(f"❌ Descartada (Fora de rang): {c['artista']} - {c['bpm']} BPM", "error")
                                            
                                            with consola_placeholder:
                                                render_console()
                                        except ValueError:
                                            pass
                                            
                                    prog = min(1.0, len(cancons_100x100_pures) / quantitat)
                                    barra_progres.progress(prog)
                                    time.sleep(0.1)
                                
                                if len(cancons_100x100_pures) < quantitat and (i + mida_lot) < len(cancons_ordenades):
                                    text_progres.markdown(f"**Progrés:** {percentatge_actual}% - ⏱️ *Pausa de seguretat (Anti-Ban) de 2 segons...*")
                                    time.sleep(2.0)
                                
                            text_progres.empty()
                            barra_progres.empty()
                            
                            status.update(label="✅ 4/4: Rastreig completat amb èxit!", state="complete")
                            
                            cancons_finals_verificades = verificar_uris(sp, cancons_100x100_pures)
                            
                            processades = []
                            uris = []
                            text = ""
                            for idx, c in enumerate(cancons_finals_verificades, 1):
                                processades.append({
                                    "NUM": idx, "ARTISTA": c["artista"], "TITOL": c["titol"],
                                    "BPM": c["bpm"], "CLAU": c["clau"], "ANY": c["any"],
                                    "POPULARITAT": c.get("popularitat", "N/D"),
                                    "ESTIL": estil_triat, "FONT": c["font"],
                                    "SPOTIFY": c.get("spotify_link") or "No trobat"
                                })
                                
                                if c.get("spotify_uri"):
                                    uris.append(c["spotify_uri"])
                                    
                                text += f"{idx}. {c['artista']} - {c['titol']} ({c['any']}) [BPM:{c['bpm']}]\n"

                                guardar_canco_confirmada(
                                    c["titol"], c["artista"], estil_triat, c["any"],
                                    c.get("bpm") if isinstance(c.get("bpm"), (int, float)) else None,
                                    c.get("clau"),
                                    c.get("popularitat") if isinstance(c.get("popularitat"), int) else None,
                                    c["font"], c.get("spotify_uri")
                                )

                            st.session_state.cancons_reals = processades
                            st.session_state.uris_spotify = uris
                            st.session_state.text_copiar = text
                            st.session_state.titol_playlist = f"{estil_triat} ({any_triat})"
                            
                            # === NOU BUGFIX: NOMÉS ELS ARTISTES PURS AL FEEDBACK ===
                            artistes_finals_reals = set(c["ARTISTA"] for c in processades)
                            artistes_per_feedback = []
                            for nom, gen, conf in artistes_validats:
                                if nom in artistes_finals_reals:
                                    artistes_per_feedback.append((nom, gen, conf))
                            
                            st.session_state.artistes_ultima_cerca = artistes_per_feedback
                            
                            actualitzar_estadistiques_genere(estil_triat)

            with col_dreta:
                if st.session_state.artistes_ultima_cerca:
                    st.markdown("""
                    <div style="background: #1a1a2e; padding: 10px 15px; border-radius: 8px; margin-bottom: 15px; border-left: 3px solid #f59e0b;">
                        <span style="color: #f59e0b; font-weight: bold; font-size: 16px;">🧠 Feedback Artistes</span>
                    </div>
                    """, unsafe_allow_html=True)

                    for i, (artista, genere, conf) in enumerate(st.session_state.artistes_ultima_cerca):
                        if artista in st.session_state.artistes_processats_feedback:
                            continue
                        cols = st.columns([3, 1, 1])
                        with cols[0]:
                            url_artista = f"https://open.spotify.com/search/{requests.utils.quote(artista)}/artists"
                            st.markdown(f"**{artista}** ({genere}) [{conf}] &nbsp; <a href='{url_artista}' target='_blank' style='color:#1DB954; text-decoration:none; font-weight:bold;'>🎧 Auditar</a>", unsafe_allow_html=True)
                        with cols[1]:
                            if st.button(f"✅ Si", key=f"btn_si_{i}_{st.session_state.feedback_timestamp}"):
                                guardar_artista_confirmat(artista, estil_triat, genere, "usuari", "segur")
                                st.session_state.artistes_processats_feedback.add(artista)
                                st.rerun()
                        with cols[2]:
                            if st.button(f"❌ No", key=f"btn_no_{i}_{st.session_state.feedback_timestamp}"):
                                guardar_artista_rebutjat(artista, estil_triat, "No es del genere")
                                st.session_state.artistes_processats_feedback.add(artista)
                                st.rerun()

                st.divider()

                if st.session_state.cancons_reals:
                    df = pd.DataFrame(st.session_state.cancons_reals)
                    
                    st.dataframe(
                        df, 
                        use_container_width=True, 
                        hide_index=True,
                        column_config={
                            "SPOTIFY": st.column_config.LinkColumn(
                                "SPOTIFY",
                                display_text="🎧 Obrir Cançó"
                            )
                        }
                    )

                    nom_llista = st.text_input("Nom de la playlist:", value=st.session_state.titol_playlist, key="input_nom_playlist")
                    col1, col2 = st.columns(2)
                    with col1:
                        if st.session_state.uris_spotify and st.button("Crear Playlist", key="btn_crear", use_container_width=True):
                            try:
                                pl = sp.user_playlist_create(user=usuari_sp['id'], name=nom_llista, public=True)
                                for i in range(0, len(st.session_state.uris_spotify), 100):
                                    sp.playlist_add_items(playlist_id=pl['id'], items=st.session_state.uris_spotify[i:i+100])
                                st.success("Playlist creada!")
                                st.link_button("Obrir Playlist", pl["external_urls"]["spotify"])
                            except Exception as e:
                                st.error(f"Error: {e}")
                    with col2:
                        st.text_area("Copiar llista:", value=st.session_state.text_copiar, height=120, key="ta_copiar")
                        csv = df.to_csv(index=False, encoding='utf-8-sig')
                        st.download_button(label="Descarregar CSV", data=csv, file_name=f"{st.session_state.titol_playlist}.csv", mime="text/csv", key="btn_download")

    except Exception as e:
        st.error(f"Error de sistema: {e}")
else:
    st.error("Falten credencials de Spotify.")