===================================
Hamdek Partner Delivery Method
===================================

When a **Delivery Method** is set on a **customer contact** (standard Odoo field on the partner), the **online shop checkout** only offers **that** shipping method—provided it is still valid for the order (published, company, products, and so on). If the field is **empty**, checkout behaves like standard Odoo and shows all suitable methods.

Usage
-----
* Open the **customer** (contact) in the backend.
* Set **Delivery Method** to the carrier that customer is allowed to use (per company, as in standard Odoo).
* On the **website**, go through checkout with that customer: only the matching method should appear in the delivery options.

If no method appears, check that the selected carrier is **published** on the website, matches the **company**, and passes the usual rules (weight, country, etc.).

Requirements
------------
* **website_sale**
* **delivery**

Behaviour notes
---------------
* The restriction uses the **ordering customer** on the sale order (commercial partner).
* Standard delivery rules (availability for the order, rates, click & collect, etc.) still apply before the contact filter.

Author
------
* Hamdek (https://www.hamdek.com)

License
-------
OPL-1 (Odoo Proprietary License v1.0)
