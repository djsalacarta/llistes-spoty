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
REDIRECT_URI = "http://127.0.0.1:8501"

st.set_page_config(page_title="Rastrejador de Novetats Reals", page_icon="🎛️", layout="wide")

# --- LECTURA DE CREDENCIALS (st.secrets o fitxers locals) ---
def carregar_credencials():
    """Carrega credencials de st.secrets (Cloud) o fitxers locals (Windows)"""
    creds = {
        "CLIENT_ID": "",
        "CLIENT_SECRET": "",
        "GROQ_KEY": "",
        "GROQ_URL": "",
        "DISCOGS_TOKEN": ""
    }

    # Intent 1: st.secrets (Streamlit Cloud)
    try:
        creds["CLIENT_ID"] = st.secrets.get("SPOTIFY_CLIENT_ID", "")
        creds["CLIENT_SECRET"] = st.secrets.get("SPOTIFY_CLIENT_SECRET", "")
        creds["GROQ_KEY"] = st.secrets.get("GROQ_KEY", "")
        creds["GROQ_URL"] = st.secrets.get("GROQ_URL", "")
        creds["DISCOGS_TOKEN"] = st.secrets.get("DISCOGS_TOKEN", "")
        if creds["GROQ_KEY"]:
            st.sidebar.success("🔐 Secrets de Streamlit carregats")
    except Exception:
        pass

    # Intent 2: Fitxers locals (desenvolupament Windows)
    RUTA_API_SPOTIFY = r"D:\Programa llistes Spoty\api.txt"
    RUTA_CONFIG_JSON = r"D:\Programa llistes Spoty\configuracio_api.json"

    if not creds["CLIENT_ID"] and os.path.exists(RUTA_API_SPOTIFY):
        try:
            with open(RUTA_API_SPOTIFY, "r", encoding="utf-8") as f2:
                contingut = f2.read()
            claus = re.findall(r'[a-f0-9]{32}', contingut)
            if len(claus) >= 2:
                creds["CLIENT_ID"] = claus[0]
                creds["CLIENT_SECRET"] = claus[1]
        except Exception as e:
            st.sidebar.warning(f"Error llegint api.txt: {e}")

    if not creds["GROQ_KEY"] and os.path.exists(RUTA_CONFIG_JSON):
        try:
            with open(RUTA_CONFIG_JSON, "r", encoding="utf-8") as f2:
                config = json.load(f2)
            creds["GROQ_KEY"] = config.get("GROQ_KEY", "")
            creds["GROQ_URL"] = config.get("GROQ_URL", "")
            creds["DISCOGS_TOKEN"] = config.get("DISCOGS_TOKEN", "")
        except Exception as e:
            st.sidebar.warning(f"Error llegint configuracio_api.json: {e}")

    return creds

CREDS = carregar_credencials()
CLIENT_ID = CREDS["CLIENT_ID"]
CLIENT_SECRET = CREDS["CLIENT_SECRET"]
GROQ_KEY = CREDS["GROQ_KEY"]
GROQ_URL = CREDS["GROQ_URL"]
DISCOGS_TOKEN = CREDS["DISCOGS_TOKEN"]

# --- DICCIONARI D'ESTILS MUSICALS ---
DICCIONARI_ESTILS = {
    "makina": {
        "noms": ["makina", "mákina", "spanish hardcore", "bakalao", "ch bakalao", "hard makina", 
                 "hardcore", "gabber", "mainstream hardcore", "happy hardcore", "hardtek",
                 "hardtekno", "tekno", "rave", "jumpstyle", "hard dance"],
        "artistes_clau": ["Pont Aeri", "Pastis & Buenri", "Ruboy", "Xavi Metralla", "Javi Boss",
                         "Skudero", "DJ Nau", "Xque", "Sissu", "Chimo Bayo", "Cesar Almena",
                         "M-Project", "DJ Soto", "Korsakoff", "Neophyte", "Rotterdam Terror Corps"],
        "descripcio": "Musica electronica rapida (150-200 BPM) originaria de la ruta del bakalao valencia i el hardcore holandes. Caracteritzada per kicks distorsionats, melodies euforiques i vocals agudes."
    },
    "techno": {
        "noms": ["techno", "hard techno", "industrial techno", "schranz", "acid techno", "detroit techno"],
        "artistes_clau": ["Adam Beyer", "Charlotte de Witte", "Amelie Lens", "Nina Kraviz", "Carl Cox"],
        "descripcio": "Musica electronica repetitiva amb sintetitzadors, beats mecanics i atmosfera industrial."
    },
    "house": {
        "noms": ["house", "deep house", "tech house", "progressive house", "acid house"],
        "artistes_clau": ["David Guetta", "Calvin Harris", "Swedish House Mafia", "Disclosure"],
        "descripcio": "Musica dance amb 4/4, 120-130 BPM, amb influencies de soul i funk."
    }
}

