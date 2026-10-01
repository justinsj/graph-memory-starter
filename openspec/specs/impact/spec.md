# impact Specification

## Purpose
Every project carries a thesis (if X is done, Y will change by potentially Z), where Z comes from numbers gathered from the workspace's documents and its people, never guessed; projects are then compared by projected impact per person-day of estimated effort.

## Requirements
### Requirement: A thesis resting on gathered numbers
The service SHALL research a thesis's numbers before a person approves it: a number SHALL be recorded as found only with the document sentence that states it, SHALL otherwise be asked of a person the graph knows, and MUST keep saying whether it was found, answered or estimated. The projected impact SHALL be the product of the thesis's numbers and SHALL read as still being researched until every one is in.

#### Scenario: A new project gets a draft thesis and its numbers researched
- **WHEN** an input proposes a new project
- **THEN** impact research opens a second change request beside it, before review, holding a draft thesis and a status for each number it needs, which applies only once the project exists

#### Scenario: A number found in a document is recorded with its sentence
- **WHEN** a document in the workspace states a number the thesis needs
- **THEN** the number is found, with the document and its sentence, and the build checks the sentence is in the document

#### Scenario: A number no document holds is asked of the person the project names
- **WHEN** no document states a number and the research is approved
- **THEN** the number is asked of the person who asked for the project, and a number.asked event carries the question

#### Scenario: The answer fills the number in and completes the thesis
- **WHEN** the person asked gives the number
- **THEN** the thesis states the projected impact, its working, and the clients it reaches

#### Scenario: An estimate stays marked as one
- **WHEN** a person gives a number as an estimate
- **THEN** the number and the projected impact both say it rests on an estimate

#### Scenario: Documents that disagree are not guessed between
- **WHEN** two documents state different values for the same number
- **THEN** the number is asked of a person, and the research names both documents

#### Scenario: A number not in its quote is refused
- **WHEN** a change records a number its quote does not state
- **THEN** the change request is refused

### Requirement: Priorities from projected impact and estimated effort
The service SHALL rank open projects by projected impact per person-day of estimated effort, within each unit of impact, or across units in money when the workspace prices each unit, and SHALL list apart, with what they lack, projects whose numbers or effort are still missing.

#### Scenario: A project missing numbers is not ranked
- **WHEN** a project's thesis still lacks a number
- **THEN** it is listed apart from the ranking, naming the numbers it lacks

#### Scenario: Projects are ranked by projected impact per person-day
- **WHEN** several projects have complete theses and estimated effort
- **THEN** they are ranked within each unit by impact per person-day, and the project list sorts the same way

#### Scenario: A value per unit ranks across units in money
- **WHEN** the workspace gives what one unit of each impact is worth
- **THEN** all complete projects are ranked in one list by money per person-day

#### Scenario: An approved number change updates the priority
- **WHEN** a person approves a new value for a number
- **THEN** the projected impact and the ranking change with it

### Requirement: Impact through every door
The service SHALL offer the thesis, research, answers, effort, impact and priorities over REST, and impact and priorities to agents over MCP.

#### Scenario: The impact calls work over HTTP
- **WHEN** a client proposes a thesis, answers a number, estimates effort and reads the impact over HTTP
- **THEN** each call answers as the service does, and the priorities list the project
