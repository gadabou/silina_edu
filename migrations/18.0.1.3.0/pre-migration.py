import os

from lxml import etree


def migrate(cr, version):
    """Rattache aux identifiants XML du module les matières déjà créées à la main.

    Les données fournies (data/subjects_documents_data.xml) créent des matières
    avec un code unique (ECM, EPS, ...). Si la base contient déjà une matière de
    même code, créée manuellement donc sans identifiant XML, la mise à niveau
    échoue sur la contrainte « code_unique ». On lui associe l'identifiant XML
    attendu : le fichier de données la met alors à jour au lieu de la recréer.
    Idempotent : sans effet quand tout est déjà rattaché.
    """
    path = os.path.join(os.path.dirname(__file__), '..', '..', 'data', 'subjects_documents_data.xml')
    tree = etree.parse(os.path.normpath(path))
    for rec in tree.iter('record'):
        if rec.get('model') != 'silina.subject':
            continue
        xml_id = rec.get('id')
        code_node = rec.find("field[@name='code']")
        if not xml_id or code_node is None or not code_node.text:
            continue
        cr.execute("SELECT 1 FROM ir_model_data WHERE module = 'silina_edu' AND name = %s", (xml_id,))
        if cr.fetchone():
            continue
        cr.execute("SELECT id FROM silina_subject WHERE upper(trim(code)) = upper(%s) ORDER BY id LIMIT 1",
                   (code_node.text.strip(),))
        row = cr.fetchone()
        if not row:
            continue
        cr.execute("""
            SELECT 1 FROM ir_model_data
             WHERE model = 'silina.subject' AND res_id = %s AND module = 'silina_edu'
        """, (row[0],))
        if cr.fetchone():
            continue  # déjà rattachée à un autre identifiant du module
        cr.execute("""
            INSERT INTO ir_model_data (module, name, model, res_id, noupdate)
            VALUES ('silina_edu', %s, 'silina.subject', %s, false)
        """, (xml_id, row[0]))
