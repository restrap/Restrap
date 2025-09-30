import re

from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError, RedirectWarning
import requests
import json
import base64
import logging
from lxml import etree

from odoo.tools import frozendict

_logger = logging.getLogger(__name__)


class Invoice(models.Model):
    _inherit = 'account.move'

    xero_cust_id = fields.Char(string="Xero Customer Id")
    xero_invoice_id = fields.Char(string="Xero Invoice Id", copy=False)
    tax_state = fields.Selection([('inclusive', 'Tax Inclusive'), ('exclusive', 'Tax Exclusive'), ('no_tax', 'No Tax')],
                                 string='Tax Status', default='exclusive')
    xero_invoice_number = fields.Char(string="Xero Invoice Number", copy=False)
    xero_bank_transaction_id = fields.Char(string="Xero Bank Transaction Id", copy=False)
    bank_transaction_type = fields.Char(string="Bank Transaction Type")
    inclusive = fields.Boolean('Inclusive', default=False, copy=False)
    sale_purchase = fields.Selection([('sale', 'sale'), ('purchase', 'purchase')])

    @api.onchange('partner_id')
    def _onchange_partner_id(self):
        self = self.with_company(self.journal_id.company_id)

        warning = {}
        if self.partner_id:
            rec_account = self.partner_id.property_account_receivable_id
            pay_account = self.partner_id.property_account_payable_id
            if not rec_account and not pay_account:
                action = self.env.ref('account.action_account_config')
                msg = _('Receivable and Payable Accounts are not found.')
                raise RedirectWarning(msg, action.id, _('Go to the configuration panel'))
            p = self.partner_id
            if p.invoice_warn == 'no-message' and p.parent_id:
                p = p.parent_id
            if p.invoice_warn and p.invoice_warn != 'no-message':
                # Block if partner only has warning but parent company is blocked
                if p.invoice_warn != 'block' and p.parent_id and p.parent_id.invoice_warn == 'block':
                    p = p.parent_id
                warning = {
                    'title': _("Warning for %s", p.name),
                    'message': p.invoice_warn_msg
                }
                if p.invoice_warn == 'block':
                    self.partner_id = False
                    return {'warning': warning}

        if self.is_sale_document(include_receipts=True) and self.partner_id:
            self.invoice_payment_term_id = self.partner_id.property_payment_term_id or self.invoice_payment_term_id
            new_term_account = self.partner_id.commercial_partner_id.property_account_receivable_id
        elif self.is_purchase_document(include_receipts=True) and self.partner_id:
            self.invoice_payment_term_id = self.partner_id.property_supplier_payment_term_id or self.invoice_payment_term_id
            new_term_account = self.partner_id.commercial_partner_id.property_account_payable_id
        else:
            new_term_account = None

        for line in self.line_ids:
            line.partner_id = self.partner_id.commercial_partner_id

            if new_term_account and line.account_id.account_type and line.account_id.account_type in (
                    'receivable', 'payable'):
                line.account_id = new_term_account

        self._compute_bank_partner_id()
        self.partner_bank_id = self.bank_partner_id.bank_ids and self.bank_partner_id.bank_ids[0]

        # Find the new fiscal position.
        self.fiscal_position_id = self.env['account.fiscal.position']._get_fiscal_position(
            self.partner_id)
        # delivery_partner_id = self._get_invoice_delivery_partner_id()
        # self.fiscal_position_id = self.env['account.fiscal.position'].get_fiscal_position(
        #     self.partner_id.id, delivery_id=delivery_partner_id)
        # self._recompute_dynamic_lines()
        if warning:
            return {'warning': warning}

    # @api.model
    # def _fields_view_get(self, view_id=None, view_type='form', toolbar=False, submenu=False):
    #     """ Set the correct domain for `partner_id`, depending on invoice type """
    #     result = super(Invoice, self)._fields_view_get(view_id=view_id, view_type=view_type, toolbar=toolbar,
    #                                                           submenu=submenu)
    #     _logger.info("CONTEXT IS ---------------> {}".format(self._context))
    #     document_type = self._context.get('default_move_type')
    #     _logger.info("DOCUMENT TYPE IS --> {}".format(document_type))
    #     if view_type == 'form':
    #         doc = etree.XML(result['arch'])
    #         _logger.info("CONTEXT IS *************---------------> {}".format(doc))
    #         node = doc.xpath("//field[@name='invoice_line_ids']/tree/field[@name='tax_ids']")[0]
    #         node2 = doc.xpath("//field[@name='partner_id']")[0]
    #         _logger.info("CONTEXT IS *************---------------> {}".format(node))
    #         if document_type == 'in_invoice':
    #             _logger.info("DOCUMENT IS OF TYPE VENDOR BILL")
    #             node.set('domain', "[('type_tax_use', '=', 'purchase'),('price_include','=', inclusive)]")
    #             node2.set('domain', "[('supplier_rank', '>=', 1)]")
    #         if document_type == 'out_invoice':
    #             _logger.info("DOCUMENT IS OF TYPE CUSTOMER INVOICE")
    #             node.set('domain', "[('type_tax_use', '=', 'sale'),('price_include','=', inclusive)]")
    #             node2.set('domain', "[('customer_rank', '>=', 1)]")
    #         if document_type == 'out_refund':
    #             _logger.info("DOCUMENT IS OF TYPE CUSTOMER CREDIT NOTE")
    #             node.set('domain', "[('type_tax_use', '=', 'sale'),('price_include','=', inclusive)]")
    #             node2.set('domain', "[('customer_rank', '>=', 1)]")
    #         if document_type == 'in_refund':
    #             _logger.info("DOCUMENT IS OF TYPE  VENDOR CREDIT NOTE")
    #             node.set('domain', "[('type_tax_use', '=', 'purchase'),('price_include','=', inclusive)]")
    #             node2.set('domain', "[('supplier_rank', '>=', 1)]")
    #
    #         result['arch'] = etree.tostring(doc)
    #     return result

    @api.model
    @api.onchange('tax_state')
    def onchange_tax_status(self):
        if self.type_name == 'Vendor Bill':
            self.sale_purchase = 'purchase'
            if self.tax_state == 'inclusive':
                self.inclusive = True
            elif self.tax_state == 'no_tax':
                self.sale_purchase = None
            else:
                self.inclusive = False

        else:
            self.sale_purchase = 'sale'
            if self.tax_state == 'inclusive':
                self.inclusive = True
            elif self.tax_state == 'no_tax':
                self.sale_purchase = None
            else:
                self.inclusive = False

        for line_id in self.invoice_line_ids:
            if self.tax_state == 'inclusive':
                line_id.inclusive = True
            elif self.tax_state == 'exclusive':
                line_id.inclusive = False
            elif self.tax_state == 'no_tax':
                line_id.tax_ids = [(5, 0, 0)]


    @api.model
    def prepare_invoice_export_line_dict(self, line):

        company = self.env['res.users'].search([('id', '=', self._uid)], limit=1).company_id
        line_vals = {}
        account_code = None
        if self.partner_id:
            line_tax = self.env['account.tax'].search([('id', '=', line.tax_ids.id), ('company_id', '=', company.id)])

            if line.quantity < 0:
                qty = -line.quantity
                price = -line.price_unit
            else:
                qty = line.quantity
                price = line.price_unit

            if line.discount:
                discount = line.discount
            else:
                discount = 0.0

            Tracking_list = []
            if line.analytic_distribution:
                for analytic_dist_id in line.analytic_distribution:
                    analytic_account_id = self.env['account.analytic.account'].search(
                        [('id', '=', analytic_dist_id)])
                    analytic_account_id.create_analytic_account_in_xero(
                        account_id=analytic_account_id.id)
                    Tracking_list.append({'Name': analytic_account_id.plan_id.name,
                                          'Option': analytic_account_id.name})

            if line.account_id:
                if line.account_id.xero_account_id:
                    account_code = line.account_id.code
                else:
                    self.env['account.account'].create_account_ref_in_xero(line.account_id)
                    if line.account_id.xero_account_id:
                        account_code = line.account_id.code

            if line.product_id and not company.export_invoice_without_product:
                if line.tax_ids:
                    if line_tax:
                        tax = line_tax.xero_tax_type_id
                        if not tax:
                            self.env['account.tax'].get_xero_tax_ref(line_tax)
                            line_tax = self.env['account.tax'].search(
                                [('id', '=', line.tax_ids.id), ('company_id', '=', company.id)])
                            tax = line_tax.xero_tax_type_id

                        line_vals = {
                            'Description': line.name,
                            'UnitAmount': price,
                            'ItemCode': line.product_id.default_code,
                            'AccountCode': account_code,
                            'Quantity': qty,
                            'DiscountRate': discount,
                            "Tracking": Tracking_list,
                            'TaxType': tax
                        }
                    else:
                        line_vals = {
                            'Description': line.name,
                            'UnitAmount': price,
                            'ItemCode': line.product_id.default_code,
                            'AccountCode': account_code,
                            'Quantity': qty,
                            'DiscountRate': discount,
                            "Tracking": Tracking_list,
                        }
                else:
                    line_vals = {
                        'Description': line.name,
                        'UnitAmount': price,
                        'ItemCode': line.product_id.default_code,
                        'AccountCode': account_code,
                        'Quantity': qty,
                        'DiscountRate': discount,
                        "Tracking": Tracking_list,
                    }
            else:
                if line.tax_ids:
                    if line_tax:
                        tax = line_tax.xero_tax_type_id
                        if not tax:
                            self.env['account.tax'].get_xero_tax_ref(line_tax)
                            line_tax = self.env['account.tax'].search(
                                [('id', '=', line.tax_ids.id), ('company_id', '=', company.id)])
                            tax = line_tax.xero_tax_type_id

                        line_vals = {
                            'Description': line.name,
                            'UnitAmount': price,
                            'AccountCode': account_code,
                            'Quantity': qty,
                            'DiscountRate': discount,
                            'TaxType': tax,
                            "Tracking": Tracking_list,
                        }
                    else:
                        line_vals = {
                            'Description': line.name,
                            'UnitAmount': price,
                            'AccountCode': account_code,
                            'Quantity': qty,
                            'DiscountRate': discount,
                            "Tracking": Tracking_list,
                        }
                else:
                    line_vals = {
                        'Description': line.name,
                        'UnitAmount': price,
                        'AccountCode': account_code,
                        'DiscountRate': discount,
                        'Quantity': qty,
                        "Tracking": Tracking_list,
                    }
        return line_vals

    @api.model
    def prepare_invoice_export_dict(self):
        if self._context.get('cron'):
            company = self.company_id
        else:
            company = self.env['res.users'].search([('id', '=', self._uid)], limit=1).company_id
        if self.move_type == 'in_invoice':
            vals = self.prepare_vendorbill_export_dict()
            return vals
        else:

            if self.env.user.company_id.export_bill_parent_contact and self.partner_id.parent_id:
                cust_id = self.env['res.partner'].get_xero_partner_ref(self.partner_id.parent_id)
            else:
                cust_id = self.env['res.partner'].get_xero_partner_ref(self.partner_id)

            vals = {}
            lst_line = []
            origin_reference = ''
            if self.move_type == 'in_invoice':
                type = 'ACCPAY'
            elif self.move_type == 'out_invoice':
                type = 'ACCREC'
            elif self.move_type == 'in_refund':
                type = 'ACCPAYCREDIT'
            elif self.move_type == 'out_refund':
                type = 'ACCRECCREDIT'

            if company.map_invoice_reference == 'customer_ref':
                if self.ref:
                    origin_reference = self.ref
            elif company.map_invoice_reference == 'payment_ref':
                if self.payment_reference:
                    origin_reference = self.payment_reference

            if self.tax_state:
                if self.tax_state == 'inclusive':
                    tax_state = 'Inclusive'
                elif self.tax_state == 'exclusive':
                    tax_state = 'Exclusive'
                elif self.tax_state == 'no_tax':
                    tax_state = 'NoTax'

            if self.state:
                if self.state == 'posted':
                    status = 'AUTHORISED'

                if company.invoice_status:
                    if company.invoice_status == 'draft':
                        status = 'DRAFT'
                    if company.invoice_status == 'authorised':
                        status = 'AUTHORISED'

            if len(self.invoice_line_ids) == 1:
                single_line = self.invoice_line_ids
                Tracking_list = []
                if single_line.analytic_distribution:
                    for analytic_dist_id in single_line.analytic_distribution:
                        analytic_account_id = self.env['account.analytic.account'].search(
                            [('id', '=', analytic_dist_id)])
                        analytic_account_id.create_analytic_account_in_xero(
                            account_id=analytic_account_id.id)
                        Tracking_list.append({'Name': analytic_account_id.plan_id.name,
                                              'Option': analytic_account_id.name})

                if single_line.quantity < 0:
                    qty = -single_line.quantity
                    price = -single_line.price_unit
                else:
                    qty = single_line.quantity
                    price = single_line.price_unit

                if single_line.discount:
                    discount = single_line.discount
                else:
                    discount = 0.0

                if single_line.account_id:
                    if single_line.account_id.xero_account_id:
                        account_code = single_line.account_id.code
                    else:
                        self.env['account.account'].create_account_ref_in_xero(single_line.account_id)
                        if single_line.account_id.xero_account_id:
                            account_code = single_line.account_id.code

                if single_line.product_id and not company.export_invoice_without_product:
                    if single_line.product_id.xero_product_id:
                        _logger.info(_("PRODUCT DEFAULT CODE AVAILABLE"))
                    elif not single_line.product_id.xero_product_id:
                        self.env['product.product'].get_xero_product_ref(single_line.product_id)

                    if single_line.tax_ids:
                        line_tax = self.env['account.tax'].search(
                            [('id', '=', single_line.tax_ids.id), ('company_id', '=', company.id)])
                        if line_tax:
                            tax = line_tax.xero_tax_type_id
                            if not tax:
                                self.env['account.tax'].get_xero_tax_ref(line_tax)
                                line_tax = self.env['account.tax'].search(
                                    [('id', '=', single_line.tax_ids.id), ('company_id', '=', company.id)])
                                tax = line_tax.xero_tax_type_id

                            vals.update({
                                "Contact": {
                                    "ContactID": cust_id
                                },
                                "Type": type,
                                "LineAmountTypes": tax_state,
                                "DueDate": str(self.invoice_date_due),
                                # "Date": str(self.invoice_date),
                                "Date": str(self.date if company.invoice_bill_accounting_date else self.invoice_date),
                                "Reference": origin_reference,
                                "InvoiceNumber": self.xero_invoice_number if (
                                        self.xero_invoice_number and self.xero_invoice_id) else self.name,
                                "LineItems": [
                                    {
                                        "Description": single_line.name,
                                        "Quantity": qty,
                                        "UnitAmount": price,
                                        "ItemCode": single_line.product_id.default_code,
                                        "AccountCode": account_code,
                                        "DiscountRate": discount,
                                        "Tracking": Tracking_list,
                                        "TaxType": tax
                                    }
                                ],
                                "Status": status
                            })


                    else:
                        vals.update({
                            # "Type": "ACCREC",
                            "Contact": {
                                "ContactID": cust_id
                            },
                            "Type": type,
                            "LineAmountTypes": tax_state,
                            "DueDate": str(self.invoice_date_due),
                            # "Date": str(self.invoice_date),
                            "Date": str(self.date if company.invoice_bill_accounting_date else self.invoice_date),
                            "Reference": origin_reference,
                            "InvoiceNumber": self.xero_invoice_number if (
                                    self.xero_invoice_number and self.xero_invoice_id) else self.name,
                            "LineItems": [
                                {
                                    "Description": single_line.name,
                                    "Quantity": qty,
                                    "UnitAmount": price,
                                    'ItemCode': single_line.product_id.default_code,
                                    "DiscountRate": discount,
                                    "Tracking": Tracking_list,
                                    "AccountCode": account_code
                                }
                            ],
                            "Status": status
                        })
                else:
                    if single_line.tax_ids:
                        line_tax = self.env['account.tax'].search(
                            [('id', '=', single_line.tax_ids.id), ('company_id', '=', company.id)])
                        if line_tax:
                            tax = line_tax.xero_tax_type_id
                            if not tax:
                                self.env['account.tax'].get_xero_tax_ref(line_tax)
                                line_tax = self.env['account.tax'].search(
                                    [('id', '=', single_line.tax_ids.id), ('company_id', '=', company.id)])
                                tax = line_tax.xero_tax_type_id

                            vals.update({
                                "Contact": {
                                    "ContactID": cust_id
                                },
                                "Type": type,
                                "LineAmountTypes": tax_state,
                                "DueDate": str(self.invoice_date_due),
                                # "Date": str(self.invoice_date),
                                "Date": str(self.date if company.invoice_bill_accounting_date else self.invoice_date),
                                "Reference": origin_reference,
                                "InvoiceNumber": self.xero_invoice_number if (
                                        self.xero_invoice_number and self.xero_invoice_id) else self.name,
                                "LineItems": [
                                    {
                                        "Description": single_line.name,
                                        "Quantity": qty,
                                        "UnitAmount": price,
                                        "AccountCode": account_code,
                                        "DiscountRate": discount,
                                        "Tracking": Tracking_list,
                                        "TaxType": tax
                                    }
                                ],
                                "Status": status
                            })
                    else:
                        vals.update({
                            "Contact": {
                                "ContactID": cust_id
                            },
                            "Type": type,
                            "DueDate": str(self.invoice_date_due),
                            # "Date": str(self.invoice_date),
                            "Date": str(self.date if company.invoice_bill_accounting_date else self.invoice_date),
                            "Reference": origin_reference,
                            "InvoiceNumber": self.xero_invoice_number if (
                                    self.xero_invoice_number and self.xero_invoice_id) else self.name,
                            "LineItems": [
                                {
                                    "Description": single_line.name,
                                    "DiscountRate": discount,
                                    "Quantity": qty,
                                    "UnitAmount": price,
                                    "Tracking": Tracking_list,
                                    "AccountCode": account_code
                                }
                            ],
                            "Status": status
                        })
            else:

                for line in self.invoice_line_ids:

                    if line.product_id and not company.export_invoice_without_product:
                        if line.product_id.xero_product_id:
                            _logger.info(_("PRODUCT DEFAULT CODE AVAILABLE"))
                        elif not line.product_id.xero_product_id:
                            self.env['product.product'].get_xero_product_ref(line.product_id)

                    line_vals = self.prepare_invoice_export_line_dict(line)
                    lst_line.append(line_vals)
                vals.update({
                    "Type": type,
                    "LineAmountTypes": tax_state,
                    "Contact": {"ContactID": cust_id},
                    "DueDate": str(self.invoice_date_due),
                    # "Date": str(self.invoice_date),
                    "Date": str(self.date if company.invoice_bill_accounting_date else self.invoice_date),
                    "Reference": origin_reference,
                    "InvoiceNumber": self.xero_invoice_number if (
                            self.xero_invoice_number and self.xero_invoice_id) else self.name,
                    "Status": status,
                    "LineItems": lst_line,
                })

            if self.currency_id:
                currency_code = self.currency_id.name
                vals.update({"CurrencyCode": currency_code})
            _logger.info('vals : {}'.format(vals))
            # Filter currency rates based on the given date
            # currency_rates = self.currency_id.rate_ids.filtered(lambda rate: self.invoice_date == rate.name)
            # # If currency rate is found, update the vals dictionary
            # if currency_rates:
            #     vals["CurrencyRate"] = currency_rates[0].company_rate
            if self.currency_id != company.currency_id:
                date = self.date if company.invoice_bill_accounting_date else self.invoice_date
                currency_rates = self.currency_id.rate_ids.filtered(lambda rate: date >= rate.name)
                if currency_rates:
                    currency_rates = max(currency_rates).company_rate
                else:
                    currency_rates = 1
                vals["CurrencyRate"] = currency_rates

            return vals

    # -----------------------------------------------------------------------------------------
    @api.model
    def prepare_credit_note_export_line_dict(self, line):

        company = self.env['res.users'].search([('id', '=', self._uid)], limit=1).company_id
        line_vals = {}
        account_code = None

        if self.partner_id:
            line_tax = self.env['account.tax'].search([('id', '=', line.tax_ids.id), ('company_id', '=', company.id)])

            if line.quantity < 0:
                qty = -line.quantity
                price = -line.price_unit
            else:
                qty = line.quantity
                price = line.price_unit

            Tracking_list = []
            if line.analytic_distribution:
                for analytic_dist_id in line.analytic_distribution:
                    analytic_account_id = self.env['account.analytic.account'].search(
                        [('id', '=', analytic_dist_id)])
                    analytic_account_id.create_analytic_account_in_xero(
                        account_id=analytic_account_id.id)
                    Tracking_list.append({'Name': analytic_account_id.plan_id.name,
                                          'Option': analytic_account_id.name})

            if line.account_id:
                if line.product_id.detailed_type == 'product':
                    if company.non_tracked_item:
                        account_code = line.account_id.code
                    elif company.export_bill_without_product:
                        account_code = line.account_id.code
                    else:
                        account_code = line.product_id.categ_id.xero_inventory_account.code
                    if not company.non_tracked_item:
                        if not account_code:
                            raise UserError(_("Please Set XERO Inventory Account Field In Product Category "))
                elif line.account_id.xero_account_id:
                    account_code = line.account_id.code
                else:
                    self.env['account.account'].create_account_ref_in_xero(line.account_id)
                    if line.account_id.xero_account_id:
                        account_code = line.account_id.code

            if ((
                        line.move_id.move_type == 'in_invoice' or line.move_id.move_type == 'in_refund') and line.product_id and not company.export_bill_without_product) or (
                    line.move_id.move_type == 'out_refund' and line.product_id and not company.export_invoice_without_product):
                if line.tax_ids:
                    if line_tax:
                        tax = line_tax.xero_tax_type_id
                        if not tax:
                            self.env['account.tax'].get_xero_tax_ref(line_tax)
                            line_tax = self.env['account.tax'].search(
                                [('id', '=', line.tax_ids.id), ('company_id', '=', company.id)])
                            tax = line_tax.xero_tax_type_id

                        line_vals = {
                            'Description': line.name,
                            'UnitAmount': price,
                            'ItemCode': line.product_id.default_code,
                            'AccountCode': account_code,
                            'Quantity': qty,
                            'TaxType': tax,
                            'Tracking': Tracking_list
                        }
                else:

                    line_vals = {
                        'Description': line.name,
                        'UnitAmount': price,
                        'ItemCode': line.product_id.default_code,
                        'AccountCode': account_code,
                        'Quantity': qty,
                        'Tracking': Tracking_list
                    }
            else:
                if line.tax_ids:
                    if line_tax:
                        tax = line_tax.xero_tax_type_id
                        if not tax:
                            self.env['account.tax'].get_xero_tax_ref(line_tax)
                            line_tax = self.env['account.tax'].search(
                                [('id', '=', line.tax_ids.id), ('company_id', '=', company.id)])
                            tax = line_tax.xero_tax_type_id

                        line_vals = {
                            'Description': line.name,
                            'UnitAmount': price,
                            'AccountCode': account_code,
                            'Quantity': qty,
                            'TaxType': tax,
                            'Tracking': Tracking_list
                        }
                else:
                    line_vals = {
                        'Description': line.name,
                        'UnitAmount': price,
                        'AccountCode': account_code,
                        'Quantity': qty,
                        'Tracking': Tracking_list
                    }
        return line_vals

    @api.model
    def prepare_credit_note_export_dict(self):
        company = self.env['res.users'].search([('id', '=', self._uid)], limit=1).company_id

        if self.env.user.company_id.export_bill_parent_contact and self.partner_id.parent_id:
            cust_id = self.env['res.partner'].get_xero_partner_ref(self.partner_id.parent_id)
        else:
            cust_id = self.env['res.partner'].get_xero_partner_ref(self.partner_id)

        vals = {}
        lst_line = []
        origin_credit_note = ''
        type = ''
        _logger.info(f"Transaction  Type ======================================{self.move_type}")
        if self.move_type == 'in_invoice':
            type = 'ACCPAY'
        elif self.move_type == 'out_invoice':
            type = 'ACCREC'
        elif self.move_type == 'in_refund':
            type = 'ACCPAYCREDIT'
        elif self.move_type == 'out_refund':
            type = 'ACCRECCREDIT'
            if self.invoice_origin:
                origin_credit_note = self.invoice_origin

        if self.tax_state:
            if self.tax_state == 'inclusive':
                tax_state = 'Inclusive'
            elif self.tax_state == 'exclusive':
                tax_state = 'Exclusive'
            elif self.tax_state == 'no_tax':
                tax_state = 'NoTax'

        if self.state:
            if self.state == 'posted':
                status = 'AUTHORISED'

            if company.invoice_status:
                if company.invoice_status == 'draft':
                    status = 'DRAFT'
                if company.invoice_status == 'authorised':
                    status = 'AUTHORISED'

        if len(self.invoice_line_ids) == 1:
            single_line = self.invoice_line_ids

            Tracking_list = []
            if single_line.analytic_distribution:
                for analytic_dist_id in single_line.analytic_distribution:
                    analytic_account_id = self.env['account.analytic.account'].search(
                        [('id', '=', analytic_dist_id)])
                    analytic_account_id.create_analytic_account_in_xero(
                        account_id=analytic_account_id.id)
                    Tracking_list.append({'Name': analytic_account_id.plan_id.name,
                                          'Option': analytic_account_id.name})

            if single_line.quantity < 0:
                qty = -single_line.quantity
                price = -single_line.price_unit
            else:
                qty = single_line.quantity
                price = single_line.price_unit

            if single_line.account_id:
                if single_line.account_id.xero_account_id:
                    account_code = single_line.account_id.code
                else:
                    self.env['account.account'].create_account_ref_in_xero(single_line.account_id)
                    if single_line.account_id.xero_account_id:
                        account_code = single_line.account_id.code

            if ((
                    single_line.move_id.move_type == 'out_refund' and single_line.product_id and not company.export_invoice_without_product) or (
                    single_line.move_id.move_type == 'in_refund' and single_line.product_id and not company.export_bill_without_product)):
                if single_line.product_id.xero_product_id:
                    _logger.info(_("PRODUCT DEFAULT CODE AVAILABLE"))
                elif not single_line.product_id.xero_product_id:
                    self.env['product.product'].get_xero_product_ref(single_line.product_id)

                if single_line.tax_ids:
                    line_tax = self.env['account.tax'].search(
                        [('id', '=', single_line.tax_ids.id), ('company_id', '=', company.id)])
                    if line_tax:
                        tax = line_tax.xero_tax_type_id
                        if not tax:
                            self.env['account.tax'].get_xero_tax_ref(line_tax)
                            line_tax = self.env['account.tax'].search(
                                [('id', '=', single_line.tax_ids.id), ('company_id', '=', company.id)])
                            tax = line_tax.xero_tax_type_id

                        vals.update({
                            "Contact": {
                                "ContactID": cust_id
                            },
                            "Type": type,
                            "LineAmountTypes": tax_state,
                            "DueDate": str(self.invoice_date_due),
                            # "Date": str(self.invoice_date),
                            "Date": str(self.date if company.invoice_bill_accounting_date else self.invoice_date),
                            "CreditNoteNumber": self.xero_invoice_number if (
                                    self.xero_invoice_number and self.xero_invoice_id) else self.name,
                            "LineItems": [
                                {
                                    "Description": single_line.name,
                                    "Quantity": qty,
                                    "UnitAmount": price,
                                    'ItemCode': single_line.product_id.default_code,
                                    "AccountCode": account_code,
                                    "TaxType": tax,
                                    "Tracking": Tracking_list
                                }
                            ],
                            "Status": status
                        })
                else:
                    vals.update({
                        "Contact": {
                            "ContactID": cust_id
                        },
                        "Type": type,
                        "LineAmountTypes": tax_state,
                        "DueDate": str(self.invoice_date_due),
                        # "Date": str(self.invoice_date),
                        "Date": str(self.date if company.invoice_bill_accounting_date else self.invoice_date),
                        "CreditNoteNumber": self.xero_invoice_number if (
                                self.xero_invoice_number and self.xero_invoice_id) else self.name,
                        "LineItems": [
                            {
                                "Description": single_line.name,
                                "Quantity": qty,
                                "UnitAmount": price,
                                'ItemCode': single_line.product_id.default_code,
                                "AccountCode": account_code,
                                "Tracking": Tracking_list
                            }
                        ],
                        "Status": status
                    })
            else:
                if single_line.tax_ids:
                    line_tax = self.env['account.tax'].search(
                        [('id', '=', single_line.tax_ids.id), ('company_id', '=', company.id)])
                    if line_tax:
                        tax = line_tax.xero_tax_type_id
                        if not tax:
                            self.env['account.tax'].get_xero_tax_ref(line_tax)
                            line_tax = self.env['account.tax'].search(
                                [('id', '=', single_line.tax_ids.id), ('company_id', '=', company.id)])
                            tax = line_tax.xero_tax_type_id

                        vals.update({
                            "Contact": {
                                "ContactID": cust_id
                            },
                            "Type": type,
                            "LineAmountTypes": tax_state,
                            "DueDate": str(self.invoice_date_due),
                            # "Date": str(self.invoice_date),
                            "Date": str(self.date if company.invoice_bill_accounting_date else self.invoice_date),
                            "CreditNoteNumber": self.xero_invoice_number if (
                                    self.xero_invoice_number and self.xero_invoice_id) else self.name,
                            "LineItems": [
                                {
                                    "Description": single_line.name,
                                    "Quantity": qty,
                                    "UnitAmount": price,
                                    "AccountCode": account_code,
                                    "TaxType": tax,
                                    "Tracking": Tracking_list
                                }
                            ],
                            "Status": status
                        })
                else:
                    vals.update({
                        "Contact": {
                            "ContactID": cust_id
                        },
                        "Type": type,
                        "DueDate": str(self.invoice_date_due),
                        # "Date": str(self.invoice_date),
                        "Date": str(self.date if company.invoice_bill_accounting_date else self.invoice_date),
                        "CreditNoteNumber": self.xero_invoice_number if (
                                self.xero_invoice_number and self.xero_invoice_id) else self.name,
                        "LineItems": [
                            {
                                "Description": single_line.name,
                                "Quantity": qty,
                                "UnitAmount": price,
                                "AccountCode": account_code,
                                "Tracking": Tracking_list
                            }
                        ],
                        "Status": status
                    })
        else:

            for line in self.invoice_line_ids:
                if ((
                        line.move_id.move_type == 'out_refund' and line.product_id and not company.export_invoice_without_product) or (
                        line.move_id.move_type == 'in_refund' and line.product_id and not company.export_bill_without_product)):
                    if line.product_id.xero_product_id:
                        _logger.info(_("PRODUCT DEFAULT CODE AVAILABLE"))
                    elif not line.product_id.xero_product_id:
                        self.env['product.product'].get_xero_product_ref(line.product_id)

                line_vals = self.prepare_credit_note_export_line_dict(line)
                lst_line.append(line_vals)
            vals.update({
                "Type": type,
                "LineAmountTypes": tax_state,
                "Contact": {"ContactID": cust_id},
                "DueDate": str(self.invoice_date_due),
                # "Date": str(self.invoice_date),
                "Date": str(self.date if company.invoice_bill_accounting_date else self.invoice_date),
                "CreditNoteNumber": self.xero_invoice_number if (
                        self.xero_invoice_number and self.xero_invoice_id) else self.name,
                "Status": status,
                "LineItems": lst_line,
            })

        if origin_credit_note:
            vals.update({'Reference': origin_credit_note})

        if self.currency_id:
            currency_code = self.currency_id.name
            vals.update({"CurrencyCode": currency_code})
        if self.currency_id != company.currency_id:
            date = self.date if company.invoice_bill_accounting_date else self.invoice_date
            currency_rates = self.currency_id.rate_ids.filtered(lambda rate: date >= rate.name)
            if currency_rates:
                currency_rates = max(currency_rates).company_rate
            else:
                currency_rates = 1
            vals["CurrencyRate"] = currency_rates
        # # Filter currency rates based on the given date
        # currency_rates = self.currency_id.rate_ids.filtered(lambda rate: self.invoice_date == rate.name)
        # # If currency rate is found, update the vals dictionary
        # if currency_rates:
        #     vals["CurrencyRate"] = currency_rates[0].company_rate

        return vals

    @api.model
    def prepare_vendorbill_export_dict(self):
        company = self.env['res.users'].search([('id', '=', self._uid)], limit=1).company_id

        if self.env.user.company_id.export_bill_parent_contact and self.partner_id.parent_id:
            cust_id = self.env['res.partner'].get_xero_partner_ref(self.partner_id.parent_id)
        else:
            cust_id = self.env['res.partner'].get_xero_partner_ref(self.partner_id)

        vals = {}
        lst_line = []
        if self.move_type == 'in_invoice':
            type = 'ACCPAY'
        elif self.move_type == 'out_invoice':
            type = 'ACCREC'
        elif self.move_type == 'in_refund':
            type = 'ACCPAYCREDIT'
        elif self.move_type == 'out_refund':
            type = 'ACCRECCREDIT'

        # if self.origin:
        #     reference = self.origin
        # else:

        if (self.xero_invoice_number and self.xero_invoice_id):
            reference = self.xero_invoice_number
        else:
            reference = self.name
            if self.ref:
                reference = '{} ({})'.format(self.name, self.ref)

        if self.tax_state:
            if self.tax_state == 'inclusive':
                tax_state = 'Inclusive'
            elif self.tax_state == 'exclusive':
                tax_state = 'Exclusive'
            elif self.tax_state == 'no_tax':
                tax_state = 'NoTax'

        if self.state:
            if self.state == 'posted':
                status = 'AUTHORISED'

            if company.invoice_status:
                if company.invoice_status == 'draft':
                    status = 'DRAFT'
                if company.invoice_status == 'authorised':
                    status = 'AUTHORISED'

        if len(self.invoice_line_ids) == 1:
            single_line = self.invoice_line_ids

            Tracking_list = []
            if single_line.analytic_distribution:
                for analytic_dist_id in single_line.analytic_distribution:
                    analytic_account_id = self.env['account.analytic.account'].search(
                        [('id', '=', analytic_dist_id)])
                    analytic_account_id.create_analytic_account_in_xero(
                        account_id=analytic_account_id.id)
                    Tracking_list.append({'Name': analytic_account_id.plan_id.name,
                                          'Option': analytic_account_id.name})

            if single_line.quantity < 0:
                qty = -single_line.quantity
                price = -single_line.price_unit
            else:
                qty = single_line.quantity
                price = single_line.price_unit

            if single_line.account_id:
                if single_line.product_id.detailed_type == 'product':
                    if company.non_tracked_item:
                        account_code = single_line.account_id.code
                    elif company.export_bill_without_product:
                        account_code = single_line.account_id.code
                    else:
                        account_code = single_line.product_id.categ_id.xero_inventory_account.code
                    if not company.non_tracked_item:
                        if not account_code:
                            raise UserError(_("Please Set XERO Inventory Account Field In Product Category "))
                elif single_line.account_id.xero_account_id:
                    account_code = single_line.account_id.code
                else:
                    self.env['account.account'].create_account_ref_in_xero(single_line.account_id)
                    if single_line.account_id.xero_account_id:
                        account_code = single_line.account_id.code

            if single_line.product_id and not company.export_bill_without_product:
                if single_line.product_id.xero_product_id:
                    _logger.info(_("PRODUCT DEFAULT CODE AVAILABLE"))
                elif not single_line.product_id.xero_product_id:
                    self.env['product.product'].get_xero_product_ref(single_line.product_id)

                if single_line.tax_ids:
                    line_tax = self.env['account.tax'].search(
                        [('id', '=', single_line.tax_ids.id), ('company_id', '=', company.id)])
                    if line_tax:
                        tax = line_tax.xero_tax_type_id
                        if not tax:
                            self.env['account.tax'].get_xero_tax_ref(line_tax)
                            line_tax = self.env['account.tax'].search(
                                [('id', '=', single_line.tax_ids.id), ('company_id', '=', company.id)])
                            tax = line_tax.xero_tax_type_id


                        vals.update({
                            "Contact": {
                                "ContactID": cust_id
                            },
                            "Type": type,
                            "LineAmountTypes": tax_state,
                            "DueDate": str(self.invoice_date_due),
                            # "Date": str(self.invoice_date),
                            "Date": str(self.date if company.invoice_bill_accounting_date else self.invoice_date),
                            "InvoiceNumber": reference,
                            "LineItems": [
                                {
                                    "Description": single_line.name,
                                    "Quantity": qty,
                                    "UnitAmount": price,
                                    'ItemCode': single_line.product_id.default_code,
                                    "AccountCode": account_code,
                                    "TaxType": tax,
                                    "Tracking": Tracking_list
                                }
                            ],
                            "Status": status
                        })
                else:
                    vals.update({
                        "Contact": {
                            "ContactID": cust_id
                        },
                        "Type": type,
                        "LineAmountTypes": tax_state,
                        "DueDate": str(self.invoice_date_due),
                        # "Date": str(self.invoice_date),
                        "Date": str(self.date if company.invoice_bill_accounting_date else self.invoice_date),
                        "InvoiceNumber": reference,
                        "LineItems": [
                            {
                                "Description": single_line.name,
                                "Quantity": qty,
                                "UnitAmount": price,
                                'ItemCode': single_line.product_id.default_code,
                                "AccountCode": account_code,
                                "Tracking": Tracking_list
                            }
                        ],
                        "Status": status
                    })
            else:
                if single_line.tax_ids:
                    line_tax = self.env['account.tax'].search(
                        [('id', '=', single_line.tax_ids.id), ('company_id', '=', company.id)])
                    if line_tax:
                        tax = line_tax.xero_tax_type_id
                        if not tax:
                            self.env['account.tax'].get_xero_tax_ref(line_tax)
                            line_tax = self.env['account.tax'].search(
                                [('id', '=', single_line.tax_ids.id), ('company_id', '=', company.id)])
                            tax = line_tax.xero_tax_type_id

                        vals.update({
                            "Contact": {
                                "ContactID": cust_id
                            },
                            "Type": type,
                            "LineAmountTypes": tax_state,
                            "DueDate": str(self.invoice_date_due),
                            # "Date": str(self.invoice_date),
                            "Date": str(self.date if company.invoice_bill_accounting_date else self.invoice_date),
                            "InvoiceNumber": reference,
                            "LineItems": [
                                {
                                    "Description": single_line.name,
                                    "Quantity": qty,
                                    "UnitAmount": price,
                                    "AccountCode": account_code,
                                    "TaxType": tax,
                                    "Tracking": Tracking_list
                                }
                            ],
                            "Status": status
                        })
                else:
                    vals.update({
                        "Contact": {
                            "ContactID": cust_id
                        },
                        "Type": type,
                        "LineAmountTypes": tax_state,
                        "DueDate": str(self.invoice_date_due),
                        # "Date": str(self.invoice_date),
                        "Date": str(self.date if company.invoice_bill_accounting_date else self.invoice_date),
                        "InvoiceNumber": reference,
                        "LineItems": [
                            {
                                "Description": single_line.name,
                                "Quantity": qty,
                                "UnitAmount": price,
                                "AccountCode": account_code,
                                "Tracking": Tracking_list
                            }
                        ],
                        "Status": status
                    })
        else:

            for line in self.invoice_line_ids:
                if line.product_id and not company.export_bill_without_product:
                    if line.product_id.xero_product_id:
                        _logger.info(_("PRODUCT DEFAULT CODE AVAILABLE"))
                    elif not line.product_id.xero_product_id:
                        self.env['product.product'].get_xero_product_ref(line.product_id)

                line_vals = self.prepare_credit_note_export_line_dict(line)
                lst_line.append(line_vals)
            vals.update({
                "Type": type,
                "LineAmountTypes": tax_state,
                "Contact": {"ContactID": cust_id},
                "DueDate": str(self.invoice_date_due),
                # "Date": str(self.invoice_date),
                "Date": str(self.date if company.invoice_bill_accounting_date else self.invoice_date),
                "InvoiceNumber": reference,
                "Status": status,
                "LineItems": lst_line,
            })
        if self.currency_id:
            currency_code = self.currency_id.name
            vals.update({"CurrencyCode": currency_code})
        if self.currency_id != company.currency_id:
            date = self.date if company.invoice_bill_accounting_date else self.invoice_date
            currency_rates = self.currency_id.rate_ids.filtered(lambda rate: date >= rate.name)
            if currency_rates:
                currency_rates = max(currency_rates).company_rate
            else:
                currency_rates = 1
            vals["CurrencyRate"] = currency_rates
        # # Filter currency rates based on the given date
        # currency_rates = self.currency_id.rate_ids.filtered(lambda rate: self.invoice_date == rate.name)
        # # If currency rate is found, update the vals dictionary
        # if currency_rates:
        #     vals["CurrencyRate"] = currency_rates[0].company_rate



        return vals

    @api.model
    def exportInvoice(self, payment_export=None):
        """export account invoice to QBO"""
        headers = self.get_head()
        xero_config = self.company_id
        if not xero_config:
            xero_config = self.env['res.users'].search([('id', '=', self._uid)], limit=1).company_id
        if self._context.get('active_ids') and not payment_export:
            invoice = self.browse(self._context.get('active_ids'))
        else:
            invoice = self

        for t in invoice:
            if (t.move_type == 'out_refund') or (t.move_type == 'in_refund'):
                self.exportCreditNote()
            elif (t.move_type == 'out_invoice') or (t.move_type == 'in_invoice'):
                _logger.info(f'Export Bill/Invoice Data is------------>{t.name}')
                if not t.xero_invoice_id:
                    if t.state == 'posted':
                        values = t.prepare_invoice_export_dict()
                        vals = self.remove_note_section(values)
                        parsed_dict = json.dumps(vals)
                        _logger.info("\n\nInvoice parsed_dict :   {} ".format(parsed_dict))
                        url = 'https://api.xero.com/api.xro/2.0/Invoices?unitdp=4'
                        data = requests.request('POST', url=url, data=parsed_dict, headers=headers)

                        _logger.info("Response 1 From Server :{} {} ".format(data.status_code, data.text))  # ,data.text

                        if data.status_code == 200:
                            response_data = json.loads(data.text)
                            if response_data.get('Invoices'):
                                t.xero_invoice_number = response_data.get('Invoices')[0].get('InvoiceNumber')
                                t.xero_invoice_id = response_data.get('Invoices')[0].get('InvoiceID')
                                if t.invoice_payment_term_id:
                                    history_val = {
                                        "HistoryRecords": [
                                            {
                                                "Details": f'Payment Term - {t.invoice_payment_term_id.name}'
                                            },
                                        ]
                                    }
                                    parsed_dict = json.dumps(history_val)
                                    _logger.info("\n\nInvoice parsed_dict :   {} ".format(parsed_dict))
                                    url = f'https://api.xero.com/api.xro/2.0/Invoices/{response_data.get("Invoices")[0].get("InvoiceID")}/history'
                                    data = requests.request('POST', url=url, data=parsed_dict, headers=headers)

                                self._cr.commit()
                                _logger.info(_("Exported successfully to XERO"))
                        elif data.status_code == 400:
                            logs = self.env['xero.error.log'].create({
                                'transaction': 'Invoices Export',
                                'xero_error_response': data.text,
                                'error_date': fields.datetime.now(),
                                'record_id': t,
                            })
                            self._cr.commit()
                            self.show_error_message(data)
                        elif data.status_code == 401:
                            raise ValidationError(
                                "Time Out.\nPlease Check Your Connection or error in application or refresh token..!!")
                        else:
                            _logger.error(_('Something Went Wrong'))


                    else:
                        raise ValidationError(_("Only Posted state Invoice is exported to Xero."))



                elif self._context.get('cron'):
                    pass
                else:
                    raise ValidationError(
                        _("%s Invoice is already exported to Xero. Please, export a different invoice." % t.name))

            elif t.move_type == 'entry':  # Manual Journal Entry
                _logger.info(f'Export Journal Entry Data is------------>{t.name}')
                if not t.xero_invoice_id:
                    if t.state == 'posted':
                        values = t.prepare_manual_journal_export_dict()
                        parsed_dict = json.dumps(values)

                        _logger.info("\n\nPrepared Dictionary :   {} ".format(parsed_dict))

                        url = 'https://api.xero.com/api.xro/2.0/ManualJournals'
                        data = requests.request('POST', url=url, data=parsed_dict, headers=headers)
                        _logger.info("Response 2 From Server :{} ".format(data.status_code, ))

                        if data.status_code == 200:
                            response_data = json.loads(data.text)

                            if response_data.get('ManualJournals'):
                                # t.xero_invoice_number = response_data.get('ManualJournals')[0].get('ManualJournalID')
                                t.xero_invoice_id = response_data.get('ManualJournals')[0].get('ManualJournalID')
                                self._cr.commit()
                                _logger.info(_("Exported successfully to XERO"))

                        elif data.status_code == 400:
                            self._cr.commit()
                            self.show_error_message(data)

                        elif data.status_code == 401:
                            raise ValidationError(
                                "Time Out.\nPlease Check Your Connection or error in application or refresh token..!!")
                        
                        elif data.status_code == 429:
                                        raise ValidationError(
                                            f"[429] you have made too many requests in a short period. Please wait a while before trying again.")

                    else:
                        raise ValidationError(_("Only Posted state Invoice is exported to Xero."))
                else:
                    raise ValidationError(
                        _("%s Manual Journal is already exported to Xero. Please, export a different Manual Journal." % t.name))

        success_form = self.env.ref('pragmatic_odoo_xero_connector.export_successfull_view', False)
        return {
            'name': _('Notification'),
            'type': 'ir.actions.act_window',
            'view_type': 'form',
            'view_mode': 'form',
            'res_model': 'res.company.message',
            'views': [(success_form.id, 'form')],
            'view_id': success_form.id,
            'target': 'new',
        }

    def prepare_manual_journal_export_dict(self):

        vals = {}
        if self.state == 'posted':
            status = 'POSTED'

        narration = None
        if not self.ref:
            raise ValidationError(f"Add Reference For Journal Entry [{self.name}]")

        if self.ref:
            narration = self.ref

        if self.tax_state == 'no_tax':
            lineamounttype = 'NoTax'
        elif self.tax_state == 'inclusive':
            lineamounttype = 'Inclusive'
        elif self.tax_state == 'exclusive':
            lineamounttype = 'Exclusive'

        if self.date:
            date = str(self.date)

        #  Preparing Lines for export Journal
        journal_line_ids = []
        if self.line_ids:
            for line in self.line_ids:
                line_dict = {}

                line_amount = 0
                if line.credit > 0:
                    line_amount = -float(line.credit)
                elif line.debit > 0:
                    line_amount = float(line.debit)

                if line.account_id:
                    if line.account_id.xero_account_id:
                        account_code = line.account_id.code
                    else:
                        self.env['account.account'].create_account_ref_in_xero(line.account_id)
                        if line.account_id.xero_account_id:
                            account_code = line.account_id.code

                line_dict.update({
                    "Description": line.name,
                    "LineAmount": line_amount,
                    "AccountCode": account_code,
                })

                if not line.tax_ids:
                    line_dict.update({
                        "TaxType": "NONE",
                    })

                Tracking_list = []
                if line.analytic_distribution:
                    for analytic_dist_id in line.analytic_distribution:
                        analytic_account_id = self.env['account.analytic.account'].search(
                            [('id', '=', analytic_dist_id)])
                        analytic_account_id.create_analytic_account_in_xero(account_id=analytic_account_id.id)
                        Tracking_list.append({'Name': analytic_account_id.plan_id.name,
                                              'Option': analytic_account_id.name})

                line_dict.update({
                    'Tracking': Tracking_list
                })

                journal_line_ids.append(line_dict)

        vals.update({"JournalLines": journal_line_ids})
        vals.update({
            "Date": date,
            "Status": status,
            "Narration": narration,
            "LineAmountTypes": lineamounttype,
            "ShowOnCashBasisReports": "false"
        })

        return vals

    def remove_note_section(self, vals):
        if 'LineItems' in vals:
            vals.get('LineItems')[:] = [item for item in vals.get('LineItems') if
                                        'AccountCode' in item and item['AccountCode'] != None and item[
                                            'Quantity'] != 0.0]
        return vals

    @api.model
    def exportCreditNote(self, payment_export=None):
        xero_config = self.env['res.users'].search([('id', '=', self._uid)], limit=1).company_id
        if self._context.get('active_ids') and not payment_export:
            invoice = self.browse(self._context.get('active_ids'))
        else:
            invoice = self

        for t in invoice:
            if not t.xero_invoice_id:
                if t.state == 'posted':
                    values = t.prepare_credit_note_export_dict()
                    vals = self.remove_note_section(values)
                    parsed_dict = json.dumps(vals)
                    _logger.info(_("PARSED DICT : %s %s" % (parsed_dict, type(parsed_dict))))
                    url = 'https://api.xero.com/api.xro/2.0/CreditNotes?unitdp=4'
                    data = self.post_data(url, parsed_dict)
                    _logger.info('Response From Server : {}'.format(data.text))

                    if data.status_code == 200:

                        parsed_data = json.loads(data.text)
                        if parsed_data:
                            if parsed_data.get('CreditNotes'):
                                t.xero_invoice_number = parsed_data.get('CreditNotes')[0].get('CreditNoteNumber')
                                t.xero_invoice_id = parsed_data.get(
                                    'CreditNotes')[0].get('CreditNoteID')

                                if t.invoice_payment_term_id:
                                    headers = self.get_head()
                                    history_val = {
                                        "HistoryRecords": [
                                            {
                                                "Details": f'Payment Term - {t.invoice_payment_term_id.name}'
                                            },
                                        ]
                                    }
                                    parsed_dict = json.dumps(history_val)
                                    _logger.info("\n\nInvoice parsed_dict :   {} ".format(parsed_dict))
                                    url = f'https://api.xero.com/api.xro/2.0/Creditnotes/{parsed_data.get("CreditNotes")[0].get("CreditNoteID")}/history'
                                    data = requests.request('POST', url=url, data=parsed_dict, headers=headers)
                                self._cr.commit()
                                _logger.info(_("(CREATE) Exported successfully to XERO"))
                    elif data.status_code == 400:
                        logs = self.env['xero.error.log'].create({
                            'transaction': 'CreditNote Export',
                            'xero_error_response': data.text,
                            'error_date': fields.datetime.now(),
                            'record_id': t,
                        })
                        self._cr.commit()
                        self.show_error_message(data)
                    elif data.status_code == 401:
                        raise ValidationError(
                            "Time Out.\nPlease Check Your Connection or error in application or refresh token..!!")
                else:
                    raise ValidationError(_("Only Posted state Credit Notes is exported to Xero."))
            else:
                raise ValidationError(_(
                    "%s Credit Notes is already exported to Xero. Please, export a different credit note." % t.name))

        success_form = self.env.ref('pragmatic_odoo_xero_connector.export_successfull_view', False)
        return {
            'name': _('Notification'),
            'type': 'ir.actions.act_window',
            'view_type': 'form',
            'view_mode': 'form',
            'res_model': 'res.company.message',
            'views': [(success_form.id, 'form')],
            'view_id': success_form.id,
            'target': 'new',
        }

    def get_head(self):
        if self._context.get('cron'):
            xero_config = self.company_id
        else:
            xero_config = self.company_id
            if not xero_config:
                xero_config = self.env['res.users'].search([('id', '=', self._uid)], limit=1).company_id
        client_id = xero_config.xero_client_id
        client_secret = xero_config.xero_client_secret

        data = client_id + ":" + client_secret
        encodedBytes = base64.b64encode(data.encode("utf-8"))
        encodedStr = str(encodedBytes, "utf-8")
        headers = {
            'Authorization': "Bearer " + str(xero_config.xero_oauth_token),
            'Xero-tenant-id': xero_config.xero_tenant_id,
            'Accept': 'application/json'

        }
        return headers

    def post_data(self, url, parsed_dict):
        xero_config = self.env['res.users'].search([('id', '=', self._uid)], limit=1).company_id

        if xero_config.xero_oauth_token:
            token = xero_config.xero_oauth_token
        headers = self.get_head()

        if token:
            client_key = xero_config.xero_client_id
            client_secret = xero_config.xero_client_secret
            resource_owner_key = xero_config.xero_oauth_token
            resource_owner_secret = xero_config.xero_oauth_token_secret

            protected_url = url
            data = requests.request('POST', url=protected_url, data=parsed_dict, headers=headers)
        return data

    def show_error_message(self, data):

        response_data = json.loads(data.text)
        if response_data:
            if response_data.get('Elements'):
                for element in response_data.get('Elements'):
                    if element.get('ValidationErrors'):
                        for err in element.get('ValidationErrors'):
                            raise ValidationError(
                                '(Invoice/Vendor Bill/Credit Note) Xero Exception : ' + err.get('Message'))
            elif response_data.get('Message'):
                raise ValidationError(
                    '(Invoice/Vendor Bill/Credit Note) Xero Exception : ' + response_data.get('Message'))
            else:
                raise ValidationError(
                    '(Invoice/Vendor Bill/Credit Note) Xero Exception : please check xero logs in odoo for more details')

    @api.model
    def exportInvoice_cron(self):
        companys = self.env['res.company'].search([])
        self._context['cron'] = 1
        for xero_config in companys:
            if xero_config.xero_client_id and xero_config.xero_client_secret:
                xero_config.refresh_token()
                invoice_id = self.env['account.move'].search([
                    '|',
                    '&', ('invoice_date', '>', xero_config.export_record_after), ('xero_invoice_id', '=', False),
                    '&', ('date', '>', xero_config.export_record_after), ('xero_invoice_id', '=', False),
                    ('state', '=', 'posted'),
                    ('company_id', '=', xero_config.id)
                ])
                # invoice_id = self.env['account.move'].search(
                #     ['&', '&', ('invoice_date', '>', xero_config.export_record_after),
                #      ('xero_invoice_id', '=', False),
                #      ('state', '=', 'posted'), ('company_id', '=', xero_config.id),
                #      ])


                if xero_config.skip_stock_journal_entry:
                    operation_type_list = [operation_type.type for operation_type in
                                           xero_config.operation_type_ids]

                ref_string_list = []
                if xero_config.skip_je_if_contains:
                    ref_string_list = xero_config.skip_je_if_contains.split(',')
            else:
                continue

            for invoice in invoice_id:
                _logger.info(_(f"Export Invoice Or Journal Entry-----{invoice.id}"))
                if not invoice.xero_invoice_id:
                    if invoice.move_type == 'entry':
                        if invoice.journal_id.type == 'general':
                            if ref_string_list:
                                list_skip = []
                                for ref_string in ref_string_list:
                                    pattern = r"\b" + re.escape(ref_string.lower()) + r"\b"
                                    if re.search(pattern, invoice.ref.lower()):
                                        list_skip.append('Match Entry')
                                if not 'Match Entry' in list_skip:
                                    if xero_config.skip_stock_journal_entry and invoice.ref:
                                        try:
                                            type_str = invoice.ref.split(" - ")[0].split("/")[1]
                                        except:
                                            type_str = False
                                        if type_str:
                                            if invoice.journal_id.id == xero_config.journal.id and type_str in operation_type_list:
                                                pass
                                            else:
                                                invoice.exportInvoice()
                                        else:
                                            invoice.exportInvoice()
                                    else:
                                        invoice.exportInvoice()
                                else:
                                    _logger.info(f"Skip Quantity Update REf REcord for ID----{invoice.id}")
                            else:
                                if xero_config.skip_stock_journal_entry and invoice.ref:
                                    try:
                                        type_str = invoice.ref.split(" - ")[0].split("/")[1]
                                    except:
                                        type_str = False
                                    if type_str:
                                        if invoice.journal_id.id == xero_config.journal.id and type_str in operation_type_list:
                                            pass
                                        else:
                                            invoice.exportInvoice()
                                    else:
                                        invoice.exportInvoice()
                                else:
                                    invoice.exportInvoice()
                    else:
                        invoice.exportInvoice()


class InvoiceLine(models.Model):
    _inherit = 'account.move.line'

    xero_invoice_line_id = fields.Char(string="Xero Id", copy=False)
    inclusive = fields.Boolean('Inclusive', default=False, copy=False)

    @api.model_create_multi
    def create(self, vals_list):

        lines = super(InvoiceLine, self).create(vals_list)
        to_process = lines.filtered(lambda
                                        line: line.move_id.journal_id.name == 'Vendor Bills' and line.product_id.type == 'product' and not line.xero_invoice_line_id)

        # Nothing to process, break.
        if not to_process:
            return lines

        company_id = self.env['res.users'].search([('id', '=', self._uid)], limit=1).company_id
        if not company_id.non_tracked_item:
            for inv_line in to_process:
                if not inv_line.product_id.categ_id.xero_inventory_account:
                    raise UserError(_("Please Set XERO Inventory Account Field In Product Category "))
                # inv_line.account_id = inv_line.product_id.categ_id.xero_inventory_account
        return lines
