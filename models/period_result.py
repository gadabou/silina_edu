# -*- coding: utf-8 -*-
import logging

from odoo import models, fields, api, _
from odoo.exceptions import UserError

from . import result_utils as ru

_logger = logging.getLogger(__name__)


class PeriodResult(models.Model):
    """Résultat d'un élève pour une période (moyenne générale, rang, discipline)."""
    _name = 'silina.period.result'
    _description = 'Résultat de période'
    _order = 'academic_year_id desc, period_id, classroom_id, rank, student_id'
    _rec_name = 'student_id'

    student_id = fields.Many2one(
        'silina.student', string='Élève', required=True, ondelete='cascade', index=True)
    classroom_id = fields.Many2one(
        'silina.classroom', string='Classe', required=True, ondelete='cascade', index=True)
    academic_year_id = fields.Many2one(
        'silina.academic.year', string='Année Scolaire', required=True,
        ondelete='cascade', index=True)
    period_id = fields.Many2one(
        'silina.period', string='Période', required=True, ondelete='cascade', index=True)
    level_id = fields.Many2one(
        related='classroom_id.level_id', string='Niveau', store=True, readonly=True)
    degree = fields.Selection(
        related='classroom_id.degree', string='Degré', store=True, readonly=True)

    has_average = fields.Boolean(
        string='Moyenne disponible', default=False,
        help="Faux si l'élève n'a aucune note confirmée sur la période.")
    average = fields.Float(string='Moyenne générale', digits=(16, 2), aggregator='avg')
    rank = fields.Integer(string='Rang', help="Rang de compétition dans la classe (0 = non classé)", aggregator='avg')
    effectif = fields.Integer(string="Effectif classé", aggregator='avg')
    class_average = fields.Float(string='Moyenne de la classe', digits=(16, 2), aggregator='avg')
    class_max = fields.Float(string='Moyenne max. de la classe', digits=(16, 2), aggregator='avg')
    class_min = fields.Float(string='Moyenne min. de la classe', digits=(16, 2), aggregator='avg')
    mention = fields.Char(string='Mention')
    appreciation_scale = fields.Char(
        string='Appréciation (barème)',
        help="Appréciation de la moyenne générale selon le barème de la société.")
    average_words = fields.Char(
        string='Moyenne en lettres',
        help="Ex. « Sept virgule quatre-vingt-trois ».")
    result_phrase = fields.Char(
        string='Phrase de résultat', compute='_compute_result_phrase',
        help="Ex. « Sept virgule quatre-vingt-trois, Faible. »")

    # Alias explicites pour les gabarits (plus forte / plus faible moyenne de la classe)
    plus_forte = fields.Float(
        string='Plus forte moyenne', digits=(16, 2), compute='_compute_plus_fort_faible')
    plus_faible = fields.Float(
        string='Plus faible moyenne', digits=(16, 2), compute='_compute_plus_fort_faible')

    group_result_ids = fields.One2many(
        'silina.period.result.group', 'result_id', string='Résultats par groupe')

    absences = fields.Float(string='Absences (heures/jours)')
    absences_unjustified = fields.Float(string='Absences non justifiées')
    lates = fields.Integer(string='Retards')
    conduct_score = fields.Float(string='Note de conduite', digits=(16, 2), aggregator='avg')
    conduct_appreciation = fields.Char(string='Appréciation de conduite')

    appreciation_teacher = fields.Text(string='Appréciation du professeur principal')
    appreciation_director = fields.Text(string='Appréciation du directeur')

    state = fields.Selection([
        ('draft', 'Provisoire'),
        ('final', 'Définitif'),
    ], string='État', default='draft', required=True, index=True)

    line_ids = fields.One2many(
        'silina.period.result.line', 'result_id', string='Matières')
    line_count = fields.Integer(string='Nombre de matières', compute='_compute_line_count')

    _sql_constraints = [
        ('student_period_unique', 'unique(student_id, period_id)',
         'Un résultat existe déjà pour cet élève et cette période!'),
    ]

    @api.depends('class_max', 'class_min')
    def _compute_plus_fort_faible(self):
        for rec in self:
            rec.plus_forte = rec.class_max
            rec.plus_faible = rec.class_min

    @api.depends('average_words', 'appreciation_scale', 'has_average')
    def _compute_result_phrase(self):
        for rec in self:
            if rec.has_average and rec.average_words:
                rec.result_phrase = '%s, %s.' % (rec.average_words, rec.appreciation_scale or '')
            else:
                rec.result_phrase = ''

    def get_group_results(self):
        """Résultats par groupe (A, B, C), triés, uniquement les groupes non vides."""
        self.ensure_one()
        return self.group_result_ids.sorted(lambda g: g.group)

    @api.depends('line_ids')
    def _compute_line_count(self):
        for rec in self:
            rec.line_count = len(rec.line_ids)

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------
    def action_validate(self):
        self.write({'state': 'final'})
        return True

    def action_set_draft(self):
        self.write({'state': 'draft'})
        return True

    def action_recompute(self):
        """Recalcule la classe/période de chaque résultat sélectionné.

        Les résultats définitifs ne sont pas recalculés (remettre en provisoire d'abord).
        """
        pairs = {(r.classroom_id.id, r.period_id.id) for r in self}
        locked = self.filtered(lambda r: r.state == 'final')
        for classroom_id, period_id in pairs:
            self.compute_for_classroom(classroom_id, period_id)
        if locked:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Recalcul'),
                    'message': _('%s résultat(s) définitif(s) n\'ont pas été recalculés.') % len(locked),
                    'type': 'warning',
                    'sticky': False,
                },
            }
        return True

    # ------------------------------------------------------------------
    # Calcul
    # ------------------------------------------------------------------
    @api.model
    def compute_for_period(self, period_id, force=False):
        """Calcule les résultats de période de toutes les classes de l'année de la période."""
        period = self.env['silina.period'].browse(int(period_id))
        classrooms = self.env['silina.classroom'].search(
            [('academic_year_id', '=', period.academic_year_id.id)])
        results = self.browse()
        for classroom in classrooms:
            results |= self.compute_for_classroom(classroom.id, period.id, force=force)
        return results

    @api.model
    def _get_conduct_summary(self, student_id, period_id):
        """Appel défensif au module discipline (A3)."""
        if 'silina.discipline.conduct' not in self.env:
            return {}
        try:
            summary = self.env['silina.discipline.conduct'].get_summary(student_id, period_id)
            return summary or {}
        except Exception as e:  # noqa: BLE001 - la discipline ne doit jamais bloquer les moyennes
            _logger.warning("Discipline indisponible pour élève %s période %s : %s",
                            student_id, period_id, e)
            return {}

    @api.model
    def compute_for_classroom(self, classroom_id, period_id, force=False):
        """Crée/met à jour les résultats de période d'une classe.

        :param force: si True, recalcule aussi les résultats définitifs (et les
                      remet en provisoire s'ils sont modifiés ? non : conserve l'état).
        :return: recordset des silina.period.result de la classe pour la période.
        """
        classroom = self.env['silina.classroom'].browse(int(classroom_id))
        period = self.env['silina.period'].browse(int(period_id))
        if not classroom.exists() or not period.exists():
            raise UserError(_("Classe ou période introuvable."))
        if period.academic_year_id != classroom.academic_year_id:
            raise UserError(_("La période « %s » n'appartient pas à l'année scolaire de la classe « %s ».")
                            % (period.display_name, classroom.name))

        company = self.env.company
        max_mark = company.silina_max_mark or 20.0
        Line = self.env['silina.period.result.line']

        students = classroom.student_ids
        existing = {r.student_id.id: r for r in self.search(
            [('period_id', '=', period.id), ('student_id', 'in', students.ids)])}
        # Résultats d'élèves ayant changé de classe : on les rattache à cette classe.
        locked_ids = {sid for sid, r in existing.items() if r.state == 'final' and not force}

        # Coefficients par classe (affectations), repli sur la matière.
        coef_map = {a.subject_id.id: a.coefficient for a in classroom.subject_assignment_ids}

        # --- notes confirmées de la période, par élève et matière
        exam_results = self.env['silina.exam.result'].search([
            ('student_id', 'in', students.ids),
            ('period_id', '=', period.id),
            ('state', '=', 'confirmed'),
        ])
        marks = {}  # {student_id: {subject_id: {'devoir': [...], 'composition': [...]}}}
        subjects = {}
        for r in exam_results:
            if getattr(r, 'is_absent', False):  # champ éventuel d'absence : exclu, jamais 0
                continue
            scaled = ru.scale_mark(r.marks_obtained, r.total_marks, max_mark)
            if scaled is None:
                continue
            kind = 'composition' if r.evaluation_kind == 'composition' else 'devoir'
            marks.setdefault(r.student_id.id, {}).setdefault(
                r.subject_id.id, {'devoir': [], 'composition': []})[kind].append(scaled)
            subjects[r.subject_id.id] = r.subject_id

        # --- moyennes par élève
        data = {}  # student_id -> {'subj','coef','count','hw','comp': {sid: ...}, 'avg': x}
        for student in students:
            if student.id in locked_ids:
                res = existing[student.id]
                subj = {l.subject_id.id: l.average for l in res.line_ids}
                hw = {l.subject_id.id: (l.homework_average if l.has_homework else None)
                      for l in res.line_ids}
                comp = {l.subject_id.id: (l.composition_average if l.has_composition else None)
                        for l in res.line_ids}
                coef = {l.subject_id.id: l.coefficient for l in res.line_ids}
                count = {l.subject_id.id: l.nb_notes for l in res.line_ids}
                avg = res.average if res.has_average else None
            else:
                subj, coef, count, hw, comp = {}, {}, {}, {}, {}
                for sid, kinds in marks.get(student.id, {}).items():
                    hw[sid] = ru.mean(kinds['devoir'])
                    comp[sid] = ru.mean(kinds['composition'])
                    # Règle du bulletin : moyenne simple (devoirs, composition)
                    subj[sid] = ru.simple_average(hw[sid], comp[sid])
                    count[sid] = len(kinds['devoir']) + len(kinds['composition'])
                    coef[sid] = coef_map.get(sid, subjects[sid].coefficient or 1.0)
                avg, _cs = ru.weighted_average((subj[s], coef[s]) for s in subj)
            data[student.id] = {'subj': subj, 'coef': coef, 'count': count,
                                'hw': hw, 'comp': comp, 'avg': avg}

        # --- rangs et stats de classe
        general_ranks = ru.competition_ranks({sid: d['avg'] for sid, d in data.items()})
        c_avg, c_max, c_min = ru.class_stats([d['avg'] for d in data.values()])
        effectif = len(general_ranks)

        subject_ranks, subject_eff = {}, {}
        all_subject_ids = {s for d in data.values() for s in d['subj']}
        for sid in all_subject_ids:
            vals = {st: d['subj'].get(sid) for st, d in data.items()}
            subject_ranks[sid] = ru.competition_ranks(vals)
            subject_eff[sid] = len(subject_ranks[sid])

        # --- groupes de matières (A/B/C) : totaux, moyenne et rang par groupe
        group_of = {s.id: (s.report_group or 'C')
                    for s in self.env['silina.subject'].browse(list(all_subject_ids))}
        group_data = {}  # student_id -> {group: (total_coef, total_points, average)}
        for st, d in data.items():
            by_group = {}
            for sid, s_avg in d['subj'].items():
                by_group.setdefault(group_of.get(sid, 'C'), []).append((s_avg, d['coef'][sid]))
            group_data[st] = {g: ru.group_totals(items) for g, items in by_group.items()}
        group_ranks, group_eff = {}, {}
        for g in {g for gd in group_data.values() for g in gd}:
            vals = {st: gd[g][2] for st, gd in group_data.items() if g in gd}
            group_ranks[g] = ru.competition_ranks(vals)
            group_eff[g] = len(group_ranks[g])

        # --- écriture
        results = self.browse()
        for student in students:
            d = data[student.id]
            res = existing.get(student.id)
            if student.id in locked_ids:
                results |= res
                continue
            has_avg = d['avg'] is not None
            vals = {
                'classroom_id': classroom.id,
                'academic_year_id': classroom.academic_year_id.id,
                'has_average': has_avg,
                'average': ru.round_half_up(d['avg']) if has_avg else 0.0,
                'rank': general_ranks.get(student.id, 0),
                'effectif': effectif,
                'class_average': ru.round_half_up(c_avg),
                'class_max': ru.round_half_up(c_max),
                'class_min': ru.round_half_up(c_min),
                'mention': company.mention_for(d['avg']) if has_avg else '',
                'appreciation_scale': company.appreciation_for(d['avg']) if has_avg else '',
                'average_words': ru.average_in_words(d['avg']) if has_avg else '',
            }
            summary = self._get_conduct_summary(student.id, period.id)
            if summary:
                vals.update({
                    'absences': summary.get('absences') or 0.0,
                    'absences_unjustified': summary.get('absences_unjustified') or 0.0,
                    'lates': int(summary.get('lates') or 0),
                    'conduct_score': summary.get('conduct_score') or 0.0,
                    'conduct_appreciation': summary.get('appreciation') or '',
                })
            old_appr = {}
            if res:
                old_appr = {l.subject_id.id: l.appreciation for l in res.line_ids}
            line_cmds = [(5, 0, 0)]
            for sid in sorted(d['subj'], key=lambda s: (subjects[s].sequence if s in subjects else 0, s)):
                s_avg = d['subj'][sid]
                coef = d['coef'][sid]
                hw_avg, comp_avg = d['hw'].get(sid), d['comp'].get(sid)
                line_cmds.append((0, 0, {
                    'subject_id': sid,
                    'coefficient': coef,
                    'homework_average': ru.round_half_up(hw_avg) if hw_avg is not None else 0.0,
                    'has_homework': hw_avg is not None,
                    'composition_average': ru.round_half_up(comp_avg) if comp_avg is not None else 0.0,
                    'has_composition': comp_avg is not None,
                    'average': ru.round_half_up(s_avg),
                    'weighted_average': ru.round_half_up(s_avg * coef),
                    'rank': subject_ranks[sid].get(student.id, 0),
                    'effectif': subject_eff[sid],
                    'nb_notes': d['count'][sid],
                    'mention': company.mention_for(s_avg),
                    'appreciation_scale': company.appreciation_for(s_avg),
                    'appreciation': old_appr.get(sid) or '',
                }))
            vals['line_ids'] = line_cmds
            vals['group_result_ids'] = [(5, 0, 0)] + [(0, 0, {
                'group': g,
                'total_coef': tc,
                'total_points': ru.round_half_up(tp),
                'average': ru.round_half_up(ga) if ga is not None else 0.0,
                'has_average': ga is not None,
                'rank': group_ranks[g].get(student.id, 0),
                'effectif': group_eff[g],
                'appreciation': company.appreciation_for(ga) if ga is not None else '',
            }) for g, (tc, tp, ga) in sorted(group_data[student.id].items())]
            if res:
                res.write(vals)
            else:
                vals.update({'student_id': student.id, 'period_id': period.id,
                             'state': 'draft'})
                res = self.create(vals)
            results |= res
        return results


