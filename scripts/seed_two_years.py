# -*- coding: utf-8 -*-
"""Jeu de données SILINA-EDU : trois années scolaires.

* 2024-2025 : complète (3 trimestres, notes, résultats validés, décisions) ;
* 2025-2026 : complète (idem, après passage 2024-2025 -> 2025-2026) ;
* 2026-2027 : EN COURS (année courante, date du jour 2026-10-10) : seul le 1er
  trimestre est saisi (compositions mensuelles 1-3 et devoirs/compositions T1),
  résultats de T1 calculés, T2/T3 vides.

Les passages d'une année à l'autre utilisent l'assistant
``silina.bulk.student.promotion.wizard`` en mode « selon décision annuelle ».
Chaque enseignant a un compte de connexion (res.users, login
prenom.nom@kri-kri.test, mot de passe demo1234, groupe SILINA « Enseignant »)
et les examens / notes sont créés avec ``.with_user(utilisateur enseignant)``.

Usage (variable ``env`` fournie par le shell Odoo) :

    odoo shell -d silina_test < scripts/seed_two_years.py
    # ou, depuis un shell interactif :
    exec(open('scripts/seed_two_years.py').read())

Hors Odoo (``python3 scripts/seed_two_years.py``) : simulation « à blanc » qui
affiche les effectifs, moyennes et décisions attendus (aucune base nécessaire).

Idempotent autant que possible (recherche avant création) ; ``env.cr.commit()``
à la fin.
"""

# Bascule : True -> examens/notes créés via .with_user(compte enseignant)
# (repli automatique sur sudo + create_uid via SQL si l'accès est refusé) ;
# False -> tout en sudo, sans positionner create_uid.
SEED_AS_TEACHER = True


