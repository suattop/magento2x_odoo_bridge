# -*- coding: utf-8 -*-
#################################################################################
#
#   Copyright (c) 2017-Present Webkul Software Pvt. Ltd. (<https://webkul.com/>)
#   See LICENSE URL <https://store.webkul.com/license.html/> for full copyright and licensing details.
#################################################################################

from odoo import api,fields, models,_

class MagentoAttributesSet(models.Model):
    _rec_name='set_name'
    _name = "magento.attributes.set"
    _description = "Magento Attributes Set"
    _inherit = ['channel.mappings']

    set_name = fields.Char(
        string = 'Set Name'
    )
    attribute_ids = fields.Many2many(
        'product.attribute',
        string='Attribute(s)',
    )


    @api.model
    def default_get(self,fields):
        res=super(MagentoAttributesSet,self).default_get(fields)
        if self._context.get('wk_channel_id'):
            res['channel_id']=self._context.get('wk_channel_id')
        return res