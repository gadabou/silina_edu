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

    report_group = fields.Selection([
        ('A', 'Groupe A'),
        ('B', 'Groupe B'),
        ('C', 'Groupe C'),
    ], string='Groupe du bulletin', default='C', required=True,
        help="Groupe de matières du bulletin (collège/lycée). Les libellés des groupes "
             "sont configurables dans les paramètres (A : Matières littéraires, "
             "B : Matières scientifiques, C : Autres matières).")
    report_group_label = fields.Char(
        string='Libellé du groupe', compute='_compute_report_group_label')
    livret_group = fields.Char(
        string='Groupe du livret',
        help="Libellé d'accolade du livret (primaire/préscolaire), ex. « Mathématiques », "
             "« EAC ». Les matières ayant le même libellé sont regroupées. "
             "Vide : la matière est affichée seule.")
    livret_name = fields.Char(
        string='Nom dans le livret',
        help="Nom court affiché dans le livret (ex. « Calcul mental »). Vide : nom de la matière.")

    color = fields.Integer(string='Couleur')
    description = fields.Text(string='Description')
    active = fields.Boolean(default=True)

    _sql_constraints = [
        ('code_unique', 'unique(code)', 'Le code de la matière doit être unique!'),
    ]

    @api.depends('report_group')
    @api.depends_context('company')
    def _compute_report_group_label(self):
        company = self.env.company
        for record in self:
            record.report_group_label = company.group_label(record.report_group)

    def get_livret_name(self):
        """Nom à afficher dans le livret."""
        self.ensure_one()
        return self.livret_name or self.name

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

    coefficient = fields.Float(
        string='Coefficient',
        compute='_compute_coefficient',
        store=True,
        readonly=False,
        help="Coefficient de la matière pour cette classe, utilisé pour les moyennes. "
             "Par défaut : coefficient de la matière (modifiable)."
    )

    hours_per_week = fields.Float(
        string='Heures par semaine',
        help="Nombre d'heures d'enseignement par semaine"
    )

    description = fields.Text(string='Notes')

    teacher_name = fields.Char(
        related='teacher_id.display_short_name', string='Nom du professeur', readonly=True)

    _sql_constraints = [
        ('assignment_unique', 'unique(classroom_id, subject_id)',
         'Une matière ne peut être affectée qu\'une seule fois par classe!'),
    ]

    @api.depends('subject_id')
    def _compute_coefficient(self):
        for record in self:
            # Ne remplace pas une valeur saisie : n'est recalculé que si la matière change.
            record.coefficient = record.subject_id.coefficient or 1.0

    @api.depends('classroom_id', 'subject_id', 'teacher_id')
    def name_get(self):
        result = []
        for record in self:
            name = f"{record.subject_id.name} - {record.classroom_id.name} ({record.teacher_id.name})"
            result.append((record.id, name))
        return result
