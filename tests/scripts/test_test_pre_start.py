from unittest.mock import MagicMock, patch

from app.tests_pre_start import init, logger


def test_init_successful_connection() -> None:
    engine_mock = MagicMock()

    session_mock = MagicMock()
    session_cm = MagicMock()
    session_cm.__enter__.return_value = session_mock
    session_cm.__exit__.return_value = None

    with (
        patch("app.tests_pre_start.Session", return_value=session_cm),
        patch.object(logger, "info"),
        patch.object(logger, "error"),
        patch.object(logger, "warn"),
    ):
        try:
            init(engine_mock)
            connection_successful = True
        except Exception:
            connection_successful = False

        assert connection_successful, (
            "The database connection should be successful and not raise an exception."
        )

        assert session_mock.exec.call_count == 1
