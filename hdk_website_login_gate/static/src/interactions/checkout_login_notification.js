/** @odoo-module **/

import { Interaction } from "@web/public/interaction";
import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";

/**
 * After redirect from /shop/checkout for guests, show the same cart-style warning toast.
 *
 * Must target an element inside the public interaction scan root (`#wrapwrap`). Using `body`
 * never matched because the interaction service only searches descendants of `#wrapwrap`.
 */
export class HdkCheckoutLoginNotification extends Interaction {
    static selector = "#wrapwrap";

    start() {
        const params = new URLSearchParams(window.location.search);
        if (params.get("hdk_checkout_login") !== "1") {
            return;
        }
        const msg = _t("Please sign in to continue to checkout.");
        const show = () => {
            const cartNotification = this.services.cartNotificationService;
            if (cartNotification?.add) {
                cartNotification.add("", { warning: msg });
            }
        };
        // Next frame so cart notification container / services are fully wired (same as cart RPC flow).
        queueMicrotask(show);

        params.delete("hdk_checkout_login");
        const qs = params.toString();
        const cleanUrl =
            window.location.pathname +
            (qs ? `?${qs}` : "") +
            window.location.hash;
        window.history.replaceState({}, "", cleanUrl);
    }
}

registry
    .category("public.interactions")
    .add(
        "hdk_website_login_gate.checkout_login_notification",
        HdkCheckoutLoginNotification
    );
