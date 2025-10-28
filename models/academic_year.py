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
        required=True,
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

    _sql_constraints = [
        ('code_unique', 'unique(code)', 'Le code de l\'année scolaire doit être unique!'),
    ]

    @api.constrains('date_start', 'date_end')
    def _check_dates(self):
        for record in self:
            if record.date_start >= record.date_end:
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

    @api.model
    def get_current_year(self):
        """Retourne l'année scolaire active"""
        return self.search([('is_current', '=', True)], limit=1)
