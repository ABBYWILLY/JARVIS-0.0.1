"""Spawn-safe inference boundary. Bounded IPC; no DB or system tools in worker."""
import multiprocessing as mp
from queue import Empty

from .config import Settings
from .ollama import Event, Ollama, friendly_error


def run_worker(outbox, operation, profile, messages):
    try:
        settings = Settings(**profile).validate()
        provider = Ollama(settings.endpoint)
        if operation == "models":
            outbox.put(Event("models", provider.models()))
        elif operation == "chat":
            provider.on_request_accepted = lambda stamp: outbox.put(Event("request_accepted", {"accepted_at": stamp}))
            for event in provider.chat(messages, settings):
                outbox.put(event)
        else:
            raise ValueError("Unknown worker operation")
    except Exception as exc:
        outbox.put(Event("error", friendly_error(exc)))


class Worker:
    def __init__(self):
        self.context = mp.get_context("spawn")
        self.process = None
        self.queue = None

    def start(self, operation, settings, messages=None):
        self.stop()
        try:
            self.queue = self.context.Queue(maxsize=128)
            self.process = self.context.Process(target=run_worker,
                args=(self.queue, operation, settings.to_dict(), messages), daemon=True)
            self.process.start()
        except BaseException:
            # Allocation/spawn is transactional, including a process with no PID.
            self.stop()
            raise

    def poll(self):
        events = []
        if self.queue is not None:
            for _ in range(128):
                try:
                    events.append(self.queue.get_nowait())
                except Empty:
                    break
        return events

    def alive(self):
        return self.process is not None and self.process.is_alive()

    def stop(self):
        if self.process is not None:
            if self.process.pid is not None:
                if self.process.is_alive():
                    self.process.terminate()
                self.process.join(timeout=0.2)
                if self.process.is_alive():
                    self.process.kill()
                    self.process.join(timeout=0.2)
                if self.process.is_alive():
                    # Retain ownership: a failed stop must not permit a second worker.
                    raise RuntimeError("Le processus Ollama n'a pas pu être fermé ; réessayez l'arrêt.")
            self.process.close()
            self.process = None
        if self.queue is not None:
            self.queue.cancel_join_thread()
            self.queue.close()
            self.queue = None
