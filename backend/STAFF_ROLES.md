# Staff role provisioning

After applying the application migrations in the target environment, run:

```powershell
python manage.py provision_staff_roles
```

The command creates or updates the six named role groups and adds their approved
permissions. It does not assign groups to users, modify existing memberships,
or grant superuser status. Re-running it is safe and preserves unrelated
permissions already attached to groups.

An existing Django superuser should sign in at `/django-admin/`, open **Users**,
and add the intended group to each staff account. The `Administrator` group has
the explicit account and group management permissions needed to manage later
assignments. Assign Django superuser status separately and only when full
framework-level administration is intentionally required. Do not assign the
Administrator group to an account merely to grant report or payment access.

Role membership does not change a user's `is_staff` flag. API staff roles must
be assigned only to accounts that are already authorized staff accounts.

The active React staff application reads the signed-in account's effective
permissions from `GET /api/auth/permissions/`. This read-only endpoint only
returns the authenticated user's own staff flag and permissions; the frontend
keeps that permission snapshot in memory and refreshes it after login or token
refresh. Frontend navigation is a usability aid only; API permission checks
remain authoritative.

The Store Manager role can cancel eligible orders, request refunds, and
reconcile legacy payment records. The Payment Reviewer role can review payment
attempts and confirm or reject refund requests; a refund requester cannot
confirm their own request. Inventory receiving and manual stock adjustments
remain limited to the Inventory Manager (and Administrator) role. Reports-only
staff receive no inventory, cancellation, reconciliation, or refund mutation
permissions.
