"""GDELT : événements de contestation géolocalisés en France (fichiers quotidiens)."""
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

V1 = "http://data.gdeltproject.org/events/{j:%Y%m%d}.export.CSV.zip"
V2 = "http://data.gdeltproject.org/gdeltv2/{j:%Y%m%d}{hm}00.export.CSV.zip"


# --------------------------------------------------------------------------
# Événements de contestation (code CAMEO 14) en France
# --------------------------------------------------------------------------
# Position des colonnes dans les fichiers GDELT 1.0 (58 col.) et 2.0 (61 col.)
COLONNES = {
    58: dict(code=26, racine=28, articles=33, ton=34, type=49, lieu=50, pays=51, lat=53, lon=54),
    61: dict(code=26, racine=28, articles=33, ton=34, type=51, lieu=52, pays=53, lat=56, lon=57),
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
            if not c or row[c["pays"]] != "FR":
                continue
            try:
                n_art = int(row[c["articles"]] or 0)
                ton = float(row[c["ton"]] or 0)
            except ValueError:
                n_art, ton = 0, 0.0
            # toute l'actualité située en France : volume et tonalité
            agg["fr_evenements"] += 1
            agg["fr_articles"] += n_art
            agg["fr_ton"] += ton * n_art
            if row[c["racine"]] != "14":
                continue
            # actions de contestation
            type_evt = config.GDELT_TYPES.get(row[c["code"]][:3], "Autres")
            agg["total"] += 1
            agg[type_evt] += 1
            agg["articles"] += n_art
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
    deja = set()
    if not existant.empty:
        # un jour est complet s'il contient aussi les mesures de toute l'actualité
        complet = existant["fr_articles"].notna() if "fr_articles" in existant else False
        deja = set(existant.loc[complet, "date"]) if "fr_articles" in existant else set()
    anciens = set(existant["date"]) if not existant.empty else set()
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
                ligne = {"date": j.isoformat(), "total": agg["total"], "articles": agg["articles"],
                         "fr_evenements": agg["fr_evenements"], "fr_articles": agg["fr_articles"],
                         "fr_ton": round(agg["fr_ton"], 1)}
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
    msg = (f"{len(lignes)} jours traités ; historique du {tout['date'].min()} "
           f"au {tout['date'].max()}")
    recalcules = sum(1 for l in lignes if l["date"] in anciens)
    if recalcules:
        msg += f" ; mise à niveau : {recalcules} jours recalculés avec la tonalité"
    restants = len(a_faire) - faits
    if restants > 0:
        msg += f" ; {restants} jours plus anciens récupérés aux prochains lancements"
    recents = [m for m in manquants if (fin - date.fromisoformat(m)).days < 3]
    if recents:
        msg += f" ; pas encore publiés : {', '.join(sorted(recents))}"
    elif manquants:
        msg += f" ; {len(manquants)} jours indisponibles"
    return msg
