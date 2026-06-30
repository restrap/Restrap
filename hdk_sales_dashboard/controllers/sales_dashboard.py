from odoo import http
from odoo.http import request


class SalesDashboardController(http.Controller):

    @http.route("/hdk_sales_dashboard/data", type="json", auth="user")
    def get_data(self, date_type, date_from, date_to):
        return request.env["hdk.sales.dashboard"].get_dashboard(
            date_type, date_from, date_to
        )

    @http.route("/hdk_sales_dashboard/drilldown", type="json", auth="user")
    def drilldown(self, channel_key, date_type, date_from, date_to,
                  instance_id=False):
        return request.env["hdk.sales.dashboard"].action_drilldown(
            channel_key, date_type, date_from, date_to,
            instance_id=instance_id,
        )
