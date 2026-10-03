# Prospection : mode d'emploi (sans assistant)

## 1. Ajouter des prospects
Ouvre `prospects.csv` (tableur ou éditeur de texte, séparateur `;`) et ajoute une ligne par entreprise.

| Colonne | Obligatoire | Exemple / remarque |
|---|---|---|
| `nom` | oui | `Dupont Plomberie` |
| `email` | oui | adresse de l'entreprise |
| `ville` | conseillé | `Aix-en-Provence` |
| `activite` | conseillé | `plombier chauffagiste`, `serrurerie`, `menuisier`… (choisit le thème et le texte du mail) |
| `telephone` | conseillé | affiché sur le bouton d'appel mobile ; **prends celui du site** |
| `site_web` | si elle en a un | `https://…` ; vide = mail « n'a pas encore de site » |
| `contact` | facultatif | **nom de famille**, seulement si tu es sûr (sinon « Bonjour, ») |
| `civilite` | facultatif | `M.` ou `Mme` (défaut : Monsieur) |
| `accroche` | facultatif | titre principal de la maquette |
| `sous_titre` | facultatif | phrase sous le titre |
| `service_1`, `service_2`, `service_3` | facultatif | `Titre \| description` : les 3 cartes de la maquette |
| `statut` | auto | vide → prêt → brouillon → envoyé / ignoré |

Si tu laisses `accroche` / `service_*` vides, le script les prend sur le site (ou met un texte générique du métier).
**Relis toujours le résultat** : les textes repris d'un site sont parfois mal choisis.

## 2. Lancer
```
source .venv/bin/activate
python prospect_pipeline.py prospects.csv
```
Pour chaque prospect : `d` = ouvre le brouillon dans Thunderbird (4 images jointes) → tu envoies → réponds `o`.
Autres touches : `r` régénérer (après modification), `s` ignorer, `n` suivant, `q` quitter.

Options : `--only "nom"`, `--list` (voir les statuts), `--prepare-only` (tout préparer sans rien ouvrir).

## 3. Corriger une maquette
Chaque prospect a un dossier `prospects/<nom>/` :
- `prospect.json` : tous les textes, images, couleurs → modifie, puis touche `r` dans le script.
- `images/` : remplace ou ajoute des photos / le logo (`logo.png`), puis mets le bon nom dans le JSON.
- `maquette/` : les 4 images générées (celles envoyées).

Pour refaire un prospect de zéro (nouveau scraping) : supprime son dossier dans `prospects/` et remets `statut` à vide.

## 4. À vérifier avant chaque envoi
- Téléphone / e-mail cohérents avec le site de l'entreprise.
- Aucune information inventée dans la maquette (chiffres, avis, certifications).
- Photos : sinon des visuels génériques sont utilisés (message d'avertissement dans le terminal).
