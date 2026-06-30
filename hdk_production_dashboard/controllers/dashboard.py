from odoo import http
from odoo.http import request


class ProductionDashboardController(http.Controller):
    """Thin HTTP wrapper so the OWL client action can call the aggregator
    without going through the generic call_kw plumbing — keeps the
    payload small and the URL discoverable in the browser network tab.
    """

    @http.route(
        "/hdk_production_dashboard/data",
        type="json",
        auth="user",
    )
    def get_data(self, date_type, date_from, date_to):
        return request.env["hdk.production.dashboard"].get_dashboard(
            date_type, date_from, date_to
        )

    @http.route(
        "/hdk_production_dashboard/refresh",
        type="json",
        auth="user",
    )
    def refresh(self):
        request.env["hdk.production.dashboard"].action_refresh_cache()
        return {"ok": True}

    @http.route(
        "/hdk_production_dashboard/drilldown",
        type="json",
        auth="user",
    )
    def drilldown(self, channel_key, date_type, date_from, date_to,
                  instance_id=False):
        return request.env["hdk.production.dashboard"].action_drilldown(
            channel_key, date_type, date_from, date_to,
            instance_id=instance_id,
        )
