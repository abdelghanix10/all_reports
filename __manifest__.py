{
    'name': 'All Reports',
    'version': '20.0.2.0.0',
    'category': 'Reporting',
    'summary': 'Consolidated Dashboard for POS, Production, Top Products, and Inventory Loss',
    'depends': ['base', 'point_of_sale', 'mrp', 'stock', 'web'],
    'data': [
        'security/all_reports_security.xml',
        'security/ir.access.csv',
        'views/all_reports_menus.xml',
        'views/res_users_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'all_reports/static/src/scss/dashboard.scss',
            'all_reports/static/src/xml/dashboard.xml',
            'all_reports/static/src/js/dashboard.js',
        ],
    },
    'installable': True,
    'application': True,
    'license': 'LGPL-3',
}