# -*- coding: utf-8 -*-
#################################################################################
#
#   Copyright (c) 2017-Present Webkul Software Pvt. Ltd. (<https://webkul.com/>)
#   See LICENSE URL <https://store.webkul.com/license.html/> for full copyright and licensing details.
#################################################################################
from ast import literal_eval
import logging
import re
from datetime import date, datetime,timedelta
from odoo.http import request
from odoo.addons.magento2x_odoo_bridge.tools.magento_api import Magento2
from odoo.addons.odoo_multi_channel_sale.tools import chunks,get_hash_dict,wk_cmp_dict,ensure_string as ES

from odoo import api,fields, models,_
from odoo.exceptions import UserError
_logger = logging.getLogger(__name__)
MageDateTimeFomat = '%Y-%m-%d %H:%M:%S'

Boolean = [
    ('1', 'True'),
    ('0', 'False'),
]
Visibility = [
    ('1', 'Not Visible Individually'),
    ('2', 'Catalog'),
    ('3', 'Catalog'),
    ('4', 'Catalog, Search'),
]
Type = [
    ('simple','Simple Product'),
    ('downloadable','Downloadable Product'),
    ('grouped','Grouped Product'),
    ('virtual','Virtual Product'),
    ('bundle','Bundle Product'),
]
ShortDescription=[
    ('same','Same As Product Description'),
    ('custom','Custom')
]
TaxType = [
    ('include','Include In Price'),
    ('exclude','Exclude In Price')
]

DefaultStore = _("""***While using multi store***\n
Select the default store/parent store
from where the order and partner will imported for this child store.
""")

class response_object:
    def __init__(self,model_name,template_id,variant_ids,default_code,flag=True):
        if model_name == 'product.template':
            self.id = template_id 
            variants = []
            if flag:
                self.default_code = default_code
                for i in variant_ids:
                    variants.append(response_object(model_name,i,False,False,False))
            self.variants = variants


