"""Pages vues Wikipédia (API Wikimedia, gratuite, sans clé)."""
from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from urllib.parse import quote

import numpy as np
import pandas as pd

import config
from .common import (DATA, aujourdhui, derniere_semaine_finie, ecrire_json, fusionner,
                     get, hier, lire, lire_json, sans_accents)

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
    try:
        msg += " ; " + detecter_sujets(s)
    except Exception as e:
        msg += f" ; détection des sujets émergents indisponible ({str(e)[:100]})"
    return msg


# --------------------------------------------------------------------------
# Sujets émergents
# --------------------------------------------------------------------------
def pages_en_hausse(top: pd.DataFrame, fin: pd.Timestamp) -> pd.DataFrame:
    """Pages dont la lecture a bondi sur la semaine, vs les 4 semaines d'avant."""
    if top.empty:
        return pd.DataFrame(columns=["vues", "ratio"])
    top = top.assign(date=pd.to_datetime(top["date"]))
    sem = top[(top["date"] > fin - pd.Timedelta(days=7)) & (top["date"] <= fin)]
    base = top[(top["date"] > fin - pd.Timedelta(days=35)) &
               (top["date"] <= fin - pd.Timedelta(days=7))]
    if sem.empty:
        return pd.DataFrame(columns=["vues", "ratio"])
    # en dessous du dernier rang du classement, on ne connaît pas les vues :
    # on prend ce plancher comme estimation prudente
    plancher = 7 * (base if not base.empty else sem).groupby("date")["vues"].min().mean()
    vs = sem.groupby("page")["vues"].sum()
    vb = (base.groupby("page")["vues"].sum() / 4).reindex(vs.index).fillna(0)
    res = pd.DataFrame({"vues": vs, "ratio": vs / np.maximum(vb, plancher)})
    res = res[[not page_exclue(p) for p in res.index]]
    return res[res["vues"] >= 2 * plancher].sort_values("ratio", ascending=False)


def _categories(s, titres: list[str]) -> dict[str, list[str]]:
    """Catégories Wikipédia (hors catégories cachées) de chaque titre demandé."""
    res: dict[str, list[str]] = defaultdict(list)
    for i in range(0, len(titres), 20):
        lot = titres[i:i + 20]
        params = {"action": "query", "format": "json", "formatversion": "2",
                  "prop": "categories", "clshow": "!hidden", "cllimit": "max",
                  "redirects": "1", "titles": "|".join(lot)}
        suite: dict = {}
        for _ in range(10):
            j = get(s, API_WP, params={**params, **suite}, pause=2).json()
            q = j.get("query", {})
            retour = {n["to"]: n["from"] for n in q.get("normalized", []) + q.get("redirects", [])}
            for p in q.get("pages", []):
                t = p.get("title", "")
                for _ in range(4):  # remonte redirection puis normalisation
                    t = retour.get(t, t)
                for c in p.get("categories", []):
                    res[t.replace(" ", "_")].append(c["title"].split(":", 1)[-1])
            if "continue" not in j:
                break
            suite = j["continue"]
    return res


def classer(titre: str, categories: list[str]):
    """-> (jauge, catégorie qui justifie le choix) ou None si hors sujet."""
    norm = [sans_accents(c) for c in categories]
    t = sans_accents(titre.replace("_", " "))
    if not (any("france" in c or "francais" in c for c in norm)
            or "france" in t or "francais" in t):
        return None
    scores, raison = defaultdict(int), {}
    for jauge, mots in config.SUJETS_MOTS.items():
        for c, brute in zip(norm, categories):
            if any(m in c for m in mots):
                scores[jauge] += 1
                raison.setdefault(jauge, brute)
    if not scores:
        return None
    if any(any(m in c for m in config.SUJETS_EXCLUS) for c in norm) and "mobilisation" not in scores:
        return None
    personne = any(c.startswith(("naissance en", "deces en")) for c in norm)
    if personne and not ({"institutions", "mobilisation"} & set(scores)):
        return None
    jauge = max(scores, key=scores.get)
    return jauge, raison[jauge]


def _historique_hebdo(s, page: str, debut: date) -> pd.DataFrame:
    r = get(s, _url_article(page.replace("_", " "), debut, hier()), accepter_404=True, pause=2)
    if r is None:
        return pd.DataFrame(columns=["semaine", "page", "vues"])
    j = pd.DataFrame([{"date": it["timestamp"][:8], "vues": it["views"]}
                      for it in r.json().get("items", [])])
    if j.empty:
        return pd.DataFrame(columns=["semaine", "page", "vues"])
    j["date"] = pd.to_datetime(j["date"], format="%Y%m%d")
    jours = pd.date_range(j["date"].min(), pd.Timestamp(hier()), freq="D")
    q = j.set_index("date")["vues"].reindex(jours)
    hebdo = (q.resample("W-SUN").mean() * 7).where(q.resample("W-SUN").count() >= 4).dropna()
    return pd.DataFrame({"semaine": [d.date().isoformat() for d in hebdo.index],
                         "page": page, "vues": hebdo.round().values})


def detecter_sujets(s) -> str:
    fin = pd.Timestamp(derniere_semaine_finie())
    top = lire("wiki_top.csv", dtype={"vues": float})
    hausse = pages_en_hausse(top, fin)
    suivies = {c.replace(" ", "_") for c in resolution_pages().values() if c}
    hausse = hausse[(hausse["ratio"] >= config.SUJETS_RATIO_MIN) &
                    (~hausse.index.isin(suivies))].head(60)
    if hausse.empty:
        return "sujets émergents : aucune page en forte hausse"
    cats = _categories(s, list(hausse.index))
    retenus = []
    for page, r in hausse.iterrows():
        c = classer(page, cats.get(page, []))
        if c:
            retenus.append({"semaine": fin.date().isoformat(), "page": page, "pilier": c[0],
                            "raison": c[1], "vues": int(r.vues), "ratio": round(float(r.ratio), 2)})
        if len(retenus) >= config.SUJETS_MAX:
            break
    fusionner(pd.DataFrame(retenus, columns=["semaine", "page", "pilier", "raison", "vues", "ratio"]),
              "sujets.csv", ["semaine", "page"], garder_jours=730, col_date="semaine")

    # historique hebdomadaire depuis 2015 des sujets retenus (pour « plus haut depuis… »)
    histo = lire("wiki_sujets.csv", dtype={"vues": float})
    derniere = histo.groupby("page")["semaine"].max().to_dict() if not histo.empty else {}
    nouveaux = []
    for r in retenus:
        p = r["page"]
        debut = (date.fromisoformat(derniere[p]) - timedelta(days=13) if p in derniere
                 else date.fromisoformat(config.WIKI_DEBUT))
        try:
            nouveaux.append(_historique_hebdo(s, p, debut))
        except Exception:
            continue
    tout = pd.concat([histo] + nouveaux, ignore_index=True) if nouveaux else histo
    if not tout.empty:
        # on n'archive que les sujets vus dans les 6 derniers mois
        sujets = lire("sujets.csv", dtype=str)
        recents = set(sujets[sujets["semaine"] >= (fin - pd.Timedelta(weeks=26)).date().isoformat()]["page"])
        tout = tout[tout["page"].isin(recents)].astype({"vues": float})
        tout = tout.drop_duplicates(["page", "semaine"], keep="last").sort_values(["page", "semaine"])
        tout.to_csv(DATA / "wiki_sujets.csv", index=False)
    return (f"sujets émergents : {len(hausse)} pages en forte hausse examinées, "
            f"{len(retenus)} retenues")


def resolution_pages() -> dict:
    return lire_json("wiki_pages.json", {}) or {}
