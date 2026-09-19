# Tailorly — Build Roadmap

A phased task list to take this from a single `Customer` model to a working shop-management app.

Phases are ordered by dependency, not by importance. Phase 0 items are the ones that are painful to change later — do them first.

---

## Settled constraints

| # | Constraint |
|---|---|
| C1 | **Single shop, single branch.** No `Branch` model. |
| C2 | **India, INR.** Not GST-registered — invoices carry no tax breakdown. |
| C3 | **Two roles: admin and staff.** Staff must not see customer PII (see below). Customers don't log in; they get read-only tracking links. |
| C4 | **Payments via UPI link/QR.** No payment gateway, no Razorpay, no webhooks. |
| C5 | **Tailors are on fixed daily salary**, not piece rate. No per-piece wage ledger. |
| C6 | Server-rendered Django templates, no separate SPA frontend. |
| C7 | **Order intake is admin-only.** No front-desk role — the shop takes orders when the admin is present. |
| C8 | **WhatsApp: Meta Cloud API, direct and simple.** One provider, one module, no abstraction layer. |
| C9 | **No existing data to import.** Customers and measurements start empty. |
| C10 | **Agentic access via MCP**, one remote server serving both Claude and ChatGPT (Phase 13). |

All scoping decisions are resolved. Nothing below is blocked on an answer.

---

## Cross-cutting: the PII boundary

This is the constraint that shapes the most code, so it gets stated once here rather than repeated in every phase.

**Rule:** staff see orders, garments, measurements, and their own assignments. Staff do **not** see customer phone, email, address, date of birth, or the customer list. On an order, staff see the customer's **name only**.

Consequences to design for:

- **Measurements stay visible to staff.** They're arguably personal data, but tailors cannot work without them. The boundary is *contact details*, not *everything about the customer*.
- **Enforce at the query layer, not the template layer.** Hiding a field in HTML still leaks it through admin, exports, error pages, and any future API. Use distinct views per role with querysets that `.only()` the safe columns, and never pass a full `Customer` instance into a staff-facing template.
- **Django admin is part of the boundary.** Staff should have no admin permission on `Customer` at all. Don't rely on `list_display` to hide things.
- **Printed job tickets carry no phone number** (4.9) — they're handled by staff all day.
- **WhatsApp sends are system-triggered.** A staff member marking an order `READY` causes a message to go out without ever seeing the number. That's the intended design; the send happens in a background job under system credentials.
- **Notification failure alerts go to admin, not staff** (8.7) — "couldn't reach +91…" would leak the number.
- **The MCP server is another surface, not an exception** (13.2). It must run through the same querysets, and it adds a new question the UI never raised: PII sent to a tool result leaves your server for a model provider. See risk 3.

---

## Phase 0 — Foundations

Hard-to-reverse decisions. Nothing else should start before these land.

