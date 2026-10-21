# Step 1 — Ask the VW portal for your car's data (once)

Raval Trips reads the data that **you** ask the VW Group to share with you under the EU Data Act.
You only need to do this once.

1. Open **https://eu-data-act.drivesomethinggreater.com/** and sign in with your **VW ID**
   (the same account you use for the CUPRA app).
2. Go to **Data clusters → Vehicle overview**.
   If your car is not listed, follow the pairing and consent steps for your VIN.
3. Click **Get customised data** for your car and create a request with:
   - type: **continuous**
   - frequency: **every 15 minutes**
   - data clusters: **all** of them
4. Wait. Data files (small ZIPs) appear in the car's delivery list roughly every 15 minutes.
   The first one can take a while.
5. Drive or charge the car. The car only reports when something happens, so a parked car sends little.

## If nothing shows up
- Check that vehicle consent is enabled in your VW ID account settings.
- Some cars have an infotainment privacy mode that blocks data sharing.
- Files named `..._no_content_found.zip` mean the portal had nothing to send for that slot.
  If every file is like that after a day or two of driving, the problem is on the VW side.

## Good to know
- The portal does not send window or door states for every model, so there are **no "window open" alerts**.
- Values arrive with a delay of up to ~15 minutes, and battery level has 1 % steps, so energy and cost
  are estimates.
