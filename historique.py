"""Test sur le passé (lancement ponctuel) : reconstitue l'historique GDELT et carburants.

    python historique.py SORTIE gdelt AAAA-MM-JJ AAAA-MM-JJ
    python historique.py SORTIE carburants
"""
import os
import sys
import time
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor
from datetime import date, timedelta
from pathlib import Path

sortie = Path(sys.argv[1]).resolve()
sortie.mkdir(parents=True, exist_ok=True)
os.environ["BAROMETRE_DATA"] = str(sortie)
mode = sys.argv[2]

import pandas as pd  # noqa: E402

import config  # noqa: E402
from collect import carburants, gdelt  # noqa: E402
from collect.common import session  # noqa: E402


def jour(j: date):
    contenus = gdelt._telecharger_jour(j)
    if not contenus:
        return None
    agg, lieux = defaultdict(int), {}
    gdelt._compter(contenus, agg, lieux)
    ligne = {"date": j.isoformat(), "total": agg["total"], "articles": agg["articles"],
             "fr_evenements": agg["fr_evenements"], "fr_articles": agg["fr_articles"],
             "fr_ton": round(agg["fr_ton"], 1)}
    for nom in list(config.GDELT_TYPES.values()) + ["Autres"]:
        ligne[nom] = agg[nom]
    return ligne


if mode == "gdelt":
    debut, fin = date.fromisoformat(sys.argv[3]), date.fromisoformat(sys.argv[4])
    jours = [debut + timedelta(days=k) for k in range((fin - debut).days + 1)]
    t0, lignes, manquants = time.time(), [], []
    with ProcessPoolExecutor(max_workers=6) as ex:
        for j, l in zip(jours, ex.map(jour, jours, chunksize=2)):
            if l:
                lignes.append(l)
            else:
                manquants.append(j.isoformat())
    pd.DataFrame(lignes).to_csv(sortie / f"gdelt_{debut}_{fin}.csv", index=False)
    print(f"{len(lignes)} jours en {time.time() - t0:.0f} s ; {len(manquants)} manquants : {manquants[:30]}")
elif mode == "carburants":
    config.CARBURANTS_ANNEES = 11
    print(carburants.rattraper_historique(session()))
