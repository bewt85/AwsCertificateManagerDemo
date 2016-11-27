#!/bin/bash

set -eu -o pipefail

export ZIP_FILE=$(pwd)/ElbBackendCertificates_$(date +%Y%m%d%H%M).zip
zip $ZIP_FILE lambda_function.py
if [[ ! -d lambda_env ]]; then
    virtualenv lambda_env
fi
lambda_env/bin/pip install -r requirements.txt
pushd lambda_env/lib/python2.7/site-packages/
find -type f | zip $ZIP_FILE -@
popd
echo "Created $ZIP_FILE for upload"
