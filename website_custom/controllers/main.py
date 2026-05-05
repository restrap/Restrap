from odoo import http
from odoo.http import request
import json
import re
class PaymentControllenedfr(http.Controller):

    @http.route('/collect-payment', type='json', auth='public', methods=['GET', 'POST'],)
    def collect_payment(self, **kwargs):
        current_domain = request.httprequest.host
        base_url = request.httprequest.host_url
        data = json.loads(http.request.httprequest.data.decode('utf-8'))
        current_url = data.get('current_url')
        main_product = (data.get('product_id_variant_ids'))
        main_product_tmpl = (data.get('product_id'))
        product_id_variant = data.get('product_id_variant')
        base_url = base_url[:-1]
        website = request.env['website'].get_current_website()
        website2 = request.env['website'].search([("domain","=",base_url)])
        response_data = website2.allow_out_of_stock_order
        qty = 0
        qty2 = 0
        
        if product_id_variant:
            product = request.env['product.product'].sudo().search([('id', '=', product_id_variant)])
            stock1 = request.env['stock.quant'].sudo().search([('product_id', '=', product.id)])
            for stock in stock1:
                if website2.warehouse_id.view_location_id == stock.location_id.location_id:
                    qty2 = stock.inventory_quantity_auto_apply - stock.reserved_quantity
        if main_product:
            product_s = request.env['product.template.attribute.value'].sudo().search([('id', '=', main_product)])
            stock22 = request.env['product.product'].sudo().search([('product_template_variant_value_ids', '=', product_s.id)])
            for stock2 in stock22:
                stock3 = request.env['stock.quant'].sudo().search([('product_id', '=', stock2.id),('location_id', '=', website2.warehouse_id.lot_stock_id.id)])
            #qty2 = stock2.free_qty
                if stock3:
                    for stock34 in stock3:
                        qty2 = stock34.inventory_quantity_auto_apply - stock34.reserved_quantity
                else:
                    qty2 = 0
                

        if qty2 <= 0 and response_data != True:
            return False
        else:
            return True 

        

