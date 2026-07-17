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

# --- 1. CONFIGURACIÓ ---
RUTA_API_SPOTIFY = r"D:\Programa llistes Spoty\api.txt"
RUTA_CONFIG_JSON = r"D:\Programa llistes Spoty\configuracio_api.json"
REDIRECT_URI = "http://127.0.0.1:8501"

st.set_page_config(page_title="Rastrejador de Novetats Reals", page_icon="🎛️", layout="wide")

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
        "debug": "⚪"
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
    
    # Generar HTML per la consola
    html_lines = []
    for entry in st.session_state.console_logs[-50:]:
        html_lines.append(
            f'<div style="font-family: \'Courier New\', monospace; font-size: 11px; padding: 2px 4px; border-left: 2px solid {entry["color"]}; margin-bottom: 1px;">'
            f'<span style="color: #888;">[{entry["time"]}]</span> '
            f'<span style="color: {entry["color"]}; font-weight: bold;">{entry["icon"]} {entry["level"]}</span> '
            f'<span style="color: #e0e0e0;">{entry["msg"]}</span>'
            f'</div>'
        )
    
    st.session_state.console_html = "\n".join(html_lines)

def clear_console():
    st.session_state.console_logs = []
    st.session_state.console_html = ""

def render_console_permanent():
    """Renderitza la consola permanent amb fons negre"""
    init_console()
    
    console_html = st.session_state.console_html
    
    if not console_html:
        console_html = '<div style="color: #666; font-family: monospace; padding: 20px; text-align: center;">⏳ Esperant operacions...</div>'
    
    st.markdown(
        f'''
        <div style="
            background: #0a0a0a;
            border: 2px solid #333;
            border-radius: 8px;
            padding: 10px;
            height: 500px;
            overflow-y: auto;
            font-family: \'Courier New\', monospace;
            box-shadow: 0 0 20px rgba(0, 255, 136, 0.1);
        ">
            <div style="
                position: sticky;
                top: 0;
                background: #1a1a1a;
                padding: 5px 10px;
                border-bottom: 1px solid #333;
                margin-bottom: 10px;
                border-radius: 4px;
                display: flex;
                justify-content: space-between;
                align-items: center;
            ">
                <span style="color: #00ff88; font-weight: bold; font-size: 12px;">🖥️ CONSOLA DE DEPURACIÓ - TEMPS REAL</span>
                <span style="color: #888; font-size: 11px;">{len(st.session_state.console_logs)} registres</span>
            </div>
            {console_html}
        </div>
        ''',
        unsafe_allow_html=True
    )

# --- 3. LECTORS DE CREDENCIALS ---
def carregar_credencials():
    """Carrega credencials de st.secrets (Cloud) o fitxers locals (Windows)"""
    creds = {
        "CLIENT_ID": "",
        "CLIENT_SECRET": "",
        "GROQ_KEY": "",
        "GROQ_URL": "",
        "DISCOGS_TOKEN": ""
    }

    try:
        creds["CLIENT_ID"] = st.secrets.get("SPOTIFY_CLIENT_ID", "")
        creds["CLIENT_SECRET"] = st.secrets.get("SPOTIFY_CLIENT_SECRET", "")
        creds["GROQ_KEY"] = st.secrets.get("GROQ_KEY", "")
        creds["GROQ_URL"] = st.secrets.get("GROQ_URL", "")
        creds["DISCOGS_TOKEN"] = st.secrets.get("DISCOGS_TOKEN", "")
    except Exception:
        pass

    if not creds["CLIENT_ID"]:
        if os.path.exists(RUTA_API_SPOTIFY):
            try:
                with open(RUTA_API_SPOTIFY, "r", encoding="utf-8") as f:
                    contingut = f.read()
                claus = re.findall(r'[a-f0-9]{32}', contingut)
                if len(claus) >= 2:
                    creds["CLIENT_ID"] = claus[0]
                    creds["CLIENT_SECRET"] = claus[1]
            except Exception:
                pass

    if not creds["GROQ_KEY"]:
        if os.path.exists(RUTA_CONFIG_JSON):
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

# --- 4. OBTENCIÓ DE MODELS IA ---
def obtenir_model_ia_actulitzat():
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
            if ids: return ids[0]
    except: pass
    return "llama-3.3-70b-versatile"

MODEL_IA_VIVU = obtenir_model_ia_actulitzat() if GROQ_KEY else None

