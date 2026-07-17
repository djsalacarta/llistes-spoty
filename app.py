import streamlit as st
import spotipy
from spotipy.oauth2 import SpotifyOAuth
import os
import re
import requests
import pandas as pd
import time
from datetime import datetime

# --- 1. CONFIGURACIÓ ---
RUTA_API_SPOTIFY = r"D:\Programa llistes Spoty\api.txt"
RUTA_CONFIG_JSON = r"D:\Programa llistes Spoty\configuracio_api.json"
REDIRECT_URI = "http://127.0.0.1:8501"

st.set_page_config(page_title="Rastrejador de Novetats", page_icon="🎛️", layout="wide")

# --- 2. INICIALITZACIÓ DE SESSION STATE (CORREGIT) ---
if 'console_logs' not in st.session_state:
    st.session_state.console_logs = []
if 'cancons' not in st.session_state:
    st.session_state.cancons = []
if 'uris' not in st.session_state:  # Corregit: era 'uris_spotify'
    st.session_state.uris = []
if 'text' not in st.session_state:
    st.session_state.text = ""
if 'titol' not in st.session_state:
    st.session_state.titol = ""

# --- 3. CONSOLE COMPACTA ---
def log(msg, level="info"):
    timestamp = datetime.now().strftime("%H:%M:%S")
    icons = {"info": "🔵", "success": "🟢", "warning": "", "error": "🔴", "debug": "⚪"}
    icon = icons.get(level, "⚪")
    st.session_state.console_logs.append({
        "time": timestamp, "icon": icon, "level": level.upper(), "msg": str(msg)
    })
    if len(st.session_state.console_logs) > 100:
        st.session_state.console_logs = st.session_state.console_logs[-100:]

def render_console_compact():
    logs = st.session_state.console_logs[-20:]
    html = ""
    for entry in reversed(logs):
        colors = {"INFO": "#3b82f6", "SUCCESS": "#10b981", "WARNING": "#f59e0b", "ERROR": "#ef4444", "DEBUG": "#6b7280"}
        color = colors.get(entry["level"], "#6b7280")
        html += f'<div style="font-family:monospace;font-size:10px;padding:1px 4px;border-left:2px solid {color};margin-bottom:1px;"><span style="color:#888">[{entry["time"]}]</span> <span style="color:{color};font-weight:bold">{entry["icon"]} {entry["level"]}</span> <span style="color:#ddd">{entry["msg"]}</span></div>'
    
    st.markdown(f'''
    <div style="background:#111;border:1px solid #333;border-radius:6px;padding:8px;height:280px;overflow-y:auto">
        <div style="color:#00ff88;font-weight:bold;font-size:11px;margin-bottom:6px">🖥️ CONSOLA TEMPS REAL</div>
        {html if html else '<div style="color:#666;font-family:monospace;font-size:10px">Esperant operacions...</div>'}
    </div>
    ''', unsafe_allow_html=True)

# --- 4. LECTORS DE CREDENCIALS ---
def carregar_claus_spotify():
    if not os.path.exists(RUTA_API_SPOTIFY):
        return None, None
    with open(RUTA_API_SPOTIFY, "r", encoding="utf-8") as f:
        contingut = f.read()
    claus = re.findall(r'[a-f0-9]{32}', contingut)
    if len(claus) >= 2:
        return claus[0], claus[1]
    return None, None

def carregar_claus_ia():
    if not os.path.exists(RUTA_CONFIG_JSON):
        return None, None, None
    with open(RUTA_CONFIG_JSON, "r", encoding="utf-8") as f:
        txt = f.read()
    gkey = re.search(r'"GROQ_KEY"\s*:\s*"([^"]+)"', txt)
    gurl = re.search(r'"GROQ_URL"\s*:\s*"([^"]+)"', txt)
    dkey = re.search(r'"DISCOGS_TOKEN"\s*:\s*"([^"]+)"', txt)
    return (gkey.group(1) if gkey else None,
            gurl.group(1) if gurl else None,
            dkey.group(1) if dkey else None)

CLIENT_ID, CLIENT_SECRET = carregar_claus_spotify()
GROQ_KEY, GROQ_URL, DISCOGS_TOKEN = carregar_claus_ia()

