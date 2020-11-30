# -*- coding: utf-8 -*-
#################################################################################
#
#   Copyright (c) 2017-Present Webkul Software Pvt. Ltd. (<https://webkul.com/>)
#   See LICENSE URL <https://store.webkul.com/license.html/> for full copyright and licensing details.
#################################################################################
import logging
import itertools

from odoo import api, fields, models, _

_logger = logging.getLogger(__name__)

Source = [
    ('all','All')
]

class Importmagento2xattributes(models.TransientModel):
    _inherit = ['channel.operation']

    _name = "import.magento2x.attributes.sets"
    _description = "import.magento2x.attributes.sets"
    source = fields.Selection(Source, required=1, default='all')

    @staticmethod
    def get_attribute_set_vals(data,**kwargs):
        """Parse  data in odoo format and return as dict vals ."""


        attribute_set_id = data.get('attribute_set_id')
        odoo_attribute_ids = kwargs.get('odoo_attribute_ids')
        return dict(
        set_name = data.get('attribute_set_name'),
        store_id = attribute_set_id,
        attribute_ids = [(6,0,odoo_attribute_ids)]
        )


    @staticmethod
    def _magento2x_update_attribute_set_feed(match,vals,**kwargs):
        """Update  attribute set  with then vals."""
        return match.write(vals)


    @staticmethod
    def _magento2x_create_attribute_set_feed(set_obj,channel_id,  attribute_set_id, vals,**kwargs):
        """Create new  attribute set for given vals."""
        vals['store_id']=attribute_set_id
        return  channel_id._create_obj(set_obj, vals)


    @classmethod
    def _magento2x_import_attribute(cls, set_obj,channel_id, attribute_set_id, data,**kwargs):
        """
        Import attributes set in odoo.
        :param set_obj: attributes set model ==> self.env['magento.attributes.set']
        :param channel_id: channel instance of magento   ==> multi.channel.sale(1)
        :attribute_set_id: magento attribute set id ==> 4
        :data: magento attribute set data dict
        :return: error in example pointed by example number.
        Note: If attributes set exits, then don't create a new attributes set.
        """

        match = channel_id._match_feed(
            set_obj, [('store_id', '=', attribute_set_id)])
        update =False

        # extact  attribute set vals from  magento 2.x attribute set  data .
        vals = cls.get_attribute_set_vals(data, **kwargs)

        if match:
            update=cls._magento2x_update_attribute_set_feed( match,  vals)
            update  =True
        else:
            match= cls._magento2x_create_attribute_set_feed(set_obj,channel_id, attribute_set_id, vals)
        return dict(
            feed_id=match,
            update=update
        )

    @staticmethod
    def get_magento2x_odoo_attribute_ids(sdk,attribute_set_id,attribute_ids,**kwargs):
        set_data = sdk.get_products_attribute_sets(attribute_set_id).get('data',{})
        attribute_set_atrr_ids = set(map(
            lambda item:item.get('attribute_id'),set_data and set_data or dict()))
        attribute_ids = list(set(attribute_ids).intersection(
            attribute_set_atrr_ids))
        odoo_attribute_ids = kwargs.get('attributes_mapping').filtered(
            lambda mapping:int(mapping.store_attribute_id) in attribute_ids
        ).mapped('odoo_attribute_id')
        return odoo_attribute_ids

    @classmethod
    def _magento2x_import_attribute_sets(cls, set_obj, channel_id, items, sdk, attribute_ids, **kwargs):
        """Import attributes sets in odoo.

        Args:
            set_obj: Attributes set model ==> self.env['magento.attributes.set']
            channel_id: Channel instance of magento   ==> multi.channel.sale(1)
            items: Magento attribute sets data dict
        Returns:
            A dict (create_ids , update_ids) of newly created and updated attributes sets ids.
        """

        create_ids ,update_ids = [] , []

        for item in items.get('items') or []:
            attribute_set_id = item.get('attribute_set_id')
            odoo_attribute_ids = cls.get_magento2x_odoo_attribute_ids(
                sdk = sdk,attribute_set_id = attribute_set_id,
                attribute_ids = attribute_ids,**kwargs
            )
            import_res =   cls._magento2x_import_attribute(
                set_obj = set_obj,
                channel_id = channel_id,
                attribute_set_id = attribute_set_id,
                odoo_attribute_ids = odoo_attribute_ids,
                data = item,
                **kwargs
            )
            feed_id = import_res.get('feed_id')

            if import_res.get('update'):
                update_ids.append(feed_id)
            else:
                create_ids.append(feed_id)

        return dict(
            create_ids = create_ids,
            update_ids = update_ids,
        )

    @api.model
    def _magento2x_import_attributes(self, channel_id, attributes,sdk):
        """Import magento attributes in odoo."""
        ImportMagento2xAttributes = self.env['import.magento2x.attributes']
        AttributesMappping = self.env['channel.attribute.mappings']
        Attribute = self.env['product.attribute']

        # Create import.magento2x.attributes instance with source=all and operation=import.
        vals =dict(
            channel_id=channel_id.id,
        )
        record =ImportMagento2xAttributes.create(vals)

        #Import magento2x attributes in odoo.
        res= record._magento2x_import_attributes(
            attribute_obj = Attribute,
            channel_id = channel_id,
            items = attributes,
            sdk=sdk
        )

        #Merge all crated and updated attributes odoo mapping.
        AttributesMappping+=res.get('create_ids')
        AttributesMappping+=res.get('update_ids')
        return AttributesMappping


    def import_now(self,kwargs=dict()):
        """Import magento attributes sets in odoo."""
        create_ids,update_ids,map_create_ids,map_update_ids=[],[],[],[]
        message=''
        AttributesSet = self.env['magento.attributes.set']

        for record in self:
            channel_id = record.channel_id

            # Create the magento sdk instance .
            res =channel_id.get_magento2x_sdk()
            sdk = res.get('sdk')

            if not sdk:
                message+=res.get('message')
            else:
                # Fetch  attributes (is_global=True, is_user_defined=True, frontend_input=select ).
                attribute_res = channel_id._fetch_magento2x_product_attributes(sdk = sdk)
                message+= attribute_res.get('message','')
                attributes =  attribute_res.get('data') or {}


                # Import  all attributes.
                attributes_mapping = self._magento2x_import_attributes(channel_id, attributes,sdk)
                attribute_ids =[item.get('attribute_id') for item in (attributes.get('items') or [])]
                # Fetch all attributes  sets .
                fetch_res =sdk.get_products_attribute_sets()
                attribute_sets = fetch_res.get('data') or {}
                message+= fetch_res.get('message','')

                if not attribute_ids and attribute_sets:
                    message+="Attribute Sets data not received."
                else:

                    # Import  all attributes  sets .
                    feed_res=record._magento2x_import_attribute_sets(
                        set_obj = AttributesSet,
                        channel_id = channel_id,
                        items = attribute_sets,
                        sdk = sdk,
                        attribute_ids = attribute_ids,
                        attributes_mapping = attributes_mapping,
                    )
                    create_ids+=feed_res.get('create_ids')
                    update_ids+=feed_res.get('update_ids')
        kwargs.update(
            message=message
        )
        return dict(
            create_ids=create_ids,
            update_ids=update_ids,
            message=message
        )
        # Get Message about create and updated  attributes  sets .
        message+=self.env['multi.channel.sale'].get_operation_message_v1(
            obj = 'attribute set',
            obj_model = 'record',
            operation = 'created',
            obj_ids = create_ids
        )
        message+=self.env['multi.channel.sale'].get_operation_message_v1(
            obj = 'attribute set',
            obj_model = 'record',
            operation = 'updated',
            obj_ids = update_ids
        )
        return self.env['multi.channel.sale'].display_message(message)


