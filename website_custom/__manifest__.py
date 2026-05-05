{
    'name': 'Website Custom',
    'version': '17.9',
    'author': 'Pragmatic TechSoft Pvt Ltd.',
    'website': 'http://www.pragtech.co.in',
    'category': 'Website',
    'summary': '',
    'description': """ """,
    'depends': ['website', 'website_sale','web','stock','website_sale_stock'],
    'data': [
        'views/website_view.xml',
    ],
    'assets': {
        
        'web.assets_frontend': [
            'website_custom/static/src/js/cash_on_delivery.js',
        ],
    },
    'license': 'OPL-1',
    'installable': True,
    'application': True,
    'auto_install': False,
}
