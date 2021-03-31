#!/usr/bin/env python
import os.path

import base64
import json
import requests
import socket
import time
from dnsdisttests import DNSDistTest

class APITestsBase(DNSDistTest):
    __test__ = False
    _webTimeout = 2.0
    _webServerPort = 8083
    _webServerBasicAuthPassword = 'secret'
    _webServerBasicAuthPasswordHashed = '$argon2id$v=19$m=65536,t=2,p=1$mTJBHtI/KyO8oVDy8wyizg$8NK4ap5ohC7ylY8Dua61iBqhQw0cbcmXUaOpotC2hC0'
    _webServerAPIKey = 'apisecret'
    _webServerAPIKeyHashed = '$argon2id$v=19$m=65536,t=2,p=1$gw/ygc0SC6RID13ifimJhQ$nOBy+Tu+JYiQ4hRBhLpTNyaff7rlFPogYUAGGfy5134'
    _config_params = ['_testServerPort', '_webServerPort', '_webServerBasicAuthPasswordHashed', '_webServerAPIKeyHashed']
    _config_template = """
    setACL({"127.0.0.1/32", "::1/128"})
    newServer{address="127.0.0.1:%s", pool={'', 'mypool'}}
    webserver("127.0.0.1:%s")
    setWebserverConfig({password="%s", apiKey="%s"})
    """

