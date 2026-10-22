"""Point d'entrée : collecte -> calcul -> page web.

Usage :
    python main.py               # collecte complète puis génération de la page
    python main.py --sans-collecte   # recalcule la page avec les données déjà stockées
"""
from __future__ import annotations

import sys
import time
import traceback

from collect import carburants, gdelt, insee, wikipedia
from collect.common import ecrire_json, lire_json, session

SOURCES = [
    ("Wikipédia", wikipedia.collecter),
    ("INSEE (enquête ménages)", insee.collecter),
    ("GDELT presse", gdelt.collecter_presse),
    ("GDELT événements", gdelt.collecter_evenements),
    ("Prix des carburants", carburants.collecter),
]


def collecter() -> list[dict]:
    s = session()
    statuts = []
    for nom, fonction in SOURCES:
        debut = time.time()
        try:
            message = fonction(s)
            statuts.append({"source": nom, "ok": True, "message": message})
            print(f"[ok] {nom} ({time.time() - debut:.0f} s) : {message}", flush=True)
        except Exception as e:  # une source en panne ne bloque jamais les autres
            traceback.print_exc()
            statuts.append({"source": nom, "ok": False, "message": str(e)[:300]})
            print(f"[ÉCHEC] {nom} : {e}", flush=True)
    ecrire_json("statut.json", statuts)
    return statuts


def main(argv: list[str]) -> int:
    if "--sans-collecte" in argv:
        statuts = lire_json("statut.json", []) or []
    else:
        statuts = collecter()

    import indicators
    import nowcast
    import render

    ind = indicators.calculer()
    try:
        prev = nowcast.prevoir(ind)
    except Exception as e:
        traceback.print_exc()
        prev = {"dispo": False, "raison": f"prévision indisponible cette semaine ({e})"}
    chemin = render.generer(ind, prev, statuts)
    print(f"Page générée : {chemin}")
    print(f"Météo sociale : {ind['meteo']['score']} ({ind['meteo']['statut'][0]})")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
