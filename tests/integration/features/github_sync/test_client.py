"""FEA-0008: the GitHub client, against a local test double of the GitHub API."""

import ssl

import httpx
import pytest

from issuedeck.core.errors import GitHubError
from issuedeck.features.github_sync.client import GitHubClient, git_blob_sha, tls_context

from .fake_github import TOKEN, FakeGitHub


def _client(fake, *, token=TOKEN, transport=None, sleep=None, max_wait=30.0):
    kwargs = {"transport": transport or fake.transport, "max_wait": max_wait}
    if sleep:
        kwargs["sleep"] = sleep
    return GitHubClient(token, fake.owner, fake.repo, **kwargs)


async def test_repository_reports_privacy_and_write_access():
    fake = FakeGitHub(private=True, can_push=True)
    async with _client(fake) as client:
        info = await client.repository()
    assert (info.private, info.can_push, info.default_branch) == (True, True, "main")


async def test_the_token_travels_only_in_the_authorization_header():
    fake = FakeGitHub()
    async with _client(fake) as client:
        await client.repository()
        blob = await client.create_blob(b"hello")
        await client.blob(blob)
    for call in fake.requests:
        assert call["headers"]["authorization"] == f"Bearer {TOKEN}"
        assert TOKEN not in call["url"]
        assert TOKEN not in str(call["body"])


async def test_an_invalid_token_is_reported_without_echoing_it():
    fake = FakeGitHub()
    wrong = "ghp_wrong_token_value"
    async with _client(fake, token=wrong) as client:
        with pytest.raises(GitHubError) as caught:
            await client.repository()
    assert caught.value.kind == "auth"
    message = caught.value.message
    assert wrong not in message and "invalid, expired or revoked" in message


async def test_a_missing_repository_or_branch_is_not_found():
    fake = FakeGitHub()
    async with _client(fake) as client:
        with pytest.raises(GitHubError) as caught:
            await client.commit("no-such-branch", what="branch 'no-such-branch'")
    assert caught.value.kind == "not_found"
    assert "branch 'no-such-branch'" in caught.value.message

    other = GitHubClient(TOKEN, "octo", "missing", transport=fake.transport)
    async with other:
        with pytest.raises(GitHubError) as caught:
            await other.repository()
    assert caught.value.kind == "not_found" and "octo/missing" in caught.value.message


async def test_a_token_without_write_access_is_refused_with_a_clear_message():
    fake = FakeGitHub(can_push=False)
    async with _client(fake) as client:
        info = await client.repository()
        assert info.can_push is False
        with pytest.raises(GitHubError) as caught:
            await client.create_blob(b"x")
    message = caught.value.message
    assert caught.value.kind == "permission"
    assert "Resource not accessible by personal access token" in message
    assert "contents=write" in message and "Contents: Read and write" in message


async def test_a_short_rate_limit_is_waited_out_once():
    fake = FakeGitHub()
    fake.queue(429, headers={"retry-after": "2"}, body={"message": "slow down"})
    waited: list[float] = []

    async def fake_sleep(seconds):
        waited.append(seconds)

    async with _client(fake, sleep=fake_sleep) as client:
        info = await client.repository()
    assert info.private is True and waited == [2.0]


async def test_a_long_rate_limit_stops_with_the_reset_time():
    fake = FakeGitHub()
    fake.queue(403, headers={"x-ratelimit-remaining": "0", "x-ratelimit-reset": "4102444800"},
               body={"message": "API rate limit exceeded"})
    async with _client(fake, max_wait=5.0) as client:
        with pytest.raises(GitHubError) as caught:
            await client.repository()
    assert caught.value.kind == "rate_limit"
    assert "rate limit is reached" in caught.value.message and "UTC" in caught.value.message


async def test_network_failures_are_reported_without_internals():
    def broken(request):
        raise httpx.ConnectError(f"cannot connect with {TOKEN}")

    async with _client(FakeGitHub(), transport=httpx.MockTransport(broken)) as client:
        with pytest.raises(GitHubError) as caught:
            await client.repository()
    assert caught.value.kind == "network"
    assert TOKEN not in caught.value.message and "ConnectError" in caught.value.message


async def test_a_token_echoed_by_github_is_scrubbed_from_the_error():
    fake = FakeGitHub()
    fake.queue(422, body={"message": f"Validation failed for {TOKEN}"}, match="/git/blobs")
    async with _client(fake) as client:
        with pytest.raises(GitHubError) as caught:
            await client.create_blob(b"x")
    assert TOKEN not in caught.value.message and "***" in caught.value.message


async def test_several_files_become_one_commit():
    fake = FakeGitHub()
    async with _client(fake) as client:
        head = await client.commit("main")
        blobs = {path: await client.create_blob(data) for path, data in
                 {"p/a.json": b"[1]", "p/b.toml": b'key = "p"'}.items()}
        tree = await client.create_tree(head.tree_sha, blobs)
        commit = await client.create_commit(
            message="export p", tree_sha=tree, parent_sha=head.sha,
            author_name="Tester", author_email="tester@example.com",
        )
        await client.move_branch("main", commit)
    files = fake.files()
    assert files["p/a.json"] == b"[1]" and files["p/b.toml"] == b'key = "p"'
    assert files["README.md"] == b"exports\n"  # what was there is kept
    assert len(fake.history()) == 2
    assert fake.commits[commit]["author"]["name"] == "Tester"


async def test_the_branch_is_never_forced_when_it_moved_meanwhile():
    fake = FakeGitHub()
    async with _client(fake) as client:
        head = await client.commit("main")
        tree = await client.create_tree(head.tree_sha, {"p/a.json": await client.create_blob(b"1")})
        commit = await client.create_commit(
            message="export", tree_sha=tree, parent_sha=head.sha,
            author_name="T", author_email="t@example.com",
        )
        fake.commit_files({"other.txt": b"someone else"}, "pushed meanwhile")
        with pytest.raises(GitHubError) as caught:
            await client.move_branch("main", commit)
    assert caught.value.kind == "conflict" and "run the export again" in caught.value.message
    assert "p/a.json" not in fake.files()
    assert fake.calls("PATCH")[0]["body"]["force"] is False


def test_the_blob_hash_matches_git():
    # git hash-object of "hello\n"
    assert git_blob_sha(b"hello\n") == "ce013625030ba8dba906f756967f9e9ca394464a"


def test_tls_is_verified_against_the_system_certificate_store():
    context = tls_context()
    assert context.verify_mode == ssl.CERT_REQUIRED and context.check_hostname is True