def obtenir_estils_permesos(estil_usuari):
    estil_lower = estil_usuari.lower().strip()
    estils_permesos = [estil_usuari]
    for clau, dades in DICCIONARI_ESTILS.items():
        if clau in estil_lower or estil_lower in clau:
            estils_permesos.extend(dades["noms"])
    if len(estils_permesos) == 1:
        estils_permesos.extend([estil_lower, estil_lower.replace("á", "a").replace("é", "e").replace("í", "i").replace("ó", "o").replace("ú", "u")])
    return list(set(estils_permesos))

def artista_es_relevant(artista, estil_usuari):
    artista_lower = artista.lower()
    estil_lower = estil_usuari.lower().strip()
    if "makina" in estil_lower or "mákina" in estil_lower:
        paraules_clau = ["makina", "mákina", "hardcore", "bakalao", "rave", "tekno", "gabber"]
        for paraula in paraules_clau:
            if paraula in artista_lower:
                return True
    return False

# --- 2. SISTEMA DE LOGS EN TEMPS REAL ---
def init_console():
    if 'console_logs' not in st.session_state:
        st.session_state.console_logs = []
    if 'console_html' not in st.session_state:
        st.session_state.console_html = ""

def log(msg, level="info"):
    init_console()
    timestamp = datetime.now().strftime("%H:%M:%S")
    colors = {
        "info": "#3b82f6",
        "success": "#10b981",
        "warning": "#f59e0b",
        "error": "#ef4444",
        "debug": "#6b7280"
    }
    icons = {
        "info": "🔵",
        "success": "✅",
        "warning": "⚠️",
        "error": "❌",
        "debug": "🔍"
    }
    color = colors.get(level, "#6b7280")
    icon = icons.get(level, "⚪")
    st.session_state.console_logs.append({
        "time": timestamp,
        "icon": icon,
        "level": level.upper(),
        "msg": str(msg),
        "color": color
    })
    if len(st.session_state.console_logs) > 200:
        st.session_state.console_logs = st.session_state.console_logs[-200:]
    html_lines = []
    for entry in st.session_state.console_logs[-20:]:
        line = f'<div style="font-family: \'Courier New\', monospace; font-size: 11px; padding: 2px 4px; border-left: 2px solid {entry["color"]}; margin-bottom: 1px;">'
        line += f'<span style="color: #888;">[{entry["time"]}]</span> '
        line += f'<span style="color: {entry["color"]}; font-weight: bold;">{entry["icon"]} {entry["level"]}</span> '
        line += f'<span style="color: #e0e0e0;">{entry["msg"]}</span>'
        line += '</div>'
        html_lines.append(line)

def clear_console():
    st.session_state.console_logs = []
    st.session_state.console_html = ""

def render_console_permanent():
    init_console()
    console_html = st.session_state.console_html
    if not console_html:
        console_html = '<div style="color: #666; font-family: monospace; padding: 20px; text-align: center;">⏳ Esperant operacions...</div>'

    html = '<div style="background: #0a0a0a; border: 2px solid #333; border-radius: 8px; padding: 10px; height: 280px; overflow-y: auto; font-family: Courier New, monospace; box-shadow: 0 0 20px rgba(0, 255, 136, 0.1);">'
    html += '<div style="position: sticky; top: 0; background: #1a1a1a; padding: 5px 10px; border-bottom: 1px solid #333; margin-bottom: 10px; border-radius: 4px; display: flex; justify-content: space-between; align-items: center;">'
    html += '<span style="color: #00ff88; font-weight: bold; font-size: 12px;">🖥️ CONSOLA DE DEPURACIO - TEMPS REAL</span>'
    html += '<span style="color: #888; font-size: 11px;">' + str(len(st.session_state.console_logs)) + ' registres</span>'
    html += '</div>'
    html += console_html
    html += '</div>'

    st.markdown(html, unsafe_allow_html=True)

