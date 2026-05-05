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
    "name": "Hamdek Partner Delivery Method",

    "summary": "Online shop: only show the customer’s selected delivery method at checkout.",

    "description": """
        Partner Delivery Method (Odoo 19)
        ==================================

        **hdk_partner_delivery_method** uses the standard **Delivery Method** field on the
        customer contact. When it is set, the website checkout and related shop flows only list
        that shipping method (if it is otherwise available for the order). When it is empty, all
        standard eligible methods are shown.

        Key points
        ----------
        - No new fields: uses **Inventory / Shipping** delivery method on the contact.
        - Filters the list returned for the web shop cart and express checkout the same way.
        - Respects company-dependent values on the partner.

        Configuration
        ---------------
        1. Install the module (requires **eCommerce** and **Delivery**).
        2. On a customer contact, set **Delivery Method** to the carrier that customer may use.
        3. Test checkout: only that method should appear when the field is set.
    """,

    "author": "Hamdek",
    "company": "Hamdek",
    "website": "https://www.hamdek.com",
    "live_test_url": "https://www.hamdek.com/get-demo?module=hdk_partner_delivery_method",
    "version": "17.0.1.0.0",
    "category": "Website/eCommerce",

    "depends": [
        "website_sale",
        "delivery",
    ],

    "data": [],

    "license": "OPL-1",
    "currency": "EUR",
    "price": "10.0",
    "support": "admin@hamdek.com",
    "images": ["static/description/images/thumbnail.gif"],

    "application": False,
    "installable": True,
    "auto_install": False,
}
