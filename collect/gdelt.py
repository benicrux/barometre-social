"""GDELT : couverture presse (API DOC) et événements de contestation géolocalisés."""
from __future__ import annotations

import csv
import io
import time
import zipfile
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta

import pandas as pd

import config
from .common import ErreurSource, fusionner, get, hier, lire, session

DOC = "https://api.gdeltproject.org/api/v2/doc/doc"
V1 = "http://data.gdeltproject.org/events/{j:%Y%m%d}.export.CSV.zip"
V2 = "http://data.gdeltproject.org/gdeltv2/{j:%Y%m%d}{hm}00.export.CSV.zip"
PAUSE_DOC = 6  # GDELT demande au plus une requête toutes les 5 secondes


# --------------------------------------------------------------------------
# 1. Couverture presse : part des articles français qui parlent d'un sujet
# --------------------------------------------------------------------------
def _requete_doc(s, q: str, mode: str, debut: date | None = None,
                 fin: date | None = None) -> list[dict]:
    params = {"query": q, "mode": mode, "format": "json"}
    if debut:
        params["startdatetime"] = f"{debut:%Y%m%d}000000"
        params["enddatetime"] = f"{fin:%Y%m%d}235959"
    else:
        params["timespan"] = "3m"
    for essai in range(4):
        r = get(s, DOC, params=params, pause=8)
        texte = r.text.strip()
        if texte.startswith("{"):
            return r.json().get("timeline", [])
        if "limit" in texte.lower():  # « merci de limiter à 1 requête / 5 s »
            time.sleep(10 * (essai + 1))
            continue
        raise ErreurSource(f"réponse GDELT : {texte[:160]}")
    raise ErreurSource("GDELT limite les requêtes, réessai la semaine prochaine")


def _lignes(cle: str, timeline: list[dict]) -> list[dict]:
    jours: dict[str, dict] = defaultdict(lambda: {"valeur": 0.0, "norm": 0.0, "n": 0})
    if not timeline:
        return []
    for point in timeline[0].get("data", []):
        d = point.get("date", "")
        if len(d) < 8:
            continue
        j = jours[f"{d[:4]}-{d[4:6]}-{d[6:8]}"]
        j["valeur"] += float(point.get("value", 0) or 0)
        j["norm"] += float(point.get("norm", 0) or 0)
        j["n"] += 1
    sortie = []
    for d, v in jours.items():
        if cle == "presse_ton":
            if v["n"]:
                sortie.append({"date": d, "serie": cle, "valeur": v["valeur"] / v["n"]})
        elif v["norm"] > 0:
            sortie.append({"date": d, "serie": cle, "valeur": v["valeur"] / v["norm"]})
    return sortie


def collecter_presse(s) -> str:
    existant = lire("gdelt_presse.csv", dtype=str)
    cible = hier() - timedelta(days=365 * config.GDELT_PRESSE_ANNEES)
    series = dict(config.GDELT_REQUETES, presse_ton=config.GDELT_TON)
    lignes, notes, reussies = [], [], 0
    for cle, spec in series.items():
        mode = "timelinetone" if cle == "presse_ton" else "timelinevolraw"
        # a) rattrapage de l'historique, par tranches de 3 mois : seules les tranches
        #    encore incomplètes sont demandées (donc une seule fois en pratique)
        deja = set(existant[existant["serie"] == cle]["date"]) if not existant.empty else set()
        d, n, borne = cible, 0, hier() - timedelta(days=85)
        while d < borne:
            f = min(d + timedelta(days=89), borne)
            jours = (f - d).days + 1
            presents = sum((d + timedelta(days=k)).isoformat() in deja for k in range(jours))
            if presents < 0.8 * jours:
                try:
                    lignes += _lignes(cle, _requete_doc(s, spec["q"], mode, d, f))
                    n += 1
                except Exception as e:
                    notes.append(f"historique {cle} interrompu ({str(e)[:80]})")
                    break
                time.sleep(PAUSE_DOC)
            d = f + timedelta(days=1)
        if n:
            notes.append(f"historique {cle} : {n} tranches récupérées")
        # b) les trois derniers mois (chaque semaine)
        try:
            lignes += _lignes(cle, _requete_doc(s, spec["q"], mode))
            reussies += 1
        except Exception as e:
            notes.append(f"{cle} : {str(e)[:100]}")
        time.sleep(PAUSE_DOC)
    if not lignes:
        raise ErreurSource("aucune donnée renvoyée par l'API DOC ; " + " ; ".join(notes))
    tout = fusionner(pd.DataFrame(lignes), "gdelt_presse.csv", ["serie", "date"])
    msg = (f"{reussies}/{len(series)} séries à jour, historique depuis "
           f"{tout['date'].min()}, jusqu'au {tout['date'].max()}")
    if notes:
        msg += " ; " + " ; ".join(notes)
    return msg


