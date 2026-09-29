# review Specification

## Purpose
Every edit, from anyone, applied only when a person approves it.

## Requirements
### Requirement: People approve every edit
The service SHALL apply a change request only when a person with the approver role approves it; by default one approval is enough and a proposer MAY approve their own request.

#### Scenario: Nothing applies until a person approves
- **WHEN** a service account proposes a project
- **THEN** the project is not listed until a person approves

#### Scenario: A proposer may approve their own request and one approval is enough
- **WHEN** an approver proposes and approves their own request
- **THEN** it is applied with one recorded approval

#### Scenario: Approve true proposes and approves in one call and records both
- **WHEN** an approver sends a write with approve=true
- **THEN** it is applied at once, and the proposal and the approval are both recorded

#### Scenario: The workspace can turn self approval off
- **WHEN** self approval is off
- **THEN** a proposer cannot approve their own request but another approver can

#### Scenario: Service accounts editors and runs never approve
- **WHEN** a service account, an editor or a run tries to approve
- **THEN** it is refused, and a service account cannot be given the approve scope

### Requirement: Checked when opened and when approved
The service SHALL check a change request against the rules when it is opened and again when it is approved.

#### Scenario: A move the rules forbid is refused before anyone is asked
- **WHEN** an edit moves a project from proposed to active
- **THEN** it is refused with 422 and the reason, and nothing is opened

#### Scenario: A dry run shows the diff and opens nothing
- **WHEN** operations are sent with dry_run=true
- **THEN** the diff and problems come back and no change request exists

#### Scenario: A request another approval made stale is caught
- **WHEN** another approved request made one no longer apply
- **THEN** approving it answers 409 and marks it stale until it is brought up to date

#### Scenario: If match refuses an edit based on an old version
- **WHEN** an edit sends an If-Match that is not the project's version
- **THEN** it answers 409 with the current version

### Requirement: Partial and edited decisions
The service SHALL let a person approve some operations or edited values, or reject with a reason, and SHALL record each decision.

#### Scenario: Approving some operations
- **WHEN** a person approves operations 1 and 3 of three
- **THEN** only those apply and the second is marked skipped

#### Scenario: Approving an edited version records the edit
- **WHEN** a person edits a value while approving
- **THEN** the edited value applies and the request document records the edit

#### Scenario: A rejection keeps its reason
- **WHEN** a person rejects a request with a note
- **THEN** the note is kept and the request cannot be approved later

### Requirement: History and soft delete
The service SHALL keep every decision in the project's history and SHALL delete projects softly.

#### Scenario: Soft delete leaves recall and the list and restore brings it back
- **WHEN** a project is deleted and then restored
- **THEN** it leaves recall and the list, and comes back

#### Scenario: Every decision is in the projects history
- **WHEN** a status change is approved
- **THEN** the history shows it with the approver and the request it quotes

### Requirement: The change-set engine
The service MUST apply project changes through projects/model.py, with the same results as its cases.

#### Scenario: Each case as a change request
- **WHEN** each project case is applied as a change request
- **THEN** the records are what the case expects and every quote is in its file
