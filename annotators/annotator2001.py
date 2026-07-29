import streamlit as st
import streamlit.components.v1 as components
import os
import json
import copy
from PIL import Image

IMAGE_DIR   = "images"
JSON_DIR    = "../Gemma_output"
OUTPUT_DIR  = "jsons_corriges"
# Dossier contenant les JSON (meme nom que les fichiers images/JSON source)
# avec les annotations humaines erronees, a titre de comparaison visuelle.
HUMAN_ERR_DIR = "../data\groundtruth_numaclay\separated_groundtruth_titlepages_numaclay"

os.makedirs(OUTPUT_DIR, exist_ok=True)

st.set_page_config(layout="wide", page_title="Annotateur")

# ── Scroll to top (called at render time when flag is set) ─────────────────────
if st.session_state.get("_scroll_top"):
    components.html(
        "<script>window.parent.document.querySelector('section.main').scrollTo({top:0,behavior:'instant'});</script>",
        height=0,
    )
    st.session_state._scroll_top = False

st.markdown("""
<style>
.prog-wrap { background: #1e2130; border-radius: 99px; height: 6px; margin-bottom: 4px; }
.prog-bar  { background: #4f8ef7; height: 6px; border-radius: 99px; transition: width .3s; }
.prog-label { font-size: 12px; color: #64748b; text-align: right; margin-bottom: 16px; }

.field-block {
    border: 1px solid #1e2130;
    border-radius: 8px;
    padding: 10px 14px 6px 14px;
    margin-bottom: 8px;
    background: #0f1117;
}
.field-block.corrected { border-color: #f59e0b; }
.field-path  { font-size: 11px; color: #64748b; font-family: monospace; margin-bottom: 3px; }
.field-value { font-size: 13px; color: #cbd5e1; font-style: italic; margin-bottom: 6px; }
.field-value.empty { color: #374151; }
.corr-label  { font-size: 11px; color: #f59e0b; margin: 6px 0 2px 0; }

div[data-testid="stHorizontalBlock"] .stRadio > div { flex-direction: row !important; gap: 6px; }
.stRadio label { font-size: 12px !important; padding: 3px 10px !important;
                 border: 1px solid #2e3347 !important; border-radius: 6px !important; }
.stRadio label:hover { border-color: #4f8ef7 !important; }

input[type="text"] {
    font-size: 13px !important;
    background: #0a0d14 !important;
    border: 1px solid #2e3347 !important;
    border-radius: 6px !important;
    color: #fde68a !important;
    padding: 4px 8px !important;
}
.stButton > button {
    background: #1d4ed8 !important;
    border: none !important; border-radius: 8px !important;
    color: #fff !important; font-weight: 600 !important; padding: 10px 0 !important;
}
.stButton > button:hover { background: #1e40af !important; }
.stButton > button:disabled { background: #1e2130 !important; color: #374151 !important; }

h3 { font-size: 14px !important; font-weight: 600; color: #94a3b8;
     margin: 18px 0 8px 0; letter-spacing: .04em; text-transform: uppercase; }
</style>
""", unsafe_allow_html=True)

# ── Helpers ────────────────────────────────────────────────────────────────────

SKIP_KEYS = {"image_filename", "processing_time_seconds"}

def extract_leaf_paths(obj, prefix=""):
    paths = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in SKIP_KEYS:
                continue
            child = f"{prefix}.{k}" if prefix else k
            paths.extend(extract_leaf_paths(v, child))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            child = f"{prefix}.{i}" if prefix else str(i)
            paths.extend(extract_leaf_paths(v, child))
    else:
        paths.append((prefix, obj))
    return paths


def set_by_path(obj, path, value):
    keys = path.split(".")
    cur = obj
    for k in keys[:-1]:
        cur = cur[int(k)] if isinstance(cur, list) else cur[k]
    last = keys[-1]
    if isinstance(cur, list):
        cur[int(last)] = value
    else:
        cur[last] = value


def navigate(delta):
    """Change image index, clear widget state for next render, request scroll."""
    st.session_state.current_index += delta
    st.session_state._scroll_top = True
    # Drop all widget keys belonging to the current image so they reset
    to_delete = [k for k in st.session_state if k.startswith("w_")]
    for k in to_delete:
        del st.session_state[k]


