from odoo import models, fields, api, _
from odoo.exceptions import ValidationError

LIVRET_MODES = [
    ('numeric', 'Notes sur 20'),
    ('competency', 'Compétences'),
]

MENTION_FIELDS = [
    # (champ société, libellé de mention, défaut)
    ('silina_mention_excellent', 'Excellent', 18.0),
    ('silina_mention_very_good', 'Très bien', 16.0),
    ('silina_mention_good', 'Bien', 14.0),
    ('silina_mention_fairly_good', 'Assez bien', 12.0),
    ('silina_mention_passable', 'Passable', 10.0),
]


class ResCompany(models.Model):
    _inherit = 'res.company'

    silina_pass_average = fields.Float(string='Moyenne de passage', default=10.0)
    silina_indulgence_average = fields.Float(
        string="Moyenne minimale d'admission par indulgence", default=9.0)
    silina_max_mark = fields.Float(string='Barème (note maximale)', default=20.0)
    silina_livret_mode_daycare = fields.Selection(
        LIVRET_MODES, string='Mode du livret - Crèche', default='numeric')
    silina_livret_mode_preschool = fields.Selection(
        LIVRET_MODES, string='Mode du livret - Préscolaire', default='numeric')
    silina_livret_mode_primary = fields.Selection(
        LIVRET_MODES, string='Mode du livret - Primaire', default='numeric')
    silina_show_rank_daycare = fields.Boolean(string='Afficher le rang - Crèche', default=False)
    silina_show_rank_preschool = fields.Boolean(string='Afficher le rang - Préscolaire', default=False)
    silina_mention_excellent = fields.Float(string='Seuil Excellent', default=18.0)
    silina_mention_very_good = fields.Float(string='Seuil Très bien', default=16.0)
    silina_mention_good = fields.Float(string='Seuil Bien', default=14.0)
    silina_mention_fairly_good = fields.Float(string='Seuil Assez bien', default=12.0)
    silina_mention_passable = fields.Float(string='Seuil Passable', default=10.0)

    # En-tête officiel et signatures
    silina_director_name = fields.Char(string='Nom du directeur')
    silina_ministry_line1 = fields.Char(
        string='En-tête officiel - ligne 1',
        default="Ministère de l'éducation nationale")
    silina_ministry_line2 = fields.Char(
        string='En-tête officiel - ligne 2', default='RÉPUBLIQUE TOGOLAISE')
    silina_ministry_line3 = fields.Char(
        string='En-tête officiel - devise', default='Travail – Liberté – Patrie')

    # Identité de l'en-tête (vide = valeur de la société Odoo)
    silina_school_name = fields.Char(string="Nom de l'établissement (en-tête)")
    silina_show_logo = fields.Boolean(string="Afficher le logo", default=True)
    silina_header_logo = fields.Binary(string="Logo de l'en-tête")
    silina_header_address = fields.Char(string="Adresse (en-tête)")
    silina_header_phone = fields.Char(string="Téléphone (en-tête)")
    silina_header_email = fields.Char(string="Email (en-tête)")
    silina_header_extra = fields.Char(
        string="Mention complémentaire (agrément, BP, etc.)")
    silina_footer_text = fields.Char(string="Pied de page des bulletins")

    # Groupes de matières du bulletin
    silina_group_label_a = fields.Char(
        string='Libellé du groupe A', default='Matières littéraires')
    silina_group_label_b = fields.Char(
        string='Libellé du groupe B', default='Matières scientifiques')
    silina_group_label_c = fields.Char(
        string='Libellé du groupe C', default='Autres matières')

    # Barème d'appréciation par moyenne : moyenne < seuil_i -> libellé_i
    silina_appr_threshold_1 = fields.Float(string='Seuil 1', default=5.0)
    silina_appr_threshold_2 = fields.Float(string='Seuil 2', default=8.0)
    silina_appr_threshold_3 = fields.Float(string='Seuil 3', default=10.0)
    silina_appr_threshold_4 = fields.Float(string='Seuil 4', default=12.0)
    silina_appr_threshold_5 = fields.Float(string='Seuil 5', default=14.0)
    silina_appr_threshold_6 = fields.Float(string='Seuil 6', default=16.0)
    silina_appr_label_1 = fields.Char(string='Libellé < seuil 1', default='Très faible')
    silina_appr_label_2 = fields.Char(string='Libellé < seuil 2', default='Faible')
    silina_appr_label_3 = fields.Char(string='Libellé < seuil 3', default='Insuffisant')
    silina_appr_label_4 = fields.Char(string='Libellé < seuil 4', default='Passable')
    silina_appr_label_5 = fields.Char(string='Libellé < seuil 5', default='Assez bien')
    silina_appr_label_6 = fields.Char(string='Libellé < seuil 6', default='Bien')
    silina_appr_label_7 = fields.Char(string='Libellé ≥ seuil 6', default='Très bien')

    @api.constrains('silina_pass_average', 'silina_indulgence_average')
    def _check_silina_averages(self):
        for company in self:
            if company.silina_indulgence_average > company.silina_pass_average:
                raise ValidationError(_(
                    "La moyenne d'indulgence doit être inférieure ou égale à la moyenne de passage."))

    # ------------------------------------------------------------------
    # Helpers publics
    # ------------------------------------------------------------------
    def get_silina_settings(self):
        """Retourne les paramètres Silina de la société sous forme de dict."""
        self.ensure_one()
        return {
            'pass_average': self.silina_pass_average,
            'indulgence_average': self.silina_indulgence_average,
            'max_mark': self.silina_max_mark,
            'livret_mode': {
                'daycare': self.silina_livret_mode_daycare or 'numeric',
                'preschool': self.silina_livret_mode_preschool or 'numeric',
                'primary': self.silina_livret_mode_primary or 'numeric',
            },
            'show_rank': {
                'daycare': self.silina_show_rank_daycare,
                'preschool': self.silina_show_rank_preschool,
            },
            'mention_scale': self._get_silina_mention_scale(),
            'appreciation_scale': self._get_silina_appreciation_scale(),
            'group_labels': {c: self.group_label(c) for c in ('A', 'B', 'C')},
            'director_name': self.silina_director_name or '',
            'ministry_lines': [self.silina_ministry_line1 or '',
                               self.silina_ministry_line2 or '',
                               self.silina_ministry_line3 or ''],
        }

    def get_silina_header(self):
        """En-tête des bulletins/livrets : valeurs saisies dans les paramètres,
        à défaut celles de la société enregistrée."""
        self.ensure_one()
        partner = self.partner_id
        address = self.silina_header_address
        if not address:
            parts = [self.street, self.street2,
                     ' '.join(p for p in (self.zip, self.city) if p),
                     self.country_id.name]
            address = ', '.join(p for p in parts if p)
        logo = False
        if self.silina_show_logo:
            logo = self.silina_header_logo
            # Le logo de la société est ignoré s'il s'agit de l'image « Your logo » d'Odoo.
            if not logo and self.logo and self.logo != self._get_logo():
                logo = self.logo
        return {
            'name': self.silina_school_name or self.name or '',
            'logo': logo,
            'address': address,
            'phone': self.silina_header_phone or self.phone or partner.phone or '',
            'email': self.silina_header_email or self.email or '',
            'extra': self.silina_header_extra or '',
            'footer': self.silina_footer_text or '',
        }

    def group_label(self, code):
        """Libellé du groupe de matières ('A', 'B', 'C') du bulletin."""
        self.ensure_one()
        return {
            'A': self.silina_group_label_a or 'Matières littéraires',
            'B': self.silina_group_label_b or 'Matières scientifiques',
            'C': self.silina_group_label_c or 'Autres matières',
        }.get(code, '')

    def _get_silina_appreciation_scale(self):
        """Retourne ([seuils croissants], [libellés]) ; len(libellés) = len(seuils) + 1."""
        self.ensure_one()
        defaults_t = [5.0, 8.0, 10.0, 12.0, 14.0, 16.0]
        defaults_l = ['Très faible', 'Faible', 'Insuffisant', 'Passable',
                      'Assez bien', 'Bien', 'Très bien']
        thresholds = []
        for i, d in enumerate(defaults_t, start=1):
            val = self['silina_appr_threshold_%d' % i]
            thresholds.append(d if val is False or val is None else val)
        labels = [self['silina_appr_label_%d' % i] or defaults_l[i - 1] for i in range(1, 8)]
        return thresholds, labels

    def appreciation_for(self, average):
        """Appréciation du bulletin pour une moyenne (sur 20) : '' si pas de moyenne.

        < s1 Très faible, < s2 Faible, < s3 Insuffisant, < s4 Passable,
        < s5 Assez bien, < s6 Bien, sinon Très bien (seuils/libellés configurables).
        """
        self.ensure_one()
        if average is None or average is False:
            return ''
        from . import result_utils as ru
        value = ru.round_half_up(average)
        thresholds, labels = self._get_silina_appreciation_scale()
        for threshold, label in zip(thresholds, labels):
            if value < threshold:
                return label
        return labels[-1]

    def _get_silina_mention_scale(self):
        """Liste [(seuil, libellé)] triée par seuil décroissant."""
        self.ensure_one()
        return [(self[fname], _(label)) for fname, label, _default in MENTION_FIELDS]

    def mention_for(self, average):
        """Retourne le libellé de mention pour une moyenne (sur 20), ou ''."""
        self.ensure_one()
        if average is None or average is False:
            return ''
        scale = sorted(self._get_silina_mention_scale(), key=lambda s: s[0], reverse=True)
        for threshold, label in scale:
            if average >= threshold:
                return label
        return ''


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    silina_pass_average = fields.Float(
        related='company_id.silina_pass_average', readonly=False)
    silina_indulgence_average = fields.Float(
        related='company_id.silina_indulgence_average', readonly=False)
    silina_max_mark = fields.Float(
        related='company_id.silina_max_mark', readonly=False)
    silina_livret_mode_daycare = fields.Selection(
        related='company_id.silina_livret_mode_daycare', readonly=False)
    silina_livret_mode_preschool = fields.Selection(
        related='company_id.silina_livret_mode_preschool', readonly=False)
    silina_livret_mode_primary = fields.Selection(
        related='company_id.silina_livret_mode_primary', readonly=False)
    silina_show_rank_daycare = fields.Boolean(
        related='company_id.silina_show_rank_daycare', readonly=False)
    silina_show_rank_preschool = fields.Boolean(
        related='company_id.silina_show_rank_preschool', readonly=False)
    silina_mention_excellent = fields.Float(
        related='company_id.silina_mention_excellent', readonly=False)
    silina_mention_very_good = fields.Float(
        related='company_id.silina_mention_very_good', readonly=False)
    silina_mention_good = fields.Float(
        related='company_id.silina_mention_good', readonly=False)
    silina_mention_fairly_good = fields.Float(
        related='company_id.silina_mention_fairly_good', readonly=False)
    silina_mention_passable = fields.Float(
        related='company_id.silina_mention_passable', readonly=False)

    silina_director_name = fields.Char(
        related='company_id.silina_director_name', readonly=False)
    silina_ministry_line1 = fields.Char(
        related='company_id.silina_ministry_line1', readonly=False)
    silina_ministry_line2 = fields.Char(
        related='company_id.silina_ministry_line2', readonly=False)
    silina_ministry_line3 = fields.Char(
        related='company_id.silina_ministry_line3', readonly=False)
    silina_school_name = fields.Char(
        related='company_id.silina_school_name', readonly=False)
    silina_show_logo = fields.Boolean(
        related='company_id.silina_show_logo', readonly=False)
    silina_header_logo = fields.Binary(
        related='company_id.silina_header_logo', readonly=False)
    silina_header_address = fields.Char(
        related='company_id.silina_header_address', readonly=False)
    silina_header_phone = fields.Char(
        related='company_id.silina_header_phone', readonly=False)
    silina_header_email = fields.Char(
        related='company_id.silina_header_email', readonly=False)
    silina_header_extra = fields.Char(
        related='company_id.silina_header_extra', readonly=False)
    silina_footer_text = fields.Char(
        related='company_id.silina_footer_text', readonly=False)
    silina_group_label_a = fields.Char(
        related='company_id.silina_group_label_a', readonly=False)
    silina_group_label_b = fields.Char(
        related='company_id.silina_group_label_b', readonly=False)
    silina_group_label_c = fields.Char(
        related='company_id.silina_group_label_c', readonly=False)
    silina_appr_threshold_1 = fields.Float(
        related='company_id.silina_appr_threshold_1', readonly=False)
    silina_appr_threshold_2 = fields.Float(
        related='company_id.silina_appr_threshold_2', readonly=False)
    silina_appr_threshold_3 = fields.Float(
        related='company_id.silina_appr_threshold_3', readonly=False)
    silina_appr_threshold_4 = fields.Float(
        related='company_id.silina_appr_threshold_4', readonly=False)
    silina_appr_threshold_5 = fields.Float(
        related='company_id.silina_appr_threshold_5', readonly=False)
    silina_appr_threshold_6 = fields.Float(
        related='company_id.silina_appr_threshold_6', readonly=False)
    silina_appr_label_1 = fields.Char(
        related='company_id.silina_appr_label_1', readonly=False)
    silina_appr_label_2 = fields.Char(
        related='company_id.silina_appr_label_2', readonly=False)
    silina_appr_label_3 = fields.Char(
        related='company_id.silina_appr_label_3', readonly=False)
    silina_appr_label_4 = fields.Char(
        related='company_id.silina_appr_label_4', readonly=False)
    silina_appr_label_5 = fields.Char(
        related='company_id.silina_appr_label_5', readonly=False)
    silina_appr_label_6 = fields.Char(
        related='company_id.silina_appr_label_6', readonly=False)
    silina_appr_label_7 = fields.Char(
        related='company_id.silina_appr_label_7', readonly=False)
