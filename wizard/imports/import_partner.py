# -*- coding: utf-8 -*-
#################################################################################
#
#   Copyright (c) 2017-Present Webkul Software Pvt. Ltd. (<https://webkul.com/>)
#   See LICENSE URL <https://store.webkul.com/license.html/> for full copyright and licensing details.
#################################################################################
import logging
from math import ceil
_logger = logging.getLogger(__name__)
from odoo import api, fields, models, _

class Importmagento2xpartners(models.TransientModel):
    _inherit = ['import.partners']
   
    @staticmethod
    def _parse_magento2x_customer_address(channel_id,addresses,email,customer_id,**kwargs):
        res=[]
        for item in addresses:
            name = item.get('firstname')
            if item.get('lastname'):
                name+=' %s'%(item.get('lastname'))
            _type = 'invoice'
            if item.get('default_shipping'):
                _type = 'delivery'
            street=street2=''
            street_list = item.get('street')
            if len(street_list):
                street=street_list[0]
                if len(street_list)>1:
                    street2 = street_list[1]
            vals= dict(
                channel_id=channel_id.id,
                name=name,
                email=email,
                street=street,
                street2=street2,
                phone=item.get('telephone'),
                city=item.get('city'),
                state_name=item.get('region').get('region'),
                country_id=item.get('country_id'),
                zip=item.get('postcode'),
                store_id=item.get('id'),
                parent_id = customer_id,
                type=_type
            )
            res+=[vals]
        return res


    @staticmethod
    def get_customer_vals(customer_data,**kwargs):
        name = customer_data.get('firstname')
        if customer_data.get('lastname'):
            name+=' %s'%(customer_data.get('lastname'))
        vals = dict(
            name=name,
            store_id=customer_data.get('id'),
            email=customer_data.get('email'),
            mobile=customer_data.get('telephone')
        )
        return vals

    def import_now(self, channel_id, sdk, kwargs):
        message=''
        page_size = channel_id.api_record_limit
        page_len = channel_id.api_record_limit
        current_page = 1
        current_page = kwargs.pop('current_page') if kwargs.get('current_page') else 1 
        if not kwargs.get("filter_on"):
            if channel_id.import_customer_date and channel_id.update_customer_date:
                kwargs.update(
                    filter_on="date_range",
                    start_date=channel_id.import_customer_date,
                    end_date=channel_id.update_customer_date
                )
        fetch_res = channel_id.fetch_magento2x_customers_data(
            sdk=sdk,
            current_page = current_page,
            operation = "import",
            **kwargs,
        )
        partners = fetch_res.get('data') or {}
        total_count = partners.get('total_count')
        current_page += 1
        kwargs.update(current_page=current_page)
        if current_page == ceil(total_count/page_len):
            kwargs.update(page_size=10000)
        message+= fetch_res.get('message','')
        if not partners.get('items'):
            message+="Partners data not received."
            kwargs.update(
                message=message
            )
            return []
        else:
            partners=filter(lambda i:i.get('store_id'),(partners.get('items') or []))
            if not partners:
                kwargs.update(
                    message=message
                )
                return []
            else:
                partner_list = []
                for i in partners:
                    customer_data = self.get_customer_vals(i)
                    customer_data.update(channel_id=channel_id.id)
                    if i.get('addresses'):
                        address_data = self._parse_magento2x_customer_address(channel_id,i.get('addresses'),i.get('email'),i.get('id'))
                        customer_data['contacts'] = address_data
                    partner_list.append(customer_data)
                return partner_list
