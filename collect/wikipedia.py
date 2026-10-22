"""Pages vues Wikipédia (API Wikimedia, gratuite, sans clé)."""
from __future__ import annotations

from datetime import date, timedelta
from urllib.parse import quote

import pandas as pd

import config
from .common import (aujourdhui, ecrire_json, fusionner, get, hier, lire,
                     lire_json)

API_PV = "https://wikimedia.org/api/rest_v1/metrics/pageviews"
API_WP = "https://fr.wikipedia.org/w/api.php"

# Pages techniques à ne jamais afficher dans « ce qui monte »
EXCLUS_PREFIXES = ("Spécial:", "Special:", "Wikipédia:", "Fichier:", "Portail:",
                   "Aide:", "Catégorie:", "Modèle:", "Utilisateur:", "Projet:",
                   "Discussion", "Module:", "Référence:")
EXCLUS_TITRES = {"-", "Accueil", "Wikipédia:Accueil_principal", "Main_Page"}


def resoudre_titres(s, titres: list[str]) -> dict[str, str | None]:
    """Titre configuré -> titre canonique (redirections suivies) ou None."""
    resultat: dict[str, str | None] = {}
    for i in range(0, len(titres), 40):
        lot = titres[i:i + 40]
        r = get(s, API_WP, params={
            "action": "query", "format": "json", "formatversion": "2",
            "redirects": "1", "titles": "|".join(lot)})
        q = r.json().get("query", {})
        norm = {n["from"]: n["to"] for n in q.get("normalized", [])}
        redir = {n["from"]: n["to"] for n in q.get("redirects", [])}
        absents = {p["title"] for p in q.get("pages", [])
                   if p.get("missing") or p.get("invalid")}
        for t in lot:
            final = norm.get(t, t)
            # une redirection peut en cacher une autre
            for _ in range(3):
                final = redir.get(final, final)
            resultat[t] = None if final in absents else final
    return resultat


def _url_article(titre: str, debut: date, fin: date) -> str:
    t = quote(titre.replace(" ", "_"), safe="")
    return (f"{API_PV}/per-article/fr.wikipedia/all-access/user/{t}/daily/"
            f"{debut:%Y%m%d}00/{fin:%Y%m%d}00")


def collecter_pages(s) -> str:
    titres = sorted({t for liste in config.WIKI_PAGES.values() for t in liste})
    resolution = resoudre_titres(s, titres)
    ecrire_json("wiki_pages.json", resolution)

    existant = lire("wikipedia.csv", dtype={"vues": float})
    derniere = {}
    if not existant.empty:
        derniere = existant.groupby("page")["date"].max().to_dict()

    fin = hier()
    lignes, erreurs = [], []
    for canon in sorted({c for c in resolution.values() if c}):
        debut = date.fromisoformat(config.WIKI_DEBUT)
        if canon in derniere:
            debut = date.fromisoformat(derniere[canon]) - timedelta(days=3)
        if debut > fin:
            continue
        try:
            r = get(s, _url_article(canon, debut, fin), accepter_404=True, pause=2)
        except Exception as e:  # une page en erreur n'arrête pas les autres
            erreurs.append(f"{canon} ({e})")
            continue
        if r is None:
            continue
        for it in r.json().get("items", []):
            ts = it["timestamp"]
            lignes.append({"date": f"{ts[:4]}-{ts[4:6]}-{ts[6:8]}",
                           "page": canon, "vues": it["views"]})
    nouveau = pd.DataFrame(lignes, columns=["date", "page", "vues"])
    tout = fusionner(nouveau, "wikipedia.csv", ["page", "date"])
    manquantes = [t for t, c in resolution.items() if c is None]
    msg = f"{len(set(tout['page'])) if not tout.empty else 0} pages suivies"
    if manquantes:
        msg += f" ; introuvables : {', '.join(manquantes)}"
    if erreurs:
        msg += f" ; erreurs : {', '.join(erreurs[:3])}"
    return msg


def collecter_top(s, jours: int = 35) -> str:
    """Classement quotidien des pages les plus lues (pour « ce qui monte »)."""
    existant = lire("wiki_top.csv", dtype=str)
    deja = set(existant["date"]) if not existant.empty else set()
    lignes, n = [], 0
    for k in range(1, jours + 1):
        d = aujourdhui() - timedelta(days=k)
        if d.isoformat() in deja:
            continue
        r = get(s, f"{API_PV}/top/fr.wikipedia/all-access/{d:%Y/%m/%d}",
                accepter_404=True, pause=2)
        if r is None:
            continue
        items = r.json().get("items", [])
        if not items:
            continue
        n += 1
        for a in items[0].get("articles", [])[:500]:
            lignes.append({"date": d.isoformat(), "page": a["article"],
                           "vues": a["views"]})
    fusionner(pd.DataFrame(lignes, columns=["date", "page", "vues"]),
              "wiki_top.csv", ["date", "page"], garder_jours=70)
    return f"classements quotidiens : {n} nouveaux jours"


def page_exclue(titre: str) -> bool:
    return titre in EXCLUS_TITRES or titre.startswith(EXCLUS_PREFIXES)


def collecter(s) -> str:
    msg = collecter_pages(s)
    try:
        msg += " ; " + collecter_top(s)
    except Exception as e:
        msg += f" ; classement indisponible ({e})"
    return msg


def resolution_pages() -> dict:
    return lire_json("wiki_pages.json", {}) or {}
