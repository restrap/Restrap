# -*- coding: utf-8 -*-
#################################################################################
# Author: Hamdek
# Copyright(c): 2026-TODAY Hamdek
# All Rights Reserved.
#
# License: OPL-1 (Odoo Proprietary License v1.0)
#################################################################################

from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    hdk_menu_hide_public_ids = fields.Many2many(
        related="website_id.hdk_menu_hide_public_ids",
        readonly=False,
    )

    hdk_login_required_add_to_cart = fields.Boolean(
        related="website_id.hdk_login_required_add_to_cart",
        readonly=False,
    )
    hdk_login_required_checkout = fields.Boolean(
        related="website_id.hdk_login_required_checkout",
        readonly=False,
    )
    hdk_login_required_website = fields.Boolean(
        related="website_id.hdk_login_required_website",
        readonly=False,
    )
