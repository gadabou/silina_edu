def migrate(cr, version):
    """Résultats d'examen : les notes déjà présentes sont des notes saisies.

    Le champ « Note saisie » (mark_entered) est nouveau : sans cette reprise, les
    résultats existants s'afficheraient vides et seraient exclus des calculs.
    Idempotent.
    """
    cr.execute("ALTER TABLE silina_exam_result ADD COLUMN IF NOT EXISTS mark_entered boolean")
    cr.execute("UPDATE silina_exam_result SET mark_entered = true WHERE mark_entered IS NULL")
