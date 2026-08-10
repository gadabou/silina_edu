from odoo import models, fields, api, _


class AccountMove(models.Model):
    """Extension des factures pour rattacher les frais scolaires à un élève
    et à une année scolaire précise.

    Chaque enregistrement `silina.student` représente un élève pour UNE année
    scolaire donnée. En taguant la facture avec cet élève, on obtient
    automatiquement l'année concernée : on peut ainsi distinguer les factures
    par année pour un même élève, et continuer à régler les frais impayés
    d'une année passée même lorsqu'on est dans une nouvelle année.
    """
    _inherit = 'account.move'

    silina_student_id = fields.Many2one(
        'silina.student',
        string='Élève (SILINA)',
        index=True,
        copy=False,
        help="Élève (année scolaire précise) rattaché à cette facture de frais."
    )

    silina_academic_year_id = fields.Many2one(
        'silina.academic.year',
        string='Année scolaire (SILINA)',
        related='silina_student_id.academic_year_id',
        store=True,
        index=True,
        help="Année scolaire de la facture, déduite de l'élève rattaché."
    )

    silina_fee_type_id = fields.Many2one(
        'silina.fee.type',
        string='Type de frais (SILINA)',
        index=True,
        copy=False,
        help="Type de frais scolaire facturé."
    )

    is_silina_fee = fields.Boolean(
        string='Facture de frais scolaires',
        compute='_compute_is_silina_fee',
        store=True
    )

    @api.depends('silina_student_id')
    def _compute_is_silina_fee(self):
        for move in self:
            move.is_silina_fee = bool(move.silina_student_id)