class TestAPIBasics(APITestsBase):

    # paths accessible using the API key only
    _apiOnlyPaths = ['/api/v1/servers/localhost/config', '/api/v1/servers/localhost/config/allow-from', '/api/v1/servers/localhost/statistics']
    # paths accessible using an API key or basic auth
    _statsPaths = [ '/jsonstat?command=stats', '/jsonstat?command=dynblocklist', '/api/v1/servers/localhost']
    # paths accessible using basic auth only (list not exhaustive)
    _basicOnlyPaths = ['/', '/index.html']
    __test__ = True

    def testBasicAuth(self):
        """
        API: Basic Authentication
        """
        for path in self._basicOnlyPaths + self._statsPaths:
            url = 'http://127.0.0.1:' + str(self._webServerPort) + path
            r = requests.get(url, auth=('whatever', "evilsecret"), timeout=self._webTimeout)
            self.assertEqual(r.status_code, 401)
            r = requests.get(url, auth=('whatever', self._webServerBasicAuthPassword), timeout=self._webTimeout)
            self.assertTrue(r)
            self.assertEqual(r.status_code, 200)

    def testXAPIKey(self):
        """
        API: X-Api-Key
        """
        headers = {'x-api-key': self._webServerAPIKey}
        for path in self._apiOnlyPaths + self._statsPaths:
            url = 'http://127.0.0.1:' + str(self._webServerPort) + path
            r = requests.get(url, headers=headers, timeout=self._webTimeout)
            self.assertTrue(r)
            self.assertEqual(r.status_code, 200)

    def testWrongXAPIKey(self):
        """
        API: Wrong X-Api-Key
        """
        headers = {'x-api-key': "evilapikey"}
        for path in self._apiOnlyPaths + self._statsPaths:
            url = 'http://127.0.0.1:' + str(self._webServerPort) + path
            r = requests.get(url, headers=headers, timeout=self._webTimeout)
            self.assertEqual(r.status_code, 401)

    def testBasicAuthOnly(self):
        """
        API: Basic Authentication Only
        """
        headers = {'x-api-key': self._webServerAPIKey}
        for path in self._basicOnlyPaths:
            url = 'http://127.0.0.1:' + str(self._webServerPort) + path
            r = requests.get(url, headers=headers, timeout=self._webTimeout)
            self.assertEqual(r.status_code, 401)

    def testAPIKeyOnly(self):
        """
        API: API Key Only
        """
        for path in self._apiOnlyPaths:
            url = 'http://127.0.0.1:' + str(self._webServerPort) + path
            r = requests.get(url, auth=('whatever', self._webServerBasicAuthPassword), timeout=self._webTimeout)
            self.assertEqual(r.status_code, 401)

    def testServersLocalhost(self):
        """
        API: /api/v1/servers/localhost
        """
        headers = {'x-api-key': self._webServerAPIKey}
        url = 'http://127.0.0.1:' + str(self._webServerPort) + '/api/v1/servers/localhost'
        r = requests.get(url, headers=headers, timeout=self._webTimeout)
        self.assertTrue(r)
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json())
        content = r.json()

        self.assertEqual(content['daemon_type'], 'dnsdist')

        rule_groups = ['response-rules', 'cache-hit-response-rules', 'self-answered-response-rules', 'rules']
        for key in ['version', 'acl', 'local', 'servers', 'frontends', 'pools'] + rule_groups:
            self.assertIn(key, content)

        for rule_group in rule_groups:
            for rule in content[rule_group]:
                for key in ['id', 'creationOrder', 'matches', 'rule', 'action', 'uuid']:
                    self.assertIn(key, rule)
                for key in ['id', 'creationOrder', 'matches']:
                    self.assertTrue(rule[key] >= 0)

        for server in content['servers']:
            for key in ['id', 'latency', 'name', 'weight', 'outstanding', 'qpsLimit',
                        'reuseds', 'state', 'address', 'pools', 'qps', 'queries', 'order', 'sendErrors',
                        'dropRate', 'responses', 'tcpDiedSendingQuery', 'tcpDiedReadingResponse',
                        'tcpGaveUp', 'tcpReadTimeouts', 'tcpWriteTimeouts', 'tcpCurrentConnections',
                        'tcpNewConnections', 'tcpReusedConnections', 'tlsResumptions', 'tcpAvgQueriesPerConnection',
                        'tcpAvgConnectionDuration']:
                self.assertIn(key, server)

            for key in ['id', 'latency', 'weight', 'outstanding', 'qpsLimit', 'reuseds',
                        'qps', 'queries', 'order']:
                self.assertTrue(server[key] >= 0)

            self.assertTrue(server['state'] in ['up', 'down', 'UP', 'DOWN'])

        for frontend in content['frontends']:
            for key in ['id', 'address', 'udp', 'tcp', 'type', 'queries']:
                self.assertIn(key, frontend)

            for key in ['id', 'queries']:
                self.assertTrue(frontend[key] >= 0)

        for pool in content['pools']:
            for key in ['id', 'name', 'cacheSize', 'cacheEntries', 'cacheHits', 'cacheMisses', 'cacheDeferredInserts', 'cacheDeferredLookups', 'cacheLookupCollisions', 'cacheInsertCollisions', 'cacheTTLTooShorts']:
                self.assertIn(key, pool)

            for key in ['id', 'cacheSize', 'cacheEntries', 'cacheHits', 'cacheMisses', 'cacheDeferredInserts', 'cacheDeferredLookups', 'cacheLookupCollisions', 'cacheInsertCollisions', 'cacheTTLTooShorts']:
                self.assertTrue(pool[key] >= 0)

    def testServersLocalhostPool(self):
        """
        API: /api/v1/servers/localhost/pool?name=mypool
        """
        headers = {'x-api-key': self._webServerAPIKey}
        url = 'http://127.0.0.1:' + str(self._webServerPort) + '/api/v1/servers/localhost/pool?name=mypool'
        r = requests.get(url, headers=headers, timeout=self._webTimeout)
        self.assertTrue(r)
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json())
        content = r.json()

        self.assertIn('stats', content)
        self.assertIn('servers', content)

        for key in ['name', 'cacheSize', 'cacheEntries', 'cacheHits', 'cacheMisses', 'cacheDeferredInserts', 'cacheDeferredLookups', 'cacheLookupCollisions', 'cacheInsertCollisions', 'cacheTTLTooShorts']:
            self.assertIn(key, content['stats'])

        for key in ['cacheSize', 'cacheEntries', 'cacheHits', 'cacheMisses', 'cacheDeferredInserts', 'cacheDeferredLookups', 'cacheLookupCollisions', 'cacheInsertCollisions', 'cacheTTLTooShorts']:
            self.assertTrue(content['stats'][key] >= 0)

        for server in content['servers']:
            for key in ['id', 'latency', 'name', 'weight', 'outstanding', 'qpsLimit',
                        'reuseds', 'state', 'address', 'pools', 'qps', 'queries', 'order', 'sendErrors',
                        'dropRate', 'responses', 'tcpDiedSendingQuery', 'tcpDiedReadingResponse',
                        'tcpGaveUp', 'tcpReadTimeouts', 'tcpWriteTimeouts', 'tcpCurrentConnections',
                        'tcpNewConnections', 'tcpReusedConnections', 'tcpAvgQueriesPerConnection',
                        'tcpAvgConnectionDuration']:
                self.assertIn(key, server)

            for key in ['id', 'latency', 'weight', 'outstanding', 'qpsLimit', 'reuseds',
                        'qps', 'queries', 'order']:
                self.assertTrue(server[key] >= 0)

            self.assertTrue(server['state'] in ['up', 'down', 'UP', 'DOWN'])

    def testServersIDontExist(self):
        """
        API: /api/v1/servers/idonotexist (should be 404)
        """
        headers = {'x-api-key': self._webServerAPIKey}
        url = 'http://127.0.0.1:' + str(self._webServerPort) + '/api/v1/servers/idonotexist'
        r = requests.get(url, headers=headers, timeout=self._webTimeout)
        self.assertEqual(r.status_code, 404)

    def testServersLocalhostConfig(self):
        """
        API: /api/v1/servers/localhost/config
        """
        headers = {'x-api-key': self._webServerAPIKey}
        url = 'http://127.0.0.1:' + str(self._webServerPort) + '/api/v1/servers/localhost/config'
        r = requests.get(url, headers=headers, timeout=self._webTimeout)
        self.assertTrue(r)
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json())
        content = r.json()
        values = {}
        for entry in content:
            for key in ['type', 'name', 'value']:
                self.assertIn(key, entry)

            self.assertEqual(entry['type'], 'ConfigSetting')
            values[entry['name']] = entry['value']

        for key in ['acl', 'control-socket', 'ecs-override', 'ecs-source-prefix-v4',
                    'ecs-source-prefix-v6', 'fixup-case', 'max-outstanding', 'server-policy',
                    'stale-cache-entries-ttl', 'tcp-recv-timeout', 'tcp-send-timeout',
                    'truncate-tc', 'verbose', 'verbose-health-checks']:
            self.assertIn(key, values)

        for key in ['max-outstanding', 'stale-cache-entries-ttl', 'tcp-recv-timeout',
                    'tcp-send-timeout']:
            self.assertTrue(values[key] >= 0)

        self.assertTrue(values['ecs-source-prefix-v4'] >= 0 and values['ecs-source-prefix-v4'] <= 32)
        self.assertTrue(values['ecs-source-prefix-v6'] >= 0 and values['ecs-source-prefix-v6'] <= 128)

    def testServersLocalhostConfigAllowFrom(self):
        """
        API: /api/v1/servers/localhost/config/allow-from
        """
        headers = {'x-api-key': self._webServerAPIKey}
        url = 'http://127.0.0.1:' + str(self._webServerPort) + '/api/v1/servers/localhost/config/allow-from'
        r = requests.get(url, headers=headers, timeout=self._webTimeout)
        self.assertTrue(r)
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json())
        content = r.json()
        for key in ['type', 'name', 'value']:
            self.assertIn(key, content)

        self.assertEqual(content['name'], 'allow-from')
        self.assertEqual(content['type'], 'ConfigSetting')
        acl = content['value']
        expectedACL = ["127.0.0.1/32", "::1/128"]
        acl.sort()
        expectedACL.sort()
        self.assertEqual(acl, expectedACL)

    def testServersLocalhostConfigAllowFromPut(self):
        """
        API: PUT /api/v1/servers/localhost/config/allow-from (should be refused)

        The API is read-only by default, so this should be refused
        """
        newACL = ["192.0.2.0/24", "198.51.100.0/24", "203.0.113.0/24"]
        payload = json.dumps({"name": "allow-from",
                              "type": "ConfigSetting",
                              "value": newACL})
        headers = {'x-api-key': self._webServerAPIKey}
        url = 'http://127.0.0.1:' + str(self._webServerPort) + '/api/v1/servers/localhost/config/allow-from'
        r = requests.put(url, headers=headers, timeout=self._webTimeout, data=payload)
        self.assertFalse(r)
        self.assertEqual(r.status_code, 405)

    def testServersLocalhostStatistics(self):
        """
        API: /api/v1/servers/localhost/statistics
        """
        headers = {'x-api-key': self._webServerAPIKey}
        url = 'http://127.0.0.1:' + str(self._webServerPort) + '/api/v1/servers/localhost/statistics'
        r = requests.get(url, headers=headers, timeout=self._webTimeout)
        self.assertTrue(r)
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json())
        content = r.json()
        values = {}
        for entry in content:
            self.assertIn('type', entry)
            self.assertIn('name', entry)
            self.assertIn('value', entry)
            self.assertEqual(entry['type'], 'StatisticItem')
            values[entry['name']] = entry['value']

        expected = ['responses', 'servfail-responses', 'queries', 'acl-drops',
                    'frontend-noerror', 'frontend-nxdomain', 'frontend-servfail',
                    'rule-drop', 'rule-nxdomain', 'rule-refused', 'self-answered', 'downstream-timeouts',
                    'downstream-send-errors', 'trunc-failures', 'no-policy', 'latency0-1',
                    'latency1-10', 'latency10-50', 'latency50-100', 'latency100-1000',
                    'latency-slow', 'latency-sum', 'latency-count', 'latency-avg100', 'latency-avg1000',
                    'latency-avg10000', 'latency-avg1000000', 'uptime', 'real-memory-usage', 'noncompliant-queries',
                    'noncompliant-responses', 'rdqueries', 'empty-queries', 'cache-hits',
                    'cache-misses', 'cpu-iowait', 'cpu-steal', 'cpu-sys-msec', 'cpu-user-msec', 'fd-usage', 'dyn-blocked',
                    'dyn-block-nmg-size', 'rule-servfail', 'rule-truncated', 'security-status',
                    'udp-in-errors', 'udp-noport-errors', 'udp-recvbuf-errors', 'udp-sndbuf-errors',
                    'doh-query-pipe-full', 'doh-response-pipe-full', 'proxy-protocol-invalid', 'tcp-listen-overflows',
                    'outgoing-doh-query-pipe-full', 'tcp-query-pipe-full', 'tcp-cross-protocol-query-pipe-full',
                    'tcp-cross-protocol-response-pipe-full']

        for key in expected:
            self.assertIn(key, values)
            self.assertTrue(values[key] >= 0)

        for key in values:
            self.assertIn(key, expected)

    def testJsonstatStats(self):
        """
        API: /jsonstat?command=stats
        """
        headers = {'x-api-key': self._webServerAPIKey}
        url = 'http://127.0.0.1:' + str(self._webServerPort) + '/jsonstat?command=stats'
        r = requests.get(url, headers=headers, timeout=self._webTimeout)
        self.assertTrue(r)
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json())
        content = r.json()

        expected = ['responses', 'servfail-responses', 'queries', 'acl-drops',
                    'frontend-noerror', 'frontend-nxdomain', 'frontend-servfail',
                    'rule-drop', 'rule-nxdomain', 'rule-refused', 'rule-truncated', 'self-answered', 'downstream-timeouts',
                    'downstream-send-errors', 'trunc-failures', 'no-policy', 'latency0-1',
                    'latency1-10', 'latency10-50', 'latency50-100', 'latency100-1000',
                    'latency-slow', 'latency-avg100', 'latency-avg1000', 'latency-avg10000',
                    'latency-avg1000000', 'uptime', 'real-memory-usage', 'noncompliant-queries',
                    'noncompliant-responses', 'rdqueries', 'empty-queries', 'cache-hits',
                    'cache-misses', 'cpu-user-msec', 'cpu-sys-msec', 'fd-usage', 'dyn-blocked',
                    'dyn-block-nmg-size', 'packetcache-hits', 'packetcache-misses', 'over-capacity-drops',
                    'too-old-drops', 'proxy-protocol-invalid', 'doh-query-pipe-full', 'doh-response-pipe-full']

        for key in expected:
            self.assertIn(key, content)
            self.assertTrue(content[key] >= 0)

    def testJsonstatDynblocklist(self):
        """
        API: /jsonstat?command=dynblocklist
        """
        headers = {'x-api-key': self._webServerAPIKey}
        url = 'http://127.0.0.1:' + str(self._webServerPort) + '/jsonstat?command=dynblocklist'
        r = requests.get(url, headers=headers, timeout=self._webTimeout)
        self.assertTrue(r)
        self.assertEqual(r.status_code, 200)

        content = r.json()

        if content:
            for key in ['reason', 'seconds', 'blocks', 'action']:
                self.assertIn(key, content)

            for key in ['blocks']:
                self.assertTrue(content[key] >= 0)

