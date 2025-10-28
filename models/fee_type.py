from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
from dateutil.relativedelta import relativedelta


class FeeType(models.Model):
    _name = 'silina.fee.type'
    _description = 'Type de Frais'
    _order = 'sequence, name'

    name = fields.Char(
        string='Nom',
        required=True,
        help="Ex: Frais de scolarité, Frais d'inscription, Frais de cantine, etc."
    )
    code = fields.Char(
        string='Code',
        required=True,
        help="Ex: SCOL, INSC, CANT, etc."
    )

    fee_category = fields.Selection([
        ('tuition', 'Frais de scolarité'),
        ('registration', 'Frais d\'inscription'),
        ('exam', 'Frais d\'examen'),
        ('transport', 'Frais de transport'),
        ('canteen', 'Frais de cantine'),
        ('library', 'Frais de bibliothèque'),
        ('activities', 'Activités extrascolaires'),
        ('other', 'Autres'),
    ], string='Catégorie', required=True)

    total_amount = fields.Monetary(
        string='Montant total',
        required=True,
        currency_field='currency_id',
        help="Montant total du frais (somme de toutes les tranches)"
    )
    currency_id = fields.Many2one(
        'res.currency',
        string='Devise',
        default=lambda self: self.env.company.currency_id
    )

    # Tranches de paiement
    installment_ids = fields.One2many(
        'silina.fee.type.installment',
        'fee_type_id',
        string='Tranches de paiement',
        help="Définissez les tranches de paiement avec leurs montants et échéances"
    )
    installment_count = fields.Integer(
        string='Nombre de tranches',
        compute='_compute_installment_count',
        store=True
    )

    # Applicabilité
    level_ids = fields.Many2many(
        'silina.level',
        'fee_type_level_rel',
        'fee_type_id',
        'level_id',
        string='Niveaux',
        help="Niveaux pour lesquels ces frais sont applicables"
    )

    academic_year_id = fields.Many2one(
        'silina.academic.year',
        string='Année scolaire',
        help="Année scolaire pour laquelle ces frais sont applicables"
    )

    is_mandatory = fields.Boolean(
        string='Obligatoire',
        default=True,
        help="Si coché, ces frais seront automatiquement ajoutés à tous les élèves"
    )

    # Intégration facturation
    product_id = fields.Many2one(
        'product.product',
        string='Article',
        help="Article lié pour la facturation"
    )

    account_id = fields.Many2one(
        'account.account',
        string='Compte comptable',
        domain="[('account_type', '=', 'income')]",
        help="Compte comptable pour la facturation"
    )

    sequence = fields.Integer(
        string='Séquence',
        default=10,
        help="Ordre d'affichage"
    )

    description = fields.Text(string='Description')
    active = fields.Boolean(default=True)

    _sql_constraints = [
        ('code_unique', 'unique(code)', 'Le code du type de frais doit être unique!'),
    ]

    @api.depends('installment_ids')
    def _compute_installment_count(self):
        for record in self:
            record.installment_count = len(record.installment_ids)

    @api.constrains('installment_ids', 'total_amount')
    def _check_installment_amounts(self):
        """Vérifier que la somme des tranches correspond au montant total"""
        for record in self:
            if record.installment_ids:
                installment_sum = sum(record.installment_ids.mapped('amount'))
                if abs(installment_sum - record.total_amount) > 0.01:
                    raise ValidationError(_(
                        'La somme des tranches (%s) ne correspond pas au montant total (%s)!'
                    ) % (installment_sum, record.total_amount))

    @api.model_create_multi
    def create(self, vals_list):
        """Créer automatiquement un article pour la facturation si non fourni"""
        records = super().create(vals_list)
        for record in records:
            if not record.product_id:
                product_vals = {
                    'name': record.name,
                    'type': 'service',
                    'list_price': record.total_amount,
                    'categ_id': self.env.ref('product.product_category_all').id,
                    'default_code': record.code,
                }
                product = self.env['product.product'].create(product_vals)
                record.product_id = product.id
        return records

    def action_generate_invoices(self):
        """Générer les factures pour tous les élèves éligibles"""
        self.ensure_one()

        # Ouvrir le wizard de génération de factures
        return {
            'name': _('Générer les Factures'),
            'type': 'ir.actions.act_window',
            'res_model': 'silina.generate.fee.invoices.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_fee_type_id': self.id,
            }
        }


class FeeTypeInstallment(models.Model):
    _name = 'silina.fee.type.installment'
    _description = 'Tranche de Type de Frais'
    _order = 'fee_type_id, sequence'

    fee_type_id = fields.Many2one(
        'silina.fee.type',
        string='Type de frais',
        required=True,
        ondelete='cascade'
    )

    name = fields.Char(
        string='Nom de la tranche',
        required=True,
        help="Ex: 1ère tranche, Tranche octobre, etc."
    )

    sequence = fields.Integer(
        string='Séquence',
        default=10,
        help="Ordre de la tranche"
    )

    amount = fields.Monetary(
        string='Montant',
        required=True,
        currency_field='currency_id',
        help="Montant de cette tranche"
    )
    currency_id = fields.Many2one(
        related='fee_type_id.currency_id',
        string='Devise',
        store=True
    )

    due_date_type = fields.Selection([
        ('fixed', 'Date fixe'),
        ('relative', 'Date relative'),
    ], string='Type d\'échéance', default='relative', required=True)

    due_date = fields.Date(
        string='Date d\'échéance',
        help="Date d'échéance fixe pour cette tranche"
    )

    due_days = fields.Integer(
        string='Délai (jours)',
        default=30,
        help="Nombre de jours après la date de début de l'année scolaire"
    )

    description = fields.Text(string='Description')

    _sql_constraints = [
        ('amount_positive', 'CHECK(amount > 0)', 'Le montant de la tranche doit être positif!'),
    ]
