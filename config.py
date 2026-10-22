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

# Les questions de l'enquête, pour voir ce qui pèse sur le moral et ce qui tient.
# Affichage seulement (elles ne changent pas les scores).
# bon = +1 : plus le solde est haut, mieux c'est ; -1 : l'inverse.
INSEE_QUESTIONS = {
    "q_niveau_vie_passe": dict(libelle="Niveau de vie en France, l'année passée",
                               inclure=["niveau de vie passe en france"], exclure=[], bon=+1),
    "q_niveau_vie_futur": dict(libelle="Niveau de vie en France, l'année à venir",
                               inclure=["niveau de vie futur en france"], exclure=[], bon=+1),
    "q_finances_passees": dict(libelle="Ses propres finances, l'année passée",
                               inclure=["situation financiere passee"], exclure=[], bon=+1),
    "q_finances_futures": dict(libelle="Ses propres finances, l'année à venir",
                               inclure=["situation financiere future"], exclure=[], bon=+1),
    "q_gros_achats": dict(libelle="Le bon moment pour faire de gros achats",
                          inclure=["achats importants"], exclure=[], bon=+1),
    "q_epargne_actuelle": dict(libelle="Capacité à mettre de l'argent de côté",
                               inclure=["capacite d'epargne actuelle"], exclure=[], bon=+1),
    "q_epargne_future": dict(libelle="Capacité à épargner dans l'année à venir",
                             inclure=["capacite d'epargne future"], exclure=[], bon=+1),
    "q_chomage": dict(libelle="Peur que le chômage augmente",
                      inclure=["evolution future du chomage"], exclure=["proportion"], bon=-1),
    "q_prix_passes": dict(libelle="Hausse des prix ressentie",
                          inclure=["evolution passee des prix"], exclure=[], bon=-1),
    "q_prix_futurs": dict(libelle="Hausse des prix attendue",
                          inclure=["evolution future des prix"], exclure=[], bon=-1),
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
GDELT_RATTRAPAGE_JOURS = 210   # événements : ~7 mois, pour être actifs tout de suite
GDELT_BUDGET_MINUTES = 25      # temps max par lancement ; le reste suit la semaine d'après

# ---------------------------------------------------------------------------
# Le terrain par département (carte)
# Chômage localisé : automatique, chaque trimestre (INSEE, jeu TAUX-CHOMAGE).
# Pauvreté : fichier Filosofi publié une fois par an par l'Insee (page « Niveau de
# vie et pauvreté par région »). À la sortie d'un nouveau millésime, remplacer
# l'adresse et l'année ci-dessous.
# ---------------------------------------------------------------------------
PAUVRETE_URL = "https://www.insee.fr/fr/statistiques/fichier/7941411/RPM2024-F21.xlsx"
PAUVRETE_MILLESIME = 2021

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
# Listes « Ce qui se tend » / « Ce qui s'apaise » : mêmes règles dans les deux sens.
# Un indicateur y figure dès qu'il s'écarte d'au moins 1σ de sa normale (une page
# Wikipédia isolée, plus bruitée, à partir de SEUIL_VOYANT + 0,5).
SEUIL_LISTE = 1.0
LISTE_MAX = 6           # lignes par colonne, identique des deux côtés

# Score 0-100 : 50 = semaine normale, 73 ≈ +1σ, 88 ≈ +2σ ; seuils d'affichage
SEUILS = [(90, "Alerte", "critical"), (75, "Tension", "serious"),
          (60, "Vigilance", "warning"), (0, "Calme", "good")]

# ===========================================================================
# VOLET 2 : ÉTAT DU PAYS (page mensuelle)
# Tous les chiffres viennent de la base INSEE (identifiants « idbank »).
#   mode « taux »   : on compare des points (8,3 % -> 9,1 % = +0,8 pt)
#   mode « niveau » : on compare en % (créations, emplois, consommation…)
#   mode « ca »     : chiffre d'affaires, comparé hors hausse des prix
#   bon = +1 : plus haut = mieux ; -1 : plus bas = mieux
#   seuil : écart en dessous duquel on parle de « stable »
#   lissage : nombre de mois moyennés (évite les à-coups d'un mois isolé)
#   horizon : comparaison à 1 an (conjoncture) ou 5 ans (indicateurs de fond)
# ===========================================================================
PAYS_SECTIONS = {
    "economie": "Économie et emploi",
    "loisirs": "Sorties et loisirs",
    "richesse": "Les indicateurs de richesse",
}
PAYS_DEFLATEUR = "011812231"   # prix à la consommation harmonisés, ensemble (base 2025)
PAYS = [
    # --- Économie et emploi --------------------------------------------------
    dict(id="chomage", section="economie", libelle="Taux de chômage", idbank="011818543",
         mode="taux", bon=-1, seuil=0.2, unite="%", aide="au sens du BIT, France entière"),
    dict(id="chomage_jeunes", section="economie", libelle="… des moins de 25 ans", idbank="001688537",
         mode="taux", bon=-1, seuil=0.5, unite="%", aide="hors Mayotte", sous=True),
    dict(id="chomage_25_49", section="economie", libelle="… des 25-49 ans", idbank="001688529",
         mode="taux", bon=-1, seuil=0.2, unite="%", aide="hors Mayotte", sous=True),
    dict(id="chomage_seniors", section="economie", libelle="… des 50 ans ou plus", idbank="001688531",
         mode="taux", bon=-1, seuil=0.2, unite="%", aide="hors Mayotte", sous=True),
    dict(id="inflation", section="economie", libelle="Hausse des prix sur un an", idbank="011812232",
         mode="taux", bon=-1, seuil=0.3, unite="%", aide="prix à la consommation harmonisés"),
    dict(id="emploi_salarie", section="economie", libelle="Emplois salariés", idbank="001796852",
         mode="niveau", bon=+1, seuil=0.2, unite="milliers", aide="ensemble des salariés"),
    dict(id="conso", section="economie", libelle="Consommation des ménages en biens",
         idbank="011794487", mode="niveau", bon=+1, seuil=1, lissage=3, unite="indice",
         aide="en volume, moyenne sur 3 mois"),
    dict(id="creations", section="economie", libelle="Créations d'entreprises", idbank="010755538",
         mode="niveau", bon=+1, seuil=3, lissage=3, unite="nombre", aide="par mois, moyenne sur 3 mois"),
    dict(id="defaillances", section="economie", libelle="Défaillances d'entreprises",
         idbank="001656101", mode="niveau", bon=-1, seuil=3, unite="nombre",
         aide="cumul sur 12 mois"),
    dict(id="industrie", section="economie", libelle="Production industrielle", idbank="010768261",
         mode="niveau", bon=+1, seuil=1, lissage=3, unite="indice", aide="moyenne sur 3 mois"),
    dict(id="logements", section="economie", libelle="Logements mis en chantier", idbank="001718274",
         mode="niveau", bon=+1, seuil=3, unite="nombre", aide="cumul sur 12 mois, métropole"),
    # --- Sorties et loisirs (chiffre d'affaires, hors hausse des prix) ----------
    dict(id="restaurants", section="loisirs", libelle="Restaurants", idbank="010774417",
         mode="ca", bon=+1, seuil=2, lissage=3, unite="indice"),
    dict(id="cinemas", section="loisirs", libelle="Cinémas", idbank="010775181",
         mode="ca", bon=+1, seuil=2, lissage=3, unite="indice"),
    dict(id="parcs", section="loisirs", libelle="Parcs d'attractions", idbank="010775419",
         mode="ca", bon=+1, seuil=2, lissage=3, unite="indice"),
    dict(id="clubs_sport", section="loisirs", libelle="Clubs de sport", idbank="010774740",
         mode="ca", bon=+1, seuil=2, lissage=3, unite="indice"),
    dict(id="salles_sport", section="loisirs", libelle="Salles de sport", idbank="010774365",
         mode="ca", bon=+1, seuil=2, lissage=3, unite="indice"),
    dict(id="spectacles", section="loisirs", libelle="Spectacles vivants", idbank="010775169",
         mode="ca", bon=+1, seuil=2, lissage=3, unite="indice"),
    dict(id="musees", section="loisirs", libelle="Musées", idbank="010775218",
         mode="ca", bon=+1, seuil=2, lissage=3, unite="indice"),
    dict(id="hotels", section="loisirs", libelle="Hôtels", idbank="010775045",
         mode="ca", bon=+1, seuil=2, lissage=3, unite="indice"),
    # --- Indicateurs de richesse (loi de 2015), comparés à il y a 5 ans ---------
    dict(id="taux_emploi", section="richesse", libelle="Taux d'emploi des 15-64 ans",
         idbank="011818676", mode="taux", bon=+1, seuil=0.5, unite="%", horizon=5),
    dict(id="recherche", section="richesse", libelle="Effort de recherche", idbank="010594852",
         mode="taux", bon=+1, seuil=0.05, unite="% du PIB", horizon=5, decimales=2),
    dict(id="dette", section="richesse", libelle="Dette publique", idbank="010777608",
         mode="taux", bon=-1, seuil=2, unite="% du PIB", horizon=5),
    dict(id="sante", section="richesse", libelle="Espérance de vie en bonne santé",
         idbank=["010593268", "010593269"], mode="taux", bon=+1, seuil=0.5, unite="ans",
         horizon=5, aide="moyenne femmes et hommes"),
    dict(id="satisfaction", section="richesse", libelle="Satisfaction dans la vie",
         idbank="010593281", mode="taux", bon=+1, seuil=0.2, unite="/10", horizon=5),
    dict(id="inegalites", section="richesse", libelle="Inégalités de niveau de vie",
         idbank="010594680", mode="taux", bon=-1, seuil=0.1, unite="fois", horizon=5,
         aide="les 20 % les plus aisés comparés aux 20 % les plus modestes, après impôts et prestations"),
    dict(id="privation", section="richesse", libelle="Privation matérielle et sociale",
         idbank="010594486", mode="taux", bon=-1, seuil=0.5, unite="%", horizon=5,
         aide="part des personnes privées d'au moins 5 éléments de la vie courante sur 13"),
    dict(id="sorties_precoces", section="richesse", libelle="Jeunes sortis tôt de l'école sans diplôme",
         idbank="010594746", mode="taux", bon=-1, seuil=0.5, unite="%", horizon=5,
         aide="18-24 ans"),
    dict(id="empreinte", section="richesse", libelle="Empreinte carbone par habitant",
         idbank="010595988", mode="taux", bon=-1, seuil=0.3, unite="t éq. CO₂", horizon=5),
]
