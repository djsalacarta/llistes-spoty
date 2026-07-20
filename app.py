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
# 2. LLISTA NEGRA MINIMA
# ============================================================
LLISTA_NEGRA = [
    "tuyo", "rimsky-korsakov", "mussorgsky", "modest mussorgsky",
    "nikolai rimsky-korsakov"
]

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
# 6. IA: TROBAR ARTISTES (PASSADA 1)
# ============================================================
def trobar_artistes_passada1(estil):
    """Primera passada: la IA troba artistes potencials"""
    if not GROQ_KEY or not GROQ_URL:
        return []

    headers = {"Authorization": f"Bearer {GROQ_KEY}", "Content-Type": "application/json"}

    prompt = f"""Ets un expert musical. L'usuari busca musica de l'estil: "{estil}"

Troba artistes REALS i EXISTENTS d'aquest estil. Per cada artiste, indica el seu genere principal.

FORMAT (estricte, una linia per artiste):
NOM_ARTISTE | GENERE_PRINCIPAL

Exemple per "Makina":
Pont Aeri | hardcore
Ruboy | hard makina
Xavi Metralla | hardcore

Respon NOMES amb la llista. Sense explicacions. Maxim 30 artistes."""

    data = {
        "model": MODEL_IA,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.2,
        "max_tokens": 2048
    }

    try:
        log("IA: Passada 1 - Trobant artistes...", "info")
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
                        if nom and len(nom) > 1:
                            artistes.append((nom, genere))
                else:
                    nom = linia.strip().strip(",").strip("-")
                    if nom and len(nom) > 1:
                        artistes.append((nom, "desconegut"))

            log(f"IA: Passada 1 -> {len(artistes)} artistes trobats", "success")
            return artistes
        return []
    except Exception as e:
        log(f"Error IA passada 1: {e}", "error")
        return []

# ============================================================
# 7. IA: VALIDAR ARTISTES (PASSADA 2)
# ============================================================
def validar_artistes_passada2(artistes, estil):
    """
    Segona passada: la IA revisa la seva propia llista i descarta el que no encaixa.
    A mes, per cada artiste validat, indica si es "segur" o "probable".
    """
    if not artistes or not GROQ_KEY or not GROQ_URL:
        return []

    headers = {"Authorization": f"Bearer {GROQ_KEY}", "Content-Type": "application/json"}

    # Preparar la llista per la IA
    llista_text = "\n".join([f"{i+1}. {nom} ({genere})" for i, (nom, genere) in enumerate(artistes)])

    prompt = f"""Ets un expert musical. Has trobat aquesta llista d'artistes per l'estil "{estil}".

LLISTA D'ARTISTES TROBATS:
{llista_text}

La teva tasca ara es REVISAR aquesta llista i descartar qualsevol artiste que:
1. NO toqui realment l'estil "{estil}"
2. Sigui d'un genere completament diferent
3. Sigui un artiste generic que pugui confondre's amb altres generes
4. NO existeixi realment (noms inventats)

Per cada artiste que MANTINGUIS, indica el nivell de confianca:
- "segur" = artiste conegut i confirmat d'aquest estil
- "probable" = artiste que sembla encaixar pero no esta 100% confirmat

FORMAT DE RESPOSTA (estricte):
NOM_ARTISTE | GENERE | CONFIANCA

Exemple:
Pont Aeri | hardcore | segur
Ruboy | hard makina | segur

Respon NOMES amb els artistes VALIDATS. No incloure explicacions."""

    data = {
        "model": MODEL_IA,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.1,
        "max_tokens": 2048
    }

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
            log(f"IA: Passada 2 -> {len(artistes_validats)} artistes validats ({segurs} segurs, {probables} probables)", "success")
            return artistes_validats
        return []
    except Exception as e:
        log(f"Error IA passada 2: {e}", "error")
        # Si falla la passada 2, retornar tots de la passada 1 amb confiança probable
        return [(nom, gen, "probable") for nom, gen in artistes]

