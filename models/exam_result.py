from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class ExamResult(models.Model):
    _name = 'silina.exam.result'
    _description = 'Résultat d\'Examen'
    _order = 'exam_id, student_id, subject_id'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    exam_id = fields.Many2one(
        'silina.exam',
        string='Examen',
        required=True,
        ondelete='cascade',
        tracking=True
    )

    student_id = fields.Many2one(
        'silina.student',
        string='Élève',
        required=True,
        ondelete='cascade',
        tracking=True
    )

    subject_id = fields.Many2one(
        'silina.subject',
        string='Matière',
        required=True,
        ondelete='cascade',
        tracking=True
    )

    classroom_id = fields.Many2one(
        related='student_id.classroom_id',
        string='Classe',
        store=True,
        readonly=True
    )

    academic_year_id = fields.Many2one(
        related='exam_id.academic_year_id',
        string='Année Scolaire',
        store=True,
        readonly=True
    )

    period_id = fields.Many2one(
        related='exam_id.period_id',
        string='Période',
        store=True,
        readonly=True
    )

    evaluation_kind = fields.Selection(
        related='exam_id.evaluation_kind', string="Nature de l'évaluation",
        store=True, readonly=True)
    composition_number = fields.Integer(
        related='exam_id.composition_number', string='N° de composition',
        store=True, readonly=True)

    # Notes
    marks_obtained = fields.Float(
        string='Note obtenue',
        tracking=True
    )
    total_marks = fields.Float(
        related='exam_id.total_marks',
        string='Note maximale',
        store=True,
        readonly=True
    )
    passing_marks = fields.Float(
        related='exam_id.passing_marks',
        string='Note de passage',
        store=True,
        readonly=True
    )

    # Calculs
    percentage = fields.Float(
        string='Pourcentage',
        compute='_compute_percentage',
        store=True
    )
    grade = fields.Char(
        string='Mention',
        compute='_compute_grade',
        store=True
    )
    is_passed = fields.Boolean(
        string='Admis',
        compute='_compute_is_passed',
        store=True
    )

    coefficient = fields.Float(
        related='subject_id.coefficient',
        string='Coefficient',
        store=True,
        readonly=True
    )

    weighted_marks = fields.Float(
        string='Note pondérée',
        compute='_compute_weighted_marks',
        store=True,
        help="Note obtenue × Coefficient"
    )

    # Informations complémentaires
    remarks = fields.Text(string='Observations')
    teacher_id = fields.Many2one(
        'silina.teacher',
        string='Enseignant',
        help="Enseignant qui a évalué"
    )

    state = fields.Selection([
        ('draft', 'Brouillon'),
        ('confirmed', 'Confirmé'),
    ], string='État', default='draft', required=True, tracking=True)

    _sql_constraints = [
        ('result_unique', 'unique(exam_id, student_id, subject_id)',
         'Un résultat existe déjà pour cet examen, élève et matière!'),
    ]

    @api.constrains('marks_obtained', 'total_marks')
    def _check_marks(self):
        for record in self:
            if record.marks_obtained < 0:
                raise ValidationError(_('La note obtenue ne peut pas être négative!'))
            if record.marks_obtained > record.total_marks:
                raise ValidationError(_('La note obtenue ne peut pas être supérieure à la note maximale!'))

    @api.depends('marks_obtained', 'total_marks')
    def _compute_percentage(self):
        for record in self:
            if record.total_marks > 0:
                record.percentage = (record.marks_obtained / record.total_marks) * 100
            else:
                record.percentage = 0.0

    @api.depends('percentage')
    def _compute_grade(self):
        for record in self:
            percentage = record.percentage
            if percentage >= 90:
                record.grade = 'Excellent'
            elif percentage >= 80:
                record.grade = 'Très Bien'
            elif percentage >= 70:
                record.grade = 'Bien'
            elif percentage >= 60:
                record.grade = 'Assez Bien'
            elif percentage >= 50:
                record.grade = 'Passable'
            else:
                record.grade = 'Insuffisant'

    @api.depends('marks_obtained', 'passing_marks')
    def _compute_is_passed(self):
        for record in self:
            record.is_passed = record.marks_obtained >= record.passing_marks

    @api.depends('marks_obtained', 'coefficient')
    def _compute_weighted_marks(self):
        for record in self:
            record.weighted_marks = record.marks_obtained * record.coefficient

    @api.model
    def get_monthly_grid(self, student, academic_year=None):
        """Grille des compositions mensuelles d'un élève (livret).

        Notes confirmées des examens ``evaluation_kind = 'composition'`` de
        l'année, ramenées sur le barème de la société (20), moyennées si
        plusieurs évaluations pour la même matière et le même mois.
        Absents/sans note exclus (jamais 0).

        :param student: silina.student
        :param academic_year: silina.academic.year (défaut : année de l'élève)
        :return: dict
            {
              'grid':          {subject_id: {n: note}},        n = 1..12
              'subject_totals': {subject_id: total des mois},
              'months':        [n, ...] mois ayant au moins une note (trié),
              'totals':        {n: somme des notes du mois},
              'averages':      {n: moyenne pondérée par coefficient (affectations de la
                                classe, repli coefficient matière) },
              'ranks':         {n: rang dans la classe (1,1,3), absent si non classé},
              'effectifs':     {n: nb d'élèves classés ce mois},
            }
        """
        from . import result_utils as ru
        student.ensure_one()
        year = academic_year or student.academic_year_id
        company = self.env.company
        max_mark = company.silina_max_mark or 20.0
        classroom = student.classroom_id
        classmates = classroom.student_ids if classroom else student
        results = self.search([
            ('student_id', 'in', classmates.ids),
            ('academic_year_id', '=', year.id),
            ('evaluation_kind', '=', 'composition'),
            ('composition_number', '>', 0),
            ('state', '=', 'confirmed'),
        ])
        coef_map = {}
        if classroom:
            coef_map = {a.subject_id.id: a.coefficient for a in classroom.subject_assignment_ids}
        raw = {}  # {student_id: {n: {subject_id: [notes]}}}
        coef_default = {}
        for r in results:
            if getattr(r, 'is_absent', False):
                continue
            scaled = ru.scale_mark(r.marks_obtained, r.total_marks, max_mark)
            if scaled is None:
                continue
            raw.setdefault(r.student_id.id, {}).setdefault(
                r.composition_number, {}).setdefault(r.subject_id.id, []).append(scaled)
            coef_default[r.subject_id.id] = r.subject_id.coefficient or 1.0

        def coef_of(sid):
            return coef_map.get(sid) or coef_default.get(sid) or 1.0

        # {student_id: {n: (total, average)}}
        per_month = {}
        for sid_student, months in raw.items():
            per_month[sid_student] = {}
            for n, subjects in months.items():
                avgs = {sub: ru.mean(v) for sub, v in subjects.items()}
                total = sum(a for a in avgs.values() if a is not None)
                avg, _cs = ru.weighted_average((a, coef_of(sub)) for sub, a in avgs.items())
                per_month[sid_student][n] = (total, avg)

        grid, subject_totals, totals, averages, ranks, effectifs = {}, {}, {}, {}, {}, {}
        mine = raw.get(student.id, {})
        for n, subjects in mine.items():
            for sub, values in subjects.items():
                note = ru.round_half_up(ru.mean(values))
                grid.setdefault(sub, {})[n] = note
        for sub, months in grid.items():
            subject_totals[sub] = ru.round_half_up(sum(months.values()))
        months_list = sorted({n for m in per_month.values() for n in m})
        for n in months_list:
            if n in per_month.get(student.id, {}):
                total, avg = per_month[student.id][n]
                totals[n] = ru.round_half_up(total)
                averages[n] = ru.round_half_up(avg) if avg is not None else None
            month_avgs = {st: m[n][1] for st, m in per_month.items() if n in m}
            month_ranks = ru.competition_ranks(month_avgs)
            effectifs[n] = len(month_ranks)
            if student.id in month_ranks:
                ranks[n] = month_ranks[student.id]
        return {
            'grid': grid,
            'subject_totals': subject_totals,
            'months': sorted(totals),
            'totals': totals,
            'averages': averages,
            'ranks': ranks,
            'effectifs': effectifs,
        }

    def action_confirm(self):
        self.ensure_one()
        self.state = 'confirmed'
        return True

    def action_draft(self):
        self.ensure_one()
        self.state = 'draft'
        return True

    @api.depends('student_id', 'exam_id', 'subject_id')
    def name_get(self):
        result = []
        for record in self:
            name = f"{record.student_id.name} - {record.exam_id.name} - {record.subject_id.name}"
            result.append((record.id, name))
        return result


