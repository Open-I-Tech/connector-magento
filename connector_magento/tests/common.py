# Copyright 2013-2019 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html)

# pylint: disable=missing-manifest-dependency
# disable warning on 'vcr' missing in manifest: this is only a dependency for
# dev/tests

"""
Helpers usable in the tests
"""

import xmlrpc.client
import logging
import urllib

import odoo

from os.path import dirname, join
from contextlib import contextmanager
from unittest import mock
from psycopg2.extensions import AsIs
from odoo import models
try:
    from odoo.addons.component.tests.common import SavepointComponentCase
except ImportError:
    from odoo.addons.component.tests.common import (
        TransactionComponentCase as SavepointComponentCase,
    )
from odoo.tools import mute_logger

from vcr import VCR
from odoo.addons.connector_magento.components import backend_adapter
from odoo.addons.connector_magento.models import magento_backend

logging.getLogger("vcr").setLevel(logging.WARNING)

recorder = VCR(
    record_mode='once',
    cassette_library_dir=join(dirname(__file__), 'fixtures/cassettes'),
    path_transformer=VCR.ensure_suffix('.yaml'),
    filter_headers=['Authorization'],
)


class StubMagentoAPI(object):
    """Small Magento API test double for metadata synchronization."""

    _magento1_records = {
        'ol_websites': {
            '0': {
                'website_id': '0',
                'code': 'admin',
                'name': 'Admin',
                'sort_order': '0',
                'default_group_id': '0',
            },
            '1': {
                'website_id': '1',
                'code': 'base',
                'name': 'Main Website',
                'sort_order': '0',
                'default_group_id': '1',
            },
        },
        'ol_groups': {
            '0': {
                'group_id': '0',
                'website_id': '0',
                'name': 'Default',
                'root_category_id': '0',
                'default_store_id': '0',
            },
            '1': {
                'group_id': '1',
                'website_id': '1',
                'name': 'Madison Island',
                'root_category_id': '2',
                'default_store_id': '1',
            },
        },
        'ol_storeviews': {
            '0': {
                'store_id': '0',
                'code': 'admin',
                'website_id': '0',
                'group_id': '0',
                'name': 'Admin',
                'sort_order': '0',
                'is_active': '1',
            },
            '1': {
                'store_id': '1',
                'code': 'default',
                'website_id': '1',
                'group_id': '1',
                'name': 'English',
                'sort_order': '0',
                'is_active': '1',
            },
            '2': {
                'store_id': '2',
                'code': 'french',
                'website_id': '1',
                'group_id': '1',
                'name': 'French',
                'sort_order': '0',
                'is_active': '1',
            },
            '3': {
                'store_id': '3',
                'code': 'german',
                'website_id': '1',
                'group_id': '1',
                'name': 'German',
                'sort_order': '0',
                'is_active': '1',
            },
        },
    }

    _magento2_websites = [
        {'id': 1, 'code': 'base', 'name': 'Main Website',
         'default_group_id': 1},
        {'id': 0, 'code': 'admin', 'name': 'Admin',
         'default_group_id': 0},
    ]
    _magento2_groups = [
        {'id': 0, 'website_id': 0, 'root_category_id': 0,
         'default_store_id': 0, 'name': 'Default', 'code': 'default'},
        {'id': 1, 'website_id': 1, 'root_category_id': 2,
         'default_store_id': 1, 'name': 'Main Website Store',
         'code': 'main_website_store'},
    ]
    _magento2_storeviews = [
        {'id': 1, 'code': 'default', 'name': 'Default Store View',
         'website_id': 1, 'store_group_id': 1, 'is_active': 1},
        {'id': 0, 'code': 'admin', 'name': 'Admin', 'website_id': 0,
         'store_group_id': 0, 'is_active': 1},
    ]
    _magento2_storeconfigs = [
        {'id': 1, 'code': 'default', 'website_id': 1, 'locale': 'en_US',
         'base_media_url': 'http://magento/media/'},
    ]

    def __init__(self, location):
        self.location = location

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def call(self, method, arguments=None, http_method=None, storeview=None):
        if self.location.version == '1.7':
            return self._call_magento1(method, arguments)
        return self._call_magento2(method, arguments)

    def _call_magento1(self, method, arguments=None):
        model, operation = method.rsplit('.', 1)
        records = self._magento1_records[model]
        if operation == 'search':
            return list(records)
        if operation == 'info':
            return records[str(arguments[0])]
        raise NotImplementedError(method)

    def _filter_fields(self, records, arguments):
        if arguments and arguments.get('fields') == 'id':
            return [{'id': record['id']} for record in records]
        return records

    def _call_magento2(self, method, arguments=None):
        if method == 'store/websites':
            return self._filter_fields(self._magento2_websites, arguments)
        if method == 'store/storeGroups':
            return self._filter_fields(self._magento2_groups, arguments)
        if method == 'store/storeViews':
            return self._magento2_storeviews
        if method == 'store/storeConfigs':
            return self._filter_fields(self._magento2_storeconfigs, arguments)
        raise NotImplementedError(method)


