# sources Specification

## Purpose
Files in: any set of files, deduplicated, extracted, and checked against their own text before they reach the graph.

## Requirements
### Requirement: Deduplication
The service SHALL recognise a file it already holds, whether by its bytes, its text, its identity or a near copy of its text, and SHALL keep one fact once however many files state it.

#### Scenario: The same file twice is unchanged
- **WHEN** a file is sent again with the same name and bytes
- **THEN** the answer is unchanged and no version is added

#### Scenario: The same text with other line endings is the same text
- **WHEN** a file differs only in line endings and a byte-order mark
- **THEN** it is recognised as the same text

#### Scenario: A renamed copy is another location of the same version
- **WHEN** the same text arrives under another name
- **THEN** it is recorded as another location of the version already held

#### Scenario: A new version replaces the old ones facts
- **WHEN** a document arrives again with new content
- **THEN** its new facts replace the old version's, which is kept as superseded

#### Scenario: A near copy is linked and left out
- **WHEN** a file is at least 90 percent the same as another document
- **THEN** it is linked to that document and left out of the graph

#### Scenario: A short file with a word changed is not a near copy
- **WHEN** a 66-word file has one word changed
- **THEN** it is a new document, since its similarity is under 90 percent

#### Scenario: A near copy can be sent to a person
- **WHEN** near copies are set to review
- **THEN** the copy is held and a change request asks a person

#### Scenario: The same fact from two files is one claim with two sources
- **WHEN** two files state the same fact
- **THEN** the graph holds one claim with both sources and their quotes

### Requirement: Checked extraction
The service SHALL accept a document's facts only when each quote is in the document's text and the graph still builds with them, and SHALL hold for a person a file that disagrees with the graph.

#### Scenario: An extraction that misquotes is refused
- **WHEN** an extraction quotes words the document does not contain
- **THEN** the version fails with the reasons

#### Scenario: Two files that disagree go to a person
- **WHEN** a new file states a threshold that overlaps another document's
- **THEN** it is held, and a change request offers to make it current and retract the other

#### Scenario: Without an extractor a document waits for its extraction
- **WHEN** no extractor is configured
- **THEN** the document waits until its extraction is sent, and is then checked and applied

### Requirement: Sync and retraction
The service SHALL tell a connector what to upload and what is gone, and SHALL retract and restore sources softly.

#### Scenario: A manifest says what to upload and what to retract
- **WHEN** a collection's full listing is sent
- **THEN** the answer lists new or changed files to upload and missing ones to retract

#### Scenario: Retracting a source takes its facts out and restoring brings them back
- **WHEN** a source is retracted and then restored
- **THEN** its facts leave the graph and come back

### Requirement: Inputs and limits
The service SHALL route transcripts to change requests that quote them, and SHALL refuse what it cannot read or store.

#### Scenario: A transcript becomes a change request quoting it
- **WHEN** a meeting transcript is sent with the changes it supports
- **THEN** a change request is opened, and once approved the record cites the transcript

#### Scenario: A pdf needs its text
- **WHEN** a PDF is sent without its text
- **THEN** it is refused with a reason

#### Scenario: The storage limit holds
- **WHEN** a file would pass the workspace's storage limit
- **THEN** it is refused with 429
