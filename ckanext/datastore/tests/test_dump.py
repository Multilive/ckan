import json
import nose
from nose.tools import assert_equals
from pylons import config
import sqlalchemy.orm as orm
import paste.fixture
from ckan.config.middleware import make_app

import ckan.plugins as p
import ckan.lib.create_test_data as ctd
import ckan.model as model
import ckan.tests as tests

import ckanext.datastore.db as db
from ckanext.datastore.tests.helpers import rebuild_all_dbs


class TestDatastoreDump(tests.WsgiAppCase):
    sysadmin_user = None
    normal_user = None

    @classmethod
    def setup_class(cls):
        if not tests.is_datastore_supported():
            raise nose.SkipTest("Datastore not supported")
        p.load('datastore')
        ctd.CreateTestData.create()
        cls.sysadmin_user = model.User.get('testsysadmin')
        cls.normal_user = model.User.get('annafan')
        resource = model.Package.get('annakarenina').resources[0]
        cls.data = {
            'resource_id': resource.id,
            'aliases': 'books',
            'fields': [{'id': u'b\xfck', 'type': 'text'},
                       {'id': 'author', 'type': 'text'},
                       {'id': 'published'},
                       {'id': u'characters', u'type': u'_text'}],
            'records': [{u'b\xfck': 'annakarenina', 'author': 'tolstoy',
                        'published': '2005-03-01', 'nested': ['b', {'moo': 'moo'}],
                        u'characters': [u'Princess Anna', u'Sergius']},
                        {u'b\xfck': 'warandpeace', 'author': 'tolstoy',
                        'nested': {'a': 'b'}}
                       ]
        }
        postparams = '%s=1' % json.dumps(cls.data)
        auth = {'Authorization': str(cls.sysadmin_user.apikey)}
        res = cls.app.post('/api/action/datastore_create', params=postparams,
                           extra_environ=auth)
        res_dict = json.loads(res.body)
        assert res_dict['success'] is True

        import pylons
        engine = db._get_engine(
                None,
                {'connection_url': pylons.config['ckan.datastore.write_url']}
            )
        cls.Session = orm.scoped_session(orm.sessionmaker(bind=engine))

        cls._original_config = config.copy()
        config['ckan.plugins'] = 'datastore'
        wsgiapp = make_app(config['global_conf'], **config)
        cls.app = paste.fixture.TestApp(wsgiapp)

    @classmethod
    def teardown_class(cls):
        rebuild_all_dbs(cls.Session)
        p.unload('datastore')
        config.clear()
        config.update(cls._original_config)

    def test_dump_basic(self):
        auth = {'Authorization': str(self.normal_user.apikey)}
        res = self.app.get('/datastore/dump/{0}'.format(str(self.data['resource_id'])),
                           extra_environ=auth)
        content = res.body.decode('utf-8')
        expected = u'_id,b\xfck,author,published,characters,nested'
        assert_equals(content[:len(expected)], expected)
        assert 'warandpeace' in content
        assert "[u'Princess Anna', u'Sergius']" in content

        # get with alias instead of id
        res = self.app.get('/datastore/dump/{0}'.format(str(self.data['aliases'])),
                           extra_environ=auth)