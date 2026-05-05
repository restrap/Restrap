# -*- coding: utf-8 -*-
#################################################################################
# Author: Hamdek
# Copyright(c): 2026-TODAY Hamdek
# All Rights Reserved.
#
# License: OPL-1 (Odoo Proprietary License v1.0)
#################################################################################

from odoo import models
from odoo.http import request


class WebsiteMenu(models.Model):
    _inherit = "website.menu"

    def _compute_visible(self):
        super()._compute_visible()
        try:
            req = request
        except RuntimeError:
            return
        if not req or not getattr(req, "env", None):
            return
        if not req.env.user._is_public():
            return
        website = getattr(req, "website", None)
        if not website:
            return
        hidden = website.hdk_menu_hide_public_ids
        if not hidden:
            return
        for menu in self:
            if not menu.is_visible:
                continue
            m = menu.sudo()
            while m:
                if m in hidden:
                    menu.is_visible = False
                    break
                m = m.parent_id
