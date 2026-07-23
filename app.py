import streamlit as st
import spotipy
from spotipy.oauth2 import SpotifyOAuth
import os
import re
import requests
import pandas as pd
import json
import time
import random
from datetime import datetime
import firebase_admin
from firebase_admin import credentials, firestore
import traceback

# ============================================================
# 1. CONFIGURACIO
# ============================================================
RUTA_API_SPOTIFY = r"D:\Programa llistes Spoty\api.txt"
RUTA_CONFIG_JSON = r"D:\Programa llistes Spoty\configuracio_api.json"
RUTA_FIREBASE_JSON = "spoty-bd-firebase-adminsdk-fbsvc-846ece3ab5.json"
REDIRECT_URI = "http://127.0.0.1:8501"

st.set_page_config(page_title="Rastrejador de Novetats Reals v2.0.0", page_icon="🎛️", layout="wide")

# ============================================================
# 2. FIREBASE ADMIN - INICIALITZACIO AMB LOGS D'ERROR
# ============================================================
_db = None
_firebase_error = None

def init_firebase():
    global _db, _firebase_error
    if _db is not None:
        return _db
    try:
        if not firebase_admin._apps:
            firebase_creds = None
            # Intent 1: st.secrets
            try:
                firebase_creds = dict(st.secrets["firebase"])
                log("Firebase: credencials carregades de st.secrets", "info")
            except Exception as e:
                log(f"Firebase: st.secrets no disponible: {e}", "debug")

            # Intent 2: fitxer JSON local
            if not firebase_creds:
                if os.path.exists(RUTA_FIREBASE_JSON):
                    try:
                        with open(RUTA_FIREBASE_JSON, "r", encoding="utf-8") as f2:
                            firebase_creds = json.load(f2)
                        log(f"Firebase: credencials carregades de {RUTA_FIREBASE_JSON}", "info")
                    except Exception as e:
                        log(f"Firebase: error llegint JSON local: {e}", "error")
                else:
                    log(f"Firebase: fitxer {RUTA_FIREBASE_JSON} no trobat", "warning")

            if firebase_creds:
                pk = firebase_creds["private_key"]
                firebase_creds["private_key"] = pk.replace("\\n", chr(10))
                cred = credentials.Certificate(firebase_creds)
                firebase_admin.initialize_app(cred)
                _db = firestore.client()
                log("Firebase: connectat correctament", "success")
                return _db
            else:
                _firebase_error = "No s'han trobat credencials de Firebase (ni a st.secrets ni a fitxer local)"
                log(_firebase_error, "error")
        else:
            _db = firestore.client()
            log("Firebase: client reutilitzat", "debug")
            return _db
    except Exception as e:
        _firebase_error = f"Error Firebase: {str(e)}"
        log(_firebase_error, "error")
        log(traceback.format_exc(), "debug")
    return None

def get_db():
    if _db is None:
        return init_firebase()
    return _db

def firebase_ok():
    return _db is not None

def firebase_error_msg():
    return _firebase_error or "Firebase no inicialitzat"

# ============================================================
# 3. BASE DE DADES FIRESTORE
# ============================================================
def guardar_artista_confirmat(nom, genere, subgenere=None, font="IA", confianza="probable"):
    db = get_db()
    if not db:
        log(f"No es pot guardar {nom}: Firebase no connectat", "error")
        return False
    try:
        doc_id = f"{nom.lower().strip()}_{genere.lower().strip()}"
        doc_ref = db.collection("artistes_confirmats").document(doc_id)
        doc = doc_ref.get()
        if doc.exists:
            data = doc.to_dict()
            doc_ref.update({
                "cerca_count": data.get("cerca_count", 0) + 1,
                "confianza": "segur" if confianza == "segur" else data.get("confianza", "probable"),
                "data_afegit": firestore.SERVER_TIMESTAMP
            })
        else:
            doc_ref.set({
                "nom": nom,
                "genere": genere,
                "subgenere": subgenere or "",
                "font": font,
                "confianza": confianza,
                "data_afegit": firestore.SERVER_TIMESTAMP,
                "cerca_count": 1
            })
        log(f"Guardat: {nom} -> {genere}", "success")
        return True
    except Exception as e:
        log(f"Error guardant {nom}: {e}", "error")
        return False

def guardar_artista_rebutjat(nom, genere, motiu="No es del genere"):
    db = get_db()
    if not db:
        return False
    try:
        doc_id = f"{nom.lower().strip()}_{genere.lower().strip()}"
        db.collection("artistes_rebutjats").document(doc_id).set({
            "nom": nom,
            "genere": genere,
            "motiu": motiu,
            "data_rebutjat": firestore.SERVER_TIMESTAMP
        })
        return True
    except Exception as e:
        log(f"Error rebutjant {nom}: {e}", "error")
        return False

def guardar_canco_confirmada(titol, artista, genere, any_ll, bpm=None, clau=None, popularitat=None, font="Spotify", spotify_uri=None):
    db = get_db()
    if not db:
        return False
    try:
        doc_id = f"{titol.lower().strip()}_{artista.lower().strip()}_{genere.lower().strip()}"
        db.collection("cancons_confirmades").document(doc_id).set({
            "titol": titol,
            "artista": artista,
            "genere": genere,
            "any_ll": any_ll,
            "bpm": bpm,
            "clau": clau,
            "popularitat": popularitat,
            "font": font,
            "spotify_uri": spotify_uri or "",
            "data_afegit": firestore.SERVER_TIMESTAMP
        })
        return True
    except Exception as e:
        log(f"Error guardant canço {titol}: {e}", "error")
        return False

