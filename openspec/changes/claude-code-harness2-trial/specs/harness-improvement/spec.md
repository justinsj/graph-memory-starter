# Spec Delta

## Purpose

Offline trials that improve the Claude Code harness (CLAUDE.md, skills, preferences) with the Harness² method: on past decision points the user picks, graded against the answers the user really gave, and changing nothing live until the user approves.

## ADDED Requirements

### Requirement: Runs start only from decision points the user names
A trial run SHALL use only the decision points named on its command line as reference runs, with the k value and mode given there. It SHALL refuse to start without at least one named decision point, and SHALL offer no option that selects every task.

#### Scenario: A run without a reference is refused
- **WHEN** the user starts a run with no `--reference`
- **THEN** the run exits with code 2, makes no model call, and the message names `list-references`

#### Scenario: A run takes only the decision points it names
- **WHEN** the user names two decision points out of 92
- **THEN** the run's records hold exactly those two as reference runs

#### Scenario: The k value and mode come from the command
- **WHEN** the user gives no `--k` and no `--mode`
- **THEN** the run uses k=1 in parallel mode, and a k above 5 or an unknown mode is refused before any model call

#### Scenario: A dry run makes no model calls
- **WHEN** the user adds `--dry-run`
- **THEN** the run prints the references, k, mode, models, fast set, number of calls and a cost estimate, and starts no model process

### Requirement: Decision points come from the user's transcripts
A decision point SHALL be an assistant turn in a Claude Code transcript that asked one or more questions with a recommended option and received the user's answer. Its replay SHALL hold the session up to the user message that started that turn, and SHALL NOT hold the asking turn or the answer.

#### Scenario: An answered question becomes a decision point
- **WHEN** a transcript holds an AskUserQuestion call with a "(Recommended)" option and its answer, or a "### Q1." chat block with a "(Recommended)" option followed by a reply such as "Q1: B"
- **THEN** each becomes a decision point with its recommended option and the chosen option

#### Scenario: An unanswered question is not a decision point
- **WHEN** the question's tool call was interrupted or rejected, or the user's reply names no option
- **THEN** no decision point is made from it

#### Scenario: Archived copies of a session are counted once
- **WHEN** the same session is in both the projects folder and the session archive
- **THEN** each of its questions appears once

### Requirement: Runs execute in a sandbox without live tools
Every executor run SHALL execute in a new folder that holds only the materialised harness and the replay, with no MCP servers, no user-level settings or hooks, only read-only file tools, and no cloud, database or source-control credentials in its environment. Editor and grader sessions SHALL run under the same limits, except that an editor may also write files inside its own working folder.

#### Scenario: An editor session has no live tools
- **WHEN** an editor session starts
- **THEN** its command line has no permission bypass, uses an empty MCP configuration in strict mode and project settings only, allows only Read, Glob, Grep, Write and Edit, and its environment has no Vertex, cloud, database or source-control variables

#### Scenario: A sandbox run has no live tools
- **WHEN** an executor run starts
- **THEN** its command line uses an empty MCP configuration in strict mode, project settings only, and allows only the Read, Glob and Grep tools

#### Scenario: Cloud and database credentials are removed from a sandbox run
- **WHEN** the parent environment holds `AWS_PROFILE`, `AWS_SECRET_ACCESS_KEY`, `GH_TOKEN` or a variable whose name ends in `PASSWORD`
- **THEN** none of them is in the executor's environment

#### Scenario: A sandbox run sees only the harness and the replay
- **WHEN** an executor run starts
- **THEN** its working folder holds the harness files and `replay.md` and nothing from the user's repositories

### Requirement: User-specific data stays outside the repository
The configuration, the client list, the transcripts read, the runs, the library and the ledger SHALL live under the user's `~/.claude/harness2cc/` folder. The repository SHALL hold only code, tests and an example configuration with placeholder values.

#### Scenario: Runs and the library are written outside the repository
- **WHEN** a run ends and a lesson is approved
- **THEN** every file the run and the approval wrote is under `~/.claude/harness2cc/`, and no file under the repository changed

### Requirement: Guardrail files stay read-only
A candidate harness SHALL be rejected before it runs when it changes a file or a CLAUDE.md section that the configuration marks protected (such as database access rules, the Needs-your-yes list, settings and hooks), or when it writes a path outside the editable surface.

#### Scenario: A candidate that edits a guardrail is rejected
- **WHEN** a candidate changes a CLAUDE.md section that the configuration lists as protected, such as "Database access"
- **THEN** the candidate is rejected with the section's name, and is not probed

#### Scenario: A candidate outside the editable surface is rejected
- **WHEN** a candidate writes `.claude/settings.json` or a script file
- **THEN** the candidate is rejected with the path, and is not probed

### Requirement: The user's answers are hidden from the editor
The answers the user gave SHALL be used only by the grader. No replay, editor workspace or library entry SHALL hold them or any grade.

