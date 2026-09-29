# context Specification

## Purpose
Reading the graph: each workspace's graph is a projection of the log, and answers as the hook does.

## Requirements
### Requirement: The same answers as the hook
The service SHALL answer a question with exactly the facts in-process recall gives over the same files, and SHALL name each fact by its content.

#### Scenario: Document questions
- **WHEN** the recall questions are asked of a workspace holding the corpus
- **THEN** each answer is the in-process answer, apart from the extraction date

#### Scenario: Code questions
- **WHEN** the sixteen code questions are asked of a workspace holding the shop
- **THEN** each answer is the in-process answer

#### Scenario: Each fact names its claim by content
- **WHEN** context is asked for
- **THEN** each claim carries an id that finds the same claim

### Requirement: A projection of the log
The service SHALL rebuild a workspace's graph from the log alone, rewriting only the files that changed, and MUST never replace a graph file under a reader.

#### Scenario: Any sequence of changes gives the graph a full build gives
- **WHEN** files are added, changed, retracted and restored in a random order
- **THEN** after each step the graph equals a full build of the surviving files

#### Scenario: A new version rewrites only its own files
- **WHEN** one document gets a new version
- **THEN** only its text and its extraction are rewritten in the snapshot

#### Scenario: A claims id is the same in every build
- **WHEN** other files are added and the graph is rebuilt from nothing
- **THEN** the same claims have the same ids

#### Scenario: A graph file is never replaced under a reader
- **WHEN** the graph is rebuilt while a reader holds the old file
- **THEN** the reader can still read it

### Requirement: Clients
The service SHALL answer the Claude Code hook and MCP clients holding a key, and the hook MUST answer in-process when the service is down.

#### Scenario: The hook asks the service and falls back when it is down
- **WHEN** the hook runs with the service up, then down
- **THEN** it injects the service's answer, then the in-process one

#### Scenario: Mcp with an api key reads and proposes
- **WHEN** an MCP client holding an API key searches
- **THEN** it gets results, and a problem comes back as the tool's answer
