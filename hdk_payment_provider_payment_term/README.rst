===================================
Hamdek Payment Provider Payment Terms
===================================

This module links **payment providers (acquirers)** to **customer payment terms**. During **eCommerce checkout** (and any sale-order payment context that passes ``sale_order_id`` to the payment engine), providers are shown using **symmetric** rules (see below). It also blocks creating a shop payment transaction with a non-allowed provider if the request is tampered with.

Usage
-----
* On the **contact**, set **Receivables** → **Payment Terms** (``property_payment_term_id``) as usual.
* Open **Website → Configuration → Payment Providers** (or **Accounting → Configuration → Payment Providers**, depending on menus).
* Edit a provider: under **Configuration → Availability**, set **Allowed Payment Terms** to the same term as the customers who should use this acquirer.

Behavior summary
------------------
* Contact **without** a payment term: only providers that have **no** “Allowed Payment Terms” (empty) are shown.
* Contact **with** payment term **T**: only providers whose “Allowed Payment Terms” is **exactly T** are shown (unrestricted/empty providers are **not** shown).
* The commercial partner and **order company** are used when reading ``property_payment_term_id`` (company-dependent field).

Why a payment method (e.g. Cash on Delivery) may still not appear
-------------------------------------------------------------------
* **This module:** If the contact has a receivable payment term, a provider with an **empty** “Allowed Payment Terms” is **not** shown. Set “Allowed Payment Terms” on that provider to the **same** term as the contact, or adjust the contact, if you need COD and card rules to line up.
* **Standard Odoo (``delivery``):** Cash on Delivery is only offered when the **selected delivery/shipping method** has **Allow Cash on Delivery** enabled. Publishing the payment provider is not enough; check **Inventory / Configuration / Delivery Methods** (the carrier on the order).
* **``website_sale_collect`` (if installed):** “Pay on site” custom providers are hidden unless the order uses **pick up in store** delivery and the cart has deliverable products (see Odoo’s ``website_sale_collect`` payment provider logic).

Requirements
------------
* **website_sale** (eCommerce checkout; brings **sale**, **website_payment**, **payment**, **account_payment**, **account**).

Validation
----------
* Shop checkout creates transactions through an extended controller so a forged ``provider_id`` cannot bypass the rule.

Author
------
* Hamdek (https://www.hamdek.com)

License
-------
OPL-1 (Odoo Proprietary License v1.0)
