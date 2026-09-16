{
    'name': "Bureau de change",
    'summary': "Gestion des opérations de change (achat/vente de devises)",
    'description': """
Bureau de change
=================

Module métier pour un bureau de change (client unique, base de test).

- Cours du jour par devise (achat / vente)
- Position en devises valorisée au coût moyen pondéré (CMP)
- Opérations de change (fx.deal) générant nativement une facture client
  (vente de devises) ou une facture fournisseur (achat de devises), avec
  comptabilisation explicite de la marge de change

Ce module dépend uniquement du module Comptabilité (account) : la balance,
le lettrage, la balance auxiliaire et les rapports comptables (SYSCOHADA)
restent entièrement natifs. Aucune écriture manuelle de type "entry" : chaque
opération de change est une facture, avec ses propres comptes paramétrables.
""",
    'version': '19.0.1.0.0',
    'category': 'Accounting/Accounting',
    'author': "Toftal Technologies",
    'license': 'LGPL-3',
    'depends': ['account'],
    'data': [],
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
