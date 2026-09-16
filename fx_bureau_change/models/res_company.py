from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    fx_journal_id = fields.Many2one(
        'account.journal',
        string="Journal des opérations de change",
        domain="[('company_id', '=', id), ('type', '=', 'general')]",
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
