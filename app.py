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

st.set_page_config(page_title="Rastrejador de Novetats Reals", page_icon="🎛️", layout="wide")

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
        WHERE genere = ? 
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
    cursor.execute("SELECT nom FROM artistes_rebutjats WHERE genere = ?", (genere,))
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

init_db()

# ============================================================
# 3. LLISTA NEGRA
# ============================================================
LLISTA_NEGRA = ["tuyo", "rimsky-korsakov", "mussorgsky", "modest mussorgsky", "nikolai rimsky-korsakov"]

# ============================================================
# 4. SISTEMA DE LOGS
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
    for entry in st.session_state.console_logs[-20:]:
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
    <div style="background: #0a0a0a; border: 2px solid #333; border-radius: 8px; padding: 10px; height: 280px; overflow-y: auto; font-family: Courier New, monospace; box-shadow: 0 0 20px rgba(0, 255, 136, 0.1);">
        <div style="position: sticky; top: 0; background: #1a1a1a; padding: 5px 10px; border-bottom: 1px solid #333; margin-bottom: 10px; border-radius: 4px; display: flex; justify-content: space-between; align-items: center;">
            <span style="color: #00ff88; font-weight: bold; font-size: 12px;">🖥️ CONSOLA</span>
            <span style="color: #888; font-size: 11px;">{len(st.session_state.console_logs)} registres</span>
        </div>
        {html}
    </div>
    """, unsafe_allow_html=True)

# ============================================================
# 5. CREDENCIALS
# ============================================================
def carregar_credencials():
    creds = {"CLIENT_ID": "", "CLIENT_SECRET": "", "GROQ_KEY": "", "GROQ_URL": "", "DISCOGS_TOKEN": ""}
    try:
        creds["CLIENT_ID"] = st.secrets.get("SPOTIFY_CLIENT_ID", "")
        creds["CLIENT_SECRET"] = st.secrets.get("SPOTIFY_CLIENT_SECRET", "")
        creds["GROQ_KEY"] = st.secrets.get("GROQ_KEY", "")
        creds["GROQ_URL"] = st.secrets.get("GROQ_URL", "")
        creds["DISCOGS_TOKEN"] = st.secrets.get("DISCOGS_TOKEN", "")
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
# 6. MODEL IA
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
# 7. DETECTAR TIPUS DE CERCA
# ============================================================
def detectar_tipus_cerca(any_triat):
    any_actual = datetime.now().year
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
    if any_max >= any_actual - 1:
        return "novetats"
    else:
        return "classics"

# ============================================================
# 8. IA: TROBAR ARTISTES
# ============================================================
def trobar_artistes_passada1(estil, any_triat):
    if not GROQ_KEY or not GROQ_URL:
        return []
    tipus_cerca = detectar_tipus_cerca(any_triat)
    artistes_db = consultar_artistes_db(estil, min_confiança="probable")
    rebutjats_db = consultar_rebutjats_db(estil)
    if artistes_db:
        log(f"DB: Trobats {len(artistes_db)} artistes confirmats de \"{estil}\"", "success")
    if rebutjats_db:
        log(f"DB: {len(rebutjats_db)} artistes rebutjats", "debug")

    headers = {"Authorization": f"Bearer {GROQ_KEY}", "Content-Type": "application/json"}
    context_db = ""
    if artistes_db:
        context_db = "ARTISTES JA CONEGUTS A LA BASE DE DADES (confirmats):\n"
        for nom, sub, conf in artistes_db[:15]:
            context_db += f"- {nom} ({sub}) [{conf}]\n"
    if rebutjats_db:
        context_db += "\nARTISTES QUE NO SON D'AQUEST ESTIL (rebutjats):\n"
        for nom in list(rebutjats_db)[:10]:
            context_db += f"- {nom}\n"

    if tipus_cerca == "novetats":
        instruccions_any = f"L'usuari busca NOVETATS de l'any {any_triat}. Troba artistes actius que publiquin musica nova."
    else:
        instruccions_any = f"L'usuari busca CLASSICS/TOP de l'any/periode {any_triat}. Troba artistes classics i emblematics."

    prompt = f"""Ets un expert musical. L'usuari busca musica de l'estil: \"{estil}\"
{context_db}
{instruccions_any}
INSTRUCCIONS:
1. Si hi ha artistes a la base de dades, MANTE-LOS i afegeix-ne de nous.
2. NO repeteixis artistes ja coneguts.
3. NO incloguis artistes de la llista de rebutjats.
4. Troba artistes REALS i EXISTENTS.
FORMAT (una linia per artiste):
NOM_ARTISTE | GENERE_PRINCIPAL
Respon NOMES amb la llista. Maxim 30 artistes."""

    data = {"model": MODEL_IA, "messages": [{"role": "user", "content": prompt}], "temperature": 0.2, "max_tokens": 2048}
    try:
        log(f"IA: Passada 1 - Mode {tipus_cerca.upper()}...", "info")
        res = requests.post(GROQ_URL, headers=headers, json=data, timeout=20)
        if res.status_code == 200:
            resposta = res.json()["choices"][0]["message"]["content"].strip()
            artistes = []
            for linia in resposta.split("\n"):
                linia = linia.strip()
                if not linia or linia.startswith("-") or linia.startswith("*"):
                    continue
                if "|" in linia:
                    parts = linia.split("|")
                    if len(parts) >= 2:
                        nom = parts[0].strip()
                        genere = parts[1].strip()
                        if nom and len(nom) > 1 and nom not in rebutjats_db:
                            artistes.append((nom, genere))
                else:
                    nom = linia.strip().strip(",").strip("-")
                    if nom and len(nom) > 1 and nom not in rebutjats_db:
                        artistes.append((nom, "desconegut"))
            log(f"IA: Passada 1 -> {len(artistes)} artistes trobats", "success")
            return artistes
        return []
    except Exception as e:
        log(f"Error IA passada 1: {e}", "error")
        return []

def validar_artistes_passada2(artistes, estil, any_triat):
    if not artistes or not GROQ_KEY or not GROQ_URL:
        return []
    headers = {"Authorization": f"Bearer {GROQ_KEY}", "Content-Type": "application/json"}
    llista_text = "\n".join([f"{i+1}. {nom} ({genere})" for i, (nom, genere) in enumerate(artistes)])
    tipus_cerca = detectar_tipus_cerca(any_triat)
    context_any = "novetats recents" if tipus_cerca == "novetats" else f"classics del periode {any_triat}"
    prompt = f"""Ets un expert musical. Revisa aquesta llista d'artistes per l'estil \"{estil}\" ({context_any}).
