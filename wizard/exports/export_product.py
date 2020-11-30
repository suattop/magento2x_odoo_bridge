# -*- coding: utf-8 -*-
#################################################################################
#
#   Copyright (c) 2017-Present Webkul Software Pvt. Ltd. (<https://webkul.com/>)
#   See LICENSE URL <https://store.webkul.com/license.html/> for full copyright and licensing details.
#################################################################################
import logging

from odoo import api, fields, models, _
from odoo.exceptions import  UserError,RedirectWarning, ValidationError ,Warning
from odoo.addons.odoo_multi_channel_sale.tools import extract_list as EL
from odoo.addons.odoo_multi_channel_sale.tools import ensure_string as ES
from odoo.addons.odoo_multi_channel_sale.tools import JoinList as JL
from odoo.addons.odoo_multi_channel_sale.tools import MapId

_logger = logging.getLogger(__name__)


class ExportMagento2xProducts(models.TransientModel):
    _inherit = ['export.templates']


    magento2x_default_product_set_id = fields.Many2one(
        comodel_name='magento.attributes.set',
        string='Default Attribute Set',
        help='Magento Product Attribute Set.',
    )

    @api.onchange('channel_id')
    def set_default_magento_data(self):
        channel_id = self.channel_id
        if channel_id.channel=='magento2x':
            context = dict(self._context)
            context['wk_channel_id'] = channel_id.id
            set_id = channel_id.with_context(context).magento2x_get_default_product_set_id()
            self.magento2x_default_product_set_id =set_id

    @api.model
    def magento2x_image_data(self,sdk,sku,product_id,image):
        _type='image/%s'%(self.env['multi.channel.sale'].get_image_type(image))
        media_data={
                "media_type": "image",
                "label": None,
                "position": 1,
                "disabled": False,
                "types":[u'image', u'small_image', u'thumbnail', u'swatch_image'],
                "content": {
                "base64_encoded_data": image.decode(),
                "type":_type,
                "name":'product_image_%s'%(sku)
                },
        }
        return media_data

    @api.model
    def magento2x_upload_products(self,sdk,product_id,data,sku=None):
        image = data.pop('image', None)
        if image:
            image_data = self.magento2x_image_data(sdk,sku,product_id,image)
            data['media_gallery_entries'] = [image_data]
        res = sdk.post_products(data,sku=sku)
        return res


    @api.model
    def magento2x_get_store_category_ids(self,template_id,channel_id):
        res =None
        mapped_ids=[]
        channel_categ_ids = None
        #leaving below code here in case of errors or for future resolution.
        # match_category = channel_id.get_channel_category_id(template_id,channel_id,limit=None)
        # category = (template_id.channel_category_ids or
        # template_id.categ_id)
        # category_ids = category.extra_category_ids
        if template_id.channel_category_ids:
            channel_categ_ids = template_id.channel_category_ids.filtered(lambda categ: categ.instance_id.id == channel_id.id).mapped('extra_category_ids')
        if channel_categ_ids:
            mapped_ids = channel_categ_ids.mapped('channel_mapping_ids').mapped('store_category_id')
        elif template_id.categ_id.channel_mapping_ids:
            mapped_ids = template_id.categ_id.channel_mapping_ids.mapped('store_category_id')
        # raise ValueError
        
        elif self.channel_id.magento2x_default_product_categ_id:
            res= [self.channel_id.magento2x_default_product_categ_id.store_category_id]
        if mapped_ids:
            res = list(map(int,mapped_ids))
            if 1 in res:res.remove(1)
        return res



    @api.model
    def get_magento2x_configurable_product_options(self, template_id, channel_id, product_set_id):
        result = dict(
            data = None,
            message=''
        )
        data=dict()
        set_attribute_ids = product_set_id.attribute_ids
        for attribute_value_id in template_id.product_variant_ids.mapped('product_template_attribute_value_ids'):
                attribute_id = attribute_value_id.attribute_id
                attribute_match = channel_id.match_attribute_mappings(
                    odoo_attribute_id=attribute_id.id
                )
                if attribute_match:
                    if attribute_id not in set_attribute_ids:
                        result['message']+='<br/> Attribute(%s) not related with attribute set (%s)'%(attribute_id.name,product_set_id.set_name)
                        return result
                    property_id = attribute_match.store_attribute_id
                    if not property_id in data:
                        data[property_id] = dict(
                            attribute_id= int(property_id),
                            label=attribute_id.name,
                            position=0,
                            isUseDefault= 1,
                            values=[]
                        )
                    value_match = channel_id.match_attribute_value_mappings(attribute_value_id=attribute_value_id.product_attribute_value_id.id)
                    if value_match:
                        data[property_id]['values'] +=[dict(value_index= int(value_match.store_attribute_value_id))]
                    else:
                        result['message']+='<br/> No  attribute value mappping found for %s ==> %s.'%(attribute_id.name,attribute_value_id.name)
                        return result
                else:
                    result['message']+='<br/>No attribute mappping found for %s ==> %s.'%(attribute_id.name,attribute_value_id.name)
                    return result
        result['data']=data
        return result

    @api.model
    def get_magento2x_custom_attributes(self,product_id,channel_id,**kwargs):
        result = dict(
            data = None,
            message=''
        )
        data=[]
        for value_id in product_id.product_template_attribute_value_ids:
            attribute_id = value_id.attribute_id
            attribute_match = channel_id.match_attribute_mappings(odoo_attribute_id=attribute_id.id)
            if attribute_match:
                temp_data = dict(
                    attribute_code= attribute_match.store_attribute_name,
                )
                value_match = channel_id.match_attribute_value_mappings(attribute_value_id=value_id.product_attribute_value_id.id)
                if value_match:
                    temp_data['value'] = int(value_match.store_attribute_value_id)
                    data+=[temp_data]
                else:
                    result['message']+='<br/> No  attribute value mappping found for %s  ==> %s.'%(attribute_id.name,value_id.name)
                    return result
            else:
                result['message']+='<br/> No  attribute  mappping found for %s ==> %s.'%(attribute_id.name,value_id.name)
                return result
        result['data']=data
        return result

    @api.model
    def magento2x_get_product_data(self,_type,product_id,channel_id,
            product_links=[],configurable_product_options=None,**kwargs):
        result =  dict(data=None,message='')
        product_set_id = channel_id.magento2x_default_product_set_id
        if not product_set_id:
            return dict(
                data=None,
                message="Please select a default attribute set id in configurations"
            )
        context = dict(self._context)
        context.update({
            'lang':channel_id.language_id.code,
            'pricelist':channel_id.pricelist_name.id
        })
        product_data =  product_id.with_context(context).read([])[0]
        description = product_data.get('description_sale') or product_data.get('name')
        if not product_id.default_code:
            product_id.default_code = channel_id.sku_sequence_id.next_by_id() if channel_id.sku_sequence_id \
                else product_id.name + "_oid_" + str(product_id.id)
        sku =  product_id.default_code
        url_key ='%s-%s'%(product_data.get('name').lower().replace(" ", "-").strip(),sku)
        product_qty = channel_id.get_quantity(product_id)
        data=dict(
            type_id=_type,
            attribute_set_id=int(product_set_id.store_id),
            sku = sku,
            name=product_data.get('name') ,
            price=product_data.get('price'),#product_id.list_price ,
            weight=product_id.weight ,
            status=product_id.sale_ok and 1 or 2,
            visibility=4,
            extension_attributes=dict(
                stock_item=dict(
                   qty= product_qty,
                   is_in_stock= product_qty and 1 or 0,
                )
            ),
            custom_attributes=[
                {u'attribute_code': u'short_description', u'value': description },
                {u'attribute_code': u'url_key', u'value': url_key },
                {u'attribute_code': u'tax_class_id', u'value': '0'},
            ]
        )
        image=product_id.image_1920
        if image:
            data['image']=image
        if _type=='configurable':
            if kwargs.get('match'):
                data['sku'] = kwargs.get('match').default_code
            else:
                data['sku'] = channel_id.sku_sequence_id.next_by_id() if channel_id.sku_sequence_id \
                else product_id.name + "_oe_template_" + str(product_id.id)
            data['extension_attributes']['configurable_product_options']=configurable_product_options
            data['extension_attributes']['configurable_product_links']= product_links
        else:
            if product_id.__class__.__name__=='product.product':
                custom_attributes = self.get_magento2x_custom_attributes(product_id,channel_id,**kwargs)
                if custom_attributes.get('message'):
                    result['message']+=custom_attributes.get('message')
                    return result
                else:
                    data['custom_attributes']+= custom_attributes.get('data')
        categories = self.magento2x_get_store_category_ids(product_id,channel_id)
        if categories:
            data['custom_attributes'].append({u'attribute_code': u'category_ids', u'value': categories})

        result['data']=data
        return result

    @api.model
    def magento2x_send_simple_product_data(self, sdk, template_id ,channel_id, operation = 'export'):
        result=dict(
            mapping_id = None,
            message = '<br/>==>For Template %s [%s] Operation (%s) <br/>'%(template_id.name,template_id.id,operation)
        )
        data_res = self.magento2x_get_product_data(
            _type = 'simple',product_id = template_id,channel_id = channel_id
        )
        data = data_res.get('data')
        result['message']+=data_res.get('message')
        if data:
            result['message'] +='<br/> Template %s done.'%operation

            #In case of update must pass sku .
            sku = operation != 'export' and data['sku']
            #website issue but the product is getting updated on sku basis.
            res=self.magento2x_upload_products(sdk, template_id, data, sku = sku)
            result['message']+=res.get('message')
            data = res.get('data')
            store_template_id =data and data.get('id')
            if store_template_id:
                if self._context.get('base_operation')=="export":
                    result['mapping_id'] = [store_template_id]
                    return result
                if self._context.get('base_operation')=="update":
                    result['update_simple'] = "done" # returning true as no store id required Update required scope can also be added
                if operation != 'update':
                    result['mapping_id']=channel_id.create_template_mapping(
                    erp_id = template_id, store_id =store_template_id,
                    vals = dict(default_code = data['sku'],operation='export')
                    )
                    for variant_id in template_id.product_variant_ids:
                        channel_id.create_product_mapping(
                            odoo_template_id = template_id, odoo_product_id = variant_id,
                            store_id = store_template_id, store_variant_id ='No Variants',
                            vals = dict(default_code = variant_id.default_code,operation='export')
                        )
        return result

    @api.model
    def magento2x_send_product_data(self, sdk, template_id ,channel_id, product_set_id,operation = 'export'):
        mapping_obj = self.env['channel.template.mappings']
        mapping_ids = []
        variant_mapping_vals = []
        product_links = []
        configurable_product_options = []
        result=dict(
            mapping_id = None,
            message = '<br/>==>For Template %s [%s] Operation (%s) <br/>'%(template_id.name,template_id.id,operation)
        )
        # IF operation is update check match , if match not exits return message
        match = None
        if operation != 'export':
            match = self.channel_id._match_mapping(
                    mapping_obj,
                    [('odoo_template_id', '=',template_id.id)],
                    limit=1
            )

            result['mapping_id'] = match
            if not match:
                result['message']+='<br/>Mapping not exits .'
                return result
            #Due to empty sku magento is throwing error.
        if not(template_id.attribute_line_ids):
            exp_res = self.magento2x_send_simple_product_data(sdk, template_id ,channel_id, operation)
            # if exp_res['update_done'] == "done":
            # can update mapping here update required to no without above mapping match
            if match:
                result['message'] = exp_res['message']
            else:
                result.update(exp_res)
            return result
        # IF product have attributes , create it's childs first  and store in product_links
        if template_id.attribute_line_ids:
            conf = self.get_magento2x_configurable_product_options(
                template_id,channel_id,product_set_id
            )
            if conf.get('message'):
                result['message']+=conf.get('message')
                return result
            configurable_product_options = list(conf.get('data').values())
            for product_id in template_id.product_variant_ids:
                #Get the configurable product.product data.
                if  (operation != 'export') and (not channel_id.match_product_mappings(domain=[('product_name','=',product_id.id)])) :
                    result['message']+= _('<br/>New product variant can not added while template update (product %r(%r) )'%(product_id.name,product_id.id))
                    continue

                data_res = self.magento2x_get_product_data(
                    _type = 'simple',product_id = product_id,
                    channel_id = channel_id, sdk = sdk
                )

                data = data_res.get('data')
                if data_res.get('message',''):
                    result['message'] +=data_res.get('message','')
                if data:
                    data['visibility'] = 1
                    #In case of update must pass sku .
                    sku = operation != 'export' and data['sku']

                    #Create  simple product.
                    res=self.magento2x_upload_products(sdk, product_id, data, sku = sku)
                    if res.get('message',''):
                        result['message'] +='<br/>'+ res.get('message','')
                    else:
                        result['message'] +='<br/> Variant %s(%s) Operation(%s)'%(product_id.name,product_id.id,operation)
                    data = res.get('data')
                    store_variant_id =data and data.get('id')
                    if store_variant_id:
                        product_links += [store_variant_id]
                        variant_mapping_vals += [
                            dict(
                            odoo_template_id = template_id, odoo_product_id = product_id,
                            store_id = None, store_variant_id = store_variant_id,
                            vals = dict(default_code=product_id.default_code, operation=operation)
                            )
                        ]
                else:
                    return result
            #Get the configurable product tempalte data.
            data_res = self.magento2x_get_product_data(
                _type = 'configurable',product_id = template_id,
                channel_id = channel_id,product_links=product_links,
                configurable_product_options=configurable_product_options,
                match=match
            )

            data = data_res.get('data')
            if data.get('message',''):
                result['message'] +='<br/>'+ data.get('message','')

            if data:
                # if operation == 'export':
                    # data['sku']='oe_template%s'%(template_id.id)
                #In case of update must pass sku .
                sku = operation != 'export' and data['sku']
                #Create  configurable product.\
                res=self.magento2x_upload_products(sdk, template_id, data , sku = sku)
                data = data_res.get('data')
                if res.get('message',''):
                    result['message'] +='<br/>'+ res.get('message','')
                else:
                    result['message'] +='<br/> Template Operation(%s) done.'%operation
                data = res.get('data')
                store_template_id =data and data.get('id')
                if store_template_id:
                    if self._context.get('base_operation')=="export":
                        result['mapping_id'] = [store_template_id, data.get('sku'), product_links]
                        # result['mapping_varinat_id'] = product_links
                        return result
                    if self._context.get('base_operation')=="update":
                        result['update_template'] = "done"
                    match_template = self.channel_id.match_template_mappings(store_template_id)
                    if not match_template:
                        result['mapping_id']=channel_id.create_template_mapping(
                            erp_id = template_id, store_id = store_template_id,
                            vals = dict(default_code = data['sku'],operation=operation)
                        )
                    else:
                        result['mapping_id']=match_template
                    for mval in variant_mapping_vals:
                        store_variant_id = mval['store_variant_id']
                        match_product= self.channel_id.match_product_mappings(store_template_id,store_variant_id)
                        if not match_product:
                            mval['store_id']=store_template_id
                            mapping_ids+=[channel_id.create_product_mapping(**mval)]
                        else:
                            mapping_ids+=[match_product]
        return result

    @api.model
    def magento2x_post_products_data(self,sdk,product_tmpl_ids,channel_id):
        message=''
        update_ids ,create_ids = [],[]
        export_attr = self.export_mage2x_pre_product_data(
            sdk, product_tmpl_ids, channel_id
        )
        product_set_id =  (self.magento2x_default_product_set_id or
            channel_id.magento2x_default_product_set_id
        )
        if (not export_attr.get('status')) and export_attr.get('message'):
            message+=export_attr.get('message')
        else:
            operation = self._context.get('base_operation') if self._context.get('base_operation') else self.operation
            for template_id in product_tmpl_ids:
                try:
                    sync_vals = dict(
                        status ='error',
                        action_on ='template',
                        action_type ='export',
                        odoo_id =  template_id.id
                    )
                    post_res = dict()
                    if operation=='export':
                        post_res=self.magento2x_send_product_data(sdk,template_id,channel_id,product_set_id)
                        if post_res.get('mapping_id'):
                            create_ids+=post_res.get('mapping_id')
                        else:
                            message += post_res.get('message','')
                    else:
                        post_res=self.magento2x_send_product_data(sdk,template_id,channel_id,product_set_id, operation = 'update')
                        if post_res.get('mapping_id'):
                            update_ids+=post_res.get('mapping_id')
                    msz = post_res.get('message')
                    if post_res.get('mapping_id') and not self._context.get('base_operation')=="export":
                        sync_vals['status'] = 'success'
                        sync_vals['ecomstore_refrence'] =post_res.get('mapping_id').store_product_id
                    else:
                        if len(create_ids) == 3:
                            create_ids = dict(
                                template_id=create_ids[0],
                                variant_ids=create_ids[2],
                                default_code=create_ids[1]
                            )
                        elif len(create_ids) == 1:
                            create_ids = dict(
                                template_id=create_ids[0],
                                variant_ids=[create_ids[0]]
                            )
                    sync_vals['summary'] = msz or '%s %sed'%(template_id.name,operation)
                    channel_id._create_sync(sync_vals)
                    message+=msz
                except Exception as e:
                    message+='<br/>Error While %s(%s) %s <br/>%s'%(e,template_id.name,template_id.id,operation)
        
        return dict(
            message=message,
            update_ids=update_ids,
            create_ids=create_ids,

        )

    @api.model
    def post_magento2x_attribute(self, sdk, channel_id, odoo_attribute_ids, operation ='export', **kwargs):
        Attribute = self.env['export.attributes.magento']
        return  Attribute.magento2x_post_attributes_data(sdk, channel_id,odoo_attribute_ids,operation)

    @api.model
    def post_magento2x_category(self, sdk, channel_id, odoo_category_ids, operation ='export', **kwargs):
        create_ids = []
        for category in odoo_category_ids:
            mag_cat_id = self.env['export.categories'].magento2x_post_categories_data(sdk,  channel_id, category,operation="export")
            if mag_cat_id:
                self.env['channel.category.mappings'].create(
                    {
                        'channel_id'       : channel_id.id,
                        'ecom_store'       : channel_id.channel,
                        'category_name'    : category.id,
                        'odoo_category_id' : category.id,
                        'store_category_id': mag_cat_id,
                        'operation'        : 'export',
                    }
                )
                create_ids.append(mag_cat_id)
            else:
                pass
            

    @api.model
    def export_mage2x_product_category(self,sdk,product_tmpl_ids,channel_id):
        result = dict(
            data = None,
            message='',
            status = True,
        )
        map_obj = self.env['channel.category.mappings']
        channel_category_ids = product_tmpl_ids.mapped('channel_category_ids')
        categ = channel_category_ids.filtered(lambda cat:cat.instance_id==channel_id)
        extra_category_ids = categ.mapped('extra_category_ids')
        domain = [
            ('category_name', 'in',extra_category_ids.ids),
        ]
        match = channel_id._match_mapping(map_obj, domain)
        new_categ = extra_category_ids-match.mapped('category_name')
        if len(new_categ):
            result= self.post_magento2x_category(sdk,channel_id, new_categ, operation='export')
        return result

    @api.model
    def import_mage2x_product_attribute(self,sdk,product_tmpl_ids,channel_id):
        ImportAttributes = self.env['import.magento2x.attributes']
        vals = dict(
            channel_id = channel_id.id,
        )
        object_id = ImportAttributes.create(vals)
        object_id.import_now()

    @api.model
    def export_mage2x_product_attribute(self,sdk,product_tmpl_ids,channel_id):
        result = dict(
            data = None,
            message='',
            status = True
        )
        data=dict()
        new_attribute =self.env['product.attribute']
        new_attribute_for_value = self.env['product.attribute']
        attribute_value_ids = product_tmpl_ids.mapped('product_variant_ids').mapped('product_template_attribute_value_ids')

        for attribute_value_id in attribute_value_ids:
                attribute_id = attribute_value_id.attribute_id
                attribute_match = channel_id.match_attribute_mappings(
                    odoo_attribute_id=attribute_id.id
                )
                if not attribute_match and (attribute_id not in new_attribute):
                    new_attribute+=attribute_id
                else:
                    value_match = channel_id.match_attribute_value_mappings(
                        attribute_value_id=attribute_value_id.product_attribute_value_id.id
                    )
                    if not value_match and (attribute_id not in new_attribute_for_value):
                        new_attribute_for_value+=attribute_id
        import_attrs = False
        if len(new_attribute):
            result =  self.post_magento2x_attribute(sdk,channel_id, new_attribute, operation='export')
            import_attrs = True
        elif len(new_attribute_for_value):
            import_attrs = True
            result = self.post_magento2x_attribute(sdk,channel_id, new_attribute_for_value, operation='update')
        if import_attrs:
            self.import_mage2x_product_attribute(sdk,product_tmpl_ids,channel_id)
        return result

    @api.model
    def export_mage2x_pre_product_data(self,sdk,product_tmpl_ids,channel_id):
        result = dict(
            data = None,
            message='',
            status = True,
        )
        status =True
        cate_res = self.export_mage2x_product_category(sdk,product_tmpl_ids,channel_id)
        if status:
            status =cate_res.get('status')
        if cate_res.get('message'):

            result['message']+=cate_res.get('message')
        attr_res = self.export_mage2x_product_attribute(sdk,product_tmpl_ids,channel_id)
        if status:
            status =attr_res.get('status')
        if attr_res.get('message'):
            result['message']+=attr_res.get('message')
        result['status']=status
        return result

    def magento2x_export_templates(self):
        message = ''
        ex_create_ids,ex_update_ids,create_ids,update_ids= [],[],[],[]
        exclude_type_ids=[]

        for record in self:
            channel_id = record.channel_id
            res =channel_id.get_magento2x_sdk()
            sdk = res.get('sdk')
            if not sdk:
                message+=res.get('message')
            else:
                exclude_res=record.exclude_export_data(record.product_tmpl_ids,channel_id,record.operation,domain=[])
                template_ids=exclude_res.get('object_ids')
                product_tmpl_ids = template_ids.filtered(
                    lambda pt:pt.type in ['product','consu']
                )
                ex_update_ids+=exclude_res.get('ex_update_ids')
                ex_create_ids+=exclude_res.get('ex_create_ids')
                exclude_type_ids+=record.product_tmpl_ids.filtered(
                    lambda pt:pt.type not in ['product','consu']
                )
                if not len(product_tmpl_ids):
                    message+='No Product filter for %s over magento.'%(record.operation)
                else:
                    post_res=record.magento2x_post_products_data(sdk,product_tmpl_ids,channel_id)

                    create_ids+=post_res.get('create_ids')
                    update_ids+=post_res.get('update_ids')
                    message+=post_res.get('message')
        if len(exclude_type_ids):
            message += '<br/> Total %s  product template not exported/updated because of having type other than product  and consumable .'%(len(exclude_type_ids))
        message+=self.env['multi.channel.sale'].get_operation_message_v1(
            obj = 'product template',
            obj_model = '',
            operation = 'exported',
            obj_ids = create_ids
        )
        message+=self.env['multi.channel.sale'].get_operation_message_v1(
            obj = 'product template',
            obj_model = '',
            operation = 'updated',
            obj_ids = update_ids
        )
        return self.env['multi.channel.sale'].display_message(message)