# --- 4. OBTENCIO DE MODELS IA ---
def obtenir_model_ia_actualitzat():
    if not GROQ_URL or not GROQ_KEY:
        return "llama-3.3-70b-versatile"
    url_models = GROQ_URL.replace("/chat/completions", "/models")
    headers = {"Authorization": "Bearer " + GROQ_KEY}
    try:
        resposta = requests.get(url_models, headers=headers, timeout=5)
        if resposta.status_code == 200:
            models_data = resposta.json().get("data", [])
            ids = [m.get("id") for m in models_data if m.get("status") == "active" or not m.get("status")]
            for m_id in ids:
                if "llama" in m_id.lower() and "70b" in m_id.lower():
                    return m_id
            if ids: return ids[0]
    except: pass
    return "llama-3.3-70b-versatile"

MODEL_IA_VIU = obtenir_model_ia_actualitzat() if GROQ_KEY else None

# --- 5. IA: IDENTIFICAR ARTISTES REALS ---
def identificar_artistes_reals_genere(estil):
    if not GROQ_KEY or not GROQ_URL:
        log("No hi ha claus IA", "warning")
        return []
    headers = {"Authorization": "Bearer " + GROQ_KEY, "Content-Type": "application/json"}
    estil_lower = estil.lower().strip()
    info_estil = ""
    artistes_clau = []
    for clau, dades in DICCIONARI_ESTILS.items():
        if clau in estil_lower or estil_lower in clau:
            info_estil = dades["descripcio"]
            artistes_clau = dades["artistes_clau"]
            break
    prompt = "Ets un expert en musica electronica amb 20 anys d\'experiencia.\n\n"
    prompt += "L\'usuari busca musica de l\'estil: \"" + estil + "\".\n\n"
    prompt += "DESCRIPCIO DEL GENERE:\n" + (info_estil if info_estil else "Musica electronica del subgenere " + estil) + "\n\n"
    prompt += "ARTISTES CONEGUTS D\'AQUEST GENERE (per referencia):\n" + (", ".join(artistes_clau) if artistes_clau else "No disponible") + "\n\n"
    prompt += "INSTRUCCIONS ESTRICTES:\n"
    prompt += "1. Identifica ARTISTES REALS I EXISTENTS d\'aquest genere musical.\n"
    prompt += "2. NOMES artistes reals que hagin publicat musica. PROHIBIT inventar.\n"
    prompt += "3. Inclou artistes classics del genere I artistes emergents/nous.\n"
    prompt += "4. Si l\'estil es \"Makina\", inclou artistes de: hardcore, bakalao, hardtek, makina espanyola.\n"
    prompt += "5. Format: noms separats per comes.\n"
    prompt += "6. Maxim 25 artistes.\n\n"
    prompt += "Respon NOMES amb la llista d\'artistes reals separats per comes. Sense explicacions."

    data = {
        "model": MODEL_IA_VIU,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.3
    }
    try:
        log("IA identificant artistes reals de '" + estil + "'...", "info")
        res = requests.post(GROQ_URL, headers=headers, json=data, timeout=15)
        if res.status_code == 200:
            resposta = res.json()["choices"][0]["message"]["content"].strip()
            resposta = resposta.replace("\n", ",").replace("\r", "")
            resposta = re.sub(r"^\d+[.\-)]\s*", "", resposta, flags=re.MULTILINE)
            artistes = [a.strip().strip('"').strip("'") for a in resposta.split(",") if a.strip()]
            artistes = [a for a in artistes if len(a) > 1 and not a.lower().startswith("nota") and not a.lower().startswith("exemple")]
            if not artistes:
                return []
            log("IA ha identificat " + str(len(artistes)) + " artistes reals", "success")
            return artistes
        else:
            log("Error IA: status " + str(res.status_code), "error")
            return []
    except Exception as e:
        log("Error connectant amb la IA: " + str(e), "error")
        return []

