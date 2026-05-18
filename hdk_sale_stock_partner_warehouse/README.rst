=====================================
Hamdek Sale Stock Partner Warehouse
=====================================

Set the **default warehouse** on **sales orders** from a **Sale warehouse** field on the **customer**
(and optionally prefer the **delivery address** warehouse when your company enables that option).
If the partner fields are empty, the order uses the **standard default warehouse** for the company.

Usage
-----
* Open the **customer** (contact) and set **Sale warehouse** for each company where it applies.
* Create a **quotation**: the warehouse should default from that partner (for draft orders).
* To prioritise the **shipping address** contact’s warehouse first: **Sales → Configuration → Settings**
  → enable **Prioritize Shipping Partner in Sale Warehouse Proposal**.

You need at least **two warehouses** configured to see a meaningful difference between defaults.

Requirements
------------
* **sale_stock**

Behaviour notes
---------------
* Warehouse default is recomputed from **partner** and **partner shipping** while the sale order is **draft**.
* Other Odoo rules (multi-company, user rights, etc.) still apply.

Author
------
* Hamdek (https://www.hamdek.com)
