"""
Paramètres du baromètre social.

C'est le seul fichier à modifier pour changer les mots-clés suivis, les séries
INSEE ou les seuils d'alerte. Tout le reste se recalcule automatiquement.
"""

# ---------------------------------------------------------------------------
# Les cinq jauges du tableau de bord
# ---------------------------------------------------------------------------
PILIERS = {
    "pouvoir_achat": "Pouvoir d'achat",
    "emploi": "Emploi",
    "moral": "Moral des ménages",
    "mobilisation": "Mobilisation",
    "institutions": "Tension institutionnelle",
}

# ---------------------------------------------------------------------------
# Wikipédia : pages suivies, par jauge (titres de fr.wikipedia.org).
# Les redirections sont résolues automatiquement ; une page introuvable est
# simplement ignorée et signalée dans « Santé des sources ».
# ---------------------------------------------------------------------------
WIKI_PAGES = {
    "pouvoir_achat": [
        "Inflation",
        "Pouvoir d'achat",
        "Restos du cœur",
        "Surendettement",
        "Prime d'activité",
        "Revenu de solidarité active",
        "Chèque énergie",
        "Salaire minimum interprofessionnel de croissance",
    ],
    "emploi": [
        "Licenciement",
        "Licenciement économique",
        "Plan de sauvegarde de l'emploi",
        "Rupture conventionnelle",
        "France Travail",
        "Allocation d'aide au retour à l'emploi",
        "Chômage en France",
    ],
    "mobilisation": [
        "Grève",
        "Grève générale",
        "Préavis de grève",
        "Manifestation",
        "Mouvement des Gilets jaunes",
        "Désobéissance civile",
        "Confédération générale du travail",
    ],
    "institutions": [
        "Motion de censure",
        "Article 49 de la Constitution de la Cinquième République française",
        "Dissolution de l'Assemblée nationale",
        "Question de confiance",
        "Gouvernement de la France",
    ],
}

# Première date disponible dans l'API Wikimedia
WIKI_DEBUT = "2015-07-01"

# ---------------------------------------------------------------------------
# Sujets émergents : détection automatique, chaque semaine, des pages
# Wikipédia en forte hausse qui touchent au social, à l'économie ou à la
# politique en France. Le tri se fait sur les catégories Wikipédia de la page
# (mots écrits sans accents). Ces sujets sont affichés comme alertes ; ils
# n'entrent pas dans le calcul des scores.
# ---------------------------------------------------------------------------
SUJETS_RATIO_MIN = 1.8   # lecture au moins 1,8 fois plus forte que les 4 semaines d'avant
SUJETS_MAX = 8           # nombre de sujets affichés
SUJETS_MOTS = {
    "mobilisation": ["greve", "manifestation", "mouvement social", "syndicat", "syndical",
                     "contestation", "emeute", "desobeissance", "blocage", "conflit social",
                     "revolte", "protestation", "militantisme", "mouvement de protestation"],
    "emploi": ["emploi", "chomage", "licenciement", "droit du travail", "plan social",
               "relations de travail", "travail en france", "retraite", "fermeture d'usine"],
    "pouvoir_achat": ["prix", "inflation", "impot", "fiscalite", "taxe", "pauvrete",
                      "aide sociale", "prestation sociale", "salaire", "logement",
                      "cout de la vie", "carburant", "energie en france", "consommation"],
    "institutions": ["gouvernement", "assemblee nationale", "senat", "election", "parlement",
                     "constitution", "ministre", "personnalite politique", "parti politique",
                     "depute", "senateur", "maire de", "candidat a l'election",
                     "dirigeant de parti", "personnalite de la cinquieme republique",
                     "loi francaise", "projet de loi", "budget de l'etat", "finances publiques",
                     "politique en france", "president de la republique", "referendum",
                     "procedure parlementaire"],
}
SUJETS_EXCLUS = ["sport", "football", "rugby", "tennis", "cyclisme", "olympique", "film",
                 "serie televisee", "emission de television", "chanson", "album", "acteur",
                 "actrice", "chanteur", "chanteuse", "jeu video", "personnage de fiction",
                 "manga", "roman ", "telerealite", "championnat", "club de", "festival",
                 "affaire criminelle", "meurtre"]
# Catégories ignorées : elles décrivent l'entourage d'une personne, pas son rôle
# (« Conjoint de personnalité politique », « Enfant de… »)
SUJETS_CATEGORIES_IGNOREES = ["conjoint", "epoux", "epouse", "enfant de", "famille ",
                              "frere de", "soeur de", "pere de", "mere de"]
