/** @odoo-module **/
import { registry } from "@web/core/registry";
import { listView } from "@web/views/list/list_view";
import { ListController } from "@web/views/list/list_controller";

/**
 * Liste des résultats d'examen : « Nouveau » ouvre la saisie groupée
 * (choix de l'examen -> tous les élèves de ses classes, matière et classe fixées).
 */
class ExamResultListController extends ListController {
    async createRecord() {
        await this.actionService.doAction("silina_edu.action_exam_result_entry", {
            additionalContext: this.props.context,
            onClose: () => this.model.load(),
        });
    }
}

registry.category("views").add("silina_exam_result_list", {
    ...listView,
    Controller: ExamResultListController,
});
