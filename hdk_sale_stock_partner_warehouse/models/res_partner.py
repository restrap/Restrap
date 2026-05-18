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

from odoo import fields, models


class ResPartner(models.Model):
    _inherit = "res.partner"

    sale_warehouse_id = fields.Many2one(
        "stock.warehouse", string="Sale Warehouse", company_dependent=True
    )
