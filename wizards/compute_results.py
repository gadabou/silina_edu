# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError


class ComputeResultsWizard(models.TransientModel):
    _name = 'silina.compute.results.wizard'
    _description = 'Calcul des résultats (période / annuel)'

    academic_year_id = fields.Many2one(
        'silina.academic.year', string='Année Scolaire', required=True,
        default=lambda self: self.env['silina.academic.year'].get_current_year())
    period_id = fields.Many2one(
        'silina.period', string='Période',
        domain="[('academic_year_id', '=', academic_year_id)]",
        help="Laisser vide pour calculer toutes les périodes de l'année.")
    classroom_ids = fields.Many2many(
        'silina.classroom', string='Classes',
        domain="[('academic_year_id', '=', academic_year_id)]",
        help="Laisser vide pour calculer toutes les classes de l'année.")
    compute_period = fields.Boolean(string='Résultats de période', default=True)
    compute_annual = fields.Boolean(string='Résultats annuels', default=True)
    force = fields.Boolean(
        string='Inclure les résultats définitifs',
        help="Recalcule aussi les résultats de période déjà validés (définitifs).")

    @api.onchange('academic_year_id')
    def _onchange_academic_year_id(self):
        self.period_id = False
        self.classroom_ids = False

    def action_compute(self):
        self.ensure_one()
        if not (self.compute_period or self.compute_annual):
            raise UserError(_("Sélectionnez au moins un type de résultat à calculer."))
        PeriodResult = self.env['silina.period.result']
        Annual = self.env['silina.annual.result']
        classrooms = self.classroom_ids or self.env['silina.classroom'].search(
            [('academic_year_id', '=', self.academic_year_id.id)])
        periods = self.period_id or self.env['silina.period'].search(
            [('academic_year_id', '=', self.academic_year_id.id)])
        if self.compute_period and not periods:
            raise UserError(_("Aucune période n'est définie pour cette année scolaire."))

        if self.compute_period:
            for classroom in classrooms:
                for period in periods:
                    PeriodResult.compute_for_classroom(classroom.id, period.id, force=self.force)
        if self.compute_annual:
            for classroom in classrooms:
                Annual.compute_for_classroom(classroom.id)

        if self.compute_period and not self.compute_annual:
            action = self.env.ref('silina_edu.action_period_result').read()[0]
            action['domain'] = [('classroom_id', 'in', classrooms.ids),
                                ('period_id', 'in', periods.ids)]
        else:
            action = self.env.ref('silina_edu.action_annual_result').read()[0]
            action['domain'] = [('classroom_id', 'in', classrooms.ids)]
        return action
