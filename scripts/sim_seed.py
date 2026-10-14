# -*- coding: utf-8 -*-
"""Phase 1 de la simulation SILINA-EDU : structure + comptes + élèves de la 1re année.

Rejouable (idempotent). À exécuter dans une base de TEST uniquement :
    docker exec -i odoo1_app odoo shell -d csbonscitoyens_sim --no-http \
        -c /etc/odoo/odoo.conf < scripts/sim_seed.py
"""
import random
from datetime import date

PASSWORD = 'P@ssword123!'
random.seed(2024)
from odoo import api  # noqa: E402
env = api.Environment(env.cr, env.uid, dict(  # noqa: F821
    tracking_disable=True, mail_create_nolog=True,
    mail_create_nosubscribe=True, no_reset_password=True))

Year = env['silina.academic.year']
Level = env['silina.level']
Classroom = env['silina.classroom'].with_context(skip_classroom_copy=True)
Subject = env['silina.subject']
Assignment = env['silina.subject.assignment']
Teacher = env['silina.teacher']
Student = env['silina.student']
Users = env['res.users']
Employee = env['hr.employee']

# ---------------------------------------------------------------- paramètres
company = env.company
company.write({
    'name': 'Complexe Scolaire Bons Citoyens',
    'silina_pass_average': 10.0,
    'silina_indulgence_average': 10.0,   # règle stricte : moyenne >= moyenne de passage
    'silina_director_name': 'M. Kossi AGBODJAN',
    'silina_school_name': 'Complexe Scolaire Bons Citoyens',
    'silina_header_phone': '+228 90 00 00 00',
    'silina_header_email': 'contact@bonscitoyens.tg',
    'silina_header_address': 'Lomé, Togo',
    'silina_header_extra': 'Agrément N° 0123/MEPSTA/2020',
    'silina_footer_text': 'Ce bulletin ne doit pas être remis en duplicata.',
})
company.partner_id.write({'city': 'Lomé'})
company.write({'city': 'Lomé'})

# ---------------------------------------------------------------- années
YEARS = [
    ('2024-2025', date(2024, 9, 2), date(2025, 7, 4)),
    ('2025-2026', date(2025, 9, 1), date(2026, 7, 3)),
    ('2026-2027', date(2026, 9, 1), date(2027, 7, 2)),
]
years = {}
for name, start, end in YEARS:
    y = Year.search([('name', '=', name)], limit=1)
    if not y:
        y = Year.with_context(skip_classroom_copy=True).create({
            'name': name, 'code': name, 'date_start': start, 'date_end': end,
            'period_type': 'trimester'})
    if not y.period_ids:
        y.action_generate_periods()
    years[name] = y
first_year = years['2024-2025']
if first_year.state != 'active' and not Year.search([('is_current', '=', True)]):
    first_year.action_activate()

# ---------------------------------------------------------------- niveaux
LEVELS = ['CRECHE', 'CI', 'CP1', 'CP2', 'CE1', 'CE2', 'CM1', 'CM2',
          '6EME', '5EME', '4EME', '3EME']
levels = {c: Level.search([('code', '=', c)], limit=1) for c in LEVELS}
assert all(levels.values()), 'niveaux manquants'

# ---------------------------------------------------------------- enseignants
# (login, prénom, nom, genre, spécialisation, matières, niveaux enseignés, titulaire de)
PRIM = ['CP1', 'CP2', 'CE1', 'CE2', 'CM1', 'CM2']
COLL = ['6EME', '5EME', '4EME', '3EME']
TEACHERS = [
    ('akouvi.mensah', 'Akouvi', 'MENSAH', 'female', 'primary', 'ALL_PRESCHOOL', ['CRECHE'], 'CRECHE'),
    ('ama.koffi', 'Ama', 'KOFFI', 'female', 'primary', 'ALL_PRESCHOOL', ['CI'], 'CI'),
    ('edem.agbo', 'Edem', 'AGBO', 'male', 'primary', 'ALL_PRIMARY', ['CP1'], 'CP1'),
    ('yawa.tete', 'Yawa', 'TETE', 'female', 'primary', 'ALL_PRIMARY', ['CP2'], 'CP2'),
    ('kodjo.amegah', 'Kodjo', 'AMEGAH', 'male', 'primary', 'ALL_PRIMARY', ['CE1'], 'CE1'),
    ('afi.dosseh', 'Afi', 'DOSSEH', 'female', 'primary', 'ALL_PRIMARY', ['CE2'], 'CE2'),
    ('komlan.adjovi', 'Komlan', 'ADJOVI', 'male', 'primary', 'ALL_PRIMARY', ['CM1'], 'CM1'),
    ('esso.lawson', 'Esso', 'LAWSON', 'male', 'primary', 'ALL_PRIMARY', ['CM2'], 'CM2'),
    ('mawuli.gbeto', 'Mawuli', 'GBETO', 'male', 'all', ['EPS'], LEVELS, None),
    ('sena.klutse', 'Séna', 'KLUTSE', 'female', 'all',
     ['ART', 'CHANT', 'DESSIN', 'TM', 'MUS'], LEVELS[:8], None),
    ('kossi.amouzou', 'Kossi', 'AMOUZOU', 'male', 'middle', ['FR'], COLL, '6EME'),
    ('dela.atsou', 'Délali', 'ATSOU', 'female', 'middle', ['MATH'], COLL, '5EME'),
    ('koami.nyaku', 'Koami', 'NYAKU', 'male', 'middle', ['ANG'], COLL, '4EME'),
    ('abla.sodji', 'Abla', 'SODJI', 'female', 'middle', ['HISTGEO', 'ECM'], COLL, '3EME'),
    ('yao.fiawoo', 'Yao', 'FIAWOO', 'male', 'middle', ['PC', 'SVT'], COLL, None),
]
group_teacher = env.ref('silina_edu.group_silina_edu_teacher')


