from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class StudentFeePayment(models.TransientModel):
    _name = 'silina.student.fee.payment.wizard'
    _description = 'Paiement des Frais Scolaires'

    student_id = fields.Many2one(
        'silina.student',
        string='Élève',
        required=True
    )

    fee_type_id = fields.Many2one(
        'silina.fee.type',
        string='Type de frais',
        help="Requis uniquement pour créer une nouvelle facture. "
             "Ignoré si une facture existante est sélectionnée."
    )

    # Règlement d'une facture existante, éventuellement d'une année antérieure.
    payment_target = fields.Selection([
        ('existing', 'Régler une facture existante'),
        ('new', 'Créer une nouvelle facture de frais'),
    ], string='Objet du paiement', default='existing', required=True)

    invoice_id = fields.Many2one(
        'account.move',
        string='Facture à régler',
        domain="[('id', 'in', available_invoice_ids)]",
        help="Factures impayées de l'élève, toutes années scolaires confondues."
    )

    available_invoice_ids = fields.Many2many(
        'account.move',
        compute='_compute_available_invoices',
        string='Factures réglables'
    )

    invoice_academic_year_id = fields.Many2one(
        'silina.academic.year',
        string='Année de la facture',
        compute='_compute_invoice_info'
    )
    invoice_residual = fields.Monetary(
        string='Reste dû sur la facture',
        compute='_compute_invoice_info',
        currency_field='currency_id'
    )
    is_previous_year_payment = fields.Boolean(
        string="Facture d'une année antérieure",
        compute='_compute_invoice_info'
    )

    installment_id = fields.Many2one(
        'silina.fee.type.installment',
        string='Tranche à payer',
        domain="[('fee_type_id', '=', fee_type_id)]"
    )

    payment_type = fields.Selection([
        ('full', 'Paiement complet'),
        ('installment', 'Paiement par tranche'),
    ], string='Type de paiement', default='full', required=True)

    amount = fields.Monetary(
        string='Montant à payer',
        required=True,
        currency_field='currency_id',
        compute='_compute_amount',
        readonly=False,
        store=True
    )

    payment_method = fields.Selection([
        ('cash', 'Espèces'),
        ('bank_transfer', 'Virement bancaire'),
        ('check', 'Chèque'),
        ('mobile_money', 'Mobile Money'),
    ], string='Mode de paiement', default='cash', required=True)

    payment_date = fields.Date(
        string='Date de paiement',
        default=fields.Date.today,
        required=True
    )

    reference = fields.Char(
        string='Référence de paiement',
        help="Numéro de chèque, référence de virement, etc."
    )

    currency_id = fields.Many2one(
        'res.currency',
        string='Devise',
        default=lambda self: self.env.company.currency_id
    )

    notes = fields.Text(string='Notes')

    # Informations sur les factures existantes
    existing_invoices = fields.Boolean(
        string='Factures existantes',
        compute='_compute_existing_invoices'
    )

    unpaid_amount = fields.Monetary(
        string='Montant impayé',
        compute='_compute_existing_invoices',
        currency_field='currency_id'
    )

    overdue_invoices_count = fields.Integer(
        string='Factures en retard',
        compute='_compute_existing_invoices'
    )

    has_installments = fields.Boolean(
        string='A des tranches',
        compute='_compute_has_installments',
        help="Indique si le type de frais sélectionné a des tranches de paiement"
    )

    @api.depends('student_id')
    def _compute_available_invoices(self):
        """Toutes les factures impayées de l'élève, toutes années confondues."""
        for record in self:
            if not record.student_id:
                record.available_invoice_ids = False
                continue
            persons = record.student_id._get_person_students()
            invoices = record.student_id._get_fee_invoices(persons).filtered(
                lambda m: m.payment_state in ('not_paid', 'partial'))
            record.available_invoice_ids = invoices

    @api.depends('invoice_id', 'student_id')
    def _compute_invoice_info(self):
        for record in self:
            inv = record.invoice_id
            record.invoice_residual = inv.amount_residual if inv else 0.0
            year = inv.silina_academic_year_id if inv else False
            record.invoice_academic_year_id = year
            current_year = record.student_id.academic_year_id
            record.is_previous_year_payment = bool(
                inv and year and current_year and year != current_year)

    @api.depends('fee_type_id')
    def _compute_has_installments(self):
        for record in self:
            record.has_installments = bool(record.fee_type_id and record.fee_type_id.installment_ids)

    @api.depends('fee_type_id', 'payment_type', 'installment_id', 'payment_target', 'invoice_id')
    def _compute_amount(self):
        for record in self:
            if record.payment_target == 'existing':
                # Par défaut : solder le reste dû de la facture sélectionnée
                record.amount = record.invoice_id.amount_residual if record.invoice_id else 0.0
            elif record.payment_type == 'installment' and record.installment_id:
                record.amount = record.installment_id.amount
            elif record.payment_type == 'full' and record.fee_type_id:
                # Si le type de frais a des tranches, additionner les montants
                if record.fee_type_id.installment_ids:
                    record.amount = sum(record.fee_type_id.installment_ids.mapped('amount'))
                else:
                    # Sinon, utiliser le montant total
                    record.amount = record.fee_type_id.total_amount
            else:
                record.amount = 0.0

    @api.depends('student_id')
    def _compute_existing_invoices(self):
        for record in self:
            if record.student_id:
                # Toutes les factures impayées de l'élève, toutes années confondues
                persons = record.student_id._get_person_students()
                invoices = record.student_id._get_fee_invoices(persons).filtered(
                    lambda m: m.payment_state in ('not_paid', 'partial'))
                record.existing_invoices = bool(invoices)
                record.unpaid_amount = sum(invoices.mapped('amount_residual'))

                # Compter les factures en retard
                today = fields.Date.today()
                overdue = invoices.filtered(
                    lambda inv: inv.invoice_date_due and inv.invoice_date_due < today)
                record.overdue_invoices_count = len(overdue)
            else:
                record.existing_invoices = False
                record.unpaid_amount = 0.0
                record.overdue_invoices_count = 0

    @api.onchange('invoice_id')
    def _onchange_invoice_id(self):
        """Charger le reste dû de la facture sélectionnée."""
        if self.invoice_id:
            self.amount = self.invoice_id.amount_residual
            if self.invoice_id.silina_fee_type_id:
                self.fee_type_id = self.invoice_id.silina_fee_type_id

    @api.onchange('payment_target')
    def _onchange_payment_target(self):
        """Proposer par défaut la plus ancienne facture impayée."""
        if self.payment_target == 'existing':
            if not self.invoice_id and self.available_invoice_ids:
                self.invoice_id = self.available_invoice_ids.sorted(
                    key=lambda m: (m.invoice_date_due or m.invoice_date))[0]
        else:
            self.invoice_id = False

    @api.onchange('student_id')
    def _onchange_student_id(self):
        """Filtrer les types de frais selon le niveau de l'élève"""
        if self.student_id:
            # Réinitialiser le type de frais quand on change d'élève
            self.fee_type_id = False
            self.invoice_id = False

            # Retourner le domaine pour filtrer les types de frais
            if self.student_id.level_id:
                return {
                    'domain': {
                        'fee_type_id': [
                            '|',
                            ('level_ids', '=', False),  # Types de frais sans niveau spécifique (applicables à tous)
                            ('level_ids', 'in', [self.student_id.level_id.id])  # Types de frais pour ce niveau
                        ]
                    }
                }
        return {
            'domain': {
                'fee_type_id': []
            }
        }

    @api.onchange('fee_type_id')
    def _onchange_fee_type_id(self):
        """Réinitialiser la tranche et charger le montant automatiquement"""
        self.installment_id = False

        # Charger automatiquement le montant total du type de frais
        if self.fee_type_id:
            if self.fee_type_id.installment_ids:
                # Type de frais avec tranches : montant total = somme des tranches
                self.amount = sum(self.fee_type_id.installment_ids.mapped('amount'))
                # Par défaut, mode paiement complet
                self.payment_type = 'full'
            else:
                # Type de frais sans tranches : montant total
                self.amount = self.fee_type_id.total_amount
                # Forcer le paiement complet car pas de tranches
                self.payment_type = 'full'

    @api.onchange('payment_type')
    def _onchange_payment_type(self):
        """Adapter le montant selon le type de paiement"""
        if self.payment_type == 'full':
            self.installment_id = False
            # Recharger le montant total
            if self.fee_type_id:
                if self.fee_type_id.installment_ids:
                    self.amount = sum(self.fee_type_id.installment_ids.mapped('amount'))
                else:
                    self.amount = self.fee_type_id.total_amount
        elif self.payment_type == 'installment':
            # Réinitialiser le montant (sera mis à jour quand on sélectionne la tranche)
            self.amount = 0.0

    @api.onchange('installment_id')
    def _onchange_installment_id(self):
        """Charger automatiquement le montant de la tranche sélectionnée"""
        if self.installment_id:
            self.amount = self.installment_id.amount

    @api.constrains('amount', 'student_id', 'fee_type_id', 'invoice_id', 'payment_target')
    def _check_payment_amount(self):
        """Vérifier que le montant de paiement ne dépasse pas le montant restant dû"""
        for record in self:
            if record.amount <= 0:
                raise ValidationError(_('Le montant du paiement doit être supérieur à 0.'))

            # Cas 1 : règlement d'une facture précise (y compris année antérieure)
            invoice = False
            if record.payment_target == 'existing':
                invoice = record.invoice_id
            elif record.student_id and record.student_id.partner_id and record.fee_type_id:
                # Cas 2 : création/complément d'une facture de l'année en cours
                invoice = self.env['account.move'].search([
                    ('partner_id', '=', record.student_id.partner_id.id),
                    ('move_type', '=', 'out_invoice'),
                    ('state', '=', 'posted'),
                    ('payment_state', 'in', ['not_paid', 'partial']),
                    ('invoice_line_ids.product_id', '=', record.fee_type_id.product_id.id),
                ], limit=1)

            if invoice and record.amount > invoice.amount_residual:
                raise ValidationError(_(
                    'Le montant du paiement (%s) ne peut pas dépasser le montant restant dû de la facture (%s).\n\n'
                    'Montant restant dû: %s %s'
                ) % (
                    record.amount,
                    invoice.amount_residual,
                    invoice.amount_residual,
                    record.currency_id.symbol
                ))

    def action_process_payment(self):
        """Traiter le paiement : créer/retrouver la facture et enregistrer le paiement"""
        self.ensure_one()

        # Vérifier que l'élève a un partner
        if not self.student_id.partner_id:
            self.student_id._create_partner()

        if self.payment_target == 'existing':
            # Régler une facture précise (y compris d'une année scolaire passée)
            if not self.invoice_id:
                raise ValidationError(_(
                    'Veuillez sélectionner la facture à régler.'))
            invoice = self.invoice_id
        else:
            # Créer (ou compléter) une facture pour l'année en cours
            if not self.fee_type_id:
                raise ValidationError(_(
                    'Veuillez sélectionner le type de frais pour créer la facture.'))
            invoice = self._get_or_create_invoice()

        # Enregistrer le paiement
        payment = self._register_payment(invoice)

        # Générer le reçu de paiement
        return self._generate_receipt(payment, invoice)

    def _get_or_create_invoice(self):
        """Récupérer ou créer la facture appropriée
        Une seule facture par type de frais et par élève par année scolaire
        """
        # Chercher la facture existante pour ce type de frais et cette année
        # d'inscription. On s'appuie sur le tag silina_student_id (précis) et,
        # à défaut, sur le partenaire + produit (factures historiques).
        invoices = self.env['account.move'].search([
            ('silina_student_id', '=', self.student_id.id),
            ('silina_fee_type_id', '=', self.fee_type_id.id),
            ('move_type', '=', 'out_invoice'),
            ('state', '=', 'posted'),
        ], order='create_date desc')
        if not invoices:
            invoices = self.env['account.move'].search([
                ('partner_id', '=', self.student_id.partner_id.id),
                ('move_type', '=', 'out_invoice'),
                ('state', '=', 'posted'),
                ('invoice_line_ids.product_id', '=', self.fee_type_id.product_id.id),
                ('invoice_origin', 'ilike', self.student_id.academic_year_id.name),
            ], order='create_date desc')

        if invoices:
            invoice = invoices[0]  # Prendre la plus récente

            # Vérifier si la facture est déjà complètement payée
            if invoice.payment_state == 'paid':
                raise ValidationError(_(
                    'Ce type de frais (%s) a déjà été entièrement payé pour cet élève (%s) '
                    'pour l\'année scolaire %s.\n\n'
                    'Facture: %s\n'
                    'Montant total: %s %s\n'
                    'Statut: Payée intégralement'
                ) % (
                    self.fee_type_id.name,
                    self.student_id.name,
                    self.student_id.academic_year_id.name,
                    invoice.name,
                    invoice.amount_total,
                    invoice.currency_id.symbol
                ))

            # Si la facture existe et n'est pas complètement payée, la réutiliser
            return invoice

        # Aucune facture trouvée : en créer une nouvelle
        invoice = self._create_fee_invoice()
        return invoice

    def _create_fee_invoice(self):
        """Créer UNE SEULE facture avec toutes les tranches en lignes distinctes
        Ou une ligne unique si pas de tranches définies"""
        # Préparer les lignes de facture
        invoice_lines = []
        first_due_date = False

        if self.fee_type_id.installment_ids:
            # Type de frais avec tranches : créer une ligne par tranche
            for installment in self.fee_type_id.installment_ids:
                # Garder la date d'échéance de la première tranche
                if not first_due_date and installment.due_date_type == 'fixed':
                    first_due_date = installment.due_date

                invoice_lines.append((0, 0, {
                    'product_id': self.fee_type_id.product_id.id,
                    'name': f"{self.fee_type_id.name} - {installment.name}\nÉlève: {self.student_id.name}\nMatricule: {self.student_id.registration_number}\nClasse: {self.student_id.classroom_id.name if self.student_id.classroom_id else 'N/A'}",
                    'quantity': 1,
                    'price_unit': installment.amount,
                }))
        else:
            # Type de frais sans tranches : créer une ligne unique avec le montant total
            invoice_lines.append((0, 0, {
                'product_id': self.fee_type_id.product_id.id,
                'name': f"{self.fee_type_id.name}\nÉlève: {self.student_id.name}\nMatricule: {self.student_id.registration_number}\nClasse: {self.student_id.classroom_id.name if self.student_id.classroom_id else 'N/A'}",
                'quantity': 1,
                'price_unit': self.fee_type_id.total_amount,
            }))

        # Créer UNE facture avec toutes les lignes
        invoice_vals = {
            'move_type': 'out_invoice',
            'partner_id': self.student_id.partner_id.id,
            'silina_student_id': self.student_id.id,
            'silina_fee_type_id': self.fee_type_id.id,
            'invoice_date': fields.Date.today(),
            'invoice_date_due': first_due_date or fields.Date.today(),
            'invoice_origin': f"{self.fee_type_id.name} - Année scolaire {self.student_id.academic_year_id.name}",
            'invoice_line_ids': invoice_lines,
        }

        invoice = self.env['account.move'].create(invoice_vals)
        invoice.action_post()
        return invoice

    def _register_payment(self, invoice):
        """Enregistrer le paiement sur la facture.

        Le partenaire est celui de la facture : pour une facture d'une année
        antérieure, il peut différer du contact de l'inscription courante."""
        # Créer le paiement via le wizard standard d'Odoo
        payment_vals = {
            'payment_type': 'inbound',
            'partner_type': 'customer',
            'partner_id': invoice.partner_id.id,
            'amount': self.amount,
            'date': self.payment_date,
            'journal_id': self._get_payment_journal().id,
        }

        payment = self.env['account.payment'].create(payment_vals)

        # Ajouter la référence dans le mouvement comptable si fournie
        if self.reference:
            payment.move_id.write({'ref': self.reference})

        payment.action_post()

        # Réconcilier avec la facture sur le compte de créances clients uniquement
        # Trouver le compte de créances (receivable) - celui qui permet le lettrage
        receivable_lines = invoice.line_ids.filtered(
            lambda line: line.account_id.account_type == 'asset_receivable' and not line.reconciled
        )
        payment_lines = payment.move_id.line_ids.filtered(
            lambda line: line.account_id.account_type == 'asset_receivable' and not line.reconciled
        )

        # Réconcilier les lignes de créances
        lines_to_reconcile = receivable_lines + payment_lines
        if lines_to_reconcile:
            lines_to_reconcile.reconcile()

        return payment

    def _get_payment_journal(self):
        """Récupérer le journal de paiement approprié"""
        journal_type = 'cash' if self.payment_method == 'cash' else 'bank'
        journal = self.env['account.journal'].search([
            ('type', '=', journal_type),
            ('company_id', '=', self.env.company.id),
        ], limit=1)

        if not journal:
            raise ValidationError(_(
                f'Aucun journal de type {journal_type} trouvé! '
                'Veuillez configurer un journal de paiement.'
            ))

        return journal

    def _generate_receipt(self, payment, invoice):
        """Générer et afficher le reçu de paiement"""
        # Afficher un message de succès avec le bouton d'impression
        message = _(
            'Paiement enregistré avec succès!\n\n'
            'Montant: %s %s\n'
            'Facture: %s\n'
            'Reste à payer: %s %s'
        ) % (
            payment.amount,
            payment.currency_id.symbol,
            invoice.name,
            invoice.amount_residual,
            invoice.currency_id.symbol
        )

        # Retourner une action qui ouvre la fiche du paiement avec le rapport disponible
        return {
            'type': 'ir.actions.act_window',
            'name': _('Paiement enregistré - Imprimer le reçu'),
            'res_model': 'account.payment',
            'res_id': payment.id,
            'view_mode': 'form',
            'target': 'current',
            'context': {
                'default_message': message,
            }
        }
