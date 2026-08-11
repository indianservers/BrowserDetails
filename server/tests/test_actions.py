import pytest

from app.services.actions import validate_action_parameters


def test_rejects_unbounded_latency_samples():
    with pytest.raises(ValueError):
        validate_action_parameters("MEASURE_WEBSOCKET_LATENCY", {"samples": 999})


def test_rejects_unexpected_parameters_for_empty_actions():
    with pytest.raises(ValueError):
        validate_action_parameters("REQUEST_RECONNECT", {"script": "alert(1)"})


def test_accepts_support_notification_message():
    assert validate_action_parameters("DISPLAY_SUPPORT_NOTIFICATION", {"message": "Support is available."}) == {
        "message": "Support is available."
    }


def test_accepts_support_username_prompt():
    result = validate_action_parameters("REQUEST_SUPPORT_USERNAME", {"prompt": "Please enter a display name."})
    assert result == {"prompt": "Please enter a display name."}


def test_accepts_support_message():
    result = validate_action_parameters("DISPLAY_SUPPORT_MESSAGE", {"title": "Support", "message": "Please check the highlighted section."})
    assert result["message"] == "Please check the highlighted section."


def test_accepts_https_support_image():
    result = validate_action_parameters("DISPLAY_SUPPORT_IMAGE", {"image_url": "https://example.com/help.png", "caption": "Example"})
    assert result["image_url"] == "https://example.com/help.png"


def test_rejects_non_file_image_url():
    with pytest.raises(ValueError):
        validate_action_parameters("DISPLAY_SUPPORT_IMAGE", {"image_url": "https://encrypted-tbn0.gstatic.com/images?q=abc"})


def test_rejects_javascript_image_url():
    with pytest.raises(ValueError):
        validate_action_parameters("DISPLAY_SUPPORT_IMAGE", {"image_url": "javascript:alert(1)"})


def test_accepts_support_iframe_params():
    result = validate_action_parameters("OPEN_APPROVED_SUPPORT_IFRAME", {"url": "https://example.com/support", "title": "Support"})
    assert result == {"url": "https://example.com/support", "title": "Support"}


def test_rejects_extra_iframe_params():
    with pytest.raises(ValueError):
        validate_action_parameters("OPEN_APPROVED_SUPPORT_IFRAME", {"url": "https://example.com/support", "script": "alert(1)"})


def test_accepts_support_banner_command():
    result = validate_action_parameters("SHOW_SUPPORT_BANNER", {"message": "Please look here.", "tone": "info"})
    assert result["message"] == "Please look here."


def test_accepts_highlight_selector_command():
    result = validate_action_parameters("HIGHLIGHT_PAGE_ELEMENT", {"selector": "#checkout-button", "label": "Click here"})
    assert result["selector"] == "#checkout-button"


def test_rejects_unsafe_selector_command():
    with pytest.raises(ValueError):
        validate_action_parameters("SCROLL_TO_PAGE_ELEMENT", {"selector": "input[type=password]"})
