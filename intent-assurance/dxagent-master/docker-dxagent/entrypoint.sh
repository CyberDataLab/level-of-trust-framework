#!/bin/bash
set -e

# Generate certificates
cd certs
./gen_certs.sh 0.0.0.0 0.0.0.0

cd /app

sudo python3 dxagent start

tail -f /dev/null