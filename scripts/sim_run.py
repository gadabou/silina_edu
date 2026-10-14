# -*- coding: utf-8 -*-
"""Phase 2 de la simulation : rentrée, évaluations, notes saisies PAR LES ENSEIGNANTS
(avec leur propre compte), calcul des résultats, bulletins, promotion, année suivante.

Rejouable : chaque étape vérifie ce qui existe déjà.
    docker exec -i odoo1_app odoo shell -d csbonscitoyens_sim --no-http \
        -c /etc/odoo/odoo.conf < scripts/sim_run.py
"""
import random
import time
from datetime import timedelta

from odoo import api, fields
from odoo.exceptions import AccessError, UserError, ValidationError

random.seed(42)
CTX = dict(tracking_disable=True, mail_create_nolog=True, mail_create_nosubscribe=True)
env = api.Environment(env.cr, env.uid, CTX)  # noqa: F821
cr = env.cr


def env_of(login):
    user = env['res.users'].search([('login', '=', login)], limit=1)
    assert user, login
    return api.Environment(cr, user.id, CTX)


envC = env_of('coordinateur')
envS = env_of('secretaire')
envA = env_of('comptable')
YEARS = ['2024-2025', '2025-2026', '2026-2027']
LOG = []


def log(msg):
    print(msg, flush=True)
    LOG.append(msg)


# --------------------------------------------------------------- frais
def setup_fees(year):
    """Frais d'inscription + scolarité en 3 tranches, pour tous les niveaux."""
    Fee = env['silina.fee.type']
    base = Fee.search([('academic_year_id', '=', False)], limit=1)
    levels = env['silina.level'].search([('code', 'in', [
        'CRECHE', 'CI', 'CP1', 'CP2', 'CE1', 'CE2', 'CM1', 'CM2', '6EME', '5EME', '4EME', '3EME'])])
    out = []
    for code, label, cat, parts in (
            ('INS', 'Inscription', 'registration', [('Inscription', 25000)]),
            ('SCO', 'Scolarité', 'tuition', [('1re tranche', 60000), ('2e tranche', 60000),
                                              ('3e tranche', 60000)])):
        fee = Fee.search([('code', '=', '%s-%s' % (code, year.code))], limit=1)
        if not fee:
            ref = Fee.search([('fee_category', '=', cat)], limit=1)
            fee = Fee.create({
                'name': '%s %s' % (label, year.name), 'code': '%s-%s' % (code, year.code),
                'fee_category': cat, 'academic_year_id': year.id,
                'total_amount': float(sum(a for _n, a in parts)),
                'currency_id': env.company.currency_id.id,
                'level_ids': [(6, 0, levels.ids)], 'is_mandatory': True,
                'product_id': ref.product_id.id, 'account_id': ref.account_id.id,
                'installment_ids': [(0, 0, {
                    'name': n, 'sequence': i * 10, 'amount': a,
                    'due_date_type': 'fixed',
                    'due_date': year.date_start + timedelta(days=i * 100),
                }) for i, (n, a) in enumerate(parts)],
            })
        out.append(fee)
    return out


def bill_year(year):
    Move = env['account.move']
    if Move.search_count([('silina_fee_type_id.academic_year_id', '=', year.id)]):
        return
    for fee in setup_fees(year):
        wiz = envC['silina.generate.fee.invoices.wizard'].create({
            'fee_type_id': fee.id, 'academic_year_id': year.id,
            'generation_mode': 'all', 'start_date': year.date_start})
        res = wiz.action_generate_invoices()
        log('    %s : %s' % (fee.code, res['params']['message'].split(chr(10))[0]))
    cr.commit()
    # Paiements via l'assistant du module : 65 % soldent, 20 % paient la 1re facture, 15 % rien
    invs = Move.sudo().search([('silina_fee_type_id.academic_year_id', '=', year.id),
                               ('state', '=', 'posted'), ('payment_state', '=', 'not_paid')])
    by_student = {}
    for inv in invs:
        by_student.setdefault(inv.partner_id.id, []).append(inv)
    paid = errors = 0
    for _pid, lst in by_student.items():
        r = random.random()
        todo = lst if r < 0.65 else lst[:1] if r < 0.85 else []
        for inv in todo:
            amount = inv.amount_residual if random.random() < 0.85 else round(inv.amount_residual / 2)
            try:
                w = envS['silina.student.fee.payment.wizard'].create({
                    'student_id': inv.silina_student_id.id, 'payment_target': 'existing',
                    'invoice_id': inv.id,
                    'amount': amount, 'payment_method': random.choice(['cash', 'bank_transfer']),
                    'payment_date': year.date_start + timedelta(days=random.randint(0, 150))})
                w.action_process_payment()
                paid += 1
            except (UserError, ValidationError, AccessError) as e:
                errors += 1
                if errors <= 3:
                    log('    paiement refusé : %s' % str(e)[:150])
    cr.commit()
    log('  facturation %s : %d factures, %d paiements, %d erreurs' % (year.name, len(invs), paid, errors))


