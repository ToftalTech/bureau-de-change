from odoo import api, fields, models, _
from odoo.exceptions import UserError
from odoo.tools import float_compare, float_round

PRECISION = 4


class FxPosition(models.Model):
    _name = 'fx.position'
    _description = "Position en devise (coût moyen pondéré)"
    _order = 'currency_id'

    currency_id = fields.Many2one('res.currency', required=True, string="Devise")
    company_id = fields.Many2one(
        'res.company', required=True, default=lambda self: self.env.company,
    )
    quantity = fields.Float(string="Quantité en stock", digits=(16, PRECISION), default=0.0)
    value_xof = fields.Float(string="Valeur (XOF)", digits=(16, PRECISION), default=0.0)
    unit_cost = fields.Float(
        string="Coût moyen pondéré", digits=(16, PRECISION), default=0.0, readonly=True,
        help="Coût moyen pondéré (CMP) d'une unité de devise, en XOF.",
    )

    _sql_constraints = [
        ('currency_company_uniq', 'unique(currency_id, company_id)',
         "Une seule position peut exister par devise et par société."),
    ]

    @api.model
    def _get_or_create(self, currency, company=None):
        company = company or self.env.company
        position = self.search([
            ('currency_id', '=', currency.id),
            ('company_id', '=', company.id),
        ], limit=1)
        if not position:
            position = self.create({
                'currency_id': currency.id,
                'company_id': company.id,
            })
        return position

    def _register_in(self, qty, value):
        """Entrée en position (achat) : recalcule le CMP de façon pondérée."""
        self.ensure_one()
        if qty <= 0:
            raise UserError(_("La quantité entrante doit être strictement positive."))
        new_quantity = self.quantity + qty
        new_value = self.value_xof + value
        unit_cost = float_round(new_value / new_quantity, precision_digits=PRECISION) if new_quantity else 0.0
        self.write({
            'quantity': new_quantity,
            'value_xof': new_value,
            'unit_cost': unit_cost,
        })

    def _register_out(self, qty):
        """Sortie de position (vente) au CMP courant. Renvoie le coût cédé."""
        self.ensure_one()
        if qty <= 0:
            raise UserError(_("La quantité sortante doit être strictement positive."))
        if float_compare(self.quantity, qty, precision_digits=PRECISION) < 0:
            raise UserError(_(
                "Position insuffisante en %(currency)s : disponible %(available)s, "
                "demandé %(requested)s.",
                currency=self.currency_id.name,
                available=self.quantity, requested=qty,
            ))
        cost = float_round(qty * self.unit_cost, precision_digits=PRECISION)
        self.write({
            'quantity': self.quantity - qty,
            'value_xof': self.value_xof - cost,
        })
        return cost
