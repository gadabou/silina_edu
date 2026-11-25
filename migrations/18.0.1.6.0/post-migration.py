OLD = "Ministère de l'éducation nationale"
NEW = "Ministère de l'éducation nationale (MEN)"


def migrate(cr, version):
    """En-tête officiel : ajoute le sigle (MEN) à l'ancienne valeur par défaut.

    Les nouvelles lignes (direction régionale, inspection, établissement) reçoivent
    leur valeur par défaut à la création des colonnes. Un intitulé personnalisé est
    conservé. Idempotent.
    """
    cr.execute(
        "UPDATE res_company SET silina_ministry_line1 = %s WHERE silina_ministry_line1 = %s",
        (NEW, OLD))
