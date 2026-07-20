import streamlit as st
import spotipy
from spotipy.oauth2 import SpotifyOAuth
import os
import re
import requests
import pandas as pd
import json
import time
from datetime import datetime

# ============================================================
# 1. CONFIGURACIO
# ============================================================
RUTA_API_SPOTIFY = r"D:\Programa llistes Spoty\api.txt"
RUTA_CONFIG_JSON = r"D:\Programa llistes Spoty\configuracio_api.json"
REDIRECT_URI = "http://127.0.0.1:8501"

st.set_page_config(page_title="Rastrejador de Novetats Reals", page_icon="🎛️", layout="wide")

# ============================================================
# 2. DICCIONARI D'ESTILS (per la IA i validacio)
# ============================================================
DICCIONARI_ESTILS = {
    "makina": {
        "subgeneres": ["hardcore", "bakalao", "hardtek", "tekno", "gabber", "jumpstyle", "rave", "hard dance"],
        "artistes_reals": ["Pont Aeri", "Pastis & Buenri", "Ruboy", "Xavi Metralla", "Javi Boss",
                          "Skudero", "DJ Nau", "Xque", "Sissu", "Chimo Bayo", "Cesar Almena",
                          "M-Project", "DJ Soto", "Korsakoff", "Neophyte", "Rotterdam Terror Corps",
                          "Charly Sinewave", "Radium", "The Speed Freak", "Party Animals", "Bass Generator"],
        "desc": "Musica electronica rapida (150-200 BPM) de la ruta del bakalao valencia i hardcore holandes. Kicks distorsionats, melodies euforiques."
    },
    "rock catala": {
        "subgeneres": ["rock", "indie rock", "pop rock", "ska", "punk", "alternatiu"],
        "artistes_reals": ["Els Pets", "Sopa de Cabra", "Gossos", "Lax'n'Busto", "Sau",
                          "Els Amics de les Arts", "Manel", "Txarango", "Catarres", "Oques Grasses",
                          "Buhos", "Els Catarres", "Strombers", "Doctor Prats", "La Pegatina"],
        "desc": "Rock cantat en catala, des del rock dur dels 80s fins l'indie-pop actual. Lletres en catala, guitars electriques."
    },
    "techno": {
        "subgeneres": ["techno", "hard techno", "industrial techno", "schranz", "acid techno", "minimal"],
        "artistes_reals": ["Adam Beyer", "Charlotte de Witte", "Amelie Lens", "Nina Kraviz", "Carl Cox",
                          "Jeff Mills", "Richie Hawtin", "Ben Klock", "Dax J", "I Hate Models"],
        "desc": "Musica electronica repetitiva amb sintetitzadors, beats mechanics i atmosfera industrial o fosca."
    },
    "house": {
        "subgeneres": ["house", "deep house", "tech house", "progressive house", "acid house", "electro house"],
        "artistes_reals": ["David Guetta", "Calvin Harris", "Swedish House Mafia", "Disclosure",
                          "Fisher", "Dom Dolla", "John Summit", "Peggy Gou", "Black Coffee"],
        "desc": "Musica dance amb ritme 4/4, 120-130 BPM, amb influencies de soul, funk i disco."
    },
    "reggaeton": {
        "subgeneres": ["reggaeton", "latin", "trap latino", "dembow", "perreo"],
        "artistes_reals": ["Bad Bunny", "Daddy Yankee", "J Balvin", "Karol G", "Anuel AA",
                          "Ozuna", "Maluma", "Rauw Alejandro", "Feid", "Myke Towers"],
        "desc": "Musica urbana latina amb ritme dembow, beats pesats i lletres en espanyol."
    },
    "hip hop": {
        "subgeneres": ["hip hop", "rap", "trap", "boom bap", "conscious hip hop"],
        "artistes_reals": ["Kendrick Lamar", "J. Cole", "Drake", "Travis Scott", "Eminem",
                          "Nas", "Jay-Z", "Kanye West", "Tyler the Creator", "A$AP Rocky"],
        "desc": "Musica urbana amb rimes, beats de sampler i bases de bateria."
    }
}

def obtenir_info_estil(estil_usuari):
    """Retorna la info del diccionari per un estil, o generica si no existeix"""
    estil_lower = estil_usuari.lower().strip()
    for clau, dades in DICCIONARI_ESTILS.items():
        if clau in estil_lower or estil_lower in clau:
            return dades
    return {
        "subgeneres": [estil_usuari.lower()],
        "artistes_reals": [],
        "desc": f"Musica del genere {estil_usuari}"
    }

