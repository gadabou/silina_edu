# -*- coding: utf-8 -*-
"""Bulletins (collège/lycée) et livrets (crèche/préscolaire/primaire).

Choix d'architecture
--------------------
* Les actions de rapport portent sur ``silina.student`` : un bulletin/livret est
  un document « élève », et la période/mode annuel sont des *paramètres* du
  rapport (et non l'objet imprimé). Un rapport sur ``silina.period.result``
  n'aurait pas permis la version annuelle (toutes périodes en colonnes).
* Les paramètres (période, annuel, options) sont transmis via le ``data`` du
  rapport. Les AbstractModel ``report.silina_edu.report_*_document`` préparent
  toutes les données (chaînes déjà formatées) pour garder les gabarits QWeb
  simples.
* ``silina.report.card.mixin.get_report_card_action`` est la méthode de dispatch
  (bulletin vs livret d'après ``degree``).
"""
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError

from odoo.addons.silina_edu.models import result_utils as ru

# Niveaux de compétence : (seuil minimal sur 20, libellé, classe CSS).
# Le seuil s'applique à la moyenne ramenée sur 20 (barème société pris en compte).
COMPETENCY_LEVELS = [
    (16.0, 'Acquis dépassé', 'sl-lvl-4'),
    (12.0, 'Acquis', 'sl-lvl-3'),
    (8.0, "En cours d'acquisition", 'sl-lvl-2'),
    (0.0, 'Non acquis', 'sl-lvl-1'),
]
NOT_EVALUATED = 'Non évalué'

BULLETIN_DEGREES = ('middle', 'high')
LIVRET_DEGREES = ('daycare', 'preschool', 'primary')

# --- Livret (modèle papier « NEUVIÈME ANNÉE / COMPOSITIONS ») ----------------
# Libellé d'ordinal affiché en titre, par code de niveau (en majuscules).
# Niveaux absents (crèche, préscolaire...) : nom du niveau en majuscules.
LIVRET_LEVEL_TITLES = {
    'CP1': 'PREMIÈRE ANNÉE',
    'CP2': 'DEUXIÈME ANNÉE',
    'CE1': 'TROISIÈME ANNÉE',
    'CE2': 'QUATRIÈME ANNÉE',
    'CM1': 'CINQUIÈME ANNÉE',
    'CM2': 'SIXIÈME ANNÉE',
}
# Nombre minimal de colonnes « mois » du livret (9 mois de composition).
LIVRET_MONTHS = 9
# Libellés courts (mode « competency ») pour les cellules étroites de la grille.
LIVRET_LEVEL_SHORT = {
    'Acquis dépassé': 'AD',
    'Acquis': 'A',
    "En cours d'acquisition": 'ECA',
    'Non acquis': 'NA',
}
# Rang trimestre -> code de période attendu (repli : ordre des périodes).
LIVRET_TERM_CODES = ('T1', 'T2', 'T3')

REPORT_REFS = {
    'bulletin': 'silina_edu.action_report_bulletin',
    'livret': 'silina_edu.action_report_livret',
    'bulletin_stub': 'silina_edu.action_report_bulletin_souche',
}

DECISION_LABELS = {
    'passed': 'Admis(e) en classe supérieure',
    'indulgence': 'Admis(e) par indulgence',
    'repeat': 'Redouble',
}


def _fmt(value, digits=2):
    """Nombre formaté à la française ('12,50'), '—' si absent."""
    if value is None or value is False:
        return '—'
    return ('%.*f' % (digits, value)).replace('.', ',')


def _fmt_g(value):
    """Nombre sans zéros inutiles (absences en jours/heures)."""
    if value is None or value is False:
        return '—'
    return ('%g' % value).replace('.', ',')


def _rank(rank, effectif):
    if not rank:
        return ''
    return '%d / %d' % (rank, effectif) if effectif else str(rank)


def competency_level(average, max_mark=20.0):
    """Retourne (libellé, classe CSS) pour une moyenne, ou Non évalué."""
    if average is None:
        return NOT_EVALUATED, 'sl-lvl-0'
    on20 = average * 20.0 / (max_mark or 20.0)
    for threshold, label, css in COMPETENCY_LEVELS:
        if on20 >= threshold:
            return label, css
    return COMPETENCY_LEVELS[-1][1], COMPETENCY_LEVELS[-1][2]


