import unittest
from types import SimpleNamespace
from unittest.mock import Mock
from unittest.mock import patch

from lib.api import APIClient, APIError


class ResetTests(unittest.TestCase):
    def test_direct_usage_enriches_available_resets_from_app_server(self):
        client = APIClient()
        usage = {"rate_limit_reset_credits": {"available_count": 2}}
        details = {"availableCount": 2, "credits": [
            {"id": "credit-1", "status": "available", "grantedAt": "2026-06-01T00:00:00Z", "expiresAt": "2026-07-01T00:00:00Z"}
        ]}
        with patch.object(client, "_fetch_wham_usage", return_value=usage), patch.object(client, "_read_reset_credits", return_value=details):
            result = client.fetch_all()
        self.assertEqual(result["reset_credits"]["availableCount"], 2)
        self.assertEqual(result["reset_credits"]["credits"][0]["id"], "credit-1")

    def test_details_failure_preserves_usage_count_without_redeemable_rows(self):
        client = APIClient()
        usage = {"rate_limit_reset_credits": {"available_count": 2}}
        with patch.object(client, "_fetch_wham_usage", return_value=usage), patch.object(client, "_read_reset_credits", side_effect=APIError("offline")):
            result = client.fetch_all()
        self.assertEqual(result["reset_credits"], {"availableCount": 2, "credits": []})

    def test_cli_fallback_reads_top_level_reset_credits(self):
        client = APIClient()
        reset = {"availableCount": 1, "credits": [{"id": "credit-1", "status": "available"}]}
        with patch("lib.api.CodexRpc") as rpc:
            rpc.return_value.__enter__.return_value.request.side_effect = [
                {"account": {"type": "chatgpt"}},
                {"rateLimits": {"planType": "plus"}, "rateLimitResetCredits": reset},
            ]
            result = client._fetch_cli_rpc()
        self.assertEqual(result["reset_credits"], reset)

    def test_consumption_sends_selected_credit_with_idempotency_key(self):
        client = APIClient()
        with patch("lib.api.CodexRpc") as rpc, patch("lib.api.uuid.uuid4", return_value="request-1"):
            rpc.return_value.__enter__.return_value.request.return_value = {"code": "reset", "windowsReset": 2}
            result = client.consume_reset("credit-1")
        self.assertEqual(result["code"], "reset")
        rpc.return_value.__enter__.return_value.request.assert_called_once_with(
            "account/rateLimitResetCredit/consume",
            {"idempotencyKey": "request-1", "creditId": "credit-1"}, timeout=30,
        )

    def test_menu_shows_each_available_reset_with_award_and_expiry(self):
        from lib.indicator import CodexApp

        app = SimpleNamespace()
        app._mi = {key: Mock() for key in ("header", "account", "primary", "primary_reset", "secondary", "secondary_reset", "status", "resets")}
        app._reset_menu = Mock()
        app._set_window_labels = Mock()
        app._reset_menu.get_children.return_value = []
        app._update_menu = CodexApp._update_menu.__get__(app)
        app._on_redeem_reset = Mock()
        with patch("lib.indicator.Gtk.MenuItem") as menu_item:
            app._update_menu({
            "plan_type": "plus", "email": "", "account_type": "chatgpt", "primary": None, "secondary": None,
            "ts": __import__("datetime").datetime(2026, 9, 24, 12, 0),
            "reset_credits": {"availableCount": 1, "credits": [{"id": "credit-1", "status": "available", "title": "Full reset", "grantedAt": 1788264000, "expiresAt": 1790856000}]},
        })
        self.assertIn("1 available", app._mi["resets"].set_label.call_args.args[0])
        label = menu_item.call_args.kwargs["label"]
        self.assertIn("Sep", label)
        self.assertIn("Oct", label)

    def test_menu_handles_missing_expiry_among_resets(self):
        from datetime import datetime
        from lib.indicator import CodexApp

        app = SimpleNamespace(
            _mi={key: Mock() for key in ("header", "account", "status", "resets")},
            _reset_menu=Mock(), _set_window_labels=Mock(), _on_redeem_reset=Mock(),
        )
        app._reset_menu.get_children.return_value = []
        with patch("lib.indicator.Gtk.MenuItem"):
            CodexApp._update_menu(app, {
                "plan_type": "plus", "email": "", "account_type": "chatgpt",
                "primary": None, "secondary": None, "ts": datetime(2026, 9, 24),
                "reset_credits": {"availableCount": 2, "credits": [
                    {"id": "credit-1", "status": "available", "expiresAt": 1790856000},
                    {"id": "credit-2", "status": "available", "expiresAt": None},
                ]},
            })
        self.assertEqual(app._reset_menu.append.call_count, 2)

    def test_worker_refreshes_after_broken_pipe_on_consume(self):
        from lib.indicator import CodexApp

        app = SimpleNamespace(_fetch_shutdown=False, _fetch_queue=Mock(), _client=Mock(),
                              _on_reset_error=Mock(), _on_reset_result=Mock(),
                              _on_data=Mock(), _on_error=Mock())
        app._fetch_queue.get.side_effect = ["credit-1", None]
        app._client.consume_reset.side_effect = BrokenPipeError("closed")
        app._client.fetch_all.side_effect = lambda: (setattr(app, "_fetch_shutdown", True) or {"source": "test"})
        with patch("lib.indicator.GLib.idle_add") as idle_add:
            CodexApp._fetch_worker(app)
        app._client.fetch_all.assert_called_once_with()
        self.assertTrue(any(call.args[0] is app._on_reset_error for call in idle_add.call_args_list))

    def test_menu_shows_resets_with_unix_timestamp_dates(self):
        from lib.indicator import CodexApp

        app = SimpleNamespace()
        app._mi = {key: Mock() for key in ("header", "account", "status", "resets")}
        app._reset_menu = Mock()
        app._reset_menu.get_children.return_value = []
        app._set_window_labels = Mock()
        app._on_redeem_reset = Mock()
        with patch("lib.indicator.Gtk.MenuItem") as menu_item:
            CodexApp._update_menu(app, {
                "plan_type": "plus", "email": "", "account_type": "chatgpt",
                "primary": None, "secondary": None,
                "ts": __import__("datetime").datetime(2026, 9, 24, 12, 0),
                "reset_credits": {"availableCount": 1, "credits": [{
                    "id": "credit-1", "status": "available", "title": "Full reset",
                    "grantedAt": 1788264000, "expiresAt": 1790856000,
                }]},
            })
        self.assertEqual(app._reset_menu.append.call_count, 1)
        self.assertIn("Sep", menu_item.call_args.kwargs["label"])
        self.assertIn("Oct", menu_item.call_args.kwargs["label"])

    def test_detail_window_lists_resets_and_buttons_use_existing_confirmation(self):
        from datetime import datetime
        from lib.indicator import Gtk
        from lib.detail import DetailWindow

        app = Gtk.Application()
        app.register()
        app._on_redeem_reset = Mock()
        window = DetailWindow(app)
        data = {
            "plan_type": "plus", "email": "", "account_type": "chatgpt",
            "primary": None, "secondary": None, "ts": datetime(2026, 9, 24),
            "reset_credits": {"availableCount": 1, "credits": [{
                "id": "credit-1", "status": "available", "title": "Full reset",
                "grantedAt": 1788264000, "expiresAt": 1790856000,
            }]},
        }
        try:
            window.update_data(data)
            labels = [w.get_text() for w in window._reset_rows.get_children() if isinstance(w, Gtk.Label)]
            self.assertTrue(any("Sep" in text and "Oct" in text for text in labels))
            zone = datetime.now().astimezone().tzname()
            self.assertTrue(any(zone in text for text in labels))
            buttons = [w for w in window._reset_rows.get_children() if isinstance(w, Gtk.Button)]
            self.assertEqual(len(buttons), 1)
            buttons[0].clicked()
            app._on_redeem_reset.assert_called_once_with(buttons[0], "credit-1")
            window.update_data({**data, "reset_credits": {"availableCount": 0, "credits": []}})
            self.assertFalse(any(isinstance(w, Gtk.Button) for w in window._reset_rows.get_children()))
        finally:
            window.destroy()

    def test_cancelled_confirmation_never_queues_redemption(self):
        from lib.indicator import CodexApp

        app = SimpleNamespace()
        app._on_redeem_reset = CodexApp._on_redeem_reset.__get__(app)
        app._win = None
        app._fetch_queue = Mock()
        app._redeeming = False
        app._data = {"reset_credits": {"credits": [{"id": "credit-1", "status": "available", "expiresAt": "2026-10-01T12:00:00Z"}]}}
        with patch("lib.indicator.Gtk.MessageDialog") as dialog:
            dialog.return_value.run.return_value = 0
            app._on_redeem_reset(None, "credit-1")
        app._fetch_queue.put.assert_not_called()
        dialog.return_value.destroy.assert_called_once()

    def test_reset_result_recognizes_app_server_success_code(self):
        from lib.indicator import CodexApp

        app = SimpleNamespace(_notify=Mock())
        CodexApp._on_reset_result(app, {"code": "alreadyRedeemed"})
        app._notify.assert_called_once_with("Codex reset used", "Usage is refreshing.")

    def test_confirmed_reset_queues_only_selected_credit(self):
        from lib.indicator import CodexApp, Gtk

        app = SimpleNamespace()
        app._on_redeem_reset = CodexApp._on_redeem_reset.__get__(app)
        app._win = None
        app._mi = {"resets": Mock()}
        app._set_status = Mock()
        app._start_fetch_worker = Mock()
        app._fetch_queue = Mock()
        app._data = {"reset_credits": {"credits": [{"id": "credit-1", "status": "available", "expiresAt": "2026-10-01T12:00:00Z"}]}}
        app._redeeming = False
        with patch("lib.indicator.Gtk.MessageDialog") as dialog:
            dialog.return_value.run.return_value = Gtk.ResponseType.ACCEPT
            app._on_redeem_reset(None, "credit-1")
        app._fetch_queue.put.assert_called_once_with("credit-1")
        dialog.return_value.set_default_response.assert_called_once_with(Gtk.ResponseType.CANCEL)

    def test_consumption_rejects_empty_credit_id(self):
        with self.assertRaises(APIError):
            APIClient().consume_reset("")


if __name__ == "__main__":
    unittest.main()
