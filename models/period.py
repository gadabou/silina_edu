from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class Period(models.Model):
    _name = 'silina.period'
    _description = 'Période scolaire'
    _order = 'academic_year_id desc, sequence, date_start'

    academic_year_id = fields.Many2one(
        'silina.academic.year',
        string='Année Scolaire',
        required=True,
        ondelete='cascade',
        index=True,
        default=lambda self: self.env['silina.academic.year'].get_current_year(),
    )
    name = fields.Char(string='Nom', required=True, help="Ex: 1er Trimestre")
    code = fields.Char(string='Code', required=True, help="Ex: T1, S1")
    sequence = fields.Integer(string='Séquence', default=10)
    date_start = fields.Date(string='Date de début', required=True)
    date_end = fields.Date(string='Date de fin', required=True)
    state = fields.Selection([
        ('open', 'Ouverte'),
        ('closed', 'Clôturée'),
    ], string='État', default='open', required=True)

    _sql_constraints = [
        ('code_year_unique', 'unique(academic_year_id, code)',
         'Le code de la période doit être unique pour une année scolaire!'),
    ]

    @api.constrains('date_start', 'date_end')
    def _check_dates(self):
        for record in self:
            if record.date_start and record.date_end and record.date_start > record.date_end:
                raise ValidationError(_('La date de fin doit être postérieure à la date de début!'))

    def action_close(self):
        self.write({'state': 'closed'})
        return True

    def action_reopen(self):
        self.write({'state': 'open'})
        return True

    @api.depends('name', 'academic_year_id.name')
    def _compute_display_name(self):
        for record in self:
            if record.academic_year_id:
                record.display_name = '%s (%s)' % (record.name, record.academic_year_id.name)
            else:
                record.display_name = record.name or ''
