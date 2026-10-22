"""Volet « État du pays » : derniers chiffres officiels, comparés à l'an dernier
(ou à il y a cinq ans pour les indicateurs de fond), avec un verdict simple."""
from __future__ import annotations

import re

import pandas as pd

import config
from collect.common import lire
from indicators import MOIS

VERDICTS = {"mieux": ("S'améliore", "good"), "stable": ("Stable", "none"),
            "moins bien": ("Se dégrade", "serious")}


def _date(periode: str) -> pd.Timestamp | None:
    p = str(periode)
    if re.fullmatch(r"\d{4}-\d{2}", p):
        return pd.Timestamp(p + "-01")
    m = re.fullmatch(r"(\d{4})-Q(\d)", p)
    if m:
        return pd.Timestamp(int(m.group(1)), 3 * int(m.group(2)) - 2, 1)
    if re.fullmatch(r"\d{4}", p):
        return pd.Timestamp(int(p), 1, 1)
    return None


def _frequence(periodes) -> str:
    p = str(periodes[0])
    return "M" if re.fullmatch(r"\d{4}-\d{2}", p) else ("T" if "Q" in p else "A")


def _fr(x, nd=1, signe=False):
    s = f"{x:+,.{nd}f}" if signe else f"{x:,.{nd}f}"
    return s.replace(",", " ").replace(".", ",").replace("-", "−")


def _libelle_periode(t: pd.Timestamp, freq: str, lissage: int = 1) -> str:
    if freq == "A":
        return str(t.year)
    if freq == "T":
        n = (t.month - 1) // 3 + 1
        return f"{n}{'er' if n == 1 else 'e'} trim. {t.year}"
    if lissage > 1:
        debut = t - pd.DateOffset(months=lissage - 1)
        return f"{MOIS[debut.month - 1]}-{MOIS[t.month - 1]} {t.year}"
    return f"{MOIS[t.month - 1]} {t.year}"


def _serie(df: pd.DataFrame, idbank) -> tuple[pd.Series, str] | None:
    ids = idbank if isinstance(idbank, list) else [idbank]
    morceaux = []
    for i in ids:
        d = df[df["idbank"] == i]
        if d.empty:
            return None
        morceaux.append(pd.Series(d["valeur"].values, index=d["date"].values).sort_index())
    s = pd.concat(morceaux, axis=1).dropna().mean(axis=1).sort_index()
    if s.empty:
        return None
    return s, _frequence(df[df["idbank"] == ids[0]]["periode"].tolist())


def _point_de_reference(s: pd.Series, t: pd.Timestamp, annees: int):
    """Valeur à la même période `annees` plus tôt (ou la plus proche, à un an près)."""
    cible = t - pd.DateOffset(years=annees)
    if cible in s.index:
        return cible
    proches = s.loc[cible - pd.DateOffset(years=1):cible + pd.DateOffset(years=1)]
    if proches.empty:
        return None
    return min(proches.index, key=lambda d: (abs((d - cible).days), d > cible))


def _moyenne(s: pd.Series, t: pd.Timestamp, n: int) -> float | None:
    fenetre = s.loc[t - pd.DateOffset(months=n - 1):t]
    return float(fenetre.mean()) if len(fenetre) == n else None


def _valeur_txt(v: float, ind: dict) -> str | None:
    u, nd = ind["unite"], ind.get("decimales", 1)
    if u == "indice":
        return None
    if u == "milliers":
        return f"{_fr(v / 1000, 2)} millions"
    if u == "nombre":
        return _fr(v, 0)
    if u in ("%", "% du PIB"):
        return f"{_fr(v, nd)} {u}"
    if u == "/10":
        return f"{_fr(v, 1)} / 10"
    return f"{_fr(v, nd)} {u}"


def _evol_txt(ecart: float, ind: dict, brut: float | None = None) -> str:
    u, nd = ind["unite"], ind.get("decimales", 1)
    if ind["mode"] == "taux":
        if u in ("%", "% du PIB"):
            return f"{_fr(ecart, nd, True)} pt"
        if u == "ans":
            return f"{_fr(ecart, 1, True)} an" + ("s" if abs(ecart) >= 2 else "")
        if u.startswith("t "):
            return f"{_fr(ecart, 1, True)} t"
        return _fr(ecart, nd, True)
    txt = f"{_fr(ecart, 1, True)} %"
    if u == "milliers" and brut is not None:
        txt += f" ({_fr(round(brut) * 1000, 0, True)} emplois)"
    return txt


