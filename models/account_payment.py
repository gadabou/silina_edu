# -*- coding: utf-8 -*-

from odoo import models, api


class AccountPayment(models.Model):
    _inherit = 'account.payment'

    def action_print_thermal_receipt(self):
        """
        Action pour imprimer automatiquement le reçu de paiement sur une imprimante thermique 80mm.
        Cette méthode génère le PDF et retourne l'action pour déclencher l'impression automatique.
        """
        self.ensure_one()

        # Générer le rapport PDF
        report = self.env.ref('silina_edu.action_report_payment_receipt_thermal_80mm')

        # Retourner l'action qui déclenche l'impression
        return report.report_action(self)
