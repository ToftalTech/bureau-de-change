from odoo import Command, fields, models, _


class FxCurrencyAccount(models.Model):
    _name = 'fx.currency.account'
    _description = "Compte de position par devise"

    company_id = fields.Many2one(
        'res.company', required=True, default=lambda self: self.env.company,
    )
    currency_id = fields.Many2one('res.currency', required=True, string="Devise")
    account_id = fields.Many2one(
        'account.account', required=True, string="Compte de position",
        domain="[('company_ids', 'in', company_id)]",
    )
    product_id = fields.Many2one(
        'product.product', string="Produit de facturation", readonly=True, copy=False,
    )

    def _get_or_create_product(self):
        """Produit technique (service) portant la ligne de cession/acquisition
        de la devise sur le bon de commande. Son compte de revenu/charge est
        aligné sur ``account_id`` : la ligne facturée retombe sur le compte de
        position de la devise, pas sur un compte générique de vente/achat."""
        self.ensure_one()
        if not self.product_id:
            product = self.env['product.product'].sudo().create({
                'name': _("Devise %s (change)", self.currency_id.name),
                'type': 'service',
                'invoice_policy': 'order',
                'sale_ok': True,
                'purchase_ok': True,
                'property_account_income_id': self.account_id.id,
                'property_account_expense_id': self.account_id.id,
                'taxes_id': [Command.clear()],
                'supplier_taxes_id': [Command.clear()],
            })
            self.product_id = product.id
        return self.product_id

    _sql_constraints = [
        ('currency_company_uniq', 'unique(company_id, currency_id)',
         "Un seul compte de position peut être défini par devise et par société."),
    ]

    def _compute_display_name(self):
        for rec in self:
            rec.display_name = rec.currency_id.name or ""
