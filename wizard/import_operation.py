from odoo import api, fields, models

class ImportOperation(models.TransientModel):
    _inherit = 'import.operation'

    object = fields.Selection(
        selection_add=[
            ('product.attribute','Attributes')
        ]
    )

    magento2x_filter_type = fields.Selection(
        selection=[
            ('date_range','Date Range'),
            ('id_range', 'ID Range'),
            ('category_id', 'Category ID'),
            ('customer_id', 'Customer Email'),
            ('store_id', 'Store ID'),
            ('order_state', 'Order State')
        ]
    )
    magento2x_start_date = fields.Datetime("From Magento Date")
    magento2x_end_data = fields.Datetime("Till Magento Date")
    magento2x_start_id = fields.Integer('From ID')
    magento2x_end_id = fields.Integer('Till ID')
    magento2x_category_id = fields.Integer('Category ID',help="Get product which belongs to this category ID")
    magento2x_customer_email = fields.Char('Customer Email', help="Get Orders made by specific customers",size=30)
    magento2x_order_state = fields.Selection([('pending','Pending'),('done','Done')])
    # magento2x_store_id = fields.Character('Store ID', help="Get Orders")
    #more filter types to be implemented

    def magento2x_get_filter(self):
        kw = {'filter_on':self.magento2x_filter_type}
        if self.magento2x_start_date or self.magento2x_end_data:
            kw['start_date'] = self.magento2x_start_date
            kw['end_date'] = self.magento2x_end_data
        elif self.magento2x_start_id or self.magento2x_end_id:
            kw.update(
                start_id=self.magento2x_start_id,
                end_id=self.magento2x_end_id
            )
        elif self.magento2x_category_id:
            kw.update(
                category_id=self.magento2x_category_id
            ) 
        elif self.magento2x_customer_email:
            kw.update(
                customer_email=self.magento2x_customer_email
            )
        elif self.magento2x_order_state:
            kw.update(
                order_state=self.magento2x_order_state
            )
        return kw

