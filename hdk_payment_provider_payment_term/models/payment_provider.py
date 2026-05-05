# Part of Hamdek. See LICENSE file for full copyright and licensing details.

from odoo import _, api, fields, models

from odoo.addons.payment import utils as payment_utils


class PaymentProvider(models.Model):
    _inherit = "payment.provider"

    allowed_payment_term_id = fields.Many2one(
        comodel_name="account.payment.term",
        string="Allowed Payment Terms",
        help="When set, this provider is only shown to customers whose receivable payment term "
        "matches. When the contact has no payment term, only providers with this field left empty "
        "are shown. When the contact has a payment term, only providers explicitly set to that "
        "same term are shown.",
    )

    def _hdk_matches_partner_payment_term(self, partner, company):
        """Return whether this provider is allowed for the given commercial partner."""
        self.ensure_one()
        partner_term = partner.commercial_partner_id.with_company(
            company
        ).property_payment_term_id
        if not partner_term:
            return not self.allowed_payment_term_id
        return self.allowed_payment_term_id == partner_term

    @api.model
    def _get_compatible_providers(
        self,
        company_id,
        partner_id,
        amount,
        currency_id=None,
        force_tokenization=False,
        is_express_checkout=False,
        is_validation=False,
        report=None,
        sale_order_id=None,
        **kwargs,
    ):
        providers = super()._get_compatible_providers(
            company_id,
            partner_id,
            amount,
            currency_id=currency_id,
            force_tokenization=force_tokenization,
            is_express_checkout=is_express_checkout,
            is_validation=is_validation,
            report=report,
            sale_order_id=sale_order_id,
            **kwargs,
        )
        if not sale_order_id:
            return providers

        order = self.env["sale.order"].sudo().browse(sale_order_id).exists()
        if not order:
            return providers

        company = order.company_id
        pay_partner = self.env["res.partner"].sudo().browse(partner_id).exists() or order.partner_id
        unfiltered = providers
        providers = providers.filtered(
            lambda p: p._hdk_matches_partner_payment_term(pay_partner, company)
        )
        # `payment.utils.add_to_report` exists from newer Odoo versions (e.g. 18+); Odoo 17 has no API.
        add_to_report = getattr(payment_utils, "add_to_report", None)
        if report is not None and add_to_report:
            add_to_report(
                report,
                unfiltered - providers,
                available=False,
                reason=_("incompatible customer payment terms"),
            )
        return providers