- [ ] **0.1** Add a custom user model (`accounts.User`, subclassing `AbstractUser`) and set `AUTH_USER_MODEL` **before any further migrations exist**. Swapping this after production data exists requires manual table surgery.
- [ ] **0.2** Split settings into `base/dev/prod` (or use `django-environ`). Move `SECRET_KEY`, `DEBUG`, `ALLOWED_HOSTS`, and DB config to env vars. Current `settings.py` is stock `startproject` output with a committed dev secret key.
- [ ] **0.3** Add an abstract `TimeStampedModel` (`created_at`/`updated_at`) and inherit it everywhere. Retrofit `Customer`.
- [ ] **0.4** Switch to PostgreSQL for dev/prod (SQLite is fine for tests). You will want `JSONField` querying, proper constraints, and concurrent writes.
- [ ] **0.5** Set up the test harness: `pytest-django` (or stick with Django's runner), `factory_boy` for fixtures, and a `make test` / `just test` entry point.
- [ ] **0.6** Add `ruff` for lint + format and wire a pre-commit hook.
- [ ] **0.7** Add media file handling (`MEDIA_ROOT`/`MEDIA_URL`, S3 or local) — needed for reference photos in Phase 4.
- [ ] **0.8** Set `TIME_ZONE = 'Asia/Kolkata'` (keep `USE_TZ = True`).

## Phase 1 — People, roles & the PII boundary

- [ ] **1.1** `Employee` profile model: OneToOne to `User`, plus `phone`, `joined_on`, `is_active`, `daily_salary`, `daily_capacity`.
- [ ] **1.2** Two Django Groups: `ADMIN` (owner/manager — full access) and `STAFF` (tailors/production). Use Groups + permissions rather than a role column, so the set can grow without a migration.
- [ ] **1.3** **Implement the PII boundary** per the section above: staff-safe querysets, no `Customer` admin permission for staff, name-only exposure on order screens.
- [ ] **1.4** Write the permission tests *first* and keep them adversarial — assert that a staff session gets 403 or a masked field on every customer-detail, export, and admin URL. This is the rule most likely to regress silently as screens get added.
- [ ] **1.5** Employee CRUD + deactivation (never hard-delete — historical orders reference them).
- [ ] **1.6** Audit log for admin PII access — who opened which customer record, when.

## Phase 2 — Customers (harden what exists)

- [ ] **2.1** Add a unique constraint on normalized `phone`. Right now two records can hold the same number in different formats.
- [ ] **2.2** Fix the normalization gap: `Customer.clean()` rewrites `phone` to E.164, but `Model.save()` never calls `clean()`. Either override `save()` to call `full_clean()`, or move normalization into a custom field / `pre_save` signal. Otherwise scripted and imported records store raw input.
- [ ] **2.3** Add optional `email`, `address`, `date_of_birth`, `notes`, `preferred_language`.
- [ ] **2.4** Add `whatsapp_opt_in` (boolean + timestamp). Required for compliant business-initiated messaging in Phase 8.
- [ ] **2.5** Customer search by name or phone, with partial-phone matching (last 4 digits). **Admin-only** — this screen is the PII boundary's main pressure point.
- [ ] **2.6** Customer detail page (admin-only): order history, outstanding balance, saved measurements.
- [ ] **2.7** Duplicate-customer merge tool.

## Phase 3 — Catalog & measurements

The central design problem. Get this right and orders are easy.

- [ ] **3.1** `GarmentType` — Shirt, Pant, Blouse, Kurta, Salwar, Suit, Lehenga, etc. With `name`, `base_price`, `default_stitching_days`, `is_active`.
- [ ] **3.2** `MeasurementField` — the per-garment field catalog: `garment_type` FK, `name` ("Chest"), `code` (`chest`), `unit` (in/cm), `display_order`, `is_required`. This makes garment types configurable from the admin instead of hardcoded.
- [ ] **3.3** `MeasurementProfile` — a customer's saved measurements for one garment type. Store values in a `JSONField` keyed by `MeasurementField.code`, validated against the template in `clean()`.
- [ ] **3.4** **Version measurement profiles.** Bodies change. Keep old versions rather than overwriting, so a six-month-old order still shows the measurements it was actually cut to.
- [ ] **3.5** `StyleOption` — per-garment choices (collar type, sleeve length, pocket count, fit) with optional price deltas.
- [ ] **3.6** Measurement entry UI: pick garment type → render its fields in `display_order` → prefill from the customer's latest profile.

## Phase 4 — Orders

- [ ] **4.1** `Order` — `customer` FK, human-readable `order_number` (e.g. `TLR-2026-0142`), `placed_on`, `promised_date`, `priority` (normal/rush), `status`, `notes`, `total_amount`, `amount_paid`.
- [ ] **4.2** `OrderItem` — one row per garment: `garment_type`, `quantity`, `unit_price`, chosen `StyleOption`s, per-item `status` and `promised_date`.
- [ ] **4.3** **Snapshot measurements and price onto `OrderItem` at creation time.** Copy the values, don't just FK the profile — otherwise editing a customer's measurements silently rewrites the history of completed orders.
- [ ] **4.4** Order status workflow: `DRAFT → RECEIVED → CUTTING → STITCHING → FINISHING → TRIAL_PENDING → READY → DELIVERED`, plus `CANCELLED`. Enforce legal transitions in one place (a `transition_to()` method), not scattered across views.
- [ ] **4.5** `OrderStatusLog` — who changed status, when, from what to what. Non-negotiable for "who said this was ready?"
- [ ] **4.6** Fabric tracking: `source` (customer-provided / shop-provided), `fabric_description`, `meters_used`, and for shop cloth a FK to inventory (Phase 14).
- [ ] **4.7** Reference photos: attach multiple images per order item (design references customers bring on their phones).
- [ ] **4.8** Due-date calculation from `GarmentType.default_stitching_days` + current workload, overridable by admin.
- [ ] **4.9** Job ticket / tag printing — order number, **customer name only**, garment, due date, and a QR code linking to the internal order page. No phone number on the ticket.
- [ ] **4.10** Staff order list with filters: by status, overdue, due today/this week, by assigned tailor. Built on the staff-safe queryset (1.3).

## Phase 5 — Production & work assignment

- [ ] **5.1** `WorkAssignment` — `order_item` FK, `employee` FK, `stage` (cutting/stitching/finishing), `assigned_at`, `started_at`, `completed_at`.
- [ ] **5.2** Tailor worklist view — "my jobs", sorted by due date, with a one-tap complete action. This is the screen staff actually use; keep it mobile-friendly and inside the PII boundary.
- [ ] **5.3** Auto-advance `OrderItem.status` when all assignments for a stage complete.
- [ ] **5.4** Workload/capacity view — jobs per tailor per day, to spot overcommitment before promising a date.
- [ ] **5.5** *(Optional, given C5)* Attendance register — days present per employee per month. With fixed daily salary, monthly pay is `days_present × daily_salary`; that's simple enough that payroll may be better left outside the app. Build only if you want attendance tracked here.

## Phase 6 — Trials, alterations & delivery

- [ ] **6.1** `Trial` — scheduled fitting appointment against an order: `scheduled_for`, `status`, `notes`.
- [ ] **6.2** `Alteration` — raised after a trial or after delivery: `order_item` FK, description, `is_chargeable`, `charge_amount`, assigned employee, due date. Loops the item back into the production workflow.
- [ ] **6.3** Track rework rate per tailor — the single most useful quality metric you'll have, and it stays useful even without piece-rate pay.
- [ ] **6.4** Delivery: record `delivered_at`, `delivered_to` (customer vs. someone collecting on their behalf), and block delivery when a balance is outstanding unless admin overrides.

## Phase 7 — Billing & payments

No GST (C2): invoices are `subtotal − discount = total`. No payment gateway (C4): UPI links only.

- [ ] **7.1** `Invoice` — `order` FK, `invoice_number` (gapless sequence, generated in a transaction), line items copied from order items, `subtotal`, `discount`, `total`, `issued_at`.
- [ ] **7.2** `Payment` — supports **partial payments**: `invoice` FK, `amount`, `method` (cash/UPI/card), `paid_at`, `reference` (UPI txn ID, typed in by hand), `recorded_by`. An order typically takes an advance at booking and the balance at delivery.
- [ ] **7.3** Derived balance on order and customer (`total - sum(payments)`), plus an outstanding-dues report.
- [ ] **7.4** UPI link + QR generation. Build a `upi://pay?pa=<vpa>&pn=<shop>&am=<amount>&cu=INR&tn=<order no>&tr=<ref>` deep link, render it as a QR (the `qrcode` library) for the counter, and include the link in WhatsApp messages. Shop VPA lives in settings.
- [ ] **7.5** **Manual payment confirmation.** A plain UPI link has no callback — nothing tells the app that money arrived. Admin marks payments received after checking their UPI app or SMS. Put the "record payment" action one tap from the order, and generate a unique `tr` reference per invoice so a bank statement can be matched back to an order.
- [ ] **7.6** Unpaid/partially-paid dues list, since reconciliation is manual and things will be missed.
- [ ] **7.7** PDF invoice generation (WeasyPrint or ReportLab) + a shareable invoice link. Admin-only actions; the customer's own copy goes out via the tokenised link in 10.2.
- [ ] **7.8** Refunds / cancellation handling and credit notes.

## Phase 8 — WhatsApp notifications

- [ ] **8.1** Direct Meta WhatsApp Cloud API integration in one module, `notifications/whatsapp.py` (C8). Keep sending behind a single `send_template(customer, template_name, params)` function — that's enough indirection to swap providers later without building a plugin system now.
- [ ] **8.2** Background job runner — Celery + Redis (or django-q2 for something lighter). Never send messages inline in a request/response cycle. Sends run under system credentials, so staff actions can trigger them without staff seeing the number.
- [ ] **8.3** `MessageLog` — record every send with provider message ID, status, and failure reason. You will need this when a customer insists they were never told. **Admin-only viewing** — the log contains phone numbers. Template names and their parameter order live in settings; no DB template model at this scale.
- [ ] **8.4** Get templates approved by Meta. Business-initiated messages outside the 24-hour customer-service window **must** use a pre-approved template — this has a lead time, so start it early.
- [ ] **8.5** Triggered messages:
  - Order confirmed (order number + promised date + tracking link)
  - Trial appointment reminder (day before)
  - **Order ready for pickup** ← your original ask
  - Payment reminder with the UPI link for the outstanding balance
  - Delivery confirmation + invoice link
  - Optional: birthday/anniversary offers
- [ ] **8.6** Respect `whatsapp_opt_in` and handle opt-out replies (STOP).
- [ ] **8.7** Retry with backoff on send failure; alert **admin** (not staff) after final failure so someone can phone the customer instead.

## Phase 9 — UI

- [ ] **9.1** Django templates + HTMX (C6) — lowest-effort path that still feels responsive.
- [ ] **9.2** Order intake flow — the highest-traffic screen. Customer lookup/create → garments → measurements → styles → fabric → price → advance payment → print ticket. Optimise for speed; it happens with a customer standing at the counter. Admin-only (C7).
- [ ] **9.3** Admin dashboard: due today, overdue, ready for pickup, unpaid balances, today's intake.
- [ ] **9.4** Staff home: mobile-friendly worklist (5.2) plus the shop-wide order board (4.10). No customer or money screens.
- [ ] **9.5** Keep Django admin as the back-office tool for catalog and corrections — but only for the `ADMIN` group.

## Phase 10 — Customer-facing

- [ ] **10.1** Tokenised public order-tracking page (unguessable UUID in the URL, no login) showing status and promised date.
- [ ] **10.2** Public invoice view with a UPI pay button / QR.
- [ ] **10.3** Include the tracking link in the order-confirmation WhatsApp message.

## Phase 11 — Reporting

Admin-only, all of it.

- [ ] **11.1** Revenue by day/week/month; collected vs. outstanding.
- [ ] **11.2** Orders by status and garment type; average turnaround time.
- [ ] **11.3** Tailor productivity: pieces completed, on-time rate, rework rate.
- [ ] **11.4** Customer insights: repeat rate, top customers, dormant customers.
- [ ] **11.5** CSV export for the accountant — route through the same permission checks as the screens; exports are the classic PII leak.

## Phase 12 — Expenses & profitability

Rent, electricity, salaries, materials — the other half of the money picture. Without it, Phase 11 reports revenue and calls it profit.

Admin-only, all of it. Staff never see money screens.

- [ ] **12.1** `ExpenseCategory` — `name`, `is_recurring`, `is_fixed`, `is_active`. Seed with: rent, electricity, water, staff salaries, fabric & materials, consumables (thread/buttons/zips), machine maintenance, transport, phone & internet, shop supplies, licences & fees, misc. Keep it a **model, not a choices enum**, so adding a category doesn't need a migration.
- [ ] **12.2** `Expense` — `category` FK, `amount`, `incurred_on`, `paid_on` (nullable — a bill you've received but not paid is still one you need to see), `payment_method` (cash/UPI/bank), `payee`, `bill_reference`, `receipt` image, `notes`, `recorded_by`.
- [ ] **12.3** `RecurringExpense` — a template for the predictable ones: category, expected amount, day of month, active flag. A scheduled job on the Phase 8 worker materialises a **draft** `Expense` each month for the admin to confirm and correct — rent is the same every month, electricity isn't. **This is the task that stops the P&L quietly overstating profit** because someone forgot to log rent.
- [ ] **12.4** Salaries as expenses. With fixed daily pay (C5), a month's wage bill is `days_present × daily_salary` per employee. If the attendance register (5.5) gets built, generate the salary expense from it; if not, it's one manual entry per employee per month. Either way it posts to the staff-salaries category and lands in the P&L like any other cost.
- [ ] **12.5** Optional `order` FK on `Expense`, for fabric bought against a specific job. Enough to answer "what did this order actually cost us" without building full job costing — don't go further unless shop-provided cloth becomes the norm.
- [ ] **12.6** Receipt capture — one photo per expense, reusing the media storage from 0.7. The owner will photograph the electricity bill on their phone; make that the fast path, not an afterthought.
- [ ] **12.7** Expense entry + list UI: filter by category, date range, paid/unpaid. Adding an expense should take well under a minute or it won't happen.
- [ ] **12.8** Unpaid bills view, driven by `paid_on IS NULL`.
- [ ] **12.9** **Monthly P&L** — revenue from `Payment` records (7.2) minus expenses, by month, broken down by category, with a fixed-vs-variable split. This is the report that justifies the phase.
- [ ] **12.10** Expense trend by category over time, to catch the month the electricity bill doubles.
- [ ] **12.11** CSV export by period for the accountant — same permission checks as 11.5.

**Cash basis, not accrual.** Record against `paid_on` — correct for a single shop and much simpler to reason about. `incurred_on` exists only so an unpaid bill still surfaces in 12.8. No GST input-credit tracking, since the shop isn't registered (C2).

## Phase 13 — Agentic access (MCP)

Expose the shop over the Model Context Protocol so the owner can ask "what's due today?", "which orders are unpaid?", or "how loaded is Ramesh this week?" from Claude or ChatGPT instead of a dashboard.

**One server serves both.** Claude (Desktop, claude.ai connectors, Claude Code) and ChatGPT (connectors / developer mode, and the OpenAI Responses API) both speak MCP. Build one remote server, not two integrations.

Depends on Phases 1, 4 and 7 — there needs to be data and a permission layer worth exposing.

- [ ] **13.1** Pick the implementation: FastMCP mounted into the existing `tailorly/asgi.py`, or `django-mcp-server`. Mounting into ASGI keeps one deployable, one settings module, and one auth stack.
- [ ] **13.2** **Reuse the Phase 1 permission layer — do not reimplement it.** Map the MCP session to a Django user and run every tool through the same staff-safe / admin querysets from 1.3. A second ORM path for MCP is exactly how the PII boundary drifts out of sync.
- [ ] **13.3** Transport: Streamable HTTP for the remote server (plain SSE is deprecated). stdio for local development only.
- [ ] **13.4** Auth, in two stages:
  - **Stage 1 — local.** stdio server on the admin's own machine, scoped to a read-only DB role or an API token. Works in Claude Desktop and Claude Code immediately, no OAuth. Get value here first.
  - **Stage 2 — remote.** OAuth 2.1 with PKCE, dynamic client registration, and a protected-resource-metadata document — what claude.ai connectors and ChatGPT require. `django-oauth-toolkit` covers most of it. **This is the bulk of the phase; budget accordingly.**
- [ ] **13.5** Read-only tools first:
  - `search_orders(status, due_before, customer_name, garment_type)`
  - `get_order(order_number)` — items, measurements, status history
  - `orders_due_today()` / `overdue_orders()`
  - `outstanding_dues()`
  - `tailor_workload(employee, date_range)`
  - `revenue_summary(period)`
- [ ] **13.6** ChatGPT compatibility: its connector surface expects `search` and `fetch` tools with a particular result shape. Add them as thin wrappers over 13.5 rather than redesigning the tool set around one client.
- [ ] **13.7** Expose the catalog as read-only MCP **Resources** — garment types, measurement field definitions, price list. Stable reference data the model pulls once instead of re-querying.
- [ ] **13.8** Write tools, only once read is solid and audited. Keep them narrow and strictly typed: `update_order_status(order_number, status)`, `record_payment(invoice, amount, method, reference)`. Each returns the resulting state so the agent can verify rather than assume.
- [ ] **13.9** **No free-text messaging tool.** Expose `send_ready_notification(order_number)`, which fires the approved template from 8.5 — never a generic `send_whatsapp(to, body)`. A free-text send tool converts any prompt injection into arbitrary messages to real customers, on the shop's number.
- [ ] **13.10** Audit every tool call: identity, tool, arguments, result, timestamp. An agent acting for the shop needs the traceability `OrderStatusLog` (4.5) gives humans.
- [ ] **13.11** Rate-limit and cap result sizes. An agent will cheerfully ask for every order ever placed.
- [ ] **13.12** Require confirmation for state-changing tools, and keep genuinely destructive operations (cancel, refund, delete) off MCP entirely at first.
- [ ] **13.13** Test against both Claude and ChatGPT. They differ on tool-name limits, schema strictness, and annotation support.

## Phase 14 — Optional / later

- [ ] **14.1** Fabric inventory: stock in meters, purchase records, low-stock alerts, auto-deduct on shop-cloth orders.
- [ ] **14.2** Barcode scanner support for job tickets.
- [ ] **14.3** Loyalty / discount schemes.
- [ ] **14.4** GST invoicing — only if the shop registers later (crossing the ₹20 lakh services threshold, or voluntarily). Would add GSTIN, SAC 998821, and a CGST/SGST split to `Invoice`. Not in scope now.
- [ ] **14.5** Payment gateway with real webhooks, if manual UPI reconciliation (7.5) becomes too much work.

## Phase 15 — Production readiness

- [ ] **15.1** Full `python manage.py check --deploy` pass: `DEBUG=False`, real `SECRET_KEY`, `ALLOWED_HOSTS`, HTTPS/HSTS settings, secure cookies.
- [ ] **15.2** Automated Postgres backups with a tested restore. A tailoring shop losing its measurement database is unrecoverable.
- [ ] **15.3** Error tracking (Sentry) and structured logging — **scrub phone numbers from error reports**, or a stack trace becomes a PII leak.
- [ ] **15.4** Deployment: Docker + gunicorn, or a PaaS. Include the Celery worker and beat scheduler.
- [ ] **15.5** CI running lint + tests on every push.
- [ ] **15.6** Rate-limit the public tracking and invoice endpoints.
- [ ] **15.7** Staff training notes / handover doc.

---

## Suggested app layout

```
tailorly/          project config
accounts/          custom User, Employee, groups, PII permission helpers
customers/         Customer (exists), MeasurementProfile
catalog/           GarmentType, MeasurementField, StyleOption, pricing
orders/            Order, OrderItem, status workflow, WorkAssignment, Trial, Alteration
billing/           Invoice, Payment, UPI link + QR generation
notifications/     WhatsApp adapter, templates, message log
mcp/               MCP server — tools, resources, OAuth, tool-call audit log
expenses/          ExpenseCategory, Expense, RecurringExpense, P&L
reports/           dashboards and exports
```

## Risks worth watching

1. **The PII boundary erodes.** Every new screen, export, admin registration, or MCP tool is a chance to leak a phone number. The adversarial permission tests in 1.4 are what keep this honest — write them early, not after the surfaces exist.
2. **Prompt injection through customer-supplied text.** Order notes, customer names, and fabric descriptions are all attacker-controllable and land directly in a model's context via MCP. Treat every tool result as untrusted data, never as instructions — that is the whole reason 13.9 exists.
3. **PII leaving your server for a model provider.** Any admin-scoped MCP tool can put customer phone numbers into Claude's or ChatGPT's context. Decide deliberately whether MCP tools return contact details at all; defaulting to the staff-safe view *even for admin* is the safer call and costs you almost nothing.
4. **Unlogged recurring expenses.** A P&L is only as honest as its inputs; if rent and electricity get entered sporadically the shop looks more profitable than it is. The draft-generation job in 12.3 is the mitigation — build it with the models, not later.
5. **Manual payment reconciliation** (7.5). A UPI link with no webhook means someone ticks off every payment by hand. Workable for one shop; if it starts slipping, 14.5 is the escape hatch.
6. **Measurement schema flexibility vs. queryability.** JSONField keyed by a `MeasurementField` catalog (3.2–3.3) is the recommended balance, but you can't easily do `WHERE chest > 40`. Acceptable for a single shop.
7. **WhatsApp template approval lead time** (8.4) can hold up the whole notification phase. Start it during Phase 4, not Phase 8.
8. **Snapshot-vs-reference on orders** (4.3). Getting this wrong corrupts history quietly, and you won't notice for months.
9. **Custom user model timing** (0.1). After real data exists, this stops being a migration and becomes manual SQL.
10. **Gapless invoice numbering** (7.1) under concurrency — needs a transaction with a row lock, not `max(id) + 1`.
