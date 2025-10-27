from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class GenerateReportCard(models.TransientModel):
    _name = 'silina.generate.report.card.wizard'
    _description = 'Assistant de Génération de Bulletin de Notes'

    exam_id = fields.Many2one(
        'silina.exam',
        string='Examen',
        required=True,
        domain="[('state', '=', 'completed')]"
    )

    academic_year_id = fields.Many2one(
        related='exam_id.academic_year_id',
        string='Année Scolaire',
        readonly=True
    )

    generation_type = fields.Selection([
        ('classroom', 'Par classe'),
        ('student', 'Par étudiant'),
    ], string='Type de génération', default='classroom', required=True)

    classroom_ids = fields.Many2many(
        'silina.classroom',
        'report_card_classroom_rel',
        'wizard_id',
        'classroom_id',
        string='Classes',
        domain="[('academic_year_id', '=', academic_year_id)]"
    )

    student_ids = fields.Many2many(
        'silina.student',
        'report_card_student_rel',
        'wizard_id',
        'student_id',
        string='Étudiants'
    )

    template_type = fields.Selection([
        ('standard', 'Standard'),
        ('modern', 'Moderne'),
        ('detailed', 'Détaillé'),
    ], string='Modèle de bulletin', default='standard', required=True)

    include_rank = fields.Boolean(
        string='Inclure le rang',
        default=True,
        help="Afficher le rang de l'étudiant dans sa classe"
    )

    include_statistics = fields.Boolean(
        string='Inclure les statistiques',
        default=True,
        help="Afficher les moyennes de classe, min, max"
    )

    include_comments = fields.Boolean(
        string='Inclure les commentaires',
        default=True,
        help="Afficher les observations des enseignants"
    )

    language = fields.Selection([
        ('fr_FR', 'Français'),
        ('en_US', 'Anglais'),
    ], string='Langue', default='fr_FR')

    @api.onchange('generation_type')
    def _onchange_generation_type(self):
        """Réinitialiser les champs selon le type"""
        if self.generation_type == 'classroom':
            self.student_ids = False
        else:
            self.classroom_ids = False

    @api.onchange('classroom_ids')
    def _onchange_classroom_ids(self):
        """Charger automatiquement les étudiants des classes sélectionnées"""
        if self.generation_type == 'classroom' and self.classroom_ids:
            students = self.env['silina.student'].search([
                ('classroom_id', 'in', self.classroom_ids.ids),
                ('state', '=', 'enrolled')
            ])
            self.student_ids = students

    def action_generate_summaries(self):
        """Générer les résumés d'examen si pas déjà fait"""
        self.ensure_one()

        # Récupérer tous les étudiants concernés
        if self.generation_type == 'classroom':
            students = self.env['silina.student'].search([
                ('classroom_id', 'in', self.classroom_ids.ids)
            ])
        else:
            students = self.student_ids

        if not students:
            raise ValidationError(_('Aucun étudiant sélectionné!'))

        # Générer les résumés
        summary_model = self.env['silina.exam.result.summary']
        for student in students:
            # Vérifier si un résumé existe déjà
            existing = summary_model.search([
                ('exam_id', '=', self.exam_id.id),
                ('student_id', '=', student.id)
            ])

            if not existing:
                # Créer le résumé
                summary_model.create({
                    'exam_id': self.exam_id.id,
                    'student_id': student.id,
                })

        # Calculer les rangs par classe
        for classroom in students.mapped('classroom_id'):
            classroom_summaries = summary_model.search([
                ('exam_id', '=', self.exam_id.id),
                ('classroom_id', '=', classroom.id)
            ])
            sorted_summaries = classroom_summaries.sorted(key=lambda s: s.average, reverse=True)
            for rank, summary in enumerate(sorted_summaries, 1):
                summary.rank = rank

        return True

    def action_generate_preview(self):
        """Prévisualiser un bulletin"""
        self.ensure_one()

        # Générer les résumés d'abord
        self.action_generate_summaries()

        # Prendre le premier étudiant pour la prévisualisation
        student = self.student_ids[0] if self.student_ids else False
        if not student:
            raise ValidationError(_('Aucun étudiant sélectionné!'))

        return self._generate_report([student.id])

    def action_generate(self):
        """Générer les bulletins pour tous les étudiants sélectionnés"""
        self.ensure_one()

        # Générer les résumés d'abord
        self.action_generate_summaries()

        if not self.student_ids:
            raise ValidationError(_('Aucun étudiant sélectionné!'))

        return self._generate_report(self.student_ids.ids)

    def _generate_report(self, student_ids):
        """Générer le rapport selon le modèle choisi"""
        self.ensure_one()

        # Sélectionner le bon template
        if self.template_type == 'standard':
            report_ref = 'silina_edu.action_report_card_standard'
        elif self.template_type == 'modern':
            report_ref = 'silina_edu.action_report_card_modern'
        else:
            report_ref = 'silina_edu.action_report_card_detailed'

        # Préparer le contexte
        context = {
            'exam_id': self.exam_id.id,
            'include_rank': self.include_rank,
            'include_statistics': self.include_statistics,
            'include_comments': self.include_comments,
            'lang': self.language,
        }

        # Générer le rapport
        students = self.env['silina.student'].browse(student_ids)
        return self.env.ref(report_ref).with_context(**context).report_action(students)
