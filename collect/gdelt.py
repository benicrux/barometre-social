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
import requests

import config
from .common import ErreurSource, fusionner, get, hier, lire, session

DOC = "https://api.gdeltproject.org/api/v2/doc/doc"
V1 = "http://data.gdeltproject.org/events/{j:%Y%m%d}.export.CSV.zip"
V2 = "http://data.gdeltproject.org/gdeltv2/{j:%Y%m%d}{hm}00.export.CSV.zip"
PAUSE_DOC = 12      # GDELT freine les machines partagées de GitHub : on espace les appels
ATTENTE_429 = 60    # pause quand GDELT répond « trop de requêtes »


class TropDeRequetes(ErreurSource):
    pass


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
    for essai in range(2):
        try:
            r = s.get(DOC, params=params, timeout=90)
        except requests.RequestException:
            time.sleep(15)
            continue
        texte = r.text.strip()
        if r.status_code == 429 or (not texte.startswith("{") and "limit" in texte[:300].lower()):
            raise TropDeRequetes("GDELT refuse pour l'instant les requêtes venant de GitHub (erreur 429)")
        if r.status_code >= 500:
            time.sleep(20)
            continue
        if r.status_code != 200:
            raise ErreurSource(f"HTTP {r.status_code}")
        if texte.startswith("{"):
            return r.json().get("timeline", [])
        if not texte:
            return []  # rien ne correspond à la recherche
        raise ErreurSource(f"réponse GDELT : {texte[:160]}")
    raise ErreurSource("API DOC de GDELT indisponible")


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
    """Bonus : couverture presse via l'API DOC (souvent bloquée depuis GitHub).

    La part de la contestation et la tonalité de l'actualité ne dépendent pas de
    cette API : elles sont calculées à partir des fichiers d'événements.
    """
    existant = lire("gdelt_presse.csv", dtype=str)
    cible = hier() - timedelta(days=365 * config.GDELT_PRESSE_ANNEES)
    series = config.GDELT_REQUETES
    limite = time.time() + 60 * getattr(config, "GDELT_PRESSE_BUDGET_MINUTES", 12)
    lignes, notes, reussies, bloque = [], [], 0, False

    # 1) les trois derniers mois de chaque série
    for cle, spec in series.items():
        try:
            lignes += _lignes(cle, _requete_doc(s, spec["q"], "timelinevolraw"))
            reussies += 1
        except TropDeRequetes:
            bloque = True
            break
        except Exception as e:
            notes.append(f"{cle} : {str(e)[:90]}")
        time.sleep(PAUSE_DOC)

    # 2) l'historique, des tranches les plus récentes aux plus anciennes
    taches, faites = [], 0
    if not bloque:
        borne = hier() - timedelta(days=85)
        for cle in series:
            deja = set(existant[existant["serie"] == cle]["date"]) if not existant.empty else set()
            f = borne
            while f > cible:
                d = max(f - timedelta(days=89), cible)
                jours = (f - d).days + 1
                presents = sum((d + timedelta(days=k)).isoformat() in deja for k in range(jours))
                if presents < 0.8 * jours:
                    taches.append((f, cle, d))
                f = d - timedelta(days=1)
        taches.sort(key=lambda t: t[0], reverse=True)
        for f, cle, d in taches:
            if time.time() > limite:
                break
            try:
                lignes += _lignes(cle, _requete_doc(s, series[cle]["q"], "timelinevolraw", d, f))
                faites += 1
            except TropDeRequetes:
                bloque = True
                break
            except Exception as e:
                notes.append(f"tranche {cle} {d}: {str(e)[:60]}")
            time.sleep(PAUSE_DOC)

    tout = fusionner(pd.DataFrame(lignes, columns=["date", "serie", "valeur"]),
                     "gdelt_presse.csv", ["serie", "date"])
    if reussies == 0:
        raise ErreurSource(
            "GDELT refuse pour l'instant les requêtes venant de GitHub (erreur 429) : "
            "l'indicateur « Presse : licenciements » est en pause, nouvel essai au prochain "
            "lancement. Le reste du tableau de bord n'est pas concerné." if bloque else
            "API DOC indisponible ; " + " ; ".join(notes))
    msg = f"{reussies}/{len(series)} séries à jour"
    if not tout.empty:
        msg += f" ; historique du {tout['date'].min()} au {tout['date'].max()}"
    if taches:
        msg += f" ; rattrapage : {faites}/{len(taches)} tranches"
        if faites < len(taches):
            msg += " (la suite au prochain lancement)"
    if notes:
        msg += " ; " + " ; ".join(notes)
    return msg


# --------------------------------------------------------------------------
# 2. Événements de contestation (code CAMEO 14) en France
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
