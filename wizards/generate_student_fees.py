from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class GenerateStudentFees(models.TransientModel):
    _name = 'silina.generate.student.fees.wizard'
    _description = 'Assistant de Génération de Frais Élèves'

    academic_year_id = fields.Many2one(
        'silina.academic.year',
        string='Année Scolaire',
        required=True,
        default=lambda self: self.env['silina.academic.year'].get_current_year()
    )

    generation_type = fields.Selection([
        ('level', 'Par niveau'),
        ('classroom', 'Par classe'),
        ('student', 'Par élève'),
    ], string='Type de génération', default='classroom', required=True)

    level_ids = fields.Many2many(
        'silina.level',
        'generate_fees_level_rel',
        'wizard_id',
        'level_id',
        string='Niveaux'
    )

    classroom_ids = fields.Many2many(
        'silina.classroom',
        'generate_fees_classroom_rel',
        'wizard_id',
        'classroom_id',
        string='Classes',
        domain="[('academic_year_id', '=', academic_year_id)]"
    )

    student_ids = fields.Many2many(
        'silina.student',
        'generate_fees_student_rel',
        'wizard_id',
        'student_id',
        string='Élèves',
        domain="[('academic_year_id', '=', academic_year_id)]"
    )

    fee_type_ids = fields.Many2many(
        'silina.fee.type',
        'generate_fees_type_rel',
        'wizard_id',
        'fee_type_id',
        string='Types de frais',
        required=True,
        help="Frais à générer pour les élèves sélectionnés"
    )

    due_date = fields.Date(
        string='Date d\'échéance',
        help="Date d'échéance par défaut pour les frais"
    )

    allow_duplicate = fields.Boolean(
        string='Autoriser les doublons',
        default=False,
        help="Générer même si les frais existent déjà pour certains élèves"
    )

    student_count = fields.Integer(
        string='Nombre d\'élèves',
        compute='_compute_student_count'
    )

    @api.depends('generation_type', 'level_ids', 'classroom_ids', 'student_ids')
    def _compute_student_count(self):
        for record in self:
            students = record._get_students()
            record.student_count = len(students)

    @api.onchange('generation_type')
    def _onchange_generation_type(self):
        """Réinitialiser les champs selon le type"""
        self.level_ids = False
        self.classroom_ids = False
        self.student_ids = False

    @api.onchange('level_ids')
    def _onchange_level_ids(self):
        """Charger les classes du niveau"""
        if self.generation_type == 'level' and self.level_ids:
            classrooms = self.env['silina.classroom'].search([
                ('level_id', 'in', self.level_ids.ids),
                ('academic_year_id', '=', self.academic_year_id.id)
            ])
            self.classroom_ids = classrooms

    @api.onchange('classroom_ids')
    def _onchange_classroom_ids(self):
        """Charger les élèves des classes"""
        if self.classroom_ids:
            students = self.env['silina.student'].search([
                ('classroom_id', 'in', self.classroom_ids.ids),
                ('state', '=', 'enrolled')
            ])
            self.student_ids = students

    def _get_students(self):
        """Obtenir la liste des élèves selon le type de génération"""
        self.ensure_one()

        if self.generation_type == 'level':
            return self.env['silina.student'].search([
                ('level_id', 'in', self.level_ids.ids),
                ('academic_year_id', '=', self.academic_year_id.id),
                ('state', '=', 'enrolled')
            ])
        elif self.generation_type == 'classroom':
            return self.env['silina.student'].search([
                ('classroom_id', 'in', self.classroom_ids.ids),
                ('state', '=', 'enrolled')
            ])
        else:
            return self.student_ids

    def action_generate(self):
        """Générer les frais pour les élèves sélectionnés"""
        self.ensure_one()

        if not self.fee_type_ids:
            raise ValidationError(_('Veuillez sélectionner au moins un type de frais!'))

        students = self._get_students()
        if not students:
            raise ValidationError(_('Aucun élève sélectionné!'))

        created_count = 0
        skipped_count = 0
        errors = []

        for student in students:
            for fee_type in self.fee_type_ids:
                # Vérifier si les frais existent déjà
                existing = self.env['silina.student.fee'].search([
                    ('student_id', '=', student.id),
                    ('fee_type_id', '=', fee_type.id),
                    ('academic_year_id', '=', self.academic_year_id.id)
                ])

                if existing and not self.allow_duplicate:
                    skipped_count += 1
                    continue

                try:
                    # Créer les frais
                    fee_vals = {
                        'student_id': student.id,
                        'fee_type_id': fee_type.id,
                        'academic_year_id': self.academic_year_id.id,
                        'amount': fee_type.total_amount,
                        'due_date': self.due_date,
                        'state': 'confirmed',
                    }

                    # Gestion des tranches
                    if fee_type.installment_count > 1:
                        fee_vals['installment_count'] = fee_type.installment_count

                    fee = self.env['silina.student.fee'].create(fee_vals)
                    created_count += 1

                except Exception as e:
                    errors.append(f"{student.name} - {fee_type.name}: {str(e)}")

        # Message de résultat
        message = _('%s frais créés avec succès.') % created_count
        if skipped_count > 0:
            message += '\n' + _('%s frais ignorés (déjà existants).') % skipped_count
        if errors:
            message += '\n\n' + _('Erreurs:') + '\n' + '\n'.join(errors[:10])
            if len(errors) > 10:
                message += '\n' + _('... et %s autres erreurs') % (len(errors) - 10)

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Génération de Frais Terminée'),
                'message': message,
                'type': 'success' if not errors else 'warning',
                'sticky': True,
            }
        }

    def action_preview(self):
        """Afficher un aperçu des frais qui seront générés"""
        self.ensure_one()

        students = self._get_students()
        if not students:
            raise ValidationError(_('Aucun élève sélectionné!'))

        # Compter les frais qui seront créés
        total_fees = 0
        total_amount = 0

        for student in students:
            for fee_type in self.fee_type_ids:
                existing = self.env['silina.student.fee'].search_count([
                    ('student_id', '=', student.id),
                    ('fee_type_id', '=', fee_type.id),
                    ('academic_year_id', '=', self.academic_year_id.id)
                ])

                if not existing or self.allow_duplicate:
                    total_fees += 1
                    total_amount += fee_type.total_amount

        message = _(
            'Aperçu:\n\n'
            '- Nombre d\'élèves: %s\n'
            '- Types de frais: %s\n'
            '- Nombre de frais à créer: %s\n'
            '- Montant total: %s'
        ) % (
            len(students),
            len(self.fee_type_ids),
            total_fees,
            f"{total_amount:,.2f}"
        )

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Aperçu de la Génération'),
                'message': message,
                'type': 'info',
                'sticky': True,
            }
        }
