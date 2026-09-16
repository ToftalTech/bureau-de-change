from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError
from odoo.tools import float_compare


class FxRate(models.Model):
    _name = 'fx.rate'
    _description = "Cours du jour"
    _order = 'date desc, currency_id'

    currency_id = fields.Many2one('res.currency', required=True, string="Devise")
    date = fields.Date(required=True, default=fields.Date.context_today)
    rate_buy = fields.Float(
        string="Cours d'achat", required=True, digits=(16, 4),
        help="Cours auquel le bureau achète la devise au client (XOF pour 1 unité de devise).",
    )
    rate_sell = fields.Float(
        string="Cours de vente", required=True, digits=(16, 4),
        help="Cours auquel le bureau vend la devise au client (XOF pour 1 unité de devise).",
    )
    reference_rate = fields.Float(
        string="Cours de référence", digits=(16, 4),
        help="Cours de marché / BCEAO, à titre indicatif.",
    )
    source = fields.Selection(
        [('manual', "Manuel"), ('auto', "Automatique")],
        string="Source", required=True, default='manual',
    )
    company_id = fields.Many2one(
        'res.company', required=True, default=lambda self: self.env.company,
    )

    _sql_constraints = [
        ('currency_date_company_uniq', 'unique(currency_id, date, company_id)',
         "Un seul cours peut être défini par devise, par date et par société."),
    ]

    @api.constrains('rate_buy', 'rate_sell', 'reference_rate')
    def _check_rates_positive(self):
        for rate in self:
            if rate.rate_buy <= 0 or rate.rate_sell <= 0:
                raise ValidationError(_(
                    "Les cours d'achat et de vente doivent être strictement positifs."
                ))
            if rate.reference_rate and rate.reference_rate <= 0:
                raise ValidationError(_(
                    "Le cours de référence doit être strictement positif s'il est renseigné."
                ))

    @api.constrains('rate_buy', 'rate_sell')
    def _check_margin_not_negative(self):
        for rate in self:
            if float_compare(rate.rate_sell, rate.rate_buy, precision_digits=4) < 0:
                raise ValidationError(_(
                    "Le cours de vente (%(sell)s) ne peut pas être inférieur au cours "
                    "d'achat (%(buy)s) : cela génèrerait une marge négative.",
                    sell=rate.rate_sell, buy=rate.rate_buy,
                ))

    @api.model
    def get_rate(self, currency, date, direction, company=None):
        """Cours applicable le plus récent à ``date`` (inclus) pour ``currency``.

        ``direction`` vaut 'buy' (le bureau achète la devise -> rate_buy) ou
        'sell' (le bureau vend la devise -> rate_sell).
        """
        if direction not in ('buy', 'sell'):
            raise ValueError("direction must be 'buy' or 'sell'")
        company = company or self.env.company
        rate = self.search([
            ('currency_id', '=', currency.id),
            ('company_id', '=', company.id),
            ('date', '<=', date),
        ], order='date desc', limit=1)
        if not rate:
            raise UserError(_(
                "Aucun cours n'est défini pour %(currency)s à la date du %(date)s "
                "ou avant.",
                currency=currency.name, date=date,
            ))
        return rate.rate_buy if direction == 'buy' else rate.rate_sell
