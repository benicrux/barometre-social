"""Transforme les données brutes en indicateurs hebdomadaires comparables.

Principe : chaque série est comparée à ses deux années précédentes (écart en σ,
« z-score »), orientée pour que + = plus de tension, puis moyennée par jauge.
Un score 0-100 s'en déduit : 50 = semaine normale, 73 ≈ +1σ, 88 ≈ +2σ.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

import config
from collect import wikipedia
from collect.common import RACINE, aujourdhui, lire

MOIS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août",
        "septembre", "octobre", "novembre", "décembre"]
MOIS_COURT = ["janv.", "févr.", "mars", "avr.", "mai", "juin", "juil.", "août",
              "sept.", "oct.", "nov.", "déc."]


# --------------------------------------------------------------------------
# Outils
# --------------------------------------------------------------------------
def phi(z: float) -> float:
    return 0.5 * (1 + math.erf(z / math.sqrt(2)))


def vers_score(z):
    """Écart en σ -> score 0-100 : 50 = normal, 73 ≈ +1σ, 88 ≈ +2σ, 95 ≈ +3σ.

    L'échelle est volontairement douce pour garder de la nuance pendant les
    crises (une loi normale saturerait à 100 dès +3σ).
    """
    if z is None or (isinstance(z, float) and math.isnan(z)):
        return None
    return float(round(50 + 50 * math.tanh(float(z) / 2), 0))


def statut(score):
    if score is None:
        return ("Indisponible", "none")
    for seuil, libelle, niveau in config.SEUILS:
        if score >= seuil:
            return (libelle, niveau)
    return ("Calme", "good")


def zscore(serie: pd.Series, fenetre: int, minimum: int) -> pd.Series:
    """Écart à la moyenne des `fenetre` périodes précédentes, en écarts-types."""
    base = serie.shift(1).rolling(fenetre, min_periods=minimum)
    ecart = base.std().where(lambda x: x > 1e-9)
    return ((serie - base.mean()) / ecart).replace([np.inf, -np.inf], np.nan)


def fin_de_semaine(d) -> pd.Timestamp:
    d = pd.Timestamp(d).normalize()
    return d + pd.Timedelta(days=6 - d.weekday())


def derniere_semaine() -> pd.Timestamp:
    """Dernier dimanche strictement passé (semaine complète)."""
    hier = pd.Timestamp(aujourdhui()) - pd.Timedelta(days=1)
    return hier - pd.Timedelta(days=(hier.weekday() + 1) % 7)


def hebdo(journalier: pd.DataFrame, fin: pd.Timestamp, minimum_jours=4,
          somme=True) -> pd.DataFrame:
    """Journalier -> hebdomadaire (lundi-dimanche) ; jours manquants tolérés."""
    if journalier.empty:
        return journalier
    jours = pd.date_range(journalier.index.min(), fin, freq="D")
    j = journalier.reindex(jours)
    moy = j.resample("W-SUN").mean()
    nb = j.resample("W-SUN").count()
    sortie = (moy * 7) if somme else moy
    return sortie.where(nb >= minimum_jours)


def libelle_semaine(fin: pd.Timestamp) -> str:
    debut = fin - pd.Timedelta(days=6)
    if debut.month == fin.month:
        return f"du {debut.day} au {fin.day} {MOIS[fin.month - 1]} {fin.year}"
    return (f"du {debut.day} {MOIS[debut.month - 1]} au {fin.day} "
            f"{MOIS[fin.month - 1]} {fin.year}")


def libelle_mois(ts) -> str:
    ts = pd.Timestamp(ts)
    return f"{MOIS_COURT[ts.month - 1]} {ts.year}"


def _f(x, nd=2):
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return None
    return round(float(x), nd)


# --------------------------------------------------------------------------
# Construction des composantes
# --------------------------------------------------------------------------
class Composante:
    def __init__(self, id, pilier, libelle, source, z, affichage, historique,
                 brut=None, ratio=True, mensuel=None, bas=True):
        self.id, self.pilier, self.libelle, self.source = id, pilier, libelle, source
        self.z = z                    # série hebdo orientée (+ = tension)
        self.affichage = affichage    # série hebdo de textes lisibles
        self.historique = historique  # nb de semaines de données
        self.brut = brut              # valeurs brutes hebdo (pour « vs normale » et « niveau »)
        self.ratio = ratio            # un écart en % a-t-il un sens ? (non pour un solde ou un ton)
        self.mensuel = mensuel        # série mensuelle brute (INSEE)
        self.bas = bas                # un creux est-il remarquable ? (non pour Wikipédia,
                                      # dont l'audience baisse d'année en année)


# --------------------------------------------------------------------------
# Traduction en clair : « vs normale » (%) et niveau en mots
# --------------------------------------------------------------------------
def vs_normale(brut, fin, fenetre=None):
    """Écart en % entre la semaine et la médiane des deux années précédentes."""
    if brut is None:
        return None
    s = brut.loc[:fin].dropna()
    if len(s) <= config.MIN_HISTORIQUE or s.index[-1] != fin:
        return None
    mediane = s.iloc[:-1].tail(fenetre or config.FENETRE_SEMAINES).median()
    if pd.isna(mediane) or mediane <= 0:
        return None
    return _f(100 * (s.iloc[-1] / mediane - 1), 0)


def niveau(brut, fin=None, fenetre=None, recent=None, minimum=None, bas=True):
    """Situe la dernière valeur en mots : « plus haut depuis mars 2023 », etc."""
    if brut is None:
        return None
    s = brut.dropna()
    if fin is not None:
        s = s.loc[:fin]
        if s.empty or s.index[-1] != fin:
            return None
    if len(s) <= (minimum or config.MIN_HISTORIQUE):
        return None
    v, passe = s.iloc[-1], s.iloc[:-1]
    fen = passe.tail(fenetre or config.FENETRE_SEMAINES)
    plus_bas = 100 * (fen < v).mean()   # part du temps où c'était plus bas
    plus_haut = 100 * (fen > v).mean()
    limite = s.index[-1] - (recent or pd.Timedelta(weeks=26))
    if plus_bas >= 90:
        avant = passe[passe >= v]
        if avant.empty:
            return f"record (données depuis {passe.index[0].year})"
        if avant.index[-1] < limite:
            return f"plus haut depuis {libelle_mois(avant.index[-1])}"
        return "nettement au-dessus de la normale"
    if plus_haut >= 90:
        if not bas:
            return "nettement en dessous de la normale"
        avant = passe[passe <= v]
        if avant.empty:
            return f"plus bas jamais mesuré (depuis {passe.index[0].year})"
        if avant.index[-1] < limite:
            return f"plus bas depuis {libelle_mois(avant.index[-1])}"
        return "nettement en dessous de la normale"
    if plus_bas >= 75:
        return "au-dessus de la normale"
    if plus_haut >= 75:
        return "en dessous de la normale"
    return "dans la normale"


def _niveau_composante(c, fin):
    if c.mensuel is not None:
        m = c.mensuel.dropna()
        m = m[m.index + pd.Timedelta(days=26) <= fin]  # mois déjà publiés
        return niveau(m, fenetre=config.FENETRE_MOIS, recent=pd.DateOffset(months=6),
                      minimum=config.MIN_HISTORIQUE_MOIS)
    return niveau(c.brut, fin, bas=c.bas)


def _wiki(fin, semaines):
    comps, pages_detail = [], {}
    df = lire("wikipedia.csv", dtype={"vues": float})
    if df.empty:
        return comps, pages_detail, pd.DataFrame()
    df["date"] = pd.to_datetime(df["date"])
    piv = df.pivot_table(index="date", columns="page", values="vues", aggfunc="sum")
    vues = hebdo(piv, fin).reindex(semaines)
    zpage = pd.DataFrame({p: zscore(np.log1p(vues[p]), config.FENETRE_SEMAINES,
                                     config.MIN_HISTORIQUE) for p in vues.columns})
    resolution = wikipedia.resolution_pages()
    paniers = {}
    for pilier, titres in config.WIKI_PAGES.items():
        pages = [resolution.get(t) or t for t in titres]
        pages = [p for p in dict.fromkeys(pages) if p in vues.columns]
        if not pages:
            continue
        brut = zpage[pages].clip(-4, 6).mean(axis=1)
        z = zscore(brut, config.FENETRE_SEMAINES, config.MIN_HISTORIQUE)
        total = vues[pages].sum(axis=1, min_count=1)
        aff = total.map(lambda v: f"{v:,.0f} vues".replace(",", " ")
                        if pd.notna(v) else "")
        comps.append(Composante(f"wiki_{pilier}", pilier,
                                f"Intérêt sur Wikipédia ({len(pages)} pages)", "Wikipédia",
                                z, aff, int(total.notna().sum()), brut=total, bas=False))
        paniers[pilier] = brut
        pages_detail[pilier] = pages
    return comps, pages_detail, (vues, zpage, pd.DataFrame(paniers))


def _insee(semaines):
    comps, mensuel = [], pd.DataFrame()
    df = lire("insee.csv", dtype={"valeur": float})
    if df.empty:
        return comps, mensuel
    df["date"] = pd.to_datetime(df["date"])
    mensuel = df.pivot_table(index="date", columns="serie", values="valeur").sort_index()
    cible = pd.DataFrame({"semaine": semaines})
    for cle, spec in config.INSEE_SERIES.items():
        if cle not in mensuel:
            continue
        s = mensuel[cle].dropna()
        z = zscore(s, config.FENETRE_MOIS, config.MIN_HISTORIQUE_MOIS) * spec["sens"]
        # publication vers la fin du mois concerné
        m = pd.DataFrame({"dispo": s.index + pd.Timedelta(days=26), "z": z.values,
                          "valeur": s.values, "mois": s.index}).sort_values("dispo")
        j = pd.merge_asof(cible, m, left_on="semaine", right_on="dispo")
        aff = [f"{v:g} ({libelle_mois(mo)})" if pd.notna(v) else ""
               for v, mo in zip(j["valeur"], j["mois"])]
        comps.append(Composante(f"insee_{cle}", spec["pilier"], spec["libelle"], "INSEE",
                                pd.Series(j["z"].values, index=semaines),
                                pd.Series(aff, index=semaines), int(s.size),
                                ratio=False, mensuel=s))
    return comps, mensuel


def _gdelt(fin, semaines):
    comps = []
    presse = lire("gdelt_presse.csv", dtype={"valeur": float})
    if not presse.empty:
        presse["date"] = pd.to_datetime(presse["date"])
        piv = presse.pivot_table(index="date", columns="serie", values="valeur")
        sem = hebdo(piv, fin, somme=False).reindex(semaines)
        for cle, spec in config.GDELT_REQUETES.items():
            if cle not in sem:
                continue
            s = sem[cle]
            z = zscore(np.log(s.where(s > 0)), config.FENETRE_SEMAINES, config.MIN_HISTORIQUE)
            aff = s.map(lambda v: f"{100 * v:.2f} % des articles".replace(".", ",")
                        if pd.notna(v) else "")
            comps.append(Composante(f"gdelt_{cle}", spec["pilier"], spec["libelle"],
                                    "GDELT (presse)", z * spec["sens"], aff,
                                    int(s.notna().sum()), brut=s))
    evt = lire("gdelt_evenements.csv")
    types = pd.DataFrame()
    if not evt.empty:
        evt["date"] = pd.to_datetime(evt["date"])
        evt = evt.set_index("date").sort_index().apply(pd.to_numeric, errors="coerce")
        sem = hebdo(evt, fin).reindex(semaines)
        s = sem["total"]
        z = zscore(np.log1p(s), config.FENETRE_SEMAINES, config.MIN_HISTORIQUE)
        aff = s.map(lambda v: f"{v:,.0f} actions".replace(",", " ") if pd.notna(v) else "")
        spec = config.GDELT_EVENEMENTS
        comps.append(Composante("gdelt_evenements", spec["pilier"], spec["libelle"],
                                "GDELT", z * spec["sens"], aff, int(s.notna().sum()), brut=s))
        types = sem
        if "fr_articles" in sem:
            base = sem["fr_articles"].where(sem["fr_articles"] > 0)
            # part des articles consacrés à la contestation, parmi toute l'actualité en France
            part = sem["articles"] / base
            z = zscore(np.log(part.where(part > 0)), config.FENETRE_SEMAINES,
                       config.MIN_HISTORIQUE)
            aff = part.map(lambda v: f"{100 * v:.1f} % de l'actualité".replace(".", ",")
                           if pd.notna(v) else "")
            spec = config.GDELT_PART
            comps.append(Composante("gdelt_part", spec["pilier"], spec["libelle"], "GDELT",
                                    z * spec["sens"], aff, int(part.notna().sum()), brut=part))
            # tonalité moyenne des articles (négatif = actualité plus sombre)
            if "fr_ton" in sem:
                ton = sem["fr_ton"] / base
                z = zscore(ton, config.FENETRE_SEMAINES, config.MIN_HISTORIQUE)
                aff = ton.map(lambda v: f"ton {v:+.2f}".replace(".", ",").replace("-", "−")
                              if pd.notna(v) else "")
                spec = config.GDELT_TON
                comps.append(Composante("gdelt_ton", spec["pilier"], spec["libelle"], "GDELT",
                                        z * spec["sens"], aff, int(ton.notna().sum()),
                                        brut=ton, ratio=False))
    return comps, types


def _carburants(semaines):
    df = lire("carburants.csv")
    if df.empty:
        return []
    df["date"] = pd.to_datetime(df["date"])
    df["semaine"] = (df["date"] - pd.Timedelta(days=1)).map(fin_de_semaine)
    df = df.sort_values("date").groupby("semaine").last().reindex(semaines)
    zs, aff = [], pd.Series("", index=semaines)
    for cle in config.CARBURANTS:
        if cle in df:
            prix = pd.to_numeric(df[cle], errors="coerce")
            zs.append(zscore(np.log(prix), config.FENETRE_SEMAINES, config.MIN_HISTORIQUE))
    if not zs:
        return []
    z = pd.concat(zs, axis=1).mean(axis=1)
    g = pd.to_numeric(df.get("gazole"), errors="coerce") if "gazole" in df else None
    e = pd.to_numeric(df.get("e10"), errors="coerce") if "e10" in df else None
    for t in semaines:
        morceaux = []
        if g is not None and pd.notna(g.get(t)):
            morceaux.append(f"gazole {g[t]:.2f} €".replace(".", ","))
        if e is not None and pd.notna(e.get(t)):
            morceaux.append(f"E10 {e[t]:.2f} €".replace(".", ","))
        aff[t] = " · ".join(morceaux)
    n = int((aff != "").sum())
    prix_moyen = pd.concat([pd.to_numeric(df[c], errors="coerce")
                            for c in config.CARBURANTS if c in df], axis=1).mean(axis=1)
    return [Composante("carburants", "pouvoir_achat", "Prix à la pompe", "Carburants",
                       z, aff, n, brut=prix_moyen)]


# --------------------------------------------------------------------------
# Synthèse
# --------------------------------------------------------------------------
def _sparkline(serie: pd.Series, n=26):
    s = serie.tail(n)
    return [None if pd.isna(v) else float(v) for v in s]


def _variation(serie: pd.Series, decalage: int):
    s = serie.dropna()
    if len(s) <= decalage:
        return None
    return _f(s.iloc[-1] - s.iloc[-1 - decalage], 0)


def _montent(fin: pd.Timestamp):
    res = wikipedia.pages_en_hausse(lire("wiki_top.csv", dtype={"vues": float}), fin).head(8)
    return [{"titre": p.replace("_", " "), "url": f"https://fr.wikipedia.org/wiki/{p}",
             "vues": int(r.vues), "ratio": _f(r.ratio, 1)} for p, r in res.iterrows()]


def _sujets(fin: pd.Timestamp):
    """Sujets émergents détectés cette semaine, situés dans leur histoire."""
    suj = lire("sujets.csv", dtype=str)
    if suj.empty:
        return None  # détection jamais lancée
    cour = suj[suj["semaine"] == fin.date().isoformat()]
    histo = lire("wiki_sujets.csv", dtype={"vues": float})
    recent = (fin - pd.Timedelta(weeks=8)).date().isoformat()
    sortie = []
    for _, r in cour.iterrows():
        page = r["page"]
        serie = pd.Series(dtype=float)
        if not histo.empty:
            h = histo[histo["page"] == page]
            serie = pd.Series(h["vues"].values, index=pd.to_datetime(h["semaine"])).sort_index()
        serie = serie.loc[:fin]
        if serie.notna().sum() > config.MIN_HISTORIQUE:
            situation = niveau(serie, fin, bas=False)
        else:
            situation = "page récente ou peu lue jusqu'ici"
        deux_ans = serie.tail(104)
        maxi = deux_ans.max() if not deux_ans.empty else None
        spark = ([None if pd.isna(v) else float(100 * v / maxi) for v in deux_ans]
                 if maxi and maxi > 0 else [])
        sortie.append({
            "titre": page.replace("_", " "), "url": f"https://fr.wikipedia.org/wiki/{page}",
            "cle": r["pilier"], "pilier": config.PILIERS.get(r["pilier"], r["pilier"]),
            "raison": r["raison"], "vues": int(float(r["vues"])), "ratio": _f(float(r["ratio"]), 1),
            "niveau": situation, "spark": spark,
            "semaines": int(suj[(suj["page"] == page) & (suj["semaine"] >= recent)]["semaine"].nunique()),
        })
    return sorted(sortie, key=lambda x: -(x["ratio"] or 0))


def _carte(fin: pd.Timestamp):
    lieux = lire("gdelt_lieux.csv")
    if lieux.empty:
        return []
    lieux["date"] = pd.to_datetime(lieux["date"])
    l = lieux[(lieux["date"] > fin - pd.Timedelta(days=7)) & (lieux["date"] <= fin)]
    if l.empty:
        return []
    l = l.assign(n=pd.to_numeric(l["n"], errors="coerce"),
                 lat=pd.to_numeric(l["lat"], errors="coerce"),
                 lon=pd.to_numeric(l["lon"], errors="coerce"))
    g = l.groupby("lieu").agg(n=("n", "sum"), lat=("lat", "first"), lon=("lon", "first"))
    g = g.dropna().sort_values("n", ascending=False).head(80)
    return [{"lieu": k.replace(", France", ""), "n": int(r.n), "lat": float(r.lat),
             "lon": float(r.lon)} for k, r in g.iterrows()]


def _types(types: pd.DataFrame, fin):
    if types.empty or fin not in types.index:
        return []
    noms = list(config.GDELT_TYPES.values())
    sortie = []
    for nom in noms:
        if nom not in types:
            continue
        s = types[nom]
        cour = s.get(fin)
        avant = s.loc[:fin].iloc[-5:-1].mean()
        sortie.append({"nom": nom, "valeur": None if pd.isna(cour) else int(round(cour)),
                       "moyenne": None if pd.isna(avant) else int(round(avant))})
    return sortie


def _decisions(debut, fin):
    chemin = RACINE / "decisions.csv"
    if not chemin.exists():
        return []
    df = pd.read_csv(chemin, comment="#", dtype=str).dropna(subset=["date"])
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = df.dropna(subset=["date"]).sort_values("date")
    df = df[(df["date"] >= debut) & (df["date"] <= fin)]
    return [{"date": d.date().isoformat(), "semaine": fin_de_semaine(d).date().isoformat(),
             "texte": str(t), "type": str(ty) if pd.notna(ty) else ""}
            for d, t, ty in zip(df["date"], df["evenement"], df.get("type", [None] * len(df)))]


def calculer() -> dict:
    fin = derniere_semaine()
    semaines = pd.date_range(pd.Timestamp(config.WIKI_DEBUT), fin, freq="W-SUN")

    comps, pages_par_pilier, wiki_brut = _wiki(fin, semaines)
    c_insee, insee_mensuel = _insee(semaines)
    c_gdelt, types = _gdelt(fin, semaines)
    comps += c_insee + c_gdelt + _carburants(semaines)

    # Jauges
    piliers, scores, zpiliers = {}, pd.DataFrame(index=semaines), pd.DataFrame(index=semaines)
    for cle, nom in config.PILIERS.items():
        cs = [c for c in comps if c.pilier == cle]
        if not cs:
            piliers[cle] = {"cle": cle, "nom": nom, "score": None, "statut": statut(None),
                            "composantes": [], "moteurs": [], "sparkline": [],
                            "delta1": None, "delta4": None}
            scores[cle] = np.nan
            continue
        brut = pd.concat([c.z.clip(-4, 4) for c in cs], axis=1).mean(axis=1)
        # la moyenne de plusieurs indicateurs écrase les écarts : on la remet à l'échelle
        z = brut if len(cs) == 1 else zscore(
            brut, config.FENETRE_SEMAINES, config.MIN_HISTORIQUE).fillna(brut)
        z = z.clip(-4, 4)
        zpiliers[cle] = z
        scores[cle] = z.map(vers_score)
        details = []
        for c in cs:
            zf = c.z.get(fin)
            details.append({
                "libelle": c.libelle, "source": c.source,
                "valeur": c.affichage.get(fin, "") or "",
                "z": _f(zf), "historique": c.historique,
                "court": c.historique < 52,
                "actif": zf is not None and not pd.isna(zf),
                "niveau": _niveau_composante(c, fin),
                "vs": vs_normale(c.brut, fin) if c.ratio else None,
            })
        details.sort(key=lambda d: -(d["z"] if d["z"] is not None else -99))
        sc = scores[cle].get(fin)
        sc = None if pd.isna(sc) else sc
        piliers[cle] = {
            "cle": cle, "nom": nom, "score": sc, "statut": statut(sc),
            "delta1": _variation(scores[cle].loc[:fin], 1),
            "delta4": _variation(scores[cle].loc[:fin], 4),
            "sparkline": _sparkline(scores[cle].loc[:fin]),
            "composantes": details,
            "moteurs": [d for d in details if d["actif"] and d["z"] >= 0.5][:2],
        }

    # Météo sociale : moyenne des jauges, re-standardisée
    brut = zpiliers.clip(-4, 4).mean(axis=1)
    zm = zscore(brut, config.FENETRE_SEMAINES, config.MIN_HISTORIQUE).fillna(brut).clip(-4, 4)
    meteo = zm.map(vers_score)
    sc = meteo.get(fin)
    sc = None if pd.isna(sc) else sc

    # Voyants : composantes et pages à plus de 2σ
    voyants = []
    for c in comps:
        z = c.z.get(fin)
        if z is not None and pd.notna(z) and abs(z) >= config.SEUIL_VOYANT:
            voyants.append({"libelle": c.libelle, "pilier": config.PILIERS[c.pilier],
                            "z": _f(z), "valeur": c.affichage.get(fin, ""),
                            "sens": "hausse" if z > 0 else "baisse",
                            "niveau": _niveau_composante(c, fin),
                            "vs": vs_normale(c.brut, fin) if c.ratio else None})
    pages_suivies = []
    if isinstance(wiki_brut, tuple):
        vues, zpage, _ = wiki_brut
        for pilier, pages in pages_par_pilier.items():
            for p in pages:
                v = vues[p].get(fin)
                avant = vues[p].loc[:fin].iloc[-5:-1].mean()
                z = zpage[p].get(fin)
                ligne = {"page": p, "pilier": config.PILIERS[pilier],
                         "url": f"https://fr.wikipedia.org/wiki/{p.replace(' ', '_')}",
                         "vues": None if pd.isna(v) else int(v),
                         "evol": None if pd.isna(v) or pd.isna(avant) or avant == 0
                         else _f(100 * (v / avant - 1), 0),
                         "z": _f(z),
                         "vs": vs_normale(vues[p], fin),
                         "niveau": niveau(vues[p], fin, bas=False)}
                pages_suivies.append(ligne)
                if z is not None and pd.notna(z) and z >= config.SEUIL_VOYANT + 0.5:
                    voyants.append({"libelle": f"Wikipédia « {p} »",
                                    "pilier": config.PILIERS[pilier], "z": _f(z),
                                    "valeur": f"{int(v):,} vues".replace(",", " ")
                                    if pd.notna(v) else "", "sens": "hausse",
                                    "niveau": ligne["niveau"], "vs": ligne["vs"]})
    voyants.sort(key=lambda v: -abs(v["z"]))
    for cle, p in piliers.items():
        if p.get("delta1") is not None and p["delta1"] >= 15:
            voyants.insert(0, {"libelle": f"Jauge « {p['nom']} » : +{p['delta1']:.0f} points "
                               "en une semaine", "pilier": p["nom"], "z": None,
                               "valeur": "", "sens": "hausse"})

    # Historique (2 ans) et vue mensuelle (12 mois)
    debut_hist = fin - pd.Timedelta(weeks=104)
    hist = pd.concat([meteo.rename("meteo"), scores], axis=1).loc[debut_hist:fin]
    historique = [{"semaine": t.date().isoformat(),
                   **{k: (None if pd.isna(v) else float(v)) for k, v in row.items()}}
                  for t, row in hist.iterrows()]
    mens = pd.concat([meteo.rename("meteo"), scores], axis=1).loc[:fin]
    mens = mens.resample("MS").mean().tail(12)
    mensuel = [{"mois": libelle_mois(t), "en_cours": t.month == fin.month and t.year == fin.year
                and fin.day < 28,
                **{k: (None if pd.isna(v) else round(float(v))) for k, v in row.items()}}
               for t, row in mens.iterrows()]

    return {
        "fin": fin.date().isoformat(),
        "semaine": libelle_semaine(fin),
        "meteo": {"score": sc, "statut": statut(sc),
                  "delta1": _variation(meteo.loc[:fin], 1),
                  "delta4": _variation(meteo.loc[:fin], 4),
                  "sparkline": _sparkline(meteo.loc[:fin])},
        "piliers": list(piliers.values()),
        "voyants": voyants[:12],
        "montent": _montent(fin),
        "sujets": _sujets(fin),
        "pages_suivies": pages_suivies,
        "carte": _carte(fin),
        "types": _types(types, fin),
        "historique": historique,
        "mensuel": mensuel,
        "decisions": _decisions(debut_hist, fin + pd.Timedelta(days=7)),
        # pour la prévision
        "_wiki_paniers": wiki_brut[2] if isinstance(wiki_brut, tuple) else pd.DataFrame(),
        "_insee": insee_mensuel,
        "_fin": fin,
    }