# --- 5. IA: IDENTIFICAR ARTISTES REALS ---
def identificar_artistes_reals_genere(estil):
    if not GROQ_KEY or not GROQ_URL:
        log("No hi ha claus IA", "warning")
        return []
    
    headers = {"Authorization": f"Bearer {GROQ_KEY}", "Content-Type": "application/json"}
    
    prompt = f"""
Ets un expert en música electrònica.
L'usuari busca música de l'estil: "{estil}"
Identifica ARTISTES REALS I EXISTENTS d'aquest gènere musical.
NOMÉS artistes reals, PROHIBIT inventar.
Màxim 20-25 artistes. Format: noms separats per comes.
Exemples vàlids per "Mákina": Pont Aeri, Xque, Javi Boss, Ruboy, Pastis & Buenri, Skudero, Sissu, Xavi Metralla, DJ Nau, M-Project, Chimo Bayo
Respon NOMÉS amb la llista d'artistes reals separats per comes.
"""
    
    data = {
        "model": MODEL_IA_VIVU,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.3
    }
    
    try:
        log(f"IA identificant artistes reals de '{estil}'...", "info")
        res = requests.post(GROQ_URL, headers=headers, json=data, timeout=15)
        if res.status_code == 200:
            resposta = res.json()['choices'][0]['message']['content'].strip()
            artistes = [a.strip() for a in resposta.split(",") if a.strip()]
            if not artistes:
                return []
            log(f"IA ha identificat {len(artistes)} artistes reals", "success")
            return artistes
        else:
            return []
    except Exception as e:
        log(f"Error connectant amb la IA: {e}", "error")
        return []

# --- 6. VALIDACIÓ DE GÈNERE A SPOTIFY ---
def validar_genere_artista_spotify(sp, artista, estils_permesos):
    try:
        resultats = sp.search(q=f"artist:{artista}", type="artist", limit=1)
        artists = resultats.get("artists", {}).get("items", [])

        if not artists:
            log(f"Artista no trobat a Spotify: {artista} - Acceptat per cerca a Discogs", "info")
            return True

        artist = artists[0]
        genres = artist.get("genres", [])

        log(f"{artista} - Gèneres a Spotify: {genres if genres else 'Sense gèneres'}", "debug")

        if not genres:
            log(f"{artista} acceptat (sense gèneres a Spotify)", "info")
            return True

        for genre in genres:
            genre_lower = genre.lower()
            for estil_permes in estils_permesos:
                estil_permes_lower = estil_permes.lower()
                if estil_permes_lower in genre_lower or genre_lower in estil_permes_lower:
                    log(f"{artista} és del gènere correcte: {genre}", "success")
                    return True

        artista_lower = artista.lower()
        paraules_clau_makina = ["makina", "mákina", "hardcore", "bakalao", "rave", "tekno", "gabber", "jumpstyle"]
        for paraula in paraules_clau_makina:
            if paraula in artista_lower:
                log(f"{artista} acceptat per nom (conté paraula clau del gènere)", "info")
                return True

        log(f"{artista} descartat. Gèneres trobats: {genres}", "warning")
        return False

    except Exception as e:
        log(f"Error validant gènere de {artista}: {e}", "error")
        return True


# --- 7. CERCA NOvetats ARTISTA a SPOTIFY ---
def cercar_novetats_artista_spotify(sp, artista, any_triat, limit=20):
    cançons = []
    
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
                        "bpm": "N/D",
                        "clau": "N/D",
                        "any": any_llancament,
                        "spotify_uri": track["uri"],
                        "spotify_link": track["external_urls"]["spotify"],
                        "font": "Spotify"
                    })
                    log(f"{artista}: {track['name']} ({any_llancament})", "debug")
            except:
                pass
    except Exception as e:
        log(f"Error cercant {artista}: {e}", "error")
    
    return cançons