class TestAPIServerDown(APITestsBase):
    __test__ = True
    _config_template = """
    setACL({"127.0.0.1/32", "::1/128"})
    newServer{address="127.0.0.1:%s"}
    getServer(0):setDown()
    webserver("127.0.0.1:%s")
    setWebserverConfig({password="%s", apiKey="%s"})
    """

    def testServerDownNoLatencyLocalhost(self):
        """
        API: /api/v1/servers/localhost, no latency for a down server
        """
        headers = {'x-api-key': self._webServerAPIKey}
        url = 'http://127.0.0.1:' + str(self._webServerPort) + '/api/v1/servers/localhost'
        r = requests.get(url, headers=headers, timeout=self._webTimeout)
        self.assertTrue(r)
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json())
        content = r.json()

        self.assertEqual(content['servers'][0]['latency'], None)

class TestAPIWritable(APITestsBase):
    __test__ = True
    _APIWriteDir = '/tmp'
    _config_params = ['_testServerPort', '_webServerPort', '_webServerBasicAuthPasswordHashed', '_webServerAPIKeyHashed', '_APIWriteDir']
    _config_template = """
    setACL({"127.0.0.1/32", "::1/128"})
    newServer{address="127.0.0.1:%s"}
    webserver("127.0.0.1:%s")
    setWebserverConfig({password="%s", apiKey="%s"})
    setAPIWritable(true, "%s")
    """

    def testSetACL(self):
        """
        API: Set ACL
        """
        headers = {'x-api-key': self._webServerAPIKey}
        url = 'http://127.0.0.1:' + str(self._webServerPort) + '/api/v1/servers/localhost/config/allow-from'
        r = requests.get(url, headers=headers, timeout=self._webTimeout)
        self.assertTrue(r)
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json())
        content = r.json()
        acl = content['value']
        expectedACL = ["127.0.0.1/32", "::1/128"]
        acl.sort()
        expectedACL.sort()
        self.assertEqual(acl, expectedACL)

        newACL = ["192.0.2.0/24", "198.51.100.0/24", "203.0.113.0/24"]
        payload = json.dumps({"name": "allow-from",
                              "type": "ConfigSetting",
                              "value": newACL})
        r = requests.put(url, headers=headers, timeout=self._webTimeout, data=payload)
        self.assertTrue(r)
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json())
        content = r.json()
        acl = content['value']
        acl.sort()
        self.assertEqual(acl, newACL)

        r = requests.get(url, headers=headers, timeout=self._webTimeout)
        self.assertTrue(r)
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json())
        content = r.json()
        acl = content['value']
        acl.sort()
        self.assertEqual(acl, newACL)

        configFile = self._APIWriteDir + '/' + 'acl.conf'
        self.assertTrue(os.path.isfile(configFile))
        fileContent = None
        with open(configFile, 'rt') as f:
            header = f.readline()
            body = f.readline()

        self.assertEqual(header, """-- Generated by the REST API, DO NOT EDIT\n""")

        self.assertIn(body, {
            """setACL({"192.0.2.0/24", "198.51.100.0/24", "203.0.113.0/24"})\n""",
            """setACL({"192.0.2.0/24", "203.0.113.0/24", "198.51.100.0/24"})\n""",
            """setACL({"198.51.100.0/24", "192.0.2.0/24", "203.0.113.0/24"})\n""",
            """setACL({"198.51.100.0/24", "203.0.113.0/24", "192.0.2.0/24"})\n""",
            """setACL({"203.0.113.0/24", "192.0.2.0/24", "198.51.100.0/24"})\n""",
            """setACL({"203.0.113.0/24", "198.51.100.0/24", "192.0.2.0/24"})\n"""
        })

