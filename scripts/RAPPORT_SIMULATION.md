# Rapport de simulation SILINA-EDU (2024-2025 à 2026-2027)

Base de test : `csbonscitoyens_sim` (copie propre ; `csbonscitoyens` n'est pas modifiée).
Rejouer : `sim_seed.py` puis `sim_run.py` puis `sim_verify.py` (voir `PROMPT_SIMULATION.md`).

## Volumes
| | 2024-2025 | 2025-2026 | 2026-2027 |
|---|---|---|---|
| Élèves | 202 | 218 | 235 |
| Effectif par classe (min) | 15 | 15 | 15 |
| Admis | 163 | 158 | 162 |
| Redoublants | 39 | 60 | 73 |
| Diplômés (3ème) | 14 | 12 | n/a (dernière année) |
| Moyenne générale | 12,54 | 12,38 | 12,44 |

Au total : 324 examens, 74 682 notes saisies par les enseignants avec leur propre compte,
2 620 factures, 1 865 paiements (assistant de paiement du module).

## Vérifications automatiques : 40 / 40 OK
- 15 élèves minimum par classe et par année.
- Promotion : tout élève avec moyenne >= 10 est inscrit au niveau supérieur, les autres redoublent,
  les élèves de 3ème admis sortent diplômés ; aucun doublon de matricule.
- En-tête du bulletin et du livret : valeurs paramétrées, repli sur la société si vides ; PDF générés.
- Permissions : un enseignant ne voit que ses classes, élèves, notes, affectations ; accès direct
  par identifiant refusé ; paie, frais, comptabilité, paramètres refusés ; secrétariat, coordinateur,
  directeur, comptable conformes au tableau de rôles.

## Bugs trouvés et corrigés
1. Erreur `account.move` à l'ouverture des fiches/tableau de bord pour un utilisateur sans Facturation.
2. Les enseignants voyaient toutes les classes, affectations, parents et documents élèves.
3. La paie et les types de frais étaient lisibles par tout utilisateur SILINA (donc les enseignants).
4. Le coordinateur ne pouvait pas calculer les résultats (lecture d'une action fenêtre réservée aux admins).
5. La génération de factures échouait en silence pour le coordinateur (accès `account.move`).
6. L'encaissement échouait pour le secrétariat (accès aux factures) : le groupe Secrétariat
   implique désormais Facturation, et le coordinateur hérite du Secrétariat.
7. Le logo « Your logo » d'Odoo apparaissait sur les bulletins sans logo configuré.

## Points d'attention (non corrigés)
- Odoo ouvre l'assistant « Configurer la mise en page » au 1er bulletin tant que la société n'a pas de
  mise en page de document : à configurer une fois par base.
- La date d'une facture générée est la date du jour (pas celle de la rentrée) ; les échéances, elles,
  suivent la date de début saisie.
- La promotion reste déclenchée par l'assistant « Promotion en masse » (non planifiée).
- La 3ème n'a plus de niveau suivant dans la base de test (périmètre crèche → collège).
- Exemples : `scripts/exemples/bulletin_3eme.pdf`, `scripts/exemples/livret_ce1.pdf`.
