from odoo import api, fields, models

class ImportOperation(models.TransientModel):
    _inherit = 'export.operation'

    object = fields.Selection(
        selection_add=[
            ('product.attribute','Attributes')
        ]
    )

    def export_button(self):
        if self.object == 'product.attribute' and self.channel_id.channel == "magento2x":
            return self.channel_id.export_magento2x_attributes()
        else:
            return super().export_button()