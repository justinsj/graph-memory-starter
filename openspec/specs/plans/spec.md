# plans Specification

## Purpose
How a deliverable gets made: a graph of tasks, general or imported from an OpenSpec change, approved by a person.

## Requirements
### Requirement: A plan that can run
The service SHALL refuse a plan whose tasks wait on each other in a circle, wait on tasks it does not have, repeat a key, or belong to a deliverable the project does not have.

#### Scenario: A plan that cannot run is refused with its reasons
- **WHEN** a plan has a circle, an unknown task to wait on, a repeated key, or no such deliverable
- **THEN** it is refused with 422 and each reason

### Requirement: OpenSpec changes as plans
The service SHALL turn an OpenSpec change folder into a plan: tasks.md in order, the spec deltas' scenarios as acceptance checks, and MUST refuse a change that breaks the format.

#### Scenario: An openspec change becomes a task graph
- **WHEN** a change folder with proposal, design, tasks and a spec delta is proposed as a plan
- **THEN** its tasks wait on each other in order and its scenario becomes an acceptance check

#### Scenario: Sections can run side by side within themselves
- **WHEN** parallel_sections is set
- **THEN** a section's tasks wait only on the section before

#### Scenario: An openspec change that breaks the format is refused
- **WHEN** a delta's requirement lacks SHALL and a scenario
- **THEN** the plan is refused with both reasons

### Requirement: Approval and change
The service SHALL mirror an approved plan's tasks into the project's steps, and SHALL hold only the tasks a proposed new version would change.

#### Scenario: An approved plan is mirrored into the projects steps
- **WHEN** a plan is approved
- **THEN** the record's plan is agreed with one step per task, quoting the approval note

#### Scenario: A new plan version holds only the tasks it changes
- **WHEN** a new version that changes one task is proposed while the old one runs
- **THEN** that task is held, the rest run, and on approval the execution moves to the new version keeping finished tasks
