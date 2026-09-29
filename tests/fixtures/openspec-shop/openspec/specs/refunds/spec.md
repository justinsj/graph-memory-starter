# refunds Specification

## Purpose
How refunds are approved and paid.

## Requirements
### Requirement: Approval threshold
Refunds over £500 SHALL need approval before payment.

#### Scenario: Large refund needs approval
- **WHEN** a refund of £1,000 is requested
- **THEN** it needs approval

#### Scenario: Small refund needs no approval
- **WHEN** a refund of £10 is requested
- **THEN** it is paid without approval
