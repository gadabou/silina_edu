OLD = "MINISTÈRE DES ENSEIGNEMENTS PRIMAIRE, SECONDAIRE, TECHNIQUE ET DE L'ARTISANAT"
NEW = "Ministère de l'éducation nationale"


def migrate(cr, version):
    """Intitulé du ministère : remplace l'ancienne valeur par défaut.

    Seules les sociétés qui ont encore l'ancienne valeur par défaut sont modifiées ;
    un intitulé personnalisé est conservé. Idempotent.
    """
    cr.execute(
        "UPDATE res_company SET silina_ministry_line1 = %s WHERE silina_ministry_line1 = %s",
        (NEW, OLD))
