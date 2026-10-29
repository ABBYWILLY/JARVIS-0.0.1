"""Bounded process/startup regressions, without models or audio devices."""
import multiprocessing as mp
from pathlib import Path
import sqlite3
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from jarvis.config import Settings
from jarvis.storage import Store
from jarvis.worker import Worker, run_worker


class WorkerLifecycleTests(unittest.TestCase):
    def test_failed_spawn_closes_unstarted_process_and_queue_then_allows_retry(self):
        worker = Worker()
        self.addCleanup(worker.stop)
        channels = []
        original_queue = worker.context.Queue

        def channel(*args, **kwargs):
            result = original_queue(*args, **kwargs)
            channels.append(result)
            return result

        process = worker.context.Process(target=run_worker)
        with patch.object(worker.context, "Queue", side_effect=channel), \
                patch.object(worker.context, "Process", return_value=process), \
                patch.object(process, "start", side_effect=OSError("spawn unavailable")):
            with self.assertRaisesRegex(OSError, "spawn unavailable"):
                worker.start("models", Settings())
        self.assertIsNone(worker.process)
        self.assertIsNone(worker.queue)
        self.assertTrue(process._closed)
        self.assertTrue(all(item._closed for item in channels))
        self.run_error_worker(worker)

    def test_process_allocation_failure_also_closes_allocated_queue(self):
        worker = Worker()
        channel = Mock()
        with patch.object(worker.context, "Queue", return_value=channel), \
                patch.object(worker.context, "Process", side_effect=OSError("allocation")):
            with self.assertRaisesRegex(OSError, "allocation"):
                worker.start("models", Settings())
        channel.cancel_join_thread.assert_called_once()
        channel.close.assert_called_once()
        self.assertIsNone(worker.queue)
        worker.stop()

    def test_live_child_is_retained_if_termination_and_kill_fail(self):
        worker = Worker()
        process, channel = Mock(pid=123), Mock()
        process.is_alive.return_value = True
        worker.process, worker.queue = process, channel
        with self.assertRaisesRegex(RuntimeError, "Ollama"):
            worker.stop()
        self.assertIs(worker.process, process)
        self.assertIs(worker.queue, channel)
        process.close.assert_not_called()
        channel.close.assert_not_called()
        with patch.object(worker.context, "Queue") as allocate:
            with self.assertRaises(RuntimeError):
                worker.start("models", Settings())
            allocate.assert_not_called()
        process.is_alive.return_value = False
        worker.stop()
        self.assertIsNone(worker.process)
        channel.close.assert_called_once()

    def run_error_worker(self, worker):
        worker.start("invalid-operation", Settings())
        process = worker.process
        events = []
        deadline = time.monotonic() + 5
        try:
            while not events and time.monotonic() < deadline:
                events.extend(worker.poll())
                time.sleep(.01)
            self.assertEqual([event.kind for event in events], ["error"])
        finally:
            worker.stop()
        self.assertTrue(process._closed)

    def test_ten_real_spawn_stop_cycles_leave_no_child_or_queue(self):
        original = {child.pid for child in mp.active_children()}
        worker = Worker()
        self.addCleanup(worker.stop)
        for _ in range(10):
            self.run_error_worker(worker)
            self.assertIsNone(worker.process)
            self.assertIsNone(worker.queue)
        self.assertEqual({child.pid for child in mp.active_children()}, original)


class StartupFailureTests(unittest.TestCase):
    def test_invalid_preferences_close_database_and_preserve_archive(self):
        import run
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "jarvis.sqlite3"
            store = Store(path)
            sid = store.new_session()
            mid = store.begin_turn(sid, "Conserver mon archive", "local")
            store.update_response(mid, "Fragment à conserver")
            with store.db:
                store.db.execute("INSERT INTO settings VALUES ('profile', '{invalid')")
            root = Mock()
            with patch("sys.argv", ["run.py"]), \
                    patch("tkinter.Tk", return_value=root), \
                    patch("tkinter.messagebox.showerror") as error, \
                    patch("jarvis.config.data_directory", return_value=Path(directory)), \
                    patch("jarvis.storage.Store", return_value=store):
                self.assertEqual(run.main(), 1)
            self.assertIn("JSONDecodeError", error.call_args.args[1])
            root.destroy.assert_called_once()
            with self.assertRaises(sqlite3.ProgrammingError):
                store.db.execute("SELECT 1")
            reopened = Store(path)
            try:
                self.assertEqual(reopened.message(mid)["content"], "Fragment à conserver")
                self.assertEqual(reopened.message(mid)["status"], "interrupted")
                self.assertEqual(reopened.db.execute("SELECT value FROM settings").fetchone()[0], "{invalid")
                self.assertEqual(reopened.db.execute("PRAGMA integrity_check").fetchone()[0], "ok")
            finally:
                reopened.close()

    def test_app_close_keeps_owner_alive_when_child_stop_fails(self):
        from jarvis.ui import App
        owner = SimpleNamespace(closed=False, voice=Mock(), presence=Mock(), worker=Mock(),
                                operation=None, set_status=Mock(), root=Mock(), poll_id="poll",
                                markdown=Mock(), cognitive_view=Mock(), store=Mock(),
                                navigation_font=object(), input_font=object())
        owner.presence.close.return_value = False
        App.close(owner)
        self.assertFalse(owner.closed)
        owner.root.destroy.assert_not_called()
        owner.worker.stop.assert_not_called()
        owner.presence.close.return_value = True
        owner.worker.stop.side_effect = RuntimeError("live inference")
        App.close(owner)
        self.assertFalse(owner.closed)
        owner.root.destroy.assert_not_called()
        self.assertIn("live inference", owner.set_status.call_args.args[0])
        owner.worker.stop.side_effect = None
        App.close(owner)
        self.assertTrue(owner.closed)
        owner.root.destroy.assert_called_once()
        owner.store.close.assert_called_once()
        App.close(owner)
        owner.root.destroy.assert_called_once()
