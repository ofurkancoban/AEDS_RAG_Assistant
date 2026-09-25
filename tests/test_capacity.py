"""The limits, checked against the cohort they are meant to serve.

Roughly 50 students, who may open the assistant together at the start of one
lecture from a single campus address. These assertions exist so a future
tightening of the numbers fails here rather than in a lecture hall.
"""

from api import rate_limit

COHORT = 50


def test_a_whole_cohort_can_obtain_a_session_from_one_address():
    limiter = rate_limit.guest_limiter
    key = "campus-wifi"

    allowed = sum(1 for _ in range(COHORT) if limiter.check_and_record(key))

    # Being refused here means never getting a session at all, which is worse
    # than being throttled partway through a conversation.
    assert allowed == COHORT


def test_the_cohort_can_come_back_the_same_day():
    limiter = rate_limit.guest_limiter
    hourly, _ = limiter._rules[0]
    _, daily_window = limiter._rules[-1]
    daily = limiter._rules[-1][0]

    # A lab session and a lecture on the same day are two separate arrivals of
    # broadly the same people, each on fresh browsers or cleared storage.
    assert daily >= COHORT * 2
    assert hourly >= COHORT


def test_one_student_still_cannot_monopolise_the_pipeline():
    # get_chat_limiter() picks by the live provider - conftest.py pins
    # LLM_PROVIDER=ollama, so this is the ollama-tier numbers this test's
    # own reasoning is about.
    limiter = rate_limit.get_chat_limiter()
    hourly = limiter._rules[0][0]

    # Measured throughput on the answer pipeline is about 6.5 answers/minute,
    # so an hour of exclusive use is roughly 390 answers. One person's hourly
    # allowance must stay far below that or the limit protects nobody.
    assert hourly <= 60


def test_the_address_backstop_stays_near_what_the_hardware_can_serve():
    hourly = rate_limit.get_chat_ip_limiter()._rules[0][0]

    # Too low and a busy shared network is throttled below capacity; far above
    # capacity and the backstop stops bounding anything, since the queue would
    # absorb the excess instead.
    assert 250 <= hourly <= 600


def test_every_limiter_category_has_a_distinct_name():
    limiters = [
        rate_limit.submission_limiter,
        rate_limit.auth_limiter,
        rate_limit.guest_limiter,
        rate_limit.get_chat_limiter(),
        rate_limit.get_chat_ip_limiter(),
    ]
    names = [limiter.name for limiter in limiters]
    # Sharing a name would silently merge two limiters' windows in the table.
    assert len(names) == len(set(names))


def test_every_provider_has_chat_and_chat_ip_rules():
    """get_chat_limiter/get_chat_ip_limiter fall back to gemini's numbers for
    an unrecognised provider (see their docstrings) - this would silently
    hide a missing entry for a real provider name instead of erroring, so
    it's checked explicitly here."""
    from runtime_config import ALLOWED_LLM_PROVIDERS

    for provider in ALLOWED_LLM_PROVIDERS:
        assert provider in rate_limit._chat_limiters
        assert provider in rate_limit._chat_ip_limiters
