"""Prix à la pompe : moyenne nationale du jour (flux instantané v2) et, au premier
lancement, historique hebdomadaire reconstitué depuis les archives annuelles officielles."""
from __future__ import annotations

import io
import re
import xml.etree.ElementTree as ET
import zipfile
from collections import defaultdict
from datetime import date, timedelta

import pandas as pd

import config
from .common import ErreurSource, aujourdhui, fusionner, get, lire

URL = ("https://data.economie.gouv.fr/api/explore/v2.1/catalog/datasets/"
       "prix-des-carburants-en-france-flux-instantane-v2/exports/csv")
ANNUEL = ["https://donnees.roulez-eco.fr/opendata/annee/{annee}",
          "https://donnees.roulez-eco.fr/opendata/annee"]  # année en cours

MOTIFS = {"gazole": r"gazole.*prix|prix.*gazole", "e10": r"e10.*prix|prix.*e10"}
NOMS_XML = {"gazole": "gazole", "e10": "e10"}


def _colonne(colonnes, motif):
    for c in colonnes:
        if re.search(motif, c.lower()):
            return c
    return None


def _prix(v: float) -> float | None:
    if v > 100:  # anciennes archives : millièmes d'euro
        v = v / 1000
    return v if 0.5 < v < 4 else None


def _fin_semaine(d: date) -> date:
    return d + timedelta(days=6 - d.weekday())


# --------------------------------------------------------------------------
# Historique : archives annuelles (XML de toutes les mises à jour de prix)
# --------------------------------------------------------------------------
def _archive_annuelle(s, annee: int) -> dict:
    """{(fin de semaine, carburant): [somme, nombre]} pour une année."""
    contenu = None
    for modele in ANNUEL:
        if "{annee}" not in modele and annee != aujourdhui().year:
            continue
        try:
            r = get(s, modele.format(annee=annee), essais=2, timeout=600, accepter_404=True)
            if r is not None and r.content[:2] == b"PK":
                contenu = r.content
                break
        except Exception:
            continue
    if contenu is None:
        raise ErreurSource(f"archive {annee} indisponible")
    cumul = defaultdict(lambda: [0.0, 0])
    with zipfile.ZipFile(io.BytesIO(contenu)) as z:
        for nom in z.namelist():
            with z.open(nom) as f:
                for _, el in ET.iterparse(f, events=("end",)):
                    if el.tag == "prix":
                        carbu = NOMS_XML.get((el.get("nom") or "").lower())
                        maj, val = el.get("maj") or "", el.get("valeur")
                        if carbu and len(maj) >= 10 and val:
                            try:
                                p = _prix(float(val.replace(",", ".")))
                                j = date.fromisoformat(maj[:10])
                            except ValueError:
                                continue
                            if p:
                                c = cumul[(_fin_semaine(j), carbu)]
                                c[0] += p
                                c[1] += 1
                    elif el.tag == "pdv":
                        el.clear()
    return cumul


def rattraper_historique(s) -> str:
    existant = lire("carburants.csv", dtype=str)
    if len(existant) >= 30:
        return ""
    cumul = defaultdict(lambda: [0.0, 0])
    annees, erreurs = [], []
    an = aujourdhui().year
    for annee in range(an - config.CARBURANTS_ANNEES + 1, an + 1):
        try:
            for k, (somme, n) in _archive_annuelle(s, annee).items():
                cumul[k][0] += somme
                cumul[k][1] += n
            annees.append(str(annee))
        except Exception as e:
            erreurs.append(str(e)[:80])
    semaine_en_cours = _fin_semaine(aujourdhui())
    deja = set(existant["date"]) if not existant.empty else set()
    par_semaine = defaultdict(dict)
    for (fin_sem, carbu), (somme, n) in cumul.items():
        if fin_sem < semaine_en_cours and n >= 500:
            par_semaine[fin_sem][carbu] = round(somme / n, 4)
            par_semaine[fin_sem][f"n_{carbu}"] = n
    lignes = []
    for fin_sem, v in sorted(par_semaine.items()):
        cle_date = (fin_sem + timedelta(days=1)).isoformat()  # comme un relevé du lundi
        if cle_date not in deja:
            lignes.append({"date": cle_date, **v})
    if lignes:
        fusionner(pd.DataFrame(lignes), "carburants.csv", ["date"])
    msg = f"historique reconstitué : {len(lignes)} semaines ({', '.join(annees) or 'aucune archive'})"
    if erreurs:
        msg += f" ; {' ; '.join(erreurs)}"
    return msg


# --------------------------------------------------------------------------
# Relevé de la semaine : moyenne nationale du flux instantané
# --------------------------------------------------------------------------
def collecter(s) -> str:
    try:
        histo = rattraper_historique(s)
    except Exception as e:
        histo = f"historique indisponible ({str(e)[:80]})"

    r = None
    for params in ({"delimiter": ";", "select": "gazole_prix,e10_prix"},
                   {"delimiter": ";"}):
        try:
            r = get(s, URL, params=params, essais=2, timeout=180)
            break
        except Exception:
            r = None
    if r is None:
        raise ErreurSource("export des prix des carburants indisponible"
                           + (f" ; {histo}" if histo else ""))

    df = pd.read_csv(io.BytesIO(r.content), sep=";", low_memory=False)
    ligne = {"date": aujourdhui().isoformat()}
    for carbu, motif in MOTIFS.items():
        col = _colonne(df.columns, motif)
        if col is None:
            continue
        prix = pd.to_numeric(df[col].astype(str).str.replace(",", "."), errors="coerce")
        if prix.median() > 100:  # certaines versions donnent des millièmes d'euro
            prix = prix / 1000
        prix = prix[(prix > 0.5) & (prix < 4)]
        if len(prix) > 100:
            ligne[carbu] = round(float(prix.mean()), 4)
            ligne[f"n_{carbu}"] = int(len(prix))
    if "gazole" not in ligne and "e10" not in ligne:
        raise ErreurSource(f"colonnes de prix introuvables ({', '.join(df.columns[:12])}…)")
    fusionner(pd.DataFrame([ligne]), "carburants.csv", ["date"])
    msg = " ; ".join(f"{k} {v:.3f} €" for k, v in ligne.items() if k in MOTIFS)
    return msg + (f" ; {histo}" if histo else "")