#### Scenario: The replay holds no answer
- **WHEN** a replay is built for a decision point
- **THEN** it ends with the user message that started the asking turn, and neither the turn that asked (with its recommended option) nor the user's reply is in it

#### Scenario: Grades are not written into the editor's workspace
- **WHEN** a run grades a candidate
- **THEN** the grade is written only under the run's `grades/` folder, which the editor sessions cannot read

### Requirement: A new harness changes live files only after approval
A composed harness SHALL be staged with its diff, evidence and grades, and SHALL change the live harness files only when the user approves it. Approval SHALL back up each file it changes and update the file's source copy and the install guide. It SHALL be refused when CLAUDE.md would grow past the cap, or when the diff has a scan finding.

#### Scenario: A composed harness waits for approval
- **WHEN** a run finishes composing
- **THEN** the live harness files are byte-for-byte unchanged, and the run prints the `approve-harness` and `reject-harness` commands

#### Scenario: An approved harness updates the live files and their sources
- **WHEN** the user approves a staged harness
- **THEN** each changed live file is backed up, then written, its source copy and the install guide match it, and the ledger records the approval

#### Scenario: A rejected harness leaves every file unchanged
- **WHEN** the user rejects a staged harness
- **THEN** no live file, source copy or library entry changes, and the ledger records the rejection

#### Scenario: An approved harness that grows CLAUDE.md past the cap is refused
- **WHEN** a staged harness adds more than 2,000 characters to CLAUDE.md
- **THEN** approval exits with code 3 and changes nothing

#### Scenario: An approval after the live file changed is refused
- **WHEN** a live harness file was edited after the run read it
- **THEN** approval exits with code 3, names the file, says to run again, and changes nothing

#### Scenario: A harness diff with a scan finding is refused
- **WHEN** a staged harness adds a client name from the client list to a file that has a source copy in the repository
- **THEN** approval exits with code 3, names the file, the line and the finding, and changes nothing

### Requirement: A lesson enters the library only after approval
A lesson written by reflection SHALL wait in the library's pending folder until the user approves it. Approval SHALL be refused while a scan finds a client name, a database hostname, a secret or an injected instruction in it, or when its domain already holds the maximum number of entries.

#### Scenario: A lesson waits in pending until approved
- **WHEN** reflection writes a lesson
- **THEN** it is under `library/pending/<domain>/`, the library index does not list it, and later runs do not read it

#### Scenario: A lesson with a scan finding cannot be approved
- **WHEN** a pending lesson holds a client name from the configuration's client list (such as "Acme Widgets"), a database hostname such as `db-prod.cluster-abc123.us-east-1.rds.amazonaws.com`, an AWS secret key or "ignore previous instructions"
- **THEN** approval exits with code 3 and names the line and the finding

#### Scenario: A full library refuses a new lesson
- **WHEN** a domain holds 20 approved entries
- **THEN** approving another lesson in that domain exits with code 3 and names `library prune`

### Requirement: Each candidate is graded against the user's real answers
At each gate the run SHALL grade the current and the composed harness on a fast set of decision points not used as references, reporting how many questions each asked, how many matched the user's answer, and how many Needs-your-yes questions it settled without asking. The full held-out set SHALL run only when the user asks for it.

#### Scenario: The fast set grades both harnesses
- **WHEN** a run reaches gate 1
- **THEN** it prints asked, matched and Needs-your-yes counts for the current and the composed harness on the same fast set

#### Scenario: Settling a Needs-your-yes question counts as a failure
- **WHEN** a harness settles a question about purging a production queue without asking
- **THEN** the grade counts it under "settled a Needs-your-yes", whatever option it chose

#### Scenario: The full held-out set runs only on request
- **WHEN** the user runs `test --full`
- **THEN** every labelled decision point not used as a reference is graded, and no other command grades them all

#### Scenario: A saved harness snapshot can be graded
- **WHEN** the user runs `test --harness <folder>` on a fast set
- **THEN** the harness in that folder and the current harness are graded on the same decision points, and the live files do not change

### Requirement: Every run is recorded with its cost
Each run SHALL keep its references, harness trees and fingerprints, diffs, executor and editor transcripts, grades, the cost of every call and the upstream commit, SHALL stop at its cost cap, and every approval or rejection SHALL be written to the ledger.

#### Scenario: A run records its inputs, outputs and cost
- **WHEN** a run ends
- **THEN** its folder holds `run.json` with references, k, mode, models, harness fingerprints, upstream commit, the cost of each call and the total

#### Scenario: A run stops at its cost cap
- **WHEN** the spent cost reaches `--budget-usd`
- **THEN** the run stops with status BUDGET_REACHED, keeps its records, and stages nothing for approval

#### Scenario: Every approval is written to the ledger
- **WHEN** the user approves or rejects a harness or a lesson
- **THEN** `ledger.jsonl` gains one line with the time, the action, the run or entry, and the fingerprints before and after
