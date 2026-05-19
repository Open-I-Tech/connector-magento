# Copyright 2026 Avosdim
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html)

from .common import MagentoSyncTestCase


class TestSaleStockMinimal(MagentoSyncTestCase):
    """Minimal Odoo 18 checks for sale and picking bindings."""

    @classmethod
    def setUpClass(cls):
        super(TestSaleStockMinimal, cls).setUpClass()
        cls.storeview = cls.env['magento.storeview'].search([
            ('backend_id', '=', cls.backend.id),
            ('external_id', '=', '1'),
        ], limit=1)
        assert cls.storeview, "Magento storeview metadata was not created"

    def test_sale_order_mapper_uses_storeview_binding(self):
        with self.backend.work_on('magento.sale.order') as work:
            mapper = work.component(usage='import.mapper')

        values = mapper.storeview_id({'store_id': '1'})

        self.assertEqual(values['storeview_id'], self.storeview.id)

    def test_sale_line_mapper_does_not_write_product_qty(self):
        with self.backend.work_on('magento.sale.order.line') as work:
            mapper = work.component(usage='import.mapper')

        self.assertIn(('qty_ordered', 'product_uom_qty'), mapper.direct)
        self.assertNotIn(('qty_ordered', 'product_qty'), mapper.direct)

    def test_picking_export_lines_from_sale_order_binding(self):
        order_binding = self._create_confirmed_order_binding()
        picking = order_binding.odoo_id.picking_ids[:1]
        self.assertTrue(picking)

        picking_binding = self.env['magento.stock.picking'].create({
            'backend_id': self.backend.id,
            'odoo_id': picking.id,
            'magento_order_id': order_binding.id,
            'picking_method': 'partial',
        })

        with self.backend.work_on('magento.stock.picking') as work:
            exporter = work.component(usage='record.exporter')

        self.assertEqual(
            exporter._get_lines_info(picking_binding),
            {'1234': 2.0},
        )

    def _create_confirmed_order_binding(self):
        partner = self.env['res.partner'].create({
            'name': 'Magento Stock Customer',
        })
        product = self.env['product.product'].create({
            'name': 'Magento Stock Test Product',
            'type': 'consu',
            'invoice_policy': 'order',
            'list_price': 10.0,
        })
        order = self.env['sale.order'].create({
            'partner_id': partner.id,
            'payment_mode_id': self.env['account.payment.mode'].search(
                [('name', '=', 'checkmo')],
                limit=1,
            ).id,
            'order_line': [(0, 0, {
                'product_id': product.id,
                'product_uom_qty': 2.0,
                'price_unit': 10.0,
            })],
        })
        order_binding = self.env['magento.sale.order'].create({
            'backend_id': self.backend.id,
            'odoo_id': order.id,
            'external_id': '200000001',
            'magento_order_id': 200000001,
            'storeview_id': self.storeview.id,
        })
        order_binding.ignore_exception = True
        self.env['magento.sale.order.line'].create({
            'magento_order_id': order_binding.id,
            'odoo_id': order.order_line.id,
            'external_id': '1234',
        })
        order.action_confirm()
        return order_binding
