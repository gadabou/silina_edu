# -*- coding: utf-8 -*-

from odoo import models, api


class AccountMove(models.Model):
    _inherit = 'account.move'

    def action_print_thermal_invoice(self):
        """
        Action pour imprimer automatiquement la facture sur une imprimante thermique 80mm.
        Cette méthode génère le PDF et retourne l'action pour déclencher l'impression automatique.
        """
        self.ensure_one()

        # Générer le rapport PDF
        report = self.env.ref('silina_edu.action_report_invoice_thermal')

        # Retourner l'action qui déclenche l'impression
        return report.report_action(self)

    def action_auto_print_thermal(self):
        """
        Action pour impression automatique avec dialogue d'impression du navigateur.
        Cette méthode retourne une action client qui ouvrira automatiquement la fenêtre d'impression.
        """
        self.ensure_one()

        # Obtenir le rapport
        report = self.env.ref('silina_edu.action_report_invoice_thermal')

        # Générer le PDF et obtenir les données
        pdf_content, content_type = report._render_qweb_pdf(self.ids)

        # Retourner une action qui déclenchera l'impression automatique côté client
        return {
            'type': 'ir.actions.report',
            'report_type': 'qweb-pdf',
            'report_name': 'silina_edu.report_invoice_thermal_document',
            'report_file': 'silina_edu.report_invoice_thermal_document',
            'data': {
                'id': self.id,
                'ids': self.ids,
            },
            'context': dict(
                self.env.context,
                auto_print=True,  # Flag pour déclencher l'impression automatique
            ),
        }
