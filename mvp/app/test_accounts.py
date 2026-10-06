"""Accounts: a customer must never see another store, and must be signed in
to see anything. Runs the real request handler against a throwaway database."""

import http.client
import os
import tempfile
import threading
import unittest
import urllib.parse
from http.server import ThreadingHTTPServer

import accounts
import app
import config
import db


class AccountsTest(unittest.TestCase):
    def setUp(self):
        # Throwaway database chosen inside setUp - see test_scheduler.setUp.
        self.tmp = tempfile.TemporaryDirectory()
        self.old = config.DB_PATH
        config.DB_PATH = os.path.join(self.tmp.name, "a.db")
        assert not config.DB_PATH.endswith("produkto.db")
        db.init()
        accounts.init()
        for d in ("mine.test", "theirs.test"):
            db.write("INSERT INTO stores(domain,brand) VALUES (?,?)", (d, d))
            ps = db.write("INSERT INTO prompt_sets(store_domain,prompts) VALUES (?,'[]')", (d,))
            db.write("INSERT INTO scans(token,prompt_set_id,status) VALUES (?,?,'done')", ("tok-" + d, ps))
            db.write("INSERT INTO products(store_domain,shopify_id,title) VALUES (?,?,?)", (d, 1, d))
        self.admin = accounts.create_user("admin@x.test", "adminpassword1", is_admin=True)
        self.cust = accounts.create_user("brand@x.test", "brandpassword1", question_limit=25)
        db.write("INSERT INTO user_stores(user_id,store_domain) VALUES (?,?)", (self.cust, "mine.test"))
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), app.Handler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        accounts.set_current(None)
        config.DB_PATH = self.old
        self.tmp.cleanup()

    def req(self, method, path, form=None, cookie=None):
        c = http.client.HTTPConnection("127.0.0.1", self.server.server_address[1], timeout=10)
        headers = {"Cookie": cookie} if cookie else {}
        body = None
        if form is not None:
            body = urllib.parse.urlencode(form)
            headers["Content-Type"] = "application/x-www-form-urlencoded"
        c.request(method, path, body=body, headers=headers)
        r = c.getresponse()
        r.read()
        return r

    def login(self, email, pw):
        r = self.req("POST", "/login", {"email": email, "password": pw})
        self.assertEqual(r.status, 303)
        return r.getheader("Set-Cookie").split(";")[0]

    def test_passwords_are_hashed_and_checked(self):
        stored = accounts.hash_pw("correct horse")
        self.assertNotIn("correct horse", stored)
        self.assertTrue(accounts.check_pw("correct horse", stored))
        self.assertFalse(accounts.check_pw("wrong", stored))

    def test_signed_out_visitor_is_sent_to_login(self):
        r = self.req("GET", "/r/tok-mine.test")
        self.assertEqual(r.status, 303)
        self.assertTrue(r.getheader("Location").startswith("/login"))
        self.assertEqual(self.req("POST", "/api/scan?d=mine.test", {}).status, 401)

    def test_wrong_password_gets_no_session(self):
        r = self.req("POST", "/login", {"email": "brand@x.test", "password": "nope"})
        self.assertEqual(r.status, 200)
        self.assertIsNone(r.getheader("Set-Cookie"))

    def test_customer_cannot_open_another_store(self):
        cookie = self.login("brand@x.test", "brandpassword1")
        for path in ("/r/tok-theirs.test", "/r/tok-theirs.test/answers", "/brand?d=theirs.test",
                     "/store?d=theirs.test", "/api/scan?t=tok-theirs.test", "/topics?d=theirs.test"):
            self.assertEqual(self.req("GET", path, cookie=cookie).status, 404, path)
        self.assertEqual(self.req("POST", "/api/scan?d=theirs.test", {}, cookie=cookie).status, 404)
        theirs_pid = db.one("SELECT id FROM products WHERE store_domain='theirs.test'")[0]
        self.assertEqual(self.req("GET", "/product?id=%d" % theirs_pid, cookie=cookie).status, 404)
        self.assertEqual(self.req("POST", "/api/brand?id=%d" % theirs_pid, {}, cookie=cookie).status, 404)
        self.assertEqual(self.req("GET", "/admin", cookie=cookie).status, 404)
        self.assertEqual(self.req("GET", "/costs", cookie=cookie).status, 404)

    def test_admin_sees_every_store_and_can_invite(self):
        cookie = self.login("admin@x.test", "adminpassword1")
        self.assertNotEqual(self.req("GET", "/api/scan?t=tok-theirs.test", cookie=cookie).status, 404)
        self.assertEqual(self.req("GET", "/admin", cookie=cookie).status, 200)
        r = self.req("POST", "/admin/invite", {"email": "new@x.test", "plan": "growth"}, cookie=cookie)
        self.assertEqual(r.status, 303)               # redirect: a refresh can't re-submit
        self.assertTrue(r.getheader("Location").startswith("/admin?created="))
        self.assertEqual(self.req("GET", r.getheader("Location"), cookie=cookie).status, 200)
        self.assertEqual(db.one("SELECT COUNT(*) FROM invites")[0], 1)
        inv = db.one("SELECT * FROM invites WHERE email='new@x.test'")
        self.assertEqual(inv["question_limit"], 75)

    def test_invite_link_creates_account_once(self):
        db.write("INSERT INTO invites(token,email,question_limit,created_at) VALUES ('inv1','new@x.test',25,0)")
        self.assertEqual(self.req("GET", "/invite/inv1").status, 200)
        r = self.req("POST", "/invite/inv1", {"password": "newpassword1", "password2": "newpassword1"})
        self.assertEqual((r.status, r.getheader("Location")), (303, "/new"))
        self.assertIn("pk_session=", r.getheader("Set-Cookie"))
        self.assertEqual(self.req("GET", "/invite/inv1").status, 404)
        self.assertEqual(db.one("SELECT question_limit FROM users WHERE email='new@x.test'")[0], 25)

    def test_customer_limited_to_one_store_and_no_stealing(self):
        accounts.set_current(dict(db.one("SELECT * FROM users WHERE id=?", (self.cust,))))
        with self.assertRaises(PermissionError):
            accounts.claim("another.test")          # plan covers one store
        other = accounts.create_user("other@x.test", "otherpassword1")
        accounts.set_current(dict(db.one("SELECT * FROM users WHERE id=?", (other,))))
        with self.assertRaises(PermissionError):
            accounts.claim("mine.test")             # owned by someone else
        accounts.claim("fresh.test")
        self.assertTrue(accounts.can_see("fresh.test"))
        self.assertFalse(accounts.can_see("mine.test"))

    def test_question_cap_follows_the_owner(self):
        accounts.set_current(None)                  # e.g. the daily scheduler
        with self.assertRaises(ValueError):
            accounts.check_question_limit("mine.test", 26)
        accounts.check_question_limit("mine.test", 25)
        accounts.check_question_limit("theirs.test", 500)   # admin/demo store: no cap

    def test_admin_reset_link_changes_password_once(self):
        admin = self.login("admin@x.test", "adminpassword1")
        old_session = self.login("brand@x.test", "brandpassword1")
        r = self.req("POST", "/admin/reset", {"user": str(self.cust)}, cookie=admin)
        self.assertEqual(r.status, 303)
        token = r.getheader("Location").split("reset=")[1]
        self.assertEqual(self.req("GET", "/admin?reset=" + token, cookie=admin).status, 200)
        self.assertEqual(self.req("GET", "/reset/" + token).status, 200)
        r = self.req("POST", "/reset/" + token, {"password": "brandnewpass1", "password2": "brandnewpass1"})
        self.assertEqual(r.status, 303)
        self.assertEqual(self.req("GET", "/reset/" + token).status, 404)          # works once
        self.assertEqual(self.req("GET", "/r/tok-mine.test", cookie=old_session).status, 303)  # old session gone
        self.login("brand@x.test", "brandnewpass1")
        r = self.req("POST", "/login", {"email": "brand@x.test", "password": "brandpassword1"})
        self.assertIsNone(r.getheader("Set-Cookie"))

    def test_customer_cannot_issue_reset_links(self):
        cookie = self.login("brand@x.test", "brandpassword1")
        self.assertEqual(self.req("POST", "/admin/reset", {"user": str(self.admin)}, cookie=cookie).status, 404)

    def test_logout_ends_the_session(self):
        cookie = self.login("brand@x.test", "brandpassword1")
        self.req("GET", "/logout", cookie=cookie)
        self.assertEqual(self.req("GET", "/r/tok-mine.test", cookie=cookie).status, 303)


if __name__ == "__main__":
    unittest.main()
