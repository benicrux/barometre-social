"""Le « terrain » par département : chômage localisé (trimestriel) et pauvreté (annuelle).

Le chômage vient de la même base INSEE que l'enquête ménages (jeu TAUX-CHOMAGE),
avec un repli sur le miroir DBnomics. La pauvreté vient du fichier Filosofi publié
une fois par an par l'Insee (adresse dans config.py, à mettre à jour chaque année).
"""
from __future__ import annotations

import io
import re

import pandas as pd

import config
from .common import DATA, ErreurSource, fusionner, get, lire
from .insee import parser_sdmx, telecharger

DBNOMICS = "https://api.db.nomics.world/v22/series/INSEE/TAUX-CHOMAGE"


def _code_dep(zone: str) -> str | None:
    """« D01 » -> « 01 », « D2A » -> « 2A » ; None pour les régions et la France."""
    m = re.fullmatch(r"D(\d{2,3}|2A|2B)", zone or "")
    return m.group(1) if m else None


def _zone(valeurs) -> str:
    """Première valeur de la forme « D01 » parmi les dimensions d'une série."""
    for v in valeurs:
        if _code_dep(str(v)):
            return str(v)
    return ""


def _chomage_bdm(s) -> list[dict]:
    contenu = telecharger(s, "data/TAUX-CHOMAGE", params={"startPeriod": "2010-Q1"})
    lignes = []
    for se in parser_sdmx(contenu):
        a = se["attrs"]
        if a.get("CORRECTION") not in (None, "", "CVS"):
            continue
        zone = a.get("REF_AREA", "") if _code_dep(a.get("REF_AREA", "")) else _zone(a.values())
        if not zone:  # dernier recours : le code entre parenthèses dans le titre
            titre = a.get("TITLE_FR", "")
            m = re.search(r"\((\d{2}|2A|2B|97\d)\)", titre)
            zone = f"D{m.group(1)}" if m and "partement" in titre.lower() else ""
        for periode, valeur in se["obs"]:
            lignes.append({"trimestre": periode, "zone": zone, "valeur": valeur})
    return lignes


def _chomage_dbnomics(s) -> list[dict]:
    lignes, offset = [], 0
    while offset < 500:
        r = get(s, DBNOMICS, params={"observations": "1", "format": "json",
                                      "limit": "100", "offset": str(offset)}, essais=2)
        docs = r.json().get("series", {}).get("docs", [])
        if not docs:
            break
        for d in docs:
            dims = d.get("dimensions") or {}
            if "BRUT" in dims.values():
                continue
            zone = _zone(dims.values())
            for periode, valeur in zip(d.get("period", []), d.get("value", [])):
                if valeur not in (None, "NA") and str(periode) >= "2010":
                    lignes.append({"trimestre": str(periode), "zone": zone,
                                   "valeur": float(valeur)})
        offset += 100
    return lignes


def collecter_chomage(s) -> str:
    source, lignes = "INSEE", []
    try:
        lignes = _chomage_bdm(s)
    except Exception as e:
        print(f"  chômage INSEE indisponible, repli sur DBnomics : {e}", flush=True)
        source = "miroir DBnomics, INSEE indisponible"
    if not lignes:
        lignes = _chomage_dbnomics(s)
    lignes = [l for l in lignes if _code_dep(l["zone"])]
    if not lignes:
        raise ErreurSource("aucune série départementale de chômage reconnue")
    tout = fusionner(pd.DataFrame(lignes), "chomage_dep.csv", ["zone", "trimestre"])
    return (f"chômage : {tout['zone'].nunique()} départements, dernier trimestre "
            f"{tout['trimestre'].max()} ({source})")


def _lire_pauvrete(contenu: bytes) -> pd.DataFrame:
    """Repère, dans le classeur Filosofi, le tableau « taux de pauvreté par département »."""
    feuilles = pd.read_excel(io.BytesIO(contenu), sheet_name=None, header=None, dtype=str)
    meilleur = pd.DataFrame()
    for nom, f in feuilles.items():
        lignes = []
        for _, row in f.iterrows():
            cells = [str(c).strip() for c in row.tolist() if str(c).strip() not in ("", "nan")]
            if len(cells) < 2:
                continue
            code = cells[0]
            if not re.fullmatch(r"\d{2}|2A|2B|97\d", code):
                continue
            valeurs = []
            for c in cells[1:]:
                try:
                    valeurs.append(float(c.replace(",", ".").replace(" ", "")))
                except ValueError:
                    continue
            taux = [v for v in valeurs if 3 <= v <= 90]
            if taux:
                lignes.append({"dep": code, "taux_pauvrete": taux[0]})
        df = pd.DataFrame(lignes).drop_duplicates("dep") if lignes else pd.DataFrame()
        if len(df) > len(meilleur):
            meilleur = df
    return meilleur


def collecter_pauvrete(s) -> str:
    url = getattr(config, "PAUVRETE_URL", "")
    if not url:
        return "pauvreté : pas de fichier configuré"
    deja = lire("pauvrete_dep.csv", dtype=str)
    if not deja.empty and (deja["source"] == url).all():
        return f"pauvreté : millésime {deja['millesime'].iloc[0]} déjà en place"
    r = get(s, url, essais=2, timeout=120)
    df = _lire_pauvrete(r.content)
    if len(df) < 80:
        raise ErreurSource(f"tableau départemental de pauvreté non reconnu dans {url}")
    df["millesime"] = str(getattr(config, "PAUVRETE_MILLESIME", ""))
    df["source"] = url
    df.to_csv(DATA / "pauvrete_dep.csv", index=False)
    return f"pauvreté : {len(df)} départements (millésime {df['millesime'].iloc[0]})"


def collecter(s) -> str:
    msg = collecter_chomage(s)
    try:
        msg += " ; " + collecter_pauvrete(s)
    except Exception as e:
        msg += f" ; pauvreté indisponible ({str(e)[:100]})"
    return msg
