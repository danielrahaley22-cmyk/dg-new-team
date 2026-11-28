# DG New Team sales dashboard (Jan 2027)

Live page: https://danielrahaley22-cmyk.github.io/dg-new-team/

**This repo is public.** It holds only code, state, first name, tickets, last 7 days, last sale
and this week's count. No phones, emails, Instagram handles, notes or statuses, ever.
Jan 2027 only: never put July 2027 team data in here.

## How to refresh

1. **Export.** Open the *DG Discount Code Sales* sheet, go to the **New Team** tab and choose
   File → Download → Comma-separated values (.csv). (The **Data** tab also works: the script keeps
   only rows whose Team starts with "New team".) Leave the CSV in Downloads. Don't put it in this folder.
2. **Run the script** from this folder:

   ```bash
   python3 refresh.py ~/Downloads/"DG Discount Code Sales - New Team.csv"
   ```

   It drops everything except the fields above. It matches sales on code + state only, and checks
   the totals against the tab's own "Tickets:" / "Last 7 days:" line. It works out this week's
   (Mon–Sun) tickets and runs a privacy scan. It stops and writes nothing if any check fails.
   Add `--as-of "2026-11-30 09:15"` if the export was taken earlier than now.
3. **Check.** Open `index.html` in a browser. The tickets total should equal the New Team tab's
   "Tickets:" number. Read any `NOTE` or `WEEK` lines the script printed.
4. **Push.**

   ```bash
   git add -A && git commit -m "Sales refresh 30 Nov 9:15am" && git push
   ```

   The page updates on GitHub Pages within a minute or two. Check it on your phone.

## Weekly cash bonus

Team weeks run Monday to Sunday (Week 1 = w/c 19 Oct). `weekly.json` keeps each code's
ticket total at the start of the week. "This week" = tickets now minus that Monday number.
On the first refresh of a new week the script closes the old week, adds it to the
finished list on the page, and sets the new Monday numbers. For exact weekly results,
do one refresh late Sunday or early Monday. If you don't, the script lists the codes whose
counts might be off.

## Safety checks

- `python3 refresh.py --check` scans every file in the repo for emails, phone numbers and handles.
- The pre-commit hook in `.githooks/` runs that scan. It also blocks commits unless git uses
  your GitHub no-reply email (`refresh.py` switches the hook on). On a new computer, copy the
  no-reply address from GitHub → Settings → Emails and run `git config user.email <that address>`
  in this folder.

The finished one-off incentives (Week 4, New Promoter, Merch) are fixed lists in `index.html`.
The Links & codes roster (first name, code, state) is also in `index.html`.