def estils_permesos(estil_usuari):
    info = obtenir_info_estil(estil_usuari)
    return [estil_usuari] + info["subgeneres"]

# ============================================================
# 3. SISTEMA DE LOGS
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

    st.session_state.console_logs.append({
        "time": timestamp, "icon": icon, "level": level.upper(),
        "msg": str(msg), "color": color
    })
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
    <div style="
        background: #0a0a0a;
        border: 2px solid #333;
        border-radius: 8px;
        padding: 10px;
        height: 280px;
        overflow-y: auto;
        font-family: Courier New, monospace;
        box-shadow: 0 0 20px rgba(0, 255, 136, 0.1);
    ">
        <div style="
            position: sticky; top: 0; background: #1a1a1a; padding: 5px 10px;
            border-bottom: 1px solid #333; margin-bottom: 10px; border-radius: 4px;
            display: flex; justify-content: space-between; align-items: center;
        ">
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
# 6. IA: IDENTIFICAR ARTISTES REALS (amb context complet)
# ============================================================
def identificar_artistes_reals_genere(estil):
    if not GROQ_KEY or not GROQ_URL:
        log("No hi ha claus IA", "warning")
        return []

    info = obtenir_info_estil(estil)

    headers = {"Authorization": f"Bearer {GROQ_KEY}", "Content-Type": "application/json"}

    prompt = f"""Ets un expert musical amb 20 anys d'experiencia. Coneixes tots els artistes reals de cada genere.

L'usuari busca musica de l'estil: "{estil}"

DESCRIPCIO DEL GENERE:
{info['desc']}

SUBGENERES RELACIONATS:
{', '.join(info['subgeneres'])}

ARTISTES CONEGUTS D'AQUEST GENERE (referencia):
{chr(10).join(info['artistes_reals']) if info['artistes_reals'] else 'No disponible'}

INSTRUCCIONS ESTRICTES:
1. NOMES artistes REALS que hagin publicat musica d'aquest genere concret.
2. PROHIBIT inventar artistes.
3. PROHIBIT incloure artistes d'altres generes (ex: si busca Mákina, NO posar pop, rock, reggaeton, etc.)
4. Inclou artistes classics del genere I artistes emergents actuals.
5. Format: noms separats per comes.
6. Maxim 25 artistes.

Respon NOMES amb la llista d'artistes reals separats per comes. Sense numeros, sense explicacions."""

    data = {
        "model": MODEL_IA,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.2
    }

    try:
        log(f"IA analitzant estil '{estil}'...", "info")
        res = requests.post(GROQ_URL, headers=headers, json=data, timeout=15)
        if res.status_code == 200:
            resposta = res.json()["choices"][0]["message"]["content"].strip()
            resposta = resposta.replace("\n", ",").replace("\r", "")
            resposta = re.sub(r'^\d+[.\-)]\s*', '', resposta, flags=re.MULTILINE)
            artistes = [a.strip().strip('"').strip("'") for a in resposta.split(",") if a.strip()]
            artistes = [a for a in artistes if len(a) > 1 and not a.lower().startswith('nota')]

            # FILTRE: validar contra paraules clau del genere
            info = obtenir_info_estil(estil)
            subgeneres = info["subgeneres"]
            artistes_clau = [a.lower() for a in info["artistes_reals"]]

            artistes_filtrats = []
            for a in artistes:
                a_lower = a.lower()
                # Si es un artiste conegut del diccionari, acceptar
                if any(known in a_lower or a_lower in known for known in artistes_clau):
                    artistes_filtrats.append(a)
                    continue
                # Si el nom conte paraules clau del genere, acceptar
                if any(sg in a_lower for sg in subgeneres):
                    artistes_filtrats.append(a)
                    continue
                # Si no passa cap filtre, descartar (probablement inventat o d'altre genere)
                log(f"Filtrat: {a} (no coincideix amb el genere)", "debug")

            if artistes_filtrats:
                log(f"IA: {len(artistes_filtrats)} artistes validats", "success")
                return artistes_filtrats
            else:
                log("Cap artista ha passat el filtre, usant llista de seguretat", "warning")
                return info["artistes_reals"][:15] if info["artistes_reals"] else []
        else:
            log(f"Error IA: {res.status_code}", "error")
            return info["artistes_reals"][:15] if info["artistes_reals"] else []
    except Exception as e:
        log(f"Error IA: {e}", "error")
        return info["artistes_reals"][:15] if info["artistes_reals"] else []

