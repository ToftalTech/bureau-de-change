from odoo import Command, fields, models, _
from odoo.exceptions import UserError


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
    fx_margin_product_id = fields.Many2one(
        'product.product', string="Produit de facturation - marge de change",
        readonly=True, copy=False,
    )

    def _get_fx_position_account(self, currency):
        """Retourne le compte de position paramétré pour ``currency``, vide si absent."""
        self.ensure_one()
        line = self.fx_currency_account_ids.filtered(lambda l: l.currency_id == currency)
        return line[:1].account_id

    def _get_or_create_fx_margin_product(self):
        """Produit technique (service) utilisé pour porter la ligne de marge
        sur le bon de commande de vente. Son compte de revenu est aligné sur
        ``fx_margin_account_id`` à la création : la ligne facturée retombe
        bien sur le compte de marge paramétré, pas sur un compte générique."""
        self.ensure_one()
        if not self.fx_margin_account_id:
            raise UserError(_(
                "Aucun compte de marge de change n'est configuré pour la "
                "société %s.", self.name,
            ))
        if not self.fx_margin_product_id:
            product = self.env['product.product'].sudo().create({
                'name': _("Marge de change"),
                'type': 'service',
                'invoice_policy': 'order',
                'sale_ok': True,
                'purchase_ok': False,
                'property_account_income_id': self.fx_margin_account_id.id,
                'taxes_id': [Command.clear()],
            })
            self.fx_margin_product_id = product.id
        return self.fx_margin_product_id
