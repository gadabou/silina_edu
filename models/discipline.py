from odoo import models, fields, api, _
from odoo.exceptions import ValidationError

SEVERITY_DEFAULT_POINTS = {'1': 0.5, '2': 1.0, '3': 2.0, '4': 4.0, '5': 6.0}


def _find_period(env, student, date):
    """Retourne la période (silina.period) contenant `date` pour l'année de
    l'élève. Tolérant à l'absence du modèle ou de périodes."""
    Period = env.get('silina.period')
    if Period is None or not date:
        return False
    domain = [('date_start', '<=', date), ('date_end', '>=', date)]
    if student and student.academic_year_id:
        domain.append(('academic_year_id', '=', student.academic_year_id.id))
    return Period.sudo().search(domain, order='date_start', limit=1)


class DisciplineTrackedMixin(models.AbstractModel):
    """Recalcule la note de conduite quand une entrée disciplinaire change."""
    _name = 'silina.discipline.tracked.mixin'
    _description = 'Suivi disciplinaire (mixin)'

    def _tracked_pairs(self):
        return {(r.student_id.id, r.period_id.id)
                for r in self if r.student_id and r.period_id}

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        self.env['silina.discipline.conduct']._recompute_pairs(records._tracked_pairs())
        return records

    def write(self, vals):
        pairs = self._tracked_pairs()
        res = super().write(vals)
        pairs |= self._tracked_pairs()
        self.env['silina.discipline.conduct']._recompute_pairs(pairs)
        return res

    def unlink(self):
        pairs = self._tracked_pairs()
        res = super().unlink()
        self.env['silina.discipline.conduct']._recompute_pairs(pairs)
        return res


class DisciplineAbsence(models.Model):
    _name = 'silina.discipline.absence'
    _description = 'Absence'
    _inherit = ['silina.discipline.tracked.mixin']
    _rec_name = 'student_id'
    _order = 'date desc, id desc'

    student_id = fields.Many2one(
        'silina.student', string='Élève', required=True, index=True,
        ondelete='cascade')
    academic_year_id = fields.Many2one(
        related='student_id.academic_year_id', string='Année Scolaire',
        store=True, index=True)
    classroom_id = fields.Many2one(
        related='student_id.classroom_id', string='Classe', store=True)
    date = fields.Date(
        string='Date', required=True, default=fields.Date.context_today,
        index=True)
    absence_type = fields.Selection([
        ('day', 'Journée'),
        ('half_day', 'Demi-journée'),
        ('course', 'Cours'),
    ], string="Type d'absence", required=True, default='day')
    justified = fields.Boolean(string='Justifiée', default=False)
    motif = fields.Char(string='Motif')
    period_id = fields.Many2one(
        'silina.period', string='Période', compute='_compute_period_id',
        store=True, readonly=False, index=True)

    @api.depends('date', 'student_id', 'student_id.academic_year_id')
    def _compute_period_id(self):
        for rec in self:
            rec.period_id = _find_period(self.env, rec.student_id, rec.date)


class DisciplineLate(models.Model):
    _name = 'silina.discipline.late'
    _description = 'Retard'
    _inherit = ['silina.discipline.tracked.mixin']
    _rec_name = 'student_id'
    _order = 'date desc, id desc'

    student_id = fields.Many2one(
        'silina.student', string='Élève', required=True, index=True,
        ondelete='cascade')
    academic_year_id = fields.Many2one(
        related='student_id.academic_year_id', string='Année Scolaire',
        store=True, index=True)
    classroom_id = fields.Many2one(
        related='student_id.classroom_id', string='Classe', store=True)
    date = fields.Date(
        string='Date', required=True, default=fields.Date.context_today,
        index=True)
    minutes = fields.Integer(string='Minutes de retard', default=10)
    justified = fields.Boolean(string='Justifié', default=False)
    motif = fields.Char(string='Motif')
    period_id = fields.Many2one(
        'silina.period', string='Période', compute='_compute_period_id',
        store=True, readonly=False, index=True)

    @api.depends('date', 'student_id', 'student_id.academic_year_id')
    def _compute_period_id(self):
        for rec in self:
            rec.period_id = _find_period(self.env, rec.student_id, rec.date)

    @api.constrains('minutes')
    def _check_minutes(self):
        for rec in self:
            if rec.minutes < 0:
                raise ValidationError(_("Les minutes de retard ne peuvent pas être négatives."))


