from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class GenerateReportCard(models.TransientModel):
    _name = 'silina.generate.report.card.wizard'
    _description = 'Assistant de Génération de Bulletin de Notes'

    academic_year_id = fields.Many2one(
        'silina.academic.year',
        string='Année Scolaire',
        required=True,
        default=lambda self: self.env['silina.academic.year'].get_current_year(),
        help="Sélectionnez l'année scolaire pour laquelle générer les bulletins"
    )

    generation_type = fields.Selection([
        ('classroom', 'Par classe'),
        ('student', 'Par élève'),
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
        string='Élèves'
    )

    template_type = fields.Selection([
        ('standard', 'Standard'),
        ('modern', 'Moderne'),
        ('detailed', 'Détaillé'),
    ], string='Modèle de bulletin', default='standard', required=True)

    include_rank = fields.Boolean(
        string='Inclure le rang',
        default=True,
        help="Afficher le rang de l'élève dans sa classe"
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
        """Charger automatiquement les élèves des classes sélectionnées"""
        if self.generation_type == 'classroom' and self.classroom_ids:
            students = self.env['silina.student'].search([
                ('classroom_id', 'in', self.classroom_ids.ids),
                ('state', '=', 'enrolled')
            ])
            self.student_ids = students

    def action_generate_summaries(self):
        """Générer les résumés d'examen si pas déjà fait"""
        self.ensure_one()

        # Récupérer tous les élèves concernés
        if self.generation_type == 'classroom':
            students = self.env['silina.student'].search([
                ('classroom_id', 'in', self.classroom_ids.ids)
            ])
        else:
            students = self.student_ids

        if not students:
            raise ValidationError(_('Aucun élève sélectionné!'))

        # Récupérer tous les examens de l'année scolaire où les élèves ont des résultats
        exams = self.env['silina.exam'].search([
            ('academic_year_id', '=', self.academic_year_id.id),
            ('state', 'in', ['in_progress', 'completed'])
        ])

        # Filtrer pour ne garder que les examens où au moins un élève a des résultats
        exam_ids_with_results = self.env['silina.exam.result'].search([
            ('exam_id', 'in', exams.ids),
            ('student_id', 'in', students.ids)
        ]).mapped('exam_id')

        if not exam_ids_with_results:
            raise ValidationError(_('Aucun résultat trouvé pour les élèves sélectionnés dans cette année scolaire!'))

        # Générer les résumés pour chaque examen
        summary_model = self.env['silina.exam.result.summary']
        for exam in exam_ids_with_results:
            for student in students:
                # Vérifier si l'élève a des résultats pour cet examen
                has_results = self.env['silina.exam.result'].search_count([
                    ('exam_id', '=', exam.id),
                    ('student_id', '=', student.id)
                ])

                if has_results:
                    # Vérifier si un résumé existe déjà
                    existing = summary_model.search([
                        ('exam_id', '=', exam.id),
                        ('student_id', '=', student.id)
                    ])

                    if not existing:
                        # Créer le résumé
                        summary_model.create({
                            'exam_id': exam.id,
                            'student_id': student.id,
                        })

            # Calculer les rangs par classe pour cet examen
            for classroom in students.mapped('classroom_id'):
                classroom_summaries = summary_model.search([
                    ('exam_id', '=', exam.id),
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

        # Prendre le premier élève pour la prévisualisation
        student = self.student_ids[0] if self.student_ids else False
        if not student:
            raise ValidationError(_('Aucun élève sélectionné!'))

        return self._generate_report([student.id])

    def action_generate(self):
        """Générer les bulletins pour tous les élèves sélectionnés"""
        self.ensure_one()

        # Générer les résumés d'abord
        self.action_generate_summaries()

        if not self.student_ids:
            raise ValidationError(_('Aucun élève sélectionné!'))

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
            'academic_year_id': self.academic_year_id.id,
            'include_rank': self.include_rank,
            'include_statistics': self.include_statistics,
            'include_comments': self.include_comments,
            'lang': self.language,
        }

        # Générer le rapport
        students = self.env['silina.student'].browse(student_ids)
        return self.env.ref(report_ref).with_context(**context).report_action(students)
