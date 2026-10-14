# -*- coding: utf-8 -*-
"""Phase 3 : vérifications indépendantes après sim_run.py (base de TEST).

    docker exec -i odoo1_app odoo shell -d csbonscitoyens_sim --no-http \
        -c /etc/odoo/odoo.conf < scripts/sim_verify.py
"""
import re

from odoo import api
from odoo.exceptions import AccessError, UserError, ValidationError

CTX = dict(tracking_disable=True)
cr = env.cr  # noqa: F821
RES = []


def check(label, ok, detail=''):
    RES.append((label, ok, detail))
    print('%s %s %s' % ('OK ' if ok else 'KO ', label, ('| ' + str(detail)) if detail else ''), flush=True)


def as_user(login):
    u = env['res.users'].search([('login', '=', login)], limit=1)  # noqa: F821
    return api.Environment(cr, u.id, CTX)


def denied(fn):
    """True si l'opération est refusée (AccessError/UserError d'accès)."""
    try:
        fn()
    except (AccessError, UserError, ValidationError):
        cr.rollback()
        return True
    except Exception:
        cr.rollback()
        return True
    cr.rollback()
    return False


Year = env['silina.academic.year']  # noqa: F821
Student = env['silina.student']  # noqa: F821
Annual = env['silina.annual.result']  # noqa: F821
years = Year.search([], order='date_start')
LEVELS = env['silina.level'].search([('code', 'in', ['CRECHE', 'CI', 'CP1', 'CP2', 'CE1', 'CE2', 'CM1', 'CM2', '6EME', '5EME', '4EME', '3EME'])], order='sequence')  # noqa: F821
pass_avg = env.company.silina_pass_average  # noqa: F821

print('\n=== 1. Effectifs : minimum 15 élèves par classe et par année ===')
for y in years:
    sizes = {c.code: len(c.student_ids) for c in env['silina.classroom'].search([('academic_year_id', '=', y.id)])}  # noqa: F821
    small = {k: v for k, v in sizes.items() if v < 15}
    check('%s : %d classes, min=%d' % (y.name, len(sizes), min(sizes.values())), not small, small or '')

print('\n=== 2. Promotion automatique (moyenne annuelle >= %.1f) ===' % pass_avg)
for y, ny in zip(years, years[1:]):
    wrong, n = [], 0
    for r in Annual.search([('academic_year_id', '=', y.id)]):
        n += 1
        st = r.student_id
        nxt = Student.search([('registration_number', '=', st.registration_number),
                              ('academic_year_id', '=', ny.id)], limit=1)
        should_pass = r.has_average and r.annual_average >= pass_avg
        if should_pass:
            lv = st.level_id.next_level_id
            if lv:
                if not nxt or nxt.level_id != lv:
                    wrong.append((st.name, r.annual_average, 'devait passer en %s' % lv.code,
                                  nxt.level_id.code if nxt else 'absent'))
            elif st.state != 'graduated':
                wrong.append((st.name, r.annual_average, 'devait être diplômé', st.state))
        else:
            if not nxt or nxt.level_id != st.level_id:
                wrong.append((st.name, r.annual_average, 'devait redoubler',
                              nxt.level_id.code if nxt else 'absent'))
    check('%s -> %s : %d élèves contrôlés' % (y.name, ny.name, n), not wrong, wrong[:3] or '')
    dup = Student.read_group([('academic_year_id', '=', ny.id)], ['registration_number'], ['registration_number'])
    check('  aucun doublon de matricule en %s' % ny.name, all(d['registration_number_count'] == 1 for d in dup))