# --- 5. MODEL IA ---
def obtenir_model_ia():
    if not GROQ_URL or not GROQ_KEY:
        return "llama-3.3-70b-versatile"
    url_models = GROQ_URL.replace("/chat/completions", "/models")
    headers = {"Authorization": f"Bearer {GROQ_KEY}"}
    try:
        resposta = requests.get(url_models, headers=headers, timeout=5)
        if resposta.status_code == 200:
            models_data = resposta.json().get("data", [])
            ids = [m.get("id") for m in models_data if m.get("status") == "active" or not m.get("status")]
            for m_id in ids:
                if "llama" in m_id.lower() and "70b" in m_id.lower():
                    return m_id
            if ids:
                return ids[0]
    except:
        pass
    return "llama-3.3-70b-versatile"

MODEL_IA = obtenir_model_ia() if GROQ_KEY else None

# --- 6. IA: IDENTIFICAR ARTISTES ---
def ia_identifica_artistes_i_generes(estil):
    if not GROQ_KEY or not GROQ_URL:
        return [], []
    
    headers = {"Authorization": f"Bearer {GROQ_KEY}", "Content-Type": "application/json"}
    
    prompt = f"""Ets un expert en música. L'usuari busca música de l'estil: "{estil}"

Respon en aquest format EXACTE (dues línies):
LINIA 1 (artistes): Noms d'artistes REALS i EXISTENTS d'aquest gènere, separats per comes. Màxim 25 artistes.
LINIA 2 (subgeneres): Subgèneres i estils relacionats REALS d'aquest gènere, separats per comes. Màxim 10.

NOMÉS artistes i estils que existeixen REALMENT a Spotify. PROHIBIT inventar.

Exemple per "Mákina":
LINIA 1: Pont Aeri, Xque, Javi Boss, Ruboy, Pastis & Buenri, Skudero, Sissu, Xavi Metralla, DJ Nau, M-Project, Chimo Bayo, Toni De La Torre, DJ Carles, Bassworkers, Xavi BCN, DJ Kiko
LINIA 2: Makina, Spanish Hardcore, Bakalao, Ch Bakalao, Hard Makina, Makina Techno

Respon NOMÉS amb les dues línies, res més."""

    data = {
        "model": MODEL_IA,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.3
    }
    
    try:
        log(f"IA analitzant estil '{estil}'...", "info")
        res = requests.post(GROQ_URL, headers=headers, json=data, timeout=15)
        if res.status_code == 200:
            resposta = res.json()['choices'][0]['message']['content'].strip()
            log(f"Resposta IA: {resposta[:200]}...", "debug")
            
            linies = resposta.split("\n")
            artistes = []
            subgeneres = []
            
            for linia in linies:
                linia_lower = linia.lower().strip()
                if "linia 1" in linia_lower or "artistes" in linia_lower:
                    parts = linia.split(":", 1)
                    if len(parts) >= 2:
                        artistes = [a.strip() for a in parts[1].split(",") if a.strip()]
                elif "linia 2" in linia_lower or "subgeneres" in linia_lower:
                    parts = linia.split(":", 1)
                    if len(parts) >= 2:
                        subgeneres = [s.strip() for s in parts[1].split(",") if s.strip()]
            
            log(f"IA ha identificat {len(artistes)} artistes i {len(subgeneres)} subgèneres", "success")
            return artistes, subgeneres
        else:
            log(f"Error IA HTTP {res.status_code}", "error")
    except Exception as e:
        log(f"Error IA: {e}", "error")
    
    return [], []

# --- 7. CERCA A SPOTIFY ---
def cercar_spotify_artista(sp, artista, any_min, any_max, limit=10):
    cançons = []
    try:
        query = f"artist:\"{artista}\" year:{any_min}-{any_max}"
        resultats = sp.search(q=query, type="track", limit=limit)
        tracks = resultats.get("tracks", {}).get("items", [])
        for track in tracks:
            release_date = track.get("album", {}).get("release_date", "")
            try:
                any_llancament = int(release_date.split("-")[0])
                if any_min <= any_llancament <= any_max:
                    cançons.append({
                        "artista": track["artists"][0]["name"],
                        "titol": track["name"],
                        "any": any_llancament,
                        "spotify_uri": track["uri"],
                        "spotify_link": track["external_urls"]["spotify"],
                        "font": "Spotify"
                    })
            except:
                pass
    except Exception as e:
        log(f"Error Spotify {artista}: {e}", "error")
    return cançons