CAUSES = {
    "absent":    "Champ absent",
    "qualite":   "Qualite d'image",
    "recouvert": "Champ recouvert",
    "manuscrit": "Ecriture manuscrite"
}

# ── Data ───────────────────────────────────────────────────────────────────────
images = sorted([f for f in os.listdir(IMAGE_DIR)
                 if f.lower().endswith(('.png', '.jpg', '.jpeg'))])

if not images:
    st.error("Aucune image trouvee dans le dossier `images/`.")
    st.stop()

if "current_index" not in st.session_state:
    start = len(images)
    for i, img_name in enumerate(images):
        base = os.path.splitext(img_name)[0]
        if not os.path.exists(os.path.join(OUTPUT_DIR, f"{base}.json")):
            start = i
            break
    st.session_state.current_index = start

if st.session_state.current_index >= len(images):
    st.success("Toutes les images ont ete annotees.")
    st.stop()

idx   = st.session_state.current_index
total = len(images)
pct   = int(idx / total * 100)

# ── Load JSON ──────────────────────────────────────────────────────────────────
current_img_name = images[idx]
base_name = os.path.splitext(current_img_name)[0]
json_name = f"{base_name}.json"
out_path  = os.path.join(OUTPUT_DIR, json_name)

src_path = out_path if os.path.exists(out_path) else os.path.join(JSON_DIR, json_name)
if os.path.exists(src_path):
    with open(src_path, "r", encoding="utf-8") as f:
        try:
            src_data = json.load(f)
        except Exception:
            src_data = {}
    prior_annotations = src_data.pop("_annotations", {})
else:
    src_data = {}
    prior_annotations = {}
    st.warning(f"Aucun JSON source pour `{current_img_name}`.")

leaf_paths = [(p, v) for p, v in extract_leaf_paths(src_data) if p != "langue"]
leaf_paths = extract_leaf_paths(src_data)

# ── Load human (erroneous) annotation JSON, same filename ──────────────────────
human_err_path = os.path.join(HUMAN_ERR_DIR, json_name)
human_err_raw  = None
human_err_data = None
if os.path.exists(human_err_path):
    with open(human_err_path, "r", encoding="utf-8") as f:
        human_err_raw = f.read()
    try:
        human_err_data = json.loads(human_err_raw)
    except Exception:
        human_err_data = None

# On ajoute "langue" comme champ a annoter, avec sa valeur initiale
# recuperee directement dans le JSON humain (colonne de droite).
langue_value = ""
if isinstance(human_err_data, dict):
    metadata_block = human_err_data.get("metadata", {})
    if isinstance(metadata_block, dict):
        langue_value = metadata_block.get("language", "")
leaf_paths = leaf_paths + [("langue", langue_value)]

# ── Header ─────────────────────────────────────────────────────────────────────
st.markdown(f"""
<div class='prog-wrap'><div class='prog-bar' style='width:{pct}%'></div></div>
<div class='prog-label'>{idx} / {total}</div>
""", unsafe_allow_html=True)
st.markdown(f"**{current_img_name}**")

col_img, col_right, col_human = st.columns([1, 1, 1], gap="large")

# ── Image + navigation ─────────────────────────────────────────────────────────
with col_img:
    img_path = os.path.join(IMAGE_DIR, current_img_name)
    if os.path.exists(img_path):
        st.image(Image.open(img_path), use_container_width=True)
    else:
        st.warning("Image introuvable.")

    nav_l, nav_r = st.columns(2)
    with nav_l:
        if st.button("Precedent", use_container_width=True, disabled=(idx == 0)):
            navigate(-1)
            st.rerun()
    with nav_r:
        if st.button("Passer", use_container_width=True):
            navigate(+1)
            st.rerun()

