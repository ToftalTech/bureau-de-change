from odoo import fields, models


class FxCurrencyAccount(models.Model):
    _name = 'fx.currency.account'
    _description = "Compte de position par devise"

    company_id = fields.Many2one(
        'res.company', required=True, default=lambda self: self.env.company,
    )
    currency_id = fields.Many2one('res.currency', required=True, string="Devise")
    account_id = fields.Many2one(
        'account.account', required=True, string="Compte de position",
        domain="[('company_id', '=', company_id)]",
    )

    _sql_constraints = [
        ('currency_company_uniq', 'unique(company_id, currency_id)',
         "Un seul compte de position peut être défini par devise et par société."),
    ]

    def _compute_display_name(self):
        for rec in self:
            rec.display_name = rec.currency_id.name or ""
