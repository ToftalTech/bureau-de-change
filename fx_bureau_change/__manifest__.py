{
    'name': "Bureau de change",
    'summary': "Gestion des opérations de change (achat/vente de devises)",
    'description': """
Bureau de change
=================

Module métier pour un bureau de change (client unique, base de test).

- Cours du jour par devise (achat / vente)
- Position en devises valorisée au coût moyen pondéré (CMP)
- Opérations de change (fx.deal) qui pilotent un bon de commande client
  (vente de devises) ou un bon de commande fournisseur (achat de devises)
  natif, lequel génère lui-même sa facture via les flux standards Vente et
  Achat, avec comptabilisation explicite de la marge de change

Ce module s'appuie sur Contacts, Ventes, Achats et Comptabilité : la balance,
le lettrage, la balance auxiliaire, les rapports SYSCOHADA et le cycle
devis/commande/facture restent entièrement natifs. Le CMP est calculé par ce
module (fx.rate / fx.position) ; la comptabilisation de chaque opération
passe par un vrai bon de commande, jamais par une écriture manuelle.
""",
    'version': '19.0.1.0.0',
    'category': 'Accounting/Accounting',
    'author': "Toftal Technologies",
    'license': 'LGPL-3',
    'depends': ['contacts', 'sale', 'purchase', 'account'],
    'data': [
        'security/fx_security.xml',
        'security/ir.model.access.csv',
        'data/ir_sequence_data.xml',
        'views/fx_deal_views.xml',
        'views/fx_position_views.xml',
        'views/fx_rate_views.xml',
        'views/res_company_views.xml',
    ],
    'demo': [
        'demo/account_demo.xml',
        'demo/res_partner_demo.xml',
        'demo/fx_position_demo.xml',
        'demo/fx_rate_demo.xml',
        'demo/fx_deal_demo.xml',
    ],
    'installable': True,
    'application': True,
}
