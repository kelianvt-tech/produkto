"""Dates on the dashboard belong to the merchant's clock.

The bug these guard against: the server runs in Barcelona, the merchant sells
from California, and a scan taken on the Barcelona morning of the 28th is
still the evening of the 27th in Los Angeles. Labelled with the server's date
it reads as a measurement from tomorrow, which is the fastest way to lose
someone's trust in a number.
"""

import datetime as dt
import os
import tempfile
import unittest
from zoneinfo import ZoneInfo

import config
import db
import period
import storetime

US = "shop-usa.com"
ES = "tienda.es"


class StoreTimeTest(unittest.TestCase):
    def setUp(self):
        # Choose the database inside setUp, never via PRODUKTO_DB at import
        # time: another test module may already have loaded config and picked
        # the real produkto.db.
        self.tmp = tempfile.TemporaryDirectory()
        self.old = config.DB_PATH
        config.DB_PATH = os.path.join(self.tmp.name, "t.db")
        assert not config.DB_PATH.endswith("produkto.db")
        db.init()
        storetime.forget()
        db.write("INSERT INTO stores(domain,country) VALUES(?,?)", (US, "US"))
        db.write("INSERT INTO stores(domain,country) VALUES(?,?)", (ES, "ES"))

    def tearDown(self):
        storetime.forget()
        config.DB_PATH = self.old
        self.tmp.cleanup()

    def test_country_picks_the_zone(self):
        self.assertEqual(storetime.zone_name(US), "America/New_York")
        self.assertEqual(storetime.zone_name(ES), "Europe/Madrid")

    def test_an_unknown_store_falls_back_to_utc_not_the_server(self):
        # UTC is neutral. Falling back to the server's clock would make every
        # unknown store quietly Spanish.
        self.assertEqual(storetime.zone_name("never-seen.com"), "UTC")

    def test_a_scan_is_never_dated_in_the_merchants_future(self):
        # 00:30 on 28 Sep in Madrid is still 18:30 on the 27th in New York.
        madrid_midnight = dt.datetime(2026, 9, 28, 0, 30,
                                      tzinfo=ZoneInfo("Europe/Madrid")).timestamp()
        self.assertEqual(storetime.date_of(madrid_midnight, storetime.zone(US)),
                         dt.date(2026, 9, 27))
        self.assertEqual(storetime.date_of(madrid_midnight, storetime.zone(ES)),
                         dt.date(2026, 9, 28))

    def test_a_morning_scan_keeps_its_date_across_the_whole_us(self):
        # The reason America/New_York is the representative US zone: a 06:00
        # Eastern scan is still the same calendar day in Los Angeles and
        # Honolulu, so no US merchant sees yesterday's date on it.
        eastern_six = dt.datetime(2026, 9, 27, 6, 0,
                                  tzinfo=ZoneInfo("America/New_York")).timestamp()
        for zone in ("America/Los_Angeles", "Pacific/Honolulu", "America/Anchorage"):
            self.assertEqual(storetime.date_of(eastern_six, ZoneInfo(zone)),
                             dt.date(2026, 9, 27), zone)

    def test_the_period_is_the_merchants_days(self):
        # "Last 7 days" ends on the merchant's today and starts 6 days before.
        per = dict(range="7", group="day", frm="", to="")
        today = dt.date(2026, 9, 27)
        a, b, start, end = period.bounds(per, today=today, tz=storetime.zone(US))
        self.assertEqual((a, b), (dt.date(2026, 9, 21), today))
        # The window must open at midnight in New York, not in Barcelona.
        self.assertEqual(dt.datetime.fromtimestamp(start, storetime.zone(US)).hour, 0)
        self.assertEqual(dt.datetime.fromtimestamp(end, storetime.zone(US)).date(), today)

    def test_a_scan_at_the_edge_of_the_period_is_included(self):
        # A scan at 23:50 on the merchant's last day is inside the range.
        per = dict(range="7", group="day", frm="", to="")
        tz = storetime.zone(US)
        _, _, start, end = period.bounds(per, today=dt.date(2026, 9, 27), tz=tz)
        late = dt.datetime(2026, 9, 27, 23, 50, tzinfo=tz).timestamp()
        self.assertTrue(start <= late <= end)


if __name__ == "__main__":
    unittest.main()
