# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError

from . import result_utils as ru


class AnnualResult(models.Model):
    """Résultat annuel d'un élève (moyenne des moyennes de période).

    La décision de passage (admis / indulgence / redoublement) n'est PAS portée
    ici : elle est ajoutée par le module de passage (A4) en héritant de ce modèle.
    """
    _name = 'silina.annual.result'
    _description = 'Résultat annuel'
    _order = 'academic_year_id desc, classroom_id, rank, student_id'
    _rec_name = 'student_id'

    student_id = fields.Many2one(
        'silina.student', string='Élève', required=True, ondelete='cascade', index=True)
    academic_year_id = fields.Many2one(
        'silina.academic.year', string='Année Scolaire', required=True,
        ondelete='cascade', index=True)
    classroom_id = fields.Many2one(
        'silina.classroom', string='Classe', required=True, ondelete='cascade', index=True)
    level_id = fields.Many2one(
        related='classroom_id.level_id', string='Niveau', store=True, readonly=True)
    degree = fields.Selection(
        related='classroom_id.degree', string='Degré', store=True, readonly=True)

    period_result_ids = fields.One2many(
        'silina.period.result', compute='_compute_period_results', string='Résultats de période')
    period_count = fields.Integer(
        string='Périodes prises en compte', compute='_compute_period_results')

    has_average = fields.Boolean(string='Moyenne disponible', default=False)
    annual_average = fields.Float(string='Moyenne annuelle', digits=(16, 2), aggregator='avg')
    rank = fields.Integer(string='Rang', aggregator='avg')
    effectif = fields.Integer(string='Effectif classé', aggregator='avg')
    class_average = fields.Float(string='Moyenne de la classe', digits=(16, 2), aggregator='avg')
    class_max = fields.Float(string='Moyenne max. de la classe', digits=(16, 2), aggregator='avg')
    class_min = fields.Float(string='Moyenne min. de la classe', digits=(16, 2), aggregator='avg')
    mention = fields.Char(string='Mention')
    total_absences = fields.Float(string='Total absences')
    total_lates = fields.Integer(string='Total retards')

    _sql_constraints = [
        ('student_year_unique', 'unique(student_id, academic_year_id)',
         'Un résultat annuel existe déjà pour cet élève et cette année scolaire!'),
    ]

    def _compute_period_results(self):
        for rec in self:
            results = self.env['silina.period.result'].search([
                ('student_id', '=', rec.student_id.id),
                ('academic_year_id', '=', rec.academic_year_id.id),
                ('has_average', '=', True),
            ])
            rec.period_result_ids = results
            rec.period_count = len(results)

    def action_recompute(self):
        for classroom in self.mapped('classroom_id'):
            self.compute_for_classroom(classroom.id)
        return True

    @api.model
    def compute_for_year(self, year_id):
        """Calcule les résultats annuels de toutes les classes de l'année."""
        classrooms = self.env['silina.classroom'].search([('academic_year_id', '=', int(year_id))])
        results = self.browse()
        for classroom in classrooms:
            results |= self.compute_for_classroom(classroom.id)
        return results

    @api.model
    def compute_for_classroom(self, classroom_id):
        """Crée/met à jour les résultats annuels d'une classe.

        Moyenne annuelle = moyenne simple des moyennes de période disponibles
        (résultats de période de l'élève dans l'année, toutes classes confondues).
        Les résultats de période doivent avoir été calculés au préalable.
        """
        classroom = self.env['silina.classroom'].browse(int(classroom_id))
        if not classroom.exists():
            raise UserError(_("Classe introuvable."))
        company = self.env.company
        year = classroom.academic_year_id
        students = classroom.student_ids

        pres = self.env['silina.period.result'].search([
            ('student_id', 'in', students.ids),
            ('academic_year_id', '=', year.id),
        ])
        per_student = {}
        for r in pres:
            per_student.setdefault(r.student_id.id, self.env['silina.period.result'])
            per_student[r.student_id.id] |= r

        averages = {}
        for student in students:
            rs = per_student.get(student.id, pres.browse())
            averages[student.id] = ru.mean([r.average for r in rs if r.has_average])

        ranks = ru.competition_ranks(averages)
        c_avg, c_max, c_min = ru.class_stats(list(averages.values()))
        existing = {r.student_id.id: r for r in self.search(
            [('academic_year_id', '=', year.id), ('student_id', 'in', students.ids)])}

        results = self.browse()
        for student in students:
            avg = averages[student.id]
            rs = per_student.get(student.id, pres.browse())
            has_avg = avg is not None
            vals = {
                'classroom_id': classroom.id,
                'has_average': has_avg,
                'annual_average': round(avg, 2) if has_avg else 0.0,
                'rank': ranks.get(student.id, 0),
                'effectif': len(ranks),
                'class_average': round(c_avg, 2),
                'class_max': round(c_max, 2),
                'class_min': round(c_min, 2),
                'mention': company.mention_for(avg) if has_avg else '',
                'total_absences': sum(rs.mapped('absences')),
                'total_lates': sum(rs.mapped('lates')),
            }
            res = existing.get(student.id)
            if res:
                res.write(vals)
            else:
                vals.update({'student_id': student.id, 'academic_year_id': year.id})
                res = self.create(vals)
            results |= res
        return results
