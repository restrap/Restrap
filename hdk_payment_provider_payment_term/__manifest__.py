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
    'name': "Hamdek Payment Provider Payment Terms",

    'summary': "Restrict payment acquirers by the contact's payment terms (eCommerce checkout).",

    'description': """
        Payment Provider Payment Terms (Odoo 17)
        ========================================

        **hdk_payment_provider_payment_term** adds an optional **Allowed Payment Terms** field on
        payment providers and filters compatible acquirers during checkout based on the customer
        contact's **Receivables / Payment Terms** (``property_payment_term_id``).

        Key Features
        ------------
        - Many2one on ``payment.provider`` to ``account.payment.term`` for optional restriction.
        - Extends ``_get_compatible_providers`` when ``sale_order_id`` is set so the payment page
          only lists matching providers.
        - Extends the website shop payment transaction controller to reject inconsistent provider ids.

        Configuration
        ---------------
        1. Install **website_sale** and configure payment providers as usual.
        2. For **guests / contacts without** a receivable payment term: only providers with
           **Allowed Payment Terms** left **empty** are shown.
        3. For **contacts with** a payment term *T*: only providers whose **Allowed Payment Terms**
           is set to the **same** term *T* are shown.
        4. Set **Payment Terms** on customer contacts (Receivables) and match provider **Allowed
           Payment Terms** to the same term where that acquirer should be used.

        Notes
        -----
        - Filtering uses the sale order's company for company-dependent payment term properties.
        - The payment form uses the same ``partner_id`` as the standard sale payment flow (e.g. the
          logged-in portal user) when checking terms.
        - Standard **delivery** rules still apply (e.g. Cash on Delivery requires the shipping
          method to allow COD). Other modules (e.g. **website_sale_collect**) may hide certain
          custom providers depending on delivery type.
    """,

    'author': "Hamdek",
    'company': 'Hamdek',
    'website': "https://www.hamdek.com",
    'live_test_url': 'https://www.hamdek.com/get-demo?module=hdk_payment_provider_payment_term',
    'version': '17.0.1.0.0',
    'category': 'Accounting',

    'depends': [
        'website_sale',
        'account',
    ],

    'data': [
        'views/payment_provider_views.xml',
    ],

    'license': 'OPL-1',
    'currency': 'EUR',
    'price': '15.0',
    'support': 'admin@hamdek.com',
    'images': ['static/description/images/thumbnail.gif'],

    'application': False,
    'installable': True,
    'auto_install': False,
}