def _sparkline(s: pd.Series, freq: str, lissage: int) -> list:
    if freq == "M" and lissage > 1:
        s = s.rolling(lissage).mean().dropna()
    s = s.iloc[-60:] if freq == "M" else (s.iloc[-20:] if freq == "T" else s.iloc[-12:])
    if s.empty:
        return []
    bas, haut = float(s.min()), float(s.max())
    if haut - bas < 1e-9:
        return [50.0] * len(s)
    return [round(10 + 80 * (float(v) - bas) / (haut - bas), 1) for v in s.values]


def _indicateur(ind: dict, df: pd.DataFrame, prix: pd.Series | None) -> dict:
    base = {"id": ind["id"], "libelle": ind["libelle"], "aide": ind.get("aide", ""),
            "section": ind["section"], "sous": ind.get("sous", False)}
    r = _serie(df, ind["idbank"])
    if r is None:
        return {**base, "dispo": False}
    s, freq = r
    lissage = ind.get("lissage", 1) if freq == "M" else 1
    horizon = ind.get("horizon", 1)
    t = s.index[-1]
    ref = _point_de_reference(s, t, horizon)
    if ref is None:
        return {**base, "dispo": False}
    if lissage > 1:
        cur, avant = _moyenne(s, t, lissage), _moyenne(s, ref, lissage)
    else:
        cur, avant = float(s[t]), float(s[ref])
    if cur is None or avant is None or (ind["mode"] != "taux" and avant == 0):
        return {**base, "dispo": False}

    euros = None
    if ind["mode"] == "taux":
        ecart = cur - avant
    else:
        ecart = 100 * (cur / avant - 1)
        if ind["mode"] == "ca":
            euros = ecart
            p_cur = _moyenne(prix, t, lissage) if prix is not None else None
            p_av = _moyenne(prix, ref, lissage) if prix is not None else None
            if not p_cur or not p_av:
                return {**base, "dispo": False}
            ecart = 100 * ((cur / avant) / (p_cur / p_av) - 1)
    if abs(ecart) < ind["seuil"]:
        verdict = "stable"
    else:
        verdict = "mieux" if ecart * ind["bon"] > 0 else "moins bien"

    if horizon == 1:
        ref_txt = "sur un an"
    else:
        ref_txt = f"depuis {_libelle_periode(ref, freq).replace('trim.', 'trimestre')}"
    court = _evol_txt(ecart, ind, brut=(cur - avant) if ind["unite"] == "milliers" else None)
    evol = court + (" hors hausse des prix" if ind["mode"] == "ca" else "")
    valeur = _valeur_txt(cur, ind)
    # le grand chiffre : la valeur quand elle parle d'elle-même, sinon l'évolution
    grand = valeur or court.split(" (")[0]
    if valeur:
        detail = f"{evol} {ref_txt}"
    else:
        detail = f"hors hausse des prix, {ref_txt}" if ind["mode"] == "ca" else ref_txt
    return {**base, "dispo": True, "periode": _libelle_periode(t, freq, lissage),
            "valeur": valeur, "grand": grand, "detail": detail, "evol": evol, "ref": ref_txt,
            "euros": None if euros is None else f"{_fr(euros, 1, True)} % en euros",
            "verdict": verdict, "statut": VERDICTS[verdict],
            "force": abs(ecart) / ind["seuil"], "sparkline": _sparkline(s, freq, lissage),
            "date": t.date().isoformat()}


def calculer_pays() -> dict | None:
    df = lire("pays.csv", dtype=str)
    if df.empty:
        return None
    df["valeur"] = pd.to_numeric(df["valeur"], errors="coerce")
    df["date"] = df["periode"].map(_date)
    df = df.dropna(subset=["valeur", "date"])
    p = df[df["idbank"] == config.PAYS_DEFLATEUR]
    prix = pd.Series(p["valeur"].values, index=p["date"].values).sort_index() if not p.empty else None

    tous = [_indicateur(ind, df, prix) for ind in config.PAYS]
    dispo = [i for i in tous if i["dispo"]]
    sections = [{"cle": k, "nom": nom, "indicateurs": [i for i in tous if i["section"] == k]}
                for k, nom in config.PAYS_SECTIONS.items()]
    for i in dispo:
        i["nom_complet"] = ("Chômage " + i["libelle"].lstrip("… ")) if i["sous"] else i["libelle"]
    mieux = sorted([i for i in dispo if i["verdict"] == "mieux"], key=lambda i: -i["force"])
    moins = sorted([i for i in dispo if i["verdict"] == "moins bien"], key=lambda i: -i["force"])
    stables = [i for i in dispo if i["verdict"] == "stable"]
    return {"sections": sections, "mieux": mieux, "moins": moins, "stables": stables,
            "n": len(dispo), "n_total": len(tous),
            "plus_recent": max((i["date"] for i in dispo), default=None)}