class PeriodResultLine(models.Model):
    """Moyenne d'un élève dans une matière pour une période."""
    _name = 'silina.period.result.line'
    _description = 'Ligne de résultat de période'
    _order = 'result_id, subject_sequence, subject_id'

    result_id = fields.Many2one(
        'silina.period.result', string='Résultat', required=True,
        ondelete='cascade', index=True)
    student_id = fields.Many2one(
        related='result_id.student_id', string='Élève', store=True, readonly=True)
    classroom_id = fields.Many2one(
        related='result_id.classroom_id', string='Classe', store=True, readonly=True)
    period_id = fields.Many2one(
        related='result_id.period_id', string='Période', store=True, readonly=True)
    subject_id = fields.Many2one(
        'silina.subject', string='Matière', required=True, ondelete='cascade')
    subject_sequence = fields.Integer(
        related='subject_id.sequence', string='Séquence', store=True, readonly=True)
    coefficient = fields.Float(string='Coefficient')
    homework_average = fields.Float(string='Moyenne des devoirs', digits=(16, 2))
    has_homework = fields.Boolean(string='Devoirs disponibles')
    composition_average = fields.Float(string='Note de composition', digits=(16, 2))
    has_composition = fields.Boolean(string='Composition disponible')
    average = fields.Float(
        string='Moyenne matière', digits=(16, 2),
        help="Moyenne simple de (moyenne des devoirs, note de composition) quand les deux "
             "existent, sinon celle qui existe.")
    weighted_average = fields.Float(string='Moyenne pondérée', digits=(16, 2))
    rank = fields.Integer(string='Rang')
    effectif = fields.Integer(string='Effectif')
    nb_notes = fields.Integer(string='Nb de notes')
    mention = fields.Char(string='Mention')
    appreciation = fields.Char(string='Appréciation')
    appreciation_scale = fields.Char(
        string='Appréciation (barème)',
        help="Appréciation automatique de la moyenne matière selon le barème de la société.")
    teacher_id = fields.Many2one(
        'silina.teacher', string='Professeur', compute='_compute_teacher_id')
    teacher_name = fields.Char(string='Nom du professeur', compute='_compute_teacher_id')
    report_group = fields.Selection(
        related='subject_id.report_group', string='Groupe', readonly=True)

    @api.depends('classroom_id', 'subject_id')
    def _compute_teacher_id(self):
        for line in self:
            assignment = line.classroom_id.subject_assignment_ids.filtered(
                lambda a: a.subject_id == line.subject_id)[:1]
            line.teacher_id = assignment.teacher_id
            line.teacher_name = assignment.teacher_id.display_short_name or ''