class TestAPICustomHeaders(APITestsBase):
    __test__ = True
    # paths accessible using the API key only
    _apiOnlyPath = '/api/v1/servers/localhost/config'
    # paths accessible using basic auth only (list not exhaustive)
    _basicOnlyPath = '/'
    _consoleKey = DNSDistTest.generateConsoleKey()
    _consoleKeyB64 = base64.b64encode(_consoleKey).decode('ascii')
    _config_params = ['_consoleKeyB64', '_consolePort', '_testServerPort', '_webServerPort', '_webServerBasicAuthPasswordHashed', '_webServerAPIKeyHashed']
    _config_template = """
    setKey("%s")
    controlSocket("127.0.0.1:%s")
    setACL({"127.0.0.1/32", "::1/128"})
    newServer({address="127.0.0.1:%s"})
    webserver("127.0.0.1:%s")
    setWebserverConfig({password="%s", apiKey="%s", customHeaders={["X-Frame-Options"]="", ["X-Custom"]="custom"} })
    """

    def testBasicHeaders(self):
        """
        API: Basic custom headers
        """

        url = 'http://127.0.0.1:' + str(self._webServerPort) + self._basicOnlyPath

        r = requests.get(url, auth=('whatever', self._webServerBasicAuthPassword), timeout=self._webTimeout)
        self.assertTrue(r)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.headers.get('x-custom'), "custom")
        self.assertFalse("x-frame-options" in r.headers)

    def testBasicHeadersUpdate(self):
        """
        API: Basic update of custom headers
        """

        url = 'http://127.0.0.1:' + str(self._webServerPort) + self._basicOnlyPath
        self.sendConsoleCommand('setWebserverConfig({customHeaders={["x-powered-by"]="dnsdist"}})')
        r = requests.get(url, auth=('whatever', self._webServerBasicAuthPassword), timeout=self._webTimeout)
        self.assertTrue(r)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.headers.get('x-powered-by'), "dnsdist")
        self.assertTrue("x-frame-options" in r.headers)