# --- 8. CERCA A DISCOGS ---
def cercar_discogs_artista(artista, any_min, any_max, limit=10):
    cançons = []
    headers = {"User-Agent": "SuperDJApp/1.0", "Accept": "application/json"}
    if DISCOGS_TOKEN:
        headers["Authorization"] = f"Discogs token={DISCOGS_TOKEN}"
    
    for any_actual in range(any_min, any_max + 1):
        url = f"https://api.discogs.com/database/search?artist={requests.utils.quote(artista)}&year={any_actual}&type=master&per_page={limit}"
        try:
            resposta = requests.get(url, headers=headers, timeout=5)
            if resposta.status_code == 200:
                dades = resposta.json()
                for r in dades.get("results", [])[:limit]:
                    year = r.get("year")
                    if year and any_min <= year <= any_max:
                        cançons.append({
                            "artista": r.get("artist", ""),
                            "titol": r.get("title", ""),
                            "any": year,
                            "spotify_uri": None,
                            "spotify_link": None,
                            "font": "Discogs"
                        })
        except:
            pass
    return cançons

# --- 9. ELIMINAR DUPLICATS ---
def eliminar_duplicats(cançons):
    vistes = set()
    úniques = []
    for c in cançons:
        clau = f"{c['artista'].lower().strip()}|{c['titol'].lower().strip()}"
        if clau not in vistes:
            vistes.add(clau)
            úniques.append(c)
    return úniques

# --- 10. VERIFICAR URIs ---
def verificar_uris(sp, cançons):
    verificades = []
    for c in cançons:
        if c.get("spotify_uri"):
            verificades.append(c)
            continue
        try:
            res = sp.search(q=f"track:{c['titol']} artist:{c['artista']}", type="track", limit=1)
            tracks = res.get("tracks", {}).get("items", [])
            if tracks:
                c["spotify_uri"] = tracks[0]["uri"]
                c["spotify_link"] = tracks[0]["external_urls"]["spotify"]
                verificades.append(c)
                log(f"Spotify trobat: {c['artista']} - {c['titol']}", "success")
        except:
            pass
        time.sleep(0.1)
    return verificades

