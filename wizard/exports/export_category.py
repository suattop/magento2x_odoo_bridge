# -*- coding: utf-8 -*-
#################################################################################
#
#   Copyright (c) 2017-Present Webkul Software Pvt. Ltd. (<https://webkul.com/>)
#   See LICENSE URL <https://store.webkul.com/license.html/> for full copyright and licensing details.
#################################################################################
import logging

from odoo import api, fields, models, _
_logger = logging.getLogger(__name__)


class response_object:

    def __init__(self,rid):
        self.id = rid

class exportmagento2xcategories(models.TransientModel):
    _inherit = ['export.categories']

    @api.model
    def magento2x_get_category_data(self, category_id, channel_id):
        store_parent_id = 2
        mapping_id = False
        if category_id.parent_id:
            mapping_id = channel_id.match_category_mappings(
                odoo_category_id =category_id.parent_id.id
            )
        data = {
          "parent_id": int(mapping_id.store_category_id) if mapping_id else store_parent_id,
          "name": category_id.name,
          "is_active": True,

        }
        return data


    @api.model
    def magento2x_create_category_data(self, sdk, category_id,  channel_id, op_type):
        mapping_obj = self.env['channel.category.mappings']
        result=dict(
            mapping_id=None,
            message=''
        )
        mapping_id = None
        data_res = self.magento2x_get_category_data(
            category_id = category_id,
            channel_id = channel_id,
        )
        categories_res =sdk.post_categories(data_res)
        data = categories_res.get('data')
        if not data:
            result['message']+=categories_res.get('message')
        else:
            store_id  =data.get('id')
            if op_type == 'individual':
                mapping_id = channel_id.create_category_mapping(
                erp_id=category_id,
                store_id=store_id,
                leaf_category=True if not category_id.child_id else False
                )
                result['mapping_id'] = mapping_id
            else:
                result['store_id']=store_id
        return result
        


    @api.model
    def magento2x_update_category_data(self,sdk,channel_id,category_id,op_type):
        mapping_obj = self.env['channel.category.mappings']
        result=dict(
            mapping_id=None,
            message=''
        )
        mapping_id = None
        match = channel_id.match_category_mappings(
            odoo_category_id =category_id.id
        )
        if not match:
            result['message']+='Mapping not exits for category %s [%s].'%(category_id.name,category_id.id)
        else:
            category_data = self.magento2x_get_category_data(
            category_id = category_id,
            channel_id = channel_id
            )
        data =sdk.post_categories(
            data = category_data,
            category_id = match.store_category_id
        )
        msz = data.get('message','')
        if not msz:
            # result['message'] = msz
            # return result
            if data.get('data') and int(match.store_category_id) != 2:
                parent_id = data.get('data',{}).get('parent_id',False)
                if parent_id and category_data.get('parent_id') != int(parent_id):
                    result = sdk.move_category(data=dict(parentId=category_data.get('parent_id'),afterId=0),category_id=match.store_category_id)
                    if result:
                        pass
            mapping_id=match
            match.need_sync='no'
            result['mapping_id']=mapping_id
        else:
            result['message']+='While Category %s Update %s'%(category_data.get('name'),data.get('message',''))
            result['store_id'] = match.store_category_id
        return result

    @api.model
    def magento2x_post_categories_bulk_data(self,sdk,channel_id,category_id,operation):
        if operation == 'export':
            post_res=self.magento2x_create_category_data(sdk,category_id,channel_id,'bulk')
        else:
            post_res=self.magento2x_update_category_data(sdk,channel_id,category_id,'bulk')
        if post_res.get('message'):
            return False,False
        return True,response_object(post_res.get('store_id'))

    @api.model
    def magento2x_post_categories_data(self,sdk,channel_id,category_ids):
        message = ''
        create_ids = self.env['channel.category.mappings']
        update_ids = self.env['channel.category.mappings']

        operation = self.operation
        category_dict = dict()
        status = True
        for category_id in category_ids.sorted('id'):
            category_obj_id = category_id.id
            message += '<br/>==>For Category %s [%s] Operation (%s) <br/>'%(category_id.name,category_obj_id,operation)
            try:
                sync_vals = dict(
                    status ='error',
                    action_on ='category',
                    action_type ='export',
                    odoo_id = category_obj_id
                )
                post_res = dict()
                if operation == 'export':
                    post_res=self.magento2x_create_category_data(sdk,category_id,channel_id,"individual")
                    if post_res.get('mapping_id'):
                        create_ids+=post_res.get('mapping_id')
                else:
                    post_res=self.magento2x_update_category_data(sdk,channel_id,category_id,"individual")
                    if post_res.get('mapping_id'):
                        update_ids+=post_res.get('mapping_id')
                msz = post_res.get('message')
                if status and msz:
                    status = False
                if post_res.get('mapping_id'):
                    sync_vals['status'] = 'success'
                    message +='<br/> Category ID[%s]  Operation(%s) done.'%(category_obj_id,operation)
                    sync_vals['ecomstore_refrence'] =post_res.get('mapping_id').store_category_id
                sync_vals['summary'] = msz or '%s %sed'%(category_id.name,operation)
                channel_id._create_sync(sync_vals)
                if msz:message += '%r' % msz
            except Exception as e:
                message += ' %r' % e
        self._cr.commit()
        return dict(
            status  = status,
            message=message,
            update_ids=update_ids,
            create_ids=create_ids,

        )


    def magento2x_export_categories(self):
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
                    record.category_ids,channel_id,record.operation,model='category',domain=[]
                )
                categories=exclude_res.get('object_ids')

                if not len(categories):
                    message+='No category filter for %s over magento'%(record.operation)
                else:
                    post_res=record.magento2x_post_categories_data(sdk,channel_id,categories)
                    create_ids+=post_res.get('create_ids')
                    update_ids+=post_res.get('update_ids')
                    message+=post_res.get('message')
        message+=self.env['multi.channel.sale'].get_operation_message_v1(
            obj = 'product category',
            obj_model = '',
            operation = 'exported',
            obj_ids = create_ids
        )
        message+=self.env['multi.channel.sale'].get_operation_message_v1(
            obj = 'product category',
            obj_model = '',
            operation = 'updated',
            obj_ids = update_ids
        )
        return self.env['multi.channel.sale'].display_message(message)