class TestStatsWithoutAuthentication(APITestsBase):
    __test__ = True
    # paths accessible using the API key only
    _apiOnlyPath = '/api/v1/servers/localhost/config'
    # paths accessible using basic auth only (list not exhaustive)
    _basicOnlyPath = '/'
    _noAuthenticationPaths = [ '/metrics', '/jsonstat?command=dynblocklist' ]
    _consoleKey = DNSDistTest.generateConsoleKey()
    _consoleKeyB64 = base64.b64encode(_consoleKey).decode('ascii')
    _config_params = ['_consoleKeyB64', '_consolePort', '_testServerPort', '_webServerPort', '_webServerBasicAuthPasswordHashed', '_webServerAPIKeyHashed']
    _config_template = """
    setKey("%s")
    controlSocket("127.0.0.1:%s")
    setACL({"127.0.0.1/32", "::1/128"})
    newServer({address="127.0.0.1:%s"})
    webserver("127.0.0.1:%s")
    setWebserverConfig({password="%s", apiKey="%s", statsRequireAuthentication=false })
    """

    def testAuth(self):
        """
        API: Stats do not require authentication
        """

        for path in self._noAuthenticationPaths:
            url = 'http://127.0.0.1:' + str(self._webServerPort) + path

            r = requests.get(url, timeout=self._webTimeout)
            self.assertTrue(r)
            self.assertEqual(r.status_code, 200)

        # these should still require basic authentication
        for path in [self._basicOnlyPath]:
            url = 'http://127.0.0.1:' + str(self._webServerPort) + path

            r = requests.get(url, timeout=self._webTimeout)
            self.assertEqual(r.status_code, 401)

            r = requests.get(url, auth=('whatever', self._webServerBasicAuthPassword), timeout=self._webTimeout)
            self.assertTrue(r)
            self.assertEqual(r.status_code, 200)

        # these should still require API authentication
        for path in [self._apiOnlyPath]:
            url = 'http://127.0.0.1:' + str(self._webServerPort) + path

            r = requests.get(url, timeout=self._webTimeout)
            self.assertEqual(r.status_code, 401)

            headers = {'x-api-key': self._webServerAPIKey}
            r = requests.get(url, headers=headers, timeout=self._webTimeout)
            self.assertTrue(r)
            self.assertEqual(r.status_code, 200)

