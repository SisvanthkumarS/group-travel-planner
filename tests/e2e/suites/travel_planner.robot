*** Settings ***
Resource          ../resources/planner.resource
Suite Setup       Start UI Suite
Suite Teardown    Finish UI Suite
Test Setup        Start UI Case
Test Teardown     Finish UI Case

*** Test Cases ***
TC01 — The organizer registers with valid credentials
    Prepare Registration Account    organizer
    Register Shared User    organizer

TC02 — Member 1 registers after a duplicate email is rejected
    Prepare Participant Account    organizer
    Prepare Registration Account    member
    Open Registration From Sign In
    Fill Shared Registration Form    member    email_from=organizer
    Submit Registration Form
    Assert Registration Error    duplicate
    Complete Registration    member

TC03 — Registration rejects a seven-character password for Member 2
    Prepare Member Two
    Open Registration From Sign In
    Fill Shared Registration Form    member2    password_length=7
    Submit Registration Form
    Assert Registration Error    short

TC04 — The organizer signs in with an email address
    Sign In From Home    organizer    email

TC05 — The organizer signs in with a username
    Sign In From Home    organizer    username

TC06 — An incorrect password prevents sign-in
    Prepare Sign In    organizer
    Sign In Participant    organizer    email    ${False}
    Assert Signed Out

TC07 — The organizer signs out, signs back in, and creates Trip A
    Sign In From Home    organizer
    Sign Out Participant
    Reload Page
    Assert Signed Out
    Sign In From Home    organizer
    Create Trip Through UI    A
    Remember Shared Trip
    Assert Trip Details
    Assert Trip Members    1

TC08 — Trip B cannot end before its start date
    Sign In From Home    organizer
    Open New Trip Form
    Enter Invalid Trip Dates
    Submit Trip Form
    Assert Trip Date Error
    Assert Current Page    /trips
    Close Dialog
    Assert Invalid Trip Not Created

TC09 — The organizer invites Member 1 to Trip A
    Prepare Shared Trip    ${False}
    Sign In And Open Trip    organizer
    Invite Member
    Open Trips As    member
    Assert Pending Invitation

TC10 — Trip A rejects a duplicate invitation for Member 1
    Prepare Pending Invitation
    Sign In And Open Trip    organizer
    Open Invite Dialog
    Enter Planned Invitee    member
    Send Invitation
    Assert Duplicate Invitation
    Close Dialog    Close

TC11 — The organizer sees a registration prompt when inviting unregistered Member 2
    Prepare Shared Trip    ${False}
    Sign In And Open Trip    organizer
    Open Invite Dialog
    Enter Planned Invitee    member2
    Send Invitation
    Assert Registration Required For Invitee
    Close Dialog    Close

TC12 — Member 1 accepts the invitation to Trip A
    Prepare Pending Invitation
    Open Trips As    member
    Assert Pending Invitation
    Answer Invitation    Accept
    Open Trip From List
    View Joined Workspace

TC13 — Member 1 declines the invitation to Trip B
    Sign In From Home    organizer
    Create Trip Through UI    B
    Invite Member
    Open Trips As    member
    Answer Invitation    Decline
    Assert Invitation Removed
    Assert Trip In List    ${False}

TC14 — Member 1 submits Proposal 1
    Enter Shared Workspace    member
    ${title}=    Submit Planned Proposal    1
    ${data}=    Planned Proposal    1
    Assert Proposal Fields    ${data}
    Assert Proposal Text    ${title}    No poll yet
    Assert Proposal Control    ${title}    Yes    ${False}

TC15 — Proposal 2 cannot be submitted with a randomly selected required field left blank
    Enter Shared Workspace    member
    Attempt Invalid Proposal    2    missing

TC16 — Proposal 2 cannot be submitted with a negative estimated cost
    Enter Shared Workspace    member
    Attempt Invalid Proposal    2    negative

TC17 — Proposal 2 cannot be submitted with its start and end times reversed
    Enter Shared Workspace    member
    Attempt Invalid Proposal    2    reversed

TC18 — The organizer and Member 1 both vote Yes on Proposal 1
    Prepare Shared Trip
    ${title}=    Ensure Planned Proposal    1    member
    Sign In And Open Trip    organizer
    Open Poll And Vote    ${title}    Yes    Yes

TC19 — Proposal 2 rejects a poll deadline one hour in the past
    Enter Shared Workspace    organizer
    ${title}=    Submit Planned Proposal    2
    ${data}=    Planned Proposal    2
    ${deadline}=    Proposal Deadline    ${data}    past
    Enter Poll Deadline    ${title}    ${deadline}
    Submit Poll Form    ${title}
    Assert Deadline Error    ${title}    past
    Reload Page
    Assert Proposal Status    ${title}    Pending
    Assert Proposal Text    ${title}    No poll yet
    Assert Proposal Control    ${title}    Yes    ${False}

