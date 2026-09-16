from datetime import datetime, time

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

    def action_view_move(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _("Pièce comptable"),
            'res_model': 'account.move',
            'res_id': self.move_id.id,
            'view_mode': 'form',
            'target': 'current',
        }

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
        """Pilote un bon de commande natif (vente ou achat) plutôt que de
        construire l'écriture à la main : le cycle commande -> facture ->
        comptabilisation reste entièrement celui de Vente/Achat. Les appels
        transitant par sudo() ne font que déléguer une action que l'opération
        fx.deal elle-même autorise déjà (le caissier n'obtient pas d'accès
        direct aux bons de commande ou aux factures via ce détour)."""
        self.ensure_one()
        company = self.company_id
        position_account = company._get_fx_position_account(self.currency_id)
        if not position_account:
            raise UserError(_(
                "Aucun compte de position n'est configuré pour la devise %s.",
                self.currency_id.name,
            ))
        currency_account = company.fx_currency_account_ids.filtered(
            lambda l: l.currency_id == self.currency_id
        )
        currency_product = currency_account.sudo()._get_or_create_product()
        date_order = datetime.combine(self.date, time.min)

        if self.direction == 'sell':
            margin_product = company.sudo()._get_or_create_fx_margin_product()
            order = self.env['sale.order'].sudo().create({
                'partner_id': self.partner_id.id,
                'company_id': company.id,
                'currency_id': company.currency_id.id,
                'date_order': date_order,
                'order_line': [
                    Command.create({
                        'product_id': currency_product.id,
                        'product_uom_qty': 1,
                        'product_uom_id': currency_product.uom_id.id,
                        'price_unit': self.cost_xof,
                        'tax_ids': [Command.clear()],
                        'name': _(
                            "Cession de %(qty)s %(cur)s au coût moyen pondéré",
                            qty=self.quantity, cur=self.currency_id.name,
                        ),
                    }),
                    Command.create({
                        'product_id': margin_product.id,
                        'product_uom_qty': 1,
                        'product_uom_id': margin_product.uom_id.id,
                        'price_unit': self.margin_xof,
                        'tax_ids': [Command.clear()],
                        'name': _(
                            "Marge de change sur cession de %(cur)s",
                            cur=self.currency_id.name,
                        ),
                    }),
                ],
            })
            order.action_confirm()
            move = order._create_invoices(final=True)[:1]
            if not move:
                raise UserError(_(
                    "La facture client n'a pas pu être générée depuis le bon "
                    "de commande %s.", order.name,
                ))
            if company.fx_sale_journal_id:
                move.journal_id = company.fx_sale_journal_id.id
        else:
            order = self.env['purchase.order'].sudo().create({
                'partner_id': self.partner_id.id,
                'company_id': company.id,
                'currency_id': company.currency_id.id,
                'date_order': date_order,
                'order_line': [
                    Command.create({
                        'product_id': currency_product.id,
                        'product_qty': 1,
                        'product_uom_id': currency_product.uom_id.id,
                        'price_unit': self.amount_xof,
                        'date_planned': self.date,
                        'tax_ids': [Command.clear()],
                        'name': _(
                            "Acquisition de %(qty)s %(cur)s",
                            qty=self.quantity, cur=self.currency_id.name,
                        ),
                    }),
                ],
            })
            order.button_confirm()
            if order.state != 'purchase':
                # Le paramétrage "double validation" des Achats ne doit pas
                # bloquer une opération de change déjà validée par fx.deal.
                order.button_approve()
            order.action_create_invoice()
            move = order.invoice_ids[:1]
            if not move:
                raise UserError(_(
                    "La facture fournisseur n'a pas pu être générée depuis le "
                    "bon de commande %s.", order.name,
                ))
            if company.fx_purchase_journal_id:
                move.journal_id = company.fx_purchase_journal_id.id

        move.invoice_date = self.date
        move.invoice_origin = self.name
        move.invoice_date_due = self.date_due if self.payment_mode == 'credit' else self.date
        return move

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
