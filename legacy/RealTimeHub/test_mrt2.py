#!/usr/bin/env python3
"""Validate Magenta RealTime 2 installation and generate a short audio sample."""

import argparse
import logging
import sys

try:
    import magenta_rt
    from magenta_rt import paths
except ImportError as error:
    print('ERROR: magenta_rt is not installed.')
    print('Install RealTimeHub dependencies first:')
    print('  cd RealTimeHub')
    print('  python3 -m venv .venv')
    print('  source .venv/bin/activate')
    print('  pip install -r requirements.txt')
    raise SystemExit(1) from error


RUNTIME_CLASSES = ('MagentaRT2Mlxfn', 'MagentaRT2Mlx', 'MagentaRT2Jax')


def select_runtime_class():
    for name in RUNTIME_CLASSES:
        cls = getattr(magenta_rt, name, None)
        if cls is not None:
            return name, cls
    raise RuntimeError('No supported Magenta RT2 runtime class was found in the magenta_rt package.')


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description='Magenta RT2 runtime validation script.')
    parser.add_argument('--prompt', default='gentle dance groove', help='Style prompt for embedding generation.')
    parser.add_argument('--duration', type=float, default=2.0, help='Duration in seconds to generate.')
    parser.add_argument('--model', default=None, help='Model size / name to load (defaults to package default).')
    return parser


def main() -> int:
    parser = build_arg_parser()
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format='[test_mrt2] %(message)s')

    runtime_name, runtime_cls = select_runtime_class()
    model_name = args.model or paths.DEFAULT_MODEL_NAME
    logging.info('Selected runtime: %s', runtime_name)
    logging.info('Model name: %s', model_name)
    logging.info('Magenta home directory: %s', paths.magenta_home())

    runtime = runtime_cls(size=model_name)
    logging.info('Runtime instance created: %s', runtime.__class__.__name__)

    style_embedding = runtime.embed_style(args.prompt, use_mapper=True)
    logging.info('Style embedding generated: shape=%s', getattr(style_embedding, 'shape', None))

    frames = max(1, int(args.duration * 25))
    wav, state = runtime.generate(style=style_embedding, frames=frames)

    output_dir = paths.outputs_dir()
    output_path = output_dir / 'test_mrt2.wav'
    wav.write(str(output_path))

    logging.info('Generated waveform saved to: %s', output_path)
    logging.info('Output duration: %.2f seconds', wav.seconds)
    logging.info('Sample count: %s', wav.num_samples)
    logging.info('Model state object type: %s', type(state).__name__)

    return 0


if __name__ == '__main__':
    raise SystemExit(main())