def consultar_artistes_db(genere, min_confianza="probable"):
    db = get_db()
    if not db:
        log("consultar_artistes_db: Firebase no disponible", "warning")
        return []
    try:
        mapping = {"segur": 1, "probable": 2, "dubtos": 3}
        min_nivell = mapping.get(min_confianza, 2)
        docs = db.collection("artistes_confirmats").where("genere", "==", genere).stream()
        resultats = []
        for doc in docs:
            d = doc.to_dict()
            nivell = mapping.get(d.get("confianza", "probable"), 3)
            if nivell <= min_nivell:
                resultats.append((d.get("nom"), d.get("subgenere") or "desconegut", d.get("confianza", "probable"), d.get("cerca_count", 1)))
        resultats.sort(key=lambda x: (mapping.get(x[2], 3), -x[3]))
        return resultats
    except Exception as e:
        log(f"Error consultant artistes: {e}", "error")
        return []

def consultar_rebutjats_db(genere):
    db = get_db()
    if not db:
        return set()
    try:
        docs = db.collection("artistes_rebutjats").where("genere", "==", genere).stream()
        return {d.to_dict().get("nom", "") for d in docs}
    except Exception as e:
        log(f"Error consultant rebutjats: {e}", "error")
        return set()

def obtenir_artistes_per_genere(genere):
    db = get_db()
    if not db:
        return []
    try:
        docs = db.collection("artistes_confirmats").where("genere", "==", genere).order_by("nom").stream()
        return [(d.to_dict().get("nom"), d.to_dict().get("subgenere"), d.to_dict().get("confianza"), d.to_dict().get("cerca_count", 0)) for d in docs]
    except Exception as e:
        log(f"Error obtenint artistes per genere: {e}", "error")
        return []

def obtenir_tots_generes_db():
    db = get_db()
    if not db:
        return []
    try:
        docs = db.collection("artistes_confirmats").stream()
        generes = {}
        for doc in docs:
            g = doc.to_dict().get("genere", "")
            if g:
                generes[g.lower()] = g
        docs2 = db.collection("generes_apresos").stream()
        for doc in docs2:
            g = doc.to_dict().get("nom_genere", "")
            if g:
                generes[g.lower()] = g
        return sorted(generes.values(), key=str.lower)
    except Exception as e:
        log(f"Error obtenint generes: {e}", "error")
        return []

def actualitzar_estadistiques_genere(genere):
    db = get_db()
    if not db:
        return
    try:
        docs_art = db.collection("artistes_confirmats").where("genere", "==", genere).stream()
        total_art = sum(1 for _ in docs_art)
        docs_can = db.collection("cancons_confirmades").where("genere", "==", genere).stream()
        total_can = sum(1 for _ in docs_can)
        db.collection("generes_apresos").document(genere.lower()).set({
            "nom_genere": genere,
            "total_artistes": total_art,
            "total_cancons": total_can,
            "ultima_actualitzacio": firestore.SERVER_TIMESTAMP
        }, merge=True)
    except Exception as e:
        log(f"Error actualitzant estadistiques: {e}", "error")

def obtenir_estadistiques_db():
    db = get_db()
    if not db:
        return {"artistes_confirmats": 0, "artistes_rebutjats": 0, "cancons_confirmades": 0, "generes_apresos": 0, "top_generes": []}
    try:
        total_conf = sum(1 for _ in db.collection("artistes_confirmats").stream())
        total_reb = sum(1 for _ in db.collection("artistes_rebutjats").stream())
        total_can = sum(1 for _ in db.collection("cancons_confirmades").stream())
        total_gen = sum(1 for _ in db.collection("generes_apresos").stream())
        docs = db.collection("generes_apresos").order_by("total_artistes", direction=firestore.Query.DESCENDING).limit(5).stream()
        top_generes = [(d.to_dict().get("nom_genere"), d.to_dict().get("total_artistes", 0), d.to_dict().get("total_cancons", 0)) for d in docs]
        return {
            "artistes_confirmats": total_conf, "artistes_rebutjats": total_reb,
            "cancons_confirmades": total_can, "generes_apresos": total_gen,
            "top_generes": top_generes
        }
    except Exception as e:
        log(f"Error obtenint estadistiques: {e}", "error")
        return {"artistes_confirmats": 0, "artistes_rebutjats": 0, "cancons_confirmades": 0, "generes_apresos": 0, "top_generes": []}

def esborrar_genere(genere):
    db = get_db()
    if not db:
        return
    try:
        for col_name in ["artistes_confirmats", "artistes_rebutjats", "cancons_confirmades"]:
            docs = db.collection(col_name).where("genere", "==", genere).stream()
            for doc in docs:
                doc.reference.delete()
        db.collection("generes_apresos").document(genere.lower()).delete()
        db.collection("generes_inteligents").document(genere.lower()).delete()
    except Exception as e:
        log(f"Error esborrant genere: {e}", "error")

# ============================================================
# 4. GENERES INTEL·LIGENTS
# ============================================================
def guardar_genere_inteligent(nom_genere, estils="", seeds="", color="#00ff88", icona="🎵"):
    db = get_db()
    if not db:
        return
    try:
        db.collection("generes_inteligents").document(nom_genere.lower().strip()).set({
            "nom_genere": nom_genere.lower().strip(),
            "estils": estils,
            "seeds": seeds,
            "color": color,
            "icona": icona,
            "data_creat": firestore.SERVER_TIMESTAMP
        }, merge=True)
    except Exception as e:
        log(f"Error guardant genere intel·ligent: {e}", "error")

def obtenir_generes_inteligents():
    db = get_db()
    if not db:
        return []
    try:
        docs = db.collection("generes_inteligents").order_by("nom_genere").stream()
        return [(d.to_dict().get("nom_genere"), d.to_dict().get("estils", ""), d.to_dict().get("seeds", ""), d.to_dict().get("color", "#00ff88"), d.to_dict().get("icona", "🎵")) for d in docs]
    except Exception as e:
        log(f"Error obtenint generes intel·ligents: {e}", "error")
        return []

