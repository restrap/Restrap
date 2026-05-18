# -*- coding: utf-8 -*-
#################################################################################
# Author: Hamdek
# Copyright(c): 2026-TODAY Hamdek
# All Rights Reserved.
#
# This program is copyright property of the author mentioned above.
# You can`t redistribute it and/or modify it.
#
# You should have received a copy of the License along with this program.
#
# License: OPL-1 (Odoo Proprietary License v1.0)
#################################################################################

from odoo import api, models


class SaleOrder(models.Model):
    _inherit = "sale.order"

    @api.depends("partner_id", "partner_shipping_id")
    def _compute_warehouse_id(self):
        draft_orders = self.filtered(lambda s: s.state == "draft")
        to_super = self - draft_orders
        for sale in draft_orders:
            warehouse = False
            if sale.company_id.sale_warehouse_by_partner_shipping:
                warehouse = sale.partner_shipping_id.sale_warehouse_id
            warehouse = warehouse or sale.partner_id.sale_warehouse_id
            if warehouse:
                sale.warehouse_id = warehouse
                continue
            to_super |= sale
        if to_super:
            return super(SaleOrder, to_super)._compute_warehouse_id()
