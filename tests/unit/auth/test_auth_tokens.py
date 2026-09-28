"""Session tokens: randomness and the hashed-storage contract."""

from leadgen.auth import tokens


def test_tokens_are_url_safe_and_unique():
    generated = {tokens.generate_session_token() for _ in range(200)}

    assert len(generated) == 200
    assert all(len(token) >= 40 for token in generated)
    assert all(character.isalnum() or character in "-_" for token in generated for character in token)


def test_hash_is_deterministic_sha256_hex():
    token = tokens.generate_session_token()

    digest = tokens.hash_token(token)

    assert digest == tokens.hash_token(token)
    assert len(digest) == 64
    assert digest != token
    assert int(digest, 16) >= 0


def test_different_tokens_hash_differently():
    assert tokens.hash_token("a") != tokens.hash_token("b")
