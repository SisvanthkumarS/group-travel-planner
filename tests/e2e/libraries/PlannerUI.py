"""Reusable Robot keywords. Every browser operation runs through Robot Browser.

No HTTP client, API fixtures, database access, or browser fetch/evaluate scripts.
The 1 second pause is applied centrally, including assertion failures.
"""

import json
import math
import os
import random
import tempfile
import time
from datetime import datetime, timedelta
from pathlib import Path
from uuid import uuid4
from zoneinfo import ZoneInfo

from robot.api import logger
from robot.api.deco import keyword, library
from robot.api.types import Secret
from robot.errors import ExecutionFailed
from robot.libraries.BuiltIn import BuiltIn


@library(scope="GLOBAL", auto_keywords=False)
class PlannerUI:
    def __init__(self):
        self.bi = BuiltIn()
        self.people = {}
        self.identities = {}
        self.trip = None
        self.trips = []
        self.polls = {}
        self.current = None
        self.sequence = 0
        self.owner_suite = None
        self.shared_trips = {}
        self.form_data = None
        self.users_document = None
        self.run_id = uuid4().hex[:8]
        self.proposal_sequence = 0
        self.numbered = {}
        self.member2_name = f"e2e_u_{uuid4().hex[:10]}"
        self.pending_invitation_trips = set()

    def _load_scenario_data(self):
        project = Path(__file__).resolve().parents[1]
        for kind in ("trips", "proposals"):
            path = Path(
                str(
                    self._var(
                        kind.upper() + "_FILE", project / "results" / f"{kind}.json"
                    )
                )
            )
            path = path.expanduser().resolve()
            source = (
                path if path.exists() else project / "data" / f"{kind}.example.json"
            )
            try:
                document = json.loads(source.read_text(encoding="utf-8"))
                profiles = document[kind]
                if not isinstance(profiles, dict):
                    raise TypeError
                if kind == "trips":
                    for key in ("A", "B", "late_join", "expiry"):
                        profile = profiles[key]
                        for field in (
                            "name",
                            "destination",
                            "start_date",
                            "end_date",
                            "timezone",
                        ):
                            if (
                                not isinstance(profile[field], str)
                                or not profile[field]
                            ):
                                raise ValueError
                        ZoneInfo(profile["timezone"])
                        self._resolve_date(profile["start_date"])
                        self._resolve_date(profile["end_date"])
                else:
                    profile = profiles["default"]
                    for field in (
                        "title",
                        "location",
                        "description",
                        "start_time",
                        "end_time",
                    ):
                        if not isinstance(profile[field], str) or not profile[field]:
                            raise ValueError
                    datetime.strptime(profile["start_time"], "%H:%M")
                    datetime.strptime(profile["end_time"], "%H:%M")
                    if float(profile["cost"]) < 0:
                        raise ValueError
                    int(profile["day_offset"])
            except (OSError, ValueError, KeyError, TypeError) as error:
                raise AssertionError(
                    f"Invalid {kind} data: {source} ({type(error).__name__})"
                ) from None
            document["run_id"] = self.run_id
            document["created" if kind == "trips" else "prepared"] = []
            if kind == "trips":
                document["prepared"] = []
            setattr(self, kind + "_file", path)
            setattr(self, kind + "_document", document)
            self._write_json(path, document)

    def _resolve_date(self, value):
        if value == "today" or value.startswith(("today+", "today-")):
            return (
                datetime.now(self.zone).date() + timedelta(days=int(value[5:] or 0))
            ).isoformat()
        return datetime.fromisoformat(value).date().isoformat()

    def _trip_data(self, profile):
        data = self.trips_document["trips"][profile]
        self.zone = ZoneInfo(str(self._var("TRIP_TIMEZONE", data["timezone"])))
        self.sequence += 1
        trip = {
            "profile": profile,
            "name": data["name"].format(run_id=self.run_id, sequence=self.sequence),
            "destination": data["destination"],
            "start": self._resolve_date(data["start_date"]),
            "end": self._resolve_date(data["end_date"]),
            "timezone": self.zone.key,
            "joined": False,
        }
        self.trips_document["prepared"].append(trip)
        self._write_json(self.trips_file, self.trips_document)
        return trip

    def _record_trip(self):
        self.trips.append(self.trip)
        self.trips_document["created"].append(self.trip)
        self._write_json(self.trips_file, self.trips_document)

    def _record_proposal(self, data):
        records = self.proposals_document["prepared"]
        records[:] = [row for row in records if row["title"] != data["title"]]
        records.append(
            dict(
                data,
                trip_url=self.trip["url"],
                case=self.bi.get_variable_value("${TEST NAME}"),
            )
        )
        self._write_json(self.proposals_file, self.proposals_document)

    def _load_users(self):
        default = Path(__file__).resolve().parents[1] / "results" / "users.json"
        self.users_file = (
            Path(str(self._var("USERS_FILE", default))).expanduser().resolve()
        )
        if self.users_file.exists():
            try:
                document = json.loads(self.users_file.read_text(encoding="utf-8"))
                if not isinstance(document, dict) or not isinstance(
                    document.get("users"), list
                ):
                    raise TypeError
                if document.get("base_url", self.base) != self.base:
                    raise ValueError
                users = document["users"]
                if len(users) != 2 or {user["type"] for user in users} != {
                    "organizer",
                    "member",
                }:
                    raise ValueError
                for user in users:
                    if (
                        any(
                            not isinstance(user.get(key), str) or not user[key]
                            for key in ("username", "email", "password")
                        )
                        or len(user["password"]) < 8
                    ):
                        raise ValueError
                    if "registered" in user and not isinstance(
                        user["registered"], bool
                    ):
                        raise ValueError
                    user.setdefault(
                        "registered", True
                    )  # Handwritten existing accounts.
                    user.setdefault("id", 0)  # UI does not expose the backend user ID.
                if (
                    len({user["username"] for user in users}) != 2
                    or len({user["email"] for user in users}) != 2
                ):
                    raise ValueError
            except (OSError, ValueError, KeyError, TypeError):
                raise AssertionError(
                    f"Invalid users file or BASE_URL mismatch: {self.users_file}. "
                    "Check its two user records, or choose a different USERS_FILE."
                ) from None
        else:
            users = []
            for role, tag in (("organizer", "o"), ("member", "m")):
                name = f"e2e_{tag}_{uuid4().hex[:10]}"
                users.append(
                    {
                        "type": role,
                        "id": 0,
                        "username": name,
                        "email": name + "@example.com",
                        "password": self.password,
                        "registered": False,
                    }
                )
            document = {"base_url": self.base, "users": users}
        document.setdefault("base_url", self.base)
        self.users_document = document
        self._write_users()
        for user in users:
            self.identities[user["type"]] = {
                "name": user["username"],
                "email": user["email"],
                "password": user["password"],
                "registered": user["registered"],
            }
        logger.info(f"Shared credentials file: {self.users_file}")

    def _write_users(self):
        self._write_json(self.users_file, self.users_document)

    def _write_json(self, path, document):
        path.parent.mkdir(parents=True, exist_ok=True)
        # Atomic replacement keeps the previous file intact if writing fails.
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", dir=path.parent, delete=False
            ) as handle:
                temporary = Path(handle.name)
                json.dump(document, handle, ensure_ascii=False, indent=2)
                handle.write("\n")
            temporary.replace(path)  # NamedTemporaryFile uses owner-only permissions.
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)

    def _remember_shared_identity(self, role, person):
        if role not in ("organizer", "member"):
            return
        for user in self.users_document["users"]:
            if user["type"] == role:
                user.update(
                    username=person["name"],
                    email=person["email"],
                    password=person["password"],
                    registered=True,
                )
        self._write_users()
        self.identities[role] = {
            key: person[key] for key in ("name", "email", "password", "registered")
        }

    def _var(self, name, default):
        return self.bi.get_variable_value(
            "${" + name + "}", os.getenv("E2E_" + name, default)
        )

    def _bool(self, name, default=False):
        return self.bi.convert_to_boolean(self._var(name, default))

    def _ui(self, name, *args, **kwargs):
        """Keep Browser calls visible as nested keywords in Robot reports."""
        named = [f"{key}={value}" for key, value in kwargs.items()]
        try:
            return self.bi.run_keyword("Browser." + name, *args, *named)
        finally:
            self.bi.sleep("1s")

    def _button(self, name, root=""):
        selector = (
            'button[aria-label="Close"]'
            if name == "Close"
            else f'button:text-is("{name}")'
        )
        return f"{root} >> css={selector}" if root else f"css={selector}"

    def _click(self, name, root=""):
        self._ui("Click", self._button(name, root))

    def _label(self, label):
        return self._ui("Get Element By", "Label", label, exact=True)

    def _fill(self, label, value):
        self._ui("Fill Text", self._label(label), value)

    def _text(self, selector, text):
        return self._ui("Get Text", selector, "contains", str(text))

    def _count(self, selector, expected):
        self._ui("Get Element Count", selector, "==", expected)

    def _url(self, path):
        self._ui("Get Url", "==", self.base + path)

    def _go(self, path):
        self._ui("Go To", path if path.startswith("http") else self.base + path)

    def _reload(self):
        self._ui("Reload")

    def _new_person(self, role, password=None, identity=None):
        role_tag = {"organizer": "o", "member": "m", "registration": "r"}.get(role, "u")
        name = identity["name"] if identity else f"e2e_{role_tag}_{uuid4().hex[:10]}"
        context_args = {
            "ignoreHTTPSErrors": self.ignore_tls,
            "timezoneId": self.zone.key,
            "viewport": {"width": 1440, "height": 900},
        }
        if self.record:
            # Pass a real dictionary through a Robot variable, not a stringified dict.
            self.bi.set_suite_variable(
                "${UI_VIDEO_OPTIONS}", {"dir": str(self.output / "videos")}
            )
            context_args["recordVideo"] = "${UI_VIDEO_OPTIONS}"
        context = self._ui("New Context", **context_args)
        page = self._ui("New Page", self.base + "/sign-in")
        person = {
            "name": name,
            "email": identity["email"] if identity else name + "@example.com",
            "password": identity["password"] if identity else password or self.password,
            "context": context,
            "page": page,
            "registered": identity.get("registered", True) if identity else False,
        }
        self.people[role] = person
        self.current = role
        return person

    @keyword
    def start_ui_suite(self):
        if self.owner_suite is not None:
            logger.info("Suite data already initialized.")
            return
        self.__init__()
        self.owner_suite = self.bi.get_variable_value("${SUITE NAME}")
        self.base = str(self._var("BASE_URL", "https://localhost:3000")).rstrip("/")
        self.ignore_tls = self._bool("IGNORE_HTTPS_ERRORS")
        self.record = self._bool("RECORD_VIDEO")
        self.zone = ZoneInfo(str(self._var("TRIP_TIMEZONE", "America/New_York")))
        self.password = str(self._var("PASSWORD", "UiTravel123!"))
        if len(self.password) < 8:
            raise AssertionError("PASSWORD must have at least 8 characters.")
        self.window = int(self._var("POLL_WINDOW_SECONDS", 60))
        if self.window < 60:
            raise AssertionError(
                "POLL_WINDOW_SECONDS must be >= 60 for two voters and 1s pauses."
            )
        self.output = Path(str(self.bi.get_variable_value("${OUTPUT DIR}")))
        self._load_users()
        self._load_scenario_data()

    @keyword
    def start_ui_case(self):
        self._ui("Set Browser Timeout", str(self._var("TIMEOUT", "30s")))
        self._ui("Set Retry Assertions For", str(self._var("TIMEOUT", "30s")))
        self._ui("New Browser", "chromium", headless=self._bool("HEADLESS", True))

    @keyword
    def select_participant(self, role="organizer"):
        person = self.people[role]
        self._ui("Switch Context", person["context"])
        self._ui("Switch Page", person["page"])
        self.current = role

    def _ensure_login(self, role):
        if role not in self.people:
            person = self._new_person(role, identity=self.identities.get(role))
            if person["registered"]:
                self.sign_in_participant(role)
                return
        if not self.people[role]["registered"]:
            self.create_ui_account(role)
            return
        self.select_participant(role)
        self._go("/trips")
        url = self._ui("Get Url")
        if "/sign-in" in url:
            self.sign_in_participant(role)
        else:
            self._text("css=.app-header__name", self.people[role]["name"])

    @keyword
    def login(self, role="organizer"):
        """Reuse the participant's session, signing in only when required."""
        self._ensure_login(role)

    @keyword
    def prepare_participant_account(self, role):
        """Only register if a fixture needs an account that does not exist yet."""
        if not self.identities[role]["registered"]:
            self._ensure_login(role)
            self.sign_out_participant(role)

    @keyword
    def prepare_sign_in(self, role="organizer"):
        """Keep account preparation and sign-out in Setup, outside the login assertion flow."""
        if role not in self.people:
            person = self._new_person(role, identity=self.identities.get(role))
            if not person["registered"]:
                self.create_ui_account(role)
                self.sign_out_participant(role)
            else:
                self._url("/sign-in")
            return
        self.select_participant(role)
        self._go("/trips")
        if self._ui("Get Url") != self.base + "/sign-in":
            self.sign_out_participant(role)

    @keyword
    def create_ui_account(self, role):
        person = self.people[role]
        self._go("/")
        self._ui("Click", 'css=a:text-is("Create an account")')
        self._url("/register")
        self._fill("Username", person["name"])
        self._fill("Email", person["email"])
        self.bi.set_suite_variable(
            "${UI_INTERNAL_PASSWORD}", Secret(person["password"])
        )
        self._ui("Fill Secret", self._label("Password"), "${UI_INTERNAL_PASSWORD}")
        self._click("Create account")
        self._url("/trips")
        self._text("css=.app-header__name", person["name"])
        person["registered"] = True
        self._remember_shared_identity(role, person)

    @keyword
    def sign_in_participant(self, role="organizer", identifier="email", correct=True):
        self.select_participant(role)
        self._go("/")
        person = self.people[role]
        self._fill(
            "Email or username",
            person["name"] if identifier == "username" else person["email"],
        )
        secret = person["password"] if correct else person["password"] + "-wrong"
        self.bi.set_suite_variable("${UI_INTERNAL_PASSWORD}", Secret(secret))
        self._ui("Fill Secret", self._label("Password"), "${UI_INTERNAL_PASSWORD}")
        self._click("Sign in")
        if correct:
            self._text("css=.app-header__name", person["name"])
        else:
            self._text('css=[role="alert"]', "Incorrect")
            self._url("/sign-in")

    @keyword
    def sign_out_participant(self, role="organizer"):
        self.select_participant(role)
        self._click("Sign out")
        self._url("/sign-in")
        self._count("css=.app-header__name", 0)

    @keyword
    def prepare_shared_trip(self, join=True, profile="A"):
        """Reuse a trip with the required membership; create it only on first use."""
        join = self.bi.convert_to_boolean(join)
        cached = self.shared_trips.get(profile)
        if cached:
            self.trip = cached
            logger.info(f"Reusing trip: {self.trip['name']}")
        else:
            self._ensure_login("organizer")
            self.create_trip_through_ui(profile)
            self.shared_trips[profile] = self.trip
        self.joined = self.trip["joined"]
        if not join and self.joined:
            raise AssertionError(
                f"Member already joined Trip {profile}; choose an organizer-only profile."
            )
        if join and not self.joined:
            if self.trip["url"] not in self.pending_invitation_trips:
                self._ensure_login("organizer")
                self.invite_member_through_ui()
            self._ensure_login("member")
            self.respond_to_invitation("Accept")

    @keyword
    def prepare_new_trip(self, join=True, profile="late_join"):
        """Separate fixture for cases that permanently change membership or delete a trip."""
        join = self.bi.convert_to_boolean(join)
        self._ensure_login("organizer")
        self.create_trip_through_ui(profile)
        if join:
            self.invite_member_through_ui()
            self._ensure_login("member")
            self.respond_to_invitation("Accept")
        self.select_participant("organizer")
        self.open_trip()

    @keyword
    def create_trip_through_ui(self, profile="A"):
        self.joined = False
        self.select_participant("organizer")
        self._go("/trips")
        self.trip = self._trip_data(profile)
        self._click("New trip")
        self._fill_trip_form()
        self._click("Create trip")
        self._text("css=h1.trip-ticket__name", self.trip["name"])
        self.trip["url"] = self._ui("Get Url")
        self._record_trip()

    @keyword
    def remember_shared_trip(self):
        self.shared_trips[self.trip["profile"]] = self.trip

    @keyword
    def prepare_pending_invitation(self, profile="A"):
        self.prepare_shared_trip(False, profile)
        if self.trip["url"] not in self.pending_invitation_trips:
            self._ensure_login("organizer")
            self.invite_member_through_ui()

    def _fill_trip_form(self, end=None):
        self._fill("Trip name", self.trip["name"])
        self._fill("Destination", self.trip["destination"])
        self._fill("Start date", self.trip["start"])
        self._fill("End date", end or self.trip["end"])
        self._ui("Select Options By", self._label("Time zone"), "value", self.zone.key)

    @keyword
    def open_trip(self, section="proposals"):
        self.zone = ZoneInfo(self.trip["timezone"])
        suffix = "/itinerary" if section == "itinerary" else ""
        self._go(self.trip["url"] + suffix)
        self._text("css=h1.trip-ticket__name", self.trip["name"])
        self._ui(
            "Wait For Elements State",
            "css=.trip-body" if not suffix else "css=.itinerary",
            "visible",
        )

    @keyword
    def invite_member_through_ui(self):
        self.select_participant("organizer")
        self.open_trip()
        self.invite_member()

    @keyword
    def invite_member(self):
        """Send an invitation from the current organizer's open trip page."""
        if not self.identities["member"]["registered"]:
            self.prepare_participant_account("member")
            self.select_participant("organizer")
        self._click("Invite traveler")
        self._fill("Email or username", self.identities["member"]["email"])
        self._click("Send invite")
        self._text('css=dialog [role="status"]', self.identities["member"]["email"])
        self._click("Close", "css=dialog")
        self.pending_invitation_trips.add(self.trip["url"])

    def _invitation(self):
        return f"css=li.invite-row:has(.invite-row__title:text-is({json.dumps(self.trip['name'])}))"

    @keyword
    def open_invitations(self):
        """Open the current participant's invitation list."""
        self._go("/trips")

    @keyword
    def assert_pending_invitation(self):
        """Verify the invitation card without navigating or switching participants."""
        row = self._invitation()
        self._text(row, self.trip["name"])
        self._text(row, self.identities["organizer"]["name"])
        self._count(self._button("Accept", row), 1)
        self._count(self._button("Decline", row), 1)

    @keyword
    def assert_member_not_joined(self):
        """Verify the invitee is absent from the currently open trip's member list."""
        self._count(
            f'css=.member-list__name:text-is("{self.identities["member"]["name"]}")', 0
        )

    @keyword
    def respond_to_invitation(self, decision="Accept"):
        self.select_participant("member")
        self._go("/trips")
        self._text(self._invitation(), self.identities["organizer"]["name"])
        self._click(decision, self._invitation())
        self._count(self._invitation(), 0)
        self.pending_invitation_trips.discard(self.trip["url"])
        if decision == "Accept":
            self.joined = True
            self.trip["joined"] = True
            self._write_json(self.trips_file, self.trips_document)
            self.open_trip()
            self._text("css=.member-list", self.identities["member"]["name"])
        else:
            self._go(self.trip["url"])
            self._text("css=main", "not a member")

    def _proposal(self, title):
        return (
            f"css=article.proposal:has(h3:text-is({json.dumps(title, ensure_ascii=False)})), "
            f"li.history__row:has(.history__title:text-is({json.dumps(title, ensure_ascii=False)}))"
        )

    def _item(self, title):
        return f"css=article.activity:has(h3:text-is({json.dumps(title, ensure_ascii=False)}))"

    def _trip_card(self, name):
        return f"css=a.trip-card:has(.trip-card__name:text-is({json.dumps(name, ensure_ascii=False)}))"

    def _activity_data(self, title=None, hour=None, day=None):
        template = self.proposals_document["proposals"]["default"]
        self.proposal_sequence += 1
        start_time = datetime.strptime(template["start_time"], "%H:%M")
        end_time = datetime.strptime(template["end_time"], "%H:%M")
        duration = end_time - start_time
        if duration.total_seconds() <= 0:
            raise AssertionError("Proposal end_time must be later than start_time.")
        start = datetime.fromisoformat(self.trip["start"]).replace(
            hour=start_time.hour if hour is None else int(hour),
            minute=start_time.minute,
        ) + timedelta(days=int(template["day_offset"]) if day is None else int(day))
        return {
            "title": title
            or template["title"].format(
                run_id=self.run_id, sequence=self.proposal_sequence
            ),
            "location": template["location"],
            "description": template["description"],
            "cost": str(template["cost"]),
            "start": start.strftime("%Y-%m-%dT%H:%M"),
            "end": (start + duration).strftime("%Y-%m-%dT%H:%M"),
        }

    def _proposal_form(self, data):
        self._click("New proposal")
        for label, key in [
            ("Activity", "title"),
            ("Location", "location"),
            ("Starts", "start"),
            ("Ends", "end"),
            ("Estimated cost per person", "cost"),
            ("Why go?", "description"),
        ]:
            self._fill(label, data[key])

    @keyword
    def submit_activity_proposal(
        self, author="member", title=None, cost=None, hour=None, day=None
    ):
        self.select_participant(author)
        self.open_trip()
        data = self._activity_data(title, hour, day)
        if cost is not None:
            data["cost"] = str(cost)
        self._record_proposal(data)
        self._proposal_form(data)
        self._click("Submit proposal")
        self._text(self._proposal(data["title"]), "Pending")
        return data

    @keyword
    def assert_proposal_status(self, title, status):
        self._text(self._proposal(title), status)

    @keyword
    def open_activity_poll(self, title, minimum_seconds=None):
        """Perform this action on the current participant's open proposal page."""
        root = self._proposal(title)
        self._text(root, "Pending")
        # Compute only after navigation, authentication and proposal creation.
        seconds = int(minimum_seconds or self.window)
        deadline = math.ceil((time.time() + seconds) / 60) * 60
        self.polls[title] = deadline
        wall_time = datetime.fromtimestamp(deadline, self.zone).strftime(
            "%Y-%m-%dT%H:%M"
        )
        self._ui("Fill Text", root + ' >> css=input[type="datetime-local"]', wall_time)
        self._click("Open poll", root)
        self._text(root, "Voting open")
        self._text(root, f"0 of {2 if self.joined else 1} voted")
        logger.info(
            f"{title}: deadline={wall_time} {self.zone.key}; remaining={deadline - time.time():.1f}s"
        )
        return deadline

    @keyword
    def vote_as_participant(self, role, title, choice):
        if self.polls[title] - time.time() < 18:
            raise AssertionError(
                "Insufficient poll time for a UI vote; increase POLL_WINDOW_SECONDS."
            )
        self.select_participant(role)
        self.open_trip()
        self._text(self._proposal(title), "Voting open")
        if self.polls[title] - time.time() < 6:
            raise AssertionError(
                "Poll deadline is too close after navigation; increase the window."
            )
        self._click(choice.title(), self._proposal(title))
        selected = self._button(choice.title(), self._proposal(title))
        self._ui("Get Attribute", selected, "aria-pressed", "==", "true")

    @keyword
    def assert_vote_counts(self, title, yes, no, cast=None, eligible=2):
        root = self._proposal(title)
        self._text(root, f"YES {yes} · NO {no}")
        if cast is not None:
            self._text(root, f"{cast} of {eligible} voted")

    @keyword
    def wait_for_poll_outcome(self, title, outcome):
        self.select_participant("organizer")
        self.open_trip()
        # Bounded, deadline-relative assertion; no clock mutation or API shortcuts.
        timeout = max(1, self.polls[title] - time.time()) + 45
        self.bi.run_keyword("Set Log Level", "INFO")
        try:
            # Browser assertion polling is bounded by BOTH timeouts.
            self._ui("Set Browser Timeout", f"{timeout}s")
            self._ui("Set Retry Assertions For", f"{timeout}s")
            self._text(self._proposal(title), outcome)
        finally:
            self._ui("Set Retry Assertions For", str(self._var("TIMEOUT", "30s")))
            self._ui("Set Browser Timeout", str(self._var("TIMEOUT", "30s")))

    @keyword
    def resolve_tied_proposal(self, title, decision="Approve"):
        """Perform this action on the current participant's open proposal page."""
        self._text(self._proposal(title), "Tied")
        self._click(decision, self._proposal(title))
        self._text(
            self._proposal(title), "Approved" if decision == "Approve" else "Rejected"
        )

    @keyword
    def assert_itinerary_activity(self, title, present=True):
        self.open_trip("itinerary")
        self._count(self._item(title), 1 if self.bi.convert_to_boolean(present) else 0)
        if self.bi.convert_to_boolean(present):
            self._text(
                self._item(title),
                self.proposals_document["proposals"]["default"]["location"],
            )

    @keyword
    def withdraw_activity(self, title):
        """Perform this action on the current participant's open proposal page."""
        self._click("Withdraw", self._proposal(title))
        self._text(self._proposal(title), "Withdrawn")

    @keyword
    def cancel_activity(self, title):
        self.select_participant("organizer")
        self.open_trip("itinerary")
        self._click("Cancel activity", self._item(title))
        self._click("Cancel activity", "css=dialog")
        self._count(self._item(title), 0)

    @keyword
    def finish_ui_case(self):
        try:
            if self.bi.get_variable_value("${TEST STATUS}") == "FAIL":
                self.bi.run_keyword_and_ignore_error(
                    "Browser.Take Screenshot", "filename=failure-{index}"
                )
                self.bi.sleep("1s")
        finally:
            self._close_browsers()

    def _close_browsers(self):
        try:
            self._ui("Close Browser", "ALL")
        finally:
            self.people.clear()
            self.current = None
            self.form_data = None

    @keyword
    def finish_ui_suite(self):
        if self.bi.get_variable_value("${SUITE NAME}") != self.owner_suite:
            return
        cleanup_trips = [trip for trip in self.trips if not trip.get("deleted")]
        try:
            if cleanup_trips:
                self.start_ui_case()
                self._clean_up_trips(cleanup_trips)
        finally:
            self.owner_suite = None
            if cleanup_trips:
                self._close_browsers()

    def _clean_up_trips(self, cleanup_trips):
        failures = []
        try:
            self._ensure_login("organizer")
        except ExecutionFailed as error:
            logger.warn(
                f"Cannot restore organizer for UI cleanup: {type(error).__name__}"
            )
            logger.warn(
                "Trips needing manual cleanup: "
                + ", ".join(t["name"] for t in cleanup_trips)
            )
            return
        for trip in cleanup_trips:
            try:
                self._go(trip["url"])
                self._ui(
                    "Wait For Elements State",
                    "css=.trip-ticket__stub, main.page > .empty",
                    "visible",
                )
                if self._ui("Get Element Count", self._button("Delete trip")):
                    self._click("Delete trip")
                    self._click("Delete trip", "css=dialog")
                    self._url("/trips")
            except ExecutionFailed as error:
                failures.append(trip["name"])
                logger.warn(
                    f"UI cleanup failed for {trip['name']}: {type(error).__name__}"
                )
        if failures:
            logger.warn("Trips needing manual cleanup: " + ", ".join(failures))

    @keyword
    def reload_page(self):
        self._reload()

    @keyword
    def open_trip_list(self):
        self._go("/trips")

    @keyword
    def visit_trip_url(self, section="proposals"):
        self._go(self.trip["url"] + ("/itinerary" if section == "itinerary" else ""))

    @keyword
    def open_trip_from_list(self):
        self._ui("Click", self._trip_card(self.trip["name"]))

    @keyword
    def assert_current_page(self, path):
        self._url(path)

    @keyword
    def assert_signed_in(self, role="organizer"):
        self._text("css=.app-header__name", self.people[role]["name"])

    @keyword
    def assert_signed_out(self):
        self._url("/sign-in")
        self._count("css=.app-header__name", 0)
        self._count("css=.trip-ticket", 0)

    @keyword
    def assert_trip_control(self, control, present=True):
        self._count(
            self._button(control), 1 if self.bi.convert_to_boolean(present) else 0
        )

    @keyword
    def assert_trip_details(self):
        self._text("css=h1.trip-ticket__name", self.trip["name"])
        self._text("css=.trip-ticket", self.trip["destination"].upper())
        organizer = (
            "you"
            if self.current == "organizer"
            else self.identities["organizer"]["name"]
        )
        self._text("css=.trip-ticket__meta", f"Organized by {organizer}")
        self._count(f'css=.trip-ticket [title="{self.trip["timezone"]}"]', 1)
        for date in (self.trip["start"], self.trip["end"]):
            self._text(
                "css=.trip-ticket__dates",
                datetime.fromisoformat(date).strftime("%b %-d").upper(),
            )

    @keyword
    def assert_trip_members(self, count=2):
        self._count("css=.member-list__row", int(count))
        self._text("css=.member-list", self.identities["organizer"]["name"])
        self._text(
            f'css=.member-list__row:has-text("{self.identities["organizer"]["name"]}")',
            "Organizer",
        )
        if int(count) == 2:
            self._text("css=.member-list", self.identities["member"]["name"])

    @keyword
    def assert_trip_in_list(self, present=True):
        self._ui("Wait For Elements State", "css=.trip-grid, main .empty", "visible")
        self._count(
            self._trip_card(self.trip["name"]),
            1 if self.bi.convert_to_boolean(present) else 0,
        )

    @keyword
    def assert_trip_unavailable(self, reason="not a member"):
        self._text("css=main", reason)
        self._count("css=.trip-ticket", 0)
        self._count("css=.itinerary", 0)

    @keyword
    def new_registration_participant(self, password_length=8):
        length = int(password_length)
        password = ("Abcd1234XYZ9" * (length // 12 + 1))[:length]
        self._new_person("registration", password=password)

    @keyword
    def require_unregistered_participant(self, role):
        if self.identities[role]["registered"]:
            self.bi.skip(
                f"Skipping registration because users.json lists the shared {role} account as registered."
            )

    @keyword
    def prepare_registration_account(self, role):
        self.require_unregistered_participant(role)
        if role not in self.people:
            self._new_person(role, identity=self.identities[role])
        else:
            self.select_participant(role)

    @keyword
    def open_registration_from_sign_in(self):
        self._go("/")
        self._ui("Click", 'css=a:text-is("Create an account")')
        self._url("/register")

    @keyword
    def fill_shared_registration_form(
        self, role, email_from=None, password_length=None
    ):
        person = self.people[role]
        self._fill("Username", person["name"])
        self._fill(
            "Email",
            self.identities[email_from]["email"] if email_from else person["email"],
        )
        self.fill_shared_registration_password(role, password_length)

    @keyword
    def fill_shared_registration_password(self, role, password_length=None):
        password = self.people[role]["password"]
        if password_length is not None:
            password = password[: int(password_length)]
        self.bi.set_suite_variable("${UI_INTERNAL_PASSWORD}", Secret(password))
        self._ui("Fill Secret", self._label("Password"), "${UI_INTERNAL_PASSWORD}")

    @keyword
    def remember_shared_account(self, role):
        person = self.people[role]
        person["registered"] = True
        self._remember_shared_identity(role, person)

    @keyword
    def remember_registered_participant(self, role="organizer"):
        """Reuse this successful registration's credentials without retaining its test window."""
        person = self.people["registration"]
        person["registered"] = True
        if role not in self.people and not self.identities.get(role, {}).get(
            "registered", False
        ):
            self._remember_shared_identity(role, person)

    @keyword
    def open_registration_page(self):
        self._go("/register")

    @keyword
    def fill_registration_form(self, existing_email=False):
        person = self.people["registration"]
        self._fill("Username", person["name"])
        email = (
            self.identities["organizer"]["email"]
            if self.bi.convert_to_boolean(existing_email)
            else person["email"]
        )
        self._fill("Email", email)
        self.bi.set_suite_variable(
            "${UI_INTERNAL_PASSWORD}", Secret(person["password"])
        )
        self._ui("Fill Secret", self._label("Password"), "${UI_INTERNAL_PASSWORD}")

    @keyword
    def submit_registration_form(self):
        self._click("Create account")

    @keyword
    def assert_registration_error(self, kind):
        self._text(
            "css=.field__error, .form-error",
            "8" if kind == "short" else "Email is already registered",
        )
        self._url("/register")

    @keyword
    def open_new_trip_form(self):
        self._click("New trip")

    @keyword
    def enter_invalid_trip_dates(self):
        self.invalid_trip = self._trip_data("B")
        self.invalid_trip["end"] = (
            (datetime.fromisoformat(self.invalid_trip["start"]) - timedelta(days=1))
            .date()
            .isoformat()
        )
        self._write_json(self.trips_file, self.trips_document)
        current, self.trip = self.trip, self.invalid_trip
        try:
            self._fill_trip_form()
        finally:
            self.trip = current

    @keyword
    def assert_invalid_trip_not_created(self):
        self._count(self._trip_card(self.invalid_trip["name"]), 0)

    @keyword
    def submit_trip_form(self):
        self._click("Create trip")

    @keyword
    def assert_trip_date_error(self):
        self._text("css=dialog .field__error", "before")

    @keyword
    def close_dialog(self, button="Cancel"):
        self._click(button, "css=dialog")

    @keyword
    def open_invite_dialog(self):
        self._click("Invite traveler")

    @keyword
    def new_unregistered_email(self):
        return f"unknown_{uuid4().hex}@example.com"

    @keyword
    def enter_invitee(self, email):
        self._fill("Email or username", email)

    @keyword
    def send_invitation(self):
        self._click("Send invite")

    @keyword
    def assert_registration_required_for_invitee(self):
        self._text('css=dialog [role="alert"]', "register first")
        self._count("css=dialog .notice--ok", 0)

    @keyword
    def answer_invitation(self, decision):
        self._click(decision, self._invitation())
        self.joined = decision == "Accept"
        self.pending_invitation_trips.discard(self.trip["url"])
        self.trip["joined"] = self.joined
        self._write_json(self.trips_file, self.trips_document)

    @keyword
    def assert_invitation_removed(self):
        self._count(self._invitation(), 0)

    @keyword
    def new_proposal_data(self, invalid=None):
        data = self._activity_data()
        if invalid in ("title", "location", "start", "end", "cost", "description"):
            data[invalid] = ""
        elif invalid == "negative":
            data["cost"] = "-1"
        elif invalid == "past":
            data["start"] = (datetime.now(self.zone) - timedelta(days=1)).strftime(
                "%Y-%m-%dT%H:%M"
            )
        elif invalid == "before_trip":
            data["start"] = (
                datetime.fromisoformat(self.trip["start"]) - timedelta(days=1)
            ).strftime("%Y-%m-%dT10:00")
        elif invalid == "after_trip":
            data["end"] = (
                datetime.fromisoformat(self.trip["end"]) + timedelta(days=1)
            ).strftime("%Y-%m-%dT12:00")
        self._record_proposal(data)
        return data

    @keyword
    def open_proposal_form(self):
        self._click("New proposal")

    @keyword
    def fill_proposal_form(self, data, include_times=True):
        self.form_data = data
        fields = [
            ("Activity", "title"),
            ("Location", "location"),
            ("Estimated cost per person", "cost"),
            ("Why go?", "description"),
        ]
        if self.bi.convert_to_boolean(include_times):
            fields += [("Starts", "start"), ("Ends", "end")]
        for label, key in fields:
            self._fill(label, data[key])

    @keyword
    def submit_proposal_form(self):
        self._click("Submit proposal")

    @keyword
    def assert_proposal_form_error(self, invalid):
        messages = {
            "negative": "negative",
            "reversed": "after the start",
            "past": "future",
            "before_trip": "trip dates",
            "after_trip": "trip dates",
        }
        if invalid in messages:
            self._text("css=dialog .field__error", messages[invalid])
        else:
            label = {
                "title": "Activity",
                "location": "Location",
                "start": "Starts",
                "end": "Ends",
                "cost": "Estimated cost per person",
                "description": "Why go?",
            }[invalid]
            self._ui("Get Attribute", self._label(label), "aria-invalid", "==", "true")

    @keyword
    def assert_no_active_proposals(self):
        self._count("css=article.proposal", 0)

    @keyword
    def assert_proposal_fields(self, data, status="Pending"):
        for value in (
            data["title"],
            status,
            data["location"],
            data["description"],
            "$" + data["cost"],
            data["start"][-5:],
            data["end"][-5:],
        ):
            self._text(self._proposal(data["title"]), value)

    @keyword
    def assert_proposal_control(self, title, control, present=True):
        self._count(
            self._button(control, self._proposal(title)),
            1 if self.bi.convert_to_boolean(present) else 0,
        )

    @keyword
    def assert_proposal_text(self, title, text):
        self._text(self._proposal(title), text)

    @keyword
    def assert_poll_not_final(self, title):
        for status in ("Approved", "Rejected", "Tied"):
            self._count(self._proposal(title) + f' >> css=.chip:text-is("{status}")', 0)

    @keyword
    def assert_vote_selected(self, title, choice):
        self._ui(
            "Get Attribute",
            self._button(choice, self._proposal(title)),
            "aria-pressed",
            "==",
            "true",
        )

    @keyword
    def proposal_deadline(self, data, kind):
        deadline = (
            datetime.now(self.zone) - timedelta(hours=1)
            if kind == "past"
            else datetime.fromisoformat(data["start"])
        )
        if kind == "after_start":
            deadline += timedelta(minutes=1)
        return deadline.strftime("%Y-%m-%dT%H:%M")

    @keyword
    def enter_poll_deadline(self, title, deadline):
        self._ui(
            "Fill Text",
            self._proposal(title) + ' >> css=input[type="datetime-local"]',
            deadline,
        )

    @keyword
    def submit_poll_form(self, title):
        self._click("Open poll", self._proposal(title))

    @keyword
    def assert_deadline_error(self, title, kind):
        self._text(
            self._proposal(title) + ' >> css=[role="alert"]',
            "future" if kind == "past" else "before",
        )

    @keyword
    def create_trip_starting_today(self):
        self._ensure_login("organizer")
        self.create_trip_through_ui("expiry")

    @keyword
    def enter_near_future_activity_times(self):
        starts = math.ceil((time.time() + 25) / 60) * 60
        self._fill(
            "Starts",
            datetime.fromtimestamp(starts, self.zone).strftime("%Y-%m-%dT%H:%M"),
        )
        self._fill(
            "Ends",
            datetime.fromtimestamp(starts + 3600, self.zone).strftime("%Y-%m-%dT%H:%M"),
        )
        self.form_data["start"] = datetime.fromtimestamp(starts, self.zone).strftime(
            "%Y-%m-%dT%H:%M"
        )
        self.form_data["end"] = datetime.fromtimestamp(
            starts + 3600, self.zone
        ).strftime("%Y-%m-%dT%H:%M")
        self._record_proposal(self.form_data)
        return starts

    @keyword
    def wait_until_epoch(self, epoch):
        while time.time() <= float(epoch):
            self.bi.sleep(f"{min(1.5, float(epoch) - time.time() + 0.1)}s")

    @keyword
    def wait_until_poll_deadline(self, title):
        self.wait_until_epoch(self.polls[title])

    @keyword
    def assert_scheduled_activity(self, data):
        self._count(self._item(data["title"]), 1)
        self._text(self._item(data["title"]), data["location"])
        self._text(self._item(data["title"]), data["start"][-5:])
        self._text(self._item(data["title"]), data["end"][-5:])

    @keyword
    def assert_activity_not_scheduled(self, title):
        self._count(self._item(title), 0)

    @keyword
    def assert_itinerary_count(self, count):
        self._count("css=article.activity", int(count))

    @keyword
    def assert_empty_itinerary(self):
        self._text("css=.itinerary__summary", "0 activities")
        self._text("css=.itinerary__total", "$0")

    @keyword
    def assert_voting_preview(self):
        self._text("css=.activity-pending", "still being voted on")

    @keyword
    def assert_itinerary_order(self, *activities):
        elements = self._ui("Get Elements", "css=article.activity .activity__title")
        titles = [self._ui("Get Text", element) for element in elements]
        self.bi.should_be_equal(titles, [activity["title"] for activity in activities])

    @keyword
    def assert_total_votes_visible(self, title, total=2):
        self._ui(
            "Get Text",
            self._proposal(title),
            "matches",
            rf"(?is).*\b{int(total)}\s+(?:of\s+2\s+voted|votes?\s+cast|total\s+votes?).*",
            message="US-13 requires a visible total votes cast, not only Yes/No counts.",
        )

    @keyword
    def open_trip_deletion(self):
        self._click("Delete trip")

    @keyword
    def confirm_trip_deletion(self):
        self._click("Delete trip", "css=dialog")
        self._url("/trips")
        self.trip["deleted"] = True
        self._write_json(self.trips_file, self.trips_document)

    @keyword
    def keep_trip(self):
        self._click("Keep it", "css=dialog")

    @keyword
    def open_activity_cancellation(self, title):
        self._click("Cancel activity", self._item(title))

    @keyword
    def confirm_activity_cancellation(self):
        self._click("Cancel activity", "css=dialog")

    @keyword
    def assert_activity_cancellation_unavailable(self, title):
        self._count(self._button("Cancel activity", self._item(title)), 0)

    @keyword
    def prepare_member_two(self):
        identity = {
            "name": self.member2_name,
            "email": self.member2_name + "@example.com",
            "password": self.password,
            "registered": False,
        }
        self._new_person("member2", identity=identity)

    @keyword
    def enter_planned_invitee(self, role):
        email = (
            self.member2_name + "@example.com"
            if role == "member2"
            else self.identities[role]["email"]
        )
        self.enter_invitee(email)

    @keyword
    def assert_duplicate_invitation(self):
        self._text('css=dialog [role="alert"]', "already pending")

    @keyword
    def planned_proposal(self, number):
        if number not in self.numbered:
            self.numbered[number] = self._activity_data()
        return self.numbered[number]

    @keyword
    def submit_planned_proposal(self, number):
        data = self.planned_proposal(number)
        self._proposal_form(data)
        self._click("Submit proposal")
        self.assert_proposal_status(data["title"], "Pending")
        self._record_proposal(data)
        data["submitted"] = True
        return data["title"]

    @keyword
    def ensure_planned_proposal(self, number, author):
        data = self.planned_proposal(number)
        if not data.get("submitted"):
            self._ensure_login(author)
            self.open_trip()
            self.submit_planned_proposal(number)
        return data["title"]

    @keyword
    def attempt_invalid_proposal(self, number, invalid):
        data = self.planned_proposal(number).copy()
        self.open_proposal_form()
        if invalid == "missing":
            invalid = random.choice(
                ["title", "location", "start", "end", "cost", "description"]
            )
            logger.info(f"Leaving {invalid} empty")
            data[invalid] = ""
        elif invalid == "negative":
            data["cost"] = "-1"
        else:
            data["start"], data["end"] = data["end"], data["start"]
        self.fill_proposal_form(data)
        self.submit_proposal_form()
        self.assert_proposal_form_error(invalid)
        self.close_dialog()
        self.reload_page()
        self._text("css=.section-title:text-is('Active')", "Active")
        self._count(self._proposal(self.planned_proposal(number)["title"]), 0)

    @keyword
    def assert_planned_history(self, title, status):
        self._text('css=h2:text-is("Active")', "Active")
        self._count(f"css=article.proposal:has(h3:text-is({json.dumps(title)}))", 0)
        self._text(
            f"css=.history__row:has(.history__title:text-is({json.dumps(title)}))",
            status,
        )

    @keyword
    def poll_was_opened(self, title):
        return title in self.polls

    @keyword
    def view_joined_workspace(self):
        self._text("css=.tabs a[aria-current=page]", "Proposals")
        self._text("css=h2:text-is('Active')", "Active")
        self._ui("Click", 'css=.tabs a:has-text("Itinerary")')
        self._text("css=.tabs a[aria-current=page]", "Itinerary")
        self._ui("Wait For Elements State", "css=.itinerary", "visible")

    @keyword
    def verify_trips_heading(self):
        self._text("css=h1", "Your trips")