def obtenir_genere_inteligent(nom_genere):
    db = get_db()
    if not db:
        return None
    try:
        doc = db.collection("generes_inteligents").document(nom_genere.lower().strip()).get()
        if doc.exists:
            d = doc.to_dict()
            return (d.get("nom_genere"), d.get("estils", ""), d.get("seeds", ""), d.get("color", "#00ff88"), d.get("icona", "🎵"))
        return None
    except Exception as e:
        log(f"Error obtenint genere intel·ligent: {e}", "error")
        return None

def esborrar_genere_inteligent(nom_genere):
    db = get_db()
    if not db:
        return
    try:
        db.collection("generes_inteligents").document(nom_genere.lower().strip()).delete()
    except Exception as e:
        log(f"Error esborrant genere intel·ligent: {e}", "error")

# ============================================================
# 5. DICCIONARI PREDEFINITS
# ============================================================
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

SEEDS_GENERE = {
    "makina": ["Pont Aeri", "Pastis & Buenri", "Ruboy", "Xavi Metralla", "Javi Boss", "Skudero", "DJ Nau", "Xque", "Sissu", "Chimo Bayo", "Cesar Almena", "M-Project", "DJ Soto"],
    "mákina": ["Pont Aeri", "Pastis & Buenri", "Ruboy", "Xavi Metralla", "Javi Boss", "Skudero", "DJ Nau", "Xque", "Sissu", "Chimo Bayo", "Cesar Almena", "M-Project", "DJ Soto"],
    "hardcore": ["Neophyte", "Korsakoff", "Rotterdam Terror Corps", "DJ Paul", "The Stunned Guys", "Tommyknocker", "Mad Dog", "Noize Suppressor"],
    "techno": ["Adam Beyer", "Charlotte de Witte", "Amelie Lens", "Nina Kraviz", "Carl Cox", "Jeff Mills", "Robert Hood"],
    "house": ["David Guetta", "Calvin Harris", "Swedish House Mafia", "Disclosure", "Duke Dumont", "MK"],
    "trance": ["Armin van Buuren", "Tiësto", "Above & Beyond", "Paul van Dyk", "Ferry Corsten", "Aly & Fila"],
    "drum and bass": ["Andy C", "Noisia", "Pendulum", "High Contrast", "Goldie", "Sub Focus"],
}

LLISTA_NEGRA = ["tuyo", "rimsky-korsakov", "mussorgsky", "modest mussorgsky", "nikolai rimsky-korsakov"]

# ============================================================
# 6. MESOS I ANYS
# ============================================================
MESES = {
    "gener": 1, "febrer": 2, "març": 3, "abril": 4, "maig": 5, "juny": 6,
    "juliol": 7, "agost": 8, "setembre": 9, "octubre": 10, "novembre": 11, "desembre": 12
}

MESES_NOMS = ["Indiferent", "Gener", "Febrer", "Març", "Abril", "Maig", "Juny",
              "Juliol", "Agost", "Setembre", "Octubre", "Novembre", "Desembre"]

ANYS_DISPONIBLES = ["Indiferent"] + [str(a) for a in range(1950, 2027)]

# ============================================================
# 7. PARSEJAR ANY I MES
# ============================================================
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

