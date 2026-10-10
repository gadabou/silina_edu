from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    """base.group_user n'implique plus group_silina_edu_manager : on garantit que
    les utilisateurs internes existants restent Administrateur SILINA-EDU (la
    suppression de l'implication ne retire normalement personne ; filet de sécurité)."""
    env = api.Environment(cr, SUPERUSER_ID, {})
    manager = env.ref('silina_edu.group_silina_edu_manager', raise_if_not_found=False)
    internal = env.ref('base.group_user')
    if not manager:
        return
    users = env['res.users'].with_context(active_test=False).search(
        [('groups_id', 'in', internal.id), ('share', '=', False)])
    users -= manager.users
    if users:
        manager.write({'users': [(4, u.id) for u in users]})