class TestAPIAuth(APITestsBase):
    __test__ = True
    _webServerBasicAuthPasswordNew = 'password'
    _webServerBasicAuthPasswordNewHashed = '$argon2id$v=19$m=65536,t=2,p=1$AYiZGEPogz3849qG//YsjA$ZG39i+yK8Pet8yNU8lJ9ktMbDyF2TuxC32TR74/Mx68'
    _webServerAPIKeyNew = 'apipassword'
    _webServerAPIKeyNewHashed = '$argon2id$v=19$m=65536,t=2,p=1$hNE0zlMnk+9QNKLbQGZjyA$9y0rlN+asmT3p3uyCPTcSeeMGHcwgrrNwbRlDmmLSAA'
    # paths accessible using the API key only
    _apiOnlyPath = '/api/v1/servers/localhost/config'
    # paths accessible using basic auth only (list not exhaustive)
    _basicOnlyPath = '/'
    _consoleKey = DNSDistTest.generateConsoleKey()
    _consoleKeyB64 = base64.b64encode(_consoleKey).decode('ascii')
    _config_params = ['_consoleKeyB64', '_consolePort', '_testServerPort', '_webServerPort', '_webServerBasicAuthPasswordHashed', '_webServerAPIKeyHashed']
    _config_template = """
    setKey("%s")
    controlSocket("127.0.0.1:%s")
    setACL({"127.0.0.1/32", "::1/128"})
    newServer{address="127.0.0.1:%s"}
    webserver("127.0.0.1:%s")
    setWebserverConfig({password="%s", apiKey="%s"})
    """

    def testBasicAuthChange(self):
        """
        API: Basic Authentication updating credentials
        """

        url = 'http://127.0.0.1:' + str(self._webServerPort) + self._basicOnlyPath
        self.sendConsoleCommand('setWebserverConfig({{password="{}"}})'.format(self._webServerBasicAuthPasswordNewHashed))

        r = requests.get(url, auth=('whatever', self._webServerBasicAuthPasswordNew), timeout=self._webTimeout)
        self.assertTrue(r)
        self.assertEqual(r.status_code, 200)

        # Make sure the old password is not usable any more
        r = requests.get(url, auth=('whatever', self._webServerBasicAuthPassword), timeout=self._webTimeout)
        self.assertEqual(r.status_code, 401)

    def testXAPIKeyChange(self):
        """
        API: X-Api-Key updating credentials
        """

        url = 'http://127.0.0.1:' + str(self._webServerPort) + self._apiOnlyPath
        self.sendConsoleCommand('setWebserverConfig({{apiKey="{}"}})'.format(self._webServerAPIKeyNewHashed))

        headers = {'x-api-key': self._webServerAPIKeyNew}
        r = requests.get(url, headers=headers, timeout=self._webTimeout)
        self.assertTrue(r)
        self.assertEqual(r.status_code, 200)

        # Make sure the old password is not usable any more
        headers = {'x-api-key': self._webServerAPIKey}
        r = requests.get(url, headers=headers, timeout=self._webTimeout)
        self.assertEqual(r.status_code, 401)

    def testBasicAuthOnlyChange(self):
        """
        API: X-Api-Key updated to none (disabled)
        """

        url = 'http://127.0.0.1:' + str(self._webServerPort) + self._apiOnlyPath
        self.sendConsoleCommand('setWebserverConfig({{apiKey="{}"}})'.format(self._webServerAPIKeyNewHashed))

        headers = {'x-api-key': self._webServerAPIKeyNew}
        r = requests.get(url, headers=headers, timeout=self._webTimeout)
        self.assertTrue(r)
        self.assertEqual(r.status_code, 200)

        # now disable apiKey
        self.sendConsoleCommand('setWebserverConfig({apiKey=""})')

        r = requests.get(url, headers=headers, timeout=self._webTimeout)
        self.assertEqual(r.status_code, 401)

