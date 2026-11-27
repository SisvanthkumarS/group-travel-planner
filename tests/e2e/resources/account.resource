*** Settings ***
Documentation       Reusable account registration and sign-out keywords.
Library             Browser

*** Keywords ***
Create Account
    [Documentation]    From /sign-in, register and verify the signed-in username.
    [Arguments]    ${username}    ${email}    ${password}
    Click    role=link[name="Create an account"]
    Sleep    1.5s
    Get Url    matches    /register$
    Sleep    1.5s
    Fill Text    css=input[name="user_name"]    ${username}
    Sleep    1.5s
    Fill Text    css=input[name="email"]    ${email}
    Sleep    1.5s
    Fill Secret    css=input[name="password"]    $password
    Sleep    1.5s
    ${create_account_button}=    Get Element By Role    button    name=Create account    exact=True
    Sleep    1.5s
    Click    ${create_account_button}
    Sleep    1.5s
    Get Url    matches    /trips$
    Sleep    1.5s
    Get Text    css=.app-header__name    ==    ${username}
    Sleep    1.5s
    Wait For Elements State    role=button[name="Sign out"]    visible
    Sleep    1.5s

Sign Out
    [Documentation]    Sign out and verify that the sign-in page is shown.
    ${sign_out_button}=    Get Element By Role    button    name=Sign out    exact=True
    Sleep    1.5s
    Click    ${sign_out_button}
    Sleep    1.5s
    Get Url    matches    /sign-in$
    Sleep    1.5s
    Wait For Elements State    role=link[name="Create an account"]    visible
    Sleep    1.5s
    Get Element Count    role=button[name="Sign out"]    ==    0
    Sleep    1.5s
