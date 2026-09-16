from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestFxPosition(TransactionCase):
    """Scénario de l'énoncé : achat 1000 EUR@655, achat 1000 EUR@660, vente 1500 EUR."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.currency_eur = cls.env.ref('base.EUR')
        cls.currency_eur.active = True

    def test_weighted_average_cost(self):
        position = self.env['fx.position']._get_or_create(self.currency_eur, self.env.company)

        # Achat 1 : 1000 EUR à 655 XOF -> valeur 655 000, CMP = 655
        position._register_in(1000, 1000 * 655)
        self.assertEqual(position.quantity, 1000)
        self.assertEqual(position.value_xof, 655000)
        self.assertEqual(position.unit_cost, 655.0)

        # Achat 2 : 1000 EUR à 660 XOF -> valeur 660 000
        # CMP = (655 000 + 660 000) / 2000 = 657.5
        position._register_in(1000, 1000 * 660)
        self.assertEqual(position.quantity, 2000)
        self.assertEqual(position.value_xof, 1315000)
        self.assertEqual(position.unit_cost, 657.5)

        # Vente de 1500 EUR au CMP courant
        cost = position._register_out(1500)
        expected_cost = 1500 * 657.5  # 986 250
        self.assertEqual(cost, expected_cost)
        self.assertEqual(position.quantity, 500)
        self.assertEqual(position.value_xof, 1315000 - expected_cost)
        # Le CMP ne doit pas bouger lors d'une sortie
        self.assertEqual(position.unit_cost, 657.5)

    def test_register_out_insufficient_position_raises(self):
        position = self.env['fx.position']._get_or_create(self.currency_eur, self.env.company)
        position._register_in(100, 100 * 655)
        with self.assertRaises(UserError):
            position._register_out(200)

    def test_register_in_requires_positive_quantity(self):
        position = self.env['fx.position']._get_or_create(self.currency_eur, self.env.company)
        with self.assertRaises(UserError):
            position._register_in(0, 0)