# ============================================================
# 7. VALIDACIO DE GENERE A SPOTIFY
# ============================================================
def validar_genere_artista(sp, artista, estil):
    try:
        resultats = sp.search(q=f"artist:{artista}", type="artist", limit=1)
        artists = resultats.get("artists", {}).get("items", [])

        if not artists:
            log(f"{artista}: no trobat a Spotify", "info")
            return True

        genres = artists[0].get("genres", [])
        log(f"{artista} - generes: {genres if genres else 'cap'}", "debug")

        if not genres:
            return True

        estils_perm = estils_permesos(estil)
        for genre in genres:
            g_lower = genre.lower()
            for ep in estils_perm:
                if ep.lower() in g_lower or g_lower in ep.lower():
                    log(f"{artista} validat: {genre}", "success")
                    return True

        # Si el nom de l'artista conte paraules clau del genere
        info = obtenir_info_estil(estil)
        a_lower = artista.lower()
        if any(sg in a_lower for sg in info["subgeneres"]):
            log(f"{artista} acceptat per nom", "info")
            return True

        log(f"{artista} descartat (generes: {genres})", "warning")
        return False

    except Exception as e:
        log(f"Error validant {artista}: {e}", "error")
        return True

# ============================================================
# 8. CERCA NOVETATS - TOTES LES APIs
# ============================================================
def cercar_spotify(sp, artista, any_triat, limit=20):
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
        # Estrategia 1: per any
        query = f'artist:"{artista}" year:{any_min}-{any_max}'
        resultats = sp.search(q=query, type="track", limit=limit)
        for track in resultats.get("tracks", {}).get("items", []):
            try:
                any_ll = int(track.get("album", {}).get("release_date", "").split("-")[0])
                if any_min <= any_ll <= any_max:
                    cancons.append({
                        "artista": track["artists"][0]["name"], "titol": track["name"],
                        "bpm": "N/D", "clau": "N/D", "any": any_ll,
                        "spotify_uri": track["uri"],
                        "spotify_link": track["external_urls"]["spotify"],
                        "font": "Spotify"
                    })
            except:
                pass

        # Estrategia 2: general + filtre
        if not cancons:
            resultats2 = sp.search(q=f'artist:"{artista}"', type="track", limit=50)
            for track in resultats2.get("tracks", {}).get("items", []):
                try:
                    any_ll = int(track.get("album", {}).get("release_date", "").split("-")[0])
                    if any_min <= any_ll <= any_max:
                        cancons.append({
                            "artista": track["artists"][0]["name"], "titol": track["name"],
                            "bpm": "N/D", "clau": "N/D", "any": any_ll,
                            "spotify_uri": track["uri"],
                            "spotify_link": track["external_urls"]["spotify"],
                            "font": "Spotify"
                        })
                except:
                    pass
    except Exception as e:
        log(f"Error Spotify {artista}: {e}", "error")
    return cancons

def cercar_discogs(artista, any_triat, limit=20):
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
        headers["Authorization"] = f"Discogs token={DISCOGS_TOKEN}"

    for any_actual in range(any_min, any_max + 1):
        try:
            url = f"https://api.discogs.com/database/search?artist={requests.utils.quote(artista)}&year={any_actual}&type=master&per_page={limit}"
            resposta = requests.get(url, headers=headers, timeout=5)
            if resposta.status_code == 200:
                for r in resposta.json().get("results", [])[:limit]:
                    year = r.get("year")
                    if year and any_min <= year <= any_max:
                        cancons.append({
                            "artista": r.get("artist", artista), "titol": r.get("title", ""),
                            "bpm": "N/D", "clau": "N/D", "any": year,
                            "spotify_uri": None, "spotify_link": None,
                            "discogs_link": r.get("resource_url", ""), "font": "Discogs"
                        })
            time.sleep(0.5)
        except Exception as e:
            log(f"Error Discogs {artista}: {e}", "debug")
    return cancons

def cercar_musicbrainz(artista, any_triat, limit=20):
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
        url = f"https://musicbrainz.org/ws/2/artist/?query=artist:{requests.utils.quote(artista)}&fmt=json"
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
                                cancons.append({
                                    "artista": artista, "titol": grav.get("title", ""),
                                    "bpm": "N/D", "clau": "N/D", "any": any_grav,
                                    "spotify_uri": None, "spotify_link": None, "font": "MusicBrainz"
                                })
                        except:
                            pass
                time.sleep(1)
    except Exception as e:
        log(f"Error MusicBrainz {artista}: {e}", "debug")
    return cancons

