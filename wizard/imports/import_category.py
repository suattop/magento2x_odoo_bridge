# -*- coding: utf-8 -*-
#################################################################################
#
#   Copyright (c) 2017-Present Webkul Software Pvt. Ltd. (<https://webkul.com/>)
#   See LICENSE URL <https://store.webkul.com/license.html/> for full copyright and licensing details.
#################################################################################
import logging
_logger = logging.getLogger(__name__)
from odoo import api, fields, models, _

class Importmagento2xCategories(models.TransientModel):
    _inherit = ['import.categories']

    @staticmethod
    def magento2x_extract_categ_data(data,channel_id,**kwargs):
        parent_id = int(data.get('parent_id'))
        if parent_id == 1:
            parent_id = None
        return [(
            data.get('id'),
            dict(
            channel_id=channel_id,
            name=data.get('name'),
            store_id=data.get('id'),
            parent_id=parent_id and parent_id or None
            )
        )]
        
    
    def magento2x_get_product_categ_data(self,data,channel_id):
        res=[]
        child =len(data.get('children_data'))
        index = 0
        while len(data.get('children_data'))>0:
            item = data.get('children_data')[index]
            res +=self.magento2x_get_product_categ_data(item,channel_id)
            res+=self.magento2x_extract_categ_data(data.get('children_data').pop(index),channel_id)
        return res

    def import_now(self, channel_id, sdk,kwargs):
        fetch_res =sdk.get_categories()
        categories = fetch_res.get('data') or {}
        kwargs.update(page_size=10000) #making it infinity for breaking pagination loop at base module
        message = fetch_res.get('message','')
        if not categories:
            message+="Category data not received."
            kwargs.update(
                message=message
            )
            return []
        else:
            categ_items = dict(self.magento2x_get_product_categ_data(categories,channel_id.id)+self.magento2x_extract_categ_data(categories,channel_id.id))
            return list(categ_items.values())