# ----------------------------------------------------------------------
# Préparation des données (partagée bulletin / livret)
# ----------------------------------------------------------------------
class ReportCardMixin(models.AbstractModel):
    _name = 'silina.report.card.mixin'
    _description = 'Données communes bulletin / livret'

    # --- dispatch --------------------------------------------------------
    @api.model
    def get_report_card_action(self, student_ids, period_id=False, annual=False,
                               kind=None, include_rank=True, include_statistics=True,
                               include_comments=True, stub=False, include_annual=True):
        """Retourne l'action de rapport adaptée au degré des élèves.

        :param kind: 'bulletin' / 'livret' pour restreindre un lot mixte ;
                     sinon le lot doit être homogène (UserError sinon).
        """
        students = self.env['silina.student'].browse(student_ids).exists()
        groups = {'bulletin': students.browse(), 'livret': students.browse()}
        for student in students:
            groups[self._kind_for_degree(student.degree)] |= student
        if kind:
            selected = kind
        else:
            non_empty = [k for k, v in groups.items() if v]
            if len(non_empty) > 1:
                raise UserError(_(
                    "La sélection mélange des élèves de collège/lycée (%(b)s) et de "
                    "crèche/préscolaire/primaire (%(l)s). Imprimez-les séparément.",
                    b=len(groups['bulletin']), l=len(groups['livret'])))
            selected = non_empty[0] if non_empty else 'bulletin'
        target = groups[selected]
        if not target:
            raise UserError(_("Aucun élève à imprimer pour ce type de document."))
        data = {
            'student_ids': target.ids,
            'period_id': period_id or False,
            'annual': bool(annual),
            'include_rank': bool(include_rank),
            'include_statistics': bool(include_statistics),
            'include_comments': bool(include_comments),
            'include_annual': bool(include_annual),
        }
        ref = REPORT_REFS['bulletin_stub'] if (selected == 'bulletin' and stub) else REPORT_REFS[selected]
        # Les bulletins/livrets ont leur propre en-tête (réglages SILINA) : on évite
        # l'assistant « Configurer l'agencement de votre document » d'Odoo, qui
        # s'ouvre pour l'administrateur tant que la société n'a pas de mise en page.
        return self.env.ref(ref).with_context(discard_logo_check=True).report_action(
            target.ids, data=data)

    @api.model
    def _kind_for_degree(self, degree):
        return 'livret' if degree in LIVRET_DEGREES else 'bulletin'

    # --- valeurs du rapport ----------------------------------------------
    @api.model
    def _get_card_values(self, docids, data, template_kind):
        data = data or {}
        ctx = self.env.context

        def opt(key, default):
            value = data.get(key)
            if value is None:
                value = ctx.get(key)
            return default if value is None else value

        student_ids = docids or data.get('student_ids') or []
        students = self.env['silina.student'].browse(student_ids).exists()
        period_id = opt('period_id', False)
        opts = {
            'template_kind': template_kind,
            'period': self.env['silina.period'].browse(int(period_id)) if period_id else False,
            'annual': bool(opt('annual', False)),
            'include_rank': bool(opt('include_rank', True)),
            'include_statistics': bool(opt('include_statistics', True)),
            'include_comments': bool(opt('include_comments', True)),
            'include_annual': bool(opt('include_annual', True)),
            'settings': self.env.company.get_silina_settings(),
            'cache': {},
        }
        cards = [self._build_card(student, dict(opts)) for student in students]
        return {
            'doc_ids': students.ids,
            'doc_model': 'silina.student',
            'docs': students,
            'cards': cards,
            'company': self.env.company,
            'data': data,
        }

    @api.model
    def _build_card(self, student, opts):
        env = self.env
        settings = opts['settings']
        max_mark = settings.get('max_mark') or 20.0
        template_kind = opts['template_kind']
        period = opts['period']
        annual = opts['annual']
        PR = env['silina.period.result']

        year = period.academic_year_id if period else student.academic_year_id
        all_periods = env['silina.period'].search(
            [('academic_year_id', '=', year.id)], order='sequence, date_start, id')

        if not period and not annual:
            # Aucun paramètre : dernière période ayant une moyenne, sinon annuel.
            done = PR.search([('student_id', '=', student.id),
                              ('academic_year_id', '=', year.id),
                              ('has_average', '=', True)]).mapped('period_id')
            candidates = all_periods.filtered(lambda p: p in done)
            if candidates:
                period = candidates[-1]
            else:
                annual = True

        if annual or not period:
            shown = all_periods
        elif template_kind == 'bulletin':
            shown = period
        else:  # livret : colonnes depuis la première période jusqu'à la période choisie
            ids = all_periods.ids
            shown = all_periods[:ids.index(period.id) + 1] if period.id in ids else period
        multi = len(shown) > 1 or annual

        res_by_p = {r.period_id.id: r for r in PR.search(
            [('student_id', '=', student.id), ('period_id', 'in', shown.ids)])}
        last_res = None
        for p in shown:
            if p.id in res_by_p:
                last_res = res_by_p[p.id]
        classroom = (last_res.classroom_id if last_res else student.classroom_id)
        degree = classroom.degree or student.degree
        is_livret_degree = degree in LIVRET_DEGREES

        mode = settings['livret_mode'].get(degree, 'numeric') if (
            template_kind == 'livret' and is_livret_degree) else 'numeric'
        if template_kind == 'livret':
            show_rank = degree == 'primary' or bool(settings['show_rank'].get(degree))
        else:
            show_rank = opts['include_rank']

        # Moyennes de classe par matière/période.
        cache = opts['cache']
        key = (classroom.id, tuple(shown.ids))
        if key not in cache:
            acc = {}
            for line in env['silina.period.result.line'].search(
                    [('classroom_id', '=', classroom.id), ('period_id', 'in', shown.ids)]):
                acc.setdefault((line.period_id.id, line.subject_id.id), []).append(line.average)
            cache[key] = {k: sum(v) / len(v) for k, v in acc.items()}
        class_avgs = cache[key]

        # Matières
        subjects = {}
        for p in shown:
            res = res_by_p.get(p.id)
            if not res:
                continue
            for line in res.line_ids:
                entry = subjects.setdefault(line.subject_id.id, {'subject': line.subject_id, 'lines': {}})
                entry['lines'][p.id] = line
        rows = []
        total_points = total_coef = 0.0
        for entry in sorted(subjects.values(), key=lambda e: (e['subject'].sequence, e['subject'].id)):
            cells = []
            avgs = []
            coef = 0.0
            appreciation = ''
            for p in shown:
                line = entry['lines'].get(p.id)
                if line:
                    avgs.append(line.average)
                    coef = line.coefficient
                    appreciation = line.appreciation or line.mention or appreciation
                    label, css = competency_level(line.average, max_mark)
                    cells.append({
                        'has': True, 'avg': _fmt(line.average),
                        'weighted': _fmt(line.weighted_average),
                        'rank': _rank(line.rank, line.effectif),
                        'class_avg': _fmt(class_avgs.get((p.id, entry['subject'].id))),
                        'level': label, 'css': css,
                    })
                else:
                    cells.append({'has': False, 'avg': '—', 'weighted': '—', 'rank': '',
                                  'class_avg': '—', 'level': NOT_EVALUATED, 'css': 'sl-lvl-0'})
            year_avg = sum(avgs) / len(avgs) if avgs else None
            if year_avg is not None:
                total_points += year_avg * coef
                total_coef += coef
            label, css = competency_level(year_avg, max_mark)
            rows.append({
                'name': entry['subject'].name,
                'coef': _fmt_g(coef),
                'cells': cells,
                'annual_avg': _fmt(year_avg),
                'annual_weighted': _fmt(year_avg * coef) if year_avg is not None else '—',
                'annual_level': label,
                'annual_css': css,
                'appreciation': appreciation,
            })

        # Totaux par période
        period_cells = []
        for p in shown:
            res = res_by_p.get(p.id)
            has = bool(res and res.has_average)
            label, css = competency_level(res.average if has else None, max_mark)
            period_cells.append({
                'name': p.name, 'code': p.code or p.name,
                'avg': _fmt(res.average) if has else '—',
                'rank': _rank(res.rank, res.effectif) if has else '',
                'mention': res.mention if has else '',
                'class_avg': _fmt(res.class_average) if has else '—',
                'class_max': _fmt(res.class_max) if has else '—',
                'class_min': _fmt(res.class_min) if has else '—',
                'level': label, 'css': css,
            })

        # Synthèse générale (période unique ou annuelle)
        annual_rec = env['silina.annual.result']
        if annual:
            annual_rec = env['silina.annual.result'].search(
                [('student_id', '=', student.id), ('academic_year_id', '=', year.id)], limit=1)
        if annual and annual_rec and annual_rec.has_average:
            avg = annual_rec.annual_average
            summary = {
                'average': _fmt(avg), 'rank': _rank(annual_rec.rank, annual_rec.effectif),
                'mention': annual_rec.mention or '',
                'class_avg': _fmt(annual_rec.class_average),
                'class_max': _fmt(annual_rec.class_max),
                'class_min': _fmt(annual_rec.class_min),
            }
        elif multi:
            avgs = [res_by_p[p.id].average for p in shown
                    if p.id in res_by_p and res_by_p[p.id].has_average]
            avg = sum(avgs) / len(avgs) if avgs else None
            summary = {'average': _fmt(avg), 'rank': '',
                       'mention': env.company.mention_for(avg) if avg is not None else '',
                       'class_avg': '—', 'class_max': '—', 'class_min': '—'}
        else:
            c = period_cells[0] if period_cells else {}
            avg = (last_res.average if last_res and last_res.has_average else None)
            summary = {'average': c.get('avg', '—'), 'rank': c.get('rank', ''),
                       'mention': c.get('mention', ''), 'class_avg': c.get('class_avg', '—'),
                       'class_max': c.get('class_max', '—'), 'class_min': c.get('class_min', '—')}
        label, css = competency_level(avg, max_mark)
        summary.update({
            'level': label, 'css': css,
            'total_points': _fmt(total_points) if total_coef else '—',
            'total_coef': _fmt_g(total_coef) if total_coef else '—',
        })

        # Discipline
        def per_period(getter, formatter):
            return [formatter(getter(res_by_p[p.id])) if p.id in res_by_p else '—' for p in shown]

        present = [res_by_p[p.id] for p in shown if p.id in res_by_p]
        scores = [r.conduct_score for r in present if r.conduct_score]
        discipline = [
            {'label': 'Absences', 'values': per_period(lambda r: r.absences, _fmt_g),
             'total': _fmt_g(sum(r.absences for r in present)) if present else '—'},
            {'label': 'dont non justifiées',
             'values': per_period(lambda r: r.absences_unjustified, _fmt_g),
             'total': _fmt_g(sum(r.absences_unjustified for r in present)) if present else '—'},
            {'label': 'Retards', 'values': per_period(lambda r: r.lates, _fmt_g),
             'total': _fmt_g(sum(r.lates for r in present)) if present else '—'},
            {'label': 'Conduite (/20)',
             'values': per_period(lambda r: r.conduct_score if r.conduct_score else None, _fmt),
             'total': _fmt(sum(scores) / len(scores)) if scores else '—'},
        ]
        conduct_appreciation = ''
        for r in present:
            conduct_appreciation = r.conduct_appreciation or conduct_appreciation

        teacher = director = ''
        for r in present:
            teacher = r.appreciation_teacher or teacher
            director = r.appreciation_director or director

        # Décision de fin d'année (A4, défensif)
        decision = ''
        if annual and annual_rec and 'final_decision' in annual_rec._fields:
            final = annual_rec.final_decision
            if final and final != 'pending':
                label_field = annual_rec.decision_label if 'decision_label' in annual_rec._fields else ''
                decision = label_field or DECISION_LABELS.get(final, str(final))

        if multi:
            title = _('BULLETIN ANNUEL') if template_kind == 'bulletin' else _('LIVRET SCOLAIRE')
            subtitle = year.name
            if not annual and period:
                subtitle = '%s - %s' % (period.name, year.name)
        else:
            title = _('BULLETIN DE NOTES') if template_kind == 'bulletin' else _('LIVRET SCOLAIRE')
            subtitle = '%s - %s' % (shown.name, year.name) if shown else year.name

        return {
            'student': student,
            'classroom': classroom,
            'year': year,
            'degree': degree,
            'title': title,
            'subtitle': subtitle,
            'dob': fields.Date.to_string(student.date_of_birth) if student.date_of_birth else '',
            'periods': period_cells,
            'multi': multi,
            'annual': annual,
            'rows': rows,
            'summary': summary,
            'discipline': discipline,
            'conduct_appreciation': conduct_appreciation,
            'teacher': teacher,
            'director': director,
            'decision': decision,
            'mode': mode,
            'show_rank': show_rank,
            'show_stats': opts['include_statistics'],
            'show_comments': opts['include_comments'],
            'max_mark': _fmt_g(max_mark),
            'has_data': bool(rows),
            'levels': [(label, css) for _t, label, css in COMPETENCY_LEVELS],
        }