class DisciplineSanctionType(models.Model):
    _name = 'silina.discipline.sanction.type'
    _description = 'Type de sanction'
    _order = 'severity, name'

    name = fields.Char(string='Nom', required=True, translate=True)
    severity = fields.Selection([
        ('1', '1 - Légère'),
        ('2', '2 - Modérée'),
        ('3', '3 - Sérieuse'),
        ('4', '4 - Grave'),
        ('5', '5 - Très grave'),
    ], string='Gravité', required=True, default='1')
    points_deducted = fields.Float(
        string='Points retirés', default=0.5,
        help="Points retirés de la note de conduite (sur 20).")
    is_exclusion = fields.Boolean(string='Exclusion')
    active = fields.Boolean(default=True)

    @api.onchange('severity')
    def _onchange_severity(self):
        if self.severity:
            self.points_deducted = SEVERITY_DEFAULT_POINTS.get(self.severity, 0.0)


class DisciplineSanction(models.Model):
    _name = 'silina.discipline.sanction'
    _description = 'Sanction'
    _inherit = ['silina.discipline.tracked.mixin']
    _rec_name = 'student_id'
    _order = 'date desc, id desc'

    student_id = fields.Many2one(
        'silina.student', string='Élève', required=True, index=True,
        ondelete='cascade')
    academic_year_id = fields.Many2one(
        related='student_id.academic_year_id', string='Année Scolaire',
        store=True, index=True)
    classroom_id = fields.Many2one(
        related='student_id.classroom_id', string='Classe', store=True)
    type_id = fields.Many2one(
        'silina.discipline.sanction.type', string='Type de sanction',
        required=True)
    severity = fields.Selection(related='type_id.severity', store=True,
                                string='Gravité')
    is_exclusion = fields.Boolean(related='type_id.is_exclusion', store=True,
                                  string='Exclusion')
    date = fields.Date(
        string='Date', required=True, default=fields.Date.context_today,
        index=True)
    date_end = fields.Date(string='Date de fin')
    reason = fields.Text(string='Motif')
    state = fields.Selection([
        ('pronounced', 'Prononcée'),
        ('executed', 'Exécutée'),
        ('lifted', 'Levée'),
        ('cancelled', 'Annulée'),
    ], string='Statut', required=True, default='pronounced', index=True)
    points_deducted = fields.Float(
        string='Points retirés', related='type_id.points_deducted',
        store=True, readonly=False)
    period_id = fields.Many2one(
        'silina.period', string='Période', compute='_compute_period_id',
        store=True, readonly=False, index=True)

    @api.depends('date', 'student_id', 'student_id.academic_year_id')
    def _compute_period_id(self):
        for rec in self:
            rec.period_id = _find_period(self.env, rec.student_id, rec.date)

    @api.constrains('date', 'date_end')
    def _check_dates(self):
        for rec in self:
            if rec.date and rec.date_end and rec.date_end < rec.date:
                raise ValidationError(_("La date de fin doit être postérieure à la date de la sanction."))

    def action_execute(self):
        self.write({'state': 'executed'})

    def action_lift(self):
        self.write({'state': 'lifted'})

    def action_cancel(self):
        self.write({'state': 'cancelled'})

    def action_reset(self):
        self.write({'state': 'pronounced'})