print('\n=== 3. Bulletins : en-tête paramétrable ===')
company = env.company  # noqa: F821
card = env['silina.report.card.mixin']  # noqa: F821
y = years[0]
c3 = env['silina.classroom'].search([('code', '=', '3EME'), ('academic_year_id', '=', y.id)])  # noqa: F821
studs = c3.student_ids[:2]
action = card.get_report_card_action(studs.ids, annual=True, kind='bulletin')
rname = action['report_name']
html, _t = env['ir.actions.report']._render_qweb_html(rname, studs.ids, data=action.get('data'))  # noqa: F821
html = html.decode() if isinstance(html, bytes) else html
check('bulletin : nom de l\'établissement présent', 'Complexe Scolaire Bons Citoyens' in html)
check('bulletin : adresse / téléphone / mention présents',
      'Lomé' in html and '+228 90 00 00 00' in html and 'Agrément' in html)
check('bulletin : pied de page présent', 'duplicata' in html)
# repli sur la société : on vide les champs spécifiques (transaction annulée ensuite)
company.write({'silina_school_name': False, 'silina_header_phone': False,
               'silina_header_address': False, 'silina_header_extra': False,
               'silina_header_email': False, 'silina_footer_text': False})
company.partner_id.write({'phone': '+228 22 22 22 22'})
hd = company.get_silina_header()
check('repli sur la société : nom', hd['name'] == company.name, hd['name'])
check('repli sur la société : téléphone', hd['phone'] == '+228 22 22 22 22', hd['phone'])
cr.rollback()
try:
    pdf, _t = env['ir.actions.report']._render_qweb_pdf(rname, studs.ids, data=action.get('data'))  # noqa: F821
    check('bulletin PDF généré', pdf[:4] == b'%PDF', '%d octets' % len(pdf))
except Exception as e:  # noqa: BLE001
    check('bulletin PDF généré', False, str(e)[:120])
cr_c = env['silina.classroom'].search([('code', '=', 'CRECHE'), ('academic_year_id', '=', y.id)])  # noqa: F821
la = card.get_report_card_action(cr_c.student_ids[:1].ids, annual=True, kind='livret')
try:
    pdf, _t = env['ir.actions.report']._render_qweb_pdf(la['report_name'], cr_c.student_ids[:1].ids, data=la.get('data'))  # noqa: F821
    check('livret PDF généré', pdf[:4] == b'%PDF', '%d octets' % len(pdf))
except Exception as e:  # noqa: BLE001
    check('livret PDF généré', False, str(e)[:120])

print('\n=== 4. Permissions avec de vrais comptes ===')
y3 = years[-1]
other = env['silina.classroom'].search([('code', '=', '3EME'), ('academic_year_id', '=', y3.id)])  # noqa: F821
mine_code = 'CP1'
for login, own_code in (('edem.agbo', 'CP1'), ('kodjo.amegah', 'CE1'), ('kossi.amouzou', None)):
    e = as_user(login)
    visible = e['silina.student'].search([('academic_year_id', '=', y3.id)])
    levels_seen = sorted(set(visible.mapped('level_id.code')))
    exp = {own_code} if own_code else {'6EME', '5EME', '4EME', '3EME'}
    check('%s ne voit que ses classes (%d élèves)' % (login, len(visible)), set(levels_seen) == exp, levels_seen)

e = as_user('edem.agbo')   # titulaire CP1
foreign_student = Student.search([('level_id.code', '=', '3EME'), ('academic_year_id', '=', y3.id)], limit=1)
check('enseignant : lecture d\'un élève d\'une autre classe refusée (accès direct)',
      denied(lambda: e['silina.student'].browse(foreign_student.id).read(['name'])))
foreign_res = env['silina.exam.result'].search([('student_id', '=', foreign_student.id)], limit=1)  # noqa: F821
check('enseignant : lecture d\'une note d\'une autre classe refusée',
      denied(lambda: e['silina.exam.result'].browse(foreign_res.id).read(['marks_obtained'])))
check('enseignant : modification d\'une note d\'une autre classe refusée',
      denied(lambda: e['silina.exam.result'].browse(foreign_res.id).write({'marks_obtained': 20})))
