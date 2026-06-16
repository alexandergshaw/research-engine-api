from app.processing.keywords import extract_keywords


def test_extract_keywords_surfaces_multiword_terms():
    text = (
        "Public-key cryptography uses key pairs. Public-key cryptography secures "
        "communication. A key pair includes a public key and a private key."
    )
    keywords = extract_keywords(text, limit=5)
    assert keywords
    joined = " ".join(keywords).lower()
    assert "public-key cryptography" in joined or "key pair" in joined


def test_extract_keywords_handles_empty():
    assert extract_keywords("") == []
    assert extract_keywords(None) == []


def test_extract_keywords_respects_limit():
    text = "alpha beta. gamma delta. epsilon zeta. eta theta. iota kappa."
    assert len(extract_keywords(text, limit=2)) == 2