# Un événement daté d'il y a plus de 2 ans dans son titre (« Massacre du 17 octobre
# 1961 ») qui remonte est une commémoration, pas un sujet émergent
SUJETS_ANCIENNETE_MAX = 2

# ---------------------------------------------------------------------------
# INSEE : enquête mensuelle de conjoncture auprès des ménages.
# Les séries sont repérées par des mots de leur titre officiel (sans accents),
# ce qui évite de dépendre d'identifiants qui peuvent changer.
# sens = +1 : plus la valeur monte, plus la tension monte ; -1 : l'inverse.
# ---------------------------------------------------------------------------
INSEE_DATAFLOW = "ENQ-CONJ-MENAGES"
INSEE_IDBANK_CONFIANCE = "001587668"  # indicateur synthétique de confiance (CVS)

INSEE_SERIES = {
    "confiance": dict(
        pilier="moral", sens=-1, libelle="Confiance des ménages (INSEE)",
        inclure=["synthetique", "confiance"], exclure=["epargne"],
    ),
    "niveau_vie_futur": dict(
        pilier="moral", sens=-1, libelle="Niveau de vie futur en France (INSEE)",
        inclure=["niveau de vie", "futur"], exclure=["passe"],
    ),
    "chomage": dict(
        pilier="emploi", sens=+1, libelle="Craintes sur le chômage (INSEE)",
        inclure=["chomage"], exclure=[],
    ),
    "prix_passes": dict(
        pilier="pouvoir_achat", sens=+1, libelle="Hausse des prix ressentie (INSEE)",
        inclure=["prix", "passe"], exclure=["futur"],
    ),
    "situation_fin_future": dict(
        pilier="pouvoir_achat", sens=-1, libelle="Situation financière future (INSEE)",
        inclure=["situation financiere", "futur"], exclure=[],
    ),
}

# ---------------------------------------------------------------------------
# GDELT : ce que la presse française raconte (gratuit, sans clé).
# ---------------------------------------------------------------------------
# Calculés à partir des fichiers quotidiens d'événements (fiables depuis GitHub)
GDELT_PART = dict(
    pilier="mobilisation", sens=+1, libelle="Place de la contestation dans l'actualité",
)
GDELT_TON = dict(
    pilier="moral", sens=-1, libelle="Tonalité de l'actualité en France",
)
# En bonus, via l'API DOC de GDELT (souvent bloquée depuis GitHub : erreur 429)
GDELT_REQUETES = {
    "presse_emploi": dict(
        pilier="emploi", sens=+1, libelle="Presse : licenciements et plans sociaux",
        q='(licenciements OR "plan social" OR "suppressions de postes") '
          "sourcecountry:france sourcelang:french",
    ),
}

# Événements « contestation » (code CAMEO 14) géolocalisés en France
GDELT_TYPES = {
    "141": "Manifestations",
    "143": "Grèves et boycotts",
    "144": "Blocages",
    "145": "Émeutes et violences",
}
GDELT_EVENEMENTS = dict(
    pilier="mobilisation", sens=+1, libelle="Actions de contestation recensées",
)
# Historique récupéré automatiquement (dès le premier lancement)
GDELT_PRESSE_ANNEES = 3        # couverture presse : l'API remonte jusqu'à 2017
GDELT_RATTRAPAGE_JOURS = 210   # événements : ~7 mois, pour être actifs tout de suite
GDELT_BUDGET_MINUTES = 25      # temps max par lancement ; le reste suit la semaine d'après

# ---------------------------------------------------------------------------
# Carburants : prix à la pompe (open data du ministère de l'Économie)
# ---------------------------------------------------------------------------
CARBURANTS = {
    "gazole": dict(pilier="pouvoir_achat", sens=+1, libelle="Prix du gazole"),
    "e10": dict(pilier="pouvoir_achat", sens=+1, libelle="Prix du SP95-E10"),
}
CARBURANTS_ANNEES = 2   # archives annuelles officielles récupérées au premier lancement

# ---------------------------------------------------------------------------
# Calcul
# ---------------------------------------------------------------------------
FENETRE_SEMAINES = 104   # on compare chaque semaine aux 2 années précédentes
MIN_HISTORIQUE = 26      # semaines minimum avant qu'une série compte
FENETRE_MOIS = 24        # idem pour les séries mensuelles INSEE
MIN_HISTORIQUE_MOIS = 12
SEUIL_VOYANT = 2.0       # écart (en σ) à partir duquel un voyant s'allume

# Score 0-100 : 50 = semaine normale, 73 ≈ +1σ, 88 ≈ +2σ ; seuils d'affichage
SEUILS = [(90, "Alerte", "critical"), (75, "Tension", "serious"),
          (60, "Vigilance", "warning"), (0, "Calme", "good")]
