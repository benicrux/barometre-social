"""Volet « État du pays » : séries INSEE choisies dans config.PAYS (téléchargées par identifiant)."""
from __future__ import annotations

import pandas as pd

import config
from .common import ErreurSource, fusionner
from .insee import parser_sdmx, telecharger


def idbanks() -> list[str]:
    ids = {config.PAYS_DEFLATEUR}
    for ind in config.PAYS:
        ids.update(ind["idbank"] if isinstance(ind["idbank"], list) else [ind["idbank"]])
    return sorted(ids)


def collecter(s) -> str:
    ids, lignes, erreurs = idbanks(), [], []
    for i in range(0, len(ids), 8):  # par paquets, pour garder des adresses courtes
        paquet = ids[i:i + 8]
        try:
            contenu = telecharger(s, "data/SERIES_BDM/" + "+".join(paquet),
                                  params={"startPeriod": "2008"})
        except Exception as e:
            erreurs.append(f"{', '.join(paquet)} : {str(e)[:80]}")
            continue
        for se in parser_sdmx(contenu):
            idb = se["attrs"].get("IDBANK", "")
            for periode, valeur in se["obs"]:
                lignes.append({"idbank": idb, "periode": periode, "valeur": valeur})
    if not lignes:
        raise ErreurSource("aucune série reçue de l'INSEE" + (f" ({erreurs[0]})" if erreurs else ""))
    fusionner(pd.DataFrame(lignes), "pays.csv", ["idbank", "periode"])
    recues = set(pd.DataFrame(lignes)["idbank"])
    manquantes = [i for i in ids if i not in recues]
    msg = f"{len(recues)} séries sur {len(ids)}"
    if manquantes:
        msg += f" ; non reçues : {', '.join(manquantes)}"
    return msg