class MockResponseImage(object):

    def __init__(self, resp_data, code=200, msg='OK'):
        self.resp_data = resp_data
        self.content = resp_data
        self.status_code = code
        self.msg = msg
        self.headers = {'content-type': 'image/jpeg'}

    def raise_for_status(self):
        if self.status_code != 200:
            raise urllib.error.HTTPError(
                '', self.status_code, str(self.status_code), None, None)

    def read(self):
        # pylint: disable=method-required-super
        return self.resp_data

    def getcode(self):
        return self.code


@contextmanager
def mock_urlopen_image():
    with mock.patch('requests.get') as requests_get:
        requests_get.return_value = MockResponseImage('')
        yield


class MagentoHelper(object):

    def __init__(self, cr, registry, model_name):
        self.cr = cr
        self.model = registry(model_name)

    def get_next_id(self):
        self.cr.execute("SELECT max(external_id::int) FROM %s ",
                        (AsIs(self.model._table),))
        result = self.cr.fetchone()
        if result:
            return int(result[0] or 0) + 1
        else:
            return 1


class MagentoTestCase(SavepointComponentCase):
    """ Base class - Test the imports from a Magento Mock.

    The data returned by Magento are those created for the
    demo version of Magento on a standard 1.9 version.
    """

    @classmethod
    def setUpClass(cls):
        super(MagentoTestCase, cls).setUpClass()
        cls.recorder = recorder
        # disable commits when run from pytest/nosetest
        odoo.tools.config['test_enable'] = True

        cls.backend_model = cls.env['magento.backend']
        warehouse = cls.env.ref('stock.warehouse0')
        cls.backend = cls.backend_model.create(
            {'name': 'Test Magento',
             'version': '1.7',
             'location': 'http://magento',
             'username': 'odoo',
             'warehouse_id': warehouse.id,
             'password': 'odoo42'}
        )
        # payment method needed to import a sale order
        cls.workflow = cls.env.ref(
            'sale_automatic_workflow.manual_validation')
        cls.journal = cls.env['account.journal'].create(
            {'name': 'Check', 'type': 'cash', 'code': 'Check'}
        )
        payment_method = cls.env.ref(
            'account.account_payment_method_manual_in'
        )
        for name in ['checkmo', 'ccsave', 'cashondelivery']:
            cls.env['account.payment.mode'].create(
                {'name': name,
                 'workflow_process_id': cls.workflow.id,
                 'import_rule': 'always',
                 'days_before_cancel': 0,
                 'bank_account_link': 'fixed',
                 'payment_method_id': payment_method.id,
                 'fixed_journal_id': cls.journal.id})

    def get_magento_helper(self, model_name):
        return MagentoHelper(self.cr, self.registry, model_name)

    @classmethod
    def create_binding_no_export(cls, model_name, odoo_id, external_id=None,
                                 **cols):
        if isinstance(odoo_id, models.BaseModel):
            odoo_id = odoo_id.id
        values = {
            'backend_id': cls.backend.id,
            'odoo_id': odoo_id,
            'external_id': external_id,
        }
        if cols:
            values.update(cols)
        return cls.env[model_name].with_context(
            connector_no_export=True
        ).create(values)

    @contextmanager
    def mock_with_delay(self):
        with mock.patch('odoo.addons.queue_job.models.base.DelayableRecordset',
                        name='DelayableRecordset', spec=True
                        ) as delayable_cls:
            # prepare the mocks
            delayable = mock.MagicMock(name='DelayableBinding')
            delayable_cls.return_value = delayable
            yield delayable_cls, delayable

    def parse_cassette_request(self, body):
        args, __ = xmlrpc.client.loads(body)
        # the first argument is a hash, we don't mind
        return args[1:]

    @classmethod
    def _import_record(cls, model_name, magento_id, cassette=True):
        assert model_name.startswith('magento.')
        table_name = model_name.replace('.', '_')
        # strip 'magento_' from the model_name to shorted the filename
        filename = 'import_%s_%s' % (table_name[8:], str(magento_id))

        def run_import():
            with mute_logger(
                    'odoo.addons.mail.models.mail_mail',
                    'odoo.models.unlink',
                    'odoo.tests'):
                if cls.backend.version != '1.7':
                    return cls.env[model_name].import_record(
                        cls.backend, magento_id)
                with mock_urlopen_image():
                    cls.env[model_name].import_record(
                        cls.backend, magento_id)

        if cassette:
            with cls.recorder.use_cassette(filename):
                run_import()
        else:
            run_import()

        binding = cls.env[model_name].search(
            [('backend_id', '=', cls.backend.id),
             ('external_id', '=', str(magento_id))]
        )
        assert len(binding) == 1, "Binding not found after import"
        return binding

    def assert_records(self, expected_records, records):
        """ Assert that a recordset matches with expected values.

        The expected records are a list of nametuple, the fields of the
        namedtuple must have the same name than the recordset's fields.

        The expected values are compared to the recordset and records that
        differ from the expected ones are show as ``-`` (missing) or ``+``
        (extra) lines.

        Example::

            ExpectedShop = namedtuple('ExpectedShop',
                                      'name company_id')
            expected = [
                ExpectedShop(
                    name='MyShop1',
                    company_id=self.company_ch
                ),
                ExpectedShop(
                    name='MyShop2',
                    company_id=self.company_ch
                ),
            ]
            self.assert_records(expected, shops)

        Possible output:

         - foo.shop(name: MyShop1, company_id: res.company(2,))
         - foo.shop(name: MyShop2, company_id: res.company(1,))
         + foo.shop(name: MyShop3, company_id: res.company(1,))

        :param expected_records: list of namedtuple with matching values
                                 for the records
        :param records: the recordset to check
        :raises: AssertionError if the values do not match
        """
        model_name = records._name
        records = list(records)
        assert len(expected_records) > 0, "must have > 0 expected record"
        fields = expected_records[0]._fields
        not_found = []
        equals = []
        for expected in expected_records:
            for record in records:
                for field, value in list(expected._asdict().items()):
                    if not getattr(record, field) == value:
                        break
                else:
                    records.remove(record)
                    equals.append(record)
                    break
            else:
                not_found.append(expected)
        message = []
        for record in equals:
            # same records
            message.append(
                ' ✓ {}({})'.format(
                    model_name,
                    ', '.join('%s: %s' % (field, getattr(record, field)) for
                              field in fields)
                )
            )
        for expected in not_found:
            # missing records
            message.append(
                ' - {}({})'.format(
                    model_name,
                    ', '.join('%s: %s' % (k, v) for
                              k, v in list(expected._asdict().items()))
                )
            )
        for record in records:
            # extra records
            message.append(
                ' + {}({})'.format(
                    model_name,
                    ', '.join('%s: %s' % (field, getattr(record, field)) for
                              field in fields)
                )
            )
        if not_found or records:
            raise AssertionError('Records do not match:\n\n{}'.format(
                '\n'.join(message)
            ))


class MagentoSyncTestCase(MagentoTestCase):

    @classmethod
    def setUpClass(cls):
        super(MagentoSyncTestCase, cls).setUpClass()
        # Mute logging of notifications about new checkpoints
        with mute_logger(
                'odoo.addons.mail.models.mail_mail',
                'odoo.models.unlink',
                'odoo.tests'):
            with mock.patch.object(backend_adapter, 'MagentoAPI',
                                   StubMagentoAPI):
                with mock.patch.object(magento_backend.common, 'MagentoAPI',
                                       StubMagentoAPI):
                    cls.backend.synchronize_metadata()