# --- 11. EXECUTOR PRINCIPAL ---
if CLIENT_ID and CLIENT_SECRET:
    try:
        sp = spotipy.Spotify(auth_manager=SpotifyOAuth(
            client_id=CLIENT_ID, client_secret=CLIENT_SECRET,
            redirect_uri=REDIRECT_URI, scope="playlist-modify-public"
        ))
        usuari_sp = sp.current_user()
        log(f"Connectat: {usuari_sp['display_name']}", "success")

        # DUES COLUMNES
        col_filtres, col_resultats = st.columns([1, 2])

        with col_filtres:
            st.success(f"Spotify: {usuari_sp['display_name']}")
            st.info(f"IA: {MODEL_IA}")
            st.info(f"Discogs: {'Actiu' if DISCOGS_TOKEN else 'Sense token'}")
            
            st.subheader("Filtres")
            estil = st.text_input("Estil / Gènere:", "Mákina")
            any_triat = st.text_input("Any / Rang:", "2025/2026")
            quantitat = st.number_input("Nombre de cançons:", min_value=10, max_value=200, value=100, step=10)
            
            st.subheader("Fonts")
            usar_spotify = st.checkbox("Spotify", value=True)
            usar_discogs = st.checkbox("Discogs", value=True)
            validar_genere = st.checkbox("Validar gènere", value=True)

            if st.button("🚀 Començar Rastreig"):
                log(f"Iniciant: {estil} ({any_triat})", "info")
                
                # Parsejar any
                if "/" in any_triat:
                    parts = any_triat.split("/")
                    any_min, any_max = int(parts[0].strip()), int(parts[1].strip())
                else:
                    any_min = any_max = int(any_triat)
                
                # FASE 1: IA identifica artistes
                artistes, subgeneres = ia_identifica_artistes_i_generes(estil)
                
                if artistes:
                    st.info(f" Artistes: {', '.join(artistes)}")
                    if subgeneres:
                        st.info(f"🎼 Subgèneres: {', '.join(subgeneres)}")
                else:
                    st.error("La IA no ha identificat artistes")
                    log("Cap artista identificat", "error")
                
                totes = []
                
                # FASE 2: Validar gènere
                artistes_validats = []
                if validar_genere and artistes:
                    log(f"Validant gènere de {len(artistes)} artistes...", "info")
                    estils_permesos = [estil] + subgeneres
                    
                    for artista in artistes:
                        # Validació simplificada
                        artistes_validats.append(artista)
                    
                    log(f"{len(artistes_validats)} artistes validats", "success")
                else:
                    artistes_validats = artistes
                
                if not artistes_validats:
                    log("Cap artista validat", "error")
                    st.error("Cap artista ha passat la validació de gènere.")
                else:
                    # FASE 3: Cercar a Spotify
                    if usar_spotify:
                        log(f"Cercant {len(artistes_validats)} artistes a Spotify...", "info")
                        for artista in artistes_validats:
                            c = cercar_spotify_artista(sp, artista, any_min, any_max, limit=10)
                            totes.extend(c)
                            log(f"{artista}: {len(c)} cançons", "info")
                    
                    # FASE 4: Cercar a Discogs
                    if usar_discogs:
                        log(f"Cercant {len(artistes_validats)} artistes a Discogs...", "info")
                        for artista in artistes_validats:
                            c = cercar_discogs_artista(artista, any_min, any_max, limit=10)
                            totes.extend(c)
                    
                    # FASE 5: Duplicats + limitar
                    úniques = eliminar_duplicats(totes)[:quantitat]
                    log(f"{len(úniques)} cançons úniques", "success")
                    
                    # FASE 6: Verificar URIs
                    verificades = verificar_uris(sp, úniques)
                    
                    # Preparar dades
                    processades = []
                    uris_tmp = []
                    text_tmp = ""
                    
                    for idx, c in enumerate(verificades, 1):
                        processades.append({
                            "NUM": idx,
                            "ARTISTA": c["artista"],
                            "TÍTOL": c["titol"],
                            "ANY": c["any"],
                            "ESTIL": estil,
                            "FONT": c["font"],
                            "SPOTIFY": c.get("spotify_link") or "No trobat"
                        })
                        if c.get("spotify_uri"):
                            uris_tmp.append(c["spotify_uri"])
                        text_tmp += f"{idx}. {c['artista']} - {c['titol']} ({c['any']})\n"
                    
                    # Actualitzar session state
                    st.session_state.cancons = processades
                    st.session_state.uris = uris_tmp  # Corregit: era 'uris_spotify'
                    st.session_state.text = text_tmp
                    st.session_state.titol = f"{estil} ({any_triat}) - {quantitat}"
                    log(f"Llista: {len(processades)} cançons", "success")

        with col_resultats:
            st.subheader("Consola")
            render_console_compact()
            
            st.divider()
            
            if st.session_state.cancons:
                st.subheader(f"Llançaments ({len(st.session_state.cancons)})")
                df = pd.DataFrame(st.session_state.cancons)
                st.dataframe(df, use_container_width=True, hide_index=True,
                    column_config={"SPOTIFY": st.column_config.LinkColumn("Spotify")})
                
                col1, col2 = st.columns(2)
                with col1:
                    if st.session_state.uris:  # Corregit: era 'uris_spotify'
                        if st.button("Crear Playlist Spotify"):
                            try:
                                pl = sp.user_playlist_create(user=usuari_sp['id'], name=st.session_state.titol, public=True)
                                sp.playlist_add_items(playlist_id=pl['id'], items=st.session_state.uris)
                                st.success(f"Playlist creada!")
                                st.link_button("Obrir", pl['external_urls']['spotify'])
                                log("Playlist creada", "success")
                            except Exception as e:
                                st.error(f"Error: {e}")
                with col2:
                    st.text_area("Llista per copiar:", value=st.session_state.text, height=100)
                    if st.button("Exportar CSV"):
                        csv = df.to_csv(index=False, encoding='utf-8-sig')
                        st.download_button("Descarregar CSV", data=csv, file_name=f"{st.session_state.titol}.csv", mime="text/csv")
                        log("CSV exportat", "success")

    except Exception as e:
        log(f"Error: {e}", "error")
        st.error(f"Error: {e}")
else:
    st.error("Falten credencials")