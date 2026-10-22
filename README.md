# Baromètre social

Un tableau de bord hebdomadaire du climat social en France, façon « cockpit présidentiel », calculé automatiquement chaque lundi à partir de données publiques et gratuites, et publié sur une page web consultable depuis un téléphone.

**Ce qu'il affiche :** une météo sociale sur 100, cinq jauges (pouvoir d'achat, emploi, moral des ménages, mobilisation, tension institutionnelle), les voyants rouges de la semaine, une prévision du prochain chiffre INSEE de confiance des ménages comparée au réalisé, une carte des actions de contestation, ce qui monte sur Wikipédia, l'historique sur deux ans avec vos repères, et une vue mois par mois.

**Coût : 0 €.** GitHub Actions et GitHub Pages sont gratuits pour un dépôt public.

---

## Mise en place (15 minutes, une seule fois)

### 1. Créer le dépôt
1. Créez un compte gratuit sur [github.com](https://github.com) si vous n'en avez pas.
2. En haut à droite : **+** → **New repository**.
3. Nom : `barometre-social`. Cochez **Public** (obligatoire pour la page gratuite). Cliquez **Create repository**.

### 2. Déposer les fichiers
1. Sur la page du dépôt vide, cliquez **uploading an existing file**.
2. Dézippez l'archive sur votre ordinateur, ouvrez le dossier `barometre-social`, sélectionnez **tout son contenu** et glissez-le dans la page.
3. Cliquez **Commit changes**.

> ⚠️ Le dossier `.github` commence par un point : il est **masqué** sur Mac (affichez-le avec `Cmd + Maj + .`) et parfois sur Windows. Vérifiez après l'envoi qu'il existe bien un fichier `.github/workflows/barometre.yml` dans le dépôt. Sinon : **Add file → Create new file**, tapez `.github/workflows/barometre.yml` comme nom, collez le contenu du fichier, puis **Commit changes**.

### 3. Autoriser la publication
1. **Settings → Pages** : dans *Build and deployment*, *Source*, choisissez **GitHub Actions**.
2. **Settings → Actions → General** : tout en bas, *Workflow permissions*, choisissez **Read and write permissions**, puis **Save**.

### 4. Premier lancement
1. Onglet **Actions** → cliquez **Baromètre social** à gauche → bouton **Run workflow** → **Run workflow**.
2. Attendez 20 à 40 minutes : le premier lancement récupère tout l'historique (Wikipédia depuis 2015, INSEE depuis 2010, 3 ans de presse, 7 mois de manifestations, 2 ans de prix des carburants). Les lundis suivants, quelques minutes suffisent.
3. Votre tableau de bord est à l'adresse `https://VOTRE-PSEUDO.github.io/barometre-social/`.

Sur téléphone, ouvrez cette adresse puis « Ajouter à l'écran d'accueil » pour l'avoir comme une appli.

Ensuite, tout est automatique : le calcul tourne **chaque lundi matin**.

---

## Au quotidien

- **Ajouter une décision ou un événement** sur les courbes : ouvrez `decisions.csv` sur GitHub, cliquez le crayon ✏️, ajoutez une ligne `2026-11-03,Annonce du gel des prix de l'énergie,Décision`, puis **Commit changes**. Elle apparaîtra au prochain calcul.
- **Changer les mots-clés suivis** : tout est dans `config.py` (liste des pages Wikipédia par jauge, séries INSEE, requêtes presse, seuils).
- **Relancer sans attendre lundi** : onglet Actions → Run workflow.
- **Si une source tombe en panne** : la page s'affiche quand même, et la section *Santé des sources* indique ce qui a échoué. Les données manquantes sont récupérées au lancement suivant quand c'est possible.

## Ce qu'il faut savoir

- **L'historique est récupéré dès le premier lancement**, si bien que tous les indicateurs comptent tout de suite (il en faut au moins 26 semaines). Si une source est lente ce jour-là, le rattrapage des manifestations s'arrête au bout de 25 minutes et se termine automatiquement les lundis suivants ; la section *Santé des sources* l'indique.
- **Le score 0-100** compare chaque semaine aux deux années précédentes : 50 = normal, 73 ≈ un écart-type au-dessus, 88 ≈ deux.
- **La prévision INSEE** est testée honnêtement contre une prévision naïve (« le chiffre ne bouge pas »). La page dit clairement si le modèle fait mieux ou non.
- **GDELT** code automatiquement la presse mondiale : c'est un bon thermomètre des tendances, pas un décompte officiel des manifestations.
- Le dépôt étant public, la page et les données le sont aussi. Elles ne contiennent que des données publiques.

## Organisation du code

| Fichier | Rôle |
|---|---|
| `config.py` | Tous les réglages (mots-clés, séries, seuils) |
| `collect/` | Un collecteur par source (Wikipédia, INSEE, GDELT, carburants) |
| `indicators.py` | Calcul des écarts, des jauges et de la météo sociale |
| `nowcast.py` | Prévision du prochain chiffre INSEE et test contre la prévision naïve |
| `render.py`, `templates/` | Génération de la page web |
| `data/` | Historique des données, mis à jour chaque semaine par le robot |
| `.github/workflows/barometre.yml` | Le planning du lundi et la publication |

Pour tester sur votre ordinateur : `pip install -r requirements.txt` puis `python main.py`, et ouvrez `site/index.html`.

## Sources

- Pages vues Wikipédia : API Wikimedia (licence libre)
- Enquête mensuelle de conjoncture auprès des ménages : INSEE, API BDM (Licence Ouverte)
- Presse et événements : The GDELT Project (accès libre)
- Prix des carburants : data.economie.gouv.fr, flux instantané v2 (Licence Ouverte)
