# -*- coding: utf-8 -*-
{
    "name": "Restrap Module",
    "version": "15.0.1",
    "author": "Smart IT Ltd",
    "category": "Other",
    "summary": "Zelus",
    'description': "Custom module for Restrap developed by Smart IT Ltd",
    'maintainer': "Smart IT Ltd",
    'website': 'smart-ltd.co.uk',
    "depends": ['base', 'mrp_workorder', 'sale_management'],
    "data": [
        'security/mrp_security.xml',
        'security/ir.model.access.csv',
        'wizard/sale_order_merge_wizard.xml',
        'views/res_config_settings_view.xml',
        'views/mrp_production_views.xml',
        'views/mrp_workorder_views.xml',
        'views/sale_order_views.xml',
    ],
}