LLISTA:
{llista_text}
Descarta qualsevol que NO toqui realment l'estil. FORMAT: NOM_ARTISTE | GENERE | CONFIANCA (segur/probable)
Respon NOMES amb els validats."""
    data = {"model": MODEL_IA, "messages": [{"role": "user", "content": prompt}], "temperature": 0.1, "max_tokens": 2048}
    try:
        log("IA: Passada 2 - Validant artistes...", "info")
        res = requests.post(GROQ_URL, headers=headers, json=data, timeout=20)
        if res.status_code == 200:
            resposta = res.json()["choices"][0]["message"]["content"].strip()
            artistes_validats = []
            for linia in resposta.split("\n"):
                linia = linia.strip()
                if not linia or linia.startswith("-") or linia.startswith("*"):
                    continue
                if "|" in linia:
                    parts = linia.split("|")
                    if len(parts) >= 3:
                        nom = parts[0].strip()
                        genere = parts[1].strip()
                        conf = parts[2].strip().lower()
                        if nom and len(nom) > 1:
                            artistes_validats.append((nom, genere, conf))
                    elif len(parts) == 2:
                        nom = parts[0].strip()
                        genere = parts[1].strip()
                        if nom and len(nom) > 1:
                            artistes_validats.append((nom, genere, "probable"))
                else:
                    nom = linia.strip().strip(",").strip("-")
                    if nom and len(nom) > 1:
                        artistes_validats.append((nom, "desconegut", "probable"))
            segurs = sum(1 for _, _, c in artistes_validats if c == "segur")
            probables = sum(1 for _, _, c in artistes_validats if c == "probable")
            log(f"IA: Passada 2 -> {len(artistes_validats)} validats ({segurs} segurs, {probables} probables)", "success")
            return artistes_validats
        return []
    except Exception as e:
        log(f"Error IA passada 2: {e}", "error")
        return [(nom, gen, "probable") for nom, gen in artistes]

# ============================================================
# 9. VALIDACIO DE SEGURETAT
# ============================================================
def validar_artista_seguretat(artista_nom):
    a_lower = artista_nom.lower()
    for neg in LLISTA_NEGRA:
        if neg in a_lower:
            log(f"Filtrat (llista negra): {artista_nom}", "debug")
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
        log(f"Filtrat (nom curt): {canco['artista']} (buscant {artista_nom})", "debug")
        return False
    return True

# ============================================================
# 10. CERCA SPOTIFY AMB POPULARITAT, BPM, KEY
# ============================================================
def obtenir_audio_features(sp, track_ids):
    """Obté BPM, key i altres features de Spotify per lots de tracks"""
    features = {}
    if not track_ids:
        return features
    # Spotify permet max 100 IDs per crida
    for i in range(0, len(track_ids), 100):
        batch = track_ids[i:i+100]
        try:
            result = sp.audio_features(batch)
            for f in result:
                if f:
                    features[f["id"]] = {
                        "bpm": round(f["tempo"], 1) if f["tempo"] else None,
                        "key": f["key"],
                        "mode": f["mode"],
                        "energy": f["energy"],
                        "danceability": f["danceability"],
                        "duration_ms": f["duration_ms"]
                    }
        except Exception as e:
            log(f"Error audio features: {e}", "debug")
        time.sleep(0.1)
    return features

def key_to_string(key_num, mode_num):
    """Converteix key numerica de Spotify a notacio musical"""
    keys = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
    if key_num is None or key_num < 0 or key_num > 11:
        return "N/D"
    key_str = keys[key_num]
    if mode_num == 0:
        key_str += "m"  # menor
    return key_str

def cercar_spotify(sp, artista_nom, any_triat, limit=20, tipus_cerca="novetats"):
    cancons = []
    if "/" in any_triat:
        parts = any_triat.split("/")
        try:
            any_min = int(parts[0].strip())
            any_max = int(parts[1].strip())
        except:
            any_min = any_max = 2025
    else:
        try:
            any_min = any_max = int(any_triat)
        except:
            any_min = any_max = 2025

    if tipus_cerca == "classics":
        limit = max(limit, 50)

    track_ids = []
    cancons_temp = []

    try:
        # Estrategia 1: Cerca amb filtre d'any
        query = f'artist:"{artista_nom}" year:{any_min}-{any_max}'
        resultats = sp.search(q=query, type="track", limit=limit)
        for track in resultats.get("tracks", {}).get("items", []):
            try:
                any_ll = int(track.get("album", {}).get("release_date", "").split("-")[0])
                if any_min <= any_ll <= any_max:
                    track_id = track["id"]
                    track_ids.append(track_id)
                    cancons_temp.append({
                        "artista": track["artists"][0]["name"],
                        "titol": track["name"],
                        "bpm": "N/D",
                        "clau": "N/D",
                        "any": any_ll,
                        "popularitat": track.get("popularity", 0),
                        "durada_ms": track.get("duration_ms", 0),
                        "spotify_uri": track["uri"],
                        "spotify_link": track["external_urls"]["spotify"],
                        "spotify_id": track_id,
                        "font": "Spotify"
                    })
            except:
                pass

        # Estrategia 2: Cerca general si no trobem res
        if not cancons_temp:
            log(f"{artista_nom}: cap resultat amb filtre d'any, provant cerca general...", "debug")
            resultats2 = sp.search(q=f'artist:"{artista_nom}"', type="track", limit=50)
            for track in resultats2.get("tracks", {}).get("items", []):
                try:
                    any_ll = int(track.get("album", {}).get("release_date", "").split("-")[0])
                    if any_min <= any_ll <= any_max:
                        track_id = track["id"]
                        track_ids.append(track_id)
                        cancons_temp.append({
                            "artista": track["artists"][0]["name"],
                            "titol": track["name"],
                            "bpm": "N/D",
                            "clau": "N/D",
                            "any": any_ll,
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

    # Obtenir audio features (BPM, key) per tots els tracks trobats
    if track_ids:
        log(f"{artista_nom}: Obtenint BPM i Key per {len(track_ids)} tracks...", "debug")
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

# ============================================================
# 11. CERCA ALTRES APIs
# ============================================================
def cercar_discogs(artista_nom, any_triat, limit=20, tipus_cerca="novetats"):
    cancons = []
    if "/" in any_triat:
        parts = any_triat.split("/")
        try:
            any_min = int(parts[0].strip())
            any_max = int(parts[1].strip())
        except:
            any_min = any_max = 2025
    else:
        try:
            any_min = any_max = int(any_triat)
        except:
            any_min = any_max = 2025
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
        except Exception as e:
            log(f"Error Discogs {artista_nom}: {e}", "debug")
    return cancons

def cercar_musicbrainz(artista_nom, any_triat, limit=20, tipus_cerca="novetats"):
    cancons = []
    if "/" in any_triat:
        parts = any_triat.split("/")
        try:
            any_min = int(parts[0].strip())
            any_max = int(parts[1].strip())
        except:
            any_min = any_max = 2025
    else:
        try:
            any_min = any_max = int(any_triat)
        except:
            any_min = any_max = 2025
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
    except Exception as e:
        log(f"Error MusicBrainz {artista_nom}: {e}", "debug")
    return cancons

def cercar_deezer(artista_nom, any_triat, limit=20, tipus_cerca="novetats"):
    cancons = []
    if "/" in any_triat:
        parts = any_triat.split("/")
        try:
            any_min = int(parts[0].strip())
            any_max = int(parts[1].strip())
        except:
            any_min = any_max = 2025
    else:
        try:
            any_min = any_max = int(any_triat)
        except:
            any_min = any_max = 2025
    if tipus_cerca == "classics":
        limit = max(limit, 50)
    try:
        url = f"https://api.deezer.com/search/track?q=artist:{requests.utils.quote(artista_nom)}&limit={limit}"
        res = requests.get(url, timeout=5)
        if res.status_code == 200:
            for track in res.json().get("data", []):
                try:
                    any_ll = int(track.get("album", {}).get("release_date", "").split("-")[0])
                    if any_min <= any_ll <= any_max:
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
    except Exception as e:
        log(f"Error Deezer {artista_nom}: {e}", "debug")
    return cancons

# ============================================================
# 12. UTILITATS AVANÇADES
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
    """
    Limita el nombre de cancons per artista per evitar monopolitzar la llista.
    Prioritza les mes populars.
    """
    contador = {}
    resultat = []

    # Primer ordenar per popularitat (descendent)
    cancons_ordenades = sorted(cancons, key=lambda x: x.get("popularitat", 0) if isinstance(x.get("popularitat"), (int, float)) else 0, reverse=True)

    for canco in cancons_ordenades:
        artista = canco["artista"].lower().strip()
        contador[artista] = contador.get(artista, 0) + 1

        if contador[artista] <= max_per_artista:
            resultat.append(canco)
        else:
            log(f"Limit aplicat: {canco['artista']} - {canco['titol']} (ja te {max_per_artista} cancons)", "debug")

    log(f"Limit per artista aplicat: {len(cancons)} -> {len(resultat)} cancons", "info")
    return resultat

def ordenar_cancons_intelligent(cancons, criteri="popularitat"):
    """
    Ordena les cancons segons diferents criteris.
    """
    if criteri == "popularitat":
        # Popularitat descendent
        return sorted(cancons, key=lambda x: x.get("popularitat", 0) if isinstance(x.get("popularitat"), (int, float)) else 0, reverse=True)
    elif criteri == "bpm":
        # BPM ascendent (per fer transicions suaus)
        return sorted(cancons, key=lambda x: x.get("bpm", 0) if isinstance(x.get("bpm"), (int, float)) else 999)
    elif criteri == "any":
        # Any descendent (mes nous primer)
        return sorted(cancons, key=lambda x: x.get("any", 0), reverse=True)
    elif criteri == "aleatori":
        import random
        random.shuffle(cancons)
        return cancons
    else:
        return cancons

def verificar_uris(sp, cancons):
    log(f"Verificant {len(cancons)} cancons a Spotify...", "info")
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
                # Actualitzar popularitat si no la teniem
                if c.get("popularitat") == "N/D" or c.get("popularitat") == 0:
                    c["popularitat"] = track.get("popularity", 0)
                verificades.append(c)
        except Exception as e:
            log(f"Error verificant {c['artista']}: {e}", "error")
        time.sleep(0.1)
    return verificades

# ============================================================
# 13. SESSION STATE
# ============================================================
if 'cancons_reals' not in st.session_state:
    st.session_state.cancons_reals = []
if 'uris_spotify' not in st.session_state:
    st.session_state.uris_spotify = []
if 'text_copiar' not in st.session_state:
    st.session_state.text_copiar = ""
if 'titol_playlist' not in st.session_state:
    st.session_state.titol_playlist = "Nova Playlist"
if 'artistes_ultima_cerca' not in st.session_state:
    st.session_state.artistes_ultima_cerca = []

# ============================================================
# 14. INTERFICIE PRINCIPAL
# ============================================================
if CLIENT_ID and CLIENT_SECRET:
    try:
        log("Inicialitzant Spotify...", "info")
        sp = spotipy.Spotify(auth_manager=SpotifyOAuth(
            client_id=CLIENT_ID, client_secret=CLIENT_SECRET,
            redirect_uri=REDIRECT_URI, scope="playlist-modify-public"
        ))
        usuari_sp = sp.current_user()
        log(f"Connectat: {usuari_sp['display_name']}", "success")

        col_esquerra, col_dreta = st.columns([1, 2])

        # ============= COLUMNA ESQUERRA =============
        with col_esquerra:
            st.success(f"Spotify: {usuari_sp['display_name']}")
            st.info(f"IA: {MODEL_IA}")
            st.info(f"Discogs: {'Actiu' if DISCOGS_TOKEN else 'Sense token'}")

            stats = obtenir_estadistiques_db()
            with st.expander("📊 Base de Dades (Aprenentatge)", expanded=False):
                st.write(f"**Artistes confirmats:** {stats['artistes_confirmats']}")
                st.write(f"**Artistes rebutjats:** {stats['artistes_rebutjats']}")
                st.write(f"**Cancons confirmades:** {stats['cancons_confirmades']}")
                st.write(f"**Generes apresos:** {stats['generes_apresos']}")
                if stats["top_generes"]:
                    st.write("**Top generes:**")
                    for gen, nart, ncan in stats["top_generes"]:
                        st.write(f"  - {gen}: {nart} artistes, {ncan} cancons")

            st.subheader("Cerca")

            estil_triat = st.text_input("Estil / Genere:", "Makina", key="input_estil")
            any_triat = st.text_input("Any / Rang (Ex: 2026, 1990/2005):", "2025/2026", key="input_any")

            tipus_detectat = detectar_tipus_cerca(any_triat)
            if tipus_detectat == "novetats":
                st.info("🔴 Mode NOVETATS: Buscant llançaments recents")
            else:
                st.info("🟢 Mode CLASSICS: Buscant temes classics/top")

            tipus_ref = st.radio("Referencia:", ["Canco", "Artista"], horizontal=True, key="radio_tipus")

            if "Canco" in tipus_ref:
                llavor = st.text_input("Canco de referencia:", placeholder="Ex: Pont Aeri - Flying Free", key="input_llavor")
            else:
                llavor = st.text_input("Artista de referencia:", placeholder="Ex: Pont Aeri", key="input_llavor")

            quantitat = st.number_input("Cancons a trobar:", min_value=10, max_value=200, value=100, step=10, key="input_quantitat")

            st.subheader("Opcions Avançades")

            col_opt1, col_opt2 = st.columns(2)
            with col_opt1:
                max_per_artista = st.number_input("Max per artista:", min_value=1, max_value=10, value=3, step=1, key="input_max_artista")
                validar_genere = st.checkbox("Validar genere", value=True, key="chk_validar")
            with col_opt2:
                ordenacio = st.selectbox("Ordenar per:", ["popularitat", "bpm", "any", "aleatori"], index=0, key="sel_ordenacio")
                min_conf = st.selectbox("Min confiança DB:", ["segur", "probable", "dubtos"], index=1, key="sel_conf")

            any_estricte = st.checkbox("Any estricte", value=True, key="chk_estricte")

            if st.button("🔍 Comencar Rastreig", key="btn_rastreig", use_container_width=True):
                log(f"Rastreig: {estil_triat} | {any_triat} | {quantitat} cancons", "info")

                tipus_cerca = detectar_tipus_cerca(any_triat)
                log(f"Mode detectat: {tipus_cerca.upper()}", "info")

                artistes_passada1 = trobar_artistes_passada1(estil_triat, any_triat)

                if not artistes_passada1:
                    log("IA no ha trobat artistes", "error")
                    st.error("La IA no ha pogut identificar artistes.")
                else:
                    st.info(f"IA Passada 1: {len(artistes_passada1)} artistes trobats")

                    artistes_validats = validar_artistes_passada2(artistes_passada1, estil_triat, any_triat)

                    if not artistes_validats:
                        log("IA no ha validat cap artiste", "error")
                        st.error("La IA no ha pogut validar els artistes trobats.")
                    else:
                        artistes_text = "\n".join([f"{a} ({g}) [{c}]" for a, g, c in artistes_validats])
                        st.info(f"IA Passada 2: {len(artistes_validats)} artistes validats:\n\n{artistes_text}")
                        st.session_state.artistes_ultima_cerca = artistes_validats

                        totes_cancons = []

                        for artista_nom, artista_genere, confiança in artistes_validats:
                            if not validar_artista_seguretat(artista_nom):
                                log(f"Artista descartat (llista negra): {artista_nom}", "warning")
                                continue

                            log(f"Cercant: {artista_nom} ({artista_genere}) [{confiança}]...", "info")

                            cancons_spotify = cercar_spotify(sp, artista_nom, any_triat, limit=10, tipus_cerca=tipus_cerca)
                            cancons_discogs = cercar_discogs(artista_nom, any_triat, limit=10, tipus_cerca=tipus_cerca)
                            cancons_mb = cercar_musicbrainz(artista_nom, any_triat, limit=10, tipus_cerca=tipus_cerca)
                            cancons_deezer = cercar_deezer(artista_nom, any_triat, limit=10, tipus_cerca=tipus_cerca)

                            total = len(cancons_spotify) + len(cancons_discogs) + len(cancons_mb) + len(cancons_deezer)
                            if total > 0:
                                log(f"{artista_nom}: {total} cancons trobades", "success")

                            totes_cancons.extend(cancons_spotify)
                            totes_cancons.extend(cancons_discogs)
                            totes_cancons.extend(cancons_mb)
                            totes_cancons.extend(cancons_deezer)

                        log("Eliminant duplicats...", "info")
                        cancons_uniques = eliminar_duplicats(totes_cancons)
                        log(f"Uniques: {len(cancons_uniques)}", "success")

                        # APLICAR LIMIT PER ARTISTA
                        log(f"Aplicant limit de {max_per_artista} cancons per artista...", "info")
                        cancons_limitades = limitar_cancons_per_artista(cancons_uniques, max_per_artista)

                        # ORDENAR SEGONS CRITERI
                        log(f"Ordenant per {ordenacio}...", "info")
                        cancons_ordenades = ordenar_cancons_intelligent(cancons_limitades, ordenacio)

                        cancons_finals = cancons_ordenades[:quantitat]
                        log(f"Total: {len(cancons_finals)} cancons", "success")

                        log("Verificant a Spotify...", "info")
                        cancons_verificades = verificar_uris(sp, cancons_finals)

                        processades = []
                        uris = []
                        text = ""
                        for idx, c in enumerate(cancons_verificades, 1):
                            processades.append({
                                "NUM": idx, "ARTISTA": c["artista"], "TITOL": c["titol"],
                                "BPM": c["bpm"], "CLAU": c["clau"], "ANY": c["any"],
                                "POPULARITAT": c.get("popularitat", "N/D"),
                                "ESTIL": estil_triat, "FONT": c["font"],
                                "SPOTIFY": c.get("spotify_link") or "No trobat",
                                "DISCOGS": c.get("discogs_link") or "No trobat",
                                "DEEZER": c.get("deezer_link") or "No trobat"
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
                        log(f"Llista guardada: {len(processades)} cancons", "success")

                        actualitzar_estadistiques_genere(estil_triat)

        # ============= COLUMNA DRETA =============
        with col_dreta:
            st.subheader("Consola de Depuracio")
            render_console()

            if st.button("Netejar Consola", key="btn_netejar"):
                clear_console()
                st.rerun()

            st.divider()

            if st.session_state.artistes_ultima_cerca:
                with st.expander("🧠 Ensenyar a la DB (Feedback)", expanded=True):
                    st.write("Marca quins artistes SON d'aquest estil i quins NO:")
                    for i, (artista, genere, conf) in enumerate(st.session_state.artistes_ultima_cerca):
                        cols = st.columns([3, 1, 1])
                        with cols[0]:
                            st.write(f"**{artista}** ({genere}) [{conf}]")
                        with cols[1]:
                            if st.button(f"✅ Si", key=f"btn_si_{i}"):
                                guardar_artista_confirmat(artista, estil_triat, genere, "usuari", "segur")
                                log(f"DB: {artista} marcat com a SEGUR", "success")
                                st.rerun()
                        with cols[2]:
                            if st.button(f"❌ No", key=f"btn_no_{i}"):
                                guardar_artista_rebutjat(artista, estil_triat, "No es del genere (usuari)")
                                log(f"DB: {artista} marcat com a REBUTJAT", "warning")
                                st.rerun()

            st.divider()

            if st.session_state.cancons_reals:
                st.subheader(f"Resultats ({len(st.session_state.cancons_reals)} cancons)")
                df = pd.DataFrame(st.session_state.cancons_reals)
                st.dataframe(
                    df, use_container_width=True, hide_index=True,
                    column_config={
                        "SPOTIFY": st.column_config.LinkColumn("SPOTIFY"),
                        "DISCOGS": st.column_config.LinkColumn("DISCOGS"),
                        "DEEZER": st.column_config.LinkColumn("DEEZER")
                    }
                )

                st.divider()
                st.subheader("Crear Playlist a Spotify")

                nom_llista = st.text_input("Nom de la playlist:", value=st.session_state.titol_playlist, key="input_nom_playlist")

                col1, col2 = st.columns(2)
                with col1:
                    if st.session_state.uris_spotify:
                        if st.button("Crear Playlist", key="btn_crear", use_container_width=True):
                            try:
                                log(f"Creant '{nom_llista}'...", "info")
                                pl = sp.user_playlist_create(user=usuari_sp['id'], name=nom_llista, public=True)
                                for i in range(0, len(st.session_state.uris_spotify), 100):
                                    sp.playlist_add_items(playlist_id=pl['id'], items=st.session_state.uris_spotify[i:i+100])
                                log(f"Playlist creada!", "success")
                                st.success(f"Playlist '{nom_llista}' creada!")
                                st.link_button("Obrir Playlist", pl["external_urls"]["spotify"])
                                st.session_state.titol_playlist = nom_llista
                            except Exception as e:
                                log(f"Error: {e}", "error")
                                st.error(f"Error: {e}")

                with col2:
                    st.text_area("Copiar llista:", value=st.session_state.text_copiar, height=120, key="ta_copiar")
                    if st.button("Exportar CSV", key="btn_csv"):
                        csv = df.to_csv(index=False, encoding='utf-8-sig')
                        st.download_button(label="Descarregar CSV", data=csv, file_name=f"{st.session_state.titol_playlist}.csv", mime="text/csv", key="btn_download")
                        log("CSV exportat", "success")

    except Exception as e:
        log(f"Error de sistema: {e}", "error")
        st.error(f"Error de sistema: {e}")
else:
    log("Falten credencials", "error")
    st.error("Falten credencials.")
    st.info("Configura els secrets a Streamlit Cloud o els fitxers locals.")
