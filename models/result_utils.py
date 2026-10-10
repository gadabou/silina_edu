# -*- coding: utf-8 -*-
"""Fonctions pures (sans dépendance Odoo) pour les calculs de moyennes et de rangs.

Règles :
- une note est ramenée sur ``max_mark`` (20 par défaut) : ``marks / total * max_mark`` ;
- les absents / sans note sont exclus en amont (jamais comptés 0) ;
- moyenne matière = moyenne simple des notes ramenées sur 20 de la période
  (les évaluations n'ont pas de pondération propre) ;
- moyenne générale = Σ(moyenne matière × coefficient) / Σ coefficients des
  matières ayant une moyenne ;
- rang de compétition (1, 1, 3) sur les valeurs arrondies à 2 décimales.
"""

ROUND_DIGITS = 2


def round_half_up(value, digits=ROUND_DIGITS):
    """Arrondi « commercial » (9,625 -> 9,63), contrairement au round() Python."""
    if value is None:
        return None
    from decimal import Decimal, ROUND_HALF_UP
    quant = Decimal(1).scaleb(-digits)
    return float(Decimal(repr(float(value))).quantize(quant, rounding=ROUND_HALF_UP))


def scale_mark(marks, total, max_mark=20.0):
    """Ramène ``marks`` (sur ``total``) sur ``max_mark``. None si barème invalide."""
    if not total or total <= 0 or marks is None:
        return None
    return marks / total * max_mark


def mean(values):
    values = [v for v in values if v is not None]
    if not values:
        return None
    return sum(values) / len(values)


def weighted_average(items):
    """items : iterable de (moyenne, coefficient). Ignore moyenne None / coef <= 0.

    Retourne (moyenne pondérée ou None, somme des coefficients retenus).
    """
    total = 0.0
    coef_sum = 0.0
    for avg, coef in items:
        if avg is None or not coef or coef <= 0:
            continue
        total += avg * coef
        coef_sum += coef
    if coef_sum <= 0:
        return None, 0.0
    return total / coef_sum, coef_sum


def competition_ranks(values):
    """values : dict clé -> valeur (None ignorée). Retourne dict clé -> rang (1,1,3)."""
    items = [(k, round_half_up(v)) for k, v in values.items() if v is not None]
    ranks = {}
    for key, val in items:
        ranks[key] = 1 + sum(1 for _k, other in items if other > val)
    return ranks


def class_stats(values):
    """Retourne (moyenne, max, min) des valeurs non nulles, ou (0, 0, 0)."""
    vals = [v for v in values if v is not None]
    if not vals:
        return 0.0, 0.0, 0.0
    return sum(vals) / len(vals), max(vals), min(vals)


# ----------------------------------------------------------------------
# Règle du bulletin : devoirs + composition
# ----------------------------------------------------------------------
def simple_average(homework, composition):
    """Moyenne matière = moyenne SIMPLE (moyenne des devoirs, note de composition).

    Si une seule des deux existe, c'est celle-là. None si aucune.
    Ex : (7.0, 10.5) -> 8.75 ; (9.25, 10.0) -> 9.625 (affiché 9,63).
    """
    return mean([homework, composition])


def group_totals(items):
    """items : iterable de (moyenne, coefficient) d'un groupe de matières.

    Retourne (total_coef, total_points, moyenne ou None) :
    total_points = Σ(moyenne × coef), moyenne = total_points / total_coef.
    """
    total_points = 0.0      # somme des Moy.Mat.Coeffic. déjà arrondies (comme sur le bulletin)
    exact_points = 0.0     # somme exacte, utilisée pour la moyenne du groupe
    total_coef = 0.0
    for avg, coef in items:
        if avg is None or not coef or coef <= 0:
            continue
        total_points += round_half_up(avg * coef)
        exact_points += avg * coef
        total_coef += coef
    if total_coef <= 0:
        return 0.0, 0.0, None
    return total_coef, total_points, exact_points / total_coef


# ----------------------------------------------------------------------
# Nombres en lettres (français) pour « Sept virgule quatre-vingt-trois »
# ----------------------------------------------------------------------
_UNITS = ['zéro', 'un', 'deux', 'trois', 'quatre', 'cinq', 'six', 'sept', 'huit',
          'neuf', 'dix', 'onze', 'douze', 'treize', 'quatorze', 'quinze', 'seize',
          'dix-sept', 'dix-huit', 'dix-neuf']
_TENS = {2: 'vingt', 3: 'trente', 4: 'quarante', 5: 'cinquante', 6: 'soixante'}


def int_to_french(n):
    """Entier 0..99 en lettres (orthographe rectifiée simple, traits d'union)."""
    n = int(n)
    if n < 0 or n > 99:
        return str(n)
    if n < 20:
        return _UNITS[n]
    tens, unit = divmod(n, 10)
    if tens in _TENS:
        base = _TENS[tens]
        if unit == 0:
            return base
        if unit == 1:
            return '%s et un' % base
        return '%s-%s' % (base, _UNITS[unit])
    if tens == 7:  # soixante-dix..soixante-dix-neuf
        if unit == 1:
            return 'soixante et onze'
        return 'soixante-%s' % _UNITS[10 + unit]
    # 80..99
    if n == 80:
        return 'quatre-vingts'
    return 'quatre-vingt-%s' % _UNITS[n - 80]


def average_in_words(value, digits=2):
    """12.5 -> 'Douze virgule cinquante' ; 7.83 -> 'Sept virgule quatre-vingt-trois'.

    Partie décimale lue comme un nombre (centièmes), zéros initiaux conservés
    (7.05 -> 'Sept virgule zéro cinq'). Valeurs > 99 : repli numérique.
    """
    if value is None:
        return ''
    value = round_half_up(value, digits)
    whole = int(value)
    frac = int(round((value - whole) * (10 ** digits)))
    text = int_to_french(whole)
    if frac:
        frac_str = str(frac).zfill(digits)
        words = ' '.join(['zéro'] * (len(frac_str) - len(frac_str.lstrip('0'))))
        words = (words + ' ' if words else '') + int_to_french(int(frac_str))
        text = '%s virgule %s' % (text, words)
    return text[:1].upper() + text[1:]
