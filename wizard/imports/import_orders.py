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
from odoo.addons.odoo_multi_channel_sale.tools import chunks
from odoo.exceptions import UserError,RedirectWarning, ValidationError

class ImportOrders(models.TransientModel):
    _inherit = ['import.orders']

    def import_products(self,product_tmpl_ids, channel_id, sdk, kwargs):
        product_tmpl_ids = [str(pt) for pt in product_tmpl_ids] #getting ids
        mapping_obj = self.env['channel.product.mappings'] # obj
        domain = [('store_variant_id', 'in',product_tmpl_ids)] # domain prepared
        mapped = channel_id._match_mapping(mapping_obj,domain).mapped('store_variant_id')
        product_tmpl_ids=list(set(product_tmpl_ids)-set(mapped))
        if len(product_tmpl_ids):
            feed_domain = [('store_id', 'in',product_tmpl_ids)]
            product_feeds = channel_id.match_product_feeds(domain=feed_domain,limit=0).mapped('store_id')
            product_tmpl_ids=list(set(product_tmpl_ids)-set(product_feeds))
            if len(product_tmpl_ids):
                feed_domain = [('store_id', 'in',product_tmpl_ids)]
                product_variant_feeds = channel_id.match_product_variant_feeds(domain=feed_domain,limit=0).mapped('store_id')
                product_tmpl_ids=list(set(product_tmpl_ids)-set(product_variant_feeds))
        message=''
        if len(product_tmpl_ids):
            message='For order product imported %s'%(product_tmpl_ids)
            import_product_obj=self.env['import.templates']
            attributes_res = channel_id._fetch_magento2x_product_attributes(sdk)
            message+=attributes_res.get('message','')
            attributes_res_data = attributes_res.get('data')
            attributes_list = attributes_res_data and attributes_res_data.get('items')
            import_res = list()
            for i in product_tmpl_ids:
                product_data = channel_id._fetch_magento2x_product_data(sdk,filter_on="on_id",id=i)
                product_data = product_data.get('data').get(int(i))
                if product_data:
                    sku = product_data.get('sku')
                    product_id = product_data.get('id')
                    data = sdk.get_products(sku=sku)
                    if not data.get('data'):
                        message += data.get('message')
                        break
                    import_res.append(import_product_obj._magento2x_import_product(sdk,channel_id,
                                                'import',product_id,data.get('data'),kwargs,
                                                attributes_list=attributes_list))
            if import_res:
                s_ids,e_ids,feeds = self.env['product.feed'].with_context(
                                channel_id=channel_id
                            )._create_feeds(import_res)
                if s_ids and not e_ids:
                    self._cr.commit()
                    if channel_id.auto_evaluate_feed:
                        mapping_ids = feeds.with_context(get_mapping_ids=True).import_items()
                        message += str(mapping_ids) + " "
                    message += "Products got imported during order Import."
                    result = True

                # if e_ids:
                #     message += "There is some problem in processing auto product import for orders, please check feeds or contact support."
                #     result = False
                # if feeds:
                #     mapping_ids = feeds.with_context(get_mapping_ids=True).import_items()
                #     message += str(mapping_ids) + "These products get imported while order sync because they weren't available in odoo."
                #     if channel_id.auto_evaluate_feed:channel_id._cr.commit()
                # result = True
            else:
                message += "Error in creating feed."
                result = False
            if kwargs.get('ext_msg'):
                message = message+'\n'+kwargs.get('ext_msg')
            return dict(
                res=result,
                message=message
            )

        return True # product are aready synced
        
    def update_shipping_info(self,order_items,order_data,price):
        name = 'Magento %s'%(order_data.get('shipping_description'))
        order_items+=[dict(
            product_id=name,
            price=price,
            qty_ordered=1,
            name=name,
            line_source ='delivery',
            description=name,
            tax_amount ='0',
        )]
        return order_items

    def get_discount_line_info(self,price):
        name = '%s discount'%(price)
        return dict(
            product_id=name,
            price='%s'%(abs(float(price))),
            qty_ordered=1,
            name=name,
            line_source ='discount',
            description=name,
            tax_amount ='0',
        )

    def magento2x_get_tax_line(self,item):
        tax_percent = float(item.get('tax_percent'))
        tax_type = 'percent'
        name = '{}_{} {} % '.format(self.channel_id.channel,self.channel_id.id,tax_percent)
        return {
            'rate':tax_percent,
            'name':name,
            'include_in_price':self.channel_id.magento2x_default_tax_type== 'include'and True or False,
            'tax_type':tax_type
        }

    def magento2x_get_order_line_info(self,order_item):
        product_id=order_item.get('product_id')
        line_price_unit = order_item.get('price')
        if order_item.get('line_source') not in ['discount','delivery']:
            if self.channel_id.magento2x_default_tax_type=='include'  :
                line_price_unit =  order_item.get('price_incl_tax') and order_item.get('price_incl_tax') or order_item.get('price')
        line=None
        line_product_default_code = order_item.get('sku')
        if product_id:
            line_product_id=product_id
            line_variant_ids=None
            if order_item.get('parent_id'):
                line_variant_ids=line_product_id
                line_product_id=order_item.get('parent_id')
            
            if order_item.get('line_source') not in ['discount','delivery']:
                pdata=self.channel_id.match_product_mappings(line_variant_ids=product_id) #this function can also be altered to get a pair of ids of template and variant
                # pdata=self.env['channel.product.mappings'].search([('store_variant_id','=',product_id)])
                if pdata:
                    if pdata.store_product_id == str(product_id):
                        line_variant_ids = line_product_id = product_id
                    else:
                        line_product_id = pdata.store_product_id
                        line_variant_ids = pdata.store_variant_id
                # else:
                #     line_product_id = product_id
                #     line_variant_ids = None
                line=dict(
                    line_product_uom_qty = order_item.get('qty_ordered'),
                    line_variant_ids =line_variant_ids,
                    line_product_id=line_product_id,
                    line_product_default_code=line_product_default_code,
                    line_name = order_item.get('name'),
                    line_price_unit=line_price_unit,
                    line_source = order_item.get('line_source','product'),
                )
            else:
                line=dict(
                    line_product_uom_qty = order_item.get('qty_ordered'),
                    line_variant_ids = line_variant_ids,
                    line_product_id=line_product_id,
                    line_product_default_code=line_product_default_code,
                    line_name = order_item.get('name'),
                    line_price_unit=line_price_unit ,
                    line_source = order_item.get('line_source','product'),
                )
        return line

    @staticmethod
    def manage_configurable_items(items):
        return list(filter(lambda i:i.get('product_type')!='configurable',items))

    def magento2x_get_discount_amount(self,order_item):
        discount_amount = 0
        if order_item.get('line_source') not in ['delivery','discount']:
            qty_ordered = float(order_item.get('qty_ordered'))
            discount_amount = float(order_item.get('original_price'))*qty_ordered-float(order_item.get('price'))*qty_ordered
            code_discount_amount = float(order_item.get('discount_amount','0'))
            if code_discount_amount:
                discount_amount += code_discount_amount
        return discount_amount

    def magento2x_get_order_item(self,order_item):
        res = None
        parent_item = order_item.get('parent_item')
        if parent_item and parent_item.get('product_type')=='configurable':
            parent_product_id=parent_item.get('product_id')
            res = parent_item
            res['product_id'] = order_item.get('product_id')
            res['name'] = order_item.get('name')
            res['parent_id'] = parent_product_id
        else:
            res = order_item
        return res

    def magento2x_get_discount_order_line(self,order_item):
        #discount_amount = self.magento2x_get_discount_amount(order_item)
        discount_amount = float(order_item.get('discount_amount','0'))
        if discount_amount:
            discount_data = self.get_discount_line_info(discount_amount)
            discount_line=self.magento2x_get_order_line_info(discount_data)
            if float(order_item.get('tax_percent','0.0')):
                discount_data['tax_percent'] = order_item.get('tax_percent','0.0')
                discount_line['line_taxes'] = [self.magento2x_get_tax_line(discount_data)]
            return discount_line

    def magento2x_get_order_line(self,order_id,carrier_id,order_data):
        data=dict()
        order_items=order_data.get('items')

        order_items = self.manage_configurable_items(order_items)
        message=''
        default_tax_type = self.channel_id.magento2x_default_tax_type
        lines=[]
        lines += [(5,0,0)]
        if order_items:
            shipping_amount = order_data.get('shipping_incl_tax')

            if carrier_id and float(shipping_amount):
                order_items= self.update_shipping_info(
                    order_items,order_data,shipping_amount
                )

            size = len(order_items)
            for order_item in order_items:
                order_item = self.magento2x_get_order_item(order_item)
                line=self.magento2x_get_order_line_info(order_item)
                if float(order_item.get('tax_percent','0.0')):
                    line['line_taxes'] = [self.magento2x_get_tax_line(order_item)]
                #discount_amount  = self.magento2x_get_discount_amount(order_item)
                #if discount_amount:
                #   line['discount']=discount_amount
                lines += [(0, 0, line)]
                discount_line  =self.magento2x_get_discount_order_line(order_item)
                if discount_line:
                    lines += [(0, 0, discount_line)]
                elif size==1:
                    data.update(line)
                    lines=[]

        data['line_ids'] = lines
        data['line_type'] = len(lines) >1 and 'multi' or 'single'
        return dict(
            data=data,
            message=message
            )
            
    def get_mage_invoice_address(self,item,customer_email):
        name = item.get('firstname')
        if item.get('lastname'):
            name+=' %s'%(item.get('lastname'))
        email = item.get('email') or customer_email
        street = item.get('street')
        invoice_street= invoice_street2=''
        if len(street):
            invoice_street = item.get('street')[0]
            if len(street)>1:
                invoice_street2 = ' '.join(item.get('street')[1:])

        return dict(
            invoice_name=name,
            invoice_email=email,
            invoice_street=invoice_street,
            invoice_street2=invoice_street2,
            invoice_phone=item.get('telephone'),
            invoice_city=item.get('city'),
            invoice_country_id=item.get('country_id'),
            invoice_partner_id=item.get('customer_address_id') or '0',
            invoice_zip=item.get('postcode'),
            invoice_state_name=item.get('region'),
        )

    def get_mage_shipping_address(self,item,customer_email):
        name = item.get('firstname')
        if item.get('lastname'):
            name+=' %s'%(item.get('lastname'))
        email = item.get('email') or customer_email
        street = item.get('street')
        shipping_street= shipping_street2=''
        if len(street):
            shipping_street = item.get('street')[0]
            if len(street)>1:
                shipping_street2 = ' '.join(item.get('street')[1:])


        return dict(
            shipping_name=name,
            shipping_email=email,
            shipping_street=shipping_street,
            shipping_street2=shipping_street2,
            shipping_phone=item.get('telephone'),
            shipping_city=item.get('city'),
            shipping_country_id=item.get('country_id'),
            shipping_zip=item.get('postcode'),
            invoice_state_name=item.get('region'),
        )
    def get_order_vals(self,sdk,increment_id,status,order_data):
        message = ''
        channel_id =self.channel_id
        # pricelist_id = channel_id.pricelist_name
        if order_data.get('items'):
            item = order_data
            customer_name = item.get('customer_firstname')
            if item.get('customer_lastname'):
                customer_name+=" %s"%(item.get('customer_lastname'))
            customer_email=item.get('customer_email')
            vals = dict(
                order_state = status,
                partner_id=item.get('customer_id') or '0' ,
                customer_is_guest = int(item.get('customer_is_guest')),
                currency = item.get('order_currency_code'),
                customer_name=customer_name,
                customer_email=customer_email,
                payment_method = item.get('payment').get('method'),
            )
            shipping = item.get('extension_attributes',{}).get('shipping_assignments',{})[0].get('shipping')
            shipping_method = shipping.get('method')
            vals['carrier_id']= shipping_method #shipping_mapping_id.shipping_service_id
            line_res= self.magento2x_get_order_line(
                increment_id,
                shipping_method,item
            )
            if line_res.get('data'):
                vals.update(line_res.get('data'))
            billing_address=item.get('billing_address') or {}
            shipping_address = shipping.get('address')
            billing_hash = channel_id.get_magento2x_address_hash(billing_address)
            shipping_hash = channel_id.get_magento2x_address_hash(shipping_address or {})
            same_shipping_billing = billing_hash==shipping_hash
            vals['same_shipping_billing'] =same_shipping_billing
            billing_address['customer_address_id'] = billing_hash
            billing_addr_vals = self.get_mage_invoice_address(billing_address,customer_email)
            vals.update(billing_addr_vals)
            if shipping_address and not(same_shipping_billing):
                shipping_add_vals = self.get_mage_shipping_address(shipping_address,customer_email)
                shipping_add_vals['shipping_partner_id'] = shipping_hash
                vals.update(shipping_add_vals)
            if not vals.get('customer_name'):
                vals['customer_name'] = vals.get('invoice_name') or vals.get('shipping_name')
            return vals
        else:
            #impelment this part if in some case magento api do not return order_items in some calls
            pass

    def _magento2x_update_order_feed(self,sdk,mapping,entity_id,increment_id,status,data):
        vals =self.get_order_vals(sdk,increment_id,status,data)
        mapping.write(dict(line_ids=[(5,0)]))
        vals['state'] = 'update'
        mapping.write(vals)
        return mapping

    def _magento2x_create_order_feed(self,sdk,entity_id,increment_id, status, data):
        vals = self.get_order_vals(sdk,increment_id,status,data)        
        vals['store_id'] = increment_id
        vals['store_source'] = entity_id
        vals['name'] = increment_id
        return vals

    def _magento2x_import_order(self, sdk, entity_id, increment_id,status, data):
        feed_data = self._magento2x_create_order_feed(sdk, entity_id, increment_id, status, data)
        return feed_data
    #this function is not being used for now due to unclear base module functions
    def _magento2x_import_orders_status(self,sdk,store_id,channel_id):

        message = ''
        update_ids = []
        order_state_ids = channel_id.order_state_ids
        default_order_state = order_state_ids.filtered('default_order_state')
        store_order_ids = channel_id.match_order_mappings(
            limit=None).filtered(lambda item:item.order_name.state=='draft'
            ).mapped('store_order_id')
        if not store_order_ids:
            message += 'No order mapping exits'
        else:
            for store_order_id_chunk in chunks(store_order_ids,channel_id.api_record_limit):
                params = {
                    "searchCriteria[filter_groups][0][filters][0][field]": 'increment_id',
                    "searchCriteria[filter_groups][0][filters][0][value]": ','.join(map(str,store_order_id_chunk)),
                    "searchCriteria[filter_groups][0][filters][0][condition_type]": 'in',
                }
                params['fields'] ='items[store_id,payment,increment_id,status]'
                fetch_data=sdk.get_orders(params=params)
                data = fetch_data.get('data') or {}
                message += fetch_data.get('message')
                if not data:
                    continue
                items = data.get('items',[])
                for item in items:
                    if item.get('store_id')!=store_id: continue
                    res = channel_id.set_order_by_status(
                        channel_id= channel_id,
                        store_id = item.get('increment_id'),
                        status = item.get('status'),
                        order_state_ids = order_state_ids,
                        default_order_state = default_order_state,
                        payment_method =item.get('payment',{}).get('method')
                    )
                    order_match = res.get('order_match')
                    if order_match:update_ids +=[order_match]
                self._cr.commit()
        time_now = fields.Datetime.now()
        all_imported , all_updated = 1,1
        if all_updated and len(update_ids):
            channel_id.update_order_date = time_now
        if not channel_id.import_order_date:
            channel_id.import_order_date = time_now
        return dict(
            update_ids=update_ids,
        )

    @classmethod
    def set_channel_id(cls,channel_id):
        #setting channel_id on class level becuase channel id is being used at multiple function passing  as argument will be
        #cumbersome, in testing parameter leak wasn't noted.
        cls.channel_id = channel_id

    def _magento2x_import_orders(self, sdk, store_id, channel_id, kwargs):
        message = ''
        operation = "import"
        page_size = channel_id.api_record_limit#
        page_len = channel_id.api_record_limit#
        current_page = 1
        import_products = False
        import_res = []
        current_page = kwargs.pop('current_page') if kwargs.get('current_page') else 1
        self.set_channel_id(channel_id)
        if not kwargs.get("filter_on"):
            if channel_id.import_order_date and channel_id.update_order_date:
                kwargs.update(
                    filter_on="date_range",
                    start_date=channel_id.import_order_date,
                    end_date=channel_id.update_order_date
                )
        fetch_data = channel_id._fetch_magento2x_order_data(
            sdk=sdk,
            store_id=store_id,
            current_page = current_page,
            operation = operation,
            **kwargs
        )

        data = fetch_data.get('data') or {}
        msz = fetch_data.get('message','')
        message+=msz
        current_page+=1
        kwargs.update(current_page=current_page)
        if data and data.get('items'):
            items = data.get('items',[])
            total_count = data.get('total_count')
            if current_page == ceil(total_count/page_len):
                kwargs.update(page_size=10000)
            product_ids = []
            sku = False
            import_for_orders = dict()
            for order_item in items:
                for product_item in order_item.get('items'):
                    if product_item.get('product_type') == 'configurable':
                        sku = product_item.get('sku')
                    if sku and product_item.get('product_type') == 'simple':
                        if product_item.get('sku') == sku:
                            sku = False
                            # product_item.get('product_id') in product_ids and  will see if test cases failed
                            continue
                    product_ids+=[product_item.get('product_id')]
                import_for_orders[order_item.get('entity_id')] = tuple(product_ids)
                product_ids.clear()
            ignore_ids = list()
            for order in import_for_orders:
                product_ids = import_for_orders.get(order)
                if not import_products and len(product_ids) and not any(x in ignore_ids for x in product_ids):
                    import_products = self.import_products(product_ids,channel_id,sdk,kwargs)
                    if isinstance(import_products,dict) and not import_products.get('res'):
                        ignore_ids.append(order)
                        # message += "For Order {}, These product ids couldn't be imported,  {} \n".format(order,product_ids)
                        import_products = False
                    else:
                        import_products = False 
                else:
                    ignore_ids.append(order)
            for item in items:
                if item.get('store_id')!=store_id or item.get('entity_id') in ignore_ids:
                    message += "Order " + item.get('increment_id')+" is being ignored. Order Store ID:" + str(item.get('store_id')) + " config store ID:" +str(store_id) + "<br>"
                    continue
                increment_id = item.get('increment_id')
                entity_id = item.get('entity_id')
                status = item.get('status')
                data = self._magento2x_import_order(sdk,entity_id,increment_id,status, item)
                data.update(channel_id=channel_id.id)
                import_res.append(data)
        else:
            message += "Data is not recieved from your magento please check again the applied filters or contact the support."
        kwargs.update(
            ext_msg=message
        )
        return import_res

