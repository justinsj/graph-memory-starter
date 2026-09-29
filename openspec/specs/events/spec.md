# events Specification

## Purpose
Every change, once, in order: by cursor, as a stream, and as signed webhooks.

## Requirements
### Requirement: Events in order
The service SHALL write each change's events in the same transaction as the change, and SHALL give them in order after a cursor, waiting for new ones when asked.

#### Scenario: Events come in order by cursor and type
- **WHEN** events are read after a cursor, and by type
- **THEN** they come in order, only of that type, and none twice

#### Scenario: A long poll returns as soon as something happens
- **WHEN** a client waits for events and a change happens half a second later
- **THEN** the answer comes at once with the new event

#### Scenario: The stream sends server sent events
- **WHEN** a client opens the event stream
- **THEN** it receives the events as server-sent events

### Requirement: Webhooks
The service SHALL deliver events to webhooks signed with their secret, in order, retrying until the receiver accepts, and MUST deliver none twice.

#### Scenario: Webhooks are signed and retried in order until delivered
- **WHEN** a receiver fails the first delivery and accepts the next round
- **THEN** both events arrive in order, signed, and nothing arrives twice
