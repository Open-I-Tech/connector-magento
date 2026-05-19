# Copyright 2013-2019 Camptocamp SA
# Copyright 2020 Opener B.V.
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html)

from unittest import mock

from odoo.addons.connector_magento.models.account_invoice.exporter import (
    MagentoInvoiceExporter,
)

from .common import Magento2SyncTestCase


class TestExportInvoice(Magento2SyncTestCase):
    """ Test the export of an invoice to Magento """

    @classmethod
    def setUpClass(cls):
        super(TestExportInvoice, cls).setUpClass()
        cls.sale_binding_model = cls.env['magento.sale.order']
        cls.payment_mode = cls.env['account.payment.mode'].search(
            [('name', '=', 'checkmo')],
            limit=1,
        )
        cls.order_binding = cls._create_order_binding()
        cls.stores = cls.backend.mapped('website_ids.store_ids')
        cls.order_binding.odoo_id.action_confirm()
        cls.invoice = cls.order_binding.odoo_id._create_invoices()
        assert cls.invoice
        cls.invoice_model = cls.env['account.move']

    @classmethod
    def _create_order_binding(cls):
        partner = cls.env['res.partner'].create({'name': 'Magento 2 Customer'})
        product = cls.env['product.product'].create({
            'name': 'Magento 2 Invoice Test Product',
            'invoice_policy': 'order',
            'list_price': 10.0,
        })
        order = cls.env['sale.order'].create({
            'partner_id': partner.id,
            'payment_mode_id': cls.payment_mode.id,
            'order_line': [(0, 0, {
                'product_id': product.id,
                'product_uom_qty': 1.0,
                'price_unit': 10.0,
            })],
        })
        storeview = cls.env['magento.storeview'].search([
            ('backend_id', '=', cls.backend.id),
            ('external_id', '=', '1'),
        ], limit=1)
        order_binding = cls.env['magento.sale.order'].create({
            'backend_id': cls.backend.id,
            'odoo_id': order.id,
            'external_id': '16',
            'magento_order_id': 16,
            'storeview_id': storeview.id,
        })
        order_binding.ignore_exception = True
        cls.env['magento.sale.order.line'].create({
            'magento_order_id': order_binding.id,
            'odoo_id': order.order_line.id,
            'external_id': '32',
        })
        return order_binding

    def test_export_invoice_on_validate_trigger(self):
        """ Trigger export of an invoice: when it is validated """
        # we setup the stores so they export the invoices as soon
        # as they are validated (open)
        self.stores.write({'create_invoice_on': 'open'})
        # prevent to create the job
        with self.mock_with_delay() as (delayable_cls, delayable):
            self._invoice_open()
            self.assertEqual(self.invoice.state, 'posted')

            self.assertEqual(len(self.invoice.magento_bind_ids), 1)

            self.assertEqual(1, delayable_cls.call_count)
            delay_args, delay_kwargs = delayable_cls.call_args
            self.assertEqual((self.invoice.magento_bind_ids,), delay_args)

            delayable.export_record.assert_called_with()

        # pay and verify it is NOT called
        with self.mock_with_delay() as (delayable_cls, delayable):
            self._pay_and_reconcile()
            self.assertEqual(self.invoice.payment_state, 'paid')
            self.assertEqual(0, delayable_cls.call_count)

    def test_export_invoice_on_paid_trigger(self):
        """ Trigger export of an invoice: when it is paid """
        # we setup the stores so they export the invoices as soon
        # as they are validated (open)
        self.stores.write({'create_invoice_on': 'paid'})
        # prevent to create the job
        with self.mock_with_delay() as (delayable_cls, delayable):
            self._invoice_open()
            self.assertEqual(self.invoice.state, 'posted')

            self.assertEqual(0, delayable_cls.call_count)

        # pay and verify it is NOT called
        with self.mock_with_delay() as (delayable_cls, delayable):
            self._pay_and_reconcile()

            self.assertEqual(self.invoice.payment_state, 'paid')
            self.assertEqual(len(self.invoice.magento_bind_ids), 1)

            self.assertEqual(1, delayable_cls.call_count)

            delay_args, delay_kwargs = delayable_cls.call_args
            self.assertEqual((self.invoice.magento_bind_ids,), delay_args)

            delayable.export_record.assert_called_with()

    def test_export_invoice_on_payment_mode_validate_trigger(self):
        """ Exporting an invoice: when it is validated with payment mode """
        # we setup the stores so they export the invoices as soon
        # as they are validated (open)
        self.payment_mode.write({'create_invoice_on': 'open'})
        # ensure we use the option of the payment method, not store
        self.stores.write({'create_invoice_on': 'paid'})
        with self.mock_with_delay() as (delayable_cls, delayable):
            self._invoice_open()
            self.assertEqual(self.invoice.state, 'posted')

            self.assertEqual(len(self.invoice.magento_bind_ids), 1)

            self.assertEqual(1, delayable_cls.call_count)
            delay_args, delay_kwargs = delayable_cls.call_args
            self.assertEqual((self.invoice.magento_bind_ids,), delay_args)

            delayable.export_record.assert_called_with()

        # pay and verify it is NOT called
        with self.mock_with_delay() as (delayable_cls, delayable):
            self._pay_and_reconcile()
            self.assertEqual(self.invoice.payment_state, 'paid')
            self.assertEqual(0, delayable_cls.call_count)

    def test_export_invoice_on_payment_mode_paid_trigger(self):
        """ Exporting an invoice: when it is paid on payment method """
        # we setup the stores so they export the invoices as soon
        # as they are validated (open)
        self.payment_mode.write({'create_invoice_on': 'paid'})
        # ensure we use the option of the payment method, not store
        self.stores.write({'create_invoice_on': 'open'})
        with self.mock_with_delay() as (delayable_cls, delayable):
            self._invoice_open()
            self.assertEqual(self.invoice.state, 'posted')
            self.assertEqual(0, delayable_cls.call_count)

        # pay and verify it is NOT called
        with self.mock_with_delay() as (delayable_cls, delayable):
            self._pay_and_reconcile()
            self.assertEqual(self.invoice.payment_state, 'paid')

            self.assertEqual(len(self.invoice.magento_bind_ids), 1)

            self.assertEqual(1, delayable_cls.call_count)

            delay_args, delay_kwargs = delayable_cls.call_args
            self.assertEqual((self.invoice.magento_bind_ids,), delay_args)

            delayable.export_record.assert_called_with()

    def _invoice_open(self):
        self.invoice.action_post()

    def _pay_and_reconcile(self):
        payment_register = self.env['account.payment.register'].with_context(
            active_model='account.move',
            active_ids=self.invoice.ids,
        ).create({
            'journal_id': self.journal.id,
            'amount': self.invoice.amount_residual,
        })
        payment_register.action_create_payments()

    def test_export_invoice_job(self):
        """ Exporting an invoice: call towards the Magento API """
        # we setup the payment method so it exports the invoices as soon
        # as they are validated (open)
        self.payment_mode.write({'create_invoice_on': 'open'})
        self.stores.write({'send_invoice_paid_mail': True})

        with self.mock_with_delay():
            self._invoice_open()

        invoice_binding = self.invoice.magento_bind_ids
        self.assertEqual(len(invoice_binding), 1)

        with mock.patch.object(
                MagentoInvoiceExporter, '_get_lines_info',
                return_value={'32': 1.0}) as get_lines_info:
            with mock.patch.object(
                    MagentoInvoiceExporter, '_export_invoice',
                    return_value='4') as export_invoice:
                invoice_binding.export_record()

        get_lines_info.assert_called_once_with(invoice_binding)
        export_invoice.assert_called_once_with(
            '16', {'32': 1.0}, True)
        self.assertEqual(invoice_binding.external_id, '4')
