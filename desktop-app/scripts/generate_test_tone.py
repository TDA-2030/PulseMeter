#!/usr/bin/env python3
"""
Generate a mono WAV test tone for PulseMeter calibration.

Examples:
    python scripts/generate_test_tone.py
    python scripts/generate_test_tone.py --dbfs -18 --freq 1000 --duration 10
"""

import argparse
import math
import wave
from pathlib import Path


def generate_sine_wave(
    output_path: Path,
    frequency: float,
    duration: float,
    sample_rate: int,
    dbfs: float,
) -> None:
    full_scale = 32767
    amplitude = (10.0 ** (dbfs / 20.0)) * full_scale
    frame_count = int(duration * sample_rate)

    with wave.open(str(output_path), "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)

        frames = bytearray()
        for i in range(frame_count):
            sample = math.sin(2.0 * math.pi * frequency * (i / sample_rate))
            value = int(max(-full_scale, min(full_scale, round(sample * amplitude))))
            frames.extend(value.to_bytes(2, byteorder="little", signed=True))

        wav_file.writeframes(frames)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate a calibration sine-wave WAV file.")
    parser.add_argument("--freq", type=float, default=1000.0, help="Tone frequency in Hz.")
    parser.add_argument("--duration", type=float, default=10.0, help="Duration in seconds.")
    parser.add_argument("--sample-rate", type=int, default=48000, help="Sample rate in Hz.")
    parser.add_argument("--dbfs", type=float, default=-18.0, help="Signal level in dBFS.")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("test-tone-1khz--18dbfs.wav"),
        help="Output WAV file path.",
    )
    args = parser.parse_args()

    generate_sine_wave(
        output_path=args.output,
        frequency=args.freq,
        duration=args.duration,
        sample_rate=args.sample_rate,
        dbfs=args.dbfs,
    )
    print(f"Generated {args.output} ({args.freq} Hz, {args.dbfs} dBFS, {args.duration}s)")


if __name__ == "__main__":
    main()
