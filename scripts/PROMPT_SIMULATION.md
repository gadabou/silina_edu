# Prompt de simulation SILINA-EDU (base `csbonscitoyens`)

**Contexte.** Module Odoo 18 `silina_edu`, base locale `csbonscitoyens` (déploiement via `./deploy.sh -d csbonscitoyens`). Simulation réaliste de trois années scolaires complètes (2024-2025, 2025-2026, 2026-2027), de la crèche au collège, en testant chaque fonctionnalité avec les vrais comptes utilisateurs.

## Phase 0 : mises à jour du module (à faire et déployer AVANT tout test)

1. **En-tête du bulletin / livret paramétrable.**
   - Paramètres : logo, nom de l'établissement, adresse, téléphone, email, devise/slogan, ville, mention légale, texte de pied de page.
   - Valeurs par défaut : reprises de la société Odoo (`res.company`). Si un champ est modifié dans les paramètres, il remplace la valeur par défaut.
   - Le bulletin et le livret (PDF) utilisent cet en-tête.
2. **Vérifier les paramètres existants** : moyenne minimale de passage, barème de notes, périodes (trimestres/semestres), mentions. Compléter ce qui manque.
3. **Vérifier la promotion automatique de fin d'année.** Moyenne annuelle ≥ moyenne minimale → inscription automatique dans la classe supérieure de l'année suivante. Sinon redoublement. Dernière classe du collège → sortie (« diplômé / sorti »).
4. **Revoir la matrice des rôles et permissions** (Administrateur, Coordinateur, Enseignant, Utilisateur/Secrétariat, Comptable) et corriger les écarts avant de tester.
5. Redéployer, confirmer que tout est à jour avant la phase 1.

## Phase 1 : préparation des données (idempotente : ne rien recréer si ça existe)

1. **Sauvegarde** de la base avant toute manipulation.
2. **Années scolaires** : 2024-2025, 2025-2026, 2026-2027 avec leurs périodes.
3. **Cycles et classes**, de la crèche au collège : Crèche, Maternelle (PS/MS/GS), Primaire (CP1 à CM2), Collège (6e à 3e). Toutes les classes existent pour chaque année, avec un titulaire par classe.
4. **Programme par classe et par année** : matières, coefficients, volume horaire, enseignant affecté à chaque (classe, matière). Programmes crèche/maternelle adaptés à l'âge (éveil, motricité, langage).
5. **Enseignants** : une fiche employé liée à un utilisateur Odoo par enseignant, groupe « Enseignant » uniquement. Certains enseignent plusieurs matières ou classes, d'autres sont titulaires. **Mot de passe de tous les enseignants : `P@ssword123!`**
6. **Autres comptes** : administrateur, coordinateur, secrétaire, comptable (mot de passe de test à définir).
7. **Élèves** :
   - Au moins 15 par classe et par année, données réalistes (noms, dates de naissance cohérentes avec l'âge de la classe, tuteurs).
   - Nouvelle cohorte chaque année en classe d'entrée (crèche et 6e), en plus des élèves promus.
   - Cas particuliers : abandons, un transfert, un redoublant.
8. **Frais et facturation** : grille de frais par classe, factures à l'inscription, paiements partiels et complets répartis dans l'année.

## Phase 2 : simulation année par année (3 fois, dans l'ordre chronologique)

1. **Rentrée** : inscriptions, génération des factures, premiers paiements.
2. **Pour chaque période** :
   - Planification des examens (type, date, coefficient, classe, matière).
   - **Connexion réelle de chaque enseignant** : saisie des notes de ses élèves, uniquement pour ses classes et matières.
   - Cas réalistes : absents à un examen, notes manquantes, correction de note, notes réparties de façon crédible.
   - Calcul des moyennes de période, classements, appréciations.
3. **Discipline et assiduité** : absences, retards, incidents, conduite.
4. **Fin d'année** :
   - Moyennes annuelles.
   - Bulletins/livrets PDF avec l'en-tête paramétré.
   - Clôture de l'année.
   - Promotion automatique.
   - Vérification : inscrits N+1 = promus de N + redoublants + nouveaux.
5. **Bascule** vers l'année suivante.

## Phase 3 : tests de sécurité et de visibilité (à chaque année)

Avec un compte réel (pas `sudo`) par rôle :

| Rôle | Doit voir / pouvoir | Ne doit pas voir / pouvoir |
|---|---|---|
| Enseignant | Ses classes, ses élèves, ses examens et notes | Autres classes, finances, paie, paramètres |
| Coordinateur | Tout le pédagogique | Paie, comptabilité |
| Secrétariat | Élèves, inscriptions | Notes (selon règle), paie |
| Comptable | Factures, paiements | Saisie de notes |
| Administrateur | Tout, paramètres | n/a |

Vérifier aussi :
- aucune erreur d'accès (type `account.move`) sur les écrans principaux selon le rôle ;
- un enseignant ne peut pas modifier les notes d'une autre classe, y compris par URL directe ;
- un titulaire voit sa classe entière, un enseignant de matière voit seulement sa matière.

## Livrables

1. Script de seed rejouable et script de simulation (dans `scripts/`, hors déploiement).
2. Rapport par année : effectifs par classe, promus/redoublants, moyennes de classe, anomalies.
3. Tableau permissions testées : rôle × fonctionnalité × résultat (OK/KO).
4. Liste des bugs trouvés, corrigés ou à corriger.
5. Exemple de bulletin PDF avec l'en-tête paramétré.

## Règles de travail

- Si une fonctionnalité échoue : corriger le module, redéployer, relancer le test concerné.
- Ne jamais contourner une permission par `sudo` pour faire passer un test.
- Avertir avant toute action destructive sur la base.
