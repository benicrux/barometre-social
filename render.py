"""Génère la page HTML du tableau de bord (un seul fichier, publié sur GitHub Pages)."""
from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from jinja2 import Environment, FileSystemLoader, Undefined, select_autoescape
from markupsafe import Markup

import config
from collect.common import RACINE
from indicators import MOIS

SORTIE = Path(os.environ.get("BAROMETRE_SORTIE", RACINE / "site"))


# --------------------------------------------------------------------------
# Filtres d'affichage
# --------------------------------------------------------------------------
def fr(x, nd=0, signe=False):
    if x is None or isinstance(x, Undefined):
        return "–"
    try:
        x = float(x)
    except (TypeError, ValueError):
        return str(x)
    s = f"{x:+,.{nd}f}" if signe else f"{x:,.{nd}f}"
    return s.replace(",", " ").replace(".", ",").replace("-", "−")


def sigma(z):
    return "–" if z is None else f"{fr(z, 1, signe=True)} σ"


def sparkline(valeurs, largeur=120, hauteur=32, ref=50):
    pts = [(i, v) for i, v in enumerate(valeurs or [])]
    if not any(v is not None for _, v in pts):
        return Markup("")
    n = max(len(pts) - 1, 1)
    def X(i): return 2 + i * (largeur - 6) / n
    def Y(v): return 3 + (100 - v) / 100 * (hauteur - 6)
    chemins, seg = [], []
    for i, v in pts:
        if v is None:
            if seg:
                chemins.append(seg)
            seg = []
        else:
            seg.append(f"{X(i):.1f},{Y(v):.1f}")
    if seg:
        chemins.append(seg)
    d = " ".join("M" + " L".join(s) for s in chemins)
    der = next(((i, v) for i, v in reversed(pts) if v is not None))
    texte = f"Évolution sur {len(pts)} semaines, dernière valeur {fr(der[1])}"
    svg = (f'<svg class="spark" viewBox="0 0 {largeur} {hauteur}" width="{largeur}" '
           f'height="{hauteur}" role="img" aria-label="{texte}">'
           f'<line x1="0" x2="{largeur}" y1="{Y(ref):.1f}" y2="{Y(ref):.1f}" class="spark-ref"/>'
           f'<path d="{d}" class="spark-ligne"/>'
           f'<circle cx="{X(der[0]):.1f}" cy="{Y(der[1]):.1f}" r="3.5" class="spark-point"/>'
           f"<title>{texte}</title></svg>")
    return Markup(svg)


def couleur_cellule(score):
    """Fond divergent bleu (calme) ↔ rouge (tension), gris au milieu (50)."""
    if score is None:
        return Markup('style="background:transparent"')
    t = max(-1.0, min(1.0, (score - 50) / 50))
    pole = "var(--pole-tension)" if t > 0 else "var(--pole-calme)"
    part = round(abs(t) ** 0.8 * 85)
    encre = "#ffffff" if part > 48 else "var(--encre-1)"
    return Markup(f'style="background:color-mix(in oklab, {pole} {part}%, var(--neutre));'
                  f'color:{encre}"')


ICONES = {
    "good": '<svg viewBox="0 0 16 16" aria-hidden="true"><circle cx="8" cy="8" r="7"/>'
            '<path d="M4.5 8.2l2.3 2.3 4.7-4.8" class="ic-trait"/></svg>',
    "warning": '<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M8 1.5l7 12.5H1z"/>'
               '<path d="M8 6v4M8 11.8v.4" class="ic-trait"/></svg>',
    "serious": '<svg viewBox="0 0 16 16" aria-hidden="true"><circle cx="8" cy="8" r="7"/>'
               '<path d="M8 4.2v4.6M8 11.2v.4" class="ic-trait"/></svg>',
    "critical": '<svg viewBox="0 0 16 16" aria-hidden="true">'
                '<path d="M5 1h6l4 4v6l-4 4H5l-4-4V5z"/>'
                '<path d="M5.6 5.6l4.8 4.8M10.4 5.6l-4.8 4.8" class="ic-trait"/></svg>',
    "none": '<svg viewBox="0 0 16 16" aria-hidden="true"><circle cx="8" cy="8" r="7"/></svg>',
}


def puce(statut):
    libelle, niveau = statut if statut else ("Indisponible", "none")
    return Markup(f'<span class="puce puce-{niveau}">{ICONES[niveau]}'
                  f"<span>{libelle}</span></span>")


def delta(v, suffixe=""):
    if v is None:
        return Markup('<span class="delta">–</span>')
    if abs(v) < 0.5:
        return Markup(f'<span class="delta">= stable{suffixe}</span>')
    cls = "delta-mauvais" if v > 0 else "delta-bon"
    fleche = "▲" if v > 0 else "▼"
    return Markup(f'<span class="delta {cls}">{fleche} {fr(v, 0, True)}{suffixe}</span>')


# --------------------------------------------------------------------------
def generer(ind: dict, prev: dict, statuts: list[dict]) -> Path:
    env = Environment(loader=FileSystemLoader(RACINE / "templates"),
                      autoescape=select_autoescape(["html", "j2"]))
    env.filters.update(fr=fr, sigma=sigma, sparkline=sparkline, puce=puce,
                       delta=delta, cellule=couleur_cellule)
    maintenant = datetime.now(ZoneInfo("Europe/Paris"))
    calcule = (f"{maintenant.day} {MOIS[maintenant.month - 1]} {maintenant.year} "
               f"à {maintenant:%H} h {maintenant:%M}")
    donnees_js = {
        "historique": ind["historique"],
        "decisions": ind["decisions"],
        "carte": ind["carte"],
        "piliers": {"meteo": "Météo sociale", **config.PILIERS},
    }
    html = env.get_template("tableau.html.j2").render(
        ind=ind, prev=prev, statuts=statuts, calcule=calcule,
        piliers_noms=config.PILIERS, donnees_js=donnees_js,
        min_hist=config.MIN_HISTORIQUE,
        demo=bool(os.environ.get("BAROMETRE_DEMO")),
        depot=os.environ.get("GITHUB_REPOSITORY", ""),
    )
    SORTIE.mkdir(parents=True, exist_ok=True)
    chemin = SORTIE / "index.html"
    chemin.write_text(html, encoding="utf-8")
    (SORTIE / ".nojekyll").write_text("", encoding="utf-8")
    return chemin
