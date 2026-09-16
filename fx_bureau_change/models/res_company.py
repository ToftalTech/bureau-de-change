from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    fx_sale_journal_id = fields.Many2one(
        'account.journal',
        string="Journal des ventes de devises",
        domain="[('company_id', '=', id), ('type', '=', 'sale')]",
        help="Journal utilisé pour la facture client générée lors d'une vente "
             "de devises. Odoo impose un journal de type 'Ventes' pour toute "
             "facture client (out_invoice).",
    )
    fx_purchase_journal_id = fields.Many2one(
        'account.journal',
        string="Journal des achats de devises",
        domain="[('company_id', '=', id), ('type', '=', 'purchase')]",
        help="Journal utilisé pour la facture fournisseur générée lors d'un "
             "achat de devises. Odoo impose un journal de type 'Achats' pour "
             "toute facture fournisseur (in_invoice).",
    )
    fx_margin_account_id = fields.Many2one(
        'account.account',
        string="Compte de marge de change",
        domain="[('company_ids', 'in', id)]",
    )
    fx_currency_account_ids = fields.One2many(
        'fx.currency.account', 'company_id',
        string="Comptes de position par devise",
    )

    def _get_fx_position_account(self, currency):
        """Retourne le compte de position paramétré pour ``currency``, vide si absent."""
        self.ensure_one()
        line = self.fx_currency_account_ids.filtered(lambda l: l.currency_id == currency)
        return line[:1].account_id
