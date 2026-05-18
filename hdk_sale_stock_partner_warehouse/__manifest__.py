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
{
    "name": "Partner Based Warehouse",

    "summary": "Default sales warehouse from the customer (and optional shipping address) on quotations and orders.",

    "description": """
        Sale Stock Partner Warehouse (Odoo 17)
        ======================================

        **hdk_sale_stock_partner_warehouse** sets the **default warehouse** on **sales orders**
        from a **warehouse field on the customer** (and optionally from the **delivery address**).
        If no partner warehouse is set, Odoo keeps its **usual default** warehouse behaviour.

        Key points
        ----------
        - Per-contact **Sale warehouse** (company-dependent, like standard Odoo patterns).
        - Optional company setting to **prefer the shipping partner’s** warehouse first, then the main customer.
        - Applies while the order is in **draft**; confirmed orders follow normal Odoo rules.

        Configuration
        ---------------
        1. Install the module (requires **Sales** and **Inventory** with **Sale Stock**).
        2. On a customer, set **Sale warehouse** if they should always ship from a specific warehouse.
        3. Optionally enable **Prioritize Shipping Partner in Sale Warehouse Proposal** under
           **Sales → Configuration → Settings**.
    """,

    "author": "Hamdek",
    "company": "Hamdek",
    "website": "https://www.hamdek.com",
    "live_test_url": "https://www.hamdek.com/get-demo?module=hdk_sale_stock_partner_warehouse",
    "version": "17.0.1.1.0",
    "category": "Sales/Inventory",

    "depends": [
        "sale_stock",
    ],

    "data": [
        "views/partner_view.xml",
        "views/res_config_settings_views.xml",
    ],

    "license": "OPL-1",
    "currency": "EUR",
    "price": "10.0",
    "support": "admin@hamdek.com",
    "images": ["static/description/icon.png"],

    "application": False,
    "installable": True,
    "auto_install": False,
}
