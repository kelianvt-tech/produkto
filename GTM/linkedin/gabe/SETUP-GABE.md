# LinkedIn agent: setup for Gabe

About 10 minutes. After this, your LinkedIn sends **40 connection requests a day, Monday to Friday, 9am–5pm (Spain time)** to e-commerce founders. It sends connection requests only, with no note and no messages.

Your leads are your own: 547 founders (347 coffee & tea, 200 pet). Kelian's account has different brands, so no founder hears from both of you.

**Before you start:** your LinkedIn headline should say what you do at Produkto. Founders look at your profile before accepting.

---

## 1. Put the folder somewhere

Unzip `gabe-linkedin-agent.zip` into your **Documents** folder. You should have `Documents/gabe-linkedin-agent/` with these files in it:
- `linkedin_agent.py`
- `gabe-leads-coffee-and-tea.csv`
- `gabe-leads-pet-products.csv`

## 2. Chrome

1. Open **Google Chrome** and make sure you're logged into LinkedIn.
2. In the top menu bar: **View → Developer → Allow JavaScript from Apple Events**. Make sure it has a tick.

## 3. Open Terminal and load your leads

Open **Terminal** (Cmd + Space, type "Terminal", Enter). Paste these lines one at a time and press Enter after each:

```
cd ~/Documents/gabe-linkedin-agent
```

```
python3 linkedin_agent.py import gabe-leads-coffee-and-tea.csv --niche "coffee and tea"
```

```
python3 linkedin_agent.py import gabe-leads-pet-products.csv --niche "pet products"
```

If a box pops up asking to install "command line developer tools", click **Install**, wait for it to finish, and run the line again.

You should see `Added 347` and then `Added 200`.

## 4. Test it (sends nothing)

```
python3 linkedin_agent.py test
```

- A new Chrome window opens a founder's profile, then the invite window, then closes it.
- The Mac will ask **"Terminal wants to control Google Chrome"**. Click **OK**.
- At the end you should see `DRY RUN: found 'Send without a note'`. If you see anything else, screenshot it and send it to Kelian.

## 5. Send one real request

```
python3 linkedin_agent.py send-one
```

You should see `invited`. Open that founder's profile in Chrome and check it says **Pending**.

## 6. Start the daily schedule

```
python3 linkedin_agent.py install
```

That's it. From now on it runs by itself.

- **Your Mac must be on and awake** during the day (9am–5pm, Mon–Fri). If it's asleep, it just picks up later.
- The first time it runs by itself, the Mac may ask **"python3 wants to control Google Chrome"**. Click **OK**.
- It opens its **own Chrome window**. Leave that window open (minimise it if you like); you can keep using Chrome normally in other windows.

---

## Day to day

See how it's going:
```
python3 ~/Documents/gabe-linkedin-agent/linkedin_agent.py status
```

Stop everything (e.g. you're travelling):
```
python3 ~/Documents/gabe-linkedin-agent/linkedin_agent.py pause
```

Start again:
```
python3 ~/Documents/gabe-linkedin-agent/linkedin_agent.py resume
```

**It stops itself** if LinkedIn ever shows a security check or a "weekly limit" message, and you get a Mac notification. If that happens, tell Kelian before resuming.

**Not in Spain?** The 9–5 hours are Spain time. Tell Kelian your time zone and he'll change it.
