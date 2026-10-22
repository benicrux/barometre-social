"""Exploration n°2 : jeux INSEE ciblés (objectifs de développement durable, tourisme, comptes)."""
import io, time
import xml.etree.ElementTree as ET
from pathlib import Path
import requests

OUT = Path("exploration/series2"); OUT.mkdir(parents=True, exist_ok=True)
s = requests.Session()
s.headers["User-Agent"] = "barometre-social exploration (github.com/benicrux/barometre-social)"
FLOWS = ["ODD-CONSOMMATION-PRODUCTION", "ODD-EAU-PROPRE-ASSAINISSEMENT", "ODD-EDUCATION-QUALITE",
         "ODD-EGALITE-SEXES", "ODD-ENERGIE-PROPRE-COUT-ABORDABLE", "ODD-ERADICATION-PAUVRETE",
         "ODD-INFRASTRUCTURES-RESILIENTES-INNOVATION", "ODD-LUTTE-CHANGEMENT-CLIMATIQUE",
         "ODD-PAIX-JUSTICE-INSTITUTIONS-EFFICACES", "ODD-PARTENARIATS-REALISATION", "ODD-REDUCTION-INEGALITES",
         "ODD-SANTE-BIEN-ETRE", "ODD-SECURITE-ALIMENTAIRE-AGRICULTURE-DURABLE", "ODD-TRAVAIL-CROISSANCE",
         "ODD-VIE-AQUATIQUE", "ODD-VIE-TERRESTRE", "ODD-VILLES-COMMUNAUTES-DURABLES",
         "SUIVI-DEMANDE-TOURISTIQUE", "TOURISME-FRANCE-METHODE-REDRESSEMENT-2019",
         "DETTE-TRIM-APU-2020", "CNA-2020-DETTE-APU", "INDICES_LOYERS", "DEMANDES-EMPLOIS-NATIONALES"]
resume = []
for f in FLOWS:
    lignes = []
    try:
        r = s.get(f"https://bdm.insee.fr/series/sdmx/data/{f}", params={"lastNObservations": "3"}, timeout=180)
        if not r.ok:
            resume.append(f"{f}\tERREUR {r.status_code}")
            continue
        for ev, el in ET.iterparse(io.BytesIO(r.content), events=("end",)):
            if el.tag.split("}")[-1] == "Series":
                a = el.attrib
                obs = [(o.attrib.get("TIME_PERIOD"), o.attrib.get("OBS_VALUE")) for o in el if o.tag.split("}")[-1] == "Obs"]
                lignes.append("\t".join([a.get("IDBANK", ""), a.get("FREQ", ""), a.get("CORRECTION", ""),
                                         " ".join(f"{p}={v}" for p, v in obs), a.get("TITLE_FR", "")]))
                el.clear()
    except Exception as e:
        lignes.append(f"ERREUR {e}")
    (OUT / f"{f}.tsv").write_text("\n".join(lignes), encoding="utf-8")
    resume.append(f"{f}\t{len(lignes)} séries")
    time.sleep(1)
(OUT / "resume.tsv").write_text("\n".join(resume), encoding="utf-8")
print("fini")