def _seed_main(env, SEED_AS_TEACHER=True):
    import random
    import unicodedata
    from datetime import date, timedelta

    # ==================================================================
    # 1. DONNÉES DE RÉFÉRENCE (sans Odoo)
    # ==================================================================
    YEARS = {
        '2024-2025': (date(2024, 10, 1), date(2025, 7, 15)),
        '2025-2026': (date(2025, 10, 1), date(2026, 7, 15)),
        '2026-2027': (date(2026, 10, 1), date(2027, 7, 15)),
    }
    YEAR_ORDER = ['2024-2025', '2025-2026', '2026-2027']
    # Saisie plafonnée à la date du jour (2026-10-10) pour l'année en cours
    DATE_CAP = {'2026-2027': date(2026, 10, 9)}
    PCODES = ['T1', 'T2', 'T3']
    FILLED_PERIODS = {'2024-2025': PCODES, '2025-2026': PCODES, '2026-2027': ['T1']}
    FILLED_MONTHS = {'2024-2025': range(1, 10), '2025-2026': range(1, 10),
                     '2026-2027': range(1, 4)}

    # Niveaux (ordre du cursus) et degré de bulletin
    LEVEL_CODES = ['CRECHE', 'CI', 'CP1', 'CP2', 'CE1', 'CE2', 'CM1', 'CM2',
                   '6EME', '5EME', '4EME']
    LEVEL_NEXT = dict(zip(LEVEL_CODES, LEVEL_CODES[1:] + [None]))
    LEVELS_BY_YEAR = {
        '2024-2025': LEVEL_CODES[:9],      # CRECHE .. 6EME
        '2025-2026': LEVEL_CODES[:10],     # + 5EME
        '2026-2027': LEVEL_CODES[:11],     # + 4EME
    }
    LEVEL_AGE = {'CRECHE': 3, 'CI': 5, 'CP1': 6, 'CP2': 7, 'CE1': 8, 'CE2': 9,
                 'CM1': 10, 'CM2': 11, '6EME': 12, '5EME': 13, '4EME': 14}

    def kind_of(code):
        if code in ('CRECHE', 'CI'):
            return 'preschool'
        if code in ('6EME', '5EME', '4EME'):
            return 'college'
        return 'primary'

    # Enseignants : clé -> (nom complet « NOM Prénom », spécialisation, qualification)
    TEACHERS = {
        'ALIDOU': ('ALIDOU Razak', 'middle', 'master'),
        'IBRAHIM': ('IBRAHIM Fousséni', 'middle', 'license'),
        'LAWSON': ('LAWSON Kodjo', 'middle', 'license'),
        'BOUKARI': ('BOUKARI Tchalla', 'middle', 'license'),
        'MOUSSA': ('MOUSSA Abdou', 'middle', 'master'),
        'KANGNI': ('KANGNI Essivi', 'primary', 'bac'),      # CRECHE
        'AMEGAN': ('AMEGAN Kafui', 'primary', 'bac'),       # CI
        'NOMENYO': ('NOMENYO Dela', 'primary', 'bac'),      # CP1
        'AGBEKO': ('AGBEKO Mawussi', 'primary', 'license'),  # CP2
        'FOLLY': ('FOLLY Edem', 'primary', 'bac'),          # CE1
        'TCHEDRE': ('TCHEDRE Akouavi', 'primary', 'license'),  # CE2
        'BAKAI': ('BAKAI Kossi', 'primary', 'bac'),         # CM1
        'DJOBO': ('DJOBO Ayawa', 'primary', 'license'),     # CM2
    }
    # Titulaire de chaque classe (clé de TEACHERS)
    MAIN_TEACHER = {
        'CRECHE': 'KANGNI', 'CI': 'AMEGAN', 'CP1': 'NOMENYO', 'CP2': 'AGBEKO',
        'CE1': 'FOLLY', 'CE2': 'TCHEDRE', 'CM1': 'BAKAI', 'CM2': 'DJOBO',
        '6EME': 'ALIDOU', '5EME': 'IBRAHIM', '4EME': 'LAWSON',
    }

    # (xml-id matière, clé enseignant) dans l'ordre du bulletin collège
    COLLEGE_SUBJECTS = [
        ('subject_english', 'ALIDOU'),
        ('subject_french', 'IBRAHIM'),
        ('subject_history', 'LAWSON'),
        ('subject_civic', 'BOUKARI'),
        ('subject_sport', 'BOUKARI'),
        ('subject_math', 'MOUSSA'),
        ('subject_physics', 'LAWSON'),
        ('subject_svt', 'MOUSSA'),
    ]
    PRIMARY_SUBJECTS = [
        'subject_livret_copie', 'subject_livret_dictee', 'subject_livret_redaction',
        'subject_livret_etude_texte', 'subject_livret_langage', 'subject_livret_lecture',
        'subject_livret_recitation', 'subject_livret_calcul_mental',
        'subject_livret_exo_calcul', 'subject_livret_probleme',
        'subject_livret_sc_humaines', 'subject_livret_sc_techno',
        'subject_livret_edu_sociale', 'subject_livret_chant', 'subject_livret_dessin',
        'subject_livret_tm', 'subject_sport',
    ]
    PRESCHOOL_SUBJECTS = [
        'subject_livret_langage', 'subject_livret_calcul_mental',
        'subject_livret_dessin', 'subject_sport',
    ]

    # Valeurs EXACTES du bulletin T1 de référence d'AKAKPO Mariama :
    # xml-id matière -> (notes de devoir [1 ou 2], composition)
    MARIAMA_T1 = {
        'subject_english': ([6.0, 8.0], 10.5),       # 7,00 / 10,50
        'subject_french': ([9.25], 10.0),            # 9,25 / 10,00
        'subject_history': ([10.0, 11.5], 11.5),     # 10,75 / 11,50
        'subject_civic': ([4.75], 2.5),              # 4,75 / 2,50
        'subject_sport': ([5.0, 7.0], 10.5),         # 6,00 / 10,50
        'subject_math': ([8.0], 5.0),                # 8,00 / 5,00
        'subject_physics': ([7.5, 8.5], 3.5),        # 8,00 / 3,50
        'subject_svt': ([9.5], 8.5),                 # 9,50 / 8,50
    }

    # Élèves 2024-2025 saisis à la main : (NOM, Prénom, sexe, naissance, [cibles T1-T3]).
    # Collège : cibles sur la grille k/64 pour obtenir en T1 exactement 14,69 /
    # 12,20 / 11,09 / 10,03 / 7,83 : plus forte 14,69, plus faible 7,83, classe 11,17.
    EXPLICIT_2024 = {
        '6EME': [
            ('AKAKPO', 'Mariama', 'female', date(2012, 2, 27), [501 / 64.0, 9.2, 10.2]),
            ('AGBODJAN', 'Kossi', 'male', date(2011, 11, 3), [940 / 64.0, 14.4, 15.0]),
            ('TCHAGBALE', 'Abla', 'female', date(2012, 5, 19), [781 / 64.0, 12.6, 12.9]),
            ('ATTIOGBE', 'Yao', 'male', date(2011, 8, 9), [710 / 64.0, 10.6, 11.4]),
            ('SANVEE', 'Komi', 'male', date(2012, 1, 14), [642 / 64.0, 8.4, 7.9]),
        ],
        'CE2': [
            ('KOUDJO', 'Selom', 'male', date(2016, 3, 12), [15.8, 16.2, 16.0]),
            ('DOSSOU', 'Ablavi', 'female', date(2016, 7, 21), [13.4, 13.0, 13.8]),
            ('ADJEODA', 'Komlan', 'male', date(2015, 12, 2), [11.6, 12.0, 11.2]),
            ('ZINSOU', 'Pélagie', 'female', date(2016, 1, 30), [9.4, 9.8, 9.5]),
            ('HOUNKPATIN', 'Yawa', 'female', date(2015, 9, 8), [8.2, 7.6, 8.0]),
            ('MENSAH', 'Kwami', 'male', date(2016, 5, 17), [12.5, 12.9, 13.1]),
        ],
        'CI': [
            ('AWOUDJA', 'Esso', 'male', date(2020, 4, 6), [16.1, 15.6, 16.4]),
            ('KOMBATE', 'Pamela', 'female', date(2020, 8, 25), [13.2, 13.9, 14.0]),
            ('BEDOU', 'Kodjo', 'male', date(2020, 2, 11), [10.8, 11.4, 11.0]),
            ('ASSIH', 'Mawuli', 'male', date(2020, 11, 3), [9.2, 9.6, 9.1]),
        ],
    }
    # Niveau « de fond » des élèves explicites pour les années suivantes
    EXPLICIT_BASE = {
        ('AKAKPO', 'Mariama'): 9.8, ('AGBODJAN', 'Kossi'): 14.9,
        ('TCHAGBALE', 'Abla'): 12.0, ('ATTIOGBE', 'Yao'): 10.5,
        ('SANVEE', 'Komi'): 9.6, ('KOUDJO', 'Selom'): 16.0,
        ('DOSSOU', 'Ablavi'): 13.3, ('ADJEODA', 'Komlan'): 11.5,
        ('ZINSOU', 'Pélagie'): 10.0, ('HOUNKPATIN', 'Yawa'): 8.4,
        ('MENSAH', 'Kwami'): 12.8, ('AWOUDJA', 'Esso'): 16.0,
        ('KOMBATE', 'Pamela'): 13.8, ('BEDOU', 'Kodjo'): 11.0,
        ('ASSIH', 'Mawuli'): 9.8,
    }

    # Sanctions : (NOM, Prénom, période, fraction de la période, type, motif)
    SANCTIONS = {
        '2024-2025': [
            ('SANVEE', 'Komi', 'T2', 0.5, 'sanction_type_blame',
             'Bavardages répétés et perturbation du cours de mathématiques.'),
            ('SANVEE', 'Komi', 'T3', 0.4, 'sanction_type_warning',
             'Retards répétés en début de matinée.'),
            ('ATTIOGBE', 'Yao', 'T1', 0.7, 'sanction_type_warning',
             'Oubli répété du matériel scolaire.'),
            ('HOUNKPATIN', 'Yawa', 'T2', 0.4, 'sanction_type_warning',
             'Bagarre dans la cour de récréation.'),
        ],
        '2025-2026': [
            ('SANVEE', 'Komi', 'T1', 0.6, 'sanction_type_warning',
             'Travail non fait à plusieurs reprises.'),
            ('AKAKPO', 'Mariama', 'T2', 0.5, 'sanction_type_warning',
             'Bavardages en classe.'),
        ],
        '2026-2027': [
            ('AKAKPO', 'Mariama', 'T1', 0.5, 'sanction_type_warning',
             'Oubli du cahier de textes.'),
        ],
    }

    # Réservoir de noms pour les nouveaux inscrits (déterministe, sans collision
    # avec les enseignants ni les élèves explicites)
    POOL_LAST = [
        'AMOUZOU', 'ATAKORA', 'AYIVI', 'DAOU', 'EKLOU', 'GADO', 'HOUNKANRIN',
        'KLUTSE', 'KOUMAI', 'OURO', 'PALANGA', 'SAMA', 'TAGBA', 'TOSSOU',
        'WILSON', 'YAOVI', 'ZOUMAROU', 'ABALO', 'BARCOLA', 'DOVI', 'ESSOHANAM',
        'GBATI', 'DEGBOE', 'KPEGLO', 'GNASSINGBE', 'TOGNON', 'GBEDEMAH', 'LAMBONI',
        'AGBO', 'ADOTE',
    ]
    POOL_MALE = ['Kossi', 'Komi', 'Yao', 'Kodjo', 'Koffi', 'Edem', 'Selom', 'Yawo',
                 'Senam', 'Elom', 'Koami', 'Tchilabalo', 'Akoete', 'Ayaovi', 'Kokou']
    POOL_FEMALE = ['Afi', 'Ama', 'Akossiwa', 'Adjoa', 'Efua', 'Abla', 'Mawuena',
                   'Kafui', 'Essi', 'Sika', 'Dzifa', 'Enyonam', 'Eyram', 'Mawusi', 'Afiwa']
    used_names = set((l, norm_first_) for (l, norm_first_) in EXPLICIT_BASE)
    for _lst in EXPLICIT_2024.values():
        for _p in _lst:
            used_names.add((_p[0], _p[1]))
    POOL = []
    _rng = random.Random('pool')
    for _l in POOL_LAST:
        for _f in POOL_MALE:
            POOL.append((_l, _f, 'male'))
        for _f in POOL_FEMALE:
            POOL.append((_l, _f, 'female'))
    _rng.shuffle(POOL)
    POOL = [p for p in POOL if (p[0], p[1]) not in used_names]
    pool_state = {'i': 0}

    def next_pupil():
        p = POOL[pool_state['i']]
        pool_state['i'] += 1
        return p

    # ==================================================================
    # 2. GÉNÉRATION DE NOTES (déterministe)
    # ==================================================================
    def clip(v, lo, hi):
        return max(lo, min(hi, v))

    def norm_first(first):
        return ' '.join(w.capitalize() for w in first.split())

    def q2f(q):
        return q / 4.0

    def size_for(year_name, code):
        """Effectif visé d'une classe (4 à 6 élèves)."""
        return 4 + random.Random('size|%s|%s' % (year_name, code)).randrange(0, 3)

    def base_of(last, first):
        if (last, first) in EXPLICIT_BASE:
            return EXPLICIT_BASE[(last, first)]
        return random.Random('base|%s|%s' % (last, first)).uniform(7.8, 16.8)

    def explicit_targets(year_name, code, last, first):
        if year_name == YEAR_ORDER[0]:
            for l, f, _g, _d, tg in EXPLICIT_2024.get(code, []):
                if (l, f) == (last, first):
                    return tg
        return None

    def targets_for(year_name, code, last, first, repeated):
        tg = explicit_targets(year_name, code, last, first)
        if tg:
            return tg
        rng = random.Random('tg|%s|%s|%s' % (year_name, last, first))
        t1 = clip(base_of(last, first) + (1.2 if repeated else 0.0)
                  + rng.uniform(-0.7, 0.7), 5.0, 18.5)
        return [t1, clip(t1 + rng.uniform(-0.8, 1.0), 4.0, 19.0),
                clip(t1 + rng.uniform(-0.8, 1.2), 4.0, 19.0)]

    def gen_college_period(rng, k, n_subj):
        """n_subj couples (devoir, composition) en quarts de point (0..80) dont
        la somme vaut exactement k : moyenne générale (coef 1) = k / 64."""
        n = 2 * n_subj
        base = k / float(n)
        vals = [int(clip(round(base + rng.uniform(-14, 14)), 0, 80)) for _i in range(n)]
        diff = k - sum(vals)
        guard = 0
        while diff and guard < 200000:
            i = rng.randrange(n)
            step = 1 if diff > 0 else -1
            if 0 <= vals[i] + step <= 80:
                vals[i] += step
                diff -= step
            guard += 1
        return [(vals[2 * i], vals[2 * i + 1]) for i in range(n_subj)]

    def split_devoir(rng, dq):
        """Un devoir (1 note) ou deux devoirs dont la moyenne vaut exactement dq."""
        if rng.random() < 0.5:
            e = rng.randint(1, 8)
            if dq - e >= 0 and dq + e <= 80:
                return [q2f(dq - e), q2f(dq + e)]
        return [q2f(dq)]

    def build_college_marks(year_name, last, first, targets):
        """-> {pcode: {subject_xid: ([notes devoir], composition)}}"""
        out = {}
        for pi, pcode in enumerate(PCODES):
            if year_name == '2024-2025' and pcode == 'T1' and (last, first) == ('AKAKPO', 'Mariama'):
                out[pcode] = dict(MARIAMA_T1)
                continue
            rng = random.Random('college|%s|%s|%s|%s' % (year_name, last, first, pcode))
            k = int(round(targets[pi] * 64))
            pairs = gen_college_period(rng, k, len(COLLEGE_SUBJECTS))
            res = {}
            for (xid, _t), (dq, cq) in zip(COLLEGE_SUBJECTS, pairs):
                res[xid] = (split_devoir(rng, dq), q2f(cq))
            out[pcode] = res
        return out

    def build_monthly_marks(kind, year_name, last, first, targets, n_subj):
        """-> {n (1..9): [note par discipline]} (barème 20, pas de 0,25)."""
        rng = random.Random('%s|%s|%s|%s' % (kind, year_name, last, first))
        off = [rng.uniform(-2.0, 2.0) for _i in range(n_subj)]
        m = sum(off) / n_subj
        off = [o - m for o in off]
        notes = {}
        for n in range(1, 10):
            tgt = targets[(n - 1) // 3]
            notes[n] = [q2f(int(clip(round((tgt + off[s] + rng.uniform(-1.8, 1.8)) * 4), 0, 80)))
                        for s in range(n_subj)]
        return notes

    def n_subjects(code):
        k = kind_of(code)
        return {'college': len(COLLEGE_SUBJECTS), 'primary': len(PRIMARY_SUBJECTS),
                'preschool': len(PRESCHOOL_SUBJECTS)}[k]

    def r2(x):
        return round(x + 1e-9, 2)

    def period_averages(year_name, code, last, first, targets):
        """Moyennes de période (règles du module) des trois trimestres."""
        k = kind_of(code)
        avgs = []
        if k == 'college':
            marks = build_college_marks(year_name, last, first, targets)
            for pcode in PCODES:
                subj = [(sum(d) / len(d) + c) / 2.0 for d, c in marks[pcode].values()]
                avgs.append(r2(sum(subj) / len(subj)))
        else:
            ns = n_subjects(code)
            notes = build_monthly_marks('prim' if k == 'primary' else 'pre',
                                        year_name, last, first, targets, ns)
            for p in range(3):
                subj = [sum(notes[3 * p + j + 1][s] for j in range(3)) / 3.0
                        for s in range(ns)]
                avgs.append(r2(sum(subj) / ns))
        return avgs

    def decision_of(avg):
        if avg >= 10.0:
            return 'passed'
        if avg >= 9.0:
            return 'indulgence'
        return 'repeat'

    # ---- simulation « à blanc » de toute la scolarité (effectifs, décisions)
    def simulate():
        pool_state['i'] = 0
        roster = {c: [] for c in LEVELS_BY_YEAR[YEAR_ORDER[0]]}
        for code, lst in EXPLICIT_2024.items():
            roster[code] = [{'last': l, 'first': f, 'repeated': False} for l, f, _g, _d, _t in lst]
        for yi, yname in enumerate(YEAR_ORDER):
            for code in LEVELS_BY_YEAR[yname]:
                roster.setdefault(code, [])
                if yname == YEAR_ORDER[0] and code in EXPLICIT_2024:
                    continue  # classes saisies à la main : effectif figé
                while len(roster[code]) < size_for(yname, code):
                    l, f, _g = next_pupil()
                    roster[code].append({'last': l, 'first': f, 'repeated': False})
            print('=== %s ===' % yname)
            nxt = {c: [] for c in LEVEL_CODES}
            for code in LEVELS_BY_YEAR[yname]:
                print('  %s (%d élèves)' % (code, len(roster[code])))
                t1s = []
                rows = []
                for p in roster[code]:
                    tg = targets_for(yname, code, p['last'], p['first'], p['repeated'])
                    avgs = period_averages(yname, code, p['last'], p['first'], tg)
                    ann = r2(sum(avgs) / 3.0)
                    dec = decision_of(ann)
                    rows.append((p, avgs, ann, dec))
                    t1s.append(avgs[0])
                    if dec == 'repeat':
                        nxt[code].append({'last': p['last'], 'first': p['first'], 'repeated': True})
                    elif LEVEL_NEXT[code]:
                        nxt[LEVEL_NEXT[code]].append(
                            {'last': p['last'], 'first': p['first'], 'repeated': False})
                print('    T1 : max %.2f / min %.2f / moy. classe %.2f' % (
                    max(t1s), min(t1s), r2(sum(t1s) / len(t1s))))
                for p, avgs, ann, dec in sorted(rows, key=lambda r: -r[2]):
                    print('    %-12s %-12s T1-T3 %s annuel %.2f -> %s%s' % (
                        p['last'], p['first'], avgs, ann, dec,
                        ' (redoublant)' if p['repeated'] else ''))
            roster = nxt

    if env is None:
        print('=== Simulation à blanc (aucune base) ===')
        simulate()
        return

    # ==================================================================
    # 3. ACCÈS ODOO
    # ==================================================================
    from odoo.exceptions import AccessError

    # Pas de suivi/notification mail : accélère et évite le bruit.
    env = env(context=dict(env.context, tracking_disable=True, mail_create_nolog=True,
                           mail_notrack=True, mail_activity_quick_update=True,
                           no_reset_password=True))
    Year = env['silina.academic.year']
    Classroom = env['silina.classroom']
    Assignment = env['silina.subject.assignment']
    Teacher = env['silina.teacher']
    Employee = env['hr.employee']
    Users = env['res.users']
    Student = env['silina.student']
    Parent = env['silina.parent']
    Exam = env['silina.exam']
    ExamResult = env['silina.exam.result']
    PeriodResult = env['silina.period.result']
    Annual = env['silina.annual.result']
    Absence = env['silina.discipline.absence']
    Late = env['silina.discipline.late']
    Sanction = env['silina.discipline.sanction']
    Conduct = env['silina.discipline.conduct']
    Wizard = env['silina.bulk.student.promotion.wizard']

    def ref(xid):
        return env.ref('silina_edu.' + xid)

    teacher_cache = {}
    teacher_users = {}
    created_logins = []
    denied = set()  # modèles pour lesquels with_user a été refusé (repli sudo)

    # ------------------------------------------------------------------
    # Société
    # ------------------------------------------------------------------
    company = env.company
    cvals = {
        'name': "Collège d'Enseignement Général Kri-Kri",
        'city': 'Kri-Kri',
        'silina_director_name': 'SEYDOU Issa',
        'silina_pass_average': 10.0,
        'silina_indulgence_average': 9.0,
    }
    togo = env['res.country'].search([('code', '=', 'TG')], limit=1)
    if togo:
        cvals['country_id'] = togo.id
    company.write(cvals)

    # ------------------------------------------------------------------
    # Enseignants + comptes de connexion
    # ------------------------------------------------------------------
    def ascii_lower(s):
        return unicodedata.normalize('NFKD', s).encode('ascii', 'ignore').decode().lower().replace(' ', '')

    def teacher_group_ids():
        tg = ref('group_silina_edu_teacher')
        groups = tg
        if 'trans_implied_ids' in tg._fields:
            groups |= tg.trans_implied_ids
        # jamais de groupe coordinateur / administrateur
        groups -= (ref('group_silina_edu_coordinator') | ref('group_silina_edu_manager'))
        return groups.ids

    def get_teacher(key):
        if key in teacher_cache:
            return teacher_cache[key]
        full, spec, qual = TEACHERS[key]
        last, first = full.split(' ', 1)
        login = '%s.%s@kri-kri.test' % (ascii_lower(first), ascii_lower(last))
        user = Users.search([('login', '=', login)], limit=1)
        if not user:
            user = Users.create({
                'name': full, 'login': login, 'email': login, 'password': 'demo1234',
                'groups_id': [(6, 0, teacher_group_ids())],
            })
            created_logins.append(login)
        emp = Employee.search([('user_id', '=', user.id)], limit=1) \
            or Employee.search([('name', '=', full)], limit=1)
        if not emp:
            emp = Employee.create({'name': full})
        emp.write({'name': full, 'user_id': user.id, 'work_email': login})
        teacher = Teacher.search([('employee_id', '=', emp.id)], limit=1)
        if not teacher:
            subs = [ref(x).id for x, k in COLLEGE_SUBJECTS if k == key]
            teacher = Teacher.create({
                'employee_id': emp.id, 'specialization': spec, 'qualification': qual,
                'experience_years': 6, 'subject_ids': [(6, 0, subs)],
            })
        teacher_cache[key] = teacher
        teacher_users[key] = user
        return teacher

    def create_as(model, vals, tkey):
        """Crée `vals` (dict ou liste) en tant qu'utilisateur enseignant.

        Repli sudo + create_uid via SQL si l'accès est refusé (règles d'accès
        enseignant non encore en place)."""
        get_teacher(tkey)
        user = teacher_users[tkey]
        if SEED_AS_TEACHER and model._name not in denied:
            try:
                with env.cr.savepoint():
                    rec = model.with_user(user).create(vals)
                    return rec.sudo()
            except AccessError as e:
                denied.add(model._name)
                print('  [seed] accès refusé pour %s en tant que %s -> repli sudo '
                      '(create_uid via SQL) : %s' % (model._name, user.login, e))
        rec = model.sudo().create(vals)
        if SEED_AS_TEACHER:
            rec.flush_recordset()
            env.cr.execute(
                'UPDATE %s SET create_uid=%%s, write_uid=%%s WHERE id IN %%s' % model._table,
                (user.id, user.id, tuple(rec.ids)))
            rec.invalidate_recordset()
        return rec

    # ------------------------------------------------------------------
    # Années, classes, affectations, élèves
    # ------------------------------------------------------------------
    def get_year(name):
        start, end = YEARS[name]
        year = Year.search([('code', '=', name)], limit=1)
        if not year:
            year = Year.create({'name': name, 'code': name, 'date_start': start, 'date_end': end})
        year.action_generate_periods()
        return year

    def get_classroom(year, code):
        level = ref('level_' + code.lower())
        ccode = (level.code or '').replace(' ', '')
        classroom = Classroom.search(
            [('code', '=', ccode), ('academic_year_id', '=', year.id)], limit=1)
        teacher = get_teacher(MAIN_TEACHER[code])
        if not classroom:
            classroom = Classroom.create({
                'name': level.name, 'code': ccode, 'level_id': level.id,
                'academic_year_id': year.id, 'main_teacher_id': teacher.id,
            })
        elif not classroom.main_teacher_id:
            classroom.main_teacher_id = teacher.id
        return classroom

    def subject_pairs(code):
        """[(xml-id matière, clé enseignant)] d'une classe."""
        k = kind_of(code)
        if k == 'college':
            return list(COLLEGE_SUBJECTS)
        xids = PRIMARY_SUBJECTS if k == 'primary' else PRESCHOOL_SUBJECTS
        return [(x, MAIN_TEACHER[code]) for x in xids]

    def setup_assignments(classroom, code):
        for xid, tkey in subject_pairs(code):
            subject = ref(xid)
            if not Assignment.search_count([('classroom_id', '=', classroom.id),
                                            ('subject_id', '=', subject.id)]):
                Assignment.create({
                    'classroom_id': classroom.id, 'subject_id': subject.id,
                    'teacher_id': get_teacher(tkey).id, 'coefficient': 1.0,
                    'hours_per_week': 2.0,
                })

    def get_student(year, classroom, code, last, first, gender, dob=None):
        first = norm_first(first)
        student = Student.search([
            ('last_name', '=', last.upper()), ('first_name', '=', first),
            ('academic_year_id', '=', year.id)], limit=1)
        if student:
            return student
        if dob is None:
            y0 = year.date_start.year - LEVEL_AGE[code]
            r = random.Random('dob|%s|%s' % (last, first))
            dob = date(y0, r.randint(1, 12), r.randint(1, 28))
        rng = random.Random('parent|%s|%s' % (last, first))
        father_first = rng.choice(['Kokou', 'Yaovi', 'Kodjovi', 'Komlan', 'Messan', 'Têtê'])
        mother_first = rng.choice(['Akossiwa', 'Adjoa', 'Efua', 'Ama', 'Abra', 'Dédé'])
        if rng.random() < 0.5:
            relation, pname, pgender = 'father', '%s %s' % (last.upper(), father_first), 'male'
        else:
            relation, pname, pgender = 'mother', '%s %s' % (last.upper(), mother_first), 'female'
        parent = Parent.create({
            'name': pname, 'relation': relation, 'gender': pgender,
            'mobile': '+228 9%d %02d %02d %02d' % (
                rng.randint(0, 3), rng.randint(0, 99), rng.randint(0, 99), rng.randint(0, 99)),
            'city': 'Kri-Kri', 'is_financial_responsible': True,
            'occupation': rng.choice(['Commerçant', 'Enseignant', 'Agriculteur', 'Infirmière']),
        })
        vals = {
            'first_name': first, 'last_name': last.upper(), 'gender': gender,
            'date_of_birth': dob, 'place_of_birth': 'Kri-Kri',
            'nationality': togo.id if togo else False,
            'city': 'Kri-Kri', 'country_id': togo.id if togo else False,
            'academic_year_id': year.id, 'classroom_id': classroom.id,
            'enrollment_date': year.date_start, 'state': 'enrolled',
            'parent_ids': [(6, 0, [parent.id])],
        }
        vals['father_name' if relation == 'father' else 'mother_name'] = pname
        return Student.create(vals)

    def ensure_roster(year, classroom, code):
        """Élèves de la classe : explicites (1re année), promus (déjà en base)
        puis nouveaux inscrits jusqu'à l'effectif visé."""
        if year.code == YEAR_ORDER[0]:
            for l, f, g, d, _t in EXPLICIT_2024.get(code, []):
                get_student(year, classroom, code, l, f, g, d)
        students = Student.search([('classroom_id', '=', classroom.id),
                                   ('academic_year_id', '=', year.id)])
        if year.code == YEAR_ORDER[0] and code in EXPLICIT_2024:
            return students  # classes saisies à la main : effectif figé
        missing = size_for(year.code, code) - len(students)
        for _i in range(max(0, missing)):
            l, f, g = next_pupil()
            students |= get_student(year, classroom, code, l, f, g)
        return students

    # ------------------------------------------------------------------
    # Dates / examens / résultats
    # ------------------------------------------------------------------
    def at(year, period, frac):
        end = min(period.date_end, DATE_CAP.get(year.code, period.date_end))
        length = (end - period.date_start).days
        d = period.date_start + timedelta(days=int(length * frac))
        while d.weekday() >= 5:
            d += timedelta(days=1)
        return min(d, end)

    def get_exam(year, period, classroom, code, name, kind, exam_type, d, subject_ids,
                 tkey, composition_number=0):
        exam = Exam.search([('code', '=', code), ('academic_year_id', '=', year.id)], limit=1)
        if not exam:
            exam = create_as(Exam, {
                'name': name, 'code': code, 'exam_type': exam_type,
                'evaluation_kind': kind, 'composition_number': composition_number,
                'academic_year_id': year.id, 'period_id': period.id,
                'date_start': d, 'date_end': d,
                'level_ids': [(6, 0, [classroom.level_id.id])],
                'classroom_ids': [(6, 0, [classroom.id])],
                'subject_ids': [(6, 0, subject_ids)],
                'total_marks': 20.0, 'passing_marks': 10.0,
                'state': 'completed',
            }, tkey)
        return exam

    def put_results(exam, rows, tkey):
        """rows : [(student, subject, note)] ; ignore ce qui existe déjà."""
        existing = {(r.student_id.id, r.subject_id.id) for r in exam.sudo().result_ids}
        teacher = get_teacher(tkey)
        vals = [{
            'exam_id': exam.id, 'student_id': st.id, 'subject_id': su.id,
            'marks_obtained': mark, 'teacher_id': teacher.id, 'state': 'confirmed',
        } for st, su, mark in rows if (st.id, su.id) not in existing]
        if vals:
            create_as(ExamResult, vals, tkey)
        return len(vals)

    def seed_college(year, classroom, code, students, targets):
        """Par matière et par trimestre : Devoir 1, Devoir 2 (si 2 notes) et
        Composition, créés par l'enseignant de la matière."""
        periods = {p.code: p for p in year.period_ids}
        marks = {st.id: build_college_marks(year.code, st.last_name, st.first_name,
                                            targets[st.id]) for st in students}
        for pcode in FILLED_PERIODS[year.code]:
            period = periods[pcode]
            for xid, tkey in subject_pairs(code):
                subject = ref(xid)
                rows = {'DEV1': [], 'DEV2': [], 'COMP': []}
                for st in students:
                    devs, comp = marks[st.id][pcode][xid]
                    rows['DEV1'].append((st, subject, devs[0]))
                    if len(devs) > 1:
                        rows['DEV2'].append((st, subject, devs[1]))
                    rows['COMP'].append((st, subject, comp))
                for suffix, kind, etype, frac, title in (
                        ('DEV1', 'devoir', 'monthly', 0.30, 'Devoir n°1'),
                        ('DEV2', 'devoir', 'monthly', 0.55, 'Devoir n°2'),
                        ('COMP', 'composition', 'quarterly', 0.85, 'Composition')):
                    if not rows[suffix]:
                        continue
                    exam = get_exam(
                        year, period, classroom,
                        '%s-%s-%s-%s' % (classroom.code, pcode, subject.code, suffix),
                        '%s - %s - %s - %s' % (title, subject.name, period.name, classroom.name),
                        kind, etype, at(year, period, frac), [subject.id], tkey)
                    put_results(exam, rows[suffix], tkey)

    def seed_monthly(year, classroom, code, students, targets):
        """Compositions mensuelles (1-3 : T1, 4-6 : T2, 7-9 : T3), créées par
        le titulaire ; une note par discipline du livret."""
        periods = list(year.period_ids.sorted('sequence'))
        pairs = subject_pairs(code)
        subj = [ref(x) for x, _t in pairs]
        tkey = MAIN_TEACHER[code]
        kind_key = 'prim' if kind_of(code) == 'primary' else 'pre'
        notes = {st.id: build_monthly_marks(kind_key, year.code, st.last_name, st.first_name,
                                            targets[st.id], len(pairs)) for st in students}
        for n in FILLED_MONTHS[year.code]:
            period = periods[(n - 1) // 3]
            j = (n - 1) % 3
            exam = get_exam(
                year, period, classroom, '%s-C%02d' % (classroom.code, n),
                'Composition n°%d - %s' % (n, classroom.name), 'composition', 'monthly',
                at(year, period, (j + 0.6) / 3.0), [s.id for s in subj], tkey,
                composition_number=n)
            rows = [(st, subj[i], notes[st.id][n][i]) for st in students
                    for i in range(len(pairs))]
            put_results(exam, rows, tkey)

    # ------------------------------------------------------------------
    # Discipline
    # ------------------------------------------------------------------
    def seed_discipline(year, students):
        periods = {p.code: p for p in year.period_ids}
        sanc = SANCTIONS.get(year.code, [])
        pcodes = FILLED_PERIODS[year.code]
        for st in students:
            if (Absence.search_count([('student_id', '=', st.id)])
                    or Late.search_count([('student_id', '=', st.id)])
                    or Sanction.search_count([('student_id', '=', st.id)])):
                continue
            for pcode in pcodes:
                period = periods[pcode]
                rng = random.Random('disc|%s|%s|%s|%s' % (
                    year.code, st.last_name, st.first_name, pcode))
                n_abs = rng.choice([0, 0, 1, 1, 2, 3])
                n_late = rng.choice([0, 0, 1, 2])
                if (year.code, st.last_name, st.first_name, pcode) == (
                        '2024-2025', 'AKAKPO', 'Mariama', 'T1'):
                    n_abs, n_late = 2, 1
                for i in range(n_abs):
                    Absence.create({
                        'student_id': st.id, 'date': at(year, period, rng.uniform(0.05, 0.9)),
                        'absence_type': rng.choice(['day', 'half_day', 'course']),
                        'justified': i % 2 == 0,
                        'motif': rng.choice(['Maladie', 'Raison familiale', 'Non justifiée']),
                    })
                for _i in range(n_late):
                    Late.create({
                        'student_id': st.id, 'date': at(year, period, rng.uniform(0.05, 0.9)),
                        'minutes': rng.choice([5, 10, 15, 20]),
                        'justified': False, 'motif': 'Transport',
                    })
            for last, first, pcode, frac, type_xid, reason in sanc:
                if pcode in pcodes and (last, norm_first(first)) == (st.last_name, st.first_name):
                    Sanction.create({
                        'student_id': st.id, 'type_id': ref(type_xid).id,
                        'date': at(year, periods[pcode], frac),
                        'reason': reason, 'state': 'executed',
                    })
            for pcode in pcodes:  # note de conduite (20/20 sans incident)
                Conduct.recompute_for(st, periods[pcode])

    # ------------------------------------------------------------------
    # Résultats : calcul, appréciations, validation, passage
    # ------------------------------------------------------------------
    def teacher_appr(avg):
        if avg < 7:
            return "Résultats très insuffisants. Un travail sérieux et régulier s'impose."
        if avg < 9:
            return "Travail insuffisant. Des efforts importants sont nécessaires."
        if avg < 10:
            return "Résultats fragiles. Peut mieux faire avec plus de régularité."
        if avg < 12:
            return "Résultats passables. Continuez vos efforts."
        if avg < 14:
            return "Bon travail dans l'ensemble. Continuez ainsi."
        if avg < 16:
            return "Très bon trimestre. Félicitations."
        return "Excellent travail. Félicitations."

    def director_appr(avg):
        if avg < 9:
            return "Avertissement de travail."
        if avg < 10:
            return "Doit se ressaisir."
        if avg < 12:
            return "Peut mieux faire."
        if avg < 14:
            return "Encouragements."
        if avg < 16:
            return "Tableau d'honneur."
        return "Tableau d'honneur avec félicitations."

    def compute_year(year):
        pcodes = FILLED_PERIODS[year.code]
        for period in year.period_ids.sorted('sequence'):
            if period.code in pcodes:
                PeriodResult.compute_for_period(period.id)
        # Appréciations de l'enseignant principal et de la direction
        for res in PeriodResult.search([('academic_year_id', '=', year.id),
                                        ('state', '=', 'draft')]):
            if not res.has_average:
                continue
            vals = {}
            if not res.appreciation_teacher:
                vals['appreciation_teacher'] = teacher_appr(res.average)
            if not res.appreciation_director:
                vals['appreciation_director'] = director_appr(res.average)
            if vals:
                res.write(vals)
            if res.degree == 'middle':
                for line in res.line_ids:
                    if not line.appreciation:
                        line.appreciation = teacher_appr(line.average).split('.')[0]
        if len(pcodes) == 3:
            Annual.compute_for_year(year.id)

    def validate_year(year):
        PeriodResult.search([('academic_year_id', '=', year.id),
                             ('state', '=', 'draft')]).action_validate()
        year.period_ids.action_close()

    def print_decisions(year):
        print('Décisions annuelles %s :' % year.name)
        for ar in Annual.search([('academic_year_id', '=', year.id)],
                                order='classroom_id, rank, student_id'):
            print('  %-6s %-24s moy. %5.2f rang %s/%s -> %s' % (
                ar.classroom_id.code, ar.student_id.name, ar.annual_average, ar.rank,
                ar.effectif, ar.decision_label or ar.final_decision))

    def promote(year_from, year_to):
        todo = Annual.search([
            ('academic_year_id', '=', year_from.id), ('promotion_state', '=', 'todo'),
            ('final_decision', 'not in', ('pending', False)),
        ]).mapped('student_id').filtered(lambda s: s.state == 'enrolled')
        if not todo:
            print('Passage %s -> %s : déjà traité.' % (year_from.name, year_to.name))
            return
        wizard = Wizard.create({
            'current_academic_year_id': year_from.id,
            'new_academic_year_id': year_to.id,
            'current_classroom_ids': [(6, 0, todo.mapped('classroom_id').ids)],
            'promotion_type': 'decision',
            'include_indulgence': True,
            'student_ids': [(6, 0, todo.ids)],
            'promotion_date': year_to.date_start,
        })
        wizard.action_preview()
        if wizard.skipped_info:
            print('Passage - ignorés :\n%s' % wizard.skipped_info)
        wizard.action_promote()
        lines = wizard.line_ids
        errors = lines.filtered(lambda l: l.state == 'error')
        print('Passage %s -> %s : %d lignes (%d admis/indulgence, %d redoublants), '
              '%d terminées, %d en erreur' % (
                  year_from.name, year_to.name, len(lines),
                  len(lines.filtered(lambda l: l.outcome == 'promote')),
                  len(lines.filtered(lambda l: l.outcome == 'repeat')),
                  len(lines.filtered(lambda l: l.state == 'done')), len(errors)))
        for line in errors:
            print('  ERREUR %s : %s' % (line.student_id.name, line.error_message))

    def run_year(year, classrooms):
        """Notes, discipline et résultats d'une année (élèves déjà inscrits)."""
        for code in LEVELS_BY_YEAR[year.code]:
            classroom = classrooms[(year.code, code)]
            students = ensure_roster(year, classroom, code)
            targets = {}
            for st in students:
                repeated = bool(st.previous_student_id
                                and st.previous_student_id.state == 'repeated')
                targets[st.id] = targets_for(year.code, code, st.last_name, st.first_name,
                                             repeated)
            if kind_of(code) == 'college':
                seed_college(year, classroom, code, students, targets)
            else:
                seed_monthly(year, classroom, code, students, targets)
            seed_discipline(year, students)
        compute_year(year)

    # ==================================================================
    # 4. EXÉCUTION
    # ==================================================================
    # Enseignants d'abord (comptes + fiches)
    for key in TEACHERS:
        get_teacher(key)

    # Années : chacune créée après les classes de la précédente (copie à la création)
    classrooms = {}
    years = {}
    for yname in YEAR_ORDER:
        year = get_year(yname)
        years[yname] = year
        if yname == YEAR_ORDER[0] and year.state == 'draft':
            year.action_activate()
        for code in LEVELS_BY_YEAR[yname]:
            classrooms[(yname, code)] = get_classroom(year, code)
            setup_assignments(classrooms[(yname, code)], code)
    y24, y25, y26 = (years[n] for n in YEAR_ORDER)

    # --- 2024-2025 : données, résultats, validation, décisions, passage
    run_year(y24, classrooms)
    validate_year(y24)
    print_decisions(y24)
    promote(y24, y25)
    if y24.state != 'closed':
        y24.action_close()
    if not y25.is_current and y25.state != 'closed':
        y25.action_activate()

    # --- 2025-2026 : idem
    run_year(y25, classrooms)
    validate_year(y25)
    print_decisions(y25)
    promote(y25, y26)
    if y25.state != 'closed':
        y25.action_close()

    # --- 2026-2027 : année courante, 1er trimestre uniquement
    if not y26.is_current:
        y26.action_activate()
    run_year(y26, classrooms)

    # ==================================================================
    # 5. CONTRÔLES
    # ==================================================================
    print('=' * 70)
    for year in (y24, y25, y26):
        print('%s (état %s%s) : %d classes, %d élèves, %d examens, %d notes, '
              '%d résultats de période, %d résultats annuels' % (
                  year.name, year.state, ', courante' if year.is_current else '',
                  Classroom.search_count([('academic_year_id', '=', year.id)]),
                  Student.search_count([('academic_year_id', '=', year.id)]),
                  Exam.search_count([('academic_year_id', '=', year.id)]),
                  ExamResult.search_count([('academic_year_id', '=', year.id)]),
                  PeriodResult.search_count([('academic_year_id', '=', year.id)]),
                  Annual.search_count([('academic_year_id', '=', year.id)])))
    print('Total : %d fiches élèves, %d enseignants, %d absences, %d retards, '
          '%d sanctions, %d notes de conduite' % (
              Student.search_count([]), Teacher.search_count([]), Absence.search_count([]),
              Late.search_count([]), Sanction.search_count([]), Conduct.search_count([])))
    t1 = y24.period_ids.filtered(lambda p: p.code == 'T1')
    mar = Student.search([('last_name', '=', 'AKAKPO'), ('first_name', '=', 'Mariama'),
                          ('academic_year_id', '=', y24.id)], limit=1)
    res = PeriodResult.search([('student_id', '=', mar.id), ('period_id', '=', t1.id)], limit=1)
    print('Mariama AKAKPO T1 2024-2025 : moyenne %.2f, rang %s/%s, plus forte %.2f, '
          'plus faible %.2f, moyenne classe %.2f, état %s' % (
              res.average, res.rank, res.effectif, res.class_max, res.class_min,
              res.class_average, res.state))
    for line in res.line_ids:
        print('    %-40s devoirs %5.2f  compo %5.2f  moy %5.2f' % (
            line.subject_id.name, line.homework_average, line.composition_average, line.average))
    print('Comptes enseignants (mot de passe demo1234) :')
    for key in TEACHERS:
        print('  %-28s %s' % (TEACHERS[key][0], teacher_users[key].login))
    if denied:
        print('Repli sudo utilisé (accès enseignant refusé) pour : %s' % ', '.join(sorted(denied)))

    env.cr.commit()
    print('Jeu de données validé (commit).')


if 'env' in globals():
    _seed_main(env, SEED_AS_TEACHER)  # noqa: F821 - `env` fourni par `odoo shell`
elif __name__ == '__main__':
    _seed_main(None, SEED_AS_TEACHER)
