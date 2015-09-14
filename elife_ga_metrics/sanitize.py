"""simple script that santizes the `output` directory.
works even if no santitation required."""

import sys, os, main, json
from os.path import join

def do():
    for dirname in os.listdir(main.OUTPUT_DIR):
        for filename in os.listdir(join(main.OUTPUT_DIR, dirname)):
            path = join(main.OUTPUT_DIR, dirname, filename)
            if path.endswith('.json'):
                sys.stdout.write('santizing %s' % path)
                main.write_results( \
                    main.sanitize_ga_response(json.load(open(path, 'r'))), \
                    path)
                sys.stdout.write(" ...done\n")
                sys.stdout.flush()

if __name__ == '__main__':
    do()
