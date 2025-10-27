from odoo import models, fields, api, _


class StudentDocument(models.Model):
    _name = 'silina.student.document'
    _description = 'Document Étudiant'
    _order = 'date desc, id desc'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(
        string='Nom du document',
        required=True,
        tracking=True
    )

    student_id = fields.Many2one(
        'silina.student',
        string='Étudiant',
        required=True,
        ondelete='cascade',
        tracking=True
    )

    document_type = fields.Selection([
        ('birth_certificate', 'Acte de naissance'),
        ('id_card', 'Carte d\'identité'),
        ('photo', 'Photo d\'identité'),
        ('medical_certificate', 'Certificat médical'),
        ('report_card', 'Bulletin de notes'),
        ('transfer_certificate', 'Certificat de transfert'),
        ('conduct_certificate', 'Certificat de bonne conduite'),
        ('other', 'Autre'),
    ], string='Type de document', required=True, tracking=True)

    document = fields.Binary(
        string='Document',
        attachment=True,
        help="Fichier du document"
    )
    document_filename = fields.Char(string='Nom du fichier')

    date = fields.Date(
        string='Date',
        default=fields.Date.today,
        tracking=True
    )

    expiry_date = fields.Date(
        string='Date d\'expiration',
        tracking=True
    )

    is_verified = fields.Boolean(
        string='Vérifié',
        default=False,
        tracking=True
    )
    verified_by = fields.Many2one(
        'res.users',
        string='Vérifié par',
        readonly=True
    )
    verified_date = fields.Date(
        string='Date de vérification',
        readonly=True
    )

    description = fields.Text(string='Description')
    active = fields.Boolean(default=True)

    def action_verify(self):
        """Marquer le document comme vérifié"""
        self.ensure_one()
        self.write({
            'is_verified': True,
            'verified_by': self.env.user.id,
            'verified_date': fields.Date.today()
        })
        return True

    def action_unverify(self):
        """Annuler la vérification"""
        self.ensure_one()
        self.write({
            'is_verified': False,
            'verified_by': False,
            'verified_date': False
        })
        return True