# ============================================================
# 8. VALIDACIO MINIMA DE SEGURETAT
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
# 9. CERCA APIs
# ============================================================
def cercar_spotify(sp, artista_nom, any_triat, limit=20):
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
        query = f'artist:"{artista_nom}" year:{any_min}-{any_max}'
        resultats = sp.search(q=query, type="track", limit=limit)
        for track in resultats.get("tracks", {}).get("items", []):
            try:
                any_ll = int(track.get("album", {}).get("release_date", "").split("-")[0])
                if any_min <= any_ll <= any_max:
                    canco = {
                        "artista": track["artists"][0]["name"], "titol": track["name"],
                        "bpm": "N/D", "clau": "N/D", "any": any_ll,
                        "spotify_uri": track["uri"],
                        "spotify_link": track["external_urls"]["spotify"],
                        "font": "Spotify"
                    }
                    if validar_canco_seguretat(canco, artista_nom):
                        cancons.append(canco)
            except:
                pass

        if not cancons:
            resultats2 = sp.search(q=f'artist:"{artista_nom}"', type="track", limit=50)
            for track in resultats2.get("tracks", {}).get("items", []):
                try:
                    any_ll = int(track.get("album", {}).get("release_date", "").split("-")[0])
                    if any_min <= any_ll <= any_max:
                        canco = {
                            "artista": track["artists"][0]["name"], "titol": track["name"],
                            "bpm": "N/D", "clau": "N/D", "any": any_ll,
                            "spotify_uri": track["uri"],
                            "spotify_link": track["external_urls"]["spotify"],
                            "font": "Spotify"
                        }
                        if validar_canco_seguretat(canco, artista_nom):
                            cancons.append(canco)
                except:
                    pass
    except Exception as e:
        log(f"Error Spotify {artista_nom}: {e}", "error")
    return cancons

def cercar_discogs(artista_nom, any_triat, limit=20):
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
            url = f"https://api.discogs.com/database/search?artist={requests.utils.quote(artista_nom)}&year={any_actual}&type=master&per_page={limit}"
            resposta = requests.get(url, headers=headers, timeout=5)
            if resposta.status_code == 200:
                for r in resposta.json().get("results", [])[:limit]:
                    year = r.get("year")
                    if year and any_min <= year <= any_max:
                        canco = {
                            "artista": r.get("artist", artista_nom), "titol": r.get("title", ""),
                            "bpm": "N/D", "clau": "N/D", "any": year,
                            "spotify_uri": None, "spotify_link": None,
                            "discogs_link": r.get("resource_url", ""), "font": "Discogs"
                        }
                        if validar_canco_seguretat(canco, artista_nom):
                            cancons.append(canco)
            time.sleep(0.5)
        except Exception as e:
            log(f"Error Discogs {artista_nom}: {e}", "debug")
    return cancons

def cercar_musicbrainz(artista_nom, any_triat, limit=20):
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

def cercar_deezer(artista_nom, any_triat, limit=20):
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
# 10. UTILITATS
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

# ============================================================
# 12. INTERFICIE PRINCIPAL
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

                # PASSADA 1: IA troba artistes potencials
                artistes_passada1 = trobar_artistes_passada1(estil_triat)

                if not artistes_passada1:
                    log("IA no ha trobat artistes", "error")
                    st.error("La IA no ha pogut identificar artistes.")
                else:
                    # Mostrar artistes trobats a passada 1
                    st.info(f"IA Passada 1: {len(artistes_passada1)} artistes trobats")

                    # PASSADA 2: IA valida els seus propis resultats
                    artistes_validats = validar_artistes_passada2(artistes_passada1, estil_triat)

                    if not artistes_validats:
                        log("IA no ha validat cap artiste", "error")
                        st.error("La IA no ha pogut validar els artistes trobats.")
                    else:
                        # Mostrar artistes validats amb confiança
                        artistes_text = "\n".join([f"{a} ({g}) [{c}]" for a, g, c in artistes_validats])
                        st.info(f"IA Passada 2: {len(artistes_validats)} artistes validats:\n\n{artistes_text}")

                        totes_cancons = []

                        # Cercar per cada artiste validat
                        for artista_nom, artista_genere, confiança in artistes_validats:
                            if not validar_artista_seguretat(artista_nom):
                                log(f"Artista descartat (llista negra): {artista_nom}", "warning")
                                continue

                            log(f"Cercant: {artista_nom} ({artista_genere}) [{confiança}]...", "info")

                            cancons_spotify = cercar_spotify(sp, artista_nom, any_triat, limit=10)
                            cancons_discogs = cercar_discogs(artista_nom, any_triat, limit=10)
                            cancons_mb = cercar_musicbrainz(artista_nom, any_triat, limit=10)
                            cancons_deezer = cercar_deezer(artista_nom, any_triat, limit=10)

                            total = len(cancons_spotify) + len(cancons_discogs) + len(cancons_mb) + len(cancons_deezer)
                            if total > 0:
                                log(f"{artista_nom}: {total} cancons trobades", "success")

                            totes_cancons.extend(cancons_spotify)
                            totes_cancons.extend(cancons_discogs)
                            totes_cancons.extend(cancons_mb)
                            totes_cancons.extend(cancons_deezer)

                        # Processar resultats
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

        # ============= COLUMNA DRETA =============
        with col_dreta:
            st.subheader("Consola de Depuracio")
            render_console()

            if st.button("Netejar Consola", key="btn_netejar"):
                clear_console()
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