# --------------------------------------------------------------- examens + notes
ABILITY = {}


def ability(student):
    key = student.registration_number
    if key not in ABILITY:
        ABILITY[key] = random.gauss(12.3, 2.7)
    else:
        ABILITY[key] += random.gauss(0, 0.4)
    return ABILITY[key]


def mark(student, kind):
    base = ability(student) + random.gauss(0, 2.2 if kind == 'composition' else 2.8)
    return round(max(0.0, min(20.0, base)) * 2) / 2


def run_period(year, period, idx):
    classes = envC['silina.classroom'].search([('academic_year_id', '=', year.id)])
    Exam = envC['silina.exam']
    specs = [('DEV1', 'devoir', 0, 15), ('DEV2', 'devoir', 0, 45), ('COMP', 'composition', idx + 1, -10)]
    entered = 0
    for c in classes:
        subjects = c.subject_assignment_ids.mapped('subject_id')
        for tag, kind, num, off in specs:
            code = '%s-%s-%s' % (c.code, period.code, tag)
            exam = Exam.search([('code', '=', code), ('academic_year_id', '=', year.id)], limit=1)
            if exam and exam.state == 'completed':
                continue
            if not exam:
                d = period.date_start + timedelta(days=off) if off > 0 else period.date_end + timedelta(days=off)
                exam = Exam.create({
                    'name': '%s - %s %s' % (c.name, tag, period.name), 'code': code,
                    'exam_type': 'quarterly', 'evaluation_kind': kind,
                    'composition_number': num, 'academic_year_id': year.id,
                    'period_id': period.id, 'date_start': d, 'date_end': d,
                    'classroom_ids': [(6, 0, c.ids)], 'subject_ids': [(6, 0, subjects.ids)],
                    'level_ids': [(6, 0, c.level_id.ids)],
                    'total_marks': 20.0, 'passing_marks': 10.0})
                exam.action_schedule()
                exam.action_start()
            # saisie par chaque enseignant avec SON compte
            for a in c.subject_assignment_ids:
                user = a.teacher_id.employee_id.user_id
                envT = api.Environment(cr, user.id, CTX)
                students = envT['silina.student'].search([('classroom_id', '=', c.id)])
                if len(students) != len(c.student_ids):
                    raise AssertionError('périmètre enseignant incomplet %s' % user.login)
                vals = []
                for s in students:
                    if random.random() < 0.02:        # absent à l'examen : pas de note
                        continue
                    vals.append({'exam_id': exam.id, 'student_id': s.id,
                                 'subject_id': a.subject_id.id,
                                 'classroom_id': c.id,
                                 'marks_obtained': mark(s, kind),
                                 'teacher_id': a.teacher_id.id})
                recs = envT['silina.exam.result'].create(vals)
                recs.write({'state': 'confirmed'})
                entered += len(recs)
            exam.action_complete()
        cr.commit()
    return entered


def discipline(year, period):
    Abs = envC['silina.discipline.absence']
    if Abs.search_count([('period_id', '=', period.id)]):
        return
    kinds = [k for k, _l in Abs._fields['absence_type'].selection]
    students = envC['silina.student'].search([('academic_year_id', '=', year.id)])
    n = 0
    for s in students:
        if random.random() < 0.35:
            Abs.create({'student_id': s.id, 'classroom_id': s.classroom_id.id,
                        'date': period.date_start + timedelta(days=random.randint(5, 60)),
                        'absence_type': random.choice(kinds),
                        'justified': random.random() < 0.6, 'period_id': period.id})
            n += 1
        if random.random() < 0.2:
            envC['silina.discipline.late'].create({
                'student_id': s.id, 'classroom_id': s.classroom_id.id,
                'date': period.date_start + timedelta(days=random.randint(5, 60)),
                'justified': False, 'period_id': period.id})
    cr.commit()
    log('    assiduité %s : %d absences' % (period.code, n))


