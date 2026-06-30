from datetime import datetime, timedelta

from odoo import api, fields, models
from odoo.exceptions import UserError

# Mapping of dashboard date filter to (sale_order column, stock_picking column).
# 'date_order' is the SO order date (the chosen proxy for "Scheduled Date"
# since SOs don't link to MOs in Restrap's make-to-stock model).
DATE_FIELD_MAP = {
    "delivery":  ("commitment_date", "scheduled_date"),
    "effective": ("effective_date",  "date_done"),
    "scheduled": ("date_order",      "scheduled_date"),
}

CHANNEL_DIRECT_KEY = "direct"
CHANNEL_TRANSFER_KEY = "transfer"


class ProductionDashboard(models.AbstractModel):
    """Read-only aggregator that powers the OWL dashboard."""

    _name = "hdk.production.dashboard"
    _description = "Restrap Production Time Dashboard Aggregator"

    @api.model
    def _validate_range(self, date_from, date_to):
        if not date_from or not date_to:
            raise UserError("Please select a date range.")
        if date_from > date_to:
            raise UserError("'From' date cannot be after 'To' date.")

    @api.model
    def _parse_range(self, date_from, date_to):
        df = fields.Date.from_string(date_from)
        dt = fields.Date.from_string(date_to)
        self._validate_range(df, dt)
        # Inclusive end-of-day on dt.
        return (
            datetime.combine(df, datetime.min.time()),
            datetime.combine(dt, datetime.max.time()),
        )

    @api.model
    def get_dashboard(self, date_type, date_from, date_to):
        if date_type not in DATE_FIELD_MAP:
            raise UserError("Unknown date filter '%s'." % date_type)
        so_col, pick_col = DATE_FIELD_MAP[date_type]
        df, dt = self._parse_range(date_from, date_to)

        channels = self._aggregate_sale_orders(so_col, df, dt)
        transfer_row = self._aggregate_transfers(pick_col, df, dt)
        if transfer_row:
            channels.append(transfer_row)

        incomplete = self._incomplete_bom_exception(so_col, df, dt)
        workcenter_load = self._workcenter_load(so_col, df, dt)
        daily_trend = self._daily_trend(so_col, df, dt)

        cache_meta = self.env["hdk.product.bom.time"].search_read(
            [], ["last_computed"], limit=1, order="last_computed desc"
        )
        last_refresh = cache_meta[0]["last_computed"] if cache_meta else False

        currency = self.env.company.currency_id
        return {
            "channels": channels,
            "totals": self._totals(channels),
            "incomplete": incomplete,
            "workcenter_load": workcenter_load,
            "daily_trend": daily_trend,
            "last_refresh": fields.Datetime.to_string(last_refresh) if last_refresh else False,
            "currency": {
                "symbol": currency.symbol,
                "position": currency.position,
            },
            "filters": {
                "date_type": date_type,
                "date_from": date_from,
                "date_to": date_to,
            },
        }

    # ------------------------------------------------------------------
    # Sales orders, grouped by Shopify instance (+ Direct/Other bucket)
    # ------------------------------------------------------------------
    @api.model
    def _aggregate_sale_orders(self, so_col, df, dt):
        # Excludes cancelled SOs. Includes draft+sent+sale+done so that
        # the same row makes sense whether the user looks forward (planned
        # production) or backward (delivered).
        self.env.cr.execute(
            f"""
            SELECT
                COALESCE(si.id, 0)                                AS instance_id,
                COALESCE(si.name, 'Direct / Other')               AS channel_name,
                COUNT(DISTINCT so.id)                             AS order_count,
                COALESCE(SUM(so.amount_total), 0.0)               AS order_value,
                COALESCE(SUM(
                    sol.product_uom_qty * COALESCE(bt.minutes_per_unit, 0)
                ), 0.0)                                           AS minutes,
                COUNT(DISTINCT so.id) FILTER (
                    WHERE bt.id IS NOT NULL AND bt.has_bom AND bt.operation_count = 0
                )                                                 AS incomplete_orders
            FROM sale_order so
            JOIN sale_order_line sol           ON sol.order_id = so.id
            LEFT JOIN hdk_product_bom_time bt  ON bt.product_id = sol.product_id
            LEFT JOIN shopify_instance_ept si  ON si.id = so.shopify_instance_id
            WHERE so.state IN ('draft','sent','sale','done')
              AND so.{so_col} BETWEEN %s AND %s
              AND sol.display_type IS NULL
            GROUP BY si.id, si.name
            ORDER BY si.id NULLS LAST
            """,
            [df, dt],
        )
        rows = []
        for r in self.env.cr.dictfetchall():
            key = "shopify_%s" % r["instance_id"] if r["instance_id"] else CHANNEL_DIRECT_KEY
            rows.append({
                "key": key,
                "instance_id": r["instance_id"] or False,
                "name": r["channel_name"],
                "kind": "sale",
                "order_count": int(r["order_count"]),
                "order_value": float(r["order_value"]),
                "minutes": float(r["minutes"]),
                "hours": round(float(r["minutes"]) / 60.0, 2),
                "incomplete_orders": int(r["incomplete_orders"]),
            })
        return rows

    # ------------------------------------------------------------------
    # Internal stock transfers, presented as the "Transfers" channel
    # ------------------------------------------------------------------
    @api.model
    def _aggregate_transfers(self, pick_col, df, dt):
        self.env.cr.execute(
            f"""
            SELECT
                COUNT(DISTINCT sp.id) AS transfer_count,
                COALESCE(SUM(
                    sm.product_uom_qty * COALESCE(bt.cost_per_unit, 0)
                ), 0.0)               AS value,
                COALESCE(SUM(
                    sm.product_uom_qty * COALESCE(bt.minutes_per_unit, 0)
                ), 0.0)               AS minutes
            FROM stock_picking sp
            JOIN stock_picking_type spt        ON spt.id = sp.picking_type_id
            JOIN stock_move sm                 ON sm.picking_id = sp.id
            LEFT JOIN hdk_product_bom_time bt  ON bt.product_id = sm.product_id
            WHERE spt.code = 'internal'
              AND sp.state != 'cancel'
              AND sp.{pick_col} BETWEEN %s AND %s
            """,
            [df, dt],
        )
        r = self.env.cr.dictfetchone() or {}
        count = int(r.get("transfer_count") or 0)
        if not count:
            return None
        minutes = float(r.get("minutes") or 0.0)
        return {
            "key": CHANNEL_TRANSFER_KEY,
            "instance_id": False,
            "name": "Transfers",
            "kind": "transfer",
            "order_count": count,
            "order_value": float(r.get("value") or 0.0),
            "minutes": minutes,
            "hours": round(minutes / 60.0, 2),
            "incomplete_orders": 0,
        }

    @api.model
    def _totals(self, rows):
        return {
            "order_count": sum(r["order_count"] for r in rows),
            "order_value": sum(r["order_value"] for r in rows),
            "minutes":     sum(r["minutes"] for r in rows),
            "hours":       round(sum(r["minutes"] for r in rows) / 60.0, 2),
        }

    # ------------------------------------------------------------------
    # Incomplete-BOM exception: SO lines whose product has a BOM with
    # zero operations. These do not roll into minutes — they're flagged.
    # ------------------------------------------------------------------
    @api.model
    def _incomplete_bom_exception(self, so_col, df, dt):
        self.env.cr.execute(
            f"""
            SELECT
                COUNT(DISTINCT so.id)         AS order_count,
                COUNT(DISTINCT sol.product_id) AS product_count
            FROM sale_order so
            JOIN sale_order_line sol           ON sol.order_id = so.id
            JOIN hdk_product_bom_time bt       ON bt.product_id = sol.product_id
            WHERE so.state IN ('draft','sent','sale','done')
              AND so.{so_col} BETWEEN %s AND %s
              AND bt.has_bom = TRUE
              AND bt.operation_count = 0
            """,
            [df, dt],
        )
        r = self.env.cr.dictfetchone() or {}
        return {
            "order_count":   int(r.get("order_count") or 0),
            "product_count": int(r.get("product_count") or 0),
        }

    # ------------------------------------------------------------------
    # Workcenter load: minutes per workcenter so the planner can see
    # the bottleneck across the selected range.
    # ------------------------------------------------------------------
    @api.model
    def _workcenter_load(self, so_col, df, dt):
        self.env.cr.execute(
            f"""
            WITH order_lines AS (
                SELECT
                    sol.product_id,
                    sol.product_uom_qty AS qty
                FROM sale_order so
                JOIN sale_order_line sol ON sol.order_id = so.id
                WHERE so.state IN ('draft','sent','sale','done')
                  AND so.{so_col} BETWEEN %s AND %s
                  AND sol.display_type IS NULL
            ),
            picked_bom AS (
                SELECT DISTINCT ON (pp.id) pp.id AS product_id, b.id AS bom_id
                FROM product_product pp
                JOIN product_template pt ON pt.id = pp.product_tmpl_id
                JOIN mrp_bom b
                  ON (b.product_id = pp.id OR
                      (b.product_id IS NULL AND b.product_tmpl_id = pt.id))
                 AND b.active = TRUE
                ORDER BY pp.id, (b.product_id = pp.id) DESC NULLS LAST,
                         b.sequence, b.id
            )
            SELECT
                wc.id   AS workcenter_id,
                wc.name AS workcenter_name,
                SUM(ol.qty * op.time_cycle_manual) AS minutes
            FROM order_lines ol
            JOIN picked_bom pb               ON pb.product_id = ol.product_id
            JOIN mrp_routing_workcenter op   ON op.bom_id = pb.bom_id
            JOIN mrp_workcenter wc           ON wc.id = op.workcenter_id
            GROUP BY wc.id, wc.name
            ORDER BY minutes DESC NULLS LAST
            LIMIT 15
            """,
            [df, dt],
        )
        return [
            {
                "workcenter_id": r["workcenter_id"],
                "name": r["workcenter_name"],
                "minutes": float(r["minutes"] or 0.0),
                "hours": round(float(r["minutes"] or 0.0) / 60.0, 2),
            }
            for r in self.env.cr.dictfetchall()
        ]

    # ------------------------------------------------------------------
    # Daily trend: production hours required per day across the range.
    # Cap the bin count so an over-wide range doesn't blow up the chart.
    # ------------------------------------------------------------------
    @api.model
    def _daily_trend(self, so_col, df, dt):
        days = (dt.date() - df.date()).days + 1
        bucket = "day"
        if days > 92:
            bucket = "week"
        if days > 730:
            bucket = "month"
        self.env.cr.execute(
            f"""
            SELECT
                date_trunc('{bucket}', so.{so_col})::date AS bucket,
                SUM(sol.product_uom_qty * COALESCE(bt.minutes_per_unit, 0)) AS minutes
            FROM sale_order so
            JOIN sale_order_line sol           ON sol.order_id = so.id
            LEFT JOIN hdk_product_bom_time bt  ON bt.product_id = sol.product_id
            WHERE so.state IN ('draft','sent','sale','done')
              AND so.{so_col} BETWEEN %s AND %s
              AND sol.display_type IS NULL
            GROUP BY bucket
            ORDER BY bucket
            """,
            [df, dt],
        )
        return {
            "bucket": bucket,
            "points": [
                {
                    "date": r["bucket"].isoformat(),
                    "minutes": float(r["minutes"] or 0.0),
                    "hours": round(float(r["minutes"] or 0.0) / 60.0, 2),
                }
                for r in self.env.cr.dictfetchall()
            ],
        }

    # ------------------------------------------------------------------
    # Drilldown: open list view of the SOs (or transfers) backing a
    # channel cell.
    # ------------------------------------------------------------------
    @api.model
    def action_drilldown(self, channel_key, date_type, date_from, date_to,
                          instance_id=False):
        so_col, pick_col = DATE_FIELD_MAP[date_type]
        df, dt = self._parse_range(date_from, date_to)
        if channel_key == CHANNEL_TRANSFER_KEY:
            return {
                "type": "ir.actions.act_window",
                "name": "Transfers",
                "res_model": "stock.picking",
                "view_mode": "tree,form",
                "domain": [
                    ("picking_type_id.code", "=", "internal"),
                    ("state", "!=", "cancel"),
                    (pick_col, ">=", fields.Datetime.to_string(df)),
                    (pick_col, "<=", fields.Datetime.to_string(dt)),
                ],
            }
        domain = [
            ("state", "in", ("draft", "sent", "sale", "done")),
            (so_col, ">=", fields.Datetime.to_string(df)),
            (so_col, "<=", fields.Datetime.to_string(dt)),
        ]
        if instance_id:
            domain.append(("shopify_instance_id", "=", instance_id))
        else:
            domain.append(("shopify_instance_id", "=", False))
        return {
            "type": "ir.actions.act_window",
            "name": "Sales Orders",
            "res_model": "sale.order",
            "view_mode": "tree,form",
            "domain": domain,
        }

    @api.model
    def action_refresh_cache(self):
        self.env["hdk.product.bom.time"].refresh_cache()
        return True
