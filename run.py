import os
import sys
import traceback


def launch():
    """Keep a failed windowed build check from opening a hidden error dialog."""
    if '--self-test' not in sys.argv:
        from fileback.app import main
        main()
        return
    log_path = os.environ.get('FILEBACK_SELF_TEST_LOG')
    stream = open(log_path, 'w', encoding='utf-8') if log_path else None
    try:
        if stream:
            stream.write('Importing application\n')
            stream.flush()
        from fileback.app import main
        if stream:
            stream.write('Running packaged check\n')
            stream.flush()
        main()
        if stream:
            stream.write('Passed\n')
    except Exception:
        if stream:
            traceback.print_exc(file=stream)
        raise SystemExit(1) from None
    finally:
        if stream:
            stream.close()

if __name__ == '__main__':
    launch()
