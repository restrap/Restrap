{
    "name": "Restrap Sales Dashboard",
    "summary": "Channel-split sales dashboard: revenue, AOV, fulfillment time, cash cycle and production time per order.",
    "version": "17.0.1.0.0",
    "category": "Sales",
    "author": "Hamdek",
    "website": "https://hamdek.com",
    "license": "OPL-1",
    "depends": [
        "web",
        "sale_management",
        "account",
        "stock",
        "shopify_ept",
        "hdk_production_dashboard",
    ],
    "data": [
        "security/ir.model.access.csv",
        "views/sales_dashboard_views.xml",
        "views/menu.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "hdk_sales_dashboard/static/src/js/sales_dashboard.js",
            "hdk_sales_dashboard/static/src/xml/sales_dashboard.xml",
            "hdk_sales_dashboard/static/src/scss/sales_dashboard.scss",
        ],
    },
    "installable": True,
    "application": True,
}
