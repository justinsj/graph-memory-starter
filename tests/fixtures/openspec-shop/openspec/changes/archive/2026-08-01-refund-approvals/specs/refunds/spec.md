# Spec Delta

## ADDED Requirements
### Requirement: Approval threshold
Refunds over £250 SHALL need approval before payment.

#### Scenario: Large refund needs approval
- **WHEN** a refund of £1,000 is requested
- **THEN** it needs approval

#### Scenario: Small refund needs no approval
- **WHEN** a refund of £10 is requested
- **THEN** it is paid without approval

### Requirement: Refund window
Refunds SHALL be requested within 30 days of purchase.

#### Scenario: Late refund refused
- **WHEN** a refund is requested 31 days after purchase
- **THEN** it is refused