def cercar_deezer(artista, any_triat, limit=20):
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
        url = f"https://api.deezer.com/search/track?q=artist:{requests.utils.quote(artista)}&limit={limit}"
        res = requests.get(url, timeout=5)
        if res.status_code == 200:
            for track in res.json().get("data", []):
                try:
                    any_ll = int(track.get("album", {}).get("release_date", "").split("-")[0])
                    if any_min <= any_ll <= any_max:
                        cancons.append({
                            "artista": track["artist"]["name"], "titol": track["title"],
                            "bpm": "N/D", "clau": "N/D", "any": any_ll,
                            "spotify_uri": None, "spotify_link": None,
                            "deezer_link": track.get("link", ""), "font": "Deezer"
                        })
                except:
                    pass
    except Exception as e:
        log(f"Error Deezer {artista}: {e}", "debug")
    return cancons

# ============================================================
# 9. UTILITATS
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
                verificades.append(c)
        except Exception as e:
            log(f"Error verificant {c['artista']}: {e}", "error")
        time.sleep(0.1)
    return verificades

# ============================================================
# 10. SESSION STATE
# ============================================================
if 'cancons_reals' not in st.session_state:
    st.session_state.cancons_reals = []
if 'uris_spotify' not in st.session_state:
    st.session_state.uris_spotify = []
if 'text_copiar' not in st.session_state:
    st.session_state.text_copiar = ""
if 'titol_playlist' not in st.session_state:
    st.session_state.titol_playlist = "Nova Playlist"

