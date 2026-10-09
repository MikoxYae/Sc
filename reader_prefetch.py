"""Optional one-chapter reader-cache warmer for already published Telegram PDFs."""
import argparse
import time

from chapter_reader import prepare


def main():
    parser = argparse.ArgumentParser(description='Prepare a published chapter cache before visitors open it.')
    parser.add_argument('--category', required=True)
    parser.add_argument('--slug', required=True)
    parser.add_argument('--chapter', required=True)
    parser.add_argument('--timeout', type=int, default=1200)
    args = parser.parse_args()
    limit = time.monotonic() + min(3600, max(30, args.timeout))
    while time.monotonic() < limit:
        status = prepare(args.category, args.slug, args.chapter)
        state = status.get('status')
        if state == 'ready':
            print('READY:', status['pages'], 'pages cached; future website reads can start immediately.')
            return
        if state == 'error':
            parser.exit(1, 'FAILED: ' + status.get('error', 'Unknown error') + '\n')
        print('PREPARING:', status.get('stage', 'queued'), 'pages:', status.get('pages_ready', 0),
              '/', status.get('pages_total', '?'), flush=True)
        time.sleep(3)
    parser.exit(1, 'TIMEOUT: cache warmup did not complete. Check reader logs.\n')


if __name__ == '__main__':
    main()