class ReportBulletin(models.AbstractModel):
    _name = 'report.silina_edu.report_bulletin_document'
    _inherit = 'silina.report.card.mixin'
    _description = 'Rapport bulletin collège/lycée'

    @api.model
    def _get_report_values(self, docids, data=None):
        return self._get_card_values(docids, data, 'bulletin')

    # --- préparation des données propre au bulletin ------------------------
    @staticmethod
    def _bl_num(value, digits=2):
        """Nombre français '8,75' ; chaîne vide si absent."""
        if value is None or value is False:
            return ''
        return ('%.*f' % (digits, value)).replace('.', ',')

    @staticmethod
    def _bl_coef(value):
        if value is None or value is False:
            return ''
        return ('%g' % value).replace('.', ',')

    @staticmethod
    def _bl_rank(rank):
        """Rang ordinal français : 1er, 4e (vide si non classé)."""
        if not rank:
            return ''
        return '%der' % rank if rank == 1 else '%de' % rank

    @api.model
    def _bl_period_labels(self, period, all_periods):
        """(titre en majuscules 'BULLETIN DU 1ER TRIMESTRE', libellé 'Résultat du 1er Trimestre')."""
        ids = all_periods.ids
        index = ids.index(period.id) + 1 if period.id in ids else (period.sequence or 1)
        name_l = (period.name or '').lower()
        code_u = (period.code or '').upper()
        if 'semestre' in name_l or code_u.startswith('S'):
            kind = 'Semestre'
        elif 'trimestre' in name_l or code_u.startswith('T'):
            kind = 'Trimestre'
        else:
            kind = ''
        if not kind:
            name = period.name or ''
            return 'BULLETIN - %s' % name.upper(), 'Résultat - %s' % name
        ordinal = '1er' if index == 1 else '%de' % index
        return ('BULLETIN DU %s %s' % (ordinal.upper(), kind.upper()),
                'Résultat du %s %s' % (ordinal, kind))

    @api.model
    def _bl_period_short(self, period, all_periods):
        """'1er Semestre' (libellé court d'une période, sans « Résultat du »)."""
        label = self._bl_period_labels(period, all_periods)[1]
        for prefix in ('Résultat du ', 'Résultat - '):
            if label.startswith(prefix):
                return label[len(prefix):]
        return label

    @api.model
    def _build_card(self, student, opts):
        env = self.env
        bn = self._bl_num
        company = env.company
        settings = opts['settings']
        max_mark = settings.get('max_mark') or 20.0
        pass_mark = settings.get('pass_average') or 10.0
        PR = env['silina.period.result']
        period = opts['period']
        annual = opts['annual']

        year = period.academic_year_id if period else student.academic_year_id
        all_periods = env['silina.period'].search(
            [('academic_year_id', '=', year.id)], order='sequence, date_start, id')
        if not period and not annual:
            done = PR.search([('student_id', '=', student.id),
                              ('academic_year_id', '=', year.id),
                              ('has_average', '=', True)]).mapped('period_id')
            candidates = all_periods.filtered(lambda p: p in done)
            if candidates:
                period = candidates[-1]
            else:
                annual = True
        shown = all_periods if (annual or not period) else period
        multi = bool(annual or len(shown) > 1)

        res_by_p = {r.period_id.id: r for r in PR.search(
            [('student_id', '=', student.id), ('period_id', 'in', shown.ids)])}
        last_res = False
        for p in shown:
            if p.id in res_by_p:
                last_res = res_by_p[p.id]
        classroom = last_res.classroom_id if last_res else student.classroom_id

        # --- matières par groupe ---------------------------------------
        subjects = {}
        for p in shown:
            res = res_by_p.get(p.id)
            if not res:
                continue
            for line in res.line_ids:
                entry = subjects.setdefault(line.subject_id.id, {'subject': line.subject_id, 'lines': {}})
                entry['lines'][p.id] = line
        entries = list(subjects.values())
        if subjects and classroom:
            # Matières de la classe sans aucune note confirmée pour cet élève :
            # affichées « **** » (jamais 0), hors totaux et moyennes.
            for a in classroom.subject_assignment_ids:
                if a.subject_id.id not in subjects:
                    entries.append({'subject': a.subject_id, 'lines': {}, 'assignment': a})
        groups_map = {}
        number = 0
        for entry in sorted(entries, key=lambda e: (e['subject'].sequence, e['subject'].id)):
            subj = entry['subject']
            code = subj.report_group or 'C'
            lines = [entry['lines'][p.id] for p in shown if p.id in entry['lines']]
            last = lines[-1] if lines else False
            if not last:
                a = entry.get('assignment')
                if not a:
                    continue
                number += 1
                groups_map.setdefault(code, []).append({
                    'n': number, 'name': subj.name,
                    'hw': '****', 'comp': '****',
                    'avg': '****', 'low': False,
                    'coef': '--', 'weighted': '****',
                    'rank': '', 'appr': '',
                    'teacher': a.teacher_name or '',
                    'cells': ['****'] * len(shown),
                    '_avg': None, '_coef': 0.0, '_w': 0.0,
                })
                continue
            number += 1
            cells = [bn(entry['lines'][p.id].average) if p.id in entry['lines'] else '' for p in shown]
            if multi:
                avgs = [ln.average for ln in lines if ln.average is not None]
                avg = sum(avgs) / len(avgs) if avgs else None
                coef = last.coefficient
                weighted = avg * coef if avg is not None else None
                hw = comp = ''
                rank = ''
                appr = company.appreciation_for(avg) if avg is not None else ''
            else:
                avg = last.average
                coef = last.coefficient
                weighted = last.weighted_average
                hw = bn(last.homework_average) if last.has_homework else ''
                comp = bn(last.composition_average) if last.has_composition else ''
                rank = self._bl_rank(last.rank) if opts['include_rank'] else ''
                appr = last.appreciation_scale or last.appreciation or last.mention or ''
            groups_map.setdefault(code, []).append({
                'n': number,
                'name': subj.name,
                'hw': hw, 'comp': comp,
                'avg': bn(avg), 'low': avg is not None and avg < pass_mark,
                'coef': self._bl_coef(coef),
                'weighted': bn(weighted),
                'rank': rank, 'appr': appr,
                'teacher': last.teacher_name or '',
                'cells': cells,
                '_avg': avg, '_coef': coef, '_w': weighted,
            })

        group_res = {}
        if not multi and last_res:
            group_res = {g.group: g for g in last_res.get_group_results()}
        groups = []
        tot_coef = tot_points = 0.0
        for code in sorted(groups_map):
            rows = groups_map[code]
            g_coef = sum(r['_coef'] or 0.0 for r in rows if r['_avg'] is not None)
            g_points = sum(r['_w'] or 0.0 for r in rows if r['_avg'] is not None)
            g_avg = g_points / g_coef if g_coef else None
            g_rank = ''
            g_appr = company.appreciation_for(g_avg) if g_avg is not None else ''
            rec = group_res.get(code)
            if rec:
                g_coef, g_points = rec.total_coef, rec.total_points
                g_avg = rec.average if rec.has_average else None
                g_rank = self._bl_rank(rec.rank) if (opts['include_rank'] and rec.has_average) else ''
                g_appr = (rec.appreciation or (company.appreciation_for(g_avg) if g_avg is not None else ''))
            tot_coef += g_coef
            tot_points += g_points
            rated = any(r['_avg'] is not None for r in rows)
            groups.append({
                'code': code,
                'label': company.group_label(code),
                'rows': rows,
                'total_coef': self._bl_coef(g_coef) if rated else '',
                'total_points': bn(g_points) if rated else '',
                'average': bn(g_avg) if g_avg is not None else '',
                'rank': g_rank, 'appr': g_appr,
            })

        # --- résultat général -----------------------------------------
        annual_rec = env['silina.annual.result']
        if annual:
            annual_rec = annual_rec.search(
                [('student_id', '=', student.id), ('academic_year_id', '=', year.id)], limit=1)
        title_ord, result_label = ('BULLETIN ANNUEL', 'Résultat annuel')
        if multi:
            periods_cells = []
            for p in shown:
                res = res_by_p.get(p.id)
                has = bool(res and res.has_average)
                periods_cells.append({
                    'name': p.name, 'code': p.code or p.name,
                    'avg': bn(res.average) if has else '',
                    'rank': self._bl_rank(res.rank) if has else '',
                })
            if annual_rec and annual_rec.has_average:
                avg = annual_rec.annual_average
                src = annual_rec
            else:
                avgs = [r.average for r in res_by_p.values() if r.has_average]
                avg = sum(avgs) / len(avgs) if avgs else None
                src = False
            phrase = ''
            class_avg, plus_forte, plus_faible = (
                (src.class_average, src.class_max, src.class_min) if src else (None, None, None))
            rank = self._bl_rank(src.rank) if src and opts['include_rank'] else ''
            if period and not annual:
                title_ord, result_label = self._bl_period_labels(period, all_periods)
                title_ord = 'BULLETIN'
        else:
            title_ord, result_label = self._bl_period_labels(period, all_periods)
            periods_cells = []
            res = last_res
            has = bool(res and res.has_average)
            avg = res.average if has else None
            phrase = res.result_phrase if has else ''
            class_avg = res.class_average if has else None
            plus_forte = res.plus_forte if has else None
            plus_faible = res.plus_faible if has else None
            rank = self._bl_rank(res.rank) if has and opts['include_rank'] else ''

        general_appr = company.appreciation_for(avg) if avg is not None else ''

        # --- résultat annuel (dernier bulletin de l'année) ----------------
        annual_block = False
        if (not multi and opts.get('include_annual', True) and period
                and len(all_periods) > 1 and period == all_periods[-1]):
            ar = env['silina.annual.result'].search(
                [('student_id', '=', student.id), ('academic_year_id', '=', year.id)], limit=1)
            per_res = PR.search([('student_id', '=', student.id),
                                 ('period_id', 'in', all_periods.ids),
                                 ('has_average', '=', True)])
            per_by_id = {r.period_id.id: r for r in per_res}
            if ar and ar.has_average:
                a_avg, a_rank = ar.annual_average, ar.rank
            elif per_res:
                a_avg = sum(per_res.mapped('average')) / len(per_res)
                a_rank = 0
            else:
                a_avg, a_rank = None, 0
            if a_avg is not None:
                a_decision = ''
                if ar and 'final_decision' in ar._fields:
                    final = ar.final_decision
                    if final and final != 'pending':
                        a_decision = (ar.decision_label if 'decision_label' in ar._fields else '') \
                            or DECISION_LABELS.get(final, str(final))
                a_appr = company.appreciation_for(a_avg)
                annual_block = {
                    'label': 'Résultat annuel %s' % year.name,
                    'avg': bn(a_avg),
                    'rank': self._bl_rank(a_rank) if (opts['include_rank'] and a_rank) else '',
                    'phrase': '%s, %s.' % (ru.average_in_words(a_avg), a_appr) if a_appr
                    else '%s.' % ru.average_in_words(a_avg),
                    'decision': a_decision,
                    'periods': [{'label': self._bl_period_short(p, all_periods),
                                 'avg': bn(per_by_id[p.id].average)}
                                for p in all_periods if p.id in per_by_id],
                }

        # --- identité ---------------------------------------------------
        female = student.gender == 'female'
        repeater = bool(student.is_repeater)
        dob = student.date_of_birth.strftime('%d/%m/%Y') if student.date_of_birth else ''
        ident = '%s%s, sexe %s%s' % (
            'Redoublant' if repeater else 'Non redoublant', 'e' if female else '',
            'féminin' if female else 'masculin',
            (', %s le %s' % ('née' if female else 'né', dob)) if dob else '')
        level_name = classroom.level_id.name if 'level_id' in classroom._fields and classroom.level_id else ''
        class_name = level_name or classroom.name or ''
        effectif = env['silina.student'].search_count(
            [('classroom_id', '=', classroom.id), ('state', '=', 'enrolled')]) if classroom else 0
        if not effectif and last_res:
            effectif = last_res.effectif

        decision = ''
        if annual and annual_rec and 'final_decision' in annual_rec._fields:
            final = annual_rec.final_decision
            if final and final != 'pending':
                label_field = annual_rec.decision_label if 'decision_label' in annual_rec._fields else ''
                decision = label_field or DECISION_LABELS.get(final, str(final))

        teacher = director = ''
        for p in shown:
            r = res_by_p.get(p.id)
            if r:
                teacher = r.appreciation_teacher or teacher
                director = r.appreciation_director or director

        main_teacher = classroom.main_teacher_id if classroom else False
        today = fields.Date.context_today(self)
        city = (company.city or '').upper()
        city_date = '%s le %s' % (city, today.strftime('%d/%m/%Y')) if city else \
            'Le %s' % today.strftime('%d/%m/%Y')
        multi_title = title_ord
        if multi and annual:
            multi_title = 'BULLETIN ANNUEL'

        return {
            'student': student,
            'classroom': classroom,
            'year': year,
            'year_name': year.name,
            'title': multi_title,
            'student_name': student.name,
            'ident_line': ident,
            'class_name': class_name,
            'effectif': effectif or '',
            'multi': multi,
            'annual': bool(annual),
            'periods': periods_cells,
            'groups': groups,
            'total_coef': self._bl_coef(tot_coef),
            'total_points': bn(tot_points),
            'general_avg': bn(avg) if avg is not None else '',
            'general_rank': rank,
            'general_appr': general_appr,
            'annual_block': annual_block,
            'result_label': result_label,
            'result_avg': bn(avg),
            'result_rank': rank,
            'result_phrase': phrase,
            'plus_forte': bn(plus_forte) if plus_forte else '',
            'plus_faible': bn(plus_faible) if plus_faible else '',
            'class_avg': bn(class_avg) if class_avg else '',
            'decision': decision,
            'teacher_comment': teacher if opts['include_comments'] else '',
            'director_comment': director if opts['include_comments'] else '',
            'show_rank': opts['include_rank'],
            'show_stats': opts['include_statistics'],
            'city_date': city_date,
            'teacher_name': (main_teacher.display_short_name or main_teacher.name) if main_teacher else '',
            'director_name': company.silina_director_name or '',
            'ministry1': company.silina_ministry_line1 or '',
            'ministry2': company.silina_ministry_line2 or '',
            'ministry3': company.silina_ministry_line3 or '',
            'has_data': bool(groups),
            'max_mark': self._bl_coef(max_mark),
        }


