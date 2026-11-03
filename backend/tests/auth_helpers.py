from app.main import app


def auth_code(email: str, purpose: str) -> str:
    return app.state.test_auth_codes[(email.strip().casefold(), purpose)]


async def verify_registration(client, registration, email: str):
    body = registration if isinstance(registration, dict) else registration.json()
    assert body["status"] == "email_verification_required"
    response_text = getattr(registration, "text", body)
    response = await client.post(
        "/api/v1/auth/register/verify-email",
        json={
            "challenge_token": body["challenge_token"],
            "code": auth_code(email, "registration"),
        },
    )
    assert response.status_code == 200, f"{response.text}; registration={response_text}"
    return response


async def workspace_login(client, email: str, password: str, slug: str | None = None):
    response = await client.post(
        "/api/v1/auth/login",
        json={
            "email": email,
            "password": password,
            **({"organization_slug": slug} if slug else {}),
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    challenge_token = body["challenge_token"]
    if body["status"] == "workspace_selection_required":
        assert slug is not None, (
            "Select a workspace in the test when an identity has multiple memberships"
        )
        workspace = next(item for item in body["workspaces"] if item["organization_slug"] == slug)
        selected = await client.post(
            "/api/v1/auth/login/select-workspace",
            json={
                "challenge_token": challenge_token,
                "membership_id": workspace["membership_id"],
            },
        )
        assert selected.status_code == 200, selected.text
    verification = await client.post(
        "/api/v1/auth/login/verify-code",
        json={"challenge_token": challenge_token, "code": auth_code(email, "login")},
    )
    assert verification.status_code == 200, verification.text
    return verification.json()


async def verify_login_challenge(client, response, email: str):
    body = response.json()
    verification = await client.post(
        "/api/v1/auth/login/verify-code",
        json={
            "challenge_token": body["challenge_token"],
            "code": auth_code(email, "login"),
        },
    )
    assert verification.status_code == 200, verification.text
    return verification.json()


async def accept_invitation(client, response, email: str):
    assert response.status_code == 201, response.text
    return await verify_login_challenge(client, response, email)
