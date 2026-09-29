# Spec Delta

## ADDED Requirements
### Requirement: Currency
Refund amounts SHALL be compared in pounds, converting other currencies first.

#### Scenario: Refund in euros
- **WHEN** a refund of €700 is requested
- **THEN** it is converted to pounds before the threshold is checked
