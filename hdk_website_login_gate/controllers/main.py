# -*- coding: utf-8 -*-
#################################################################################
# Author: Hamdek
# Copyright(c): 2026-TODAY Hamdek
# All Rights Reserved.
#
# License: OPL-1 (Odoo Proprietary License v1.0)
#################################################################################

from odoo import _, fields, http
from odoo.http import request

from odoo.addons.payment import utils as payment_utils
from odoo.addons.website_sale.controllers.main import WebsiteSale


class WebsiteSaleLoginGate(WebsiteSale):

    def _hdk_is_public_cart_restricted(self):
        website = request.website
        return (
            request.env.user._is_public()
            and website.hdk_login_required_add_to_cart
        )

    @http.route()
    def cart_update(
        self,
        product_id,
        add_qty=1,
        set_qty=0,
        product_custom_attribute_values=None,
        no_variant_attribute_values=None,
        express=False,
        **kwargs,
    ):
        if self._hdk_is_public_cart_restricted():
            return request.redirect("/shop/cart")
        return super().cart_update(
            product_id,
            add_qty=add_qty,
            set_qty=set_qty,
            product_custom_attribute_values=product_custom_attribute_values,
            no_variant_attribute_values=no_variant_attribute_values,
            express=express,
            **kwargs,
        )

    @http.route()
    def cart_update_json(
        self,
        product_id,
        line_id=None,
        add_qty=None,
        set_qty=None,
        display=True,
        product_custom_attribute_values=None,
        no_variant_attribute_values=None,
        **kw,
    ):
        if self._hdk_is_public_cart_restricted():
            order_sudo = request.website.sale_get_order()
            if line_id:
                qty = set_qty if set_qty is not None else (add_qty if add_qty is not None else 0)
                return self._hdk_update_cart_blocked_payload(
                    line_id,
                    qty,
                    product_id=product_id,
                    display=display,
                    **kw,
                )
            cart_qty = order_sudo.cart_quantity if order_sudo else 0
            return {
                'cart_quantity': cart_qty,
                'notification_info': {
                    'warning': _(
                        'Please sign in before adding products to your cart.'
                    ),
                },
                'quantity': 0,
                'tracking_info': [],
            }
        return super().cart_update_json(
            product_id,
            line_id=line_id,
            add_qty=add_qty,
            set_qty=set_qty,
            display=display,
            product_custom_attribute_values=product_custom_attribute_values,
            no_variant_attribute_values=no_variant_attribute_values,
            **kw,
        )

    def _hdk_update_cart_blocked_payload(
        self,
        line_id,
        quantity,
        product_id=None,
        display=True,
        **kwargs,
    ):
        """Same response shape as /shop/cart/update_json so JS can show warning and refresh DOM."""
        order_sudo = request.website.sale_get_order()
        IrUiView = request.env['ir.ui.view']
        int_qty = int(quantity)

        resolved_line_id = line_id
        if not resolved_line_id and order_sudo and product_id:
            resolved_line_id = order_sudo.order_line.filtered(
                lambda sol: sol.product_id.id == product_id
            )[:1].id

        order_line = (
            order_sudo.order_line.filtered(lambda sol: sol.id == resolved_line_id)[:1]
            if order_sudo
            else request.env['sale.order.line']
        )
        cur_qty = order_line.product_uom_qty if order_line else int_qty

        warning = _('Please sign in to change your cart.')

        values = {
            'warning': warning,
            'quantity': cur_qty,
            'cart_quantity': order_sudo.cart_quantity if order_sudo else 0,
            'cart_ready': order_sudo._is_cart_ready() if order_sudo else False,
            'amount': order_sudo.amount_total if order_sudo else 0.0,
            'minor_amount': (
                payment_utils.to_minor_currency_units(
                    order_sudo.amount_total, order_sudo.currency_id
                )
                if order_sudo
                else 0.0
            ),
        }

        if not display:
            return values

        if order_sudo:
            values['website_sale.cart_lines'] = IrUiView._render_template(
                'website_sale.cart_lines',
                {
                    'website_sale_order': order_sudo,
                    'date': fields.Date.today(),
                    'suggested_products': order_sudo._cart_accessories(),
                },
            )
            values['website_sale.total'] = IrUiView._render_template(
                'website_sale.total',
                {'website_sale_order': order_sudo},
            )
        else:
            values['website_sale.cart_lines'] = ''
            values['website_sale.total'] = ''

        return values

    @http.route()
    def clear_cart(self):
        if self._hdk_is_public_cart_restricted():
            return {'warning': _('Please sign in to clear the cart.')}
        return super().clear_cart()

    @http.route()
    def checkout(self, **post):
        order_sudo = request.website.sale_get_order()
        request.session['sale_last_order_id'] = order_sudo.id

        redirection = self.checkout_redirection(order_sudo)
        if redirection:
            location = redirection.headers.get('Location') or ''
            if not location.startswith('/web/login'):
                return redirection

        if (
            request.env.user._is_public()
            and request.website.hdk_login_required_checkout
        ):
            return request.redirect('/shop/cart?hdk_checkout_login=1')

        return super().checkout(**post)
