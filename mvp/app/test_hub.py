"""Admin hub (/admin): admin only, lists every store with demo stores marked, never shows a key,
and its robots.txt reading is right. Runs the real request handler against a throwaway database."""

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
import hub


class HubTest(unittest.TestCase):
    def setUp(self):
        # Throwaway database chosen inside setUp - see test_scheduler.setUp.
        self.tmp = tempfile.TemporaryDirectory()
        self.old = config.DB_PATH
        config.DB_PATH = os.path.join(self.tmp.name, "h.db")
        assert not os.path.basename(config.DB_PATH).startswith("produkto.db")
        db.init()
        accounts.init()
        billing.init()
        for d in ("customer.test", "demo.test"):
            db.write("INSERT INTO stores(domain,brand) VALUES (?,?)", (d, d))
        accounts.create_user("admin@x.test", "adminpassword1", is_admin=True)
        cust = accounts.create_user("brand@x.test", "brandpassword1", question_limit=25)
        db.write("INSERT INTO user_stores(user_id,store_domain) VALUES (?,?)", (cust, "customer.test"))
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
        body = urllib.parse.urlencode(form) if form is not None else None
        if body:
            headers["Content-Type"] = "application/x-www-form-urlencoded"
        c.request(method, path, body=body, headers=headers)
        r = c.getresponse()
        return r, r.read().decode()

    def login(self, email, pw):
        r, _ = self.req("POST", "/login", {"email": email, "password": pw})
        return r.getheader("Set-Cookie").split(";")[0]

    def test_customer_never_sees_the_hub(self):
        cookie = self.login("brand@x.test", "brandpassword1")
        for path in ("/admin", "/admin/accounts", "/admin/brain", "/admin/anything"):
            self.assertEqual(self.req("GET", path, cookie=cookie)[0].status, 404, path)
        _, settings = self.req("GET", "/settings", cookie=cookie)
        self.assertNotIn('href="/admin"', settings)

    def test_admin_hub_lists_stores_and_links(self):
        cookie = self.login("admin@x.test", "adminpassword1")
        r, body = self.req("GET", "/admin", cookie=cookie)
        self.assertEqual(r.status, 200)
        self.assertIn("Produkto Admin", body)
        self.assertNotIn('class="rail"', body)                      # its own page: no product sidebar
        _, dash = self.req("GET", "/settings", cookie=cookie)
        self.assertNotIn('href="/admin"', dash)                     # and the product has no Admin tab
        self.assertIn("demo.test", body)
        self.assertIn("brand@x.test", body)                         # customer's store names its owner
        self.assertEqual(body.count("Demo · only you"), 1)          # only the store nobody pays for
        for link in ("/admin/accounts", "/admin/third-party", "/costs", hub.BRAIN_PLAN,
                     "https://dashboard.stripe.com", "https://console.apify.com/billing"):
            self.assertIn(link, body)
        self.assertNotIn("apify_api_", body)
        self.assertNotIn("sk_live", body)
        self.assertEqual(self.req("GET", "/admin/accounts", cookie=cookie)[0].status, 200)

    def test_robots_reading(self):
        self.assertEqual(hub.robots_ai("User-agent: *\nAllow: /\n"), [])
        self.assertEqual(hub.robots_ai("User-agent: GPTBot\nDisallow: /\n\nUser-agent: *\nAllow: /\n"), ["GPTBot"])
        everyone = hub.robots_ai("User-agent: *\nDisallow: /\n\nUser-agent: ClaudeBot\nAllow: /\n")
        self.assertIn("GPTBot", everyone)
        self.assertNotIn("ClaudeBot", everyone)                     # its own group overrides '*'
        self.assertEqual(hub.robots_ai("User-agent: *\nDisallow: /admin\n"), [])
        self.assertEqual(hub.sitemap_urls("<url><loc> https://a.test/x </loc></url>"), ["https://a.test/x"])


if __name__ == "__main__":
    unittest.main()
