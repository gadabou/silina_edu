from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    """La paie n'est plus lisible par le groupe « Utilisateur » (donc ni par les
    enseignants) : on supprime l'ancien droit d'accès resté en base."""
    env = api.Environment(cr, SUPERUSER_ID, {})
    for xmlid in ('silina_edu.access_silina_payroll_user',):
        rec = env.ref(xmlid, raise_if_not_found=False)
        if rec:
            rec.unlink()
