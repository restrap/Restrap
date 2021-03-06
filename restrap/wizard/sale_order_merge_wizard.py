from odoo import api, fields, models, _
from odoo.exceptions import UserError


class SaleOrderMergeWizard(models.TransientModel):
    _name = 'sale.order.merge.wizard'

    line_ids = fields.One2many('sale.order.merge.wizard.line', 'wizard_id', string="Lines")
    order_ids = fields.Many2many('sale.order', string="Sale Orders")

    @api.model
    def default_get(self, fields_list):
        res = super(SaleOrderMergeWizard, self).default_get(fields_list)
        active_ids = self._context.get('active_ids', [])
        orders = self.env['sale.order'].browse(active_ids)
        already_merged_orders = orders.filtered(lambda o: o.merged)
        unconfirmed_orders = orders.filtered(lambda o: o.state != 'sale')
        # Restriction: Check if any order in not in "Sale Order" state
        if unconfirmed_orders:
            raise UserError("Only confirmed Sales Orders can be merged."
                            " Please confirm the following orders to proceed. \n %s" %
                            ", ".join(unconfirmed_orders.mapped("name")))
        # Restriction: check if any order is merged before
        if already_merged_orders:
            raise UserError("The following Sales Order(s) are already merged. \n %s" %
                            ", ".join(already_merged_orders.mapped("name")))

        order_lines = orders.mapped('order_line')
        products = order_lines.mapped('product_id').filtered(lambda p: p.type in ['product', 'consu'])
        product_list = []
        for product in products:
            combined_qty = sum(line.product_uom_qty for line in order_lines.filtered(lambda l: l.product_id == product))
            product_values = {
                'product_id': product.id,
                'product_qty': combined_qty,
            }
            product_list.append((0, 0, product_values))
        res.update({'order_ids': orders.ids, 'line_ids': product_list})
        return res

    # On wizard confirmation, system will create a MO for each line
    def action_confirm(self):
        plan_id = self.env['restrap.mrp.plan'].sudo().create({}).id
        for line in self.line_ids:
            if not line.date_planned_start:
                raise UserError("Please add scheduled date.")
            product_id = line.product_id
            order = self.env['mrp.production'].create({
                'product_id': product_id.id,
                'product_uom_id': product_id.uom_id.id,
                'date_planned_start': line.date_planned_start,
                'reference': line.reference,
            })
            order._onchange_product_id()
            order._onchange_bom_id()
            order.product_qty = line.product_qty
            order._onchange_product_qty()
            order._onchange_date_planned_start()
            order._onchange_move_raw()
            order._onchange_workorder_ids()
            order._onchange_move_finished()
            order.workorder_ids.write({'restrap_plan_id': plan_id})
            # Check if split option is checked and call action_split() in mrp.production
            if line.split:
                order.with_context(plan_id=plan_id).action_spilt()
        self.order_ids.write({'merged': True})


class SaleOrderMergeWizardLine(models.TransientModel):
    _name = 'sale.order.merge.wizard.line'

    wizard_id = fields.Many2one('sale.order.merge.wizard', string="Wizard")
    product_id = fields.Many2one('product.product', string="Product", required=True)
    product_qty = fields.Float(string="Combined Quantity")
    date_planned_start = fields.Datetime(string="Scheduled Date")
    split = fields.Boolean(string="Split Manufacture Order")
    reference = fields.Selection([('a', 'A'), ('b', 'B'), ('c', 'C')], string="Reference")