# --- 6. VALIDACIO DE GENERE A SPOTIFY (FLEXIBLE) ---
def validar_genere_artista_spotify(sp, artista, estils_permesos):
    try:
        resultats = sp.search(q="artist:" + artista, type="artist", limit=1)
        artists = resultats.get("artists", {}).get("items", [])
        if not artists:
            log("Artista no trobat a Spotify: " + artista, "warning")
            return True
        artist = artists[0]
        genres = artist.get("genres", [])
        log(artista + " - Generes a Spotify: " + (str(genres) if genres else "Sense generes"), "debug")
        if not genres:
            log(artista + " acceptat (sense generes a Spotify)", "info")
            return True
        for genre in genres:
            genre_lower = genre.lower()
            for estil_permes in estils_permesos:
                estil_permes_lower = estil_permes.lower()
                if estil_permes_lower in genre_lower or genre_lower in estil_permes_lower:
                    log(artista + " es del genere correcte: " + genre, "success")
                    return True
        if artista_es_relevant(artista, estils_permesos[0] if estils_permesos else ""):
            log(artista + " acceptat per nom (conte paraula clau del genere)", "info")
            return True
        log(artista + " descartat. Generes trobats: " + str(genres), "warning")
        return False
    except Exception as e:
        log("Error validant genere de " + artista + ": " + str(e), "error")
        return True

# --- 7. CERCA NOVETATS ARTISTA a SPOTIFY ---
def cercar_novetats_artista_spotify(sp, artista, any_triat, limit=20):
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
    try:
        query = 'artist:"' + artista + '" year:' + str(any_min) + '-' + str(any_max)
        resultats = sp.search(q=query, type="track", limit=limit)
        tracks = resultats.get("tracks", {}).get("items", [])
        for track in tracks:
            release_date = track.get("album", {}).get("release_date", "")
            try:
                any_llancament = int(release_date.split("-")[0])
                if any_min <= any_llancament <= any_max:
                    cancons.append({
                        "artista": track["artists"][0]["name"],
                        "titol": track["name"],
                        "bpm": "N/D",
                        "clau": "N/D",
                        "any": any_llancament,
                        "spotify_uri": track["uri"],
                        "spotify_link": track["external_urls"]["spotify"],
                        "font": "Spotify"
                    })
                    log(artista + ": " + track["name"] + " (" + str(any_llancament) + ")", "debug")
            except:
                pass
        if not cancons:
            log(artista + ": cap resultat amb cerca per any, provant cerca general...", "debug")
            query2 = 'artist:"' + artista + '"'
            resultats2 = sp.search(q=query2, type="track", limit=50)
            tracks2 = resultats2.get("tracks", {}).get("items", [])
            for track in tracks2:
                release_date = track.get("album", {}).get("release_date", "")
                try:
                    any_llancament = int(release_date.split("-")[0])
                    if any_min <= any_llancament <= any_max:
                        cancons.append({
                            "artista": track["artists"][0]["name"],
                            "titol": track["name"],
                            "bpm": "N/D",
                            "clau": "N/D",
                            "any": any_llancament,
                            "spotify_uri": track["uri"],
                            "spotify_link": track["external_urls"]["spotify"],
                            "font": "Spotify"
                        })
                except:
                    pass
    except Exception as e:
        log("Error cercant " + artista + ": " + str(e), "error")
    return cancons

