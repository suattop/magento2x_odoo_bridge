# -*- coding: utf-8 -*-
#################################################################################
#
#    Copyright (c) 2017-Present Webkul Software Pvt. Ltd. (<https://webkul.com/>)
#    You should have received a copy of the License along with this program.
#    If not, see <https://store.webkul.com/license.html/>
#################################################################################
from odoo import api, fields, models, _

class StockMove(models.Model):
    _inherit = "stock.move"

    def multichannel_sync_quantity(self, pick_details):
        channel_list = self._context.get('channel_list')
        if not channel_list:
            channel_list = list()
        channel_list.append('magento2x')
        return super(
            StockMove,self.with_context(
                channel_list=channel_list)
                ).multichannel_sync_quantity(pick_details)