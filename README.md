# Comfort Zone - homepage and customer cart update

## Changes made
- Updated `frontend/src/pages/Home.jsx` and `frontend/src/css/Home.css` to create the home page based on your notebook layout, with navigation, category filtering, product search, product cards, View Product, and Add to Cart.
- Added `frontend/src/pages/cart.jsx` and `frontend/src/css/Cart.css`.
- Updated `frontend/src/pages/ProductDetails.jsx` and added `frontend/src/css/ProductDetails.css` with Add to Cart and Buy Now actions.
- Added `/cart` route and a Cart navigation link.
- When a visitor clicks Add to Cart or Buy Now while logged out, the selected product is saved temporarily and they are sent to Login. Login has a link to Registration. After successful login, the cart resumes.
- Added a public customer registration endpoint and customer login response to the Django backend. Product GET endpoints are public while product writes remain admin-only.

## Run the project
For the isolated local demo, follow the commands in [Isolated local demo environment](#isolated-local-demo-environment). The default Django settings target MySQL; do not use unqualified migration commands for the local demo.

## Isolated local demo environment
The demo backend uses its own SQLite database at `backend/.demo-data/showroom.sqlite3` and private payment-file directory at `backend/.demo-data/private-payment-files`. It does not use MySQL or `test.sqlite3`.

From `backend`, initialize the demo database once and seed it:

```powershell
python manage.py migrate --settings=config.demo_settings
python manage.py seed_demo_data --settings=config.demo_settings
python manage.py runserver 127.0.0.1:8002 --settings=config.demo_settings
```

The seed command creates or recovers one Administrator and five other staff accounts, 25 customer accounts, 7 demo categories, 24 products, 6 vendors, 12 vendor purchases, and 45 synthetic customer orders. It uses the checkout, inventory, receiving, fulfillment, and unpaid-cancellation workflows; repeated runs do not duplicate records.

The command writes all demo usernames and roles plus the shared demo password to `backend/.demo-data/DEMO_CREDENTIALS.txt`. That file and the whole demo data directory are Git-ignored. The first run generates a strong local password; it remains stable across later runs and is reset only from this manifest. For a fresh database, you may set `COMFORTZONE_DEMO_PASSWORD` before the first seed. To rotate the existing password, edit the `Shared demo password` line in the local file and rerun the seed command; unset `COMFORTZONE_DEMO_PASSWORD` first if it is still set to the old value. Do not copy the password into this README or commit/share the credential file. The admin demo account is a dedicated superuser; the other staff accounts receive only their provisioned role permissions. The command refuses to overwrite a pre-existing, unmanifested `demo_admin` superuser.

Staff with the existing product-management permissions can upload product images from Manage Products. JPEG, PNG, and WebP files up to 5 MB are validated and stored under `backend/.demo-data/media/`; `image_url` remains available for existing catalogue entries. The seed includes two active products at 1 and 2 units respectively so the Low Stock report (default threshold: 5 units) and its CSV/PDF exports have real inventory movements to report. Re-running the seed command does not add duplicate adjustments, and stable demo product keys preserve seeded product records if their names are changed in the UI.

Customer accounts use Django's existing user model (name and email); the project has no separate customer-profile or customer-phone model. Their delivery addresses are stored as immutable order snapshots.

No payment attempts, verified receipts, confirmed refunds, or fabricated payment evidence are seeded. Payment approval requires checking actual bank/UPI records, and refund confirmation requires a real manual transaction reference. Orders therefore remain unpaid, while the seed includes valid unpaid cancellations and outstanding payment scenarios.

From the VS Code integrated PowerShell terminal, run `.\start_demo.ps1`. It keeps the launcher in that terminal, redirects each service's output to a unique run folder under `backend/.demo-data/logs/`, checks that each service's own PID serves its health endpoint, and stops only services it started when you press Ctrl+C. `start_demo.cmd` is a compatibility wrapper that invokes the same PowerShell launcher in the current console.

Vite 8 requires Node 22+. The launcher prints `Get-Command node`, `where.exe node`, and the selected executable/version; it does not modify PATH. If the selected PATH Node is too old, put Node 22+ first on this terminal's PATH or explicitly select it with `$env:COMFORTZONE_DEMO_NODE = 'C:\path\to\node.exe'` before running the launcher. Node installations in another terminal do not affect this selection. If PowerShell's execution policy is `AllSigned`, use `start_demo.cmd` or run `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass` first; this is limited to the current terminal process and does not change machine policy.

Start the frontend from `frontend` with Node 22 or newer:

```powershell
Set-Location ..\frontend
npm ci
$env:VITE_API_BASE_URL = 'http://127.0.0.1:8002/api'
npm run dev -- --host 127.0.0.1 --port 5173 --strictPort
```

## Checkout and payment note
The backend supports authenticated customer checkout and immutable order items. Payment remains a separate workflow requiring configured UPI instructions, customer-submitted proof, and staff verification against actual bank records. The demo seed deliberately does not fabricate payment receipts or refunds.