# --- 8. CERCA NOvetats ARTISTA a DISCOGS ---
def cercar_novetats_artista_discogs(artista, any_triat, limit=20):
    cançons = []
    
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
        url = f"https://api.discogs.com/database/search?artist={requests.utils.quote(artista)}&year={any_actual}&type=master&per_page={limit}"
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
                            cançons.append({
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
        except Exception as e:
            pass
    
    return cançons

# --- 9. ELIMINAR DUPLICATS ---
def eliminar_duplicats(cançons):
    vistes = set()
    cançons_úniques = []
    for canço in cançons:
        clau = f"{canço['artista'].lower().strip()}|{canço['titol'].lower().strip()}"
        if clau not in vistes:
            vistes.add(clau)
            cançons_úniques.append(canço)
    return cançons_úniques

# --- 10. VERIFICAR A SPOTIFY I OBTENIR URIs ---
def verificar_i_obtenir_uris(sp, cançons):
    log(f"Verificant {len(cançons)} cançons a Spotify...", "info")
    cançons_verificades = []
    for idx, canço in enumerate(cançons):
        if canço.get("spotify_uri"):
            cançons_verificades.append(canço)
            continue
        try:
            query = f"track:{canço['titol']} artist:{canço['artista']}"
            resultats = sp.search(q=query, type="track", limit=1)
            tracks = resultats.get("tracks", {}).get("items", [])
            if tracks:
                track = tracks[0]
                canço["spotify_uri"] = track["uri"]
                canço["spotify_link"] = track["external_urls"]["spotify"]
                cançons_verificades.append(canço)
                log(f"Spotify trobat: {canço['artista']} - {canço['titol']}", "success")
        except Exception as e:
            log(f"Error verificant {canço['artista']}: {e}", "error")
        time.sleep(0.1)
    return cançons_verificades

# --- 11. EXECUTOR PRINCIPAL ---

# 🔴 SOLUCIÓ BUG 1: Inicialitzem les variables a l'inici de tot el procés principal
if 'cancons_reals' not in st.session_state:
    st.session_state.cancons_reals = []
if 'uris_spotify' not in st.session_state:
    st.session_state.uris_spotify = []
if 'text_copiar' not in st.session_state:
    st.session_state.text_copiar = ""
if 'titol_playlist' not in st.session_state:
    st.session_state.titol_playlist = "Nova Playlist Mákina"

if CLIENT_ID and CLIENT_SECRET:
    try:
        log("Inicialitzant connexió amb Spotify...", "info")
        sp = spotipy.Spotify(auth_manager=SpotifyOAuth(
            client_id=CLIENT_ID, client_secret=CLIENT_SECRET,
            redirect_uri=REDIRECT_URI, scope="playlist-modify-public"
        ))
        usuari_sp = sp.current_user()
        log(f"Connectat a Spotify com: {usuari_sp['display_name']}", "success")

        # DIVIDIR PANTALLA EN DUES COLUMNES
        col_filtres, col_consola = st.columns([1, 2])

        with col_filtres:
            st.success(f"Spotify: {usuari_sp['display_name']}")
            st.info(f"IA activa: {MODEL_IA_VIVU}")
            st.info(f"Discogs: {'Actiu' if DISCOGS_TOKEN else 'Sense token'}")

            st.subheader("Filtres de la Cerca")
            estil_triat = st.text_input("Estil / Gènere:", "Mákina")
            mes_triat = st.selectbox("Mes de llançament:", [
                "Tots els mesos (Any sencer)", "Gener", "Febrer", "Març", "Abril", "Maig", "Juny",
                "Juliol", "Agost", "Setembre", "Octubre", "Novembre", "Desembre"
            ], index=0)
            any_triat = st.text_input("Any / Rang (Ex: 1999, 2025/2026):", "2025/2026")
            
            tipus_referencia = st.radio(
                "Tipus de referència:",
                ["Cançó", "Artista"],
                horizontal=True
            )
            
            if "Cançó" in tipus_referencia:
                llavor_input = st.text_input(
                    "Introdueix una CANÇÓ de referència:",
                    placeholder="Ex: Pont Aeri - Flying Free"
                )
            else:
                llavor_input = st.text_input(
                    "Introdueix un ARTISTA de referència:",
                    placeholder="Ex: Pont Aeri"
                )
            
            quantitat = st.number_input("Nombre de cançons:", min_value=10, max_value=200, value=100, step=10)

            st.subheader("Fonts de cerca")
            usar_spotify = st.checkbox("API de Spotify", value=True)
            usar_discogs = st.checkbox("API de Discogs", value=True)
            usar_musicbrainz = st.checkbox("MusicBrainz", value=True)
            usar_deezer = st.checkbox("Deezer (gratuïta)", value=False)
            usar_beatport = st.checkbox("Beatport (raspat)", value=False)
            
            st.subheader("Opcions avançades")
            any_estricte = st.checkbox("Any estricte (sentit clàssics)", value=True)
            validar_genere = st.checkbox("Validar gènere a Spotify (recomanat)", value=True)

            if st.button("Començar Rastreig de Novetats"):
                log(f"Iniciant rastreig: estil={estil_triat}, any={any_triat}, quantitat={quantitat}", "info")
                
                # FASE 1: La IA identifica ARTISTES REALS
                log("IA identificant artistes reals del gènere...", "info")
                artistes_reals = identificar_artistes_reals_genere(estil_triat)
                
                if not artistes_reals:
                    log("La IA no ha pogut identificar artistes reals", "error")
                    st.error("La IA no ha pogut identificar artistes reals del gènere.")
                else:
                    st.info(f"La IA ha identificat {len(artistes_reals)} artistes reals de {estil_triat}:\n\n{', '.join(artistes_reals)}")
                    
                    totes_cançons = []
                    
                    # FASE 2: Validar gènere
                    artistes_validats = []
                    if validar_genere:
                        log(f"Validant gènere de {len(artistes_reals)} artistes...", "info")
                        estils_permesos = [estil_triat]
                        
                        if "makina" in estil_triat.lower() or "mákina" in estil_triat.lower():
                            estils_permesos.extend(["makina", "mákina", "spanish hardcore", "bakalao", "ch bakalao", "hard makina"])
                        elif "hardcore" in estil_triat.lower():
                            estils_permesos.extend(["hardcore", "gabber", "mainstream hardcore", "happy hardcore"])
                        elif "techno" in estil_triat.lower():
                            estils_permesos.extend(["techno", "hard techno", "industrial techno", "schranz"])
                        
                        for idx, artista in enumerate(artistes_reals):
                            es_valid = validar_genere_artista_spotify(sp, artista, estils_permesos)
                            if es_valid:
                                artistes_validats.append(artista)
                        
                        log(f"{len(artistes_validats)} artistes validats del gènere correcte (de {len(artistes_reals)})", "success")
                    else:
                        artistes_validats = artistes_reals
                    
                    if not artistes_validats:
                        log("Cap artista ha passat la validació de gènere", "error")
                        st.error("Cap artista ha passat la validació de gènere.")
                    else:
                        # FASE 3: Cercar novetats a Spotify
                        if usar_spotify:
                            log(f"Cercant novetats de {len(artistes_validats)} artistes a Spotify...", "info")
                            for idx, artista in enumerate(artistes_validats):
                                cançons_artista = cercar_novetats_artista_spotify(sp, artista, any_triat, limit=10)
                                totes_cançons.extend(cançons_artista)
                                log(f"{artista}: {len(cançons_artista)} cançons trobades", "info")
                        
                        # FASE 4: Cercar novetats a Discogs
                        if usar_discogs:
                            log(f"Cercant novetats de {len(artistes_validats)} artistes a Discogs...", "info")
                            for idx, artista in enumerate(artistes_validats):
                                cançons_artista = cercar_novetats_artista_discogs(artista, any_triat, limit=10)
                                totes_cançons.extend(cançons_artista)
                                log(f"{artista}: {len(cançons_artista)} cançons trobades a Discogs", "info")
                        
                        # FASE 5: Eliminar duplicats
                        log("Eliminant duplicats...", "info")
                        cançons_úniques = eliminar_duplicats(totes_cançons)
                        log(f"Després d'eliminar duplicats: {len(cançons_úniques)} cançons", "success")
                        
                        # FASE 6: Limitar a la quantitat demanada
                        cançons_finals = cançons_úniques[:quantitat]
                        log(f"Total cançons reals trobades: {len(cançons_finals)}", "success")
                        
                        # FASE 7: Verificar a Spotify i obtenir URIs
                        log("Verificant a Spotify i obtenint URIs...", "info")
                        cançons_verificades = verificar_i_obtenir_uris(sp, cançons_finals)
                        
                        # Preparar dades per mostrar
                        cancons_processades = []
                        uris_tmp = []
                        text_tmp = ""
                        
                        for idx, canço in enumerate(cançons_verificades, 1):
                            cancons_processades.append({
                                "NUM": idx, "ARTISTA": canço["artista"], "TÍTOL REAL": canço["titol"],
                                "BPM": canço["bpm"], "CLAU HARMÒNICA": canço["clau"],
                                "ANY ORIGINARI": canço["any"], "ESTIL CONFIGURAT": estil_triat,
                                "FONT": canço["font"], "ENLLAÇ SPOTIFY": canço.get("spotify_link") or "No trobat",
                                "ENLLAÇ TIDAL": "No trobat"
                            })
                            if canço.get("spotify_uri"):
                                uris_tmp.append(canço["spotify_uri"])
                            text_tmp += f"{idx}. {canço['artista']} - {canço['titol']} ({canço['any']})\n"
                        
                        log(f"Llista guardada: {len(cancons_processades)} cançons", "success")
                        
                        st.session_state.cancons_reals = cancons_processades
                        st.session_state.uris_spotify = uris_tmp
                        st.session_state.text_copiar = text_tmp
                        st.session_state.titol_playlist = f"{estil_triat[:10]} ({any_triat}) - {quantitat} cançons"

        with col_consola:
            st.subheader("Consola de Depuració - Temps Real")
            render_console_permanent()
            
            col_btn1, col_btn2 = st.columns(2)
            with col_btn1:
                    if st.session_state.uris_spotify:
                        # 🔴 SOLUCIÓ: Posem key="input_nom_consola" per evitar duplicats
                        nom_llista_consola = st.text_input(
                            "Nom de la playlist a Spotify:", 
                            value=st.session_state.titol_playlist,
                            key="input_nom_consola"
                        )
                        
                        # 🔴 SOLUCIÓ BUG 2: Afegim key="btn_crear_consola"
                        if st.button("Crear Playlist Automàtica a Spotify", key="btn_crear_consola"):
                            try:
                                log(f"Creant playlist '{nom_llista_consola}' a Spotify...", "info")
                                pl = sp.user_playlist_create(
                                    user=usuari_sp['id'],
                                    name=nom_llista_consola,
                                    public=True
                                )
                                # Spotify té un límit de 100 cançons per petició 'playlist_add_items'
                                for i in range(0, len(st.session_state.uris_spotify), 100):
                                    sp.playlist_add_items(
                                        playlist_id=pl['id'],
                                        items=st.session_state.uris_spotify[i:i+100]
                                    )
                                log(f"Playlist creada: {pl['external_urls']['spotify']}", "success")
                                st.success(f"Playlist '{nom_llista_consola}' creada amb èxit!")
                                st.link_button("Obrir Playlist", pl['external_urls']['spotify'])
                                st.session_state.titol_playlist = nom_llista_consola
                            except Exception as e:
                                log(f"Error creant playlist: {e}", "error")
                                st.error(f"Error creant playlist: {e}")
            
            # Mostrar resultats
            if 'cancons_reals' in st.session_state and st.session_state.cancons_reals:
                st.subheader(f"Llançaments Verificats ({len(st.session_state.cancons_reals)} cançons)")
                df = pd.DataFrame(st.session_state.cancons_reals)
                st.dataframe(
                    df, use_container_width=True, hide_index=True,
                    column_config={
                        "ENLLAÇ SPOTIFY": st.column_config.LinkColumn("SPOTIFY"),
                        "ENLLAÇ TIDAL": st.column_config.LinkColumn("TIDAL")
                    }
                )

                st.divider()
                col_btn_taula1, col_btn_taula2 = st.columns(2)

                with col_btn_taula1:
                    if st.session_state.uris_spotify:
                        # 🔴 SOLUCIÓ: Posem key="input_nom_taula" per evitar duplicats
                        nom_llista_taula = st.text_input(
                            "Nom de la playlist a Spotify:", 
                            value=st.session_state.titol_playlist,
                            key="input_nom_taula"
                        )
                        
                        # 🔴 SOLUCIÓ BUG 2: Afegim key="btn_crear_taula"
                        if st.button("Crear Playlist Automàtica a Spotify", key="btn_crear_taula"):
                            try:
                                log(f"Creant playlist '{nom_llista_taula}' a Spotify...", "info")
                                pl = sp.user_playlist_create(
                                    user=usuari_sp['id'],
                                    name=nom_llista_taula,
                                    public=True
                                )
                                for i in range(0, len(st.session_state.uris_spotify), 100):
                                    sp.playlist_add_items(
                                        playlist_id=pl['id'],
                                        items=st.session_state.uris_spotify[i:i+100]
                                    )
                                log(f"Playlist creada: {pl['external_urls']['spotify']}", "success")
                                st.success(f"Playlist '{nom_llista_taula}' creada amb èxit!")
                                st.link_button("Obrir Playlist", pl['external_urls']['spotify'])
                                st.session_state.titol_playlist = nom_llista_taula
                            except Exception as e:
                                log(f"Error creant playlist: {e}", "error")
                                st.error(f"Error creant playlist: {e}")

                with col_btn_taula2:
                    st.text_area("Llista de cançons per copiar:", value=st.session_state.text_copiar, height=120)
                    if st.button("Exportar CSV"):
                        csv = df.to_csv(index=False, encoding='utf-8-sig')
                        st.download_button(
                            label="Descarregar CSV", data=csv,
                            file_name=f"{st.session_state.titol_playlist}.csv",
                            mime="text/csv"
                        )
                        log("CSV exportat", "success")

    except Exception as e:
        log(f"Error de sistema: {e}", "error")
        st.error(f"Error de sistema: {e}")
else:
    log("Falten credencials de configuració", "error")
    st.error("Falten credencials de configuració.")
    st.info("Assegura't que els fitxers `api.txt` i `configuracio_api.json` existeixen a la ruta configurada.")