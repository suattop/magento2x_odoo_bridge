# -*- coding: utf-8 -*-
#################################################################################
#
#   Copyright (c) 2017-Present Webkul Software Pvt. Ltd. (<https://webkul.com/>)
#   See LICENSE URL <https://store.webkul.com/license.html/> for full copyright and licensing details.
#################################################################################
import logging
_logger = logging.getLogger(__name__)

from odoo import api, fields, models, _


class exportmagento2xattributes(models.TransientModel):
    _name = 'export.attributes.magento'
    _inherit = ['export.attributes']

    @api.model
    def magento2x_get_attribute_value(self, attribute_id, channel_id):

        result = []
        Value = self.env['product.attribute.value']
        value_mappings =channel_id.match_attribute_value_mappings(limit = None)
        domain =[
            ('attribute_id','=',attribute_id.id),
            ('id','not in',value_mappings.mapped('odoo_attribute_value_id'))
        ]
        for value in Value.search(domain):
            vals =dict(
                label = value.name,
            )
            result+=[vals]
        return result

    @api.model
    def magento2x_get_attribute_data(self, attribute_id, channel_id):

        data = {
                "scope": "global",
                "options":self.magento2x_get_attribute_value(attribute_id, channel_id),
                "attribute_code":'%s'%attribute_id.name.lower().replace(" ", "_").replace("-", "_").strip(),
                "frontend_input": "select",
                "is_visible_on_front": "1",
                "is_user_defined": True,
                "default_frontend_label": '%s'%(attribute_id.name),
        }
        return data


    @api.model
    def magento2x_create_attribute_data(self,sdk,attribute_id,channel_id):
        mapping_obj = self.env['channel.attribute.mappings']
        result=dict(
            mapping_id=None,
            message='',
        )
        message=''
        mapping_id = None
        data_res = self.magento2x_get_attribute_data(
            attribute_id = attribute_id,
            channel_id = channel_id
        )
        attributes_res =sdk.post_products_attributes(data_res)
        data = attributes_res.get('data')
        if not data:
            result['message']+=attributes_res.get('message')
            return result
        else:
            store_id  =data.get('attribute_id')
            mapping_id = channel_id.create_attribute_mapping(
                erp_id=attribute_id,
                store_id=store_id,
                store_attribute_name= data.get('attribute_code')
            )
            result['mapping_id'] = mapping_id

        return result

    @api.model
    def magento2x_update_attribute_data(self,sdk,channel_id,attribute_id):
        mapping_obj = self.env['channel.attribute.mappings']
        result=dict(
            mapping_id=None,
            message=''
        )
        message=''
        mapping_id = None
        match = self.channel_id.match_attribute_mappings(
            odoo_attribute_id =attribute_id.id
        )
        if not match:
            message+='Mapping not exits for attribute %s [%s].'%(attribute_id.name,attribute_id.id)
        else:
            options = self.magento2x_get_attribute_value(
                attribute_id = attribute_id,
                channel_id = channel_id
            )
            for option in options:
                data =sdk.post_products_attributes(
                    data = option,
                    attribute_code = match.store_attribute_name
                )
                msz = data.get('message','')
                if msz: message+='While Value (%s) Update %s'%(option.get('label'),data.get('message',''))
            mapping_id=match
            match.need_sync='no'
        result['mapping_id']=mapping_id
        return result
    @api.model
    def create_magento2x_update_value_mapping(self,sdk,channel_id,attribute_ids):
        Attribute = self.env['product.attribute']
        items = channel_id._fetch_magento2x_product_attributes(sdk).get('data') or {}
        res = self.env['import.magento2x.attributes']._magento2x_import_attributes(
                Attribute,
                channel_id = channel_id,
                items = items,
                sdk = sdk,
        )


    @api.model
    def magento2x_post_attributes_data(self,sdk,channel_id,attribute_ids,operation):
        message = ''
        create_ids = self.env['channel.attribute.mappings']
        update_ids = self.env['channel.attribute.mappings']
        status = True
        for attribute_id in attribute_ids:
            odoo_id = attribute_id.id
            message += '<br/>==>For Attribute %s [%s] Operation (%s) <br/>'%(attribute_id.name,odoo_id,operation)
            sync_vals = dict(
                status ='error',
                action_on ='attribute',
                action_type ='export',
                odoo_id = odoo_id
            )
            post_res = dict()
            if operation == 'export':
                post_res=self.magento2x_create_attribute_data(sdk,attribute_id,channel_id)
                if post_res.get('mapping_id'):
                    create_ids+=post_res.get('mapping_id')
            else:
                post_res=self.magento2x_update_attribute_data(sdk,channel_id,attribute_id)
                if post_res.get('mapping_id'):
                    update_ids+=post_res.get('mapping_id')
            msz = post_res.get('message')
            if msz and status:
                status  = False
            if post_res.get('mapping_id'):
                message +='<br/> Attribute ID[%s]  Operation(%s) done.'%(odoo_id,operation)
                sync_vals['status'] = 'success'
                sync_vals['ecomstore_refrence'] =post_res.get('mapping_id').store_attribute_id
            sync_vals['summary'] = msz or '%s %sed'%(attribute_id.name,operation)
            channel_id._create_sync(sync_vals)
            message+=msz
        if len(create_ids+update_ids):
            self.create_magento2x_update_value_mapping(sdk,channel_id,attribute_ids)
        return dict(
            status = status,
            message=message,
            update_ids=update_ids,
            create_ids=create_ids,

        )


    def magento2x_export_attributes(self):
        message = ''
        ex_create_ids,ex_update_ids,create_ids,update_ids= [],[],[],[]
        for record in self:
            channel_id = record.channel_id
            res =channel_id.get_magento2x_sdk()
            sdk = res.get('sdk')
            if not sdk:
                message+=res.get('message')
            else:
                exclude_res=record.exclude_export_data(
                    record.attribute_ids,channel_id,record.operation,model='attribute',domain=[]
                )
                attributes=exclude_res.get('object_ids')
                ex_update_ids+=exclude_res.get('ex_update_ids')
                ex_create_ids+=exclude_res.get('ex_create_ids')
                if not len(attributes):
                    message+='No Attribute filter for %s over magento'%(record.operation)
                else:
                    post_res=record.magento2x_post_attributes_data(sdk,channel_id,attributes,record.operation)
                    create_ids+=post_res.get('create_ids')
                    update_ids+=post_res.get('update_ids')
                    message+=post_res.get('message')
            message+=self.env['multi.channel.sale'].get_operation_message_v1(
                obj = 'product attribute',
                obj_model = '',
                operation = 'exported',
                obj_ids = create_ids
            )
            message+=self.env['multi.channel.sale'].get_operation_message_v1(
                obj = 'product attribute',
                obj_model = '',
                operation = 'updated',
                obj_ids = update_ids
            )
            return self.env['multi.channel.sale'].display_message(message)
