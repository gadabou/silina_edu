/** @odoo-module **/

import { registry } from "@web/core/registry";
import { download } from "@web/core/network/download";

/**
 * Service pour gérer l'impression automatique des factures thermiques
 */
const autoPrintInvoiceService = {
    dependencies: ["action"],

    start(env, { action: actionService }) {
        // Intercepter les actions de rapport pour déclencher l'impression automatique
        const originalDoAction = actionService.doAction.bind(actionService);

        actionService.doAction = async function (actionRequest, options = {}) {
            const action = await originalDoAction(actionRequest, options);

            // Vérifier si c'est notre rapport thermique
            if (
                action &&
                action.type === "ir.actions.report" &&
                action.report_name === "silina_edu.report_invoice_thermal_document"
            ) {
                // Attendre un court instant pour s'assurer que le PDF est prêt
                setTimeout(() => {
                    // Déclencher l'impression automatique du navigateur
                    window.print();
                }, 500);
            }

            return action;
        };
    },
};

registry.category("services").add("auto_print_invoice", autoPrintInvoiceService);