class ExamResultSummary(models.Model):
    """Modèle pour calculer les moyennes générales par examen et élève"""
    _name = 'silina.exam.result.summary'
    _description = 'Résumé des Résultats d\'Examen'
    _order = 'exam_id, classroom_id, rank'
    _rec_name = 'student_id'

    exam_id = fields.Many2one(
        'silina.exam',
        string='Examen',
        required=True,
        ondelete='cascade'
    )

    student_id = fields.Many2one(
        'silina.student',
        string='Élève',
        required=True,
        ondelete='cascade'
    )

    classroom_id = fields.Many2one(
        related='student_id.classroom_id',
        string='Classe',
        store=True,
        readonly=True
    )

    academic_year_id = fields.Many2one(
        related='exam_id.academic_year_id',
        string='Année Scolaire',
        store=True,
        readonly=True
    )

    # Calculs
    total_marks_obtained = fields.Float(
        string='Total des notes',
        compute='_compute_totals',
        store=True
    )
    total_marks_possible = fields.Float(
        string='Total possible',
        compute='_compute_totals',
        store=True
    )
    total_weighted_marks = fields.Float(
        string='Total pondéré',
        compute='_compute_totals',
        store=True
    )
    total_coefficients = fields.Float(
        string='Total des coefficients',
        compute='_compute_totals',
        store=True
    )

    average = fields.Float(
        string='Moyenne générale',
        compute='_compute_average',
        store=True
    )
    percentage = fields.Float(
        string='Pourcentage',
        compute='_compute_percentage',
        store=True
    )
    grade = fields.Char(
        string='Mention',
        compute='_compute_grade',
        store=True
    )
    is_passed = fields.Boolean(
        string='Admis',
        compute='_compute_is_passed',
        store=True
    )

    rank = fields.Integer(
        string='Rang',
        help="Rang de l'élève dans sa classe"
    )

    result_ids = fields.One2many(
        'silina.exam.result',
        compute='_compute_result_ids',
        string='Résultats détaillés'
    )

    _sql_constraints = [
        ('summary_unique', 'unique(exam_id, student_id)',
         'Un résumé existe déjà pour cet examen et élève!'),
    ]

    def _compute_result_ids(self):
        for record in self:
            record.result_ids = self.env['silina.exam.result'].search([
                ('exam_id', '=', record.exam_id.id),
                ('student_id', '=', record.student_id.id)
            ])

    @api.depends('result_ids', 'result_ids.marks_obtained', 'result_ids.weighted_marks')
    def _compute_totals(self):
        for record in self:
            results = self.env['silina.exam.result'].search([
                ('exam_id', '=', record.exam_id.id),
                ('student_id', '=', record.student_id.id),
                ('state', '=', 'confirmed')
            ])
            record.total_marks_obtained = sum(results.mapped('marks_obtained'))
            record.total_marks_possible = sum(results.mapped('total_marks'))
            record.total_weighted_marks = sum(results.mapped('weighted_marks'))
            record.total_coefficients = sum(results.mapped('coefficient'))

    @api.depends('total_weighted_marks', 'total_coefficients')
    def _compute_average(self):
        for record in self:
            if record.total_coefficients > 0:
                record.average = record.total_weighted_marks / record.total_coefficients
            else:
                record.average = 0.0

    @api.depends('total_marks_obtained', 'total_marks_possible')
    def _compute_percentage(self):
        for record in self:
            if record.total_marks_possible > 0:
                record.percentage = (record.total_marks_obtained / record.total_marks_possible) * 100
            else:
                record.percentage = 0.0

    @api.depends('average')
    def _compute_grade(self):
        for record in self:
            average = record.average
            if average >= 18:
                record.grade = 'Excellent'
            elif average >= 16:
                record.grade = 'Très Bien'
            elif average >= 14:
                record.grade = 'Bien'
            elif average >= 12:
                record.grade = 'Assez Bien'
            elif average >= 10:
                record.grade = 'Passable'
            else:
                record.grade = 'Insuffisant'

    @api.depends('average', 'exam_id.passing_marks')
    def _compute_is_passed(self):
        for record in self:
            record.is_passed = record.average >= record.exam_id.passing_marks

    @api.model
    def generate_summaries(self, exam_id):
        """Générer les résumés pour tous les élèves d'un examen"""
        exam = self.env['silina.exam'].browse(exam_id)
        students = self.env['silina.exam.result'].search([
            ('exam_id', '=', exam_id),
            ('state', '=', 'confirmed')
        ]).mapped('student_id')

        summaries = []
        for student in students:
            existing = self.search([
                ('exam_id', '=', exam_id),
                ('student_id', '=', student.id)
            ])
            if not existing:
                summaries.append({
                    'exam_id': exam_id,
                    'student_id': student.id,
                })

        if summaries:
            created = self.create(summaries)
            # Calculer les rangs par classe
            for classroom in created.mapped('classroom_id'):
                classroom_summaries = created.filtered(lambda s: s.classroom_id == classroom)
                sorted_summaries = classroom_summaries.sorted(key=lambda s: s.average, reverse=True)
                for rank, summary in enumerate(sorted_summaries, 1):
                    summary.rank = rank

        return True