# ── Annotation panel ──────────────────────────────────────────────────────────
with col_right:
    annotations = {}
    corrections = {}

    st.markdown("### Champs")

    with st.container(height=700, border=False):
        for path, value in leaf_paths:
            prior = prior_annotations.get(path, {})

            raw_val      = str(value).strip() if value not in (None, "", [], {}) else ""
            val_class    = "" if raw_val else "empty"
            val_text     = raw_val if raw_val else "(vide)"
            prior_corr   = prior.get("correction", None)
            was_corrected = prior_corr is not None
            block_class  = "field-block corrected" if was_corrected else "field-block"

            st.markdown(f"""
            <div class='{block_class}'>
                <div class='field-path'>{path}</div>
                <div class='field-value {val_class}'>{val_text}</div>
            </div>
            """, unsafe_allow_html=True)

            col_read, col_cause, col_edit = st.columns([2, 3, 1])

            # Keys prefixed with "w_{idx}_" so they are fresh for every new image
            with col_read:
                read_default = prior.get("lisibilite", "Lisible")
                read_val = st.radio(
                    label="",
                    options=["Lisible", "Non lisible"],
                    index=0 if read_default == "Lisible" else 1,
                    horizontal=True,
                    label_visibility="collapsed",
                    key=f"w_{idx}_read_{path}",
                )

            cause_val = None
            with col_cause:
                if read_val == "Non lisible":
                    cause_keys  = list(CAUSES.keys())
                    prior_cause = prior.get("cause", cause_keys[0])
                    def_idx     = cause_keys.index(prior_cause) if prior_cause in cause_keys else 0
                    cause_val   = st.radio(
                        label="",
                        options=cause_keys,
                        format_func=lambda k: CAUSES[k],
                        index=def_idx,
                        horizontal=True,
                        label_visibility="collapsed",
                        key=f"w_{idx}_cause_{path}",
                    )

            with col_edit:
                show_corr = st.checkbox(
                    "Corriger",
                    value=was_corrected,
                    key=f"w_{idx}_showcorr_{path}",
                )

            if show_corr:
                st.markdown("<div class='corr-label'>Valeur corrigee</div>", unsafe_allow_html=True)
                corrected_val = st.text_input(
                    label="",
                    value=prior_corr if prior_corr is not None else raw_val,
                    label_visibility="collapsed",
                    key=f"w_{idx}_corr_{path}",
                )
                corrections[path] = corrected_val

            ann = {"lisibilite": read_val}
            if cause_val:
                ann["cause"] = cause_val
            if path in corrections:
                ann["correction"] = corrections[path]
            annotations[path] = ann

            st.markdown("<hr style='border-color:#1e2130;margin:6px 0'>", unsafe_allow_html=True)

    # Global note
    st.markdown("### Note generale")
    global_note = st.text_input(
        label="",
        value=prior_annotations.get("_note", ""),
        placeholder="Remarque globale sur cette image...",
        label_visibility="collapsed",
        key=f"w_{idx}_global_note",
    )

    # Save
    st.markdown("<br>", unsafe_allow_html=True)
    if st.button("Sauvegarder et continuer", use_container_width=True):
        output_data = copy.deepcopy(src_data)

        for path, corr_val in corrections.items():
            try:
                set_by_path(output_data, path, corr_val)
            except Exception:
                pass

        # "langue" n'est ecrite que si le champ n'existe pas deja dans la destination.
        if "langue" not in output_data:
            output_data["langue"] = corrections.get("langue", langue_value)
        elif "langue" in corrections:
            output_data["langue"] = corrections["langue"]

        output_data["_annotations"] = annotations
        if global_note.strip():
            output_data["_annotations"]["_note"] = global_note.strip()

        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(output_data, f, indent=4, ensure_ascii=False)

        navigate(+1)
        st.rerun()

# ── Panneau de droite : annotations humaines erronees (lecture seule) ──────────
with col_human:
    st.markdown("### Annotations humaines (erronees)")

    if human_err_raw is None:
        st.warning(f"Aucun JSON trouve dans `{HUMAN_ERR_DIR}/` pour `{json_name}`.")
    else:
        # On reformate proprement si le JSON est valide, sinon on affiche le texte brut
        if human_err_data is not None:
            display_text = json.dumps(human_err_data, indent=4, ensure_ascii=False)
        else:
            display_text = human_err_raw
        # st.code affiche un bloc avec coloration syntaxique + bouton copier natif
        st.code(display_text, language="json")