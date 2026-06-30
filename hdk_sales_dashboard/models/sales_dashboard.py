from datetime import datetime

from odoo import api, fields, models
from odoo.exceptions import UserError

# Same 3-option vocabulary as the production dashboard.
DATE_FIELD_MAP = {
    "delivery":  "commitment_date",
    "effective": "effective_date",
    "scheduled": "date_order",
}

# Shopify channel + Direct/Other (no instance). Sales dashboard has no
# Transfers row; transfers are not sales events.
CHANNEL_DIRECT_KEY = "direct"


class SalesDashboard(models.AbstractModel):
    _name = "hdk.sales.dashboard"
    _description = "Restrap Sales Dashboard Aggregator"

    @api.model
    def _parse_range(self, date_from, date_to):
        if not date_from or not date_to:
            raise UserError("Please select a date range.")
        df = fields.Date.from_string(date_from)
        dt = fields.Date.from_string(date_to)
        if df > dt:
            raise UserError("'From' date cannot be after 'To' date.")
        return (
            datetime.combine(df, datetime.min.time()),
            datetime.combine(dt, datetime.max.time()),
        )

    @api.model
    def get_dashboard(self, date_type, date_from, date_to):
        if date_type not in DATE_FIELD_MAP:
            raise UserError("Unknown date filter '%s'." % date_type)
        so_col = DATE_FIELD_MAP[date_type]
        df, dt = self._parse_range(date_from, date_to)

        channels = self._aggregate_channels(so_col, df, dt)
        totals = self._totals_from(channels)

        currency = self.env.company.currency_id
        return {
            "filters": {
                "date_type": date_type,
                "date_from": date_from,
                "date_to": date_to,
            },
            "channels": channels,
            "totals":   totals,
            "top_products":  self._top_products(so_col, df, dt),
            "top_customers": self._top_customers(so_col, df, dt),
            "daily_trend":   self._daily_trend(so_col, df, dt),
            "new_vs_repeat": self._new_vs_repeat(so_col, df, dt),
            "refunds":       self._refund_stats(so_col, df, dt),
            "currency": {"symbol": currency.symbol, "position": currency.position},
        }

    # ------------------------------------------------------------------
    # Channel breakdown — the headline table.
    # Wraps every row metric in COALESCE so an empty channel still
    # produces a numeric zero, not NULL.
    # ------------------------------------------------------------------
    @api.model
    def _aggregate_channels(self, so_col, df, dt):
        self.env.cr.execute(
            f"""
            WITH so_in_range AS (
                SELECT
                    so.id,
                    so.partner_id,
                    so.amount_total,
                    so.date_order,
                    so.effective_date,
                    so.shopify_instance_id,
                    EXTRACT(EPOCH FROM (so.effective_date - so.date_order))
                        / 86400.0 AS fulfill_days
                FROM sale_order so
                WHERE so.state IN ('sale','done')
                  AND so.{so_col} BETWEEN %s AND %s
            ),
            so_minutes AS (
                SELECT
                    sol.order_id AS id,
                    SUM(sol.product_uom_qty * COALESCE(bt.minutes_per_unit, 0)) AS minutes
                FROM sale_order_line sol
                JOIN so_in_range r ON r.id = sol.order_id
                LEFT JOIN hdk_product_bom_time bt ON bt.product_id = sol.product_id
                WHERE sol.display_type IS NULL
                GROUP BY sol.order_id
            ),
            so_cash AS (
                -- account_move_line.payment_date is non-stored in v17,
                -- so we walk the reconcile graph instead. max_date is
                -- the stored reconciliation date and equals the
                -- effective settlement date for that pair.
                SELECT
                    am.invoice_origin AS so_name,
                    MAX(apr.max_date) AS paid_at
                FROM account_move am
                JOIN account_move_line aml         ON aml.move_id = am.id
                JOIN account_partial_reconcile apr
                     ON apr.debit_move_id = aml.id
                     OR apr.credit_move_id = aml.id
                WHERE am.move_type = 'out_invoice'
                  AND am.state = 'posted'
                  AND am.payment_state IN ('paid','in_payment')
                GROUP BY am.invoice_origin
            ),
            so_enriched AS (
                SELECT
                    r.*,
                    COALESCE(sm.minutes, 0) AS minutes,
                    EXTRACT(EPOCH FROM (sc.paid_at - r.date_order::date))
                        / 86400.0 AS cash_days
                FROM so_in_range r
                LEFT JOIN so_minutes sm ON sm.id = r.id
                LEFT JOIN sale_order so ON so.id = r.id
                LEFT JOIN so_cash sc    ON sc.so_name = so.name
            )
            SELECT
                COALESCE(si.id, 0)                AS instance_id,
                COALESCE(si.name, 'Direct / Other') AS channel_name,
                COUNT(*)                          AS order_count,
                COALESCE(SUM(amount_total), 0)    AS revenue,
                COALESCE(AVG(amount_total), 0)    AS aov,
                AVG(fulfill_days)                 AS avg_fulfill_days,
                AVG(cash_days)                    AS avg_cash_days,
                AVG(minutes)                      AS avg_minutes
            FROM so_enriched e
            LEFT JOIN shopify_instance_ept si ON si.id = e.shopify_instance_id
            GROUP BY si.id, si.name
            ORDER BY si.id NULLS LAST
            """,
            [df, dt],
        )
        rows = []
        for r in self.env.cr.dictfetchall():
            instance_id = r["instance_id"] or False
            avg_minutes = float(r["avg_minutes"] or 0.0)
            rows.append({
                "key": "shopify_%s" % instance_id if instance_id else CHANNEL_DIRECT_KEY,
                "instance_id": instance_id,
                "name": r["channel_name"],
                "order_count": int(r["order_count"]),
                "revenue": float(r["revenue"] or 0.0),
                "aov":     float(r["aov"] or 0.0),
                "avg_fulfill_days": _safe_round(r["avg_fulfill_days"], 2),
                "avg_cash_days":    _safe_round(r["avg_cash_days"], 2),
                "avg_minutes_per_order": round(avg_minutes, 1),
                "avg_hours_per_order":   round(avg_minutes / 60.0, 2),
            })
        return rows

    @api.model
    def _totals_from(self, rows):
        if not rows:
            return {
                "order_count": 0, "revenue": 0.0, "aov": 0.0,
                "avg_fulfill_days": None, "avg_cash_days": None,
                "avg_minutes_per_order": 0.0, "avg_hours_per_order": 0.0,
            }
        orders  = sum(r["order_count"] for r in rows)
        revenue = sum(r["revenue"] for r in rows)
        return {
            "order_count": orders,
            "revenue": revenue,
            "aov": (revenue / orders) if orders else 0.0,
            # Weighted averages so an outlier channel doesn't dominate.
            "avg_fulfill_days": _weighted(
                rows, "avg_fulfill_days", "order_count", 2
            ),
            "avg_cash_days": _weighted(
                rows, "avg_cash_days", "order_count", 2
            ),
            "avg_minutes_per_order": _weighted(
                rows, "avg_minutes_per_order", "order_count", 1
            ),
            "avg_hours_per_order": _weighted(
                rows, "avg_hours_per_order", "order_count", 2
            ),
        }

    # ------------------------------------------------------------------
    # Top products by units sold + revenue.
    # ------------------------------------------------------------------
    @api.model
    def _top_products(self, so_col, df, dt):
        self.env.cr.execute(
            f"""
            SELECT
                pt.id   AS template_id,
                pt.name AS name,
                SUM(sol.product_uom_qty)            AS units,
                SUM(sol.price_subtotal)             AS revenue
            FROM sale_order so
            JOIN sale_order_line sol ON sol.order_id = so.id
            JOIN product_product pp  ON pp.id = sol.product_id
            JOIN product_template pt ON pt.id = pp.product_tmpl_id
            WHERE so.state IN ('sale','done')
              AND so.{so_col} BETWEEN %s AND %s
              AND sol.display_type IS NULL
            GROUP BY pt.id, pt.name
            ORDER BY units DESC NULLS LAST
            LIMIT 10
            """,
            [df, dt],
        )
        out = []
        for r in self.env.cr.dictfetchall():
            name = r["name"]
            if isinstance(name, dict):
                name = name.get(self.env.user.lang) or next(iter(name.values()), "")
            out.append({
                "template_id": r["template_id"],
                "name": name,
                "units": float(r["units"] or 0.0),
                "revenue": float(r["revenue"] or 0.0),
            })
        return out

    # ------------------------------------------------------------------
    # Top customers by revenue.
    # ------------------------------------------------------------------
    @api.model
    def _top_customers(self, so_col, df, dt):
        self.env.cr.execute(
            f"""
            SELECT
                rp.id   AS partner_id,
                rp.name AS name,
                COUNT(so.id)                        AS order_count,
                SUM(so.amount_total)                AS revenue
            FROM sale_order so
            JOIN res_partner rp ON rp.id = so.partner_id
            WHERE so.state IN ('sale','done')
              AND so.{so_col} BETWEEN %s AND %s
            GROUP BY rp.id, rp.name
            ORDER BY revenue DESC NULLS LAST
            LIMIT 10
            """,
            [df, dt],
        )
        return [
            {
                "partner_id": r["partner_id"],
                "name": r["name"],
                "order_count": int(r["order_count"]),
                "revenue": float(r["revenue"] or 0.0),
            }
            for r in self.env.cr.dictfetchall()
        ]

    # ------------------------------------------------------------------
    # Daily trend: orders + revenue per bucket. Same bucket-sizing rule
    # as the production dashboard.
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
                COUNT(so.id) AS orders,
                SUM(so.amount_total) AS revenue
            FROM sale_order so
            WHERE so.state IN ('sale','done')
              AND so.{so_col} BETWEEN %s AND %s
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
                    "orders": int(r["orders"]),
                    "revenue": float(r["revenue"] or 0.0),
                }
                for r in self.env.cr.dictfetchall()
            ],
        }

    # ------------------------------------------------------------------
    # New vs repeat customers per channel.
    # "New" = the customer's first-ever SO falls within the range.
    # ------------------------------------------------------------------
    @api.model
    def _new_vs_repeat(self, so_col, df, dt):
        self.env.cr.execute(
            f"""
            WITH first_order AS (
                SELECT
                    partner_id,
                    MIN(date_order) AS first_dt
                FROM sale_order
                WHERE state IN ('sale','done')
                GROUP BY partner_id
            ),
            tagged AS (
                SELECT
                    so.id,
                    so.partner_id,
                    so.amount_total,
                    COALESCE(si.id, 0)               AS instance_id,
                    COALESCE(si.name, 'Direct / Other') AS channel_name,
                    CASE
                        WHEN fo.first_dt >= %s AND fo.first_dt <= %s
                            THEN 'new'
                        ELSE 'repeat'
                    END AS bucket
                FROM sale_order so
                JOIN first_order fo ON fo.partner_id = so.partner_id
                LEFT JOIN shopify_instance_ept si ON si.id = so.shopify_instance_id
                WHERE so.state IN ('sale','done')
                  AND so.{so_col} BETWEEN %s AND %s
            )
            SELECT
                channel_name,
                instance_id,
                bucket,
                COUNT(DISTINCT partner_id) AS customers,
                COUNT(*)                   AS orders,
                SUM(amount_total)          AS revenue
            FROM tagged
            GROUP BY channel_name, instance_id, bucket
            ORDER BY instance_id NULLS LAST, bucket
            """,
            [df, dt, df, dt],
        )
        # Pivot into one row per channel with new/repeat columns.
        per_channel = {}
        for r in self.env.cr.dictfetchall():
            key = r["instance_id"] or 0
            if key not in per_channel:
                per_channel[key] = {
                    "instance_id": r["instance_id"] or False,
                    "name": r["channel_name"],
                    "new": {"customers": 0, "orders": 0, "revenue": 0.0},
                    "repeat": {"customers": 0, "orders": 0, "revenue": 0.0},
                }
            per_channel[key][r["bucket"]] = {
                "customers": int(r["customers"]),
                "orders":    int(r["orders"]),
                "revenue":   float(r["revenue"] or 0.0),
            }
        return list(per_channel.values())

    # ------------------------------------------------------------------
    # Refund stats: credit notes raised within the range.
    # ------------------------------------------------------------------
    @api.model
    def _refund_stats(self, so_col, df, dt):
        self.env.cr.execute(
            """
            SELECT
                COUNT(*)                AS refund_count,
                COALESCE(SUM(amount_total), 0) AS refund_value
            FROM account_move
            WHERE move_type = 'out_refund'
              AND state = 'posted'
              AND date BETWEEN %s::date AND %s::date
            """,
            [df, dt],
        )
        r = self.env.cr.dictfetchone() or {}
        # Compare against orders in range.
        self.env.cr.execute(
            f"""
            SELECT COUNT(*) AS c, COALESCE(SUM(amount_total), 0) AS v
            FROM sale_order
            WHERE state IN ('sale','done')
              AND {so_col} BETWEEN %s AND %s
            """,
            [df, dt],
        )
        s = self.env.cr.dictfetchone() or {"c": 0, "v": 0}
        order_count = int(s["c"] or 0)
        return {
            "refund_count": int(r.get("refund_count") or 0),
            "refund_value": float(r.get("refund_value") or 0.0),
            "refund_rate_pct": (
                round((int(r.get("refund_count") or 0) / order_count) * 100.0, 2)
                if order_count else 0.0
            ),
        }

    # ------------------------------------------------------------------
    # Drilldown to SO list view.
    # ------------------------------------------------------------------
    @api.model
    def action_drilldown(self, channel_key, date_type, date_from, date_to,
                          instance_id=False):
        so_col = DATE_FIELD_MAP[date_type]
        df, dt = self._parse_range(date_from, date_to)
        domain = [
            ("state", "in", ("sale", "done")),
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


def _safe_round(value, ndigits):
    if value is None:
        return None
    return round(float(value), ndigits)


def _weighted(rows, value_key, weight_key, ndigits):
    """Weighted average across rows, ignoring rows where value is None."""
    num = 0.0
    den = 0.0
    for r in rows:
        v = r.get(value_key)
        w = r.get(weight_key) or 0
        if v is None or w == 0:
            continue
        num += float(v) * w
        den += w
    if not den:
        return None
    return round(num / den, ndigits)
