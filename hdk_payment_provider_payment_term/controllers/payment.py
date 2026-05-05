# Part of Hamdek. See LICENSE file for full copyright and licensing details.

from odoo import _
from odoo.exceptions import ValidationError
from odoo.http import request

from odoo.addons.website_sale.controllers import main as website_sale_payment


class PaymentPortal(website_sale_payment.PaymentPortal):
    def _create_transaction(
        self,
        provider_id,
        payment_method_id,
        token_id,
        amount,
        currency_id,
        partner_id,
        flow,
        tokenization_requested,
        landing_route,
        reference_prefix=None,
        is_validation=False,
        custom_create_values=None,
        **kwargs,
    ):
        sale_order_id = kwargs.get("sale_order_id")
        if sale_order_id:
            order_sudo = request.env["sale.order"].sudo().browse(sale_order_id).exists()
            provider_sudo = request.env["payment.provider"].sudo().browse(provider_id)
            pay_partner = (
                request.env["res.partner"].sudo().browse(partner_id).exists()
                or order_sudo.partner_id
            )
            if order_sudo and provider_sudo and not provider_sudo._hdk_matches_partner_payment_term(
                pay_partner, order_sudo.company_id
            ):
                raise ValidationError(
                    _("This payment method is not available for your payment terms.")
                )
        return super()._create_transaction(
            provider_id,
            payment_method_id,
            token_id,
            amount,
            currency_id,
            partner_id,
            flow,
            tokenization_requested,
            landing_route,
            reference_prefix=reference_prefix,
            is_validation=is_validation,
            custom_create_values=custom_create_values,
            **kwargs,
        )
