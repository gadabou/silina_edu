from odoo import api, fields, models
from odoo.osv import expression


def _teacher_scope(env):
    """Périmètre de l'utilisateur courant en tant qu'enseignant.

    Retourne (pairs, mains) :
      pairs = {classroom_id: {subject_id, ...}} d'après silina.subject.assignment
              (silina.teacher.user_id = utilisateur) ;
      mains = {classroom_id} des classes dont il est titulaire.
    """
    uid = env.uid
    pairs = {}
    assignments = env['silina.subject.assignment'].sudo().search(
        [('teacher_id.user_id', '=', uid)])
    for a in assignments:
        pairs.setdefault(a.classroom_id.id, set()).add(a.subject_id.id)
    mains = set(env['silina.classroom'].sudo().search(
        [('main_teacher_id.user_id', '=', uid)]).ids)
    return pairs, mains


class SilinaTeacherUser(models.Model):
    _inherit = 'silina.teacher'

    user_id = fields.Many2one(
        'res.users', string='Utilisateur', related='employee_id.user_id',
        store=True, index=True, readonly=True,
        help="Utilisateur lié à l'employé : sert aux règles d'accès de l'enseignant.")


class _ScopeMixin(models.AbstractModel):
    _name = 'silina.teacher.scope.mixin'
    _description = "Périmètre enseignant (mixin)"

    silina_teacher_scope = fields.Boolean(
        string="Dans le périmètre de l'enseignant",
        compute='_compute_silina_teacher_scope',
        search='_search_silina_teacher_scope')

    def _silina_scope_domain(self):
        raise NotImplementedError

    @api.depends_context('uid')
    def _compute_silina_teacher_scope(self):
        ok = self.filtered_domain(self._silina_scope_domain())
        for rec in self:
            rec.silina_teacher_scope = rec in ok

    def _search_silina_teacher_scope(self, operator, value):
        if operator not in ('=', '!='):
            raise ValueError("Opérateur non supporté : %s" % operator)
        domain = self._silina_scope_domain()
        if (operator == '=') != bool(value):
            domain = ['!'] + expression.normalize_domain(domain)
        return domain


class ExamResultScope(models.Model):
    _name = 'silina.exam.result'
    _inherit = ['silina.exam.result', 'silina.teacher.scope.mixin']

    def _silina_scope_domain(self):
        """(classe affectée ET matière affectée) OU classe dont il est titulaire."""
        pairs, mains = _teacher_scope(self.env)
        parts = []
        if mains:
            parts.append([('classroom_id', 'in', list(mains))])
        for classroom_id, subjects in pairs.items():
            parts.append([('classroom_id', '=', classroom_id),
                          ('subject_id', 'in', list(subjects))])
        return expression.OR(parts) if parts else list(expression.FALSE_DOMAIN)


class ExamScope(models.Model):
    _name = 'silina.exam'
    _inherit = ['silina.exam', 'silina.teacher.scope.mixin']

    def _silina_scope_domain(self):
        """Examen d'une de ses classes (matières vides ou affectées), ou, sans
        classe, d'un niveau de ses classes. Le « créé par lui » est dans la règle."""
        pairs, mains = _teacher_scope(self.env)
        parts = []
        if mains:
            parts.append([('classroom_ids', 'in', list(mains))])
        for classroom_id, subjects in pairs.items():
            parts.append([('classroom_ids', 'in', [classroom_id]),
                          '|', ('subject_ids', '=', False),
                          ('subject_ids', 'in', list(subjects))])
        classrooms = self.env['silina.classroom'].sudo().browse(
            list(set(pairs) | mains))
        levels = classrooms.mapped('level_id').ids
        if levels:
            parts.append([('classroom_ids', '=', False),
                          ('level_ids', 'in', levels)])
        return expression.OR(parts) if parts else list(expression.FALSE_DOMAIN)
