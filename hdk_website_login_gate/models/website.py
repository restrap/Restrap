# -*- coding: utf-8 -*-
#################################################################################
# Author: Hamdek
# Copyright(c): 2026-TODAY Hamdek
# All Rights Reserved.
#
# License: OPL-1 (Odoo Proprietary License v1.0)
#################################################################################

from odoo import api, fields, models
from odoo.exceptions import ValidationError
from odoo.tools.translate import _


class Website(models.Model):
    _inherit = "website"

    hdk_menu_hide_public_ids = fields.Many2many(
        comodel_name="website.menu",
        relation="website_hdk_hide_menu_public_rel",
        column1="website_id",
        column2="menu_id",
        string="Hide menus from visitors",
        help="Selected menus are not shown to logged-out visitors. "
        "If you hide a parent menu, its submenus are hidden too.",
    )

    hdk_login_required_add_to_cart = fields.Boolean(
        string="Require login to add to cart",
        default=False,
        help="When enabled, visitors must sign in before adding products or updating the cart.",
    )
    hdk_login_required_checkout = fields.Boolean(
        string="Require login to start checkout",
        default=False,
        help="When enabled, guests who open checkout see a sign-in page until they authenticate.",
    )
    hdk_login_required_website = fields.Boolean(
        string="Require login to browse the website",
        default=False,
        help="When enabled, visitors cannot open any storefront page until they sign in. "
        "Sign-in (/web/login), account creation, password reset, login MFA under /web/login/, "
        "and payment return URLs stay allowed.",
    )

    @api.constrains("hdk_menu_hide_public_ids")
    def _check_hdk_hide_menus_for_website(self):
        for website in self:
            bad = website.hdk_menu_hide_public_ids.filtered(
                lambda m: m.website_id and m.website_id != website
            )
            if bad:
                raise ValidationError(
                    _("Menus hidden for visitors must belong to this website (%s).", website.name)
                )