def make_user(login, name, groups):
    u = Users.search([('login', '=', login)], limit=1)
    vals = {'name': name, 'login': login, 'email': login if '@' in login else login + '@bonscitoyens.tg',
            'password': PASSWORD, 'groups_id': [(6, 0, [g.id for g in groups])]}
    if u:
        u.write({'password': PASSWORD})
        return u
    return Users.with_context(no_reset_password=True).create(vals)


teachers = {}
for i, (login, first, last, gender, spec, subj, lvls, titular) in enumerate(TEACHERS, start=1):
    full = '%s %s' % (last, first)
    user = make_user(login, full, [group_teacher])
    emp = Employee.search([('user_id', '=', user.id)], limit=1)
    if not emp:
        emp = Employee.create({'name': full, 'user_id': user.id,
                               'work_email': user.email})
    t = Teacher.search([('employee_id', '=', emp.id)], limit=1)
    if not t:
        t = Teacher.create({'employee_id': emp.id, 'teacher_code': 'ENS%03d' % i,
                            'specialization': spec,
                            'date_start': date(2024, 9, 1)})
    teachers[login] = t

# ---------------------------------------------------------------- autres comptes
g = lambda x: env.ref('silina_edu.group_silina_edu_' + x)  # noqa: E731
make_user('coordinateur', 'Coordinateur pédagogique', [g('coordinator')])
make_user('secretaire', 'Secrétariat', [g('secretary')])
make_user('directeur', 'Directeur', [g('manager')])
acc_groups = [g('user')]
for xid in ('account.group_account_invoice',):
    grp = env.ref(xid, raise_if_not_found=False)
    if grp:
        acc_groups.append(grp)
make_user('comptable', 'Comptable', acc_groups)

# ---------------------------------------------------------------- classes + programmes
PRESCHOOL_SUBJECTS = {
    'CRECHE': ['LANGAGE', 'EDU_SOC', 'ART', 'CHANT', 'EPS'],
    'CI': ['LANGAGE', 'LECTURE', 'CALC_MENTAL', 'EDU_SOC', 'ART', 'CHANT', 'DESSIN', 'EPS'],
}
COEF = {'FR': 3, 'MATH': 3, 'ANG': 2, 'HISTGEO': 2, 'PC': 2, 'SVT': 2, 'ECM': 1,
        'LECTURE': 2, 'DICTEE': 2, 'REDAC': 2}
HOURS = {'FR': 5, 'MATH': 5, 'EPS': 2, 'ANG': 3, 'HISTGEO': 3, 'PC': 3, 'SVT': 2, 'ECM': 1}
tit_by_level = {t[7]: teachers[t[0]] for t in TEACHERS if t[7]}
teacher_of = {}   # (niveau, matière) -> enseignant


def subjects_for(code):
    if code in PRESCHOOL_SUBJECTS:
        return PRESCHOOL_SUBJECTS[code]
    lv = levels[code]
    return [s.code for s in Subject.search([('degree_ids', 'in', lv.id)], order='sequence')]


def teacher_for(code, scode):
    # spécialistes d'abord
    for login, _f, _l, _g, _s, subj, lvls, _t in TEACHERS:
        if isinstance(subj, list) and scode in subj and code in lvls:
            return teachers[login]
    return tit_by_level.get(code)


