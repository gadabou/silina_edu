from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class BulkStudentPromotion(models.TransientModel):
    _name = 'silina.bulk.student.promotion.wizard'
    _description = 'Assistant de Passage en Masse des Élèves'

    current_academic_year_id = fields.Many2one(
        'silina.academic.year',
        string='Année scolaire actuelle',
        required=True,
        default=lambda self: self.env['silina.academic.year'].get_current_year()
    )

    new_academic_year_id = fields.Many2one(
        'silina.academic.year',
        string='Nouvelle année scolaire',
        required=True,
        help="Année scolaire vers laquelle promouvoir les élèves"
    )

    current_classroom_ids = fields.Many2many(
        'silina.classroom',
        'promotion_current_classroom_rel',
        'wizard_id',
        'classroom_id',
        string='Classes actuelles',
        domain="[('academic_year_id', '=', current_academic_year_id)]",
        help="Sélectionnez les classes dont vous voulez promouvoir les élèves"
    )

    promotion_type = fields.Selection([
        ('passed', 'Élèves admis uniquement'),
        ('all', 'Tous les élèves'),
        ('manual', 'Sélection manuelle'),
    ], string='Type de promotion', default='passed', required=True)

    student_ids = fields.Many2many(
        'silina.student',
        'promotion_student_rel',
        'wizard_id',
        'student_id',
        string='Élèves',
        help="Élèves à promouvoir (pour sélection manuelle)"
    )

    student_count = fields.Integer(
        string='Nombre d\'élèves',
        compute='_compute_student_count'
    )

    line_ids = fields.One2many(
        'silina.bulk.student.promotion.line',
        'wizard_id',
        string='Lignes de promotion'
    )

    state = fields.Selection([
        ('draft', 'Configuration'),
        ('preview', 'Aperçu'),
        ('done', 'Terminé'),
    ], string='État', default='draft')

    promotion_date = fields.Date(
        string='Date de promotion',
        default=fields.Date.today,
        required=True
    )

    notes = fields.Text(string='Notes')

    @api.depends('student_ids', 'line_ids')
    def _compute_student_count(self):
        for record in self:
            if record.state == 'preview':
                record.student_count = len(record.line_ids)
            else:
                record.student_count = len(record.student_ids)

    @api.onchange('current_classroom_ids', 'promotion_type')
    def _onchange_classrooms(self):
        """Charger automatiquement les élèves selon le type de promotion"""
        if not self.current_classroom_ids:
            self.student_ids = False
            return

        domain = [('classroom_id', 'in', self.current_classroom_ids.ids)]

        if self.promotion_type == 'passed':
            domain.append(('state', '=', 'promoted'))
        elif self.promotion_type == 'all':
            domain.append(('state', 'in', ['enrolled', 'promoted']))

        if self.promotion_type != 'manual':
            students = self.env['silina.student'].search(domain)
            self.student_ids = students

    def action_preview(self):
        """Générer un aperçu des promotions"""
        self.ensure_one()

        if not self.student_ids:
            raise ValidationError(_('Aucun élève sélectionné pour la promotion!'))

        # Créer les lignes de promotion
        self.line_ids.unlink()
        lines = []

        for student in self.student_ids:
            # Trouver le niveau suivant
            next_level = student.level_id.next_level_id
            if not next_level:
                continue

            # Trouver une classe disponible dans le nouveau niveau
            new_classroom = self.env['silina.classroom'].search([
                ('level_id', '=', next_level.id),
                ('academic_year_id', '=', self.new_academic_year_id.id)
            ], limit=1)

            lines.append({
                'wizard_id': self.id,
                'student_id': student.id,
                'current_classroom_id': student.classroom_id.id,
                'current_level_id': student.level_id.id,
                'new_level_id': next_level.id,
                'new_classroom_id': new_classroom.id if new_classroom else False,
            })

        if lines:
            self.env['silina.bulk.student.promotion.line'].create(lines)

        self.state = 'preview'

        return {
            'name': _('Aperçu de la Promotion'),
            'type': 'ir.actions.act_window',
            'res_model': 'silina.bulk.student.promotion.wizard',
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def action_promote(self):
        """Effectuer la promotion en masse"""
        self.ensure_one()

        if self.state != 'preview':
            raise ValidationError(_('Veuillez d\'abord prévisualiser les promotions!'))

        promoted_count = 0
        errors = []

        for line in self.line_ids:
            try:
                if not line.new_classroom_id:
                    errors.append(f"{line.student_id.name}: Aucune classe de destination")
                    continue

                # Créer le nouvel enregistrement élève pour la nouvelle année
                new_student_vals = {
                    'first_name': line.student_id.first_name,
                    'last_name': line.student_id.last_name,
                    'registration_number': line.student_id.registration_number,
                    'image_1920': line.student_id.image_1920,
                    'gender': line.student_id.gender,
                    'date_of_birth': line.student_id.date_of_birth,
                    'place_of_birth': line.student_id.place_of_birth,
                    'nationality': line.student_id.nationality.id,
                    'blood_group': line.student_id.blood_group,
                    'email': line.student_id.email,
                    'phone': line.student_id.phone,
                    'mobile': line.student_id.mobile,
                    'street': line.student_id.street,
                    'street2': line.student_id.street2,
                    'city': line.student_id.city,
                    'state_id': line.student_id.state_id.id,
                    'zip': line.student_id.zip,
                    'country_id': line.student_id.country_id.id,
                    'academic_year_id': self.new_academic_year_id.id,
                    'classroom_id': line.new_classroom_id.id,
                    'enrollment_date': self.promotion_date,
                    'state': 'enrolled',
                    'parent_ids': [(6, 0, line.student_id.parent_ids.ids)],
                    'father_name': line.student_id.father_name,
                    'mother_name': line.student_id.mother_name,
                    'guardian_name': line.student_id.guardian_name,
                    'allergies': line.student_id.allergies,
                    'medical_conditions': line.student_id.medical_conditions,
                    'emergency_contact_name': line.student_id.emergency_contact_name,
                    'emergency_contact_phone': line.student_id.emergency_contact_phone,
                }

                new_student = self.env['silina.student'].create(new_student_vals)

                # Marquer l'ancien élève comme promu/gradué
                if line.new_level_id:
                    line.student_id.state = 'promoted'
                else:
                    line.student_id.state = 'graduated'

                promoted_count += 1
                line.state = 'done'

            except Exception as e:
                errors.append(f"{line.student_id.name}: {str(e)}")
                line.state = 'error'
                line.error_message = str(e)

        self.state = 'done'

        # Afficher un message de résultat
        message = _('%s élèves ont été promus avec succès.') % promoted_count
        if errors:
            message += '\n\n' + _('Erreurs:') + '\n' + '\n'.join(errors)

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Promotion terminée'),
                'message': message,
                'type': 'success' if not errors else 'warning',
                'sticky': True,
            }
        }

    def action_back_to_draft(self):
        """Retour à la configuration"""
        self.ensure_one()
        self.line_ids.unlink()
        self.state = 'draft'

        return {
            'name': _('Promotion en Masse'),
            'type': 'ir.actions.act_window',
            'res_model': 'silina.bulk.student.promotion.wizard',
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }


