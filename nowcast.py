"""Prévoir le prochain chiffre INSEE de confiance des ménages avant sa publication.

Le modèle (régression ridge) relie la variation mensuelle de la confiance aux
variations de l'intérêt pour les sujets suivis sur Wikipédia pendant les trois
premières semaines du mois (la période où l'INSEE interroge les ménages).
On le compare honnêtement à la prévision naïve « même chiffre que le mois dernier ».
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

from collect.common import aujourdhui, fusionner, lire
from indicators import MOIS_COURT, libelle_mois

LAMBDA = 5.0
N_TEST = 36


def _features_mensuelles(paniers: pd.DataFrame) -> pd.DataFrame:
    if paniers.empty:
        return paniers
    jeudi = paniers.index - pd.Timedelta(days=3)
    garde = jeudi.day <= 21
    p = paniers[garde].copy()
    p.index = jeudi[garde].to_period("M").to_timestamp()
    return p.groupby(level=0).mean()


def _ridge(X: np.ndarray, y: np.ndarray):
    mu, sd = X.mean(0), X.std(0)
    sd[sd < 1e-9] = 1
    Xs = (X - mu) / sd
    ym = y.mean()
    beta = np.linalg.solve(Xs.T @ Xs + LAMBDA * np.eye(X.shape[1]), Xs.T @ (y - ym))
    return lambda Xn: ym + ((Xn - mu) / sd) @ beta


def prevoir(ind: dict) -> dict:
    insee, paniers = ind.get("_insee"), ind.get("_wiki_paniers")
    if insee is None or insee.empty or "confiance" not in insee:
        return {"dispo": False, "raison": "série INSEE de confiance pas encore disponible"}
    y = insee["confiance"].dropna()
    dernier_mois = y.index.max()
    cible = dernier_mois + pd.DateOffset(months=1)
    base = {"dispo": True, "mois_cible": libelle_mois(cible),
            "dernier": {"mois": libelle_mois(dernier_mois), "valeur": float(y.iloc[-1])},
            "naif": float(y.iloc[-1])}

    Xm = _features_mensuelles(paniers if paniers is not None else pd.DataFrame())
    if Xm.empty or len(Xm) < 30:
        base.update(prevision=None, verdict="Pas encore assez d'historique Wikipédia "
                    "pour entraîner le modèle.", tableau=[])
        return base

    dX = Xm.diff()
    dy = y.diff()
    jeu = pd.concat([dy.rename("dy"), dX], axis=1).dropna()
    cols = list(dX.columns)

    # Test « comme en vrai » : chaque mois est prévu sans connaître la suite
    tests = []
    for t in jeu.index[-N_TEST:]:
        train = jeu.loc[:t].iloc[:-1]
        if len(train) < 24:
            continue
        f = _ridge(train[cols].values, train["dy"].values)
        pred = float(f(jeu.loc[[t], cols].values)[0])
        prec = y.get(t - pd.DateOffset(months=1))
        tests.append({"mois": t, "prevision": prec + pred, "naif": prec, "reel": y[t]})
    if tests:
        e_mod = [abs(r["prevision"] - r["reel"]) for r in tests]
        e_nai = [abs(r["naif"] - r["reel"]) for r in tests]
        rmse_m = math.sqrt(np.mean(np.square(e_mod)))
        rmse_n = math.sqrt(np.mean(np.square(e_nai)))
        # écart moyen, en points : la mesure affichée (plus parlante que la RMSE)
        ecart_m, ecart_n = float(np.mean(e_mod)), float(np.mean(e_nai))
    else:
        rmse_m = rmse_n = ecart_m = ecart_n = None

    # Prévision du mois cible
    prevision, semaines = None, 0
    if cible in Xm.index and dernier_mois in Xm.index:
        f = _ridge(jeu[cols].values, jeu["dy"].values)
        x = (Xm.loc[cible] - Xm.loc[dernier_mois]).values.reshape(1, -1)
        if not np.isnan(x).any():
            prevision = round(float(y.iloc[-1] + f(x)[0]), 1)
            jeudis = paniers.index - pd.Timedelta(days=3)
            semaines = int(((jeudis.to_period("M").to_timestamp() == cible)
                            & (jeudis.day <= 21)).sum())

    # Journal des prévisions publiées (pour le « prévu vs réalisé » en direct)
    if prevision is not None:
        fusionner(pd.DataFrame([{"date_calcul": aujourdhui().isoformat(),
                                 "mois_cible": cible.date().isoformat(),
                                 "prevision": prevision, "naif": float(y.iloc[-1])}]),
                  "previsions.csv", ["date_calcul", "mois_cible"])
    journal = lire("previsions.csv")

    tableau = []
    for r in tests[-12:]:
        ligne = {"mois": libelle_mois(r["mois"]), "court": MOIS_COURT[r["mois"].month - 1],
                 "prevision": round(r["prevision"], 1),
                 "naif": round(r["naif"], 1), "reel": round(r["reel"], 1), "mode": "test"}
        if not journal.empty:
            j = journal[journal["mois_cible"] == r["mois"].date().isoformat()]
            j = j[j["date_calcul"] < (r["mois"] + pd.Timedelta(days=26)).date().isoformat()]
            if not j.empty:
                ligne["prevision"] = round(float(j["prevision"].iloc[-1]), 1)
                ligne["mode"] = "direct"
        ligne["ecart"] = round(ligne["prevision"] - ligne["reel"], 1)
        ligne["ecart_naif"] = round(ligne["naif"] - ligne["reel"], 1)
        tableau.append(ligne)

    pts = lambda x: f"{x:.1f}".replace(".", ",") + (" point" if x < 2 else " points")
    if rmse_m is None:
        verdict, bat = "Fiabilité pas encore mesurable.", None
    else:
        bat = rmse_m < rmse_n * 0.95
        verdict = (f"Fiabilité : sur les {len(tests)} derniers mois, l'estimation est tombée en "
                   f"moyenne à {pts(ecart_m)} du vrai chiffre. ")
        if bat:
            verdict += (f"C'est mieux que de simplement reprendre le chiffre du mois "
                        f"précédent ({pts(ecart_n)} d'écart).")
        else:
            verdict += (f"Ce n'est pas mieux que de simplement reprendre le chiffre du mois "
                        f"précédent ({pts(ecart_n)} d'écart) : à prendre comme une indication.")

    tendance = None
    if prevision is not None:
        d = prevision - y.iloc[-1]
        tendance = "stable" if abs(d) < 0.5 else ("hausse" if d > 0 else "baisse")

    base.update(prevision=prevision, semaines=semaines, tendance=tendance,
                rmse_modele=None if rmse_m is None else round(rmse_m, 2),
                rmse_naif=None if rmse_n is None else round(rmse_n, 2),
                n_test=len(tests), bat_naif=bat, verdict=verdict, tableau=tableau,
                court_cible=MOIS_COURT[cible.month - 1])
    return base
