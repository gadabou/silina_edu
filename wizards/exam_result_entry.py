# -*- coding: utf-8 -*-
from odoo import api, fields, models, Command, _
from odoo.exceptions import UserError

from odoo.addons.silina_edu.models.security_helpers import _teacher_scope


class ExamResultEntry(models.TransientModel):
    """Saisie groupée des résultats : on choisit un examen, tous les élèves de ses
    classes sont chargés pour chaque matière de l'examen, notes vides.
    À l'enregistrement, chaque note saisie est confirmée automatiquement."""
    _name = 'silina.exam.result.entry'
    _description = "Saisie des résultats d'un examen"

    exam_id = fields.Many2one('silina.exam', string='Examen', required=True)
    total_marks = fields.Float(related='exam_id.total_marks', string='Note maximale')
    line_ids = fields.One2many('silina.exam.result.entry.line', 'entry_id', string='Élèves')

    def _scope_allows(self, classroom, subject, scope):
        """Vrai si l'utilisateur peut saisir (classe, matière). Les coordinateurs et
        responsables ont accès à tout ; un enseignant à ses classes/matières."""
        if self.env.user.has_group('silina_edu.group_silina_edu_coordinator'):
            return True
        pairs, mains = scope
        return classroom.id in mains or subject.id in pairs.get(classroom.id, ())

    @api.onchange('exam_id')
    def _onchange_exam_id(self):
        commands = [Command.clear()]
        exam = self.exam_id
        if exam:
            exam = exam.sudo()
            scope = _teacher_scope(self.env)
            existing = {(r.student_id.id, r.subject_id.id): r for r in
                        self.env['silina.exam.result'].search([('exam_id', '=', exam.id)])}
            for classroom in exam._get_result_classrooms():
                subjects = exam.subject_ids or classroom.subject_assignment_ids.mapped('subject_id')
                students = classroom.student_ids.filtered(
                    lambda s: s.active and s.state in ('enrolled', 'promoted', 'repeated'))
                for subject in subjects:
                    if not self._scope_allows(classroom, subject, scope):
                        continue
                    for student in students.sorted('name'):
                        result = existing.get((student.id, subject.id))
                        commands.append(Command.create({
                            'student_id': student.id,
                            'classroom_id': classroom.id,
                            'subject_id': subject.id,
                            'result_id': result.id if result else False,
                            'marks_input': result.marks_input if result else '',
                        }))
        self.line_ids = commands

    def action_save(self):
        self.ensure_one()
        Result = self.env['silina.exam.result']
        created = updated = 0
        for line in self.line_ids:
            value = Result._parse_mark(line.marks_input)
            if line.result_id:
                if value is None:
                    continue  # on n'efface pas une note existante en laissant vide
                result = line.result_id
                if (not result.mark_entered or result.marks_obtained != value
                        or result.state != 'confirmed'):
                    result.write({'mark_entered': True, 'marks_obtained': value,
                                  'state': 'confirmed'})
                    updated += 1
            elif value is not None:
                Result.create({
                    'exam_id': self.exam_id.id,
                    'student_id': line.student_id.id,
                    'subject_id': line.subject_id.id,
                    'mark_entered': True,
                    'marks_obtained': value,
                    'state': 'confirmed',
                })
                created += 1
        if not (created or updated):
            raise UserError(_("Aucune note saisie."))
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _("Résultats enregistrés"),
                'message': _("%(c)s créé(s), %(u)s mis à jour.", c=created, u=updated),
                'type': 'success',
                'next': {'type': 'ir.actions.act_window_close'},
            },
        }


class ExamResultEntryLine(models.TransientModel):
    _name = 'silina.exam.result.entry.line'
    _description = "Ligne de saisie des résultats"
    _order = 'subject_id, classroom_id, student_id'

    entry_id = fields.Many2one('silina.exam.result.entry', required=True, ondelete='cascade')
    student_id = fields.Many2one('silina.student', string='Élève', required=True)
    classroom_id = fields.Many2one('silina.classroom', string='Classe')
    subject_id = fields.Many2one('silina.subject', string='Matière', required=True)
    result_id = fields.Many2one('silina.exam.result', string='Résultat existant')
    marks_input = fields.Char(string='Note obtenue')