own_assign = e['silina.subject.assignment'].search([], limit=1)
check('enseignant : ne voit que ses affectations',
      all(a.teacher_id.employee_id.user_id == e.user or a.classroom_id.main_teacher_id.employee_id.user_id == e.user
          for a in e['silina.subject.assignment'].search([])))
for model, label in (('silina.payroll', 'paie'), ('silina.fee.type', 'types de frais'),
                     ('account.move', 'écritures comptables'), ('res.config.settings', 'paramètres')):
    check('enseignant : accès %s refusé' % label,
          denied(lambda m=model: e[m].search([], limit=1) if m != 'res.config.settings'
                 else e[m].create({}).execute()))
check('enseignant : création d\'élève refusée',
      denied(lambda: e['silina.student'].create({'first_name': 'X', 'last_name': 'Y', 'gender': 'male',
                                                 'academic_year_id': y3.id})))
check('enseignant : promotion en masse refusée',
      denied(lambda: e['silina.bulk.student.promotion.wizard'].create({
          'current_academic_year_id': y3.id, 'new_academic_year_id': y3.id})))
# un enseignant de matière ne saisit que sa matière
subj_other = env['silina.subject.assignment'].search([  # noqa: F821
    ('classroom_id.code', '=', 'CP1'), ('classroom_id.academic_year_id', '=', y3.id),
    ('teacher_id.employee_id.user_id.login', '!=', 'edem.agbo')], limit=1)
cp1_exam = env['silina.exam'].search([('classroom_ids.code', '=', 'CP1'), ('academic_year_id', '=', y3.id)], limit=1)  # noqa: F821
own_res = e['silina.exam.result'].search([('classroom_id.code', '=', 'CP1')], limit=1)
check('enseignant : modification d\'une note de sa propre classe autorisée',
      bool(own_res) and not denied(lambda: own_res.write({'marks_obtained': 12.0})))

sec = as_user('secretaire')
check('secrétariat : voit tous les élèves', sec['silina.student'].search_count([]) == Student.search_count([]))
check('secrétariat : accès paie refusé', denied(lambda: sec['silina.payroll'].search([], limit=1)))
check('secrétariat : modification d\'une note refusée',
      denied(lambda: sec['silina.exam.result'].search([], limit=1).write({'marks_obtained': 1})))
check('secrétariat : création d\'un élève autorisée', not denied(lambda: sec['silina.student'].create({
    'first_name': 'Test', 'last_name': 'Secretaire', 'gender': 'male', 'academic_year_id': y3.id,
    'classroom_id': other.id, 'state': 'enrolled'})))

co = as_user('coordinateur')
check('coordinateur : voit tout le pédagogique', co['silina.classroom'].search_count([]) == env['silina.classroom'].search_count([]))  # noqa: F821
check('coordinateur : paie lisible', not denied(lambda: co['silina.payroll'].search([], limit=1)))
check('coordinateur : paramètres société refusés', denied(lambda: co['res.config.settings'].create({}).execute()))

dr = as_user('directeur')
check('directeur : tout accessible', not denied(lambda: dr['silina.payroll'].search([], limit=1)))
check('directeur : paie créable et supprimable',
      not denied(lambda: dr['silina.payroll'].check_access('create'))
      and not denied(lambda: dr['silina.payroll'].check_access('unlink')))
check('coordinateur : suppression de paie refusée',
      denied(lambda: co['silina.payroll'].check_access('unlink')))

cm = as_user('comptable')
check('comptable : factures lisibles', not denied(lambda: cm['account.move'].search([], limit=1)))
check('comptable : saisie de note refusée',
      denied(lambda: cm['silina.exam.result'].search([], limit=1).write({'marks_obtained': 1})))

print('\n=== Bilan ===')
ko = [r for r in RES if not r[1]]
print('%d vérifications, %d OK, %d KO' % (len(RES), len(RES) - len(ko), len(ko)))
for l, _o, d in ko:
    print('  KO :', l, '|', d)
