from odoo import api, fields, models


class ProductBomTime(models.Model):
    """Cached per-product BOM operation time, in minutes per unit.

    The dashboard aggregates over tens of thousands of order/transfer lines,
    so resolving the BOM and summing operations on every page load is too slow.
    This cache is the precomputed table the dashboard SQL joins against.
    Refresh happens (1) on module install, (2) nightly via ir.cron, and
    (3) on demand via the dashboard Refresh button.
    """

    _name = "hdk.product.bom.time"
    _description = "Cached BOM operation time per product"
    _rec_name = "product_id"

    product_id = fields.Many2one(
        "product.product", required=True, ondelete="cascade", index=True
    )
    minutes_per_unit = fields.Float(
        string="Minutes / Unit",
        digits=(12, 4),
        help="Sum of all BOM operation manual durations for the resolved BOM.",
    )
    operation_count = fields.Integer()
    has_bom = fields.Boolean(
        help="False = no BOM at all (e.g. purchased item). "
        "True with zero operations = BOM exists but is incomplete."
    )
    cost_per_unit = fields.Float(
        digits=(12, 4),
        help="Snapshot of product standard_price for the company that ran "
        "the refresh. Lives here because standard_price is company_dependent "
        "and non-stored, so we can't join it from SQL.",
    )
    last_computed = fields.Datetime()

    _sql_constraints = [
        ("uniq_product", "unique(product_id)", "One cache row per product."),
    ]

    @api.model
    def refresh_cache(self):
        """Recompute the cache for every storable product.

        Strategy: one SQL pass that joins product → BOM → operations and
        sums time_cycle_manual. We pick the *first* applicable BOM per
        product (lowest sequence, lowest id) to match Odoo's _bom_find
        default selection for make-to-stock orders.
        """
        self.env.cr.execute(
            """
            WITH ranked_bom AS (
                SELECT
                    pp.id AS product_id,
                    b.id  AS bom_id,
                    ROW_NUMBER() OVER (
                        PARTITION BY pp.id
                        ORDER BY (b.product_id = pp.id) DESC NULLS LAST,
                                 b.sequence, b.id
                    ) AS rn
                FROM product_product pp
                JOIN product_template pt ON pt.id = pp.product_tmpl_id
                LEFT JOIN mrp_bom b
                       ON (b.product_id = pp.id OR
                           (b.product_id IS NULL AND b.product_tmpl_id = pt.id))
                      AND b.active = TRUE
                WHERE pt.active = TRUE
            ),
            picked AS (
                SELECT product_id, bom_id FROM ranked_bom WHERE rn = 1
            ),
            op_sum AS (
                SELECT
                    p.product_id,
                    p.bom_id,
                    COALESCE(SUM(op.time_cycle_manual), 0.0) AS minutes,
                    COUNT(op.id) AS op_count
                FROM picked p
                LEFT JOIN mrp_routing_workcenter op ON op.bom_id = p.bom_id
                GROUP BY p.product_id, p.bom_id
            )
            INSERT INTO hdk_product_bom_time
                (product_id, minutes_per_unit, operation_count,
                 has_bom, last_computed,
                 create_uid, create_date, write_uid, write_date)
            SELECT
                product_id,
                minutes,
                op_count,
                (bom_id IS NOT NULL),
                NOW() AT TIME ZONE 'UTC',
                %(uid)s, NOW() AT TIME ZONE 'UTC',
                %(uid)s, NOW() AT TIME ZONE 'UTC'
            FROM op_sum
            ON CONFLICT (product_id) DO UPDATE SET
                minutes_per_unit = EXCLUDED.minutes_per_unit,
                operation_count  = EXCLUDED.operation_count,
                has_bom          = EXCLUDED.has_bom,
                last_computed    = EXCLUDED.last_computed,
                write_uid        = EXCLUDED.write_uid,
                write_date       = EXCLUDED.write_date
            """,
            {"uid": self.env.uid},
        )
        self._refresh_cost_snapshot()
        return True

    def _refresh_cost_snapshot(self):
        """Snapshot standard_price per product into the cache.

        Done via ORM rather than SQL because standard_price is
        company_dependent + non-stored, so it isn't a real column on
        product_product. Batched to keep memory flat.
        """
        Product = self.env["product.product"]
        product_ids = Product.search([]).ids
        BATCH = 1000
        for offset in range(0, len(product_ids), BATCH):
            chunk = Product.browse(product_ids[offset:offset + BATCH])
            cost_by_id = {p.id: p.standard_price or 0.0 for p in chunk}
            if not cost_by_id:
                continue
            # Single UPDATE per chunk via VALUES list.
            args = []
            values_sql = []
            for pid, cost in cost_by_id.items():
                values_sql.append("(%s, %s)")
                args.extend([pid, cost])
            self.env.cr.execute(
                f"""
                UPDATE hdk_product_bom_time AS t
                SET cost_per_unit = v.cost
                FROM (VALUES {",".join(values_sql)}) AS v(pid, cost)
                WHERE t.product_id = v.pid
                """,
                args,
            )
