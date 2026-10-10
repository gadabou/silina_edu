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
        ('decision', 'Selon décision annuelle'),
        ('passed', 'Élèves admis uniquement'),
        ('all', 'Tous les élèves'),
        ('manual', 'Sélection manuelle'),
    ], string='Type de promotion', default='decision', required=True)

    include_indulgence = fields.Boolean(
        string='Inclure les admis par indulgence', default=True,
        help="Mode « Selon décision annuelle » : si décoché, les élèves admis par "
             "indulgence ne sont pas traités par cet assistant.")

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

    skipped_info = fields.Text(
        string='Élèves ignorés',
        readonly=True,
        help="Élèves sélectionnés mais absents de l'aperçu (ex: déjà au niveau "
             "le plus élevé, aucune classe supérieure à proposer)."
    )

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

        if self.promotion_type == 'decision':
            results = self.env['silina.annual.result'].search([
                ('classroom_id', 'in', self.current_classroom_ids.ids),
                ('academic_year_id', '=', self.current_academic_year_id.id),
                ('final_decision', '!=', False),
            ])
            self.student_ids = results.mapped('student_id').filtered(
                lambda st: st.state not in ('transferred', 'expelled', 'graduated', 'draft'))
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
        skipped = []

        Result = self.env['silina.annual.result']
        decision_mode = self.promotion_type == 'decision'

        for student in self.student_ids:
            decision = False
            outcome = 'promote'
            result = Result
            if decision_mode:
                result = Result.search([
                    ('student_id', '=', student.id),
                    ('academic_year_id', '=', self.current_academic_year_id.id),
                ], limit=1)
                decision = result.final_decision if result else False
                if not decision or decision == 'pending':
                    skipped.append(_(
                        '%s : décision annuelle en attente ou absente (traitement manuel)'
                    ) % student.name)
                    continue
                if decision == 'indulgence' and not self.include_indulgence:
                    skipped.append(_(
                        "%s : admis par indulgence (exclu de ce passage)") % student.name)
                    continue
                if decision == 'repeat':
                    outcome = 'repeat'

            if outcome == 'repeat':
                target_level = student.level_id
            else:
                target_level = student.level_id.next_level_id
                if not target_level:
                    if decision_mode:
                        # Dernier niveau du cursus : l'élève est diplômé.
                        lines.append({
                            'wizard_id': self.id,
                            'student_id': student.id,
                            'current_classroom_id': student.classroom_id.id,
                            'current_level_id': student.level_id.id,
                            'new_level_id': False,
                            'new_classroom_id': False,
                            'decision': decision,
                            'outcome': 'graduate',
                            'annual_result_id': result.id,
                        })
                        continue
                    # Pas de classe supérieure (ex: dernière classe du cursus) :
                    # cet élève ne peut pas être "passé" par cet assistant. On le
                    # signale plutôt que de le faire disparaître silencieusement.
                    skipped.append(_('%s : aucun niveau supérieur défini après %s') % (
                        student.name, student.level_id.name or _('son niveau actuel')))
                    continue

            # Trouver une classe disponible dans le niveau cible
            new_classroom = self.env['silina.classroom'].search([
                ('level_id', '=', target_level.id),
                ('academic_year_id', '=', self.new_academic_year_id.id)
            ], limit=1)

            lines.append({
                'wizard_id': self.id,
                'student_id': student.id,
                'current_classroom_id': student.classroom_id.id,
                'current_level_id': student.level_id.id,
                'new_level_id': target_level.id,
                'new_classroom_id': new_classroom.id if new_classroom else False,
                'decision': decision,
                'outcome': outcome,
                'annual_result_id': result.id if result else False,
            })

        if lines:
            self.env['silina.bulk.student.promotion.line'].create(lines)

        self.skipped_info = '\n'.join(skipped) if skipped else False
        self.state = 'preview'

        return {
            'name': _('Aperçu de la Promotion'),
            'type': 'ir.actions.act_window',
            'res_model': 'silina.bulk.student.promotion.wizard',
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def _create_student_for_new_year(self, old, classroom):
        """Crée la fiche de `old` pour la nouvelle année dans `classroom`.

        Lève ValidationError si une fiche existe déjà pour ce matricule."""
        self.ensure_one()
        existing = self.env['silina.student'].search([
            ('registration_number', '=', old.registration_number),
            ('academic_year_id', '=', self.new_academic_year_id.id),
        ], limit=1)
        if existing:
            raise ValidationError(_(
                'Une fiche existe déjà pour ce matricule sur l\'année %s : %s.'
            ) % (self.new_academic_year_id.name, existing.name))

        return self.env['silina.student'].create({
            'first_name': old.first_name,
            'last_name': old.last_name,
            'registration_number': old.registration_number,
            'image_1920': old.image_1920,
            'gender': old.gender,
            'date_of_birth': old.date_of_birth,
            'place_of_birth': old.place_of_birth,
            'nationality': old.nationality.id,
            'blood_group': old.blood_group,
            'email': old.email,
            'phone': old.phone,
            'mobile': old.mobile,
            'street': old.street,
            'street2': old.street2,
            'city': old.city,
            'state_id': old.state_id.id,
            'zip': old.zip,
            'country_id': old.country_id.id,
            'academic_year_id': self.new_academic_year_id.id,
            'classroom_id': classroom.id,
            'enrollment_date': self.promotion_date,
            'state': 'enrolled',
            'previous_student_id': old.id,
            'parent_ids': [(6, 0, old.parent_ids.ids)],
            'father_name': old.father_name,
            'mother_name': old.mother_name,
            'guardian_name': old.guardian_name,
            'allergies': old.allergies,
            'medical_conditions': old.medical_conditions,
            'emergency_contact_name': old.emergency_contact_name,
            'emergency_contact_phone': old.emergency_contact_phone,
        })

    def action_promote(self):
        """Effectuer la promotion en masse"""
        self.ensure_one()

        if self.state != 'preview':
            raise ValidationError(_('Veuillez d\'abord prévisualiser les promotions!'))

        promoted_count = 0
        errors = []

        for line in self.line_ids:
            if line.outcome != 'graduate' and not line.new_classroom_id:
                message = _('Aucune classe de destination')
                errors.append(f"{line.student_id.name}: {message}")
                line.state = 'error'
                line.error_message = message
                continue

            try:
                # Chaque élève est traité dans son propre savepoint : si l'un
                # d'eux échoue (ex: fiche déjà existante sur la nouvelle
                # année), la transaction n'est pas invalidée pour les
                # suivants et les promotions déjà faites restent valables.
                with self.env.cr.savepoint():
                    old = line.student_id
                    if line.outcome == 'graduate':
                        old.state = 'graduated'
                        note = _('Diplômé (dernier niveau du cursus) - %s') % (
                            self.current_academic_year_id.name)
                    else:
                        new_student = self._create_student_for_new_year(old, line.new_classroom_id)
                        if line.outcome == 'repeat':
                            old.state = 'repeated'
                            note = _('Redoublement en %s (nouvelle fiche : %s)') % (
                                line.new_classroom_id.name, new_student.name)
                        else:
                            old.state = 'promoted'
                            note = _('Passage en %s (nouvelle fiche : %s)') % (
                                line.new_classroom_id.name, new_student.name)
                    old.message_post(body=note)
                    if line.annual_result_id:
                        line.annual_result_id.sudo().write({'promotion_state': 'done'})

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
        self.skipped_info = False
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

    decision = fields.Selection([
        ('pending', 'En attente'),
        ('passed', 'Admis'),
        ('indulgence', 'Admis par indulgence'),
        ('repeat', 'Redouble'),
    ], string='Décision annuelle', readonly=True)
    outcome = fields.Selection([
        ('promote', 'Classe supérieure'),
        ('repeat', 'Redoublement'),
        ('graduate', 'Diplômé'),
    ], string='Issue', default='promote', required=True)
    annual_result_id = fields.Many2one(
        'silina.annual.result', string='Résultat annuel', readonly=True)

    @api.depends('student_id')
    def name_get(self):
        result = []
        for record in self:
            name = record.student_id.name if record.student_id else 'Ligne de promotion'
            result.append((record.id, name))
        return result
