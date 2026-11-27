# Group Travel Planner UI end-to-end tests

The Robot Framework suite runs 26 Chromium tests in order, from organizer registration in TC01 to trip deletion in TC26. It prepares test data and verifies outcomes through the same UI that travelers use. See the [test plan](../../ref/testcases.md) and the [executable suite](suites/travel_planner.robot).

## Run the tests

Start the application in a dedicated test environment with the backend poll scheduler running. From the repository root, install the test dependencies and Chromium once:

```sh
cd tests/e2e
uv sync --locked
uv run rfbrowser install chromium
```

Run the following commands from `tests/e2e`. This full run uses a fresh accounts file so both first-time registration cases execute. The local HTTPS example accepts the development server's self-signed certificate.

```sh
RUN_DIR="results/run-$(date +%Y%m%d-%H%M%S)"
uv run robot --outputdir "$RUN_DIR" \
  --variable "USERS_FILE:$RUN_DIR/users.json" \
  --variable BASE_URL:https://localhost:3000 \
  --variable IGNORE_HTTPS_ERRORS:True \
  suites
```

Open `report.html` in the output directory for the pass, fail, and skip counts. Open `log.html` to inspect individual steps and assertion failures.

To watch a single case, select its ID and run Chromium with a visible window. Quote the pattern so the shell passes it to Robot:

```sh
uv run robot --test 'TC15 *' --outputdir results/tc15 \
  --variable HEADLESS:False \
  --variable IGNORE_HTTPS_ERRORS:True \
  suites
```

To check test definitions and keyword arguments without opening the application:

```sh
uv run robot --dryrun --outputdir results/dryrun suites
```

## Case coverage

| ID | Behavior verified |
| --- | --- |
| TC01 | The organizer registers with valid credentials. |
| TC02 | Member 1 sees the duplicate-email error, corrects the email, and registers. |
| TC03 | Member 2's seven-character password fails validation. |
| TC04 | The organizer signs in with an email address. |
| TC05 | The organizer signs in with a username. |
| TC06 | An incorrect password leaves the organizer signed out. |
| TC07 | The organizer signs out, stays signed out after a refresh, signs back in, and creates Trip A. |
| TC08 | An end date before the start date prevents Trip B from being created. |
| TC09 | The organizer invites Member 1 to Trip A. Member 1 sees the pending invitation. |
| TC10 | A second invitation to Member 1 for Trip A shows a duplicate-invitation error. |
| TC11 | Inviting Member 2 by email shows that the recipient must register first. |
| TC12 | Member 1 accepts the Trip A invitation and opens Proposals and Itinerary. |
| TC13 | Member 1 declines the Trip B invitation. The invitation disappears and Trip B stays off the member's trip list. |
| TC14 | Member 1 submits Proposal 1 and verifies its fields, Pending status, and absence of an open poll. |
| TC15 | Proposal 2 fails validation when one randomly selected required field is empty. |
| TC16 | Proposal 2 fails validation when the estimated cost is negative. |
| TC17 | Proposal 2 fails validation when its start and end times are swapped. |
| TC18 | The organizer opens the poll for Proposal 1 and votes Yes. Member 1 then signs in and votes Yes. |
| TC19 | A poll deadline one hour in the past is rejected. Proposal 2 is still Pending after a refresh. |
| TC20 | Member 1 sees that Proposal 2 is waiting for the organizer and cannot open the poll. |
| TC21 | The organizer approves Proposal 2 after a tied vote. |
| TC22 | The organizer rejects Proposal 3 after a tied vote. |
| TC23 | Member 1 changes their vote from Yes to No. Proposal 4 is rejected with two No votes. |
| TC24 | Member 1 verifies Trip A's details, organizer, and two travelers. |
| TC25 | Member 1 verifies the four results in History and finds the two approved activities from Proposals 1 and 2 in the itinerary. |
| TC26 | The organizer deletes Trip A. Both travelers verify that it has disappeared from their trip lists. |

## Browser sessions and test data

- Each case opens a fresh Chromium browser and closes it at teardown, including after a failure or skip. Within a case, each participant has a separate browser context. A role signs in when its step requires it. For example, only the organizer signs in during TC11, even though the invitation uses Member 2's email.
- By default, the suite stores organizer and Member 1 credentials in `results/users.json`. TC01 or TC02 skips when its account is already marked as registered. Set `USERS_FILE` to an unused path to exercise registration again. Member 2 uses a fresh, unregistered identity shared by TC03 and TC11 within each run.
- The full suite reuses Trip A, its membership, and four proposals across cases. TC08 and TC13 use the Trip B profile. When running a case on its own, the suite uses the UI to create missing prerequisites with the roles needed for those actions. Trip and proposal defaults are in [trips.example.json](data/trips.example.json) and [proposals.example.json](data/proposals.example.json).
- Polls close in real time. TC21 through TC23 each return to the organizer's context and wait three minutes before checking the result. Together, those waits add nine minutes to a full run. Running TC25 on its own also requires time to create and settle the four polls.