# --------------------------------------------------------------- fin d'année
def close_year(year, next_year):
    wiz = envC['silina.compute.results.wizard'].create({
        'academic_year_id': year.id, 'compute_period': True, 'compute_annual': True})
    wiz.action_compute()
    cr.commit()
    annual = envC['silina.annual.result'].search([('academic_year_id', '=', year.id)])
    stats = {}
    for r in annual:
        stats[r.final_decision] = stats.get(r.final_decision, 0) + 1
    log('  décisions %s : %s' % (year.name, stats))

    # bulletins de la classe de 3ème (HTML rendu) + livret de la crèche : contrôle de rendu
    for code in ('3EME', 'CRECHE'):
        c = envC['silina.classroom'].search([('code', '=', code), ('academic_year_id', '=', year.id)])
        rw = envC['silina.generate.report.card.wizard'].create({
            'academic_year_id': year.id, 'generation_type': 'classroom',
            'classroom_ids': [(6, 0, c.ids)], 'report_scope': 'annual'})
        action = rw.action_generate()
        log('    bulletin annuel %s : action %s' % (code, action.get('report_name') or action.get('type')))
        cr.commit()

    if not next_year:
        return
    classes = envC['silina.classroom'].search([('academic_year_id', '=', year.id)])
    promo = envC['silina.bulk.student.promotion.wizard'].create({
        'current_academic_year_id': year.id, 'new_academic_year_id': next_year.id,
        'current_classroom_ids': [(6, 0, classes.ids)], 'promotion_type': 'decision',
        'include_indulgence': True, 'promotion_date': next_year.date_start})
    students = envC['silina.student'].search([
        ('classroom_id', 'in', classes.ids),
        ('state', 'not in', ('transferred', 'expelled', 'graduated', 'draft'))])
    promo.student_ids = [(6, 0, students.ids)]
    promo.action_preview()
    skipped = promo.skipped_info
    promo.action_promote()
    cr.commit()
    outcome = {}
    for l in promo.line_ids:
        outcome[l.outcome] = outcome.get(l.outcome, 0) + 1
    log('  promotion %s -> %s : %s (erreurs : %d)%s' % (
        year.name, next_year.name, outcome,
        len(promo.line_ids.filtered(lambda l: l.state == 'error')),
        (' | non traités : %s' % skipped.replace('\n', '; ')) if skipped else ''))
    year.action_close()
    cr.commit()


# --------------------------------------------------------------- nouveaux inscrits
FIRST = ['Kokou', 'Komi', 'Yao', 'Mawuli', 'Edem', 'Kodjo', 'Elom', 'Dodzi', 'Samuel', 'David',
         'Ama', 'Afi', 'Abla', 'Yawa', 'Mawuena', 'Elodie', 'Grâce', 'Esther', 'Ruth', 'Linda']
LAST = ['AGBO', 'ATSOU', 'MENSAH', 'KOFFI', 'TETE', 'AMEGAH', 'DOSSEH', 'AKAKPO', 'BEKUI', 'EDORH',
        'GLOKPOR', 'KPODAR', 'LOGLO', 'MEDJI', 'OLYMPIO', 'PALANGA', 'SEWAVI', 'TOGBE', 'WONU', 'ZINSOU']
AGE = {'CRECHE': 3, 'CI': 4, 'CP1': 6, 'CP2': 7, 'CE1': 8, 'CE2': 9, 'CM1': 10, 'CM2': 11,
       '6EME': 12, '5EME': 13, '4EME': 14, '3EME': 15}


def enroll_newcomers(year, minimum=15):
    """Nouveaux élèves : classe d'entrée (crèche, 6ème) + compléments pour atteindre 15."""
    Student = envS['silina.student']       # inscriptions faites par le secrétariat
    added = 0
    for c in envC['silina.classroom'].search([('academic_year_id', '=', year.id)]):
        n = len(c.student_ids)
        extra = random.randint(3, 6) if c.code in ('CRECHE', '6EME') else random.randint(0, 2)
        target = max(minimum, n + extra) if n < minimum or extra else n
        for _ in range(max(0, target - n)):
            gender = random.choice(['male', 'female'])
            Student.create({
                'first_name': random.choice(FIRST), 'last_name': random.choice(LAST),
                'gender': gender,
                'date_of_birth': fields.Date.from_string('%d-%02d-%02d' % (
                    year.date_start.year - AGE[c.code] - random.choice([0, 0, 1]),
                    random.randint(1, 12), random.randint(1, 28))),
                'place_of_birth': 'Lomé', 'academic_year_id': year.id, 'classroom_id': c.id,
                'enrollment_date': year.date_start, 'state': 'enrolled', 'city': 'Lomé',
                'father_name': '%s %s' % (random.choice(LAST), random.choice(FIRST)),
                'mother_name': '%s %s' % (random.choice(LAST), random.choice(FIRST))})
            added += 1
    cr.commit()
    return added


# --------------------------------------------------------------- orchestration
t0 = time.time()
years = [env['silina.academic.year'].search([('name', '=', n)], limit=1) for n in YEARS]
for i, year in enumerate(years):
    nxt = years[i + 1] if i + 1 < len(years) else None
    if year.state == 'closed':
        log('Année %s déjà clôturée' % year.name)
        continue
    log('=== Année %s ===' % year.name)
    if not year.is_current:
        year.action_activate()
        cr.commit()
    if i > 0:
        log('  nouveaux inscrits : %d' % enroll_newcomers(year))
    sizes = sorted(len(c.student_ids) for c in env['silina.classroom'].search(
        [('academic_year_id', '=', year.id)]))
    log('  effectifs par classe : min %d / max %d / total %d' % (sizes[0], sizes[-1], sum(sizes)))
    bill_year(year)
    for idx, period in enumerate(year.period_ids.sorted('sequence')):
        n = run_period(year, period, idx)
        discipline(year, period)
        log('  %s : %d notes saisies par les enseignants' % (period.name, n))
    close_year(year, nxt)
    log('  (%.0fs écoulées)' % (time.time() - t0))
log('SIMULATION TERMINÉE')
