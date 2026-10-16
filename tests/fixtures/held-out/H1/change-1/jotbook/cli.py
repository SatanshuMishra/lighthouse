import argparse
import importlib
import pkgutil

from jotbook import commands


def shared_options():
    shared = argparse.ArgumentParser(add_help=False)
    shared.add_argument("--notebook", help="the notes file to read and write")
    return shared


def command_modules():
    names = sorted(info.name for info in pkgutil.iter_modules(commands.__path__))
    return [importlib.import_module("jotbook.commands." + name) for name in names]


def build_parser():
    parser = argparse.ArgumentParser(prog="jotbook")
    subparsers = parser.add_subparsers(dest="command", required=True)
    shared = shared_options()
    for module in command_modules():
        module.register(subparsers, shared)
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    return args.handler(args)
