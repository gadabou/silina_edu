# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError

DECISIONS = [
    ('pending', 'En attente'),
    ('passed', 'Admis'),
    ('indulgence', 'Admis par indulgence'),
    ('repeat', 'Redouble'),
]
MANUAL_DECISIONS = [d for d in DECISIONS if d[0] != 'pending']


def compute_decision(average, has_average, pass_average, indulgence_average):
    """Règle de décision automatique (fonction pure, testable sans Odoo).

    - pas de moyenne                              -> 'pending'
    - moyenne >= moyenne de passage               -> 'passed'
    - indulgence <= moyenne < moyenne de passage  -> 'indulgence'
    - sinon                                       -> 'repeat'
    """
    if not has_average or average is None:
        return 'pending'
    avg = round(average, 2)
    if avg >= round(pass_average, 2):
        return 'passed'
    if avg >= round(indulgence_average, 2):
        return 'indulgence'
    return 'repeat'


class AnnualResultDecision(models.Model):
    _inherit = 'silina.annual.result'

    decision = fields.Selection(
        DECISIONS, string='Décision automatique', compute='_compute_decision',
        store=True, readonly=True, index=True)
    manual_decision = fields.Selection(
        MANUAL_DECISIONS, string='Décision manuelle', copy=False,
        help="Laisser vide pour appliquer la décision automatique.")
    decision_reason = fields.Text(
        string='Motif de la décision', copy=False,
        help="Obligatoire lorsque la décision manuelle diffère de la décision automatique.")
    final_decision = fields.Selection(
        DECISIONS, string='Décision finale', compute='_compute_final_decision',
        store=True, readonly=True, index=True)
    decision_label = fields.Char(
        string='Libellé de la décision', compute='_compute_decision_label')
    promotion_state = fields.Selection([
        ('todo', 'Non traité'),
        ('done', 'Traité'),
    ], string='Passage', default='todo', required=True, copy=False, index=True)

    # ------------------------------------------------------------------
    # Calculs
    # ------------------------------------------------------------------
    @api.depends('annual_average', 'has_average')
    def _compute_decision(self):
        company = self.env.company
        pass_avg = company.silina_pass_average
        indulgence_avg = company.silina_indulgence_average
        for rec in self:
            rec.decision = compute_decision(
                rec.annual_average, rec.has_average, pass_avg, indulgence_avg)

    @api.depends('decision', 'manual_decision')
    def _compute_final_decision(self):
        for rec in self:
            rec.final_decision = rec.manual_decision or rec.decision

    @api.depends('final_decision')
    def _compute_decision_label(self):
        labels = dict(self._fields['final_decision']._description_selection(self.env))
        for rec in self:
            rec.decision_label = labels.get(rec.final_decision, '') if rec.final_decision else ''

    @api.constrains('manual_decision', 'decision', 'decision_reason')
    def _check_decision_reason(self):
        for rec in self:
            if (rec.manual_decision and rec.decision != 'pending'
                    and rec.manual_decision != rec.decision
                    and not (rec.decision_reason or '').strip()):
                raise ValidationError(_(
                    "Un motif est obligatoire lorsque la décision manuelle diffère de la "
                    "décision automatique (%s).") % rec.student_id.name)

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------
    def _set_manual_decision(self, value):
        for rec in self:
            if rec.promotion_state == 'done':
                raise UserError(_(
                    "Le passage de %s est déjà traité : la décision ne peut plus être modifiée.")
                    % rec.student_id.name)
            if (rec.decision != 'pending' and value != rec.decision
                    and not (rec.decision_reason or '').strip()):
                raise UserError(_(
                    "Renseignez d'abord le motif de la décision pour %s : la décision manuelle "
                    "diffère de la décision automatique.") % rec.student_id.name)
        self.write({'manual_decision': value})
        return True

    def action_admit(self):
        return self._set_manual_decision('passed')

    def action_admit_indulgence(self):
        return self._set_manual_decision('indulgence')

    def action_make_repeat(self):
        return self._set_manual_decision('repeat')

    def action_reset_decision(self):
        self.filtered(lambda r: r.promotion_state != 'done').write(
            {'manual_decision': False, 'decision_reason': False})
        return True

    def action_reset_promotion_state(self):
        self.write({'promotion_state': 'todo'})
        return True
