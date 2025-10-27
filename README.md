# SILINA-EDU - Module de Gestion Scolaire pour Odoo 18

## Description

SILINA-EDU est un module complet de gestion scolaire pour Odoo 18, conçu pour gérer l'ensemble des activités d'un complexe scolaire incluant le primaire, le collège et le lycée.

## Fonctionnalités Principales

### 1. Gestion Académique
- **Années Scolaires**: Gestion des années académiques avec activation/désactivation
- **Niveaux**: Configuration des niveaux (CP1-CM2, 6ème-3ème, 2nde-Terminale)
- **Classes**: Gestion des classes avec capacité et affectation d'enseignant principal
- **Matières**: Configuration des matières avec coefficients
- **Affectations**: Assignation des enseignants aux matières et classes

### 2. Gestion des Étudiants
- Profil complet de l'étudiant (informations personnelles, contact, médicales)
- Numéro de matricule automatique
- Photo d'identité
- Suivi de l'historique académique
- États: Brouillon, Inscrit, Admis, Redoublant, Transféré, Diplômé, Exclu

### 3. Gestion des Parents/Tuteurs
- Informations de contact complètes
- Relations multiples (père, mère, tuteur)
- Contact d'urgence
- Responsable financier
- Autorisation de prise en charge
- Lien avec res.partner pour facturation

### 4. Gestion des Enseignants
- Intégration avec le module RH (hr.employee)
- Code enseignant automatique
- Spécialisation (Primaire, Collège, Lycée)
- Matières enseignées
- Affectations aux classes
- Qualifications et expérience

### 5. Gestion des Examens
- Configuration des examens (mensuel, trimestriel, semestriel, annuel, final)
- Périodes d'examen
- Notes maximales et notes de passage
- États: Brouillon, Programmé, En cours, Terminé, Annulé

### 6. Gestion des Résultats
- Saisie des notes par matière et étudiant
- Calcul automatique des pourcentages
- Attribution des mentions (Excellent, Très Bien, Bien, etc.)
- Notes pondérées par coefficient
- Résumés d'examens avec moyennes générales
- Calcul automatique des rangs par classe

### 7. Génération de Bulletins de Notes
- **3 modèles de bulletins**:
  - Standard: Format classique
  - Moderne: Design coloré et moderne
  - Détaillé: Avec statistiques et graphiques
- Options configurables:
  - Inclusion du rang
  - Statistiques de classe
  - Commentaires des enseignants
- Génération par classe ou par étudiant
- Multilangue (Français/Anglais)

### 8. Gestion des Frais Scolaires
- Types de frais configurables:
  - Frais de scolarité
  - Frais d'inscription
  - Frais d'examen
  - Cantine
  - Transport
  - Bibliothèque
  - Activités extrascolaires
- **Paiement par tranches**:
  - Configuration du nombre de tranches
  - Dates d'échéance automatiques
  - Suivi individuel par tranche
- Intégration avec le module Facturation (account)
- Génération automatique de factures
- Création d'articles (product.product) automatique

### 9. Gestion des Paiements
- Enregistrement des paiements
- Modes de paiement multiples:
  - Espèces
  - Virement bancaire
  - Chèque
  - Carte bancaire
  - Mobile Money
- Génération de reçus
- Intégration avec la comptabilité (account.payment)
- Suivi des montants dus, payés, restants

### 10. Gestion des Documents
- Stockage des documents étudiants:
  - Acte de naissance
  - Carte d'identité
  - Certificat médical
  - Bulletins antérieurs
  - Certificats divers
- Système de vérification
- Dates d'expiration
- Pièces jointes

### 11. Passage en Masse des Étudiants
- Assistant de promotion automatique
- Options de sélection:
  - Étudiants admis uniquement
  - Tous les étudiants
  - Sélection manuelle
- Aperçu avant validation
- Création automatique des nouveaux enregistrements
- Assignation aux classes du niveau supérieur
- Gestion des erreurs

### 12. Génération en Masse des Frais
- Génération par niveau, classe ou étudiant
- Sélection multiple des types de frais
- Configuration des dates d'échéance
- Création automatique des tranches
- Aperçu avant génération
- Gestion des doublons

### 13. Sécurité et Droits d'Accès
Quatre niveaux de droits:
- **Utilisateur**: Lecture seule
- **Enseignant**: Lecture + saisie des notes
- **Coordinateur**: Gestion complète sauf suppression
- **Administrateur**: Tous les droits

### 14. Intégrations
- **Module RH (hr)**: Gestion des enseignants
- **Module Point de Vente (point_of_sale)**: Vente d'articles scolaires
- **Module Facturation (account)**: Gestion financière
- **Module Mail (mail)**: Notifications et suivi

## Installation