classrooms = {}
for yname, y in years.items():
    for code in LEVELS:
        lv = levels[code]
        c = Classroom.search([('code', '=', code), ('academic_year_id', '=', y.id)], limit=1)
        if not c:
            c = Classroom.create({'name': lv.name, 'code': code, 'level_id': lv.id,
                                  'academic_year_id': y.id,
                                  'main_teacher_id': tit_by_level[code].id
                                  if code in tit_by_level else
                                  teachers['kossi.amouzou'].id})
        classrooms[(yname, code)] = c
        for scode in subjects_for(code):
            subj = Subject.search([('code', '=', scode)], limit=1)
            teacher = teacher_for(code, scode)
            if not subj or not teacher:
                continue
            if not Assignment.search([('classroom_id', '=', c.id), ('subject_id', '=', subj.id)], limit=1):
                Assignment.create({'classroom_id': c.id, 'subject_id': subj.id,
                                   'teacher_id': teacher.id,
                                   'coefficient': COEF.get(scode, subj.coefficient or 1.0),
                                   'hours_per_week': HOURS.get(scode, 2)})
env.cr.commit()

# ---------------------------------------------------------------- élèves de la 1re année
MALE = ['Kokou', 'Komi', 'Koffi', 'Yao', 'Mawuli', 'Edem', 'Kodjo', 'Senyo', 'Folly', 'Elom',
        'Kwami', 'Dodzi', 'Prince', 'Samuel', 'David', 'Joël', 'Éric', 'Bruno', 'Gilbert', 'Franck']
FEMALE = ['Ama', 'Akossiwa', 'Afi', 'Abla', 'Yawa', 'Adjovi', 'Mawuena', 'Elodie', 'Grâce', 'Estelle',
          'Mariam', 'Fatou', 'Sandrine', 'Ruth', 'Esther', 'Linda', 'Carine', 'Pélagie', 'Noëlle', 'Djamila']
LAST = ['AGBO', 'ATSOU', 'MENSAH', 'KOFFI', 'TETE', 'AMEGAH', 'DOSSEH', 'LAWSON', 'GBETO', 'KLUTSE',
        'AMOUZOU', 'NYAKU', 'SODJI', 'FIAWOO', 'ADJOVI', 'AKAKPO', 'BEKUI', 'EDORH', 'GLOKPOR',
        'HOUNKPATI', 'KPODAR', 'LOGLO', 'MEDJI', 'NOMEDJI', 'OLYMPIO', 'PALANGA', 'SEWAVI', 'TOGBE',
        'WONU', 'ZINSOU', 'AYITE', 'ALOGNON', 'BOCCO', 'DJOSSOU', 'EKLOU', 'FOLLY', 'GAMEDZI']
AGE = {'CRECHE': 3, 'CI': 4, 'CP1': 6, 'CP2': 7, 'CE1': 8, 'CE2': 9, 'CM1': 10, 'CM2': 11,
       '6EME': 12, '5EME': 13, '4EME': 14, '3EME': 15}


def new_student(year, classroom, code):
    gender = random.choice(['male', 'female'])
    first = random.choice(MALE if gender == 'male' else FEMALE)
    last = random.choice(LAST)
    age = AGE[code] + random.choice([0, 0, 0, 1])
    dob = date(year.date_start.year - age, random.randint(1, 12), random.randint(1, 28))
    return {
        'first_name': first, 'last_name': last, 'gender': gender, 'date_of_birth': dob,
        'place_of_birth': 'Lomé', 'academic_year_id': year.id, 'classroom_id': classroom.id,
        'enrollment_date': year.date_start, 'state': 'enrolled',
        'father_name': '%s %s' % (last, random.choice(MALE)),
        'mother_name': '%s %s' % (random.choice(LAST), random.choice(FEMALE)),
        'city': 'Lomé', 'phone': '+228 9%d %02d %02d %02d' % (
            random.randint(0, 9), random.randint(0, 99), random.randint(0, 99), random.randint(0, 99)),
    }


MIN_PER_CLASS = 15
for code in LEVELS:
    c = classrooms[('2024-2025', code)]
    missing = max(0, random.randint(MIN_PER_CLASS, 19) - len(c.student_ids))
    for _ in range(missing):
        Student.create(new_student(first_year, c, code))
env.cr.commit()

print('SEED OK')
for (yname, code), c in classrooms.items():
    if yname == '2024-2025':
        print(yname, code, len(c.student_ids), 'élèves,', len(c.subject_assignment_ids), 'matières')
print('enseignants:', Teacher.search_count([]), '| utilisateurs:', Users.search_count([]))
