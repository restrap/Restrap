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
#################################################################################
{
    'name': "Hamdek Website Login Gate",

    'summary': "Control website access: members-only browsing, cart/checkout login rules, and menus hidden from guests—per website.",

    'description': """
        Website Login Gate (Odoo 17)
        =============================

        **hdk_website_login_gate** (with **hdk_website_base**) adds **Hamdek Website Configuration**
        on Website settings so you can require login to browse the storefront, require login for cart
        and checkout, hide selected menus from visitors, and show familiar cart-style notifications for guests.

        Key Features
        ------------
        - **Require login to browse the website** — optional; guests are redirected to sign in (signup, reset password, TOTP, and payment return URLs stay allowed).
        - **Require login to add to cart** — optional; blocked actions return a cart-style warning instead of updating the cart.
        - **Require login to start checkout** — optional; guests are redirected to the cart with a checkout reminder notification.
        - **Menus hidden for visitors** — multi-select website menus that stay hidden until the customer signs in.
        - Depends on **Hamdek Website Base** for the shared settings block other Hamdek website modules can extend.

        Configuration
        ---------------
        1. Install **Hamdek Website Base** and **Hamdek Website Login Gate**.
        2. Open **Settings → Website**, select the website, and open **Hamdek Website Configuration**.
        3. Enable the options you need and pick menus to hide for anonymous users.

        Notes
        -----
        - Checkout restriction uses a redirect to ``/shop/cart`` with a query flag; a small frontend interaction shows the notification.
        - Menu hiding applies through ``website.menu`` visibility for public sessions on your storefront theme.
        - Full-site login redirects visitors to ``/web/login`` (Odoo 17 already uses the classic HTML sign-in form there).
    """,

    'author': "Hamdek",
    'company': 'Hamdek',
    'website': "https://www.hamdek.com",
    'live_test_url': 'https://www.hamdek.com/get-demo?module=hdk_website_login_gate',
    'version': '17.0.2.0.0',
    'category': 'Website/eCommerce',

    'depends': [
        'hdk_website_base',
        'website_sale',
    ],

    'data': [
        'views/res_config_settings_views.xml',
    ],

    'assets': {
        'web.assets_frontend': [
            'hdk_website_login_gate/static/src/interactions/checkout_login_notification.js',
        ],
    },

    'license': 'OPL-1',
    'currency': 'EUR',
    'price': '35.0',
    'support': 'admin@hamdek.com',
    'images': ['static/description/icon.png'],

    'application': False,
    'installable': True,
    'auto_install': False,
}
