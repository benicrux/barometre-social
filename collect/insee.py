"""Enquête mensuelle de conjoncture auprès des ménages (API BDM de l'INSEE)."""
from __future__ import annotations

import io
import unicodedata
import xml.etree.ElementTree as ET

import pandas as pd

import config
from .common import DATA, ErreurSource, fusionner, get

BASES = [
    "https://bdm.insee.fr/series/sdmx",
    "https://api.insee.fr/series/BDM/V1",
    "https://api.insee.fr/series/BDM",
]


def sans_accents(texte: str) -> str:
    t = unicodedata.normalize("NFKD", texte or "")
    return "".join(c for c in t if not unicodedata.combining(c)).lower()


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def parser_sdmx(contenu: bytes) -> list[dict]:
    """Lit une réponse SDMX (format StructureSpecific ou Generic)."""
    series, courante = [], None
    for evt, el in ET.iterparse(io.BytesIO(contenu), events=("start", "end")):
        nom = _local(el.tag)
        if evt == "start" and nom == "Series":
            courante = {"attrs": dict(el.attrib), "obs": []}
        elif evt == "end" and nom == "Obs" and courante is not None:
            periode = el.attrib.get("TIME_PERIOD")
            valeur = el.attrib.get("OBS_VALUE")
            if periode is None:  # format « Generic »
                for enfant in el:
                    n = _local(enfant.tag)
                    if n == "ObsDimension":
                        periode = enfant.attrib.get("value")
                    elif n == "ObsValue":
                        valeur = enfant.attrib.get("value")
            if periode and valeur not in (None, "", "NaN"):
                try:
                    courante["obs"].append((periode, float(valeur)))
                except ValueError:
                    pass
            el.clear()
        elif evt == "end" and nom == "Value" and courante is not None:
            # format Generic : attributs de série sous <Value id= value=>
            if "id" in el.attrib and "value" in el.attrib:
                courante["attrs"].setdefault(el.attrib["id"], el.attrib["value"])
        elif evt == "end" and nom == "Series" and courante is not None:
            series.append(courante)
            courante = None
            el.clear()
    return series


def telecharger(s, chemin: str, params=None) -> bytes:
    erreurs = []
    for base in BASES:
        try:
            r = get(s, f"{base}/{chemin}", params=params, essais=2, pause=3)
            if r is not None and r.content.strip().startswith(b"<"):
                return r.content
            erreurs.append(f"{base}: réponse inattendue")
        except Exception as e:
            erreurs.append(f"{base}: {e}")
    raise ErreurSource(" | ".join(erreurs))


def _score_candidat(attrs: dict) -> float:
    titre = sans_accents(attrs.get("TITLE_FR", ""))
    corr = sans_accents(attrs.get("CORRECTION", ""))
    score = 0.0
    if "cvs" in corr or "cvs" in titre or "corrige" in titre:
        score += 2
    if "solde" in titre:
        score += 1
    if "proportion" in titre or "part " in titre:
        score -= 1
    return score - len(titre) / 1000


def selectionner(series: list[dict]) -> tuple[dict, list[dict]]:
    """Associe chaque série du config à la meilleure série INSEE trouvée."""
    catalogue = []
    for se in series:
        a = se["attrs"]
        catalogue.append({"idbank": a.get("IDBANK", ""), "titre": a.get("TITLE_FR", ""),
                          "correction": a.get("CORRECTION", ""), "freq": a.get("FREQ", ""),
                          "n_obs": len(se["obs"]), "retenue": ""})
    choix = {}
    a_trouver = {**config.INSEE_SERIES, **getattr(config, "INSEE_QUESTIONS", {})}
    for cle, spec in a_trouver.items():
        meilleurs = []
        for i, se in enumerate(series):
            a = se["attrs"]
            if a.get("FREQ") not in (None, "", "M"):
                continue
            titre = sans_accents(a.get("TITLE_FR", ""))
            if cle == "confiance" and a.get("IDBANK") == config.INSEE_IDBANK_CONFIANCE:
                meilleurs.append((99.0, i))
                continue
            if all(m in titre for m in spec["inclure"]) and not any(
                    m in titre for m in spec["exclure"]):
                meilleurs.append((_score_candidat(a), i))
        if meilleurs:
            _, i = max(meilleurs)
            choix[cle] = series[i]
            catalogue[i]["retenue"] = ";".join(filter(None, [catalogue[i]["retenue"], cle]))
    return choix, catalogue


def collecter(s) -> str:
    series, source = [], ""
    try:
        contenu = telecharger(s, f"data/{config.INSEE_DATAFLOW}",
                              params={"startPeriod": "2010-01"})
        series = parser_sdmx(contenu)
        source = "jeu complet"
    except Exception as e:
        source = f"jeu complet indisponible ({str(e)[:120]}), repli sur la confiance seule"
    if not series:
        contenu = telecharger(s, f"data/SERIES_BDM/{config.INSEE_IDBANK_CONFIANCE}",
                              params={"startPeriod": "2010-01"})
        series = parser_sdmx(contenu)

    choix, catalogue = selectionner(series)
    pd.DataFrame(catalogue).to_csv(DATA / "insee_catalogue.csv", index=False)
    lignes = []
    for cle, se in choix.items():
        for periode, valeur in se["obs"]:
            if len(periode) == 7:  # AAAA-MM
                lignes.append({"date": f"{periode}-01", "serie": cle, "valeur": valeur})
    if not lignes:
        raise ErreurSource("aucune série reconnue dans la réponse INSEE")
    tout = fusionner(pd.DataFrame(lignes), "insee.csv", ["serie", "date"])
    dernier = tout["date"].max()[:7]
    manquantes = [c for c in config.INSEE_SERIES if c not in choix]
    n_q = sum(c in choix for c in getattr(config, "INSEE_QUESTIONS", {}))
    msg = (f"{len([c for c in choix if c in config.INSEE_SERIES])} séries ({source}), "
           f"dernier mois {dernier} ; {n_q} questions détaillées")
    if manquantes:
        msg += f" ; non trouvées : {', '.join(manquantes)}"
    return msg
