# -*- coding: utf-8 -*-
#################################################################################
#
#   Copyright (c) 2017-Present Webkul Software Pvt. Ltd. (<https://webkul.com/>)
#   See LICENSE URL <https://store.webkul.com/license.html/> for full copyright and licensing details.
#################################################################################
import logging
import itertools
import binascii
import requests
from math import ceil
_logger = logging.getLogger(__name__)
from odoo import api, fields, models, _
from odoo.addons.odoo_multi_channel_sale.tools import chunks, extract_item,IndexItems
# from odoo.exceptions import  UserError,RedirectWarning, ValidationError #validations can be added in future ...
Page_Limit  = 150

OdooType = [
    ('simple','product'),
    ('configurable','product'),
    ('downloadable','service'),#digital
    ('grouped','service'),
    ('virtual','service'),
    ('bundle','service'),
]

class Importmagento2xProducts(models.TransientModel):
    _inherit = ['import.templates']

    @staticmethod
    def _extract_magento2x_categories(item):
        category_ids=[]
        custom_attributes=dict(IndexItems(items=item.get('custom_attributes'),skey='attribute_code'))
        if custom_attributes:
            extract_item_data = custom_attributes.get('category_ids',{}).get('value')
            category_ids+=extract_item_data
        return category_ids

    
    def _import_magento2x_categories(self,channel_id,obj):
        message=''
        try:
            categ_import_res = obj.import_now(channel_id,channel_id.get_magento2x_sdk().get('sdk'),{})
            s_ids,e_ids,feeds = self.env['category.feed'].with_context(
                                channel_id=channel_id
                            )._create_feeds(categ_import_res)
            channel_id._cr.commit()
            if feeds and channel_id.auto_evaluate_feed:
                channel_id._cr.commit()
        except Exception as e:
            message += "Error while  order product import %s"%(e)
        return message

    @api.model
    def _magento2x_create_product_categories(self,channel_id,category_ids):
        result = dict(
            res=False,
            import_res=False
        )
        mapping_obj = self.env['channel.category.mappings']
        domain = [('store_category_id', 'in',list(set(category_ids)))]
        mapped = channel_id._match_mapping(mapping_obj,domain).mapped('store_category_id')
        category_ids=list(set(category_ids)-set(mapped))
        if len(category_ids):
            result['import_res'] = True
            obj=self.env['import.categories']
            result['res'] = self._import_magento2x_categories(channel_id,obj)
        return result

    @classmethod
    def get_magento2x_product_varinats_data(cls,sdk,product_link_item):
        product_item =sdk.get_products(sku = product_link_item.get('sku')).get('data')
        if not (product_item):
            params = {
                "searchCriteria[filter_groups][0][filters][0][field]": 'entity_id',
                "searchCriteria[filter_groups][0][filters][0][value]": str(product_link_item.get('id')),
                "searchCriteria[filter_groups][0][filters][0][condition_type]": 'in',
            }
            product_item_by_id=(sdk.get_products(params=params).get('data') or {}).get('items') or []
            if product_item_by_id and len(product_item_by_id):
                product_item = product_item_by_id[0]
        return  product_item

    @classmethod
    def get_magento2x_product_varinats(cls,sdk,channel_id,product_data,
            extension_attributes,attributes_list, kwargs):
        
        res=[]
        debug = channel_id.debug == 'enable'
        channel_obj_id = channel_id.id
        api_record_limit = channel_id.api_record_limit
        configurable_product_options = extension_attributes.get('configurable_product_options')
        for product_link_ids in chunks(extension_attributes.get('configurable_product_links'),api_record_limit):
            params = {
                "searchCriteria[filter_groups][0][filters][0][field]": 'entity_id',
                "searchCriteria[filter_groups][0][filters][0][value]": ','.join(map(str,product_link_ids)),
                "searchCriteria[filter_groups][0][filters][0][condition_type]": 'in',
            }
            params["fields"]='items[id,sku]'
            if debug:
                _logger.info("=config-simple=%r =%r=%r "%(
                    product_link_ids,product_data['sku'],
                    len(extension_attributes.get('configurable_product_links'))))
            product_link_data=sdk.get_products(params=params).get('data')
            if product_link_data and product_link_data.get('items'):
                for product_link_item in product_link_data.get('items'):
                    product_item = cls.get_magento2x_product_varinats_data(sdk,product_link_item)
                    if product_item:
                        vals = cls.get_magento2x_product_vals(
                            sdk,channel_id,
                            product_item.get('id'),
                            product_item, kwargs,
                            attributes_list = attributes_list,
                            configurable_product_options = configurable_product_options,
                            trace_variant=True
                        )
                        vals['channel_id']=channel_obj_id
                        res+=[vals]
        return res
    @staticmethod
    def get_magento2x_product_name_value(custom_attributes,product_data,
        attributes_list,configurable_product_options):
        custom_attributes_value  = list(map(lambda i:i.get('value'),product_data.get('custom_attributes')))
        name_value_lists = []
        for options in configurable_product_options:
            attribute_id = options.get('attribute_id')
            for value in options.get('values'):
                value_index = value.get('value_index')
                if str(value_index) in custom_attributes_value:
                    filter_attr = None
                    for attr_list in  attributes_list:
                        if attr_list.get('attribute_id')== int(attribute_id):
                            filter_attr =attr_list
                            break

                    if filter_attr:
                        value_name = value_index
                        attr_options = filter_attr.get('options')
                        for option in attr_options:
                            if (option.get('value')  not in [False,None,'']) and int(option.get('value').strip())==value_index:
                                value_name = option.get('label')
                        name_value={
                            'name': options.get('label'),
                            'attrib_name_id': attribute_id,
                            'price': 0,
                            'attrib_value_id':value_index,
                            'value': value_name,
                        }
                        name_value_lists+=[name_value]
        return name_value_lists

    @classmethod
    def get_magento2x_product_vals(cls,sdk,channel_id,product_id,product_data,kwargs,
        attributes_list=None,
        configurable_product_options=None,
        trace_variant=False):
        attributes_list = attributes_list or dict()
        configurable_product_options = configurable_product_options or list()
        type_id=product_data.get('type_id')
        default_code = product_data.get('sku')
        vals = dict(
            store_id=product_id,
            channel_id=channel_id.id
        )

        custom_attributes=dict(IndexItems(items=product_data.get('custom_attributes'),skey='attribute_code'))
        category_ids=custom_attributes.get('category_ids',{}).get('value',[])
        vals['extra_categ_ids'] = ','.join(category_ids)
        vals['description_sale'] =  extract_item(custom_attributes.get('description'),'value')


        extension_attributes = product_data.get('extension_attributes',{})
        if extension_attributes and len(extension_attributes) and extension_attributes.get('stock_item').get('qty'):
            vals['qty_available'] = int(extension_attributes.get('stock_item').get('qty'))

        if type_id == 'configurable':
            feed_variants =cls.get_magento2x_product_varinats(sdk,channel_id,product_data,
                extension_attributes,attributes_list, kwargs)
                #extension_attributes  is IMP
            if feed_variants:
                vals['variants']=feed_variants
            vals['name'] = product_data.get('name')
            vals['default_code'] = default_code

        else:
            data=dict(
                default_code=default_code,
                type = dict(OdooType).get(type_id,'service'),
                weight = product_data.get('weight'),
                list_price = product_data.get('price'),
                standard_price = product_data.get('cost'),
            )
            if trace_variant:
                vals.update(data)
            else:
                data.pop('default_code')
                vals['variants'] = []
                vals.update(data)
                vals['name'] = product_data.get('name')
                vals['default_code'] = default_code
            if attributes_list:
                vals['name_value']=cls.get_magento2x_product_name_value(
                                        custom_attributes,product_data,
                                        attributes_list,configurable_product_options
                                    )
        media=product_data.get('media_gallery_entries',[])
        if len(media):
            res_img = channel_id._magento2x_get_product_images_vals(sdk,channel_id,media,product_id)
            if res_img.get('message'):
                kwargs['ext_msg'] = res_img.get('message') if not kwargs.get('ext_msg') else kwargs.get('ext_msg') + " "+ res_img.get('message')
            else:
                vals['image'] = res_img.get('image')
                vals['image_url'] = res_img.get('image_url')
        return vals


    def _magento2x_import_product(self, sdk,channel_id,operation,
        product_id,product_data,kwargs,attributes_list):
        category_ids = list()
        category_ids+=self._extract_magento2x_categories(product_data)
        if category_ids:
            categ_import = self._magento2x_create_product_categories(channel_id,category_ids)
            if categ_import.get('import_res'):
                if categ_import.get('res'):
                    kwargs.update(
                        ext_msg=categ_import.get('res')
                    )
                else:
                    kwargs.update(
                        ext_msg="New Categories imported while doing product import. \n"
                    )
        vals =self.get_magento2x_product_vals(sdk,channel_id,product_id,
            product_data,kwargs,attributes_list=attributes_list)
        vals['store_id'] = product_id
        return vals

    def magento2x_import_products(self,sdk,
            channel_id,attributes_list,kwargs,
            type_id='configurable',condition_type='neq'):
        message = ''
        import_res = list()
        page_size = channel_id.api_record_limit
        page_len = channel_id.api_record_limit
        operation = 'import'
        debug = channel_id.debug == 'enable'
        current_page = kwargs.pop('current_page') if kwargs.get('current_page') else 1 
        magento2x_type = 'simple' if condition_type=='neq' else 'configurable'
        if not kwargs.get("filter_on"):
            if channel_id.import_product_date and channel_id.update_product_date:
                kwargs.update(
                    filter_on="date_range",
                    start_date=channel_id.import_product_date,
                    end_date=channel_id.update_product_date
                )
        fetch_data = channel_id._fetch_magento2x_product_data(
            sdk=sdk,
            type_id = type_id,
            condition_type = condition_type,
            current_page = current_page,
            operation = operation,
            fields = 'items[id,sku],total_count',
            **kwargs,
        )

        products = fetch_data.get('data') or {}
        total_count = fetch_data.get('total_count')
        if current_page==ceil(total_count/page_len):
            kwargs.update(page_size=10000)
        # products.update(product)
        msz = fetch_data.get('message','')
        message+=msz
        current_page+=1
        kwargs.update(current_page=current_page)
        if products:
            if debug:
                _logger.info("@@@@=%r %r =%r==%r"%(
                    magento2x_type,current_page,page_len,page_size)
                )
            message+= fetch_data.get('message','')
            for product_id,item in products.items():
                product_data = sdk.get_products(item.get('sku')).get('data')
                if not product_data:
                    _logger.info("=NOT product_data==%r==="%(item))
                else:
                    #categories also needs to be updated here need to think another logic for that
                    import_res.append(self._magento2x_import_product(sdk,channel_id,
                                            operation,product_id,product_data,kwargs,
                                            attributes_list=attributes_list))
        else:
            pass
        return dict(
            res=import_res,
            msg=message
        )
                    
    @staticmethod
    def returndata(data):
        a = data.get('variants')
        return [i['store_id'] for i in a]

    def _magento2x_import_products(self, sdk, channel_id, kwargs):
        message = ''
        debug = channel_id.debug == 'enable'
        message = ''
        attributes_res = channel_id._fetch_magento2x_product_attributes(sdk)
        message+=attributes_res.get('message','')
        attributes_res_data = attributes_res.get('data')
        attributes_list = attributes_res_data and attributes_res_data.get('items')
        import_config = False
        import_simple = False
        import_res = self.magento2x_import_products(sdk,channel_id,
            attributes_list,kwargs, type_id='configurable', condition_type='eq'
            )
        if import_res.get('res'):
            import_config = import_res.get('res')
        else:
            message += import_res.get('msg')

        # if debug:
        #     _logger.info("==DONE import_config ==%r===="%(import_config))
        # create_ids+=import_config.get('create_ids')
        # update_ids+=import_config.get('update_ids')
        # category_ids+=import_config.get('category_ids')
        # message+=import_config.get('message')
        import_res = self.magento2x_import_products(sdk,channel_id,
            attributes_list, kwargs, type_id='configurable', condition_type='neq'
        )
        if import_res.get('res'):
            import_simple = import_res.get('res')
        else:
            message += import_res.get('msg')
        import itertools
        if import_config and import_simple:
            config_ids = set(list(itertools.chain(*map(self.returndata, import_config))))
            simple_ids = {i.get('store_id') for i in import_simple}
            keep_ids = simple_ids - config_ids
            new_import_simple = []
            for i in import_simple:
                if i.get('store_id') in keep_ids:
                    new_import_simple.append(i)

            data_list=new_import_simple+import_config
        elif import_simple:
            data_list = import_simple
        elif import_config:
            data_list = import_config
        else:
            kwargs.update(
                message=message + "\n" + kwargs.get('ext_msg') if kwargs.get('ext_msg') else '' 
            )
            data_list = []
        return data_list
