from odoo import models, fields, api, _


class Subject(models.Model):
    _name = 'silina.subject'
    _description = 'Matière'
    _order = 'sequence, name'

    name = fields.Char(
        string='Nom',
        required=True,
        help="Ex: Mathématiques, Français, Histoire, etc."
    )
    code = fields.Char(
        string='Code',
        required=True,
        help="Ex: MATH, FR, HIST, etc."
    )

    subject_type = fields.Selection([
        ('theory', 'Théorique'),
        ('practical', 'Pratique'),
        ('both', 'Théorique et Pratique'),
    ], string='Type', default='theory', required=True)

    degree_ids = fields.Many2many(
        'silina.level',
        'subject_level_rel',
        'subject_id',
        'level_id',
        string='Niveaux',
        help="Niveaux pour lesquels cette matière est enseignée"
    )

    coefficient = fields.Float(
        string='Coefficient',
        default=1.0,
        help="Coefficient pour le calcul de la moyenne"
    )

    sequence = fields.Integer(
        string='Séquence',
        default=10,
        help="Ordre d'affichage"
    )

    color = fields.Integer(string='Couleur')
    description = fields.Text(string='Description')
    active = fields.Boolean(default=True)

    _sql_constraints = [
        ('code_unique', 'unique(code)', 'Le code de la matière doit être unique!'),
    ]

    @api.depends('name', 'code')
    def name_get(self):
        result = []
        for record in self:
            name = f"[{record.code}] {record.name}"
            result.append((record.id, name))
        return result


class SubjectAssignment(models.Model):
    _name = 'silina.subject.assignment'
    _description = 'Affectation Matière-Enseignant-Classe'
    _order = 'classroom_id, subject_id'

    classroom_id = fields.Many2one(
        'silina.classroom',
        string='Classe',
        required=True,
        ondelete='cascade'
    )

    subject_id = fields.Many2one(
        'silina.subject',
        string='Matière',
        required=True,
        ondelete='cascade'
    )

    teacher_id = fields.Many2one(
        'silina.teacher',
        string='Enseignant',
        required=True,
        ondelete='cascade'
    )

    academic_year_id = fields.Many2one(
        related='classroom_id.academic_year_id',
        string='Année Scolaire',
        store=True,
        readonly=True
    )

    hours_per_week = fields.Float(
        string='Heures par semaine',
        help="Nombre d'heures d'enseignement par semaine"
    )

    description = fields.Text(string='Notes')

    _sql_constraints = [
        ('assignment_unique', 'unique(classroom_id, subject_id)',
         'Une matière ne peut être affectée qu\'une seule fois par classe!'),
    ]

    @api.depends('classroom_id', 'subject_id', 'teacher_id')
    def name_get(self):
        result = []
        for record in self:
            name = f"{record.subject_id.name} - {record.classroom_id.name} ({record.teacher_id.name})"
            result.append((record.id, name))
        return result
