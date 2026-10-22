"""Exploration ponctuelle des sources du volet « État du pays » (lancée sur GitHub)."""
import io, json, re, sys, time, unicodedata
import xml.etree.ElementTree as ET
from pathlib import Path
import requests

OUT = Path("exploration"); OUT.mkdir(exist_ok=True)
s = requests.Session()
s.headers["User-Agent"] = "barometre-social exploration (github.com/benicrux/barometre-social)"

def sa(t): return unicodedata.normalize("NFKD", t).encode("ascii", "ignore").decode().lower()
def log(nom, texte): (OUT / nom).write_text(texte, encoding="utf-8")
def get(url, **kw):
    try:
        r = s.get(url, timeout=kw.pop("timeout", 60), **kw)
        return r
    except Exception as e:
        return e

# 1. Liste des jeux INSEE BDM
r = get("https://bdm.insee.fr/series/sdmx/dataflow")
flows = []
if isinstance(r, requests.Response) and r.ok:
    root = ET.fromstring(r.content)
    for df in root.iter():
        if df.tag.endswith("Dataflow"):
            nom = ""
            for n in df:
                if n.tag.endswith("Name") and n.attrib.get("{http://www.w3.org/XML/1998/namespace}lang") == "fr":
                    nom = n.text or ""
            flows.append((df.attrib.get("id"), nom))
    log("insee_dataflows.tsv", "\n".join(f"{i}\t{n}" for i, n in flows))
else:
    log("insee_dataflows.tsv", f"ERREUR {r}")

MOTS = ["prix", "consommation", "chiffre d'affaires", "services", "restaur", "tourisme", "hotel", "hebergement",
        "creation", "defaillance", "chomage", "emploi", "production", "esperance", "deces", "naissance",
        "demograph", "salaire", "revenu", "pauvrete", "epargne", "commerce", "immatriculation", "logement",
        "construction", "energie", "cinema", "pib", "comptes"]
cands = [(i, n) for i, n in flows if any(m in sa(n) for m in MOTS)]
log("insee_candidats.tsv", "\n".join(f"{i}\t{n}" for i, n in cands))

# 2. Titres des séries des jeux candidats (dernière observation seulement)
resume = []
for i, n in cands:
    r = get(f"https://bdm.insee.fr/series/sdmx/data/{i}", params={"lastNObservations": "1"}, timeout=120)
    if not isinstance(r, requests.Response) or not r.ok:
        resume.append(f"{i}\tERREUR {getattr(r, 'status_code', r)}")
        continue
    lignes = []
    try:
        for ev, el in ET.iterparse(io.BytesIO(r.content), events=("end",)):
            if el.tag.split("}")[-1] == "Series":
                a = el.attrib
                obs = [(o.attrib.get("TIME_PERIOD"), o.attrib.get("OBS_VALUE")) for o in el if o.tag.split("}")[-1] == "Obs"]
                lignes.append("\t".join([a.get("IDBANK", ""), a.get("FREQ", ""), a.get("CORRECTION", ""),
                                         (obs[-1][0] if obs else ""), (obs[-1][1] if obs else ""), a.get("TITLE_FR", "")]))
                el.clear()
    except Exception as e:
        lignes.append(f"ERREUR XML {e}")
    (OUT / "series").mkdir(exist_ok=True)
    log(f"series/{i}.tsv", "\n".join(lignes))
    resume.append(f"{i}\t{len(lignes)} séries\t{n}")
    time.sleep(1)
log("insee_resume.tsv", "\n".join(resume))

# 3. BODACC (Opendatasoft)
B = "https://bodacc-datadila.opendatasoft.com/api/explore/v2.1/catalog/datasets/annonces-commerciales"
sortie = {}
for nom, url, params in [
    ("info", B, {}),
    ("exemple", B + "/records", {"limit": 2}),
    ("familles", B + "/records", {"select": "familleavis_lib, count(*) as n", "group_by": "familleavis_lib", "limit": 50}),
    ("par_mois", B + "/records", {"select": "date_format(dateparution, 'yyyy-MM') as mois, familleavis_lib, count(*) as n",
                                  "group_by": "mois, familleavis_lib", "where": "dateparution >= date'2025-09-01'", "limit": 200}),
    ("par_semaine", B + "/records", {"select": "date_format(dateparution, 'YYYY-ww') as sem, count(*) as n",
                                     "group_by": "sem", "where": "familleavis_lib = 'Procédures collectives' and dateparution >= date'2026-08-01'", "limit": 100}),
    ("export_csv_test", B + "/exports/csv", {"select": "dateparution, familleavis_lib, numerodepartement", "where": "dateparution = date'2026-10-01'", "limit": 5}),
]:
    r = get(url, params=params)
    sortie[nom] = (r.text[:6000] if isinstance(r, requests.Response) else f"ERREUR {r}")
    sortie[nom + "_code"] = getattr(r, "status_code", None)
log("bodacc.json", json.dumps(sortie, ensure_ascii=False, indent=1))

# 4. data.gouv : CNC cinéma, nouveaux indicateurs de richesse, fréquentation
dg = {}
for q in ["fréquentation cinématographique", "entrées cinéma mensuelles", "nouveaux indicateurs de richesse",
          "fréquentation hôtelière", "chiffre d'affaires restauration"]:
    r = get("https://www.data.gouv.fr/api/1/datasets/", params={"q": q, "page_size": 8})
    if isinstance(r, requests.Response) and r.ok:
        dg[q] = [{"titre": d["title"], "org": (d.get("organization") or {}).get("name"), "maj": d.get("last_update"),
                  "id": d["id"], "ressources": [(x.get("title"), x.get("format"), x.get("url")) for x in d.get("resources", [])[:6]]}
                 for d in r.json().get("data", [])]
    else:
        dg[q] = f"ERREUR {getattr(r, 'status_code', r)}"
log("datagouv.json", json.dumps(dg, ensure_ascii=False, indent=1))

# 5. Pages INSEE des indicateurs de richesse (liens vers fichiers)
for nom, url in [("insee_nir", "https://www.insee.fr/fr/statistiques/3281778"),
                 ("cnc_frequentation", "https://www.cnc.fr/cinema/etudes-et-rapports/statistiques/frequentation-cinematographique")]:
    r = get(url)
    if isinstance(r, requests.Response):
        liens = sorted(set(re.findall(r'href="([^"]+\.(?:xlsx|xls|csv|zip))"', r.text)))
        log(f"{nom}.txt", f"HTTP {r.status_code}\n" + "\n".join(liens[:80]) + "\n\n" + re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", r.text))[:4000])
    else:
        log(f"{nom}.txt", f"ERREUR {r}")
print("fini")
