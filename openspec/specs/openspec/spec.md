# openspec Specification

## Purpose
OpenSpec as a source: requirements dated by their archived changes, and tests linked to the scenarios they name.

## Requirements
### Requirement: Specs as dated facts
The service SHALL read a repository's openspec folder into requirement and scenario facts, dated by the archived changes, and SHALL leave open changes out.

#### Scenario: The code zip is indexed and its specs read
- **WHEN** a repository with an openspec folder is sent as code
- **THEN** its functions, requirements and scenarios are in the graph

#### Scenario: A modified requirement ends the old claim the day its change was archived
- **WHEN** a requirement was added in one archived change and modified in another
- **THEN** the old text holds until the second change's date and the new text from it

#### Scenario: A removed requirement ends that day
- **WHEN** a requirement was removed in an archived change
- **THEN** its claim ends on that change's date

#### Scenario: Context answers as of a date
- **WHEN** the requirement is asked about as of August and as of October
- **THEN** each answer gives the text that held then

#### Scenario: An open change is not a fact
- **WHEN** a change is not yet archived
- **THEN** its requirements are not in the graph

#### Scenario: The parser checks the format
- **WHEN** a requirement lacks SHALL and a scenario
- **THEN** both problems are reported

### Requirement: Tests linked to scenarios
The service SHALL link a test whose name says a scenario's name to that scenario, and SHALL name the scenarios a code change puts at stake.

#### Scenario: A test that names a scenario verifies it
- **WHEN** a test is named after a scenario
- **THEN** the scenario lists the test and the code it calls

#### Scenario: A code change says which requirements are at stake
- **WHEN** code impact is asked for a function that tests call
- **THEN** it names the scenarios those tests verify