1. Placez le dossier `silina_edu` dans le répertoire addons d'Odoo
2. Redémarrez le serveur Odoo
3. Activez le mode développeur
4. Mettez à jour la liste des applications
5. Installez "SILINA-EDU - Gestion Scolaire"

## Configuration Initiale

### Étape 1: Configuration de Base
1. **Configuration > Années Scolaires**: Créez une année scolaire et activez-la
2. **Configuration > Niveaux**: Les niveaux sont pré-configurés (CP1 à Terminale)
3. **Configuration > Matières**: Les matières de base sont pré-configurées
4. **Configuration > Types de Frais**: Configurez vos types de frais

### Étape 2: Classes et Enseignants
1. **Personnel > Enseignants**: Créez vos enseignants (nécessite d'abord créer des employés)
2. **Académique > Classes**: Créez les classes pour l'année en cours
3. **Académique > Affectations Matières**: Assignez les enseignants aux matières par classe

### Étape 3: Étudiants
1. **Étudiants > Étudiants**: Inscrivez les étudiants
2. **Étudiants > Parents/Tuteurs**: Ajoutez les informations des parents
3. **Outils > Générer Frais en Masse**: Générez les frais pour les étudiants

### Étape 4: Examens et Résultats
1. **Académique > Examens**: Créez les examens
2. **Académique > Résultats d'Examens**: Saisissez les notes
3. **Rapports > Générer Bulletins de Notes**: Générez les bulletins

## Utilisation Quotidienne

### Inscription d'un Étudiant
1. Allez dans **Étudiants > Étudiants > Créer**
2. Remplissez les informations
3. Assignez une classe
4. Ajoutez les parents
5. Cliquez sur "Inscrire"

### Saisie des Résultats d'Examen
1. Créez un examen dans **Académique > Examens**
2. Programmez-le puis démarrez-le
3. Allez dans **Académique > Résultats d'Examens**
4. Saisissez les notes (mode éditable en ligne)
5. Confirmez les résultats
6. Terminez l'examen

### Génération des Bulletins
1. Allez dans **Rapports > Générer Bulletins de Notes**
2. Sélectionnez l'examen
3. Choisissez par classe ou par étudiant
4. Sélectionnez le modèle de bulletin
5. Configurez les options
6. Cliquez sur "Générer"

### Enregistrement d'un Paiement
1. Allez dans **Frais et Paiements > Paiements > Créer**
2. Sélectionnez l'étudiant et les frais
3. Entrez le montant et le mode de paiement
4. Confirmez le paiement
5. Imprimez le reçu

### Passage en Classe Supérieure
1. Créez la nouvelle année scolaire
2. Créez les classes pour la nouvelle année
3. Allez dans **Outils > Passage en Masse**
4. Sélectionnez l'année actuelle et la nouvelle année
5. Choisissez les classes et le type de promotion
6. Cliquez sur "Aperçu"
7. Vérifiez les affectations
8. Cliquez sur "Promouvoir"

## Rapports Disponibles

1. **Bulletin de Notes (Standard)**: Format classique
2. **Bulletin de Notes (Moderne)**: Design coloré
3. **Bulletin de Notes (Détaillé)**: Avec statistiques
4. **Reçu de Paiement**: Pour les paiements de frais
5. **Liste des Étudiants**: Liste complète avec filtres

## Données de Démonstration

Le module inclut des données de base:
- 13 niveaux (CP1 à Terminale)
- 10 matières communes
- 5 types de frais standard

## Support et Personnalisation

Pour toute demande de support ou personnalisation:
- Email: support@silina.com
- Website: https://www.silina.com

## Licence

LGPL-3

## Auteur

SILINA

## Version

18.0.1.0.0

## Notes Importantes

1. **Sauvegarde**: Effectuez des sauvegardes régulières avant les opérations en masse
2. **Année Scolaire**: Une seule année peut être active à la fois
3. **Frais**: Les frais sont liés à l'année scolaire, créez-en pour chaque année
4. **Passage en Masse**: Vérifiez toujours l'aperçu avant de valider
5. **Bulletins**: Générez les résumés d'examen avant d'imprimer les bulletins
6. **Intégration HR**: Créez d'abord un employé avant de créer un enseignant
7. **Facturation**: Configurez un parent comme responsable financier avec un contact pour la facturation

## Changelog

### Version 18.0.1.0.0
- Version initiale
- Toutes les fonctionnalités principales
- Support Odoo 18

## Feuille de Route

### Version 18.0.2.0.0 (Prévue)
- Emploi du temps
- Gestion des absences
- Planning des examens
- SMS et notifications email automatiques
- Dashboard statistiques
- Export Excel des résultats
- API REST
- Application mobile (Flutter)

## Screenshots

[À ajouter - Captures d'écran de l'interface]

## Contribution

Les contributions sont les bienvenues! Veuillez créer une pull request ou contacter l'équipe de développement.
