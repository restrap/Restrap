from odoo import models, fields, api, _
import logging
import json
import base64
import requests
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    xero_sale_id = fields.Char(string="Xero SO Id", copy=False)
    tax_state = fields.Selection([('inclusive', 'Tax Inclusive'), ('exclusive', 'Tax Exclusive'), ('no_tax', 'No Tax')],
                                 string='Tax Status', default='exclusive')
    inclusive = fields.Boolean('Inclusive')

    @api.onchange('tax_state', 'inclusive')
    def update_inclusive_flag(self):
        for line in self.order_line:
            if self.tax_state == 'inclusive':
                line.write({"inclusive": True})
            elif self.tax_state == 'exclusive':
                line.write({'inclusive': False})

    # def write(self, vals):
    #     super(SaleOrder, self).write(vals)
    #     id = self.invoice_ids.ids
    #     if id and not 1 in id:
    #         id.append(1)
    #         self.write_ids(id)
    #     return

    def write_ids(self, id):
        self.write({
            'invoice_ids': [(6, 0, id)]
        })
        id = self.invoice_ids.ids
        return

    def get_head(self):
        if self._context.get('not_cron') or self._context.get('cron'):
            xero_config = self.company_id
        else:
            xero_config = self.company_id
            if not xero_config:
                xero_config = self.env['res.users'].search([('id', '=', self._uid)], limit=1).company_id
        # client_id = xero_config.xero_client_id
        # client_secret = xero_config.xero_client_secret

        # data = client_id + ":" + client_secret
        # encodedBytes = base64.b64encode(data.encode("utf-8"))
        # encodedStr = str(encodedBytes, "utf-8")
        headers = {
            'Authorization': "Bearer " + str(xero_config.xero_oauth_token),
            'Xero-tenant-id': xero_config.xero_tenant_id,
            'Accept': 'application/json'

        }
        return headers

    def exportSaleOrder_cron(self):
        """export Quotations cron ODOO to XERO"""
        companys = self.env['res.company'].search([])
        self._context['cron'] = 1
        for xero_config in companys:
            if xero_config.xero_client_id and xero_config.xero_client_secret:
                xero_config.refresh_token()
                valid_quotations = self.search(
                    [('date_order', '>', xero_config.export_record_after), ('company_id', '=', xero_config.id),
                     ('state', '=', 'sale')])
                if valid_quotations:
                    for quotation in valid_quotations:
                        if not quotation.xero_sale_id:
                            _logger.info('Creating quotation through cron__________{}'.format(quotation.name))
                            self.create_quotation_main(quotation, xero_config, update=False, cron=True)
                        else:
                            _logger.info('Updating quotation through cron__________{}'.format(quotation.name))
                            self.create_quotation_main(quotation, xero_config, update=True, cron=True)
                else:
                    _logger.warning('\n\nNo record found for date {}'.format(xero_config.export_record_after))
            else:
                continue

    def create_quotation_in_xero(self):

        """export Quotations ODOO to XERO"""
        xero_config = self.company_id
        if not xero_config:
            xero_config = self.env['res.users'].search([('id', '=', self._uid)], limit=1).company_id
        if self._context.get('active_ids'):
            quotation = self.browse(self._context.get('active_ids'))
        else:
            quotation = self
        try:
            for quot in quotation:
                if not quot.xero_sale_id:
                    _logger.info("Creating new quotations in xero____________")
                    self.create_quotation_main(quot, xero_config, update=False)
                else:
                    _logger.info("Quotation {} is already exported, Updating it : ".format(quot.name))
                    self.create_quotation_main(quot, xero_config, update=True)

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

        except Exception as e:
            _logger.info("(Odoo) Exception : {}".format(e))
            raise ValidationError('Excepiton : {}'.format(e))

    # CREATE QUOTATION IN XERO
    def create_quotation_main(self, quot, xero_config, update=False, cron=False):
        computed_dict = quot.prepare_export_dict_for_quotation(update=update)
        parsed_dict = json.dumps(computed_dict)
        # _logger.info("computed_dict : {} ".format(parsed_dict))

        token = None
        if xero_config.xero_oauth_token:
            token = xero_config.xero_oauth_token
        if quot:
            self = quot
        headers = self.get_head()
        if token:
            protected_url = 'https://api.xero.com/api.xro/2.0/Quotes'
            data = requests.request('POST', url=protected_url, data=parsed_dict, headers=headers)
            # _logger.info("DATA : {}->{}".format(data, data.text))
            if data.status_code == 200:
                response_data = json.loads(data.text)
                if response_data.get('Quotes'):
                    if response_data.get('Quotes')[0].get('QuoteID'):
                        quot.update({'xero_sale_id': response_data.get('Quotes')[0].get('QuoteID')})
                        if update:
                            _logger.info("Quotation '{}' Updated successfully".format(
                                response_data.get('Quotes')[0].get('QuoteNumber')))
                        else:
                            _logger.info("Quotation '{}' exported successfully".format(
                                response_data.get('Quotes')[0].get('QuoteNumber')))

            elif data.status_code == 400:
                response_data = json.loads(data.text)
                if response_data:
                    if response_data.get('Elements'):
                        for element in response_data.get('Elements'):
                            if element.get('ValidationErrors'):
                                for err in element.get('ValidationErrors'):
                                    if err.get('Message'):
                                        if cron:
                                            _logger.warning("(Quot) Xero Exception : {}".format(err.get('Message')))
                                        else:
                                            if len(self._context.get('active_ids')) > 1:
                                                _logger.warning("(Quot) Xero Exception : {}".format(err.get('Message')))
                                            else:
                                                raise ValidationError(
                                                    '(Quot) Xero Exception : ' + err.get('Message'))

            elif data.status_code == 401:
                if cron:
                    _logger.warning(
                        'Time Out.\nPlease Check Your Connection or error in application or refresh token..!!')
                else:
                    raise ValidationError(
                        "Time Out.\nPlease Check Your Connection or error in application or refresh token..!!")

    def prepare_export_dict_for_quotation(self, update=False):
        #########################################################################
        # Xero Quotation Dict For reference                                     #
        #########################################################################
        # {                                                                     #
        #     "QuoteNumber": "QU-1068",                                         #
        #     "Reference": "REF-90092",                                         #
        #     "Terms": "Quote is valid for 30 business days",                   #
        #     "Contact": {                                                      #
        #         "ContactID": "6d42f03b-181f-43e3-93fb-2025c012de92",          #
        #         "ContactName": "John Hammond"                                 #
        #     },                                                                #
        #     "LineItems": [                                                    #
        #         {                                                             #
        #             "Description": "Jurassic Park Colouring Book",            #
        #             "UnitAmount": 12.50,                                      #
        #             "LineAmount": 12.50,                                      #
        #             "ItemCode": "BOOK",                                       #
        #             "Quantity": 1.0000                                        #
        #         }                                                             #
        #     ],                                                                #
        #     "Date": "2019-11-29",                                             #
        #     "ExpiryDate": "2019-12-29",                                       #
        #     "Status": "SENT",                                                 #
        #     "CurrencyCode": "NZD",                                            #
        #     "SubTotal": 12.50,                                                #
        #     "TotalTax": 0.00,                                                 #
        #     "Total": 12.50,                                                   #
        #     "Title": "Quote for product sale",                                #
        #     "Summary": "Sale of book",                                        #
        #     "Tracking": [],                                                   #
        #     "LineAmountTypes": "EXCLUSIVE"                                    #
        # }                                                                     #
        #########################################################################

        dict = {}
        if update:
            if self.xero_sale_id:
                dict.update({'QuoteID': self.xero_sale_id})

        if self.name:
            dict.update({"QuoteNumber": self.name})

        if self.partner_id:
            if not self.partner_id.xero_cust_id:
                _logger.info('Creating Customer in xero')
                self.partner_id.create_customer_in_xero()

            if self.partner_id.xero_cust_id:
                contact_dict = {
                    'ContactID': self.partner_id.xero_cust_id,
                    'ContactName': self.partner_id.name
                }
                dict.update({
                    'Contact': contact_dict
                })

        if self.client_order_ref:
            dict.update({'Reference': self.client_order_ref})

        # set state for each quotation
        if self.state == 'draft':
            dict.update({'Status': 'DRAFT'})
        elif self.state == 'sent':
            dict.update({'Status': 'SENT'})
        elif self.state == 'sale':
            dict.update({'Status': 'ACCEPTED'})
        elif self.state == 'cancel':
            dict.update({'Status': 'DECLINED'})

        if self.note:
            dict.update({'Terms': self.note})

        # Quotation order lines
        if self.order_line:
            order_lines = self.order_line
            order_lines_list = []
            for line in order_lines:
                if not line.product_id.xero_product_id:
                    _logger.info(
                        'Creating Product {} in xero____________ {}'.format(line.product_id, line.product_id.name))
                    line.product_id.create_single_product_in_xero(line.product_id)

                if line.product_id.xero_product_id:
                    if len(line.tax_id) > 1:
                        raise ValidationError("Please select only one tax for line product")
                    tax_id = False
                    if self.tax_state == 'inclusive':
                        tax_id = self.env['account.tax'].search(
                            [('type_tax_use', '=', 'sale'), ('price_include', '=', True), ('id', '=', line.tax_id.id)],
                            limit=1)
                    if self.tax_state == 'exclusive':
                        tax_id = self.env['account.tax'].search(
                            [('type_tax_use', '=', 'sale'), ('price_include', '=', False), ('id', '=', line.tax_id.id)],
                            limit=1)

                    line_dict = {
                        "Description": line.name,
                        "UnitAmount": line.price_unit,
                        "LineAmount": line.price_subtotal,
                        "DiscountRate": line.discount,
                        "ItemCode": line.product_id.default_code or False,
                        "Quantity": line.product_uom_qty,
                    }
                    if tax_id:
                        line_dict.update({"TaxType": tax_id.xero_tax_type_id if tax_id else False, })

                    order_lines_list.append(line_dict)
            dict.update({'LineItems': order_lines_list})

        if self.tax_state == 'inclusive':
            dict.update({'LineAmountTypes': 'INCLUSIVE'})
        elif self.tax_state == 'exclusive':
            dict.update({'LineAmountTypes': 'EXCLUSIVE'})

        if self.date_order:
            dict.update({'date': str(self.date_order)})

        if self.validity_date:
            dict.update({'ExpiryDate': str(self.validity_date)})

        if self.company_id:
            dict.update({'CurrencyCode': self.company_id.currency_id.name})

        dict.update({
            'SubTotal': self.amount_untaxed,
            'TotalTax': self.amount_tax,
            'Total': self.amount_total
        })

        currency = self.currency_id if self.currency_id else False
        if currency:
            dict.update({"CurrencyCode": currency.name})

        return dict


class SaleOderLine(models.Model):
    _inherit = 'sale.order.line'

    xero_sale_line_id = fields.Char(string="Xero Id", copy=False)
    inclusive = fields.Boolean('Inclusive', default=False, copy=False)