class ReportBulletinSouche(models.AbstractModel):
    """Bulletin paysage « avec souche » : mêmes données, gabarit différent."""
    _name = 'report.silina_edu.report_bulletin_souche_document'
    _inherit = 'report.silina_edu.report_bulletin_document'
    _description = 'Rapport bulletin collège/lycée avec souche'


class ReportLivret(models.AbstractModel):
    _name = 'report.silina_edu.report_livret_document'
    _inherit = 'silina.report.card.mixin'
    _description = 'Rapport livret crèche/préscolaire/primaire'

    @api.model
    def _get_report_values(self, docids, data=None):
        """Livret : grille des compositions mensuelles (modèle papier portrait)."""
        data = data or {}
        ctx = self.env.context
        student_ids = docids or data.get('student_ids') or []
        students = self.env['silina.student'].browse(student_ids).exists()
        period_id = data.get('period_id') or ctx.get('period_id')
        period = self.env['silina.period'].browse(int(period_id)) if period_id else False
        settings = self.env.company.get_silina_settings()
        cards = [self._build_livret_card(s, period, settings) for s in students]
        return {
            'doc_ids': students.ids,
            'doc_model': 'silina.student',
            'docs': students,
            'cards': cards,
            'company': self.env.company,
            'data': data,
            'levels': [(LIVRET_LEVEL_SHORT.get(lbl, lbl), lbl) for _t, lbl, _c in COMPETENCY_LEVELS],
        }

    @staticmethod
    def _livret_num(value):
        """Note au format français sans zéros inutiles ; '' si absente (jamais 0 par défaut)."""
        if value is None or value is False:
            return ''
        return ('%.2f' % value).rstrip('0').rstrip('.').replace('.', ',')

    @staticmethod
    def _livret_date(value):
        return value.strftime('%d/%m/%Y') if value else ''

    @api.model
    def _build_livret_card(self, student, period, settings):
        env = self.env
        year = period.academic_year_id if period else student.academic_year_id
        classroom = student.classroom_id
        level = classroom.level_id or student.level_id
        degree = classroom.degree or student.degree
        mode = settings['livret_mode'].get(degree, 'numeric')
        show_rank = degree == 'primary' or bool(settings['show_rank'].get(degree))
        competency = mode == 'competency'
        max_mark = 20.0

        grid_data = env['silina.exam.result'].get_monthly_grid(student, year)
        grid = grid_data['grid']

        # Disciplines : matières affectées à la classe + matières ayant des notes.
        subjects = env['silina.subject']
        if classroom:
            subjects |= classroom.subject_assignment_ids.mapped('subject_id')
        subjects |= env['silina.subject'].browse(list(grid.keys())).exists()
        subjects = subjects.sorted(lambda s: (s.sequence, s.id))

        n_months = max([LIVRET_MONTHS] + list(grid_data['totals'].keys()) +
                       [n for m in grid.values() for n in m])
        month_nums = list(range(1, n_months + 1))

        def cell_value(note):
            if note is None:
                return ''
            if competency:
                label, _css = competency_level(note, max_mark)
                return LIVRET_LEVEL_SHORT.get(label, label)
            return self._livret_num(note)

        rows = []
        prev_group = None
        for subj in subjects:
            notes = grid.get(subj.id, {})
            values = [notes.get(n) for n in month_nums]
            present = [v for v in values if v is not None]
            if competency:
                total = cell_value(sum(present) / len(present)) if present else ''
            else:
                total = self._livret_num(grid_data['subject_totals'].get(subj.id)) if present else ''
            group = (subj.livret_group or '').strip()
            rows.append({
                'name': subj.get_livret_name(),
                'group': group,
                'group_start': bool(group) and group != prev_group,
                'group_size': 0,
                'cells': [cell_value(v) for v in values],
                'total': total,
                'long': len(subj.get_livret_name() or '') > 30,
            })
            prev_group = group or None
        # Taille des groupes (matières contiguës de même libellé).
        i = 0
        while i < len(rows):
            if rows[i]['group_start']:
                j = i
                while j + 1 < len(rows) and rows[j + 1]['group'] == rows[i]['group']:
                    j += 1
                rows[i]['group_size'] = j - i + 1
                i = j + 1
            else:
                i += 1

        totals = grid_data['totals']
        averages = grid_data['averages']
        ranks = grid_data['ranks']
        avg_values = [averages[n] for n in month_nums if averages.get(n) is not None]
        total_cells = [self._livret_num(totals.get(n)) for n in month_nums]
        if competency:
            average_cells = [cell_value(averages.get(n)) for n in month_nums]
            average_total = cell_value(sum(avg_values) / len(avg_values)) if avg_values else ''
        else:
            average_cells = [self._livret_num(averages.get(n)) for n in month_nums]
            average_total = self._livret_num(sum(avg_values) / len(avg_values)) if avg_values else ''
        rank_cells = [str(ranks[n]) if (show_rank and n in ranks) else '' for n in month_nums]
        total_sum = sum(v for v in totals.values() if v is not None)

        # Appréciations par trimestre (T1/T2/T3, repli sur l'ordre des périodes).
        periods = env['silina.period'].search(
            [('academic_year_id', '=', year.id)], order='sequence, date_start, id')
        results = {r.period_id.id: r for r in env['silina.period.result'].search(
            [('student_id', '=', student.id), ('academic_year_id', '=', year.id)])}
        by_code = {(p.code or '').strip().upper(): p for p in periods}
        terms = []
        for idx, code in enumerate(LIVRET_TERM_CODES):
            p = by_code.get(code)
            if not p and len(periods) <= len(LIVRET_TERM_CODES) and idx < len(periods):
                p = periods[idx]
            res = results.get(p.id) if p else None
            terms.append({
                'teacher': (res.appreciation_teacher or '') if res else '',
                'director': (res.appreciation_director or '') if res else '',
            })

        level_key = (level.code or '').replace(' ', '').upper() if level else ''
        title = LIVRET_LEVEL_TITLES.get(level_key) or (level.name or '').upper() if level else ''
        if year.date_start and year.date_end:
            year_label = '%s / %s' % (year.date_start.year, year.date_end.year)
        else:
            year_label = (year.name or '').replace('-', ' / ')
        effectif = len(classroom.student_ids.filtered(
            lambda s: s.state in ('enrolled', 'promoted', 'repeated'))) if classroom else 0

        return {
            'student': student,
            'classroom': classroom,
            'year': year,
            'year_label': year_label,
            'title': title,
            'entry_date': self._livret_date(student.enrollment_date),
            'effectif': effectif or '',
            'mode': mode,
            'competency': competency,
            'show_rank': show_rank,
            'month_nums': month_nums,
            'rows': rows,
            'total_cells': total_cells,
            'total_sum': ('' if competency else self._livret_num(total_sum)) if totals else '',
            'average_cells': average_cells,
            'average_total': average_total,
            'rank_cells': rank_cells,
            'terms': terms,
            'has_data': bool(grid),
        }


