from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class FeePayment(models.Model):
    _name = 'silina.fee.payment'
    _description = 'Paiement de Frais'
    _order = 'payment_date desc, id desc'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(
        string='Référence',
        required=True,
        copy=False,
        readonly=True,
        default=lambda self: _('Nouveau'),
        tracking=True
    )

    student_id = fields.Many2one(
        'silina.student',
        string='Élève',
        required=True,
        tracking=True
    )

    student_fee_id = fields.Many2one(
        'silina.student.fee',
        string='Frais',
        required=True,
        domain="[('student_id', '=', student_id)]",
        tracking=True
    )

    installment_id = fields.Many2one(
        'silina.fee.installment',
        string='Tranche',
        domain="[('student_fee_id', '=', student_fee_id)]",
        help="Tranche de paiement concernée"
    )

    amount = fields.Monetary(
        string='Montant',
        required=True,
        currency_field='currency_id',
        tracking=True
    )
    currency_id = fields.Many2one(
        'res.currency',
        string='Devise',
        default=lambda self: self.env.company.currency_id
    )

    payment_date = fields.Date(
        string='Date de paiement',
        required=True,
        default=fields.Date.today,
        tracking=True
    )

    payment_method = fields.Selection([
        ('cash', 'Espèces'),
        ('bank_transfer', 'Virement bancaire'),
        ('check', 'Chèque'),
        ('card', 'Carte bancaire'),
        ('mobile_money', 'Mobile Money'),
        ('other', 'Autre'),
    ], string='Mode de paiement', required=True, default='cash', tracking=True)

    reference = fields.Char(
        string='Référence de paiement',
        help="Numéro de chèque, référence de virement, etc."
    )

    # Intégration comptable
    journal_id = fields.Many2one(
        'account.journal',
        string='Journal',
        domain="[('type', 'in', ['cash', 'bank'])]"
    )

    payment_id = fields.Many2one(
        'account.payment',
        string='Paiement comptable',
        readonly=True,
        copy=False
    )

    state = fields.Selection([
        ('draft', 'Brouillon'),
        ('paid', 'Payé'),
        ('cancelled', 'Annulé'),
    ], string='État', default='draft', required=True, tracking=True)

    # Reçu
    receipt_number = fields.Char(
        string='Numéro de reçu',
        readonly=True,
        copy=False
    )

    notes = fields.Text(string='Notes')

    _sql_constraints = [
        ('amount_positive', 'CHECK(amount > 0)', 'Le montant doit être positif!'),
    ]

    @api.constrains('amount', 'student_fee_id')
    def _check_amount(self):
        for record in self:
            if record.state == 'paid':
                total_paid = sum(record.student_fee_id.payment_ids.filtered(
                    lambda p: p.state == 'paid'
                ).mapped('amount'))
                if total_paid > record.student_fee_id.amount:
                    raise ValidationError(_(
                        'Le montant total des paiements (%s) dépasse le montant des frais (%s)!'
                    ) % (total_paid, record.student_fee_id.amount))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('Nouveau')) == _('Nouveau'):
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'silina.fee.payment'
                ) or _('Nouveau')
        return super().create(vals_list)

    def action_confirm(self):
        """Confirmer le paiement"""
        self.ensure_one()
        if self.state != 'draft':
            raise ValidationError(_('Seuls les paiements en brouillon peuvent être confirmés!'))

        # Générer le numéro de reçu
        if not self.receipt_number:
            self.receipt_number = self.env['ir.sequence'].next_by_code(
                'silina.fee.payment.receipt'
            ) or _('Nouveau')

        self.state = 'paid'

        # Créer le paiement comptable si un journal est spécifié
        if self.journal_id:
            self._create_account_payment()

        return True

    def action_cancel(self):
        """Annuler le paiement"""
        self.ensure_one()
        if self.payment_id and self.payment_id.state == 'posted':
            raise ValidationError(_(
                'Impossible d\'annuler ce paiement car le paiement comptable est validé!'
            ))

        self.state = 'cancelled'
        return True

    def action_draft(self):
        """Remettre en brouillon"""
        self.ensure_one()
        if self.payment_id:
            raise ValidationError(_(
                'Impossible de remettre en brouillon un paiement avec un paiement comptable!'
            ))

        self.state = 'draft'
        return True

    def _create_account_payment(self):
        """Créer un paiement comptable"""
        self.ensure_one()
        if self.payment_id:
            return

        # Trouver le partenaire (parent responsable financier)
        partner = False
        for parent in self.student_id.parent_ids:
            if parent.is_financial_responsible and parent.partner_id:
                partner = parent.partner_id
                break

        if not partner:
            return

        payment_vals = {
            'payment_type': 'inbound',
            'partner_type': 'customer',
            'partner_id': partner.id,
            'amount': self.amount,
            'currency_id': self.currency_id.id,
            'date': self.payment_date,
            'journal_id': self.journal_id.id,
            'ref': f"{self.name} - {self.student_id.name}",
        }

        payment = self.env['account.payment'].create(payment_vals)
        self.payment_id = payment.id

    def action_print_receipt(self):
        """Imprimer le reçu de paiement"""
        self.ensure_one()
        return self.env.ref('silina_edu.action_report_fee_receipt').report_action(self)

    @api.depends('student_id', 'amount', 'payment_date')
    def name_get(self):
        result = []
        for record in self:
            name = f"{record.name} - {record.student_id.name} - {record.amount}"
            result.append((record.id, name))
        return result
