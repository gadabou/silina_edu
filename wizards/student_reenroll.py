from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class StudentReenrollWizard(models.TransientModel):
    """Réinscrire un élève (ancien ou en cours) sur une nouvelle année scolaire.

    Chaque année scolaire correspond à un enregistrement `silina.student`
    distinct (voir models/student.py). Sans cet assistant, la seule façon de
    faire revenir un ancien élève était de modifier l'année scolaire de sa
    fiche existante, ce qui rattachait rétroactivement ses anciennes
    factures (déjà soldées) à la nouvelle année et bloquait l'encaissement
    de ses nouveaux frais."""
    _name = 'silina.student.reenroll.wizard'
    _description = "Réinscription d'un Élève"

    student_id = fields.Many2one(
        'silina.student',
        string='Élève (inscription actuelle)',
        required=True,
        readonly=True
    )
    registration_number = fields.Char(
        related='student_id.registration_number',
        string='Matricule',
        readonly=True
    )
    previous_academic_year_id = fields.Many2one(
        'silina.academic.year',
        related='student_id.academic_year_id',
        string='Année scolaire actuelle',
        readonly=True
    )
    new_academic_year_id = fields.Many2one(
        'silina.academic.year',
        string='Nouvelle année scolaire',
        required=True,
        default=lambda self: self.env['silina.academic.year'].get_current_year()
    )
    new_classroom_id = fields.Many2one(
        'silina.classroom',
        string='Nouvelle classe',
        domain="[('academic_year_id', '=', new_academic_year_id)]"
    )
    enrollment_date = fields.Date(
        string='Date de réinscription',
        default=fields.Date.today,
        required=True
    )
    notes = fields.Text(string='Notes')

    @api.onchange('new_academic_year_id')
    def _onchange_new_academic_year_id(self):
        self.new_classroom_id = False

    def action_reenroll(self):
        """Créer une nouvelle fiche élève pour la nouvelle année scolaire,
        liée à l'ancienne via `previous_student_id`."""
        self.ensure_one()
        old = self.student_id

        if self.new_academic_year_id == old.academic_year_id:
            raise ValidationError(_(
                "La nouvelle année scolaire doit être différente de l'année "
                "actuelle de l'élève (%s)."
            ) % old.academic_year_id.name)

        existing = self.env['silina.student'].search([
            ('registration_number', '=', old.registration_number),
            ('academic_year_id', '=', self.new_academic_year_id.id),
        ], limit=1)
        if existing:
            raise ValidationError(_(
                'Une fiche existe déjà pour ce matricule (%s) sur l\'année %s : %s.'
            ) % (old.registration_number, self.new_academic_year_id.name, existing.name))

        new_vals = {
            'first_name': old.first_name,
            'last_name': old.last_name,
            'registration_number': old.registration_number,
            'image_1920': old.image_1920,
            'gender': old.gender,
            'date_of_birth': old.date_of_birth,
            'place_of_birth': old.place_of_birth,
            'nationality': old.nationality.id,
            'blood_group': old.blood_group,
            'email': old.email,
            'phone': old.phone,
            'mobile': old.mobile,
            'street': old.street,
            'street2': old.street2,
            'city': old.city,
            'state_id': old.state_id.id,
            'zip': old.zip,
            'country_id': old.country_id.id,
            'academic_year_id': self.new_academic_year_id.id,
            'classroom_id': self.new_classroom_id.id,
            'enrollment_date': self.enrollment_date,
            'state': 'enrolled' if self.new_classroom_id else 'draft',
            'previous_student_id': old.id,
            'parent_ids': [(6, 0, old.parent_ids.ids)],
            'father_name': old.father_name,
            'mother_name': old.mother_name,
            'guardian_name': old.guardian_name,
            'allergies': old.allergies,
            'medical_conditions': old.medical_conditions,
            'emergency_contact_name': old.emergency_contact_name,
            'emergency_contact_phone': old.emergency_contact_phone,
            'notes': self.notes or old.notes,
        }

        new_student = self.env['silina.student'].create(new_vals)

        return {
            'type': 'ir.actions.act_window',
            'name': _('Élève réinscrit'),
            'res_model': 'silina.student',
            'res_id': new_student.id,
            'view_mode': 'form',
            'target': 'current',
        }
