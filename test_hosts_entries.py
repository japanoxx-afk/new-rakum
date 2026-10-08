import unittest
from hosts_entries import replace_entries

DOMAIN='rhakmugame.hangame.naver.com'
class HostsTests(unittest.TestCase):
    def test_replace_and_preserve(self):
        text=f'# comment\n127.0.0.1 localhost\n26.157.67.215 {DOMAIN} alias.example # keep\n25.1.2.3 {DOMAIN.upper()}\n'
        result=replace_entries(text,'26.240.153.112',[DOMAIN])
        self.assertIn('127.0.0.1 localhost\n',result)
        self.assertIn('26.157.67.215\talias.example # keep\n',result)
        self.assertEqual(result.lower().count(DOMAIN),1)
        self.assertIn('26.240.153.112 '+DOMAIN,result)
        self.assertEqual(replace_entries(result,'26.240.153.112',[DOMAIN]),result)
    def test_create(self):
        self.assertEqual(replace_entries('', '26.1.2.3',[DOMAIN]),'26.1.2.3 '+DOMAIN+'\n')
    def test_invalid(self):
        with self.assertRaises(ValueError): replace_entries('unchanged','26.1.',[DOMAIN])

if __name__=='__main__': unittest.main()