class TestAPIACL(APITestsBase):
    __test__ = True
    _consoleKey = DNSDistTest.generateConsoleKey()
    _consoleKeyB64 = base64.b64encode(_consoleKey).decode('ascii')
    _config_params = ['_consoleKeyB64', '_consolePort', '_testServerPort', '_webServerPort', '_webServerBasicAuthPasswordHashed', '_webServerAPIKeyHashed']
    _config_template = """
    setKey("%s")
    controlSocket("127.0.0.1:%s")
    setACL({"127.0.0.1/32", "::1/128"})
    newServer{address="127.0.0.1:%s"}
    webserver("127.0.0.1:%s")
    setWebserverConfig({password="%s", apiKey="%s", acl="192.0.2.1"})
    """

    def testACLChange(self):
        """
        API: Should be denied by ACL then allowed
        """

        url = 'http://127.0.0.1:' + str(self._webServerPort) + "/"
        try:
            r = requests.get(url, auth=('whatever', self._webServerBasicAuthPassword), timeout=self._webTimeout)
            self.assertTrue(False)
        except requests.exceptions.ConnectionError as exp:
            pass

        # reset the ACL
        self.sendConsoleCommand('setWebserverConfig({acl="127.0.0.1"})')

        r = requests.get(url, auth=('whatever', self._webServerBasicAuthPassword), timeout=self._webTimeout)
        self.assertTrue(r)
        self.assertEqual(r.status_code, 200)

