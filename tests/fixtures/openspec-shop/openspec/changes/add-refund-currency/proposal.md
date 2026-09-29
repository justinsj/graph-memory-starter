## Why
Customers pay in euros too, and the approval threshold only understands pounds.

## What Changes
- needs_approval takes the refund's currency
- every caller passes it

## Impact
- Affected specs: refunds
- Affected code: backend/refunds/rules.py and its callers
