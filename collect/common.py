"""Outils partagés par les collecteurs : HTTP poli, stockage CSV, journal."""
from __future__ import annotations

import json
import os
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import requests

RACINE = Path(__file__).resolve().parent.parent
DATA = Path(os.environ.get("BAROMETRE_DATA", RACINE / "data"))
DATA.mkdir(parents=True, exist_ok=True)


def aujourdhui() -> date:
    """Date du jour (UTC) ; surchargeable pour les tests."""
    force = os.environ.get("BAROMETRE_AUJOURDHUI")
    if force:
        return date.fromisoformat(force)
    return datetime.now(timezone.utc).date()


def hier() -> date:
    return aujourdhui() - timedelta(days=1)


def session() -> requests.Session:
    s = requests.Session()
    depot = os.environ.get("GITHUB_REPOSITORY", "barometre-social")
    # Wikimedia demande un User-Agent identifiable
    s.headers["User-Agent"] = (
        f"BarometreSocial/1.0 (https://github.com/{depot}; projet personnel, open data)"
    )
    return s


class ErreurSource(RuntimeError):
    pass


def get(s: requests.Session, url: str, params=None, essais: int = 4,
        timeout: int = 90, accepter_404: bool = False, pause: float = 5.0):
    """GET avec nouvelles tentatives sur les erreurs passagères."""
    derniere = None
    for i in range(essais):
        try:
            r = s.get(url, params=params, timeout=timeout)
        except requests.RequestException as e:
            derniere = f"{type(e).__name__}: {e}"
        else:
            if r.status_code == 200:
                return r
            if r.status_code == 404 and accepter_404:
                return None
            if r.status_code in (429, 500, 502, 503, 504):
                derniere = f"HTTP {r.status_code}"
            else:
                raise ErreurSource(f"HTTP {r.status_code} sur {r.url[:150]}")
        time.sleep(min(60, pause * (2 ** i)))
    raise ErreurSource(f"échec après {essais} essais ({derniere}) sur {url[:150]}")


def lire(nom: str, **kw) -> pd.DataFrame:
    chemin = DATA / nom
    if not chemin.exists() or chemin.stat().st_size == 0:
        return pd.DataFrame()
    return pd.read_csv(chemin, **kw)


def fusionner(nouveau: pd.DataFrame, nom: str, cles: list[str],
              garder_jours: int | None = None, col_date: str = "date") -> pd.DataFrame:
    """Ajoute des lignes à un CSV existant (les plus récentes l'emportent)."""
    ancien = lire(nom, dtype=str)
    if not nouveau.empty:
        nouveau = nouveau.astype(str)
    tout = pd.concat([ancien, nouveau], ignore_index=True)
    if tout.empty:
        return tout
    tout = tout.drop_duplicates(subset=cles, keep="last")
    if garder_jours and col_date in tout:
        limite = (aujourdhui() - timedelta(days=garder_jours)).isoformat()
        tout = tout[tout[col_date] >= limite]
    tout = tout.sort_values(cles).reset_index(drop=True)
    tout.to_csv(DATA / nom, index=False)
    return tout


def ecrire_json(nom: str, contenu) -> None:
    (DATA / nom).write_text(json.dumps(contenu, ensure_ascii=False, indent=1),
                            encoding="utf-8")


def lire_json(nom: str, defaut=None):
    chemin = DATA / nom
    if not chemin.exists():
        return defaut
    return json.loads(chemin.read_text(encoding="utf-8"))