# ============================================================
# 8. DETECTAR ESTILS DE GENERE
# ============================================================
def detectar_estils_genere(nom_genere):
    nom_lower = nom_genere.lower().strip()
    for clau, info in ESTILS_PREDEFINITS.items():
        if clau in nom_lower or nom_lower in clau:
            return info
    if GROQ_KEY and GROQ_URL:
        try:
            headers = {"Authorization": f"Bearer {GROQ_KEY}", "Content-Type": "application/json"}
            prompt = f"""Ets un expert musical. Per al genere "{nom_genere}", donam:
1. 5 subgeneres/estils relacionats (separats per comes)
2. 10 artistes representatius (separats per comes)
3. Un color hex (#RRGGBB) que representi aquest genere
4. Una icona emoji que el representi

FORMAT OBLIGATORI (una linia per camp):
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
            log(f"Error detectant estils per {nom_genere}: {e}", "error")
    return {"estils": nom_genere, "seeds": "", "color": "#00ff88", "icona": "🎵"}

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
        if guardar_artista_confirmat(artista, genere, subgenere=None, font="usuari", confianza="segur"):
            count += 1
    return count

# ============================================================
# 9. SISTEMA DE LOGS
# ============================================================
def init_console():
    if "console_logs" not in st.session_state:
        st.session_state.console_logs = []
    if "console_html" not in st.session_state:
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
# 10. CREDENCIALS
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
            with open(RUTA_API_SPOTIFY, "r", encoding="utf-8") as f2:
                claus = re.findall(r"[a-f0-9]{32}", f2.read())
            if len(claus) >= 2:
                creds["CLIENT_ID"] = claus[0]
                creds["CLIENT_SECRET"] = claus[1]
        except Exception:
            pass
    if not creds["GROQ_KEY"] and os.path.exists(RUTA_CONFIG_JSON):
        try:
            with open(RUTA_CONFIG_JSON, "r", encoding="utf-8") as f2:
                config = json.load(f2)
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
# 11. MODEL IA
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
            if ids:
                return ids[0]
    except Exception:
        pass
    return "llama-3.3-70b-versatile"

MODEL_IA = obtenir_model_ia() if GROQ_KEY else None

# ============================================================
# 12. DETECTAR TIPUS DE CERCA
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
# 13. IA: TROBAR I VALIDAR ARTISTES
# ============================================================
def trobar_artistes_passada1(estil, any_triat):
    if not GROQ_KEY or not GROQ_URL:
        artistes_db = consultar_artistes_db(estil, min_confianza="probable")
        if artistes_db:
            log(f"IA no disponible. Usant {len(artistes_db)} artistes de la DB", "warning")
            return [(nom, sub) for nom, sub, conf, count in artistes_db]
        return []
    tipus_cerca = detectar_tipus_cerca(any_triat)
    artistes_db = consultar_artistes_db(estil, min_confianza="probable")
    rebutjats_db = consultar_rebutjats_db(estil)
    if artistes_db:
        log(f'DB: Trobats {len(artistes_db)} artistes confirmats de "{estil}"', "success")
    headers = {"Authorization": f"Bearer {GROQ_KEY}", "Content-Type": "application/json"}
    context_db = ""
    if artistes_db:
        context_db = "ARTISTES JA CONEGUTS:\n"
        for nom, sub, conf, count in artistes_db[:15]:
            context_db += f"- {nom} ({sub}) [{conf}]\n"
    if rebutjats_db:
        context_db += "\nREBUTJATS:\n"
        for nom in list(rebutjats_db)[:10]:
            context_db += f"- {nom}\n"
    if tipus_cerca == "novetats":
        instruccions_any = f"L'usuari busca NOVETATS de l'any {any_triat}. Troba artistes actius."
    else:
        instruccions_any = f"L'usuari busca CLASSICS de {any_triat}."
    prompt = f"""Ets un expert musical. Estil: "{estil}"
{context_db}
{instruccions_any}
REGLAS:
1. NOMES noms d'ARTISTES REALS, una per linia.
2. FORMAT: NOM_ARTISTE | GENERE_PRINCIPAL
3. NO frases explicatives.
4. NO numeros de llista.
5. Maxim 25 artistes.
6. Si no coneixes: SENSE_RESULTATS"""
    data = {"model": MODEL_IA, "messages": [{"role": "user", "content": prompt}], "temperature": 0.1, "max_tokens": 1500}
    try:
        log(f"IA: Passada 1 - {tipus_cerca.upper()}...", "info")
        res = requests.post(GROQ_URL, headers=headers, json=data, timeout=20)
        if res.status_code == 200:
            resposta = res.json()["choices"][0]["message"]["content"].strip()
            if "SENSE_RESULTATS" in resposta or len(resposta) < 10:
                if artistes_db:
                    return [(nom, sub) for nom, sub, conf, count in artistes_db]
                seeds = obtenir_seeds_genere(estil)
                if seeds:
                    return [(s, "seed") for s in seeds]
                return []
            artistes = []
            for linia in resposta.splitlines():
                linia = linia.strip()
                if not linia or len(linia) > 60 or linia.startswith("-") or linia.startswith("*"):
                    continue
                if "|" in linia:
                    parts = linia.split("|")
                    if len(parts) >= 2:
                        nom = parts[0].strip()
                        genere = parts[1].strip()
                        if nom and 2 < len(nom) < 50 and nom not in rebutjats_db:
                            artistes.append((nom, genere))
                else:
                    nom = linia.strip().strip(",").strip("-").strip(".")
                    if nom and 2 < len(nom) < 40 and " " not in nom and nom not in rebutjats_db:
                        artistes.append((nom, "desconegut"))
            if artistes:
                log(f"IA: {len(artistes)} artistes trobats", "success")
                noms_nous = {a[0].lower() for a in artistes}
                for nom, sub, conf, count in artistes_db:
                    if nom.lower() not in noms_nous:
                        artistes.insert(0, (nom, sub))
                return artistes
            if artistes_db:
                return [(nom, sub) for nom, sub, conf, count in artistes_db]
            seeds = obtenir_seeds_genere(estil)
            if seeds:
                return [(s, "seed") for s in seeds]
            return []
        return []
    except Exception as e:
        log(f"Error IA passada 1: {e}", "error")
        if artistes_db:
            return [(nom, sub) for nom, sub, conf, count in artistes_db]
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
    context_any = "novetats" if tipus_cerca == "novetats" else f"classics {any_triat}"
    prompt = f"""Revisa artistes per "{estil}" ({context_any}).
