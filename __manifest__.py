# -*- coding: utf-8 -*-
#################################################################################
# Author      : Webkul Software Pvt. Ltd. (<https://webkul.com/>)
# Copyright(c): 2015-Present Webkul Software Pvt. Ltd.
# All Rights Reserved.
#
#
#
# This program is copyright property of the author mentioned above.
# You can`t redistribute it and/or modify it.
#
#
# You should have received a copy of the License along with this program.
# If not, see <https://store.webkul.com/license.html/>
#################################################################################
{
  "name"                 :  "Multi Channel  Magento 2.X Odoo Bridge(Multi Channel-MOB)",
  "summary"              :  "Integrate Magento 2 marketplace with Odoo. Configure your Magento 2 store with Odoo. Manage orders, customers, products, etc at Odoo’s end.",
  "category"             :  "Website",
  "version"              :  "1.1.0",
  "sequence"             :  1,
  "author"               :  "Webkul Software Pvt. Ltd.",
  "license"              :  "Other proprietary",
  "website"              :  "https://store.webkul.com/Multi-Channel-Magento-2-x-Odoo-Bridge-Multi-Channel-MOB.html",
  "description"          :  """Magento 2 Odoo bridge
Multi Channel Magento 2.x Odoo Bridge(Multi Channel-MOB)
Multi Channel Magento 1.x Odoo Bridge(Multi Channel-MOB)
Odoo magento bridge
Magento 2
Magento2
Magento Odoo connector
Magento to Odoo
Manage orders
Manage products
Import products
Import customers 
Import orders
Ebay to Odoo
Odoo multi-channel bridge
Multi channel connector
Multi platform connector
Multiple platforms bridge
Connect Amazon with odoo
Amazon bridge
Flipkart Bridge
Magento Odoo Bridge
Odoo magento bridge
Woocommerce odoo bridge
Odoo woocommerce bridge
Ebay odoo bridge
Odoo ebay bridge
Multi channel bridge
Prestashop odoo bridge
Odoo prestahop
Akeneo bridge
Marketplace bridge
Multi marketplace connector
Multiple marketplace platform
multi channel multichannel multi-channel magento multichannel magento2 multichannel magento bridge magento2 bridge magento connector magento2 connector magento2 odoo bridge odoo magento2 odoo""",
  "live_test_url"        :  "http://magento2odoo.webkul.com/",
  "depends"              :  ['odoo_multi_channel_sale'],
  "data"                 :  [
                             'security/ir.model.access.csv',
                             'data/data.xml',
                             'views/dashboard.xml',
                             'views/search.xml',
                             'wizard/export_operation.xml',
                             'wizard/inherits.xml',
                             'wizard/import_operation.xml',
                             'views/views.xml',
                            ],
  'qweb'  : [
    'static/src/xml/instance_dashboard.xml',
  ],
  'demo'  : [
    'data/demo.xml',
  ],
  "images"               :  ['static/description/Banner.png'],
  "application"          :  True,
  "installable"          :  True,
  "auto_install"         :  False,
  "price"                :  100,
  "currency"             :  "EUR",
}