class MultiChannelSale(models.Model):
    _inherit = "multi.channel.sale"
    @api.model
    def match_category_mappings(self, store_category_id=None, odoo_category_id=None, domain=None, limit=1):
        if self.channel=='magento2x' and self.magneto2x_default_store_id:
            self = self.magneto2x_default_store_id
        return super(MultiChannelSale,self).match_category_mappings(store_category_id=store_category_id,odoo_category_id=odoo_category_id,domain=domain,limit=limit)

    @api.model
    def match_partner_mappings(self, store_id = None, _type='contact',domain=None, limit=1):
        if self.channel=='magento2x' and self.magneto2x_default_store_id:
            self = self.magneto2x_default_store_id
        return super(MultiChannelSale,self).match_partner_mappings(store_id=store_id,_type=_type,domain=domain,limit=limit)

    @api.model
    def match_product_mappings(self, store_product_id=None, line_variant_ids=None,
            domain=None,limit=1,**kwargs):
        map_domain = self.get_channel_domain(domain)
        if self.channel=='magento2x':
            if store_product_id and line_variant_ids=='No Variants':
                line_variant_ids = store_product_id
        return super(MultiChannelSale,self).match_product_mappings(
            store_product_id = store_product_id,
            line_variant_ids = line_variant_ids,
            domain =domain,limit =limit,**kwargs)

    @api.model
    def get_magento2_category_mappings(self,limit=0):
        domain = [('ecom_store','=','magento2x')]
        if self._context.get('wk_channel_id'):
            domain += [('channel_id','=',self._context.get('wk_channel_id'))]

        return self.env['channel.category.mappings'].search(domain,limit)


    @api.model
    def get_magento2_category_mappings_domain(self):
        mappings = self.get_magento2_category_mappings().ids
        return [('id', 'in', mappings)]
    @api.model
    def get_magento2_odoo_category_domain(self):
        category_ids = self.get_magento2_category_mappings().mapped('odoo_category_id')
        return [('id', 'not in', category_ids)]


    @api.model
    def get_magento2x_channel_id(self):
        return self.env['multi.channel.sale.config'].sudo().get_default_fields({}).get('default_magneto2x_channel_id')


    @api.model
    def get_magento2x_sdk(self, test_con=False):
        message= ''
        sdk = None
        if self.state != 'validate' and not test_con:
            _logger.info('================%r===============',"connection state is not validated!")
            return dict(
                sdk=False,
                message="Connection is not validated"
            )
        try:
            debug = self.debug == 'enable'
            sdk = Magento2(
                username=self.magento2x_username,
                password=self.magento2x_password,
                base_uri=self.magento2x_base_uri,
                store_code=str(self.magento2x_store_code),
                debug=self.debug == 'enable'
            )
        except Exception as e:
            message+='<br/>%s'%(e)
        return dict(
            sdk=sdk,
            message=message,
        )

    @api.model
    def get_channel(self):
        result = super(MultiChannelSale, self).get_channel()
        result.append(("magento2x", "Magento v2"))
        return result

    @api.model
    def sync_magento2x_item(self,mapping,product_qty,sdk):
        result = {'data': {}, 'message': ''}
        store_id = mapping.store_product_id
        sku = mapping.default_code
        item = sdk.get_products(sku)
        product_data = item.get('data') or dict()
        qty_available = 0
        extension_attributes = product_data.get('extension_attributes')
        if extension_attributes and extension_attributes.get('stock_item').get('qty'):
            qty_available = int(extension_attributes.get('stock_item').get('qty'))
            qty_available += product_qty
        if qty_available:
            data=dict(
                sku = mapping.default_code,
                extension_attributes=dict(
                    stock_item=dict(
                       qty= qty_available,
                       is_in_stock= qty_available >0 and 1 or 0,
                    )
                ),
            )
            res=sdk.post_products(data,sku=mapping.default_code)
            result.update(res)
        return result

    @api.model
    def sync_quantity_magento2x(self,mapping,product_qty):
        sdk = self.get_magento2x_sdk().get('sdk')
        result = {'data': {}, 'message': ''}
        sku = mapping.default_code
        if sdk:
            item = sdk.get_products(sku)
            product_data = item.get('data') or dict()
            qty_available = 0
            extension_attributes = product_data.get('extension_attributes')
            if extension_attributes and extension_attributes.get('stock_item').get('qty') >= -999:
                # qty_available = int(extension_attributes.get('stock_item').get('qty'))
                qty_available += product_qty
            if qty_available:
                data=dict(
                    sku = mapping.default_code,
                    extension_attributes=dict(
                        stock_item=dict(
                        qty= qty_available,
                        is_in_stock= qty_available >0 and 1 or 0,
                        )
                    ),
                )
                res=sdk.post_products(data,sku=mapping.default_code)
                result.update(res)
            
            if result.get('message'):
                return False
            return True
        return False
        
    @api.model
    def get_info_urls(self):
        urls = super(MultiChannelSale,self).get_info_urls()
        urls.update(
            magento2x = {
                'blog' : 'https://webkul.com/blog/multi-channel-magento-2-x-odoo-bridgemulti-channel-mob',
                'store': 'https://store.webkul.com/Multi-Channel-Magento-2-x-Odoo-Bridge-Multi-Channel-MOB.html',
            },
        )
        return urls

    def test_magento2x_connection(self):
        for obj in self:
            state = 'error'
            message = ''
            
            res =obj.get_magento2x_sdk(test_con=True)
            sdk = res.get('sdk')
            if not (sdk and sdk.oauth_token):
                message+='<br/>%s'%(res.get('message'))
                message+='<br/>Oauth Token not received.'

            else:
                configs_res = sdk.get_store_configs()
                message+=configs_res.get('message','')
                configs =configs_res.get('data')
                if configs and len(configs):

                    magento2x_store_config = dict(map(lambda con:(con.get('code'),con),configs)).get(obj.magento2x_store_code)
                    if not magento2x_store_config:
                        message += '<br/>Store Code %s not in found over magento server.'%(obj.magento2x_store_code)
                    else:


                        self.magento2x_store_config =magento2x_store_config
                        state='validate'
                        message += '<br/> Credentials successfully validated.'
            obj.state= state


            if state!='validate':
                message+='<br/> Error While Credentials  validation.'
        return self.display_message(message)



    @api.model
    def magento2x_get_default_product_categ_id(self):
        domain =[('ecom_store','=','magento2x')]
        if self._context.get('wk_channel_id'):
            domain += [('channel_id','=',self._context.get('wk_channel_id'))]
        return self.env['channel.category.mappings'].search(domain,limit=1)


    @api.model
    def magento2x_get_default_product_set_id(self):
        domain =[('ecom_store','=','magento2x')]
        wk_channel_id = self._context.get('wk_channel_id') or self._context.get('channel_id')
        if wk_channel_id:
            domain += [('channel_id','=',wk_channel_id)]
        return self.env['magento.attributes.set'].search(domain,limit=1)


    magento2x_default_product_categ_id = fields.Many2one(
        comodel_name='channel.category.mappings',
        string='Magento Categories',
        help = 'Default Magento Categories',
        domain=lambda self:self.env['multi.channel.sale'].get_magento2_category_mappings_domain(),
        default=lambda self:self.magento2x_get_default_product_categ_id()
    )
    magento2x_default_tax_type = fields.Selection(
        selection = TaxType,
        string = 'Default Tax Type',
        default='exclude',
        required=1
    )
    magento2x_default_product_set_id = fields.Many2one(
        comodel_name='magento.attributes.set',
        string='Default Attribute Set',
        help='ID of the product attribute set',
        default=lambda self:self.magento2x_get_default_product_set_id()
    )

    magento2x_export_order_shipment =fields.Selection(
        selection =Boolean,
        string = 'Export Shipment',
        help = 'Export  Order Shipment Over Magento.',
        default='1',
        required=1,
    )
    magento2x_export_order_invoice =fields.Selection(
        selection =Boolean,
        string = 'Export Invoice',
        help = 'Export  Order Invoice Over Magento.',
        default='1',
        required=1,
    )

    magento2x_base_uri = fields.Char(
        string='Base URI'
    )
    magento2x_username = fields.Char(
        string='User Name'
    )
    magento2x_password = fields.Char(
        string='Password'
    )
    magento2x_store_code = fields.Char(
        string='Store View Code',
        default='default',
    )

    magento2x_store_config = fields.Text(
        string='Store Config'
    )
    magento2x_is_child_store = fields.Boolean(
        string = 'Is Child Store'
    )
    magneto2x_default_store_id =fields.Many2one(
        comodel_name = 'multi.channel.sale',
        string='Parent Store',
        help = DefaultStore,
    )


    @api.constrains('magento2x_is_child_store','magneto2x_default_store_id')
    def check_magento2x_base_uri(self):
        if self.channel=='magento2x' and \
            self.magento2x_is_child_store and \
                self.magneto2x_default_store_id :
	        if self.magneto2x_default_store_id.magento2x_base_uri != self.magento2x_base_uri:
	                raise Warning("""The Base URI should be same as parent for child store also.""")

    @api.model
    def create(self, vals):
        base_uri = vals.get('magento2x_base_uri')
        if base_uri:

            vals['magento2x_base_uri'] = re.sub('/index.php', '',base_uri.strip(' ').strip('/'))

        return super(MultiChannelSale,self).create(vals)


    def write(self, vals):
        base_uri = vals.get('magento2x_base_uri')
        if base_uri:
            vals['magento2x_base_uri'] = re.sub('/index.php', '', base_uri.strip(' ').strip('/'))
        return super(MultiChannelSale,self).write(vals)
    
    def magento2x_import_order_cron(self):
        #adding filter
        # kw = {'filter_on':self.magento2x_filter_type}
        obj = self.env['import.operation'].create({'channel_id':self.id})
        kw =  {'filter_on':"date_range"}
        if self.import_order_date and self.update_order_date:
            kw['start_date'] = self.import_order_date
            kw['end_date'] = self.update_order_date
        obj = self.env['import.operation'].create({'channel_id':self.id})
        obj.import_with_filter(object="sale.order",**kw)

    def magento2x_import_product_cron(self):
        #adding filter
        obj = self.env['import.operation'].create({'channel_id':self.id})
        kw =  {'filter_on':"date_range"}
        if self.import_product_date and self.update_product_date:
            kw['start_date'] = self.import_product_date
            kw['end_date'] = self.update_product_date
        obj.import_with_filter(object="product.template",**kw)
    
    def magento2x_import_partner_cron(self):
        #adding filter
        obj = self.env['import.operation'].create({'channel_id':self.id})
        kw =  {'filter_on':"date_range"}
        if self.import_customer_date and self.update_customer_date:
            kw['start_date'] = self.import_customer_date
            kw['end_date'] = self.update_customer_date
        obj.import_with_filter(object="res.partner",**kw)
    
    def magento2x_import_category_cron(self):
        obj = self.env['import.operation'].create({'channel_id':self.id})
        obj.import_with_filter(object="product.category")


    @api.model
    def magento2x_get_ship_data(self,picking_id,mapping_id,result):
        comment = 'Create For Odoo Order %s , Picking %s'%( mapping_id.order_name.name,picking_id.name)
        data ={
          "notify": True,
          "appendComment": True,
          "comment": {
            "extension_attributes": {},
            "comment": comment,
            "is_visible_on_front": 0
          }
        }
        if picking_id.carrier_tracking_ref and picking_id.carrier_id:
            data["tracks"]= [
              {
                "extension_attributes": {},
                "track_number": picking_id.carrier_tracking_ref,
                "title": picking_id.carrier_id.name,
                "carrier_code": picking_id.carrier_id.name
              }
            ]
        return data

    @staticmethod
    def get_magento2x_address_hash(itemvals):
        templ_add = {
        "city":itemvals.get("city"),
        "region_code":itemvals.get("region_code"),
        "firstname":itemvals.get("firstname"),
        "lastname":itemvals.get("lastname"),
        "region":itemvals.get("region"),
        "country_id":itemvals.get("country_id"),
        "telephone":itemvals.get("telephone"),
        "street":itemvals.get("street"),
        "postcode":itemvals.get("postcode"),
        # "customer_address_id":itemvals.get("customer_address_id") or itemvals.get('customer_id')
        }
        return get_hash_dict(templ_add)
    @api.model
    def magento2x_post_do_transfer(self,picking_id,mapping_ids,result):
        flag = True
        for i in picking_id.move_ids_without_package:
            if i.quantity_done != i.product_uom_qty:
                flag = False
        debug = self.debug=='enable'
        if flag:
            sync_vals = dict(
                status ='error',
                action_on ='order',
                action_type ='export',
            )
            res =self.get_magento2x_sdk()
            sdk = res.get('sdk')
            if debug:
                _logger.info("do_transfer #1 %r===%r="%(res,mapping_ids))
            if sdk:
                for mapping_id in mapping_ids:
                    sync_vals['ecomstore_refrence'] ='%s(%s)'%(mapping_id.store_order_id,mapping_id.store_id)
                    sync_vals['odoo_id'] = mapping_id.odoo_order_id
                    message=''
                    data = self.magento2x_get_ship_data(picking_id,mapping_id,result)
                    res=sdk.post_orders_ship(mapping_id.store_id,data)
                    if debug:
                        _logger.info("=do_transfer #2==%r=====%r==%r="%(data,res,sync_vals))
                    if res.get('data'):
                        sync_vals['status'] = 'success'
                        message  +='Delivery created successfully '
                    else:
                        sync_vals['status'] = 'error'
                        message  +=res.get('message')
                    sync_vals['summary'] = message
                    mapping_id.channel_id._create_sync(sync_vals)


    @api.model
    def magento2x_get_invoice_data(self,invoice_id,mapping_id,result):
        comment = 'Create For Odoo Order %s  Invoice %s'%( mapping_id.order_name.name,invoice_id.name)
        data = {
            "capture": True,
            "notify": True,
            "appendComment": True,
            "comment": {
                "extension_attributes": {},
                "comment": comment,
                "is_visible_on_front": 0
            }
        }
        return data

    @api.model
    def magento2x_post_cancel_order(self, order_id, mapping_ids, result):
        #cancel order function was not added
        message = ''
        debug = self.debug=='enable'
        res = self.get_magento2x_sdk()
        sdk =  res.get('sdk')
        if sdk:
            sync_vals = dict(
                    status ='error',
                    action_on ='order',
                    action_type ='export',
                )
            for mapping_id in mapping_ids:
                sync_vals['ecomstore_refrence'] ='%s(%s)'%(mapping_id.store_order_id,mapping_id.store_id)
                sync_vals['odoo_id'] = mapping_id.odoo_order_id
                res = sdk.cancel_order(mapping_id.store_id)
                if res.get('data'):
                    sync_vals['status'] = 'success'
                    message  +='Cancel Order successfully '
                else:
                    sync_vals['status'] = 'error'
                    message  +=res.get('message')
                sync_vals['summary'] = message
                if debug:
                    _logger.info("=canceled order #2==%r=====%r==="%(res,sync_vals))
                mapping_id.channel_id._create_sync(sync_vals)

        

    @api.model
    def magento2x_post_confirm_paid(self,invoice_id,mapping_ids,result):
        debug = self.debug=='enable'
        sync_vals = dict(
            status ='error',
            action_on ='order',
            action_type ='export',
        )
        res =self.get_magento2x_sdk()
        sdk = res.get('sdk')
        if debug:
            _logger.info("confirm_paid #1 %r===%r="%(res,mapping_ids))
        if sdk:
            for mapping_id in mapping_ids:
                sync_vals['ecomstore_refrence'] ='%s(%s)'%(mapping_id.store_order_id,mapping_id.store_id)
                sync_vals['odoo_id'] = mapping_id.odoo_order_id
                message=''
                data =self.magento2x_get_invoice_data(invoice_id,mapping_id,result)
                res=sdk.post_orders_invoice(mapping_id.store_id,data)
                if res.get('data'):
                    sync_vals['status'] = 'success'
                    message  +='Invoice created successfully '
                else:
                    sync_vals['status'] = 'error'
                    message  +=res.get('message')
                sync_vals['summary'] = message
                if debug:
                    _logger.info("=confirm_paid #2==%r=====%r==%r="%(data,res,sync_vals))
                mapping_id.channel_id._create_sync(sync_vals)


    def import_magento2x(self, object, **kwargs):
        self.ensure_one()
        channel_id = self
        result = None
        debug = channel_id.debug == 'enable'
        res = channel_id.get_magento2x_sdk()
        sdk = res.get('sdk')
        if kwargs.get('message'):kwargs['message'] = ''
        if not sdk:
            _logger.info('~~~~~~~~~~~~~~SDK NOT FOUND~~~~~~~~~~~~~~~~~')
            return None,None
        if object == 'product.category':
            result = self.env['import.categories'].import_now(channel_id, sdk, kwargs)
        elif object == 'res.partner':
            result = self.env['import.partners'].import_now(channel_id,sdk,kwargs)
        elif object == 'product.template':
            result = self.env['import.templates']._magento2x_import_products(sdk, channel_id, kwargs)
        elif object == 'sale.order':
            store_id = channel_id.get_magento2x_store_config(channel_id,'id')
            result = self.env['import.orders']._magento2x_import_orders(sdk,store_id,channel_id, kwargs)
        elif object == 'product.attribute':
            result = self.import_magento2x_attributes_sets(kwargs)
        elif object == 'delivery.carrier':
            result = []
            kwargs.update(
                message="For magento this operation gets automatically executed when order sync run, so you don't have to run it spearately."
            )
            # result.append({'store_id':"Attributes are Added"})
        else:
            pass
        if debug:
            _logger.info('========RESULT+++++++%r+==============',[result,kwargs])
        if not result:
            result = None
        return result,kwargs


    def import_magento2x_attributes(self):
        self.ensure_one()
        vals =dict(
            channel_id=self.id
        )
        obj=self.env['import.magento2x.attributes'].create(vals)
        return obj.import_now()


    def import_magento2x_attributes_sets(self,kwargs):
        self.ensure_one()
        vals =dict(
            channel_id=self.id,
        )
        obj=self.env['import.magento2x.attributes.sets'].create(vals)
        return obj.import_now()

    def export_magento2x_categories(self):
        self.ensure_one()
        odoo_obj_ids = self.match_category_mappings(
            limit=None).mapped('odoo_category_id')
        domain = [('id','not in',odoo_obj_ids)]
        obj_ids = self.env['product.category'].search(domain)
        vals =dict(
            channel_id=self.id,
            category_ids = [(6,0,obj_ids.ids)]
        )
        obj=self.env['export.categories'].create(vals)
        return obj.magento2x_export_categories()

    
    def export_magento2x(self, exp_obj, **kwargs):
        model_name = exp_obj._name
        channel_id = self
        res = channel_id.get_magento2x_sdk()
        sdk = res.get('sdk')
        if not sdk:
            _logger.info('======No SDK Found========%r=============',[exp_obj,model_name])
            return None,None
        if model_name == 'product.template':
            res = self.env['export.templates'].with_context(base_operation='export').magento2x_post_products_data(sdk,exp_obj,channel_id)
            store_template_id = res.get('create_ids').get('template_id') if res.get('create_ids') else False
            store_variants_id = res.get('create_ids').get('variant_ids') if res.get('create_ids')  else False #[1] if len(res.get('create_ids')) == 2 else res.get('create_ids')
            store_default_code = res.get('create_ids').get('default_code') if res.get('create_ids')  else False

            if store_template_id and store_variants_id:
                result = True,response_object(model_name,store_template_id,store_variants_id, store_default_code)
            else:
                result = False,False
        
        if model_name == 'product.category':
            result = self.env['export.categories'].magento2x_post_categories_bulk_data(sdk,channel_id,exp_obj,"export")
        return result

    def update_magento2x(self, record, get_remote_id, **kwargs):
        # get_remote_id(record)
        # return False,False
        model_name = record._name
        channel_id = self
        debug = channel_id.debug == 'enable'
        res = channel_id.get_magento2x_sdk()
        sdk = res.get('sdk')
        result = False,False
        if not sdk:
            _logger.info('======No SDK Found========%r=============',[record,model_name])
            return result
        store_id = get_remote_id(record) # update
        if store_id:
            if model_name == 'product.category':
                result = self.env['export.categories'].magento2x_post_categories_bulk_data(sdk,channel_id,record,"update")
            elif model_name == 'product.template':
                res = self.env['export.templates'].with_context(base_operation='update').magento2x_post_products_data(sdk,record,channel_id)
                if res.get('update_ids'):
                    result = True,True
                if debug:
                    _logger.info('============RESULT UPDATE++++++++++%r+++',res)
        return result

    def export_magento2x_attributes(self):
        self.ensure_one()
        odoo_obj_ids = self.match_attribute_mappings(
            limit=None).mapped('odoo_attribute_id')
        domain = [('id','not in',odoo_obj_ids)]
        obj_ids = self.env['product.attribute'].search(domain)
        vals =dict(
            channel_id=self.id,
            attribute_ids = [(6,0,obj_ids.ids)]
        )
        obj=self.env['export.attributes.magento'].create(vals)
        return obj.magento2x_export_attributes()


    @api.model
    def _fetch_magento2x_product_attributes(self, sdk, attribute_code = None,
        attribute_set_id = None,wk_params=None,**kwargs):
        # a = self.env['product.attribute'].search([])
        params = {
            "searchCriteria[filter_groups][0][filters][0][field]": "is_global",
            "searchCriteria[filter_groups][0][filters][0][value]": 1,
            "searchCriteria[filter_groups][0][filters][0][condition_type]": 'eq',
            "searchCriteria[filter_groups][1][filters][0][field]": "is_user_defined",
            "searchCriteria[filter_groups][1][filters][0][value]": 1,
            "searchCriteria[filter_groups][1][filters][0][condition_type]": 'eq',
            "searchCriteria[filter_groups][2][filters][0][field]": "frontend_input",
            "searchCriteria[filter_groups][2][filters][0][value]": "select",
            "searchCriteria[filter_groups][2][filters][0][condition_type]": 'eq'
        }
        if wk_params:
            params.update(params)
        return sdk.get_attributes(attribute_code = attribute_code, params = params)

    @api.model
    def _fetch_magento2x_order_data(self,sdk,**kwargs):
        params=None
        filter_group=0
        operation_params = self._fetch_magento2x_params(filter_group = filter_group,**kwargs)
        if len(operation_params):
            params = operation_params
        if sdk.debug:
            _logger.info('===++++%r======\n %r'%(params,kwargs))
        return sdk.get_orders(params=params)
    
    @api.model
    def fetch_magento2x_customers_data(self,sdk,**kwargs):
        operation_params = self._fetch_magento2x_params(filter_group=0,**kwargs)
        if len(operation_params):
            params = operation_params
        if sdk.debug:
            _logger.info('===++++%r======\n %r'%(params,kwargs))
        return sdk.get_customers(params=params)
        
    @staticmethod
    def get_search_criteria(filter_group,**kwargs):
        param1 = param2 = field = None
        param = dict()
        parameq = paramin = None
        if kwargs.get('filter_on') == "date_range":
            param1 = kwargs.get('start_date')
            param2 = kwargs.get('end_date')
            field = "created_at"
            if param1:
                param1 = param1.strftime(MageDateTimeFomat)
            if param2:
                param2 = param2.strftime(MageDateTimeFomat)
        elif kwargs.get('filter_on') == "id_range":
            param1 = kwargs.get('start_id')
            param2 = kwargs.get('end_id')
            field =  "entity_id"
        elif kwargs.get('filter_on') == "category_id":
            parameq = kwargs.get('category_id')
            field = 'category_id'
        elif kwargs.get('filter_on') == "customer_id":
            parameq = kwargs.get('customer_email')
            field = "customer_email"
        elif kwargs.get('filter_on') == "on_id": #specifically for runtime creation process
            parameq = kwargs.get('id')
            field = "entity_id"
        elif kwargs.get('order_state'):
            field = 'status'
            parameq=kwargs.get('order_state')
        if param1 and param2:
            param = {
                "searchCriteria[filter_groups][%s][filters][0][field]"%filter_group:field,
                "searchCriteria[filter_groups][%s][filters][0][condition_type]"%filter_group:'from',
                "searchCriteria[filter_groups][%s][filters][0][value]"%filter_group:param1,
            }
            filter_group += 1
            param.update({
                "searchCriteria[filter_groups][%s][filters][0][field]"%filter_group:field,
                "searchCriteria[filter_groups][%s][filters][0][condition_type]"%filter_group:'to',
                "searchCriteria[filter_groups][%s][filters][0][value]"%filter_group:param2
            })
        elif param1:
            param = {
                "searchCriteria[filter_groups][%s][filters][0][field]"%filter_group: field,
                "searchCriteria[filter_groups][%s][filters][0][value]"%filter_group: param1,
                "searchCriteria[filter_groups][%s][filters][0][condition_type]"%filter_group: 'gt',
            }
        elif param2:
            param = {
                "searchCriteria[filter_groups][%s][filters][0][field]"%filter_group: field,
                "searchCriteria[filter_groups][%s][filters][0][value]"%filter_group: param2,
                "searchCriteria[filter_groups][%s][filters][0][condition_type]"%filter_group: 'lt',
            }
        elif parameq:
            param = {
                "searchCriteria[filter_groups][%s][filters][0][field]"%filter_group: field,
                "searchCriteria[filter_groups][%s][filters][0][value]"%filter_group: parameq,
                "searchCriteria[filter_groups][%s][filters][0][condition_type]"%filter_group: 'eq',
            }
        elif paramin:
            param = {
                "searchCriteria[filter_groups][%s][filters][0][field]"%filter_group: field,
                "searchCriteria[filter_groups][%s][filters][0][value]"%filter_group: paramin,
                "searchCriteria[filter_groups][%s][filters][0][condition_type]"%filter_group: 'in',
            }
        else:
            return {}
        return param

    @api.model
    def _fetch_magento2x_params(self,filter_group = 0,**kwargs):
        params = dict()
        params.update(self.get_search_criteria(filter_group,**kwargs))
        if  kwargs.get('page_size'):
            params["searchCriteria[page_size]"]=kwargs.get('page_size')
        if  kwargs.get('current_page'):
            params["searchCriteria[current_page]"]=kwargs.get('current_page')
        if kwargs.get('fields'):
            params["fields"]=(kwargs.get('fields'))

        return params


    @api.model
    def _fetch_magento2x_product_data(self,sdk,**kwargs):
        message=''
        results=dict()
        params={}
        total_count = 0
        filter_group=0
        if kwargs.get('type_id'):
            params = {
               "searchCriteria[filter_groups][%s][filters][0][field]"%filter_group: 'type_id',
               "searchCriteria[filter_groups][%s][filters][0][value]"%filter_group:  kwargs.get('type_id'),
               "searchCriteria[filter_groups][%s][filters][0][condition_type]"%filter_group: kwargs.get('condition_type','eq'),
            }
            filter_group+=1
        operation_params = self._fetch_magento2x_params(filter_group = filter_group,**kwargs)
        if len(operation_params):
            params.update(operation_params)
        res = sdk.get_products(params=params)
        message+=res.get('message')
        data=res.get('data')
        if data and data.get('items'):
            total_count = data.get('total_count', 0) or data.get('items', {}).get('total_count', 0)
            for item in data.get('items'):results[item.get('id')]=item
        return dict(
            data=results,
            message=message,
            total_count=total_count
        )


    @api.model
    def get_magento2x_store_config(self,channel_id,item):
        return literal_eval(channel_id.magento2x_store_config).get(item)


    @api.model
    def _magento2x_get_product_images_vals(self,sdk,channel_id,media,product_id=None):
        vals = dict()
        base_media_url =self.get_magento2x_store_config(channel_id,'base_media_url')
        for data in media:
            image_url = '{base_media_url}/catalog/product/{file}'.format(base_media_url=base_media_url,file=data.get('file'))
            if image_url:
                image = self.read_website_image_url(image_url)
                from PIL import Image
                from io import BytesIO
                from base64 import b64decode
                if image:
                    size = Image.open(BytesIO(b64decode(image))).size
                    if size > (1920, 1080):
                        # vals['message'] = "For Product"+ str(product_id) +"Image size is too big to store, recieved image "+str(size)+ "\n"
                        vals['message'] = "For Product: {product_id} , \
                        Skipping image : {file} , \
                        size ({size}) is too large to store.".format(product_id=str(product_id)
                        ,file=data.get('file'),
                        size=str(size)
                        )
                    else:
                        vals.update(
                            image=image,
                            image_url=image_url
                        )
            break
        return vals


    @staticmethod
    def get_magento2x_attribute_value_vals(data,attribute_id,**kwargs):
        return dict(
        name = data.get('label'),
        attribute_id =attribute_id
        )


    @staticmethod
    def _magento2x_update_attribute_value(mapping,vals,**kwargs):
        # mapping.attribute_name.write(vals)
        mapping.write(dict(store_attribute_value_name=vals.get('name')))
        return  mapping


    @staticmethod
    def _magento2x_create_attribute_value(attribute_value_obj,
        channel_id, attribute_id, store_id, vals,data,**kwargs):
        erp_id = channel_id.get_store_attribute_value_id(vals.get('name'),attribute_id)
        if not erp_id:
            erp_id = attribute_value_obj.create(vals)
        return channel_id.create_attribute_value_mapping(
            erp_id=erp_id, store_id=store_id,
            store_attribute_value_name= data.get('label')
        )


    @api.model
    def _magento2x_import_attribute_value(self, data,
        channel_id, store_id, attribute_id, sdk, **kwargs):
        Attributevalue = self.env['product.attribute.value']
        update = False
        match = channel_id.match_attribute_value_mappings(
            store_attribute_value_id=store_id,
        )
        vals = self.get_magento2x_attribute_value_vals(data,attribute_id)
        if match:
            update=self._magento2x_update_attribute_value( match, vals)
        else:
            match= self._magento2x_create_attribute_value(
                Attributevalue,
                channel_id,
                attribute_id,
                store_id,
                vals,
                data
            )
        return dict(
            mapping_id=match,
            update=update
        )


    @api.model
    def _magento2x_import_attribute_values(self, attribute_mapping_id, options,
        channel_id, sdk, **kwargs):
        attribute_id = attribute_mapping_id.odoo_attribute_id
        create_ids = self.env['channel.attribute.value.mappings']
        update_ids = self.env['channel.attribute.value.mappings']

        for item in options:
            store_id  =item.get('value')
            import_res = self._magento2x_import_attribute_value(
                data = item,
                channel_id = channel_id,
                store_id = store_id,
                attribute_id =attribute_id,
                sdk = sdk,
                **kwargs
            )
            mapping_id = import_res.get('mapping_id')
            if  import_res.get('update'):
                update_ids += mapping_id
            else:
                create_ids += mapping_id

        return dict(
            create_ids=create_ids,
            update_ids=update_ids,
        )


    @api.model
    def _magento2x_import_attribute_values(self, attribute_mapping_id, options,
        channel_id, sdk, **kwargs):
        attribute_id = attribute_mapping_id.odoo_attribute_id
        create_ids = self.env['channel.attribute.value.mappings']
        update_ids = self.env['channel.attribute.value.mappings']

        for item in options:
            store_id  =item.get('value')
            import_res = self._magento2x_import_attribute_value(
                data = item,
                channel_id = channel_id,
                store_id = store_id,
                attribute_id =attribute_id,
                sdk = sdk,
                **kwargs
            )
            mapping_id = import_res.get('mapping_id')
            if  import_res.get('update'):
                update_ids += mapping_id
            else:
                create_ids += mapping_id

        return dict(
            create_ids=create_ids,
            update_ids=update_ids,
        )
