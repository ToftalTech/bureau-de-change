from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestFxDeal(TransactionCase):
    """Bout en bout : le CMP et la marge doivent se retrouver sur fx.deal et la facture."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.currency_eur = cls.env.ref('base.EUR')
        cls.currency_eur.active = True
        cls.partner = cls.env['res.partner'].create({'name': "Client Test"})

        cls.position_account = cls.env['account.account'].create({
            'code': 'FX1EUR',
            'name': "Position EUR",
            'account_type': 'asset_current',
        })
        cls.margin_account = cls.env['account.account'].create({
            'code': 'FX7MARGE',
            'name': "Marge de change",
            'account_type': 'income',
        })
        cls.sale_journal = cls.env['account.journal'].create({
            'name': "Ventes de devises",
            'code': 'FXV',
            'type': 'sale',
        })
        cls.purchase_journal = cls.env['account.journal'].create({
            'name': "Achats de devises",
            'code': 'FXA',
            'type': 'purchase',
        })
        cls.env.company.write({
            'fx_sale_journal_id': cls.sale_journal.id,
            'fx_purchase_journal_id': cls.purchase_journal.id,
            'fx_margin_account_id': cls.margin_account.id,
            'fx_currency_account_ids': [(0, 0, {
                'currency_id': cls.currency_eur.id,
                'account_id': cls.position_account.id,
            })],
        })

    def _make_deal(self, direction, quantity, rate):
        return self.env['fx.deal'].create({
            'direction': direction,
            'partner_id': self.partner.id,
            'currency_id': self.currency_eur.id,
            'quantity': quantity,
            'rate': rate,
            'payment_mode': 'cash',
        })

    def test_deal_flow_weighted_average_cost_and_margin(self):
        deal1 = self._make_deal('buy', 1000, 655)
        deal1.action_post()
        self.assertEqual(deal1.state, 'posted')
        self.assertEqual(deal1.margin_xof, 0.0)
        self.assertEqual(deal1.move_id.move_type, 'in_invoice')

        deal2 = self._make_deal('buy', 1000, 660)
        deal2.action_post()

        position = self.env['fx.position']._get_or_create(self.currency_eur, self.env.company)
        self.assertEqual(position.unit_cost, 657.5)

        deal3 = self._make_deal('sell', 1500, 665)
        deal3.action_post()

        expected_cost = 1500 * 657.5  # 986 250
        expected_margin = 1500 * 665 - expected_cost  # 11 250
        self.assertEqual(deal3.cost_xof, expected_cost)
        self.assertEqual(deal3.margin_xof, expected_margin)
        self.assertEqual(deal3.state, 'posted')
        self.assertEqual(deal3.move_id.move_type, 'out_invoice')
        self.assertEqual(deal3.move_id.state, 'posted')

        # La facture est équilibrée et porte bien coût + marge sur des comptes distincts.
        lines = deal3.move_id.invoice_line_ids
        cost_line = lines.filtered(lambda l: l.account_id == self.position_account)
        margin_line = lines.filtered(lambda l: l.account_id == self.margin_account)
        self.assertEqual(cost_line.price_subtotal, expected_cost)
        self.assertEqual(margin_line.price_subtotal, expected_margin)

    def test_deal_requires_partner(self):
        # partner_id est required=True : la création sans tiers doit être bloquée
        # nativement, avant même d'atteindre action_post().
        with self.assertRaises(UserError):
            self.env['fx.deal'].create({
                'direction': 'buy',
                'currency_id': self.currency_eur.id,
                'quantity': 100,
                'rate': 655,
            })

    def test_posted_deal_cannot_be_modified_cancelled_or_deleted(self):
        deal = self._make_deal('buy', 100, 655)
        deal.action_post()

        with self.assertRaises(UserError):
            deal.write({'quantity': 200})
        with self.assertRaises(UserError):
            deal.action_cancel()
        with self.assertRaises(UserError):
            deal.unlink()

    def test_sell_without_enough_position_raises(self):
        deal = self._make_deal('sell', 100, 665)
        with self.assertRaises(UserError):
            deal.action_post()
