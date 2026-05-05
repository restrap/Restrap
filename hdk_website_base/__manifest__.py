# -*- coding: utf-8 -*-
#################################################################################
# Author: Hamdek
# Copyright(c): 2026-TODAY Hamdek
# All Rights Reserved.
#
# This program is copyright property of the author mentioned above.
# You can`t redistribute it and/or modify it.
#
# You should have received a copy of the License along with this program.
#################################################################################
{
    'name': "Hamdek Website Base",
    'summary': "This will help in website for Enabling Features develop by Hamdek.",

    'author': "Hamdek",
    'website': "https://www.hamdek.com",
    'live_test_url': 'https://www.hamdek.com/get-demo?module=hdk_sale_base',
    'license': 'OPL-1',
    'version': '17.0.1.0.0',
    "category": 'website',

    # any module necessary for this one to work correctly
    'depends': ['base', 'website'],

    # always loaded
    'data': [
        'views/view_res_config_setting.xml',
    ],

    'images': ['static/description/images/icon.png'],

    'application': False,
    'installable': True,
    'auto_install': False,
}
