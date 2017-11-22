#!/usr/bin/env python

if __name__ == '__main__':
    try:
        from management import execute_from_command_line
    except ImportError:
        raise

    execute_from_command_line()