class DisciplineConduct(models.Model):
    _name = 'silina.discipline.conduct'
    _description = 'Note de conduite'
    _rec_name = 'student_id'
    _order = 'period_id, student_id'

    student_id = fields.Many2one(
        'silina.student', string='Élève', required=True, index=True,
        ondelete='cascade')
    academic_year_id = fields.Many2one(
        related='student_id.academic_year_id', string='Année Scolaire',
        store=True, index=True)
    classroom_id = fields.Many2one(
        related='student_id.classroom_id', string='Classe', store=True)
    period_id = fields.Many2one(
        'silina.period', string='Période', required=True, index=True,
        ondelete='cascade',
        domain="[('academic_year_id', '=', academic_year_id)]")
    base_score = fields.Float(string='Note de base', default=20.0)
    points_deducted = fields.Float(string='Points retirés', readonly=True)
    conduct_score = fields.Float(
        string='Note de conduite', compute='_compute_conduct_score',
        store=True, help="Note de base - points retirés, plancher 0. "
                         "N'entre pas dans la moyenne générale.")
    appreciation = fields.Selection([
        ('exemplary', 'Exemplaire'),
        ('good', 'Bonne'),
        ('satisfactory', 'Satisfaisante'),
        ('to_improve', 'À améliorer'),
        ('worrying', 'Préoccupante'),
    ], string='Appréciation', compute='_compute_conduct_score', store=True)
    absences_count = fields.Integer(string='Absences', readonly=True)
    absences_unjustified_count = fields.Integer(
        string='Absences injustifiées', readonly=True)
    lates_count = fields.Integer(string='Retards', readonly=True)

    _sql_constraints = [
        ('student_period_unique', 'unique(student_id, period_id)',
         "Une seule note de conduite par élève et par période."),
    ]

    @api.constrains('base_score')
    def _check_base_score(self):
        for rec in self:
            if rec.base_score < 0:
                raise ValidationError(_("La note de base ne peut pas être négative."))

    @api.depends('base_score', 'points_deducted')
    def _compute_conduct_score(self):
        for rec in self:
            score = max(0.0, (rec.base_score or 0.0) - (rec.points_deducted or 0.0))
            rec.conduct_score = score
            rec.appreciation = self._appreciation_for(score)

    @api.model
    def _appreciation_for(self, score):
        if score >= 18:
            return 'exemplary'
        if score >= 15:
            return 'good'
        if score >= 12:
            return 'satisfactory'
        if score >= 10:
            return 'to_improve'
        return 'worrying'

    # ------------------------------------------------------------------
    # Calcul
    # ------------------------------------------------------------------
    @api.model
    def _compute_period_figures(self, student_id, period_id):
        """Compteurs et points retirés d'un élève sur une période."""
        env = self.sudo().env
        base = [('student_id', '=', student_id), ('period_id', '=', period_id)]
        absences = env['silina.discipline.absence'].search(base)
        lates_count = env['silina.discipline.late'].search_count(base)
        sanctions = env['silina.discipline.sanction'].search(
            base + [('state', 'in', ('pronounced', 'executed'))])
        return {
            'points_deducted': sum(sanctions.mapped('points_deducted')),
            'absences_count': len(absences),
            'absences_unjustified_count': len(absences.filtered(lambda a: not a.justified)),
            'lates_count': lates_count,
        }

    def action_recompute(self):
        for rec in self:
            rec.sudo().write(self._compute_period_figures(
                rec.student_id.id, rec.period_id.id))
        return True

    @api.model
    def recompute_for(self, student, period):
        """Crée ou met à jour la note de conduite (student, period).
        `student` et `period` : recordsets ou ids. Retourne l'enregistrement."""
        student_id = student.id if hasattr(student, 'id') else student
        period_id = period.id if hasattr(period, 'id') else period
        if not student_id or not period_id:
            return self.browse()
        conduct = self.sudo().search(
            [('student_id', '=', student_id), ('period_id', '=', period_id)], limit=1)
        if conduct:
            conduct.action_recompute()
        else:
            conduct = self.sudo().create({
                'student_id': student_id, 'period_id': period_id})
        return conduct

    @api.model
    def _recompute_pairs(self, pairs):
        for student_id, period_id in pairs:
            self.recompute_for(student_id, period_id)

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records.action_recompute()
        return records

    @api.model
    def get_summary(self, student_id, period_id):
        """Résumé disciplinaire d'un élève sur une période (pour bulletins)."""
        student_id = student_id.id if hasattr(student_id, 'id') else student_id
        period_id = period_id.id if hasattr(period_id, 'id') else period_id
        summary = {'conduct_score': 20.0, 'appreciation': False,
                   'absences': 0, 'absences_unjustified': 0, 'lates': 0}
        if not student_id or not period_id:
            return summary
        fig = self._compute_period_figures(student_id, period_id)
        conduct = self.sudo().search(
            [('student_id', '=', student_id), ('period_id', '=', period_id)], limit=1)
        base = conduct.base_score if conduct else 20.0
        score = max(0.0, base - fig['points_deducted'])
        summary.update({
            'conduct_score': score,
            'appreciation': self._appreciation_for(score),
            'absences': fig['absences_count'],
            'absences_unjustified': fig['absences_unjustified_count'],
            'lates': fig['lates_count'],
        })
        return summary


class SilinaStudent(models.Model):
    _inherit = 'silina.student'

    absence_ids = fields.One2many(
        'silina.discipline.absence', 'student_id', string='Absences')
    late_ids = fields.One2many(
        'silina.discipline.late', 'student_id', string='Retards')
    sanction_ids = fields.One2many(
        'silina.discipline.sanction', 'student_id', string='Sanctions')
    conduct_ids = fields.One2many(
        'silina.discipline.conduct', 'student_id', string='Notes de conduite')
    absence_count = fields.Integer(compute='_compute_discipline_counts')
    late_count = fields.Integer(compute='_compute_discipline_counts')
    sanction_count = fields.Integer(compute='_compute_discipline_counts')

    @api.depends('absence_ids', 'late_ids', 'sanction_ids')
    def _compute_discipline_counts(self):
        for rec in self:
            rec.absence_count = len(rec.absence_ids)
            rec.late_count = len(rec.late_ids)
            rec.sanction_count = len(rec.sanction_ids)

    def _discipline_action(self, xmlid, name):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id(xmlid)
        action['name'] = name
        action['domain'] = [('student_id', '=', self.id)]
        action['context'] = {'default_student_id': self.id}
        return action

    def action_view_absences(self):
        return self._discipline_action(
            'silina_edu.action_discipline_absence', _('Absences'))

    def action_view_lates(self):
        return self._discipline_action(
            'silina_edu.action_discipline_late', _('Retards'))

    def action_view_sanctions(self):
        return self._discipline_action(
            'silina_edu.action_discipline_sanction', _('Sanctions'))
