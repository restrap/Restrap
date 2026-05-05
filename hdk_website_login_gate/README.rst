===================================
Hamdek Website Login Gate
===================================

Control **who can use your Odoo website** from one panel: optional **members-only browsing**, **login before add-to-cart**, **login before checkout**, and **menus hidden from guests**—all **per website** under **Settings → Website → Hamdek Website Configuration**.

After authentication, the shop behaves like standard Odoo eCommerce for your site.

Configuration
-------------
* **Hamdek Website Base** adds the shared settings section; this module provides the rules.
* **Require login to browse the website** — guests are sent to sign-in before any storefront page (signup, reset password, TOTP, and payment return URLs remain available).
* **Require login to add to cart** — blocks JSON cart actions (add product, change quantity, clear cart) for anonymous visitors when enabled.
* **Require login to start checkout** — guests who open checkout are returned to the cart with the **same cart notification toast** as other shop warnings (enabled by default on new installs).
* **Menus hidden for visitors** — pick menu entries for this website; they stay out of header/footer navigation until the customer signs in.

Usage
-----
* Install **Hamdek Website Base** and **Hamdek Website Login Gate**.
* Open **Settings**, enable **Developer Mode** if needed, go to **Website** configuration, pick your **Website**, and adjust **Hamdek Website Configuration**.
* Test in a private browser window as a guest.

Requirements
------------
* **hdk_website_base**
* **website_sale**

Behaviour notes
---------------
* Cart restrictions apply to server routes used by the storefront (add to cart, update line, clear cart).
* Checkout restriction applies when **Require login to start checkout** is enabled (redirect to cart + warning toast).
* Full-site login shows the classic email/password form on ``/web/login`` when enabled so the login screen is never blank if the OWL widget does not load.

Technical module name
---------------------
``hdk_website_login_gate``

Migrating from ``hdk_website_checkout_restrict``
-------------------------------------------------
Odoo treats a renamed addons folder as a **new** module. If that older technical name was installed, uninstall it (after backing up the database), install **hdk_website_login_gate**, then turn the same options on again—or use a migration on ``ir_module_module`` / external identifiers if you need zero downtime (consult your integrator).

Author
------
* Hamdek (https://www.hamdek.com)

License
-------
OPL-1 (Odoo Proprietary License v1.0)