# ----------------------------------------------------------------------
# Boutons « Imprimer » sur les résultats
# ----------------------------------------------------------------------
class PeriodResultPrint(models.Model):
    _inherit = 'silina.period.result'

    def action_print_report_card(self):
        self.ensure_one()
        return self.env['silina.report.card.mixin'].get_report_card_action(
            self.student_id.ids, period_id=self.period_id.id)


class AnnualResultPrint(models.Model):
    _inherit = 'silina.annual.result'

    def action_print_report_card(self):
        self.ensure_one()
        return self.env['silina.report.card.mixin'].get_report_card_action(
            self.student_id.ids, annual=True)


# ----------------------------------------------------------------------
# Assistant
# ----------------------------------------------------------------------
class GenerateReportCard(models.TransientModel):
    _name = 'silina.generate.report.card.wizard'
    _description = 'Assistant de Génération de Bulletin de Notes'

    def _default_academic_year(self):
        Student = self.env['silina.student']
        student_ids = []
        for cmd in self.env.context.get('default_student_ids') or []:
            if isinstance(cmd, (list, tuple)):
                if cmd[0] == 6:
                    student_ids += list(cmd[2])
            else:
                student_ids.append(cmd)
        if student_ids:
            year = Student.browse(student_ids).exists()[:1].academic_year_id
            if year:
                return year
        return self.env['silina.academic.year'].get_current_year()

    def _default_period(self):
        year = self._default_academic_year()
        periods = self.env['silina.period'].search(
            [('academic_year_id', '=', year.id)], order='sequence, date_start, id')
        today = fields.Date.context_today(self)
        current = periods.filtered(lambda p: p.date_start <= today <= p.date_end)
        return (current or periods)[:1]

    def _default_generation_type(self):
        return 'student' if self.env.context.get('default_student_ids') else 'classroom'

    academic_year_id = fields.Many2one(
        'silina.academic.year', string='Année Scolaire', required=True,
        default=_default_academic_year,
        help="Sélectionnez l'année scolaire pour laquelle générer les bulletins")
    report_scope = fields.Selection([
        ('period', 'Une période'),
        ('annual', 'Annuel'),
    ], string='Document', default='period', required=True,
        help="Période : bulletin/livret d'une période. Annuel : toutes les périodes + moyenne annuelle.")
    period_id = fields.Many2one(
        'silina.period', string='Période', default=_default_period,
        domain="[('academic_year_id', '=', academic_year_id)]")

    generation_type = fields.Selection([
        ('classroom', 'Par classe'),
        ('student', 'Par élève'),
    ], string='Type de génération', default=_default_generation_type, required=True)

    classroom_ids = fields.Many2many(
        'silina.classroom', 'report_card_classroom_rel', 'wizard_id', 'classroom_id',
        string='Classes', domain="[('academic_year_id', '=', academic_year_id)]")
    student_ids = fields.Many2many(
        'silina.student', 'report_card_student_rel', 'wizard_id', 'student_id',
        string='Élèves')

    bulletin_count = fields.Integer(string='Bulletins (collège/lycée)', compute='_compute_counts')
    livret_count = fields.Integer(string='Livrets (crèche/préscolaire/primaire)', compute='_compute_counts')

    recompute = fields.Boolean(
        string='Recalculer les résultats', default=False,
        help="Force le recalcul des résultats (hors résultats définitifs). "
             "Sinon, seuls les résultats manquants sont calculés.")
    include_rank = fields.Boolean(
        string='Inclure le rang', default=True,
        help="Afficher le rang de l'élève (bulletins). Pour les livrets, "
             "l'affichage du rang dépend des paramètres de la société.")
    include_statistics = fields.Boolean(
        string='Inclure les statistiques', default=True,
        help="Afficher les moyennes de classe, min, max")
    include_comments = fields.Boolean(
        string='Inclure les commentaires', default=True,
        help="Afficher les appréciations de l'enseignant et de la direction")
    include_annual = fields.Boolean(
        string='Résultat annuel sur le dernier bulletin', default=True,
        help="Sur le bulletin de la dernière période de l'année : ajoute le résultat annuel, "
             "le rang annuel, les moyennes des périodes et la décision du conseil de classe.")
    skip_empty = fields.Boolean(
        string='Ignorer les élèves sans résultat', default=True,
        help="Ne pas imprimer de bulletin vide pour les élèves sans aucune note confirmée "
             "sur la période.")
    no_result_count = fields.Integer(
        string='Élèves sans résultat', compute='_compute_counts')
    bulletin_stub = fields.Boolean(
        string='Avec souche', default=False,
        help="Bulletin paysage avec deux exemplaires côte à côte "
             "(le second est la souche à conserver par l'établissement).")
    language = fields.Selection([
        ('fr_FR', 'Français'),
        ('en_US', 'Anglais'),
    ], string='Langue', default='fr_FR')

    @api.onchange('academic_year_id')
    def _onchange_academic_year_id(self):
        if self.period_id and self.period_id.academic_year_id != self.academic_year_id:
            self.period_id = False
        if not self.period_id and self.academic_year_id:
            period = self.env['silina.period'].search(
                [('academic_year_id', '=', self.academic_year_id.id)],
                order='sequence, date_start, id', limit=1)
            self.period_id = period
        self.classroom_ids = self.classroom_ids.filtered(
            lambda c: c.academic_year_id == self.academic_year_id)

    # ------------------------------------------------------------------
    def _get_students(self):
        self.ensure_one()
        if self.generation_type == 'classroom':
            if not self.classroom_ids:
                return self.env['silina.student']
            return self.env['silina.student'].search([
                ('classroom_id', 'in', self.classroom_ids.ids),
                ('state', 'not in', ('draft', 'expelled')),
            ], order='classroom_id, name')
        return self.student_ids

    def _target_periods(self):
        """Périodes concernées par le document (toutes pour l'annuel)."""
        self.ensure_one()
        if self.report_scope == 'annual':
            return self.env['silina.period'].search(
                [('academic_year_id', '=', self.academic_year_id.id)],
                order='sequence, date_start, id')
        return self.period_id

    def _students_with_result(self, students):
        """Élèves ayant au moins un résultat calculé ou une note confirmée sur les périodes cibles."""
        self.ensure_one()
        periods = self._target_periods()
        if not (students and periods):
            return self.env['silina.student']
        base = [('student_id', 'in', students.ids), ('period_id', 'in', periods.ids)]
        with_result = self.env['silina.period.result'].search(
            base + [('has_average', '=', True)]).mapped('student_id')
        with_marks = self.env['silina.exam.result'].search(
            base + [('state', '=', 'confirmed'), ('mark_entered', '=', True)]).mapped('student_id')
        return with_result | with_marks

    @api.depends('generation_type', 'classroom_ids', 'student_ids', 'academic_year_id',
                 'report_scope', 'period_id')
    def _compute_counts(self):
        for wiz in self:
            students = wiz._get_students()
            livrets = students.filtered(lambda s: s.degree in LIVRET_DEGREES)
            wiz.livret_count = len(livrets)
            wiz.bulletin_count = len(students) - len(livrets)
            wiz.no_result_count = len(students - wiz._students_with_result(students))

    def _check_ready(self):
        self.ensure_one()
        students = self._get_students()
        if not students:
            if self.generation_type == 'classroom':
                if not self.classroom_ids:
                    raise ValidationError(_(
                        "Sélectionnez au moins une classe (champ « Classes »)."))
                raise ValidationError(_(
                    "Aucun élève à imprimer dans les classes sélectionnées : classes sans "
                    "élèves, ou élèves auxquels vous n'avez pas accès (un enseignant ne voit "
                    "que ses propres classes)."))
            raise ValidationError(_("Sélectionnez au moins un élève (champ « Élèves »)."))
        if self.report_scope == 'period':
            if not self.period_id:
                raise ValidationError(_('Veuillez sélectionner une période (ou choisir « Annuel »).'))
            if self.period_id.academic_year_id != self.academic_year_id:
                raise ValidationError(_(
                    "La période « %s » n'appartient pas à l'année scolaire « %s »."
                ) % (self.period_id.display_name, self.academic_year_id.name))
        return students

    def _ensure_results(self, students):
        """Calcule les résultats de période (et annuels) manquants."""
        self.ensure_one()
        PR = self.env['silina.period.result']
        AR = self.env['silina.annual.result']
        year = self.academic_year_id
        all_periods = self.env['silina.period'].search(
            [('academic_year_id', '=', year.id)], order='sequence, date_start, id')
        # Le dernier bulletin de l'année affiche aussi le résultat annuel.
        annual = self.report_scope == 'annual' or bool(
            self.include_annual and len(all_periods) > 1 and self.period_id == all_periods[-1])
        periods = all_periods if annual else self.period_id
        for classroom in students.mapped('classroom_id'):
            cls_students = students.filtered(lambda s: s.classroom_id == classroom)
            for period in periods:
                if period.academic_year_id != classroom.academic_year_id:
                    continue
                existing = PR.search_count([
                    ('period_id', '=', period.id), ('student_id', 'in', cls_students.ids)])
                if self.recompute or existing < len(cls_students):
                    PR.compute_for_classroom(classroom.id, period.id)
            if annual and classroom.academic_year_id == year:
                existing = AR.search_count([
                    ('academic_year_id', '=', year.id), ('student_id', 'in', cls_students.ids)])
                if self.recompute or existing < len(cls_students):
                    AR.compute_for_classroom(classroom.id)

    def _generate(self, students, kind=None):
        self.ensure_one()
        self._ensure_results(students)
        if self.skip_empty:
            with_result = self._students_with_result(students)
            students = students.filtered(lambda s: s in with_result)
            if not students:
                raise UserError(_(
                    "Aucun élève n'a de résultat pour cette période : saisissez et confirmez "
                    "les notes (Résultats d'examen) avant de générer les bulletins."))
        lang = self.language if self.env['res.lang'].search_count(
            [('code', '=', self.language), ('active', '=', True)]) else self.env.lang
        mixin = self.env['silina.report.card.mixin'].with_context(lang=lang)
        return mixin.get_report_card_action(
            students.ids,
            period_id=self.period_id.id if self.report_scope == 'period' else False,
            annual=self.report_scope == 'annual',
            kind=kind,
            include_rank=self.include_rank,
            include_statistics=self.include_statistics,
            include_comments=self.include_comments,
            stub=self.bulletin_stub,
            include_annual=self.include_annual,
        )

    def action_generate_preview(self):
        """Prévisualiser un seul document (premier élève)."""
        self.ensure_one()
        students = self._check_ready()[:1]
        return self._generate(students)

    def action_generate(self):
        """Générer pour tous les élèves (lot homogène)."""
        self.ensure_one()
        return self._generate(self._check_ready())

    def action_generate_bulletins(self):
        self.ensure_one()
        students = self._check_ready().filtered(lambda s: s.degree not in LIVRET_DEGREES)
        return self._generate(students, kind='bulletin')

    def action_generate_livrets(self):
        self.ensure_one()
        students = self._check_ready().filtered(lambda s: s.degree in LIVRET_DEGREES)
        return self._generate(students, kind='livret')
