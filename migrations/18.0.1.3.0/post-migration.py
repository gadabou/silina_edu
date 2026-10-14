from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    """Les types de frais ne sont plus lisibles par le groupe « Utilisateur »
    (donc les enseignants) : suppression des anciens droits d'accès."""
    env = api.Environment(cr, SUPERUSER_ID, {})
    for name in ('access_silina_fee_type_user', 'access_silina_fee_type_installment_user'):
        rec = env.ref('silina_edu.' + name, raise_if_not_found=False)
        if rec:
            rec.unlink()
