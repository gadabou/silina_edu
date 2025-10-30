from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class Classroom(models.Model):
    _name = 'silina.classroom'
    _description = 'Classe'
    _order = 'academic_year_id desc, level_id, name'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(
        string='Nom',
        required=True,
        tracking=True,
        help="Ex: CP1-A, 6ème-B, etc."
    )
    code = fields.Char(
        string='Code',
        required=True,
        copy=False,
        tracking=True
    )

    academic_year_id = fields.Many2one(
        'silina.academic.year',
        string='Année Scolaire',
        required=True,
        tracking=True,
        default=lambda self: self.env['silina.academic.year'].get_current_year()
    )

    level_id = fields.Many2one(
        'silina.level',
        string='Niveau',
        required=True,
        tracking=True
    )

    degree = fields.Selection(
        related='level_id.degree',
        string='Degré',
        store=True,
        readonly=True
    )

    main_teacher_id = fields.Many2one(
        'silina.teacher',
        string='Enseignant Principal',
        tracking=True
    )

    # Élèves
    student_ids = fields.One2many(
        'silina.student',
        'classroom_id',
        string='Élèves'
    )
    student_count = fields.Integer(
        string='Nombre d\'élèves',
        compute='_compute_student_count',
        store=True
    )

    # Matières et enseignants
    subject_assignment_ids = fields.One2many(
        'silina.subject.assignment',
        'classroom_id',
        string='Affectations de matières'
    )

    description = fields.Text(string='Description')
    active = fields.Boolean(default=True)

    _sql_constraints = [
        ('code_unique', 'unique(code, academic_year_id)',
         'Le code de la classe doit être unique pour une année scolaire!'),
    ]

    @api.depends('student_ids')
    def _compute_student_count(self):
        for record in self:
            record.student_count = len(record.student_ids)

    @api.onchange('level_id')
    def _onchange_level_id(self):
        """Remplir automatiquement le nom et le code avec le niveau sélectionné"""
        if self.level_id:
            # Remplir le nom avec le nom du niveau
            self.name = self.level_id.name
            # Remplir le code avec le code du niveau (sans espaces)
            self.code = self.level_id.code.replace(' ', '') if self.level_id.code else ''

    @api.onchange('code')
    def _onchange_code(self):
        """S'assurer que le code est toujours en un seul mot (sans espaces)"""
        if self.code:
            self.code = self.code.replace(' ', '')

    @api.depends('name', 'level_id', 'academic_year_id')
    def name_get(self):
        result = []
        for record in self:
            name = f"{record.name} ({record.academic_year_id.name})"
            result.append((record.id, name))
        return result

    def action_view_students(self):
        self.ensure_one()
        return {
            'name': _('Élèves'),
            'type': 'ir.actions.act_window',
            'res_model': 'silina.student',
            'view_mode': 'list,form',
            'domain': [('classroom_id', '=', self.id)],
            'context': {
                'default_classroom_id': self.id,
                'default_academic_year_id': self.academic_year_id.id,
            }
        }
