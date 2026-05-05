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

from odoo import models


class SaleOrder(models.Model):
    _inherit = "sale.order"

    def _get_delivery_methods(self):
        """Only offer the contact's selected delivery method when that standard field is set;
        otherwise return the same carrier list as the parent implementation.
        """
        carriers = super()._get_delivery_methods()
        self.ensure_one()
        partner = self.partner_id.commercial_partner_id
        company = self.company_id
        selected = partner.with_company(company).property_delivery_carrier_id
        if not selected:
            return carriers
        return carriers.filtered(lambda c: c.id == selected.id)
