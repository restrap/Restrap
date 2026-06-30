{
    "name": "Restrap Production Time Dashboard",
    "summary": "Custom dashboard showing required production time across Shopify channels and internal transfers.",
    "version": "17.0.1.0.0",
    "category": "Manufacturing",
    "author": "Hamdek",
    "website": "https://hamdek.com",
    "license": "OPL-1",
    "depends": [
        "web",
        "mrp",
        "sale_management",
        "stock",
        "shopify_ept",
    ],
    "data": [
        "security/ir.model.access.csv",
        "views/production_dashboard_views.xml",
        "views/menu.xml",
        "data/ir_cron.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "hdk_production_dashboard/static/src/js/dashboard.js",
            "hdk_production_dashboard/static/src/js/chart_renderer.js",
            "hdk_production_dashboard/static/src/xml/dashboard.xml",
            "hdk_production_dashboard/static/src/scss/dashboard.scss",
        ],
    },
    "installable": True,
    "application": True,
}
