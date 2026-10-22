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
import billing
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
        billing.init()
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
        self.assertEqual(self.req("GET", "/admin/accounts", cookie=cookie).status, 404)
        self.assertEqual(self.req("GET", "/costs", cookie=cookie).status, 404)

    def test_admin_sees_every_store_and_can_invite(self):
        cookie = self.login("admin@x.test", "adminpassword1")
        self.assertNotEqual(self.req("GET", "/api/scan?t=tok-theirs.test", cookie=cookie).status, 404)
        self.assertEqual(self.req("GET", "/admin", cookie=cookie).status, 200)
        r = self.req("POST", "/admin/invite", {"email": "new@x.test", "plan": "growth"}, cookie=cookie)
        self.assertEqual(r.status, 303)               # redirect: a refresh can't re-submit
        self.assertTrue(r.getheader("Location").startswith("/admin/accounts?created="))
        self.assertEqual(self.req("GET", r.getheader("Location"), cookie=cookie).status, 200)
        self.assertEqual(db.one("SELECT COUNT(*) FROM invites")[0], 1)
        inv = db.one("SELECT * FROM invites WHERE email='new@x.test'")
        self.assertEqual(inv["question_limit"], 75)

    def test_website_signed_in_marker_follows_the_session(self):
        os.environ["PRODUKTO_COOKIE_DOMAIN"] = "getprodukto.com"
        self.addCleanup(os.environ.pop, "PRODUKTO_COOKIE_DOMAIN", None)
        r = self.req("POST", "/login", {"email": "brand@x.test", "password": "brandpassword1"})
        cookies = r.msg.get_all("Set-Cookie")
        session = cookies[0].split(";")[0]
        self.assertIn("pk_signed_in=1; Domain=getprodukto.com", cookies[1])
        self.assertNotIn("HttpOnly", cookies[1])            # the website's script must read it
        # Signed in before the marker existed: the next visit hands it over.
        r = self.req("GET", "/api/scan?t=tok-mine.test", cookie=session)
        self.assertIn("pk_signed_in=1", r.getheader("Set-Cookie") or "")
        both = session + "; pk_signed_in=1"
        self.assertIsNone(self.req("GET", "/api/scan?t=tok-mine.test", cookie=both).getheader("Set-Cookie"))
        # Signing out, or a dead session, clears it so the site shows Log in again.
        r = self.req("GET", "/logout", cookie=both)
        self.assertIn("pk_signed_in=; Domain=getprodukto.com; Path=/; Max-Age=0", r.getheader("Set-Cookie"))
        r = self.req("GET", "/login", cookie="pk_signed_in=1")
        self.assertIn("pk_signed_in=;", r.getheader("Set-Cookie") or "")

    def test_settings_cancel_keep_and_password(self):
        cookie = self.login("brand@x.test", "brandpassword1")
        self.assertIn("Cancel plan", self.req_body("GET", "/settings", cookie=cookie))
        # No Stripe customer: the request is recorded for Kelian, not claimed as done.
        r = self.req("POST", "/settings/cancel", {"reason": "Too expensive", "note": "pricey"}, cookie=cookie)
        self.assertEqual(r.getheader("Location"), "/settings?cancel=requested")
        self.assertIn("Cancellation requested", self.req_body("GET", "/settings", cookie=cookie))
        admin = self.login("admin@x.test", "adminpassword1")
        self.assertIn("Cancel by hand in Stripe", self.req_body("GET", "/admin/accounts", cookie=admin))
        self.req("POST", "/settings/keep", {}, cookie=cookie)
        self.assertIsNone(billing.open_request(self.cust))
        # Admin sees a preview whose cancel button can't be submitted.
        self.assertEqual(self.req("POST", "/settings/cancel", {"reason": "Too expensive"}, cookie=admin)
                         .getheader("Location"), "/settings")
        self.assertIsNone(billing.open_request(self.admin))
        r = self.req("POST", "/settings/password", {"current": "nope", "new": "x" * 12, "new2": "x" * 12}, cookie=cookie)
        self.assertIn("pw_error", r.getheader("Location"))
        r = self.req("POST", "/settings/password", {"current": "brandpassword1", "new": "newbrandpass1",
                                                    "new2": "newbrandpass1"}, cookie=cookie)
        self.assertEqual(r.getheader("Location"), "/settings?saved=password")
        self.login("brand@x.test", "newbrandpass1")

    def test_cancelled_plan_switches_off_when_stripe_ends_it(self):
        cookie = self.login("brand@x.test", "brandpassword1")
        db.write("INSERT INTO cancellations(user_id,email,plan,requested_at,status,subscription,ends_at) "
                 "VALUES (?,?,?,?,?,?,?)", (self.cust, "brand@x.test", "Starter", 0, "scheduled", "sub_1", 100))
        # Period not over yet: nothing happens, whatever Stripe says.
        self.assertEqual(billing.end_due(now=50, fetch=lambda s: {"status": "canceled"}), [])
        # Over, but Stripe still has it running (cancel pending): wait.
        self.assertEqual(billing.end_due(now=200, fetch=lambda s: {"status": "active", "cancel_at_period_end": True}), [])
        self.assertEqual(self.req("GET", "/settings", cookie=cookie).status, 200)
        # Stripe ended it: account off, signed out.
        self.assertEqual(billing.end_due(now=200, fetch=lambda s: {"status": "canceled"}), ["brand@x.test"])
        self.assertEqual(db.one("SELECT disabled FROM users WHERE id=?", (self.cust,))[0], 1)
        self.assertNotEqual(self.req("GET", "/settings", cookie=cookie).status, 200)

    def test_plan_turned_back_on_in_stripe_closes_the_request(self):
        db.write("INSERT INTO cancellations(user_id,email,plan,requested_at,status,subscription,ends_at) "
                 "VALUES (?,?,?,?,?,?,?)", (self.cust, "brand@x.test", "Starter", 0, "scheduled", "sub_1", 100))
        self.assertEqual(billing.end_due(now=200, fetch=lambda s: {"status": "active"}), [])
        self.assertIsNone(billing.open_request(self.cust))
        self.assertEqual(db.one("SELECT disabled FROM users WHERE id=?", (self.cust,))[0], 0)

    def req_body(self, method, path, form=None, cookie=None):
        c = http.client.HTTPConnection("127.0.0.1", self.server.server_address[1], timeout=10)
        c.request(method, path, headers={"Cookie": cookie} if cookie else {})
        return c.getresponse().read().decode()

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


    # --- Stripe: paid checkout -> account -> onboarding (2026-10-13) ---------

    def _stripe(self, session):
        """Stand in for Stripe's API for the length of one test."""
        old = accounts.stripe_session
        accounts.stripe_session = lambda sid: session
        self.addCleanup(setattr, accounts, "stripe_session", old)

    PAID_GROWTH = {"status": "complete", "payment_status": "paid", "currency": "usd", "amount_subtotal": 29700,
                   "customer": "cus_123", "customer_details": {"email": "Buyer@Shop.test"}}

    def test_paid_checkout_creates_one_invite_with_the_bought_plan(self):
        self._stripe(self.PAID_GROWTH)
        sid = "cs_live_" + "a" * 20
        self.assertEqual(self.req("GET", "/welcome?session_id=" + sid).status, 200)
        self.req("GET", "/welcome?session_id=" + sid)          # reopened: no second invite
        rows = db.all_("SELECT * FROM invites WHERE stripe_session=?", (sid,))
        self.assertEqual(len(rows), 1)
        inv = rows[0]
        self.assertEqual((inv["email"], inv["question_limit"], inv["source"]), ("buyer@shop.test", 75, "stripe"))
        r = self.req("POST", "/invite/" + inv["token"], {"password": "buyerpassword1", "password2": "buyerpassword1"})
        self.assertEqual((r.status, r.getheader("Location")), (303, "/new"))
        u = db.one("SELECT * FROM users WHERE email='buyer@shop.test'")
        self.assertEqual((u["question_limit"], u["source"], u["stripe_customer"]), (75, "stripe", "cus_123"))

    def test_starter_price_gets_25_questions(self):
        self._stripe(dict(self.PAID_GROWTH, amount_subtotal=9900))
        self.req("GET", "/welcome?session_id=cs_live_" + "b" * 20)
        self.assertEqual(db.one("SELECT question_limit FROM invites WHERE source='stripe'")["question_limit"], 25)

    def test_unpaid_or_unknown_checkouts_create_nothing(self):
        self._stripe(dict(self.PAID_GROWTH, payment_status="unpaid", status="open"))
        self.req("GET", "/welcome?session_id=cs_live_" + "c" * 20)
        self.req("GET", "/welcome?session_id=not-a-session")
        self.req("GET", "/welcome")
        old = accounts.stripe_session
        def down(sid):
            raise accounts.StripeError("down")
        accounts.stripe_session = down
        self.addCleanup(setattr, accounts, "stripe_session", old)
        self.assertEqual(self.req("GET", "/welcome?session_id=cs_live_" + "d" * 20).status, 200)
        self.assertIsNone(db.one("SELECT 1 FROM invites"))

    # --- Emails the app sends itself (2026-10-21) ------------------------------

    def _outbox(self):
        """Catch emails instead of sending them."""
        import mailer
        box = []
        old = mailer._deliver
        def catch(eid, msg):
            box.append(msg)
            db.write("UPDATE emails SET status='sent' WHERE id=?", (eid,))
        mailer._deliver = catch
        self.addCleanup(setattr, mailer, "_deliver", old)
        return box

    def _wait(self, box, n):
        import time
        for _ in range(50):
            if len(box) >= n:
                return
            time.sleep(0.02)

    def test_payment_emails_the_buyer_their_link_once_and_tells_kelian(self):
        box = self._outbox()
        self._stripe(self.PAID_GROWTH)
        sid = "cs_live_" + "e" * 20
        self.req("GET", "/welcome?session_id=" + sid)
        self.req("GET", "/welcome?session_id=" + sid)
        self._wait(box, 2)
        self.assertEqual(sorted(m["To"] for m in box), ["buyer@shop.test", "kelian@getprodukto.com"])
        buyer = next(m for m in box if m["To"] == "buyer@shop.test")
        self.assertIn("Growth", buyer["Subject"])
        token = db.one("SELECT token FROM invites WHERE stripe_session=?", (sid,))["token"]
        self.assertIn("/invite/" + token, buyer.get_body(("plain",)).get_content())

    def test_forgot_password_emails_a_working_link_without_revealing_accounts(self):
        box = self._outbox()
        import accounts as a
        self.assertIn("Check your email", a.request_reset({"email": "Brand@x.test"})[1])
        self.assertIn("Check your email", a.request_reset({"email": "nobody@x.test"})[1])
        self.assertEqual(self.req("POST", "/forgot", {"email": "x@x.test"}).status, 200)
        self.assertEqual(self.req("GET", "/forgot").status, 200)
        self.req("POST", "/forgot", {"email": "brand@x.test"})     # within 2 minutes: no second email
        self._wait(box, 1)
        self.assertEqual([m["To"] for m in box], ["brand@x.test"])
        token = db.one("SELECT token FROM password_resets")["token"]
        self.assertIn("/reset/" + token, box[0].get_body(("plain",)).get_content())
        r = self.req("POST", "/reset/" + token, {"password": "newpassword12", "password2": "newpassword12"})
        self.assertEqual(r.status, 303)
        self.login("brand@x.test", "newpassword12")

    def test_first_results_email_goes_to_the_owner_once(self):
        import mailer
        box = self._outbox()
        mailer.first_results("mine.test", "Mine")
        mailer.first_results("mine.test", "Mine")                 # second scan: no second email
        mailer.first_results("theirs.test", "Theirs")             # no customer owns it
        self._wait(box, 1)
        self.assertEqual([m["To"] for m in box], ["brand@x.test"])
        self.assertIn("Mine", box[0]["Subject"])

    def test_excluded_demo_store_scans_once_a_customer_owns_it(self):
        import scheduler
        db.write("UPDATE prompt_sets SET prompts='[\"q\"]'")
        old = config.DAILY_SCAN_EXCLUDE
        config.DAILY_SCAN_EXCLUDE = ("mine.test", "theirs.test")
        self.addCleanup(setattr, config, "DAILY_SCAN_EXCLUDE", old)
        self.assertEqual(scheduler.scheduled(), ["mine.test"])     # mine.test has a paying owner

    def test_disabled_customer_is_signed_out_refused_and_not_scanned(self):
        import scheduler
        db.write("UPDATE prompt_sets SET prompts='[\"q\"]' WHERE store_domain='mine.test'")   # scheduler skips stores without questions
        cookie = self.login("brand@x.test", "brandpassword1")
        self.assertIn("mine.test", scheduler.scheduled())
        admin = self.login("admin@x.test", "adminpassword1")
        self.assertEqual(self.req("POST", "/admin/disable", {"user": self.cust, "disabled": "1"}, admin).status, 303)
        self.assertEqual(self.req("GET", "/r/tok-mine.test", cookie=cookie).status, 303)   # session ended
        r = self.req("POST", "/login", {"email": "brand@x.test", "password": "brandpassword1"})
        self.assertIsNone(r.getheader("Set-Cookie"))
        self.assertNotIn("mine.test", scheduler.scheduled())
        self.req("POST", "/admin/disable", {"user": self.cust, "disabled": "0"}, admin)
        self.assertIn("mine.test", scheduler.scheduled())
        self.login("brand@x.test", "brandpassword1")

    def test_customer_cannot_disable_accounts(self):
        cookie = self.login("brand@x.test", "brandpassword1")
        self.assertEqual(self.req("POST", "/admin/disable", {"user": self.admin, "disabled": "1"}, cookie).status, 404)

    def test_claiming_a_demoed_store_starts_completely_fresh(self):
        import content_agent, topics
        content_agent.init()
        db.write("INSERT INTO stores(domain,brand,brand_name) VALUES ('demoed.test','Demoed','Demoed')")
        ps = db.write("INSERT INTO prompt_sets(store_domain,prompts) VALUES ('demoed.test','[\"q\"]')")
        sc = db.write("INSERT INTO scans(token,prompt_set_id,status) VALUES ('real-demo',?,'done')", (ps,))
        a = db.write("INSERT INTO answers(scan_id,prompt,raw_text) VALUES (?,'q','x')", (sc,))
        db.write("INSERT INTO mentions(answer_id,product_name,brand) VALUES (?,'p','b')", (a,))
        db.write("INSERT INTO content_drafts(store_domain,draft_type,title,status) VALUES ('demoed.test','guide','t','draft')")
        new = accounts.create_user("new@x.test", "newpassword12", question_limit=25)
        accounts.set_current(dict(db.one("SELECT * FROM users WHERE id=?", (new,))))
        accounts.claim("demoed.test")
        for sql in ("SELECT 1 FROM prompt_sets WHERE store_domain='demoed.test'", "SELECT 1 FROM scans",
                    "SELECT 1 FROM answers WHERE id=%d" % a, "SELECT 1 FROM mentions WHERE answer_id=%d" % a,
                    "SELECT 1 FROM content_drafts WHERE store_domain='demoed.test'",
                    "SELECT 1 FROM stores WHERE domain='demoed.test'"):
            if "FROM scans" in sql:
                sql = "SELECT 1 FROM scans WHERE token='real-demo'"
            self.assertIsNone(db.one(sql), sql)
        self.assertTrue(db.one("SELECT 1 FROM user_stores WHERE store_domain='demoed.test'"))
        self.assertTrue(db.one("SELECT 1 FROM scans WHERE token='tok-mine.test'"))     # other stores untouched

if __name__ == "__main__":
    unittest.main()
