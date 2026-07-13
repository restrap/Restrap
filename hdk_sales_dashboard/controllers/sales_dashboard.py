import csv
import io

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

    @http.route("/hdk_sales_dashboard/drilldown/salesperson",
                type="json", auth="user")
    def drilldown_salesperson(self, user_id, date_type, date_from, date_to):
        return request.env["hdk.sales.dashboard"].action_drilldown_salesperson(
            user_id, date_type, date_from, date_to,
        )

    @http.route("/hdk_sales_dashboard/drilldown/product",
                type="json", auth="user")
    def drilldown_product(self, template_id, date_type, date_from, date_to):
        return request.env["hdk.sales.dashboard"].action_drilldown_product(
            template_id, date_type, date_from, date_to,
        )

    @http.route("/hdk_sales_dashboard/drilldown/customer",
                type="json", auth="user")
    def drilldown_customer(self, partner_id, date_type, date_from, date_to):
        return request.env["hdk.sales.dashboard"].action_drilldown_customer(
            partner_id, date_type, date_from, date_to,
        )

    @http.route("/hdk_sales_dashboard/export",
                type="http", auth="user", methods=["GET"], csrf=False)
    def export_csv(self, section, date_type, date_from, date_to, **_kw):
        payload = request.env["hdk.sales.dashboard"].get_csv_export(
            section, date_type, date_from, date_to,
        )
        buf = io.StringIO()
        writer = csv.writer(buf, lineterminator="\n")
        writer.writerow(payload["header"])
        for row in payload["rows"]:
            writer.writerow(["" if v is None else v for v in row])
        filename = f"sales_dashboard_{section}_{date_from}_{date_to}.csv"
        return request.make_response(
            buf.getvalue(),
            headers=[
                ("Content-Type", "text/csv; charset=utf-8"),
                ("Content-Disposition",
                 f'attachment; filename="{filename}"'),
            ],
        )
