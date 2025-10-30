from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
from datetime import date


class Student(models.Model):
    _name = 'silina.student'
    _description = 'Élève'
    _order = 'name'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    # Informations de base
    name = fields.Char(
        string='Nom complet',
        required=True,
        tracking=True
    )
    first_name = fields.Char(
        string='Prénom',
        required=True,
        tracking=True
    )
    last_name = fields.Char(
        string='Nom',
        required=True,
        tracking=True
    )
    registration_number = fields.Char(
        string='Numéro de matricule',
        required=True,
        copy=False,
        readonly=True,
        default=lambda self: _('Nouveau'),
        tracking=True
    )

    image_1920 = fields.Image(
        string='Photo',
        max_width=1920,
        max_height=1920
    )
    image_128 = fields.Image(
        string='Photo (128)',
        related='image_1920',
        max_width=128,
        max_height=128,
        store=True
    )

    gender = fields.Selection([
        ('male', 'Masculin'),
        ('female', 'Féminin'),
    ], string='Sexe', required=True, tracking=True)

    date_of_birth = fields.Date(
        string='Date de naissance',
        required=True,
        tracking=True
    )
    age = fields.Integer(
        string='Âge',
        compute='_compute_age',
        store=True
    )
    place_of_birth = fields.Char(
        string='Lieu de naissance',
        tracking=True
    )

    nationality = fields.Many2one(
        'res.country',
        string='Nationalité',
        tracking=True
    )

    blood_group = fields.Selection([
        ('a+', 'A+'),
        ('a-', 'A-'),
        ('b+', 'B+'),
        ('b-', 'B-'),
        ('o+', 'O+'),
        ('o-', 'O-'),
        ('ab+', 'AB+'),
        ('ab-', 'AB-'),
    ], string='Groupe sanguin')

    # Informations de contact
    email = fields.Char(string='Email')
    phone = fields.Char(string='Téléphone')
    mobile = fields.Char(string='Mobile')

    # Adresse
    street = fields.Char(string='Rue')
    street2 = fields.Char(string='Rue 2')
    city = fields.Char(string='Ville')
    state_id = fields.Many2one('res.country.state', string='État')
    zip = fields.Char(string='Code postal')
    country_id = fields.Many2one('res.country', string='Pays')

    # Informations académiques
    academic_year_id = fields.Many2one(
        'silina.academic.year',
        string='Année Scolaire',
        required=True,
        tracking=True,
        default=lambda self: self.env['silina.academic.year'].get_current_year()
    )

    classroom_id = fields.Many2one(
        'silina.classroom',
        string='Classe',
        tracking=True,
        domain="[('academic_year_id', '=', academic_year_id)]"
    )

    level_id = fields.Many2one(
        related='classroom_id.level_id',
        string='Niveau',
        store=True,
        readonly=True
    )

    degree = fields.Selection(
        related='classroom_id.degree',
        string='Degré',
        store=True,
        readonly=True
    )

    enrollment_date = fields.Date(
        string='Date d\'inscription',
        default=fields.Date.today,
        tracking=True
    )

    state = fields.Selection([
        ('draft', 'Brouillon'),
        ('enrolled', 'Inscrit'),
        ('promoted', 'Admis'),
        ('repeated', 'Redoublant'),
        ('transferred', 'Transféré'),
        ('graduated', 'Diplômé'),
        ('expelled', 'Exclu'),
    ], string='État', default='draft', required=True, tracking=True)

    # Parents/Tuteurs
    parent_ids = fields.Many2many(
        'silina.parent',
        'student_parent_rel',
        'student_id',
        'parent_id',
        string='Parents/Tuteurs'
    )

    father_name = fields.Char(string='Nom du père')
    mother_name = fields.Char(string='Nom de la mère')
    guardian_name = fields.Char(string='Nom du tuteur')

    # Documents
    document_ids = fields.One2many(
        'silina.student.document',
        'student_id',
        string='Documents'
    )

    # Résultats d'examens
    exam_result_ids = fields.One2many(
        'silina.exam.result',
        'student_id',
        string='Résultats d\'examens'
    )

    # Frais scolaires (gérés via factures account.move)
    currency_id = fields.Many2one(
        'res.currency',
        string='Devise',
        default=lambda self: self.env.company.currency_id
    )

    # Contact Odoo pour la facturation
    partner_id = fields.Many2one(
        'res.partner',
        string='Contact lié',
        help="Contact Odoo lié pour la facturation des frais scolaires",
        readonly=True
    )

    # Informations médicales
    allergies = fields.Text(string='Allergies')
    medical_conditions = fields.Text(string='Conditions médicales')
    emergency_contact_name = fields.Char(string='Contact d\'urgence')
    emergency_contact_phone = fields.Char(string='Téléphone d\'urgence')

    # Autres
    notes = fields.Text(string='Notes')
    active = fields.Boolean(default=True)

    _sql_constraints = [
        ('registration_number_unique', 'unique(registration_number)',
         'Le numéro de matricule doit être unique!'),
    ]

    @api.onchange('name')
    def _onchange_name(self):
        """Quand on saisit le nom complet, diviser en Nom et Prénom
        UNIQUEMENT si on tape directement dans le champ Nom complet"""
        # Ne diviser QUE si le nom complet est différent de "last_name + first_name"
        # Cela évite de rediviser quand on met à jour depuis _onchange_names()
        if self.name:
            # Vérifier si le nom complet correspond déjà à last_name + first_name
            expected_name = ''
            if self.last_name and self.first_name:
                expected_name = f"{self.last_name} {self.first_name}"
            elif self.last_name:
                expected_name = self.last_name
            elif self.first_name:
                expected_name = self.first_name

            # Si le nom complet est différent de ce qui est attendu,
            # c'est que l'utilisateur a tapé directement dedans
            if self.name.strip() != expected_name.strip():
                # Diviser le nom complet en mots
                parts = self.name.strip().split()
                if len(parts) >= 1:
                    # Le premier mot = Nom (en MAJUSCULES)
                    self.last_name = parts[0].upper()
                    # Le reste = Prénom (Capitalize chaque mot)
                    if len(parts) > 1:
                        prenom_parts = parts[1:]
                        self.first_name = ' '.join([word.capitalize() for word in prenom_parts])
                    else:
                        self.first_name = ''

    @api.onchange('last_name')
    def _onchange_last_name(self):
        """S'assurer que tous les mots du nom sont en MAJUSCULES"""
        if self.last_name:
            # Mettre tous les mots du nom en majuscules
            self.last_name = ' '.join([word.upper() for word in self.last_name.split()])

    @api.onchange('first_name')
    def _onchange_first_name(self):
        """S'assurer que tous les mots du prénom sont en Capitalize"""
        if self.first_name:
            # Capitaliser chaque mot du prénom
            self.first_name = ' '.join([word.capitalize() for word in self.first_name.split()])

    @api.onchange('first_name', 'last_name')
    def _onchange_names(self):
        """Quand on modifie Nom ou Prénom, mettre à jour le nom complet"""
        if self.first_name and self.last_name:
            # Nom complet = NOM + Prénom (Nom toujours en premier)
            self.name = f"{self.last_name} {self.first_name}"
        elif self.last_name:
            self.name = self.last_name
        elif self.first_name:
            self.name = self.first_name

    @api.depends('date_of_birth')
    def _compute_age(self):
        today = date.today()
        for record in self:
            if record.date_of_birth:
                age = today.year - record.date_of_birth.year
                if today.month < record.date_of_birth.month or \
                   (today.month == record.date_of_birth.month and today.day < record.date_of_birth.day):
                    age -= 1
                record.age = age
            else:
                record.age = 0

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('registration_number', _('Nouveau')) == _('Nouveau'):
                vals['registration_number'] = self.env['ir.sequence'].next_by_code(
                    'silina.student'
                ) or _('Nouveau')

            # Formater le nom (tous les mots en MAJUSCULES)
            if vals.get('last_name'):
                vals['last_name'] = ' '.join([word.upper() for word in vals['last_name'].split()])

            # Formater le prénom (tous les mots en Capitalize)
            if vals.get('first_name'):
                vals['first_name'] = ' '.join([word.capitalize() for word in vals['first_name'].split()])

            # Logique de division du nom complet
            if vals.get('name') and not (vals.get('first_name') or vals.get('last_name')):
                parts = vals['name'].strip().split()
                if len(parts) >= 1:
                    vals['last_name'] = parts[0].upper()
                    if len(parts) > 1:
                        prenom_parts = parts[1:]
                        vals['first_name'] = ' '.join([word.capitalize() for word in prenom_parts])

            # Mise à jour du nom complet si prénom/nom fournis
            if vals.get('first_name') and vals.get('last_name'):
                # Nom complet = NOM + Prénom (Nom toujours en premier)
                vals['name'] = f"{vals['last_name']} {vals['first_name']}"
            elif vals.get('last_name'):
                vals['name'] = vals['last_name']
            elif vals.get('first_name'):
                vals['name'] = vals['first_name']

        students = super().create(vals_list)
        # Créer automatiquement le contact partner pour chaque élève
        for student in students:
            if not student.partner_id:
                student._create_partner()
        return students

    def write(self, vals):
        # Formater le nom (tous les mots en MAJUSCULES)
        if vals.get('last_name'):
            vals['last_name'] = ' '.join([word.upper() for word in vals['last_name'].split()])

        # Formater le prénom (tous les mots en Capitalize)
        if vals.get('first_name'):
            vals['first_name'] = ' '.join([word.capitalize() for word in vals['first_name'].split()])

        # Logique de division du nom complet
        if vals.get('name') and not (vals.get('first_name') or vals.get('last_name')):
            parts = vals['name'].strip().split()
            if len(parts) >= 1:
                vals['last_name'] = parts[0].upper()
                if len(parts) > 1:
                    prenom_parts = parts[1:]
                    vals['first_name'] = ' '.join([word.capitalize() for word in prenom_parts])

        # Mise à jour du nom complet si prénom/nom modifiés
        if 'first_name' in vals or 'last_name' in vals:
            for record in self:
                first_name = vals.get('first_name', record.first_name)
                last_name = vals.get('last_name', record.last_name)
                if first_name and last_name:
                    # Nom complet = NOM + Prénom (Nom toujours en premier)
                    vals['name'] = f"{last_name} {first_name}"
                elif last_name:
                    vals['name'] = last_name
                elif first_name:
                    vals['name'] = first_name

        return super().write(vals)

    def action_enroll(self):
        self.ensure_one()
        if not self.classroom_id:
            raise ValidationError(_('Veuillez assigner une classe à l\'élève avant de l\'inscrire!'))
        self.state = 'enrolled'
        return True

    def action_promote(self):
        self.ensure_one()
        self.state = 'promoted'
        return True

    def action_repeat(self):
        self.ensure_one()
        self.state = 'repeated'
        return True

    def action_generate_report_card(self):
        self.ensure_one()
        return {
            'name': _('Générer le bulletin de notes'),
            'type': 'ir.actions.act_window',
            'res_model': 'silina.generate.report.card.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_student_ids': [(6, 0, self.ids)]}
        }

    def _create_partner(self):
        """Créer un contact res.partner pour l'élève"""
        self.ensure_one()
        if self.partner_id:
            return self.partner_id

        # Trouver le contact du parent responsable financier pour le lier
        parent_partner = False
        for parent in self.parent_ids:
            if parent.is_financial_responsible and parent.partner_id:
                parent_partner = parent.partner_id
                break

        partner_vals = {
            'name': self.name,
            'email': self.email,
            'phone': self.phone,
            'mobile': self.mobile,
            'street': self.street,
            'street2': self.street2,
            'city': self.city,
            'state_id': self.state_id.id if self.state_id else False,
            'zip': self.zip,
            'country_id': self.country_id.id if self.country_id else False,
            'comment': f'Élève - Matricule: {self.registration_number}',
            'type': 'contact',
            'customer_rank': 1,  # Marquer comme client
        }

        # Si un parent responsable financier existe, le lier comme contact parent
        if parent_partner:
            partner_vals['parent_id'] = parent_partner.id

        partner = self.env['res.partner'].sudo().create(partner_vals)
        self.partner_id = partner.id
        return partner
