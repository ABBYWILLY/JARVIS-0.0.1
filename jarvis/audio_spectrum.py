"""Bounded PCM frequency bands, independent of rendering and audio backends.

Input is normalized mono PCM at its actual sample rate. A Hann-windowed FFT
measures energy in 80–350, 350–2500 and 2500–8000 Hz; it is not three aliases
for overall RMS. The worker is optional and does the transform off the UI/audio
callback thread. No dependency, device or thread is loaded at module import.
"""
from functools import lru_cache
import math
import threading
import time


MAX_SAMPLES = 4096
ZERO_BANDS = (0., 0., 0.)


def _rate(value):
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 192000:
        raise ValueError("Le spectre attend une fréquence PCM entière entre 1 et 192 000 Hz.")
    return value


def _samples(values):
    # Retain only the newest bounded analysis window, never an unbounded queue
    # or a recording. Typical 32-ms blocks at 16/22/48 kHz use 512/706/1536 PCM.
    values = tuple(float(value) for value in values[-MAX_SAMPLES:])
    if not all(math.isfinite(value) for value in values):
        raise ValueError("Le PCM du spectre contient une valeur non finie.")
    return values


@lru_cache(maxsize=16)
def _window(count):
    weights = tuple(.5 - .5 * math.cos(math.tau * index / (count - 1))
                    for index in range(count))
    return weights, sum(weight * weight for weight in weights)