class TestCustomLuaEndpoint(APITestsBase):
    __test__ = True
    _config_template = """
    setACL({"127.0.0.1/32", "::1/128"})
    newServer{address="127.0.0.1:%s"}
    webserver("127.0.0.1:%s")
    setWebserverConfig({password="%s"})

    function customHTTPHandler(req, resp)
      if req.path ~= '/foo' then
        resp.status = 500
        return
      end

      if req.version ~= 11 then
        resp.status = 501
        return
      end

      if req.method ~= 'GET' then
        resp.status = 502
        return
      end

      local get = req.getvars
      if get['param'] ~= '42' then
        resp.status = 503
        return
      end

      local headers = req.headers
      if headers['customheader'] ~= 'foobar' then
        resp.status = 504
        return
      end

      resp.body = 'It works!'
      resp.status = 200
      resp.headers = { ['Foo']='Bar'}
    end
    registerWebHandler('/foo', customHTTPHandler)
    """
    _config_params = ['_testServerPort', '_webServerPort', '_webServerBasicAuthPasswordHashed']

    def testBasic(self):
        """
        Custom Web Handler
        """
        url = 'http://127.0.0.1:' + str(self._webServerPort) + '/foo?param=42'
        headers = {'customheader': 'foobar'}
        r = requests.get(url, auth=('whatever', self._webServerBasicAuthPassword), timeout=self._webTimeout, headers=headers)
        self.assertTrue(r)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.content, b'It works!')
        self.assertEqual(r.headers.get('foo'), "Bar")

class TestWebConcurrentConnections(APITestsBase):
    __test__ = True
    _maxConns = 2

    _config_params = ['_testServerPort', '_webServerPort', '_webServerBasicAuthPasswordHashed', '_webServerAPIKeyHashed', '_maxConns']
    _config_template = """
    newServer{address="127.0.0.1:%s"}
    webserver("127.0.0.1:%s")
    setWebserverConfig({password="%s", apiKey="%s", maxConcurrentConnections=%d})
    """

    def testConcurrentConnections(self):
        """
        Web: Concurrent connections
        """

        conns = []
        # open the maximum number of connections
        for _ in range(self._maxConns):
            conn = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            conn.connect(("127.0.0.1", self._webServerPort))
            conns.append(conn)

        # we now hold all the slots, let's try to establish a new connection
        url = 'http://127.0.0.1:' + str(self._webServerPort) + "/"
        self.assertRaises(requests.exceptions.ConnectionError, requests.get, url, auth=('whatever', self._webServerBasicAuthPassword), timeout=self._webTimeout)

        # free one slot
        conns[0].close()
        conns[0] = None
        time.sleep(1)

        # this should work
        r = requests.get(url, auth=('whatever', self._webServerBasicAuthPassword), timeout=self._webTimeout)
        self.assertTrue(r)
        self.assertEqual(r.status_code, 200)