# --- 8. CERCA NOVETATS ARTISTA a DISCOGS ---
def cercar_novetats_artista_discogs(artista, any_triat, limit=20):
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
    headers = {"User-Agent": "SuperDJBuscadorApp/1.0.0", "Accept": "application/json"}
    if DISCOGS_TOKEN:
        headers["Authorization"] = "Discogs token=" + DISCOGS_TOKEN
    for any_actual in range(any_min, any_max + 1):
        url = "https://api.discogs.com/database/search?artist=" + requests.utils.quote(artista) + "&year=" + str(any_actual) + "&type=master&per_page=" + str(limit)
        try:
            resposta = requests.get(url, headers=headers, timeout=5)
            if resposta.status_code == 200:
                dades = resposta.json()
                resultats = dades.get("results", [])
                for r in resultats[:limit]:
                    year = r.get("year")
                    if year and any_min <= year <= any_max:
                        title = r.get("title", "")
                        artist = r.get("artist", "")
                        if title and artist:
                            cancons.append({
                                "artista": artist,
                                "titol": title,
                                "bpm": "N/D",
                                "clau": "N/D",
                                "any": year,
                                "spotify_uri": None,
                                "spotify_link": None,
                                "discogs_link": r.get("resource_url", ""),
                                "font": "Discogs"
                            })
            time.sleep(0.5)
        except Exception as e:
            log("Error Discogs per " + artista + ": " + str(e), "debug")
    return cancons

# --- 9. CERCA A MUSICBRAINZ ---
def cercar_novetats_artista_musicbrainz(artista, any_triat, limit=20):
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
    headers = {"User-Agent": "SuperDJBuscadorApp/1.0.0", "Accept": "application/json"}
    try:
        url_artista = "https://musicbrainz.org/ws/2/artist/?query=artist:" + requests.utils.quote(artista) + "&fmt=json"
        res_artista = requests.get(url_artista, headers=headers, timeout=5)
        if res_artista.status_code == 200:
            dades_artista = res_artista.json()
            artistes = dades_artista.get("artists", [])
            if artistes:
                artista_id = artistes[0].get("id")
                url_gravacions = "https://musicbrainz.org/ws/2/recording/?query=arid:" + artista_id + " AND date:[" + str(any_min) + " TO " + str(any_max) + "]&fmt=json&limit=" + str(limit)
                res_grav = requests.get(url_gravacions, headers=headers, timeout=5)
                if res_grav.status_code == 200:
                    dades_grav = res_grav.json()
                    gravacions = dades_grav.get("recordings", [])
                    for grav in gravacions:
                        title = grav.get("title", "")
                        date = grav.get("first-release-date", "")
                        try:
                            any_grav = int(date.split("-")[0]) if date else any_min
                            if any_min <= any_grav <= any_max:
                                cancons.append({
                                    "artista": artista,
                                    "titol": title,
                                    "bpm": "N/D",
                                    "clau": "N/D",
                                    "any": any_grav,
                                    "spotify_uri": None,
                                    "spotify_link": None,
                                    "font": "MusicBrainz"
                                })
                        except:
                            pass
                time.sleep(1)
    except Exception as e:
        log("Error MusicBrainz per " + artista + ": " + str(e), "debug")
    return cancons

# --- 10. ELIMINAR DUPLICATS ---
def eliminar_duplicats(cancons):
    vistes = set()
    cancons_uniques = []
    for canco in cancons:
        clau = canco["artista"].lower().strip() + "|" + canco["titol"].lower().strip()
        if clau not in vistes:
            vistes.add(clau)
            cancons_uniques.append(canco)
    return cancons_uniques

# --- 11. VERIFICAR A SPOTIFY I OBTENIR URIs ---
def verificar_i_obtenir_uris(sp, cancons):
    log("Verificant " + str(len(cancons)) + " cancons a Spotify...", "info")
    cancons_verificades = []
    for idx, canco in enumerate(cancons):
        if canco.get("spotify_uri"):
            cancons_verificades.append(canco)
            continue
        try:
            query = "track:" + canco["titol"] + " artist:" + canco["artista"]
            resultats = sp.search(q=query, type="track", limit=1)
            tracks = resultats.get("tracks", {}).get("items", [])
            if tracks:
                track = tracks[0]
                canco["spotify_uri"] = track["uri"]
                canco["spotify_link"] = track["external_urls"]["spotify"]
                cancons_verificades.append(canco)
                log("Spotify trobat: " + canco["artista"] + " - " + canco["titol"], "success")
        except Exception as e:
            log("Error verificant " + canco["artista"] + ": " + str(e), "error")
        time.sleep(0.1)
    return cancons_verificades