class BulkStudentPromotionLine(models.TransientModel):
    _name = 'silina.bulk.student.promotion.line'
    _description = 'Ligne de Promotion d\'Élève'

    wizard_id = fields.Many2one(
        'silina.bulk.student.promotion.wizard',
        string='Assistant',
        required=True,
        ondelete='cascade'
    )

    student_id = fields.Many2one(
        'silina.student',
        string='Élève',
        required=True
    )

    current_classroom_id = fields.Many2one(
        'silina.classroom',
        string='Classe actuelle',
        readonly=True
    )

    current_level_id = fields.Many2one(
        'silina.level',
        string='Niveau actuel',
        readonly=True
    )

    new_level_id = fields.Many2one(
        'silina.level',
        string='Nouveau niveau',
        readonly=True
    )

    new_classroom_id = fields.Many2one(
        'silina.classroom',
        string='Nouvelle classe',
        required=False,
        domain="[('level_id', '=', new_level_id)]",
        help="Sélectionnez la classe de destination pour cet élève"
    )

    state = fields.Selection([
        ('pending', 'En attente'),
        ('done', 'Terminé'),
        ('error', 'Erreur'),
    ], string='État', default='pending')

    error_message = fields.Text(string='Message d\'erreur')

    @api.depends('student_id')
    def name_get(self):
        result = []
        for record in self:
            name = record.student_id.name if record.student_id else 'Ligne de promotion'
            result.append((record.id, name))
        return result
