from datetime import datetime, timedelta

import pytz

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
        # Interpret picked dates as the user's local day, then convert to
        # naive UTC for the SQL comparisons (datetimes are stored UTC).
        # Without this, a UK user picking 2023-08-17 misses SOs placed at
        # 2023-08-16 23:11 UTC (= 00:11 BST on 2023-08-17).
        tzname = self.env.context.get("tz") or self.env.user.tz or "UTC"
        user_tz = pytz.timezone(tzname)
        local_start = user_tz.localize(datetime.combine(df, datetime.min.time()))
        local_end = user_tz.localize(datetime.combine(dt, datetime.max.time()))
        return (
            local_start.astimezone(pytz.UTC).replace(tzinfo=None),
            local_end.astimezone(pytz.UTC).replace(tzinfo=None),
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
        # Two SQL passes:
        #   1. Per-SO snapshot from sale_order alone — one row per order —
        #      so amount_total is not multiplied by the number of lines and
        #      each order's own currency + date is available for conversion.
        #   2. Per-instance minutes + incomplete flag from the sale_order_line
        #      join — line-level rollups belong here.
        # We aggregate in Python so amounts can be summed in the SO's native
        # currency (per Shopify instance) and, in parallel, converted to the
        # company currency for the grand-totals row.
        #
        # Excludes cancelled SOs. Includes draft+sent+sale+done so the same
        # row makes sense whether the user looks forward (planned production)
        # or backward (delivered).
        self.env.cr.execute(
            f"""
            SELECT
                so.id,
                COALESCE(so.shopify_instance_id, 0) AS instance_id,
                so.amount_total,
                so.currency_id,
                so.company_id,
                so.date_order
            FROM sale_order so
            WHERE so.state IN ('draft','sent','sale','done')
              AND so.{so_col} BETWEEN %s AND %s
            """,
            [df, dt],
        )
        so_rows = self.env.cr.dictfetchall()

        self.env.cr.execute(
            f"""
            SELECT
                COALESCE(so.shopify_instance_id, 0) AS instance_id,
                COALESCE(SUM(
                    sol.product_uom_qty * COALESCE(bt.minutes_per_unit, 0)
                ), 0.0) AS minutes,
                COUNT(DISTINCT so.id) FILTER (
                    WHERE bt.id IS NOT NULL AND bt.has_bom AND bt.operation_count = 0
                ) AS incomplete_orders
            FROM sale_order so
            JOIN sale_order_line sol           ON sol.order_id = so.id
            LEFT JOIN hdk_product_bom_time bt  ON bt.product_id = sol.product_id
            WHERE so.state IN ('draft','sent','sale','done')
              AND so.{so_col} BETWEEN %s AND %s
              AND sol.display_type IS NULL
            GROUP BY so.shopify_instance_id
            """,
            [df, dt],
        )
        minutes_by_inst = {r["instance_id"]: r for r in self.env.cr.dictfetchall()}

        Currency = self.env["res.currency"]
        Company = self.env["res.company"]
        company_currency = self.env.company.currency_id

        # Cache Shopify instance names
        inst_ids = {r["instance_id"] for r in so_rows if r["instance_id"]}
        inst_name_by_id = {}
        if inst_ids and "shopify.instance.ept" in self.env:
            for si in self.env["shopify.instance.ept"].browse(list(inst_ids)):
                inst_name_by_id[si.id] = si.name

        # Aggregate per instance
        buckets = {}
        for r in so_rows:
            inst_id = r["instance_id"] or 0
            b = buckets.setdefault(inst_id, {
                "order_count": 0,
                "native_by_currency": {},  # currency_id -> sum
                "value_company": 0.0,
            })
            b["order_count"] += 1
            amount = r["amount_total"] or 0.0
            cur_id = r["currency_id"]
            b["native_by_currency"][cur_id] = (
                b["native_by_currency"].get(cur_id, 0.0) + amount
            )
            if cur_id and cur_id != company_currency.id:
                from_cur = Currency.browse(cur_id)
                company = Company.browse(r["company_id"]) if r["company_id"] else self.env.company
                b["value_company"] += from_cur._convert(
                    amount, company_currency, company,
                    r["date_order"] or df, round=False,
                )
            else:
                b["value_company"] += amount

        rows = []
        for inst_id, b in buckets.items():
            m = minutes_by_inst.get(inst_id, {})
            minutes = float(m.get("minutes") or 0.0)
            if inst_id:
                name = inst_name_by_id.get(inst_id) or f"Shopify {inst_id}"
                key = f"shopify_{inst_id}"
            else:
                name = "Direct / Other"
                key = CHANNEL_DIRECT_KEY

            # Row displays in native currency when the instance's orders all
            # share one currency (typical Shopify-per-region setup). If mixed,
            # fall back to company-currency and mark accordingly.
            native = b["native_by_currency"]
            if len(native) == 1:
                cur_id, native_amount = next(iter(native.items()))
                cur = Currency.browse(cur_id) if cur_id else company_currency
                display_amount = native_amount
                display_symbol = cur.symbol or ""
                display_position = cur.position or "before"
                currency_mixed = False
            else:
                display_amount = b["value_company"]
                display_symbol = company_currency.symbol or ""
                display_position = company_currency.position or "before"
                currency_mixed = True

            rows.append({
                "key": key,
                "instance_id": inst_id or False,
                "name": name,
                "kind": "sale",
                "order_count": b["order_count"],
                "order_value": round(display_amount, 2),
                "order_value_company": round(b["value_company"], 2),
                "currency_symbol": display_symbol,
                "currency_position": display_position,
                "currency_mixed": currency_mixed,
                "minutes": minutes,
                "hours": round(minutes / 60.0, 2),
                "incomplete_orders": int(m.get("incomplete_orders") or 0),
            })
        rows.sort(key=lambda r: (r["instance_id"] is False, r["instance_id"] or 0))
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
        value = float(r.get("value") or 0.0)
        company_currency = self.env.company.currency_id
        return {
            "key": CHANNEL_TRANSFER_KEY,
            "instance_id": False,
            "name": "Transfers",
            "kind": "transfer",
            "order_count": count,
            "order_value": round(value, 2),
            "order_value_company": round(value, 2),
            "currency_symbol": company_currency.symbol or "",
            "currency_position": company_currency.position or "before",
            "currency_mixed": False,
            "minutes": minutes,
            "hours": round(minutes / 60.0, 2),
            "incomplete_orders": 0,
        }

    @api.model
    def _totals(self, rows):
        # Grand-total row is always in company currency — that is the only
        # meaningful sum across channels that may hold different currencies.
        return {
            "order_count": sum(r["order_count"] for r in rows),
            "order_value": round(sum(r.get("order_value_company") or 0.0 for r in rows), 2),
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
        # Views must be passed as an explicit list. When the webclient
        # receives a raw act_window dict via RPC it does not synthesise
        # views from view_mode in all code paths, so an action with only
        # view_mode="tree,form" trips a `Cannot read properties of
        # undefined (reading 'map')` when the list view mounts.
        if channel_key == CHANNEL_TRANSFER_KEY:
            return {
                "type": "ir.actions.act_window",
                "name": "Transfers",
                "res_model": "stock.picking",
                "view_mode": "list,form",
                "views": [[False, "list"], [False, "form"]],
                "target": "current",
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
            "view_mode": "list,form",
            "views": [[False, "list"], [False, "form"]],
            "target": "current",
            "domain": domain,
        }

    @api.model
    def action_refresh_cache(self):
        self.env["hdk.product.bom.time"].refresh_cache()
        return True