LLISTA:
{llista_text}
REGLAS:
1. Descarta els que NO toquin l'estil.
2. FORMAT: NOM_ARTISTE | GENERE | CONFIANCA
3. CONFIANCA: segur o probable
4. NO frases.
5. Si tots valids: respon amb tots. Si cap: CAP_VALID"""
    data = {"model": MODEL_IA, "messages": [{"role": "user", "content": prompt}], "temperature": 0.1, "max_tokens": 1500}
    try:
        log("IA: Validant artistes...", "info")
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
                else:
                    nom = linia.strip().strip(",").strip("-")
                    if nom and 2 < len(nom) < 40 and " " not in nom:
                        artistes_validats.append((nom, "desconegut", "probable"))
            if artistes_validats:
                segurs = sum(1 for _, _, c in artistes_validats if c == "segur")
                log(f"IA: {len(artistes_validats)} validats ({segurs} segurs)", "success")
                return artistes_validats
            return [(nom, gen, "probable") for nom, gen in artistes]
        return [(nom, gen, "probable") for nom, gen in artistes]
    except Exception as e:
        log(f"Error IA validacio: {e}", "error")
        return [(nom, gen, "probable") for nom, gen in artistes]

# ============================================================
# 14. VALIDACIO DE SEGURETAT
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
# 15. CERCA SPOTIFY AMB POPULARITAT, BPM, KEY
# ============================================================
def obtenir_audio_features(sp, track_ids):
    features = {}
    if not track_ids:
        return features
    for i in range(0, len(track_ids), 100):
        batch = track_ids[i:i+100]
        try:
            result = sp.audio_features(batch)
            for f in result:
                if f:
                    features[f["id"]] = {
                        "bpm": round(f["tempo"], 1) if f["tempo"] else None,
                        "key": f["key"], "mode": f["mode"],
                        "energy": f["energy"], "danceability": f["danceability"],
                        "duration_ms": f["duration_ms"]
                    }
        except Exception as e:
            log(f"Error audio features: {e}", "debug")
        time.sleep(0.1)
    return features

def key_to_string(key_num, mode_num):
    keys = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
    if key_num is None or key_num < 0 or key_num > 11:
        return "N/D"
    key_str = keys[key_num]
    if mode_num == 0:
        key_str += "m"
    return key_str

# ============================================================
# 16. FUNCIONS DE CERCA
# ============================================================
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
                any_ll = int(track.get("album", {}).get("release_date", "").split("-")[0])
                if any_min <= any_ll <= any_max:
                    if mes_min is not None and mes_max is not None:
                        try:
                            mes_ll = int(track.get("album", {}).get("release_date", "").split("-")[1])
                            if not (mes_min <= mes_ll <= mes_max):
                                continue
                        except:
                            pass
                    track_id = track["id"]
                    track_ids.append(track_id)
                    cancons_temp.append({
                        "artista": track["artists"][0]["name"], "titol": track["name"],
                        "bpm": "N/D", "clau": "N/D", "any": any_ll,
                        "popularitat": track.get("popularity", 0),
                        "durada_ms": track.get("duration_ms", 0),
                        "spotify_uri": track["uri"],
                        "spotify_link": track["external_urls"]["spotify"],
                        "spotify_id": track_id, "font": "Spotify"
                    })
            except:
                pass
        if not cancons_temp:
            resultats2 = sp.search(q=f'artist:"{artista_nom}"', type="track", limit=50)
            for track in resultats2.get("tracks", {}).get("items", []):
                try:
                    any_ll = int(track.get("album", {}).get("release_date", "").split("-")[0])
                    if any_min <= any_ll <= any_max:
                        track_id = track["id"]
                        track_ids.append(track_id)
                        cancons_temp.append({
                            "artista": track["artists"][0]["name"], "titol": track["name"],
                            "bpm": "N/D", "clau": "N/D", "any": any_ll,
                            "popularitat": track.get("popularity", 0),
                            "durada_ms": track.get("duration_ms", 0),
                            "spotify_uri": track["uri"],
                            "spotify_link": track["external_urls"]["spotify"],
                            "spotify_id": track_id, "font": "Spotify"
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
        except Exception as e:
            log(f"Error Discogs {artista_nom}: {e}", "debug")
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
    except Exception as e:
        log(f"Error MusicBrainz {artista_nom}: {e}", "debug")
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
                    any_ll = int(track.get("album", {}).get("release_date", "").split("-")[0])
                    if any_min <= any_ll <= any_max:
                        canco = {
                            "artista": track["artist"]["name"], "titol": track["title"],
                            "bpm": "N/D", "clau": "N/D", "any": any_ll,
                            "popularitat": track.get("rank", "N/D"),
                            "durada_ms": track.get("duration", 0) * 1000,
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
# 17. UTILITATS AVANÇADES
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
        else:
            log(f"Limit: {canco['artista']} - {canco['titol']}", "debug")
    log(f"Limit aplicat: {len(cancons)} -> {len(resultat)}", "info")
    return resultat

def ordenar_cancons_intelligent(cancons, criteri="popularitat"):
    if criteri == "popularitat":
        return sorted(cancons, key=lambda x: x.get("popularitat", 0) if isinstance(x.get("popularitat"), (int, float)) else 0, reverse=True)
    elif criteri == "bpm":
        return sorted(cancons, key=lambda x: x.get("bpm", 0) if isinstance(x.get("bpm"), (int, float)) else 999)
    elif criteri == "any":
        return sorted(cancons, key=lambda x: x.get("any", 0), reverse=True)
    elif criteri == "aleatori":
        random.shuffle(cancons)
        return cancons
    return cancons

def verificar_uris(sp, cancons):
    log(f"Verificant {len(cancons)} cancons...", "info")
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
        except Exception as e:
            log(f"Error verificant {c['artista']}: {e}", "error")
        time.sleep(0.1)
    return verificades

# ============================================================
# 18. SESSION STATE
# ============================================================
if "cancons_reals" not in st.session_state:
    st.session_state.cancons_reals = []
if "uris_spotify" not in st.session_state:
    st.session_state.uris_spotify = []
if "text_copiar" not in st.session_state:
    st.session_state.text_copiar = ""
if "titol_playlist" not in st.session_state:
    st.session_state.titol_playlist = "Nova Playlist"
if "input_estil" not in st.session_state:
    st.session_state.input_estil = "Makina"
if "genere_aprendre_seleccionat" not in st.session_state:
    st.session_state.genere_aprendre_seleccionat = "Makina"
if "ta_artistes_aprendre" not in st.session_state:
    st.session_state["ta_artistes_aprendre"] = ""
if "artistes_processats_feedback" not in st.session_state:
    st.session_state.artistes_processats_feedback = set()
if "feedback_timestamp" not in st.session_state:
    st.session_state.feedback_timestamp = 0
if "artistes_ultima_cerca" not in st.session_state:
    st.session_state.artistes_ultima_cerca = []
if "aprendre_key_counter" not in st.session_state:
    st.session_state.aprendre_key_counter = 0

# ============================================================
# 19. INTERFICIE PRINCIPAL
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

        # Inicialitzar Firebase i mostrar estat
        db_status = init_firebase()
        if db_status:
            log("Firebase: DB operativa", "success")
        else:
            log(f"Firebase: {firebase_error_msg()}", "error")

        # ===== CAPÇALERA =====
        st.markdown("""
        <div style="display: flex; align-items: center; gap: 15px; margin-bottom: 20px; padding: 15px; background: linear-gradient(90deg, #1a1a2e 0%, #16213e 100%); border-radius: 10px; border: 1px solid #333;">
            <div style="font-size: 32px;">🎛️</div>
            <div>
                <div style="font-size: 24px; font-weight: bold; color: #00ff88;">Rastrejador de Novetats Reals</div>
                <div style="font-size: 14px; color: #888;">Spotify: <span style="color: #1DB954;">●</span> {usuari} | IA: {model} | Discogs: {discogs} | DB: {db}</div>
            </div>
            <div style="margin-left: auto; background: #0a0a0a; padding: 5px 15px; border-radius: 20px; border: 1px solid #333;">
                <span style="color: #00ff88; font-weight: bold; font-size: 12px;">📦 v2.0.0-Firebase</span>
            </div>
        </div>
        """.format(
            usuari=usuari_sp["display_name"],
            model=MODEL_IA or "No disponible",
            discogs="Actiu" if DISCOGS_TOKEN else "Sense token",
            db="Firebase ✅" if firebase_ok() else f"Firebase ❌ ({firebase_error_msg()})"
        ), unsafe_allow_html=True)

        # Alerta si Firebase no connecta
        if not firebase_ok():
            st.error(f"⚠️ Firebase no connectat: {firebase_error_msg()}")
            st.info("Configura les credencials a Streamlit Cloud Secrets (secció [firebase]) o puja el fitxer JSON al repositori.")

        tab_cercar, tab_aprendre = st.tabs(["🔍 Cercar Cançons", "🎓 Aprendre"])

        # ========================================================
        # PESTANYA 1: CERCAR CANÇONS
        # ========================================================
        with tab_cercar:
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
                        estil_triat = st.text_input("Estil / Genere:", value=st.session_state.input_estil, key="input_estil_cercar")
                    with col_estil2:
                        genere_cercar_sel = st.selectbox("Guardats:", ["-- Manual --"] + generes_guardats_cercar, key="sel_genere_cercar")
                        if genere_cercar_sel != "-- Manual --":
                            st.session_state.input_estil = genere_cercar_sel
                            estil_triat = genere_cercar_sel
                else:
                    estil_triat = st.text_input("Estil / Genere:", value=st.session_state.input_estil, key="input_estil_cercar_fallback")

                col_mes, col_any = st.columns(2)
                with col_mes:
                    mes_triat = st.selectbox("Mes:", MESES_NOMS, index=0, key="sel_mes_cercar")
                with col_any:
                    any_triat = st.selectbox("Any:", ANYS_DISPONIBLES, index=len(ANYS_DISPONIBLES)-2, key="sel_any_cercar")
                    any_manual = st.text_input("O rang (Ex: 2025/2026):", "", key="input_any_manual_cercar", help="Deixa en blanc per usar el selector d'any")
                    if any_manual.strip():
                        any_triat = any_manual.strip()

                tipus_detectat = detectar_tipus_cerca(any_triat, mes_triat)
                if tipus_detectat == "novetats":
                    st.info("🔴 Mode NOVETATS: Buscant llançaments recents")
                else:
                    st.info("🟢 Mode CLASSICS: Buscant temes classics/top")

                tipus_ref = st.radio("Referencia:", ["Canco", "Artista"], horizontal=True, key="radio_tipus_cercar")

                if "Canco" in tipus_ref:
                    llavor = st.text_input("Canco de referencia:", placeholder="Ex: Pont Aeri - Flying Free", key="input_llavor_cercar")
                else:
                    llavor = st.text_input("Artista de referencia:", placeholder="Ex: Pont Aeri", key="input_llavor_cercar_fallback")

                quantitat = st.number_input("Cancons a trobar:", min_value=10, max_value=200, value=100, step=10, key="input_quantitat_cercar")

                st.markdown("""
                <div style="background: #1a1a2e; padding: 8px 12px; border-radius: 6px; margin: 15px 0 10px 0; border-left: 3px solid #3b82f6;">
                    <span style="color: #3b82f6; font-weight: bold; font-size: 13px;">⚙️ Opcions Avançades</span>
                </div>
                """, unsafe_allow_html=True)

                col_opt1, col_opt2 = st.columns(2)
                with col_opt1:
                    max_per_artista = st.number_input("Max per artista:", min_value=1, max_value=10, value=3, step=1, key="input_max_artista_cercar")
                with col_opt2:
                    ordenacio = st.selectbox("Ordenar per:", ["popularitat", "bpm", "any", "aleatori"], index=0, key="sel_ordenacio_cercar")
                    min_conf = st.selectbox("Min confiança DB:", ["segur", "probable", "dubtos"], index=1, key="sel_conf_cercar")

                col_rastreig, col_refrescar = st.columns(2)
                with col_rastreig:
                    btn_rastreig = st.button("🔍 Comencar Rastreig", key="btn_rastreig", use_container_width=True)
                with col_refrescar:
                    if st.button("🔄 Refrescar Artistes DB", key="btn_refrescar_db", use_container_width=True):
                        artistes_db = consultar_artistes_db(estil_triat, min_confianza=min_conf)
                        if artistes_db:
                            st.session_state.artistes_ultima_cerca = [(nom, sub, conf) for nom, sub, conf, count in artistes_db]
                            log(f"Refrescat: {len(artistes_db)} artistes de la DB per '{estil_triat}'", "success")
                            st.success(f"🔄 {len(artistes_db)} artistes carregats!")
                        else:
                            st.warning(f"No hi ha artistes a la DB per '{estil_triat}'.")
                            st.session_state.artistes_ultima_cerca = []
                        st.rerun()

                st.markdown("<div style='margin-top: 15px;'></div>", unsafe_allow_html=True)
                render_console()
                if st.button("Netejar Consola", key="btn_netejar_cercar"):
                    clear_console()
                    st.rerun()

                if btn_rastreig:
                    log(f"Rastreig: {estil_triat} | {any_triat} | {quantitat} cancons", "info")
                    if any_triat == "Indiferent":
                        any_min_r, any_max_r, mes_min_r, mes_max_r = parsejar_any_mes("Indiferent", mes_triat)
                    else:
                        any_min_r, any_max_r, mes_min_r, mes_max_r = parsejar_any_mes(any_triat, mes_triat)
                    tipus_cerca = detectar_tipus_cerca(any_triat, mes_triat)
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
                            st.error("La IA no ha pogut validar els artistes.")
                        else:
                            artistes_text = "\n".join([f"{a} ({g}) [{c}]" for a, g, c in artistes_validats])
                            st.info(f"IA Passada 2: {len(artistes_validats)} validats:\n\n{artistes_text}")
                            st.session_state.artistes_ultima_cerca = artistes_validats
                            st.session_state.artistes_processats_feedback = set()
                            st.session_state.feedback_timestamp = time.time()
                            totes_cancons = []
                            for artista_nom, artista_genere, confianza in artistes_validats:
                                if not validar_artista_seguretat(artista_nom):
                                    log(f"Artista descartat (llista negra): {artista_nom}", "warning")
                                    continue
                                log(f"Cercant: {artista_nom}...", "info")
                                cancons_spotify = cercar_spotify(sp, artista_nom, any_min_r, any_max_r, mes_min_r, mes_max_r, limit=10, tipus_cerca=tipus_cerca)
                                cancons_discogs = cercar_discogs(artista_nom, any_min_r, any_max_r, mes_min_r, mes_max_r, limit=10, tipus_cerca=tipus_cerca)
                                cancons_mb = cercar_musicbrainz(artista_nom, any_min_r, any_max_r, mes_min_r, mes_max_r, limit=10, tipus_cerca=tipus_cerca)
                                cancons_deezer = cercar_deezer(artista_nom, any_min_r, any_max_r, mes_min_r, mes_max_r, limit=10, tipus_cerca=tipus_cerca)
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
                            cancons_limitades = limitar_cancons_per_artista(cancons_uniques, max_per_artista)
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

            with col_dreta:
                if st.session_state.artistes_ultima_cerca:
                    st.markdown("""
                    <div style="background: #1a1a2e; padding: 10px 15px; border-radius: 8px; margin-bottom: 15px; border-left: 3px solid #f59e0b;">
                        <span style="color: #f59e0b; font-weight: bold; font-size: 16px;">🧠 Feedback Artistes</span>
                    </div>
                    """, unsafe_allow_html=True)
                    artistes_pendents = []
                    for a, g, c in st.session_state.artistes_ultima_cerca:
                        if a in st.session_state.artistes_processats_feedback:
                            continue
                        db_fb = get_db()
                        if db_fb:
                            doc_reb = db_fb.collection("artistes_rebutjats").document(f"{a.lower().strip()}_{estil_triat.lower().strip()}").get()
                            if doc_reb.exists:
                                st.session_state.artistes_processats_feedback.add(a)
                                continue
                            doc_conf = db_fb.collection("artistes_confirmats").document(f"{a.lower().strip()}_{estil_triat.lower().strip()}").get()
                            if doc_conf.exists and doc_conf.to_dict().get("confianza") == "segur":
                                st.session_state.artistes_processats_feedback.add(a)
                                continue
                        artistes_pendents.append((a, g, c))
                    if not artistes_pendents:
                        st.success("✅ Tots els artistes ja han estat validats!")
                    else:
                        for i, (artista, genere, conf) in enumerate(artistes_pendents):
                            cols = st.columns([3, 1, 1])
                            with cols[0]:
                                st.write(f"**{artista}** ({genere}) [{conf}]")
                            with cols[1]:
                                if st.button(f"✅ Si", key=f"btn_si_{i}_{st.session_state.feedback_timestamp}"):
                                    guardar_artista_confirmat(artista, estil_triat, genere, "usuari", "segur")
                                    st.session_state.artistes_processats_feedback.add(artista)
                                    log(f"DB: {artista} marcat com a SEGUR", "success")
                                    st.rerun()
                            with cols[2]:
                                if st.button(f"❌ No", key=f"btn_no_{i}_{st.session_state.feedback_timestamp}"):
                                    guardar_artista_rebutjat(artista, estil_triat, "No es del genere (usuari)")
                                    st.session_state.artistes_processats_feedback.add(artista)
                                    log(f"DB: {artista} marcat com a REBUTJAT", "warning")
                                    st.rerun()

                st.divider()

                if st.session_state.cancons_reals:
                    st.markdown(f"""
                    <div style="background: #1a1a2e; padding: 10px 15px; border-radius: 8px; margin-bottom: 15px; border-left: 3px solid #3b82f6;">
                        <span style="color: #3b82f6; font-weight: bold; font-size: 16px;">📊 Resultats</span>
                        <span style="color: #888; font-size: 14px; margin-left: 10px;">{len(st.session_state.cancons_reals)} cançons trobades</span>
                    </div>
                    """, unsafe_allow_html=True)
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
                    st.markdown("""
                    <div style="background: #1a1a2e; padding: 10px 15px; border-radius: 8px; margin: 20px 0 15px 0; border-left: 3px solid #1DB954;">
                        <span style="color: #1DB954; font-weight: bold; font-size: 16px;">🎵 Crear Playlist a Spotify</span>
                    </div>
                    """, unsafe_allow_html=True)
                    nom_llista = st.text_input("Nom de la playlist:", value=st.session_state.titol_playlist, key="input_nom_playlist")
                    col1, col2 = st.columns(2)
                    with col1:
                        if st.session_state.uris_spotify:
                            if st.button("Crear Playlist", key="btn_crear", use_container_width=True):
                                try:
                                    log(f"Creant '{nom_llista}'...", "info")
                                    pl = sp.user_playlist_create(user=usuari_sp["id"], name=nom_llista, public=True)
                                    for i in range(0, len(st.session_state.uris_spotify), 100):
                                        sp.playlist_add_items(playlist_id=pl["id"], items=st.session_state.uris_spotify[i:i+100])
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
                            csv = df.to_csv(index=False, encoding="utf-8-sig")
                            st.download_button(label="Descarregar CSV", data=csv, file_name=f"{st.session_state.titol_playlist}.csv", mime="text/csv", key="btn_download")
                            log("CSV exportat", "success")

        # ========================================================
        # PESTANYA 2: APRENDRE
        # ========================================================
        with tab_aprendre:
            st.header("🎓 Ensenyar Artistes al Programa")
            st.write("Introdueix una llista d'artistes d'un estil concret. El programa els guardarà a Firebase.")

            # Estat de Firebase visible
            if firebase_ok():
                st.success("✅ Firebase connectat")
            else:
                st.error(f"❌ Firebase no connectat: {firebase_error_msg()}")

            col_a1, col_a2 = st.columns([2, 1])

            with col_a1:
                tots_generes = obtenir_tots_generes_db()

                col_gen1, col_gen2 = st.columns([2, 1])
                with col_gen1:
                    genere_aprendre = st.text_input("Genere / Estil:", value=st.session_state.genere_aprendre_seleccionat, key="input_genere_aprendre")
                with col_gen2:
                    if tots_generes:
                        genere_seleccionat = st.selectbox("Guardats:", ["-- Nou --"] + tots_generes, key="sel_genere_guardat_aprendre")
                        if genere_seleccionat != "-- Nou --":
                            st.session_state.genere_aprendre_seleccionat = genere_seleccionat
                            artistes_del_genere = obtenir_artistes_per_genere(genere_seleccionat)
                            nou_text = "\n".join([a[0] for a in artistes_del_genere]) if artistes_del_genere else ""
                            if st.session_state.get("ta_artistes_aprendre", "") != nou_text:
                                st.session_state["ta_artistes_aprendre"] = nou_text
                                st.session_state.aprendre_key_counter = st.session_state.get("aprendre_key_counter", 0) + 1
                                st.rerun()
                    else:
                        st.caption("Sense generes")

                if tots_generes:
                    st.caption(f"📚 Generes a Firebase: {', '.join(tots_generes)}")

                ta_key = f"ta_artistes_aprendre_{st.session_state.get('aprendre_key_counter', 0)}"
                artistes_text = st.text_area(
                    "Llista d'artistes (un per linia):",
                    value=st.session_state.get("ta_artistes_aprendre", ""),
                    height=300,
                    key=ta_key
                )
                st.session_state["ta_artistes_aprendre"] = artistes_text

                if st.button("🗑️ Buidar Camp", key="btn_buidar_camp", use_container_width=True):
                    st.session_state["ta_artistes_aprendre"] = ""
                    st.session_state.aprendre_key_counter = st.session_state.get("aprendre_key_counter", 0) + 1
                    st.rerun()

                col_btn1, col_btn2, col_btn3 = st.columns(3)

                with col_btn1:
                    if st.button("💾 Guardar a Firebase", key="btn_guardar_aprendre", use_container_width=True):
                        if not firebase_ok():
                            st.error(f"Firebase no disponible: {firebase_error_msg()}")
                        elif artistes_text.strip() and genere_aprendre.strip():
                            artistes_parsed = parsejar_llista_artistes(artistes_text)
                            if artistes_parsed:
                                count = guardar_llista_artistes_confirmats(artistes_parsed, genere_aprendre)
                                info_genere = detectar_estils_genere(genere_aprendre)
                                seeds_text = ", ".join(artistes_parsed[:15]) if artistes_parsed else info_genere["seeds"]
                                guardar_genere_inteligent(
                                    genere_aprendre,
                                    estils=info_genere["estils"],
                                    seeds=seeds_text,
                                    color=info_genere["color"],
                                    icona=info_genere["icona"]
                                )
                                log(f"Guardats {count} artistes a Firebase com a '{genere_aprendre}'", "success")
                                st.success(f"✅ {count} artistes guardats a Firebase com a '{genere_aprendre}'!")
                                st.session_state.genere_aprendre_seleccionat = genere_aprendre
                                st.balloons()
                            else:
                                st.warning("No s'han trobat noms d'artistes al text.")
                        else:
                            st.warning("Introdueix un genere i artistes abans de guardar.")

                with col_btn2:
                    if st.button("📋 Veure Artistes Guardats", key="btn_veure_aprendre", use_container_width=True):
                        if not firebase_ok():
                            st.error("Firebase no connectat")
                        else:
                            artistes_db = consultar_artistes_db(genere_aprendre, min_confianza="probable")
                            if artistes_db:
                                st.info(f"**Artistes a Firebase per '{genere_aprendre}':**\n\n" + "\n".join([f"• {a} ({g}) [{c}]" for a, g, c, count in artistes_db]))
                            else:
                                st.info(f"No hi ha artistes a Firebase per '{genere_aprendre}' encara.")
                            tots_g = obtenir_tots_generes_db()
                            if tots_g:
                                st.markdown("**📚 Tots els generes guardats:**")
                                for g in tots_g:
                                    count = len(obtenir_artistes_per_genere(g))
                                    st.write(f"• **{g}**: {count} artistes")

                with col_btn3:
                    if st.button("🗑️ Esborrar Genere", key="btn_esborrar_aprendre", use_container_width=True):
                        if not firebase_ok():
                            st.error("Firebase no connectat")
                        else:
                            esborrar_genere(genere_aprendre)
                            log(f"Genere '{genere_aprendre}' esborrat de Firebase", "warning")
                            st.warning(f"🗑️ Genere '{genere_aprendre}' esborrat de Firebase.")

            with col_a2:
                st.subheader("📊 Estadistiques")
                stats = obtenir_estadistiques_db()
                st.metric("Artistes Confirmats", stats["artistes_confirmats"])
                st.metric("Artistes Rebutjats", stats["artistes_rebutjats"])
                st.metric("Cançons Confirmades", stats["cancons_confirmades"])
                st.metric("Generes Apresos", stats["generes_apresos"])
                if stats["top_generes"]:
                    st.subheader("Top Generes")
                    for gen, nart, ncan in stats["top_generes"]:
                        st.write(f"• **{gen}**: {nart} artistes, {ncan} cancons")

    except Exception as e:
        log(f"Error de sistema: {e}", "error")
        st.error(f"Error de sistema: {e}")
        st.code(traceback.format_exc())
else:
    log("Falten credencials Spotify", "error")
    st.error("Falten credencials de Spotify.")
    st.info("Configura SPOTIFY_CLIENT_ID i SPOTIFY_CLIENT_SECRET als secrets de Streamlit Cloud.")