TC20 — Member 1 cannot open a poll for Proposal 2
    Prepare Shared Trip
    ${title}=    Ensure Planned Proposal    2    organizer
    Sign In And Open Trip    member
    Assert Proposal Text    ${title}    Waiting for the organizer to open voting.
    Assert Proposal Control    ${title}    Open poll    ${False}

TC21 — The organizer approves Proposal 2 after a tied vote
    Prepare Shared Trip
    ${title}=    Ensure Planned Proposal    2    organizer
    Sign In And Open Trip    organizer
    Vote And Resolve Tie    ${title}    Approve

TC22 — The organizer rejects Proposal 3 after a tied vote
    Enter Shared Workspace    organizer
    ${title}=    Submit Planned Proposal    3
    Vote And Resolve Tie    ${title}    Reject

TC23 — Both votes on Proposal 4 are No after Member 1 changes their vote
    Enter Shared Workspace    organizer
    ${title}=    Submit Planned Proposal    4
    Open Poll And Vote    ${title}    No    Yes
    Vote As Participant    member    ${title}    No
    Observe Closed Poll    ${title}    Rejected

TC24 — Member 1 verifies Trip A details and membership
    Enter Shared Workspace    member
    Assert Trip Details
    Assert Trip Members    2

TC25 — Member 1 verifies all four proposal outcomes and the approved itinerary
    Prepare Shared Trip
    Prepare History If Needed
    Sign In And Open Trip    member
    FOR    ${number}    ${status}    IN    1    Approved    2    Approved    3    Rejected    4    Rejected
        ${data}=    Planned Proposal    ${number}
        Assert Planned History    ${data}[title]    ${status}
    END
    FOR    ${number}    IN    1    2
        ${data}=    Planned Proposal    ${number}
        Assert Itinerary Activity    ${data}[title]
    END

TC26 — Trip A disappears from both users' trip lists after the organizer deletes it
    Enter Shared Workspace    organizer
    Open Trip Deletion
    Confirm Trip Deletion
    Reload Page
    Assert Trip In List    ${False}
    Open Trips As    member
    Assert Trip In List    ${False}

*** Keywords ***
Register Shared User
    [Arguments]    ${role}
    Open Registration From Sign In
    Complete Registration    ${role}

Complete Registration
    [Arguments]    ${role}
    Fill Shared Registration Form    ${role}
    Submit Registration Form
    Assert Current Page    /trips
    Assert Signed In    ${role}
    Remember Shared Account    ${role}

Sign In From Home
    [Arguments]    ${role}    ${identifier}=email
    Prepare Sign In    ${role}
    Sign In Participant    ${role}    ${identifier}
    Assert Current Page    /trips
    Assert Signed In    ${role}
    Verify Trips Heading

Open Trips As
    [Arguments]    ${role}
    Login    ${role}
    Verify Trips Heading

Sign In And Open Trip
    [Arguments]    ${role}
    Open Trips As    ${role}
    Open Trip From List

Enter Shared Workspace
    [Arguments]    ${role}
    Prepare Shared Trip
    Sign In And Open Trip    ${role}

Open Poll And Vote
    [Arguments]    ${title}    ${organizer_vote}    ${member_vote}
    Open Activity Poll    ${title}    120
    Vote As Participant    organizer    ${title}    ${organizer_vote}
    Sign In And Open Trip    member
    Vote As Participant    member    ${title}    ${member_vote}

Observe Closed Poll
    [Arguments]    ${title}    ${status}
    Select Participant    organizer
    Sleep    3 minutes
    Assert Proposal Status    ${title}    ${status}

Vote And Resolve Tie
    [Arguments]    ${title}    ${decision}
    Open Poll And Vote    ${title}    Yes    No
    Observe Closed Poll    ${title}    Tied
    Resolve Tied Proposal    ${title}    ${decision}

Prepare History If Needed
    FOR    ${number}    ${author}    IN    1    member    2    organizer    3    organizer    4    organizer
        ${title}=    Ensure Planned Proposal    ${number}    ${author}
        ${opened}=    Poll Was Opened    ${title}
        IF    ${opened}    CONTINUE
        Login    organizer
        Open Trip
        IF    $number == '1'
            Open Poll And Vote    ${title}    Yes    Yes
            Wait For Poll Outcome    ${title}    Approved
        ELSE IF    $number == '4'
            Open Poll And Vote    ${title}    No    No
            Wait For Poll Outcome    ${title}    Rejected
        ELSE
            ${decision}=    Set Variable If    $number == '2'    Approve    Reject
            Vote And Resolve Tie    ${title}    ${decision}
        END
    END
