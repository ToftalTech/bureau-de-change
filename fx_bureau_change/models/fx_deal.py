from odoo import api, fields, models, Command, _
from odoo.exceptions import UserError, ValidationError
from odoo.tools import float_compare

TRAITED_CURRENCIES = ('EUR', 'USD', 'CHF', 'CAD')


class FxDeal(models.Model):
    _name = 'fx.deal'
    _inherit = ['mail.thread']
    _description = "Opération de change"
    _order = 'date desc, id desc'

    name = fields.Char(
        string="Référence", required=True, copy=False, readonly=True,
        default=lambda self: _("Nouveau"),
    )
    direction = fields.Selection(
        [('buy', "Achat (le bureau achète la devise)"),
         ('sell', "Vente (le bureau vend la devise)")],
        string="Sens", required=True, default='sell', tracking=True,
    )
    partner_id = fields.Many2one(
        'res.partner', string="Client / tiers", required=True, tracking=True,
    )
    date = fields.Date(required=True, default=fields.Date.context_today, tracking=True)
    currency_id = fields.Many2one(
        'res.currency', string="Devise", required=True, tracking=True,
        domain=[('name', 'in', TRAITED_CURRENCIES)],
    )
    quantity = fields.Float(string="Quantité", digits=(16, 4), required=True)
    rate = fields.Float(
        string="Cours appliqué", digits=(16, 4), required=True, tracking=True,
        help="Cours proposé automatiquement à partir de fx.rate, modifiable à la saisie.",
    )
    amount_xof = fields.Float(
        string="Montant (XOF)", compute='_compute_amount_xof', store=True, digits=(16, 2),
    )
    cost_xof = fields.Float(
        string="Coût cédé (XOF)", digits=(16, 2), readonly=True, copy=False,
        help="Coût moyen pondéré de la quantité cédée (renseigné uniquement pour une vente).",
    )
    margin_xof = fields.Float(
        string="Marge (XOF)", digits=(16, 2), readonly=True, copy=False,
    )
    payment_mode = fields.Selection(
        [('cash', "Comptant"), ('credit', "Crédit")],
        string="Règlement", required=True, default='cash',
    )
    date_due = fields.Date(string="Échéance")
    state = fields.Selection(
        [('draft', "Brouillon"), ('posted', "Validé"), ('cancel', "Annulé")],
        string="État", required=True, default='draft', copy=False, tracking=True,
    )
    move_id = fields.Many2one('account.move', string="Pièce comptable", readonly=True, copy=False)
    company_id = fields.Many2one(
        'res.company', required=True, default=lambda self: self.env.company,
    )

    @api.depends('quantity', 'rate')
    def _compute_amount_xof(self):
        for deal in self:
            deal.amount_xof = deal.quantity * deal.rate

    @api.onchange('currency_id', 'direction', 'date')
    def _onchange_fetch_rate(self):
        for deal in self:
            if not (deal.currency_id and deal.direction and deal.date):
                continue
            try:
                deal.rate = self.env['fx.rate'].get_rate(
                    deal.currency_id, deal.date, deal.direction, deal.company_id,
                )
            except UserError:
                # Aucun cours défini : on laisse le caissier saisir manuellement.
                continue

    @api.constrains('quantity')
    def _check_quantity(self):
        for deal in self:
            if deal.quantity <= 0:
                raise ValidationError(_("La quantité doit être strictement positive."))

    @api.constrains('rate')
    def _check_rate(self):
        for deal in self:
            if deal.rate <= 0:
                raise ValidationError(_("Le cours doit être strictement positif."))

    @api.constrains('currency_id', 'company_id')
    def _check_currency_not_company(self):
        for deal in self:
            if deal.currency_id == deal.company_id.currency_id:
                raise ValidationError(_(
                    "La devise de l'opération ne peut pas être la devise de la société."
                ))

    @api.constrains('payment_mode', 'date_due')
    def _check_date_due(self):
        for deal in self:
            if deal.payment_mode == 'credit' and not deal.date_due:
                raise ValidationError(_(
                    "Une date d'échéance est requise pour une opération à crédit."
                ))

    def action_post(self):
        for deal in self:
            if deal.state != 'draft':
                raise UserError(_(
                    "Seule une opération à l'état brouillon peut être validée."
                ))
            if not deal.partner_id:
                raise UserError(_(
                    "Aucune opération de change ne peut être validée sans tiers identifié."
                ))

            position = self.env['fx.position']._get_or_create(deal.currency_id, deal.company_id)
            if deal.direction == 'buy':
                position._register_in(deal.quantity, deal.amount_xof)
                deal.cost_xof = deal.amount_xof
                deal.margin_xof = 0.0
            else:
                cost = position._register_out(deal.quantity)
                deal.cost_xof = cost
                deal.margin_xof = deal.amount_xof - cost

            if float_compare(deal.cost_xof + deal.margin_xof, deal.amount_xof, precision_digits=2) != 0:
                raise UserError(_(
                    "Écart de valorisation détecté : le coût et la marge ne "
                    "correspondent pas au montant total de l'opération."
                ))

            if deal.name == _("Nouveau"):
                deal.name = self.env['ir.sequence'].next_by_code('fx.deal') or _("Nouveau")

            move = deal._create_account_move()
            deal.move_id = move.id
            move.action_post()
            deal.state = 'posted'
        return True

    def action_cancel(self):
        for deal in self:
            if deal.state == 'posted':
                raise UserError(_(
                    "Une opération validée ne peut pas être annulée. Pour corriger "
                    "une erreur, enregistrez une opération inverse."
                ))
            deal.state = 'cancel'
        return True

    def _create_account_move(self):
        self.ensure_one()
        company = self.company_id
        journal = company.fx_journal_id
        if not journal:
            raise UserError(_(
                "Aucun journal des opérations de change n'est configuré pour la "
                "société %s (Comptabilité > Configuration > Bureau de change).",
                company.name,
            ))
        position_account = company._get_fx_position_account(self.currency_id)
        if not position_account:
            raise UserError(_(
                "Aucun compte de position n'est configuré pour la devise %s.",
                self.currency_id.name,
            ))

        if self.direction == 'sell':
            margin_account = company.fx_margin_account_id
            if not margin_account:
                raise UserError(_(
                    "Aucun compte de marge de change n'est configuré pour la "
                    "société %s.",
                    company.name,
                ))
            move_type = 'out_invoice'
            invoice_line_vals = [
                Command.create({
                    'name': _(
                        "Cession de %(qty)s %(cur)s au coût moyen pondéré",
                        qty=self.quantity, cur=self.currency_id.name,
                    ),
                    'account_id': position_account.id,
                    'quantity': 1,
                    'price_unit': self.cost_xof,
                    'tax_ids': [Command.clear()],
                }),
                Command.create({
                    'name': _(
                        "Marge de change sur cession de %(cur)s", cur=self.currency_id.name,
                    ),
                    'account_id': margin_account.id,
                    'quantity': 1,
                    'price_unit': self.margin_xof,
                    'tax_ids': [Command.clear()],
                }),
            ]
        else:
            move_type = 'in_invoice'
            invoice_line_vals = [
                Command.create({
                    'name': _(
                        "Acquisition de %(qty)s %(cur)s", qty=self.quantity, cur=self.currency_id.name,
                    ),
                    'account_id': position_account.id,
                    'quantity': 1,
                    'price_unit': self.amount_xof,
                    'tax_ids': [Command.clear()],
                }),
            ]

        move_vals = {
            'move_type': move_type,
            'journal_id': journal.id,
            'partner_id': self.partner_id.id,
            'currency_id': company.currency_id.id,
            'invoice_date': self.date,
            'invoice_date_due': self.date_due if self.payment_mode == 'credit' else self.date,
            'invoice_origin': self.name,
            'invoice_line_ids': invoice_line_vals,
            'company_id': company.id,
        }
        return self.env['account.move'].create(move_vals)

    def write(self, vals):
        for deal in self:
            if deal.state == 'posted':
                raise UserError(_(
                    "Une opération validée ne peut plus être modifiée. "
                    "Corrigez-la en enregistrant une opération inverse."
                ))
        return super().write(vals)

    def unlink(self):
        for deal in self:
            if deal.state == 'posted':
                raise UserError(_(
                    "Une opération validée ne peut pas être supprimée. "
                    "Corrigez-la en enregistrant une opération inverse."
                ))
        return super().unlink()