class PeriodResultGroup(models.Model):
    """Totaux, moyenne et rang d'un groupe de matières (A/B/C) pour une période."""
    _name = 'silina.period.result.group'
    _description = 'Résultat de période par groupe de matières'
    _order = 'result_id, group'

    result_id = fields.Many2one(
        'silina.period.result', string='Résultat', required=True,
        ondelete='cascade', index=True)
    student_id = fields.Many2one(
        related='result_id.student_id', string='Élève', store=True, readonly=True)
    classroom_id = fields.Many2one(
        related='result_id.classroom_id', string='Classe', store=True, readonly=True)
    period_id = fields.Many2one(
        related='result_id.period_id', string='Période', store=True, readonly=True)
    group = fields.Selection([
        ('A', 'Groupe A'), ('B', 'Groupe B'), ('C', 'Groupe C'),
    ], string='Groupe', required=True)
    group_label = fields.Char(string='Libellé', compute='_compute_group_label')
    total_coef = fields.Float(string='Total des coefficients', digits=(16, 2))
    total_points = fields.Float(
        string='Total des moy. × coef.', digits=(16, 2),
        help="Somme des « Moy.Mat.Coeffic. » du groupe.")
    has_average = fields.Boolean(string='Moyenne disponible', default=True)
    average = fields.Float(string='Moyenne du groupe', digits=(16, 2))
    rank = fields.Integer(string='Rang')
    effectif = fields.Integer(string='Effectif')
    appreciation = fields.Char(string='Appréciation')

    @api.depends('group')
    @api.depends_context('company')
    def _compute_group_label(self):
        company = self.env.company
        for rec in self:
            rec.group_label = company.group_label(rec.group)