# --------------------------------------------------------------------------
# 2. Événements de contestation (code CAMEO 14) en France
# --------------------------------------------------------------------------
# Position des colonnes dans les fichiers GDELT 1.0 (58 col.) et 2.0 (61 col.)
COLONNES = {
    58: dict(code=26, racine=28, articles=33, type=49, lieu=50, pays=51, lat=53, lon=54),
    61: dict(code=26, racine=28, articles=33, type=51, lieu=52, pays=53, lat=56, lon=57),
}


def _lire_zip(contenu: bytes):
    with zipfile.ZipFile(io.BytesIO(contenu)) as z:
        for nom in z.namelist():
            with z.open(nom) as f:
                texte = io.TextIOWrapper(f, encoding="utf-8", errors="replace")
                yield from csv.reader(texte, delimiter="\t", quoting=csv.QUOTE_NONE)


def _compter(contenus: list[bytes], agg: dict, lieux: dict) -> None:
    for contenu in contenus:
        for row in _lire_zip(contenu):
            c = COLONNES.get(len(row))
            if not c or row[c["racine"]] != "14" or row[c["pays"]] != "FR":
                continue
            type_evt = config.GDELT_TYPES.get(row[c["code"]][:3], "Autres")
            agg["total"] += 1
            agg[type_evt] += 1
            try:
                agg["articles"] += int(row[c["articles"]] or 0)
            except ValueError:
                pass
            if row[c["type"]] not in ("", "1") and row[c["lat"]] and row[c["lon"]]:
                lieu = lieux.setdefault(row[c["lieu"]], {"lat": row[c["lat"]],
                                                         "lon": row[c["lon"]], "n": 0})
                lieu["n"] += 1


def _telecharger_jour(j: date) -> list[bytes]:
    s = session()
    try:
        r = get(s, V1.format(j=j), accepter_404=True, essais=2, pause=3, timeout=180)
    except Exception:
        r = None
    if r is not None:
        return [r.content]
    # Repli : les 96 fichiers quart-d'heure de GDELT 2.0
    heures = [f"{h:02d}{m:02d}" for h in range(24) for m in (0, 15, 30, 45)]

    def un(hm):
        try:
            rr = get(s, V2.format(j=j, hm=hm), accepter_404=True, essais=2, pause=2)
            return rr.content if rr is not None else None
        except Exception:
            return None

    with ThreadPoolExecutor(max_workers=8) as ex:
        return [c for c in ex.map(un, heures) if c]


def collecter_evenements(s) -> str:
    existant = lire("gdelt_evenements.csv", dtype=str)
    deja = set(existant["date"]) if not existant.empty else set()
    fin = hier()
    debut = fin - timedelta(days=config.GDELT_RATTRAPAGE_JOURS - 1)
    # les jours manquants, du plus récent au plus ancien : la semaine écoulée d'abord
    a_faire = [fin - timedelta(days=k) for k in range((fin - debut).days + 1)
               if (fin - timedelta(days=k)).isoformat() not in deja]
    limite = time.time() + 60 * config.GDELT_BUDGET_MINUTES
    lignes, lignes_lieux, manquants, faits = [], [], [], 0
    with ThreadPoolExecutor(max_workers=3) as ex:
        for i in range(0, len(a_faire), 6):
            if time.time() > limite:
                break
            lot = a_faire[i:i + 6]
            for j, contenus in zip(lot, ex.map(_telecharger_jour, lot)):
                faits += 1
                if not contenus:
                    manquants.append(j.isoformat())
                    continue
                agg, lieux = defaultdict(int), {}
                _compter(contenus, agg, lieux)
                ligne = {"date": j.isoformat(), "total": agg["total"], "articles": agg["articles"]}
                for nom in list(config.GDELT_TYPES.values()) + ["Autres"]:
                    ligne[nom] = agg[nom]
                lignes.append(ligne)
                if (fin - j).days < 70:
                    for nom_lieu, v in lieux.items():
                        lignes_lieux.append({"date": j.isoformat(), "lieu": nom_lieu, **v})
    tout = fusionner(pd.DataFrame(lignes), "gdelt_evenements.csv", ["date"])
    fusionner(pd.DataFrame(lignes_lieux, columns=["date", "lieu", "lat", "lon", "n"]),
              "gdelt_lieux.csv", ["date", "lieu"], garder_jours=70)
    if tout.empty:
        raise ErreurSource("aucun fichier d'événements GDELT disponible")
    msg = (f"{len(lignes)} jours ajoutés ; historique du {tout['date'].min()} "
           f"au {tout['date'].max()}")
    restants = len(a_faire) - faits
    if restants > 0:
        msg += f" ; {restants} jours plus anciens récupérés aux prochains lancements"
    recents = [m for m in manquants if (fin - date.fromisoformat(m)).days < 3]
    if recents:
        msg += f" ; pas encore publiés : {', '.join(sorted(recents))}"
    elif manquants:
        msg += f" ; {len(manquants)} jours indisponibles"
    return msg
