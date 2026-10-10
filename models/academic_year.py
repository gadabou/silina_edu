from datetime import timedelta

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class AcademicYear(models.Model):
    _name = 'silina.academic.year'
    _description = 'Année Scolaire'
    _order = 'date_start desc'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(
        string='Nom',
        required=True,
        tracking=True,
        help="Ex: 2024-2025"
    )
    code = fields.Char(
        string='Code',
        required=True,
        copy=False,
        tracking=True
    )
    date_start = fields.Date(
        string='Date de début',
        required=True,
        tracking=True
    )
    date_end = fields.Date(
        string='Date de fin',
        tracking=True
    )
    state = fields.Selection([
        ('draft', 'Brouillon'),
        ('active', 'Active'),
        ('closed', 'Fermée'),
    ], string='État', default='draft', required=True, tracking=True)

    is_current = fields.Boolean(
        string='Année en cours',
        default=False,
        tracking=True,
        help="Une seule année peut être active à la fois"
    )

    # Compteurs
    student_count = fields.Integer(
        string='Nombre d\'élèves',
        compute='_compute_counts'
    )
    classroom_count = fields.Integer(
        string='Nombre de classes',
        compute='_compute_counts'
    )

    description = fields.Text(string='Description')

    period_type = fields.Selection([
        ('trimester', 'Trimestres'),
        ('semester', 'Semestres'),
    ], string='Découpage en périodes', default='trimester', required=True)
    period_ids = fields.One2many(
        'silina.period',
        'academic_year_id',
        string='Périodes'
    )

    _sql_constraints = [
        ('code_unique', 'unique(code)', 'Le code de l\'année scolaire doit être unique!'),
    ]

    @api.constrains('date_start', 'date_end')
    def _check_dates(self):
        for record in self:
            if record.date_end and record.date_start >= record.date_end:
                raise ValidationError(_('La date de fin doit être postérieure à la date de début!'))

    @api.constrains('is_current')
    def _check_current_year(self):
        for record in self:
            if record.is_current:
                other_current = self.search([
                    ('is_current', '=', True),
                    ('id', '!=', record.id)
                ])
                if other_current:
                    raise ValidationError(_('Une seule année scolaire peut être active à la fois!'))

    def _compute_counts(self):
        for record in self:
            record.student_count = self.env['silina.student'].search_count([
                ('academic_year_id', '=', record.id)
            ])
            record.classroom_count = self.env['silina.classroom'].search_count([
                ('academic_year_id', '=', record.id)
            ])

    def action_activate(self):
        self.ensure_one()
        # Désactiver toutes les autres années
        other_years = self.search([('is_current', '=', True), ('id', '!=', self.id)])
        other_years.write({'is_current': False})

        self.write({
            'state': 'active',
            'is_current': True
        })
        return True

    def action_close(self):
        self.ensure_one()
        self.write({
            'state': 'closed',
            'is_current': False
        })
        return True

    def action_generate_periods(self):
        """Génère 3 trimestres ou 2 semestres répartis équitablement entre
        la date de début et la date de fin. Ne recrée pas les périodes existantes."""
        Period = self.env['silina.period']
        for year in self:
            if not year.date_start or not year.date_end:
                raise ValidationError(_(
                    "Renseignez la date de début et la date de fin de l'année scolaire "
                    "avant de générer les périodes."))
            if year.period_ids:
                continue
            if year.period_type == 'semester':
                count, code_prefix = 2, 'S'
                names = [_('1er Semestre'), _('2e Semestre')]
            else:
                count, code_prefix = 3, 'T'
                names = [_('1er Trimestre'), _('2e Trimestre'), _('3e Trimestre')]
            total_days = (year.date_end - year.date_start).days + 1
            start = year.date_start
            for i in range(count):
                if i == count - 1:
                    end = year.date_end
                else:
                    end = year.date_start + timedelta(days=total_days * (i + 1) // count - 1)
                Period.create({
                    'academic_year_id': year.id,
                    'name': names[i],
                    'code': '%s%d' % (code_prefix, i + 1),
                    'sequence': (i + 1) * 10,
                    'date_start': start,
                    'date_end': end,
                })
                start = end + timedelta(days=1)
        return True

    @api.model_create_multi
    def create(self, vals_list):
        years = super().create(vals_list)
        for year in years:
            year._copy_classrooms_from_previous_year()
        return years

    def _copy_classrooms_from_previous_year(self):
        """Recrée automatiquement, à la création d'une nouvelle année scolaire,
        les classes de l'année précédente (structure uniquement, sans les élèves).

        L'année précédente est celle dont la date de début est la plus récente
        parmi celles antérieures à la nouvelle année. Le code de classe étant
        unique par année, on conserve les mêmes noms et codes."""
        self.ensure_one()
        if self.env.context.get('skip_classroom_copy') or not self.date_start:
            return
        Classroom = self.env['silina.classroom']
        # Ne rien faire si des classes existent déjà pour cette année
        if Classroom.search_count([('academic_year_id', '=', self.id)]):
            return
        previous = self.search([
            ('date_start', '<', self.date_start),
            ('id', '!=', self.id),
        ], order='date_start desc', limit=1)
        if not previous:
            return
        for classroom in Classroom.search([('academic_year_id', '=', previous.id)]):
            # Sécurité : éviter un doublon de code dans la nouvelle année
            if Classroom.search_count([
                ('code', '=', classroom.code),
                ('academic_year_id', '=', self.id),
            ]):
                continue
            Classroom.create({
                'name': classroom.name,
                'code': classroom.code,
                'level_id': classroom.level_id.id,
                'main_teacher_id': classroom.main_teacher_id.id or False,
                'description': classroom.description,
                'academic_year_id': self.id,
            })

    @api.model
    def get_current_year(self):
        """Retourne l'année scolaire active"""
        return self.search([('is_current', '=', True)], limit=1)