# ============================================================
# 11. INTERFICIE PRINCIPAL
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

        # ============= COLUMNA ESQUERRA: MENU MINIMAL =============
        with col_esquerra:
            st.success(f"Spotify: {usuari_sp['display_name']}")
            st.info(f"IA: {MODEL_IA}")
            st.info(f"Discogs: {'Actiu' if DISCOGS_TOKEN else 'Sense token'}")

            st.subheader("Cerca")

            estil_triat = st.text_input("Estil / Genere:", "Makina", key="input_estil")
            any_triat = st.text_input("Any / Rang:", "2025/2026", key="input_any")

            tipus_ref = st.radio("Referencia:", ["Canco", "Artista"], horizontal=True, key="radio_tipus")

            if "Canco" in tipus_ref:
                llavor = st.text_input("Canco de referencia:", placeholder="Ex: Pont Aeri - Flying Free", key="input_llavor")
            else:
                llavor = st.text_input("Artista de referencia:", placeholder="Ex: Pont Aeri", key="input_llavor")

            quantitat = st.number_input("Cancons a trobar:", min_value=10, max_value=200, value=100, step=10, key="input_quantitat")

            st.subheader("Opcions")
            validar_genere = st.checkbox("Validar genere", value=True, key="chk_validar")
            any_estricte = st.checkbox("Any estricte", value=True, key="chk_estricte")

            if st.button("🔍 Comencar Rastreig", key="btn_rastreig", use_container_width=True):
                log(f"Rastreig: {estil_triat} | {any_triat} | {quantitat} cancons", "info")

                # FASE 1: IA identifica artistes
                artistes_reals = identificar_artistes_reals_genere(estil_triat)

                if not artistes_reals:
                    log("IA no ha trobat artistes", "error")
                    st.error("La IA no ha pogut identificar artistes.")
                else:
                    st.info(f"IA ha trobat {len(artistes_reals)} artistes de {estil_triat}:\n\n{', '.join(artistes_reals)}")

                    totes_cancons = []

                    # FASE 2: Validar genere
                    artistes_validats = []
                    if validar_genere:
                        log("Validant artistes...", "info")
                        for artista in artistes_reals:
                            if validar_genere_artista(sp, artista, estil_triat):
                                artistes_validats.append(artista)
                        log(f"{len(artistes_validats)} artistes validats", "success")
                    else:
                        artistes_validats = artistes_reals

                    if not artistes_validats:
                        log("Cap artista validat", "error")
                        st.error("Cap artista ha passat la validacio.")
                    else:
                        # FASE 3: Cercar a TOTES les APIs (sempre engegades)
                        log("Cercant a Spotify...", "info")
                        for artista in artistes_validats:
                            cancons = cercar_spotify(sp, artista, any_triat, limit=10)
                            totes_cancons.extend(cancons)
                            if cancons:
                                log(f"{artista}: {len(cancons)} Spotify", "info")

                        log("Cercant a Discogs...", "info")
                        for artista in artistes_validats:
                            cancons = cercar_discogs(artista, any_triat, limit=10)
                            totes_cancons.extend(cancons)
                            if cancons:
                                log(f"{artista}: {len(cancons)} Discogs", "info")

                        log("Cercant a MusicBrainz...", "info")
                        for artista in artistes_validats:
                            cancons = cercar_musicbrainz(artista, any_triat, limit=10)
                            totes_cancons.extend(cancons)
                            if cancons:
                                log(f"{artista}: {len(cancons)} MusicBrainz", "info")

                        log("Cercant a Deezer...", "info")
                        for artista in artistes_validats:
                            cancons = cercar_deezer(artista, any_triat, limit=10)
                            totes_cancons.extend(cancons)
                            if cancons:
                                log(f"{artista}: {len(cancons)} Deezer", "info")

                        # FASE 4: Processar
                        log("Eliminant duplicats...", "info")
                        cancons_uniques = eliminar_duplicats(totes_cancons)
                        log(f"Uniques: {len(cancons_uniques)}", "success")

                        cancons_finals = cancons_uniques[:quantitat]
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
                                "ESTIL": estil_triat, "FONT": c["font"],
                                "SPOTIFY": c.get("spotify_link") or "No trobat",
                                "DISCOGS": c.get("discogs_link") or "No trobat",
                                "DEEZER": c.get("deezer_link") or "No trobat"
                            })
                            if c.get("spotify_uri"):
                                uris.append(c["spotify_uri"])
                            text += f"{idx}. {c['artista']} - {c['titol']} ({c['any']})\n"

                        st.session_state.cancons_reals = processades
                        st.session_state.uris_spotify = uris
                        st.session_state.text_copiar = text
                        st.session_state.titol_playlist = f"{estil_triat} ({any_triat})"
                        log(f"Llista guardada: {len(processades)} cancons", "success")

        # ============= COLUMNA DRETA: CONSOLA + RESULTATS =============
        with col_dreta:
            # --- CONSOLA (superior) ---
            st.subheader("Consola de Depuracio")
            render_console()

            if st.button("Netejar Consola", key="btn_netejar"):
                clear_console()
                st.rerun()

            st.divider()

            # --- RESULTATS (inferior) ---
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

                nom_llista = st.text_input(
                    "Nom de la playlist:",
                    value=st.session_state.titol_playlist,
                    key="input_nom_playlist"
                )

                col1, col2 = st.columns(2)

                with col1:
                    if st.session_state.uris_spotify:
                        if st.button("Crear Playlist", key="btn_crear", use_container_width=True):
                            try:
                                log(f"Creant '{nom_llista}'...", "info")
                                pl = sp.user_playlist_create(
                                    user=usuari_sp['id'],
                                    name=nom_llista,
                                    public=True
                                )
                                for i in range(0, len(st.session_state.uris_spotify), 100):
                                    sp.playlist_add_items(
                                        playlist_id=pl['id'],
                                        items=st.session_state.uris_spotify[i:i+100]
                                    )
                                log(f"Playlist creada!", "success")
                                st.success(f"Playlist '{nom_llista}' creada!")
                                st.link_button("Obrir Playlist", pl['external_urls']['spotify'])
                                st.session_state.titol_playlist = nom_llista
                            except Exception as e:
                                log(f"Error: {e}", "error")
                                st.error(f"Error: {e}")

                with col2:
                    st.text_area("Copiar llista:", value=st.session_state.text_copiar, height=120, key="ta_copiar")
                    if st.button("Exportar CSV", key="btn_csv"):
                        csv = df.to_csv(index=False, encoding='utf-8-sig')
                        st.download_button(
                            label="Descarregar CSV", data=csv,
                            file_name=f"{st.session_state.titol_playlist}.csv",
                            mime="text/csv", key="btn_download"
                        )
                        log("CSV exportat", "success")

    except Exception as e:
        log(f"Error de sistema: {e}", "error")
        st.error(f"Error de sistema: {e}")
else:
    log("Falten credencials", "error")
    st.error("Falten credencials.")
    st.info("Configura els secrets a Streamlit Cloud o els fitxers locals.")
