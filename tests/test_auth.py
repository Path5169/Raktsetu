import unittest, os, tempfile, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from raktsetu import db, seed, auth

class Auth(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.path=os.path.join(tempfile.mkdtemp(),'auth.db'); cls.conn=db.connect(cls.path); seed.seed(cls.conn)
    @classmethod
    def tearDownClass(cls): cls.conn.close()
    def test_seeded_roles_login(self):
        for username,password,role in [('admin@raktsetu.demo','Admin@123','admin'),('hospital1@raktsetu.demo','Hospital@123','hospital'),('bank1@raktsetu.demo','Bank@123','bank')]:
            result=auth.login(self.conn,username,password); self.assertEqual(result['role'],role); self.assertEqual(auth.session(self.conn,result['token'])['role'],role)
    def test_bad_password_rejected(self):
        with self.assertRaises(auth.AuthError): auth.login(self.conn,'admin@raktsetu.demo','wrong')
    def test_role_is_server_side(self):
        result=auth.login(self.conn,'hospital1@raktsetu.demo','Hospital@123')
        user=auth.require(self.conn,result['token'],'hospital'); self.assertEqual(user['hospital_id'],1)
        with self.assertRaises(auth.ForbiddenError): auth.require(self.conn,result['token'],'bank')

if __name__=='__main__': unittest.main()
