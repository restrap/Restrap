
from odoo import models, fields, api,_
from odoo.exceptions import ValidationError
import requests
import base64
import json
import re

import logging
_logger = logging.getLogger(__name__)

class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    xero_purchase_id = fields.Char(string="Xero PO Id",copy=False)
    tax_state = fields.Selection([('inclusive', 'Tax Inclusive'), ('exclusive', 'Tax Exclusive'), ('no_tax', 'No Tax')],
                                 string='Tax Status', default='exclusive')

    @api.model
    @api.onchange('tax_state')
    def onchange_tax_status(self):
        for line_id in self.order_line:
            if (self.tax_state == 'inclusive'):
                line_id.inclusive = True
            elif (self.tax_state == 'exclusive'):
                line_id.inclusive = False

    @api.model
    def prepare_purchaseorder_export_line_dict(self, line):
        #         line = self
        company = self.env['res.users'].search([('id', '=', self._uid)], limit=1).company_id
        line_vals = {}

        if self.partner_id:
            if line.taxes_id:
                line_tax = self.env['account.tax'].search([('id', '=', line.taxes_id.id),('company_id','=',company.id)])
                if line_tax:
                    tax = line_tax.xero_tax_type_id
                    if not tax:
                        self.env['account.tax'].get_xero_tax_ref(line_tax)
                        line_tax = self.env['account.tax'].search([('id', '=', line.taxes_id.id),('company_id','=',company.id)])
                        tax = line_tax.xero_tax_type_id

                    line_vals = {
                                'Description': line.name,
                                'UnitAmount': line.price_unit,
                                'ItemCode': line.product_id.default_code,
                                'Quantity': line.product_qty,
                                'TaxType': tax,
                                "DiscountRate": line.discount,
                                }
            else:
                if line.product_id:
                    line_vals = {
                        'Description': line.name,
                        'UnitAmount': line.price_unit,
                        'ItemCode': line.product_id.default_code,
                        'Quantity': line.product_qty,
                        "DiscountRate": line.discount,
                    }
                else:
                    line_vals = {
                        'Description': line.name,
                        "DiscountRate": line.discount
                        # 'UnitAmount': line.price_unit,
                        # 'ItemCode': line.product_id.default_code,
                        # 'Quantity': line.product_qty,
                    }

        return line_vals

    @api.model
    def prepare_purchaseorder_export_dict(self):
        company = self.company_id
        if not company:
            company = self.env['res.users'].search([('id', '=', self._uid)], limit=1).company_id

        if self.partner_id:
            cust_id = self.env['res.partner'].get_xero_partner_ref(self.partner_id)

        vals = {}
        lst_line = []
        if self.tax_state:
            if self.tax_state == 'inclusive':
                tax_state = 'Inclusive'
            elif self.tax_state == 'exclusive':
                tax_state = 'Exclusive'
            elif self.tax_state == 'no_tax':
                tax_state = 'NoTax'

        if self.state:
            if self.state == 'draft' or self.state == 'sent':
                status = 'DRAFT'
            elif self.state == 'purchase':
                status = 'AUTHORISED'
            else:
                status = 'DRAFT'

        if self.partner_ref:
            partner_ref = self.partner_ref
        else:
            partner_ref = ''

        def remove_tags(text):
            """
            Removes html test from string
            :param text:
            :return: new string
            """
            TAG_RE = re.compile(r'<[^>]+>')
            return TAG_RE.sub('', text)

        if self.notes:
            notes = remove_tags(self.notes)
        else:
            notes = ''


        if len(self.order_line) == 1:
            single_line = self.order_line

            if single_line.product_id.xero_product_id:
                _logger.info(_("PRODUCT DEFAULT CODE AVAILABLE"))
            elif not single_line.product_id.xero_product_id:
                self.env['product.product'].get_xero_product_ref(single_line.product_id)
            if single_line.taxes_id:
                line_tax = self.env['account.tax'].search([('id', '=', single_line.taxes_id.id),('company_id','=',company.id)])
                if line_tax:
                    tax = line_tax.xero_tax_type_id
                    # product = self.env['product.template'].get_xero_product_ref(single_line.product_id)
                    if not tax:
                        self.env['account.tax'].get_xero_tax_ref(line_tax)
                        line_tax = self.env['account.tax'].search([('id', '=', single_line.taxes_id.id),('company_id','=',company.id)])
                        tax = line_tax.xero_tax_type_id

                    vals.update({
                        "Contact": {"ContactID": cust_id},
                        "Date": str(self.date_order),
                        "PurchaseOrderNumber": self.name,
                        "DeliveryDate": str(self.date_planned) if self.date_planned else '',
                        "DeliveryInstructions":notes,
                        "Reference": partner_ref,
                        # "DeliveryAddress":address5,
                        "LineAmountTypes": tax_state,
                        "LineItems": [
                            {
                                "ItemCode":single_line.product_id.default_code,
                                "Description": single_line.name,
                                "Quantity": single_line.product_qty,
                                "UnitAmount": single_line.price_unit,
                                "TaxType":tax,
                                "DiscountRate": single_line.discount,
                            }
                        ],
                        "Status": status,
                    })
            else:
                vals.update({
                    "Contact": {"ContactID": cust_id},
                    "Date": str(self.date_order),
                    "PurchaseOrderNumber": self.name,
                    "DeliveryDate": str(self.date_planned) if self.date_planned else '',
                    # "DeliveryAddress": address5,
                    "DeliveryInstructions": notes,
                    "Reference": partner_ref,
                    "LineAmountTypes": tax_state,
                    "LineItems": [
                        {
                            "ItemCode": single_line.product_id.default_code,
                            "Description": single_line.name,
                            "Quantity": single_line.product_qty,
                            "UnitAmount": single_line.price_unit,
                            "DiscountRate": single_line.discount,
                        }
                    ],
                    "Status": status,
                })

        else:
            for line in self.order_line:

                if line.product_id.xero_product_id:
                    _logger.info(_("PRODUCT DEFAULT CODE AVAILABLE"))
                elif not line.product_id.xero_product_id:
                    self.env['product.product'].get_xero_product_ref(line.product_id)

                line_vals = self.prepare_purchaseorder_export_line_dict(line)
                lst_line.append(line_vals)
            vals.update({
                        "Contact": {"ContactID": cust_id},
                        "Date": str(self.date_order),
                        "PurchaseOrderNumber":self.name,
                        # "DeliveryAddress": address5,
                        "DeliveryDate": str(self.date_planned) if self.date_planned else '',
                        "Reference": partner_ref ,
                        "DeliveryInstructions": notes,
                        "LineAmountTypes": tax_state,
                        "LineItems": lst_line,
                        "Status": status
                    })
        currency = self.currency_id if self.currency_id else False
        if currency:
            vals.update({"CurrencyCode": currency.name})
        return vals

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

    @api.model
    def exportPurchaseOrder(self):
        """export purchase order to QBO"""
        xero_config = self.company_id
        if not xero_config:
            xero_config = self.env['res.users'].search([('id', '=', self._uid)], limit=1).company_id
        if self._context.get('active_ids'):
            purchase = self.browse(self._context.get('active_ids'))
        else:
            purchase = self
        if purchase and self._context.get('not_cron'):
            xero_config = purchase[0].company_id
        for t in purchase:
            if not t.xero_purchase_id:
                vals = t.prepare_purchaseorder_export_dict()
                parsed_dict = json.dumps(vals)
                if xero_config.xero_oauth_token:
                    token = xero_config.xero_oauth_token
                headers = self.get_head()
                if token:
                    protected_url = 'https://api.xero.com/api.xro/2.0/PurchaseOrders'
                    data = requests.request('POST', url=protected_url, data=parsed_dict, headers=headers)
                    if data.status_code == 200:
                        response_data = json.loads(data.text)
                        if response_data.get('PurchaseOrders'):
                                t.xero_purchase_id = response_data.get('PurchaseOrders')[0].get('PurchaseOrderID')
                                self._cr.commit()
                        _logger.info(_("Exported successfully to XERO"))
                    elif data.status_code == 400:
                        logs = self.env['xero.error.log'].create({
                            'transaction': 'Purchase Order Export',
                            'xero_error_response': data.text,
                            'error_date': fields.datetime.now(),
                            'record_id': t,
                        })
                        self._cr.commit()
                        response_data = json.loads(data.text)
                        if response_data:
                            if response_data.get('Elements'):
                                for element in response_data.get('Elements'):
                                    if element.get('ValidationErrors'):
                                        for err in element.get('ValidationErrors'):
                                            if err.get('Message'):
                                                raise ValidationError('(Purchase Order) Xero Exception : ' + err.get('Message'))
                            elif response_data.get('Message'):
                                raise ValidationError(
                                    '(Purchase Order) Xero Exception : ' + response_data.get('Message'))
                            else:
                                raise ValidationError(
                                    '(Purchase Order) Xero Exception : please check xero logs in odoo for more details')
                    elif data.status_code == 401:
                        raise ValidationError("Time Out.\nPlease Check Your Connection or error in application or refresh token..!!")
            else:
                vals = t.prepare_purchaseorder_export_dict()
                parsed_dict = json.dumps(vals)
                if xero_config.xero_oauth_token:
                    token = xero_config.xero_oauth_token
                headers=self.get_head()
                if token:
                    protected_url = 'https://api.xero.com/api.xro/2.0/PurchaseOrders/'+t.xero_purchase_id
                    data = requests.request('POST', url=protected_url, headers=headers, data=parsed_dict)
                    if data.status_code == 200:
                            _logger.info(_("Exported successfully to XERO"))
                    elif data.status_code == 400:
                        logs = self.env['xero.error.log'].create({
                            'transaction': 'Purchase Order Export',
                            'xero_error_response': data.text,
                            'error_date': fields.datetime.now(),
                            'record_id': t,
                        })
                        self._cr.commit()
                        response_data = json.loads(data.text)
                        if response_data:
                            if response_data.get('Elements'):
                                for element in response_data.get('Elements'):
                                    if element.get('ValidationErrors'):
                                        for err in element.get('ValidationErrors'):
                                            if err.get('Message'):
                                                raise ValidationError('(Purchase Order) Xero Exception : ' + err.get('Message'))
                            elif response_data.get('Message'):
                                raise ValidationError(
                                    '(Purchase Order) Xero Exception : ' + response_data.get('Message'))
                            else:
                                raise ValidationError(
                                    '(Purchase Order) Xero Exception : please check xero logs in odoo for more details')
                    elif data.status_code == 401:
                        raise ValidationError("Time Out.\nPlease Check Your Connection or error in application or refresh token..!!")
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

    @api.model
    def exportPurchaseOrder_cron(self):
        # xero_config = self.env['res.users'].search([('id', '=', self._uid)], limit=1).company_id
        companys = self.env['res.company'].search([])
        self._context['cron'] = 1
        for xero_config in companys:
            if xero_config.xero_client_id and xero_config.xero_client_secret:
                xero_config.refresh_token()
                purchase_id = self.env['purchase.order'].search([('date_approve', '>', xero_config.export_record_after),('company_id', '=', xero_config.id),('state', '=', 'purchase'),('xero_purchase_id', '=', False)])
                for purchase in purchase_id:
                    purchase.exportPurchaseOrder()
            else:
                continue


class PurchaseOderLine(models.Model):
    _inherit = 'purchase.order.line'

    xero_purchase_line_id = fields.Char(string="Xero Id",copy=False)
    inclusive = fields.Boolean('Inclusive', default=False,copy=False)
