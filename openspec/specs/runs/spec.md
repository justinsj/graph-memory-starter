# runs Specification

## Purpose
An approved plan's tasks, carried out by any agent on any machine through one run protocol.

## Requirements
### Requirement: Leases and run tokens
The service SHALL lease a ready task only to a runner that offers what it needs, SHALL give the lease a run token whose expiry is the lease's and moves with every renewal, and SHALL return a task to ready when a lease nobody renews expires.

#### Scenario: The happy path
- **WHEN** a runner leases, reads its brief, hands in an artifact and completes each task
- **THEN** the tasks are done, the next one sees the upstream outputs, and the deliverable goes to a person for acceptance

#### Scenario: A runner without what the task needs is refused
- **WHEN** a runner does not offer what a task needs
- **THEN** the lease is refused with the missing needs

#### Scenario: A lease nobody renews expires and its token with it
- **WHEN** a lease passes its expiry without a renewal
- **THEN** the token stops working, the run is lost, and the task is ready again

#### Scenario: Renewals while the machine starts keep the token valid past its first lease
- **WHEN** the orchestrator renews while a machine takes three leases to start
- **THEN** the token injected at lease time still works

#### Scenario: The orchestrator runs a plan on machines that start slower than a lease
- **WHEN** real machines take longer to start than a lease lasts
- **THEN** every task succeeds and no lease is lost

### Requirement: Retries, limits and credentials
The service SHALL retry a failed task until its retries run out, SHALL limit runs at once per workspace, and MUST keep run tokens only as hashes and never store a platform's credentials.

#### Scenario: A failed attempt is retried until its retries run out
- **WHEN** a task fails more times than its retries allow
- **THEN** the task and the execution fail

#### Scenario: The workspace limits runs at once
- **WHEN** a lease would pass the workspace's limit on runs at once
- **THEN** it is refused with 429

#### Scenario: A run token works only for its own run
- **WHEN** a run token is used for another run or to lease
- **THEN** it is refused

#### Scenario: The token is kept only as a hash and never lands in an artifact
- **WHEN** an agent hands in text containing its own token
- **THEN** the stored artifact has it removed and the database never holds the token

### Requirement: The agent's side
The service SHALL let an agent ask a person, propose changes, and complete idempotently, and SHALL stop a task marked for a person until one accepts it.

#### Scenario: A question to a person pauses the lease
- **WHEN** an agent asks a question and a person answers later
- **THEN** the run waits without its lease expiring, and carries on with the answer

#### Scenario: An agent proposes and a person decides
- **WHEN** an agent proposes a change
- **THEN** a change request is opened with the run as proposer, which the run cannot approve

#### Scenario: A task marked for a person waits for one
- **WHEN** a gated task completes
- **THEN** it waits for a person, goes back to ready if rejected, and is done when accepted

#### Scenario: Completing twice with the same key gives the same answer
- **WHEN** complete is retried with the same idempotency key
- **THEN** the same answer comes back, and another key is refused

#### Scenario: An openspec deliverable is accepted with what to archive
- **WHEN** an OpenSpec plan's tasks are done and a person accepts the deliverable
- **THEN** the acceptance event names the change to archive

#### Scenario: An mcp agent works a task through the tools
- **WHEN** an MCP client holding only a run token calls get_brief, graph_context, attach and complete
- **THEN** the task is done