@lru_cache(maxsize=12)
def _twiddles(size):
    return tuple(complex(math.cos(-math.tau * index / size),
                         math.sin(-math.tau * index / size)) for index in range(size // 2))


class PCMSpectrum:
    """Hann-window energy bands, RMS-normalized to [0, 1], with DC excluded.

    Uses at most 4096 source samples and zero-pads to the next power of two.
    At unusually high sample rates the cap shortens the analysis window; this
    is an intentionally coarse visual spectrum, not a studio audio analyzer.
    Envelopes belong to the consumer, so there is no hidden audio history.
    """

    def analyze(self, samples, sample_rate):
        sample_rate = _rate(sample_rate)
        samples = _samples(samples)
        count = len(samples)
        if count < 4 or max(samples) == min(samples):
            return ZERO_BANDS
        weights, weight_energy = _window(count)
        mean = sum(samples) / count
        size = 1 << (count - 1).bit_length()
        values = [complex((value - mean) * weight, 0.)
                  for value, weight in zip(samples, weights)] + [0j] * (size - count)
        # In-place radix-2 FFT; all work and cache sizes have explicit caps.
        reverse = 0
        for index in range(1, size):
            bit = size >> 1
            while reverse & bit:
                reverse ^= bit
                bit >>= 1
            reverse ^= bit
            if index < reverse:
                values[index], values[reverse] = values[reverse], values[index]
        span = 2
        while span <= size:
            half, twiddles = span // 2, _twiddles(span)
            for start in range(0, size, span):
                for index, twiddle in enumerate(twiddles):
                    first = values[start + index]
                    second = values[start + index + half] * twiddle
                    values[start + index] = first + second
                    values[start + index + half] = first - second
            span *= 2
        energy = [0., 0., 0.]
        for index in range(1, size // 2 + 1):
            frequency = index * sample_rate / size
            if not 80 <= frequency <= 8000:
                continue
            band = 0 if frequency < 350 else 1 if frequency < 2500 else 2
            value = values[index]
            energy[band] += (value.real ** 2 + value.imag ** 2) * (1 if index == size // 2 else 2)
        normalizer = size * weight_energy
        return tuple(min(1., math.sqrt(max(0., value / normalizer))) for value in energy)


class SpectrumWorker:
    """Latest-window-only analysis, <=25 Hz, with explicit generation checks.

    ``timestamp`` and ``snapshot(now)`` use the caller's same monotonic/recording
    clock. Analysis pacing uses a separate real monotonic clock. Results expire
    after 200 ms by default; an exception is visible through ``diagnostic`` and
    does not kill the worker. Reset invalidates both queued and in-flight data.
    """

    def __init__(self, *, frequency=25., lifetime=.2, analyzer=None, clock=time.monotonic):
        if not math.isfinite(frequency) or not 0 < frequency <= 25:
            raise ValueError("La cadence du spectre doit être comprise entre 0 et 25 Hz.")
        if not math.isfinite(lifetime) or not 0 < lifetime <= 1:
            raise ValueError("La durée de validité du spectre doit être comprise entre 0 et 1 s.")
        self._interval, self._lifetime = 1 / frequency, lifetime
        self._analyzer, self._clock = analyzer or PCMSpectrum(), clock
        self._condition = threading.Condition()
        self._generation = 0
        self._revision = 0
        self._pending = self._result = None
        self._last_submitted = float("-inf")
        self._closed = False
        self._diagnostic = ""
        self._analysis_count = 0
        self._thread = threading.Thread(target=self._run, name="jarvis-pcm-spectrum", daemon=True)
        self._thread.start()

    @staticmethod
    def _generation_value(generation):
        if isinstance(generation, bool) or not isinstance(generation, int) or generation < 0:
            raise ValueError("La génération du spectre doit être un entier positif ou nul.")
        return generation

    @property
    def diagnostic(self):
        with self._condition:
            return self._diagnostic

    @property
    def analysis_count(self):
        with self._condition:
            return self._analysis_count

    @property
    def pending_count(self):
        with self._condition:
            return int(self._pending is not None)

    @property
    def alive(self):
        return self._thread.is_alive()

    def submit(self, samples, sample_rate, timestamp, generation=0):
        sample_rate, generation = _rate(sample_rate), self._generation_value(generation)
        if not math.isfinite(timestamp):
            raise ValueError("Le timestamp PCM du spectre doit être fini.")
        samples = _samples(samples)
        with self._condition:
            if self._closed:
                raise RuntimeError("Le worker spectral est fermé.")
            if generation != self._generation or timestamp < self._last_submitted:
                return False
            self._last_submitted = timestamp
            self._pending = (samples, sample_rate, timestamp, generation, self._revision)
            self._condition.notify_all()
            return True

    def snapshot(self, now, generation=0):
        generation = self._generation_value(generation)
        if not math.isfinite(now):
            raise ValueError("L'horloge du spectre doit être finie.")
        with self._condition:
            if self._closed or generation != self._generation or self._result is None:
                return ZERO_BANDS
            timestamp, bands = self._result
            return bands if 0 <= now - timestamp <= self._lifetime else ZERO_BANDS

    def reset(self, generation=0):
        generation = self._generation_value(generation)
        with self._condition:
            if self._closed or generation < self._generation:
                return False
            self._generation, self._revision = generation, self._revision + 1
            self._pending = self._result = None
            self._last_submitted = float("-inf")
            self._diagnostic = ""
            self._condition.notify_all()
            return True

    def _run(self):
        next_analysis = float("-inf")
        while True:
            with self._condition:
                while not self._closed:
                    if self._pending is None:
                        self._condition.wait()
                    else:
                        remaining = next_analysis - self._clock()
                        if remaining > 0:
                            self._condition.wait(remaining)
                        else:
                            frame, self._pending = self._pending, None
                            next_analysis = self._clock() + self._interval
                            break
                if self._closed:
                    return
            samples, rate, timestamp, generation, revision = frame
            try:
                bands = tuple(self._analyzer.analyze(samples, rate))
                if len(bands) != 3 or not all(math.isfinite(value) and 0 <= value <= 1 for value in bands):
                    raise ValueError("L'analyse spectrale doit produire trois bandes finies entre 0 et 1.")
                diagnostic = ""
            except Exception as error:
                bands = ZERO_BANDS
                diagnostic = f"Spectre audio indisponible : {type(error).__name__}: {error}"
            with self._condition:
                self._analysis_count += 1
                if not self._closed and generation == self._generation and revision == self._revision:
                    self._result = (timestamp, bands)
                    self._diagnostic = diagnostic
                self._condition.notify_all()

    def close(self, timeout=2.):
        if not math.isfinite(timeout) or not 0 < timeout <= 5:
            raise ValueError("Le délai de fermeture du spectre doit être compris entre 0 et 5 s.")
        with self._condition:
            self._closed = True
            self._pending = self._result = None
            self._condition.notify_all()
        self._thread.join(timeout)
        if self._thread.is_alive():
            raise RuntimeError("Le worker spectral ne s'est pas arrêté dans le délai prévu.")
