from odoo import models, fields, api, _


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

    amount = fields.Monetary(
        string='Montant',
        required=True,
        currency_field='currency_id'
    )
    currency_id = fields.Many2one(
        'res.currency',
        string='Devise',
        default=lambda self: self.env.company.currency_id
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

    is_mandatory = fields.Boolean(
        string='Obligatoire',
        default=True,
        help="Si coché, ces frais seront automatiquement ajoutés à tous les étudiants"
    )

    allow_installment = fields.Boolean(
        string='Paiement par tranches',
        default=True,
        help="Autoriser le paiement en plusieurs tranches"
    )

    installment_count = fields.Integer(
        string='Nombre de tranches',
        default=1,
        help="Nombre de tranches pour le paiement"
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

    @api.model_create_multi
    def create(self, vals_list):
        """Créer automatiquement un article pour la facturation si non fourni"""
        records = super().create(vals_list)
        for record in records:
            if not record.product_id:
                product_vals = {
                    'name': record.name,
                    'type': 'service',
                    'list_price': record.amount,
                    'categ_id': self.env.ref('product.product_category_all').id,
                    'default_code': record.code,
                }
                product = self.env['product.product'].create(product_vals)
                record.product_id = product.id
        return